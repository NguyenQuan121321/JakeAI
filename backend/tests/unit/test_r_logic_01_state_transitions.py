"""R-LOGIC-01 — State Transitions Verification Test Suite.

Proves the orchestration state machine (Task / Run / Plan / Step / Approval /
Verification) is deterministic, valid, and terminal-safe at the highest
realistic boundary:

ST-A  Transition-matrix completeness: every allowed transition of the
      documented state machine is accepted; every forbidden transition is
      rejected — both through the explicit transition API and through raw
      status assignment (no write path may bypass the machine).
ST-B  Named forbidden transitions from the task specification: FAILED→COMPLETED,
      REJECTED→EXECUTING, CANCELLED→EXECUTING, TIMEOUT→COMPLETED and approval
      bypass (WAITING_APPROVAL→COMPLETED) can never be persisted or executed.
ST-C  Terminal-state survival under late cancellation: a cancellation delivered
      after a run reached a terminal state must not corrupt the terminal status.
ST-D  Lifecycle observability: the canonical engine actually traverses
      VERIFYING and REPLANNING (documented states, previously unreachable).
ST-E  Retry bounding: step recovery (retry / agent switch) is bounded in
      attempt count; verification revisions are bounded; a terminal-failed run
      can only be retried as a NEW run.
ST-F  Approval and cancellation semantics at the HTTP boundary: approval
      decisions, rejection finality, cancel during approval wait, no approval
      bypass, no resurrection of cancelled runs.
ST-G  Checkpoint / resume semantics: restored pre-execution runs re-enter the
      machine legally; terminal states survive checkpoint round-trips.

Classification notes: the platform runtime is exercised through the real
FastAPI HTTP boundary (ASGI transport + real JWT auth); upstream model calls
are controlled doubles at the module boundary (they verify state-machine
behavior only, not live provider integration).
"""

from __future__ import annotations

import asyncio
import json
import time
import uuid
from typing import TYPE_CHECKING, Any
from unittest.mock import AsyncMock, patch

import jwt as pyjwt
import pytest
from httpx import ASGITransport, AsyncClient

if TYPE_CHECKING:
    from collections.abc import AsyncGenerator


from app.agent.approvals.manager import ApprovalManager
from app.agent.approvals.models import ApprovalStatus
from app.agent.backends.base import (
    AgentBackendInterface,
    BackendRequest,
    BackendResponse,
    BackendStreamChunk,
)
from app.agent.domain.contracts import (
    TaskSpec,
    VerificationResult,
    VerificationVerdict,
)
from app.agent.execution.engine import ExecutionEngine
from app.agent.memory.manager import AgentMemoryManager
from app.agent.planning.models import NextAction, NextActionType, Plan
from app.agent.planning.models import PlanStep as PlanningPlanStep
from app.agent.planning.planner import BoundedPlanner
from app.agent.recovery.recovery import RecoveryLimits
from app.agent.runtime.manager import AgentRuntimeManager
from app.agent.runtime.models import AgentConfig
from app.agent.runtime.runner import AgentRunner
from app.agent.state.checkpoint import CheckpointManager
from app.agent.state.models import (
    RunState,
    RunStatus,
    TaskState,
    TaskStatus,
)
from app.agent.tools.base import Tool, ToolMetadata, ToolResult, ToolRiskLevel
from app.agent.tools.registry import ToolRegistry
from app.agent.verification.verifier import CanonicalVerifier
from app.core.config import get_settings
from app.main import app

# ===========================================================================
# Documented state-machine contracts (independent source of truth)
# ===========================================================================

EXPECTED_RUN_MATRIX: dict[RunStatus, set[RunStatus]] = {
    RunStatus.CREATED: {
        RunStatus.PLANNING,
        RunStatus.READY,
        RunStatus.RUNNING,
        RunStatus.FAILED,
        RunStatus.CANCELLED,
    },
    RunStatus.PLANNING: {
        RunStatus.READY,
        RunStatus.RUNNING,
        RunStatus.FAILED,
        RunStatus.CANCELLED,
    },
    RunStatus.READY: {
        RunStatus.RUNNING,
        RunStatus.EXECUTING,
        RunStatus.FAILED,
        RunStatus.CANCELLED,
    },
    RunStatus.RUNNING: {
        RunStatus.EXECUTING,
        RunStatus.WAITING_APPROVAL,
        RunStatus.PAUSED_APPROVAL,
        RunStatus.VERIFYING,
        RunStatus.COMPLETED,
        RunStatus.FAILED,
        RunStatus.CANCELLED,
        RunStatus.REJECTED,
        RunStatus.TIMEOUT,
    },
    RunStatus.EXECUTING: {
        RunStatus.RUNNING,
        RunStatus.WAITING_APPROVAL,
        RunStatus.PAUSED_APPROVAL,
        RunStatus.VERIFYING,
        RunStatus.COMPLETED,
        RunStatus.FAILED,
        RunStatus.CANCELLED,
        RunStatus.REJECTED,
        RunStatus.TIMEOUT,
    },
    RunStatus.WAITING_APPROVAL: {
        RunStatus.RUNNING,
        RunStatus.EXECUTING,
        RunStatus.REJECTED,
        RunStatus.CANCELLED,
        RunStatus.FAILED,
    },
    RunStatus.PAUSED_APPROVAL: {
        RunStatus.RUNNING,
        RunStatus.EXECUTING,
        RunStatus.REJECTED,
        RunStatus.CANCELLED,
        RunStatus.FAILED,
    },
    RunStatus.VERIFYING: {
        RunStatus.COMPLETED,
        RunStatus.REPLANNING,
        RunStatus.PLANNING,
        RunStatus.RUNNING,
        RunStatus.FAILED,
        RunStatus.REJECTED,
        RunStatus.CANCELLED,
    },
    # After a replan, execution resumes (RL01-F-03 wiring).
    RunStatus.REPLANNING: {
        RunStatus.PLANNING,
        RunStatus.READY,
        RunStatus.RUNNING,
        RunStatus.EXECUTING,
        RunStatus.FAILED,
        RunStatus.CANCELLED,
    },
}

TERMINAL_RUN_STATES = {
    RunStatus.COMPLETED,
    RunStatus.FAILED,
    RunStatus.CANCELLED,
    RunStatus.REJECTED,
    RunStatus.TIMEOUT,
}

EXPECTED_TASK_MATRIX: dict[TaskStatus, set[TaskStatus]] = {
    TaskStatus.PENDING: {
        TaskStatus.PLANNING,
        TaskStatus.READY,
        TaskStatus.RUNNING,
        TaskStatus.FAILED,
        TaskStatus.REJECTED,
        TaskStatus.CANCELLED,
    },
    TaskStatus.PLANNING: {
        TaskStatus.READY,
        TaskStatus.RUNNING,
        TaskStatus.FAILED,
        TaskStatus.CANCELLED,
    },
    TaskStatus.READY: {
        TaskStatus.RUNNING,
        TaskStatus.EXECUTING,
        TaskStatus.FAILED,
        TaskStatus.CANCELLED,
    },
    TaskStatus.RUNNING: {
        TaskStatus.EXECUTING,
        TaskStatus.WAITING_APPROVAL,
        TaskStatus.PAUSED_APPROVAL,
        TaskStatus.VERIFYING,
        TaskStatus.COMPLETED,
        TaskStatus.FAILED,
        TaskStatus.CANCELLED,
        TaskStatus.REJECTED,
        TaskStatus.TIMEOUT,
    },
    TaskStatus.EXECUTING: {
        TaskStatus.RUNNING,
        TaskStatus.WAITING_APPROVAL,
        TaskStatus.PAUSED_APPROVAL,
        TaskStatus.VERIFYING,
        TaskStatus.COMPLETED,
        TaskStatus.FAILED,
        TaskStatus.CANCELLED,
        TaskStatus.REJECTED,
        TaskStatus.TIMEOUT,
    },
    TaskStatus.WAITING_APPROVAL: {
        TaskStatus.RUNNING,
        TaskStatus.EXECUTING,
        TaskStatus.REJECTED,
        TaskStatus.CANCELLED,
        TaskStatus.FAILED,
    },
    TaskStatus.PAUSED_APPROVAL: {
        TaskStatus.RUNNING,
        TaskStatus.EXECUTING,
        TaskStatus.REJECTED,
        TaskStatus.CANCELLED,
        TaskStatus.FAILED,
    },
    TaskStatus.VERIFYING: {
        TaskStatus.COMPLETED,
        TaskStatus.REPLANNING,
        TaskStatus.PLANNING,
        TaskStatus.RUNNING,
        TaskStatus.FAILED,
        TaskStatus.REJECTED,
        TaskStatus.CANCELLED,
    },
    TaskStatus.REPLANNING: {
        TaskStatus.PLANNING,
        TaskStatus.READY,
        TaskStatus.RUNNING,
        TaskStatus.EXECUTING,
        TaskStatus.FAILED,
        TaskStatus.CANCELLED,
    },
}

TERMINAL_TASK_STATES = {
    TaskStatus.COMPLETED,
    TaskStatus.FAILED,
    TaskStatus.CANCELLED,
    TaskStatus.REJECTED,
    TaskStatus.TIMEOUT,
}


# ===========================================================================
# Shared test doubles
# ===========================================================================


class MockControllableBackend(AgentBackendInterface):
    """Deterministic backend that never touches the network."""

    def __init__(
        self,
        content: str = "Analysis verified and mathematically sound.",
    ) -> None:
        super().__init__()
        self.content = content
        self.calls: list[BackendRequest] = []

    async def generate(self, request: BackendRequest) -> BackendResponse:
        self.calls.append(request)
        return BackendResponse(
            content=self.content,
            model="gemini-1.5-flash",
            provider="google",
            input_tokens=42,
            output_tokens=18,
            cost_usd=0.00012,
        )

    async def generate_stream(
        self, request: BackendRequest
    ) -> AsyncGenerator[BackendStreamChunk, None]:
        yield BackendStreamChunk(delta_content=self.content, is_complete=True)


class ScriptedVerifier(CanonicalVerifier):
    """Verifier returning scripted verdicts (last one repeats)."""

    def __init__(self, verdicts: list[VerificationVerdict]) -> None:
        super().__init__()
        self._verdicts = list(verdicts)
        self.calls = 0

    def verify_execution(self, **kwargs: Any) -> VerificationResult:
        self.calls += 1
        verdict = (
            self._verdicts.pop(0) if len(self._verdicts) > 1 else self._verdicts[0]
        )
        return VerificationResult(verdict=verdict, reason="scripted verdict")


class AlwaysFailingTool(Tool):
    """Safe tool that always fails (drives the recovery path)."""

    def __init__(self, tracker: dict[str, int]) -> None:
        self._tracker = tracker

    @property
    def metadata(self) -> ToolMetadata:
        return ToolMetadata(
            name="always_fails",
            description="Deterministically failing safe tool",
            input_schema={"type": "object", "properties": {}},
            risk_level=ToolRiskLevel.READ_ONLY,
            requires_approval=False,
        )

    async def execute(self, arguments: dict, context=None) -> ToolResult:
        self._tracker["executions"] = self._tracker.get("executions", 0) + 1
        return ToolResult(success=False, error="simulated permanent tool failure")


class ScriptedActionPlanner(BoundedPlanner):
    """Platform-loop planner returning scripted next actions (last repeats)."""

    def __init__(self, backend: AgentBackendInterface, actions: list[NextAction]):
        super().__init__(backend=backend)
        self._actions = list(actions)

    def create_initial_plan(
        self,
        goal: str,
        available_tools=None,
        tenant_id: str = "default",
        task_id: str | None = None,
    ) -> Plan:
        return Plan(task_id=task_id or "task_platform", goal=goal, steps=[])

    async def determine_next_action(self, **kwargs: Any) -> NextAction:
        if len(self._actions) > 1:
            return self._actions.pop(0)
        return self._actions[0]


def make_engine_step(
    step_id: str,
    *,
    tool_name: str | None = None,
    dependencies: list[str] | None = None,
) -> PlanningPlanStep:
    return PlanningPlanStep(
        step_id=step_id,
        description=f"Step {step_id}",
        candidate_agents=["general_agent"],
        required_tools=[tool_name] if tool_name else [],
        tool_name=tool_name,
        tool_args={},
        dependencies=dependencies or [],
    )


def make_task_spec(
    tenant: str = "tenant-logic-01", timeout_seconds: float | None = None
) -> TaskSpec:
    metadata: dict[str, Any] = {}
    if timeout_seconds is not None:
        metadata["timeout_seconds"] = timeout_seconds
    return TaskSpec(
        task_id=f"task_{uuid.uuid4().hex[:10]}",
        tenant_id=tenant,
        user_id="user-logic-01",
        goal="Verify orchestration state machine",
        roles=["operator"],
        permissions=["agent:execute", "tools:execute"],
        metadata=metadata,
    )


def fresh_engine(
    backend: AgentBackendInterface | None = None,
    plan: Plan | None = None,
    verifier: CanonicalVerifier | None = None,
    tool_registry: ToolRegistry | None = None,
) -> tuple[ExecutionEngine, CheckpointManager]:
    checkpoint_mgr = CheckpointManager()
    backend = backend or MockControllableBackend()
    kwargs: dict[str, Any] = {
        "backend": backend,
        "checkpoint_manager": checkpoint_mgr,
    }
    if plan is not None:

        class _FixedPlanner(BoundedPlanner):
            def __init__(self, backend: AgentBackendInterface, plan: Plan) -> None:
                super().__init__(backend=backend)
                self._plan = plan

            async def plan_task(
                self, task_spec: TaskSpec, available_tools=None
            ) -> Plan:
                self._plan.task_id = task_spec.task_id
                return self._plan.model_copy(deep=True)

        kwargs["planner"] = _FixedPlanner(backend, plan)
    if verifier is not None:
        kwargs["verifier"] = verifier
    if tool_registry is not None:
        kwargs["tool_registry"] = tool_registry
    return ExecutionEngine(**kwargs), checkpoint_mgr


def make_agent_jwt(tenant_id: str, user_id: str = "user-logic-01") -> str:
    settings = get_settings()
    now = int(time.time())
    payload = {
        "sub": user_id,
        "tenant_id": tenant_id,
        "iat": now,
        "exp": now + 3600,
        "roles": ["admin", "operator"],
        "permissions": ["agent:read", "agent:write", "tools:execute"],
    }
    return pyjwt.encode(payload, settings.JWT_SECRET_KEY, algorithm="HS256")


def tool_call_payload(tool_name: str, arguments: dict[str, Any]) -> dict[str, Any]:
    return {
        "content": f"```json\n{json.dumps({'action': 'tool_call', 'tool_name': tool_name, 'arguments': arguments, 'thought': 'need tool'})}\n```",
        "prompt_tokens": 40,
        "completion_tokens": 25,
        "total_tokens": 65,
        "model": "gpt-4o",
        "cost_usd": 0.0002,
    }


def finish_payload(output: str) -> dict[str, Any]:
    return {
        "content": f'{{"action": "finish", "output": "{output}", "thought": "done"}}',
        "prompt_tokens": 15,
        "completion_tokens": 10,
        "total_tokens": 25,
        "model": "gpt-4o",
        "cost_usd": 0.00003,
    }


# ===========================================================================
# ST-A — Transition-matrix completeness and enforcement
# ===========================================================================


def test_run_matrix_is_complete_and_closed() -> None:
    """Every non-terminal run state defines its successors; terminals define none."""
    for status in RunStatus:
        if status in TERMINAL_RUN_STATES:
            continue
        assert status in EXPECTED_RUN_MATRIX, f"missing matrix entry for {status}"
        targets = EXPECTED_RUN_MATRIX[status]
        assert targets, f"non-terminal state {status} must allow progress"
        for target in targets:
            assert target in set(RunStatus), f"unknown target {target}"
    for terminal in TERMINAL_RUN_STATES:
        assert terminal not in EXPECTED_RUN_MATRIX


def test_every_allowed_run_transition_is_accepted_via_transition_to() -> None:
    for src, targets in EXPECTED_RUN_MATRIX.items():
        for dst in targets:
            run = RunState(
                run_id=f"run_{src.value}_{dst.value}",
                task_id="task_matrix",
                tenant_id="tenant-logic-01",
                user_id="user-logic-01",
                status=src,
            )
            run.transition_to(dst)
            assert run.status == dst
            if dst in TERMINAL_RUN_STATES:
                assert run.completed_at is not None


def test_every_forbidden_run_transition_is_rejected_via_assignment() -> None:
    """Raw status writes may not bypass the machine (RL01-F-01).

    EXPECTED: assigning an illegal successor raises and leaves state intact.
    ACTUAL (pre-fix): transition_to exists but every production writer assigns
    .status directly; assignment performed no validation, so any invalid
    transition could be persisted silently.
    """
    for src in RunStatus:
        for dst in RunStatus:
            # Identical re-assignment is an idempotent no-op for every state.
            forbidden = dst not in EXPECTED_RUN_MATRIX.get(src, set()) and dst != src
            if not forbidden:
                continue
            run = RunState(
                run_id="run_forbidden",
                task_id="task_matrix",
                tenant_id="tenant-logic-01",
                user_id="user-logic-01",
                status=src,
            )
            with pytest.raises(ValueError):
                run.status = dst
            assert run.status == src, f"{src} mutated to {dst} illegally"


def test_every_forbidden_run_transition_is_rejected_via_transition_to() -> None:
    for src in RunStatus:
        for dst in RunStatus:
            if dst in EXPECTED_RUN_MATRIX.get(src, set()) or dst == src:
                continue
            run = RunState(
                run_id="run_forbidden",
                task_id="task_matrix",
                tenant_id="tenant-logic-01",
                user_id="user-logic-01",
                status=src,
            )
            with pytest.raises(ValueError):
                run.transition_to(dst)
            assert run.status == src


def test_named_forbidden_transitions_cannot_silently_succeed() -> None:
    """The task specification's explicit forbidden pairs, on both write paths."""
    named = [
        (RunStatus.FAILED, RunStatus.COMPLETED),
        (RunStatus.REJECTED, RunStatus.EXECUTING),
        (RunStatus.CANCELLED, RunStatus.EXECUTING),
        (RunStatus.TIMEOUT, RunStatus.COMPLETED),
        # Approval bypass: a run gated on human approval cannot complete.
        (RunStatus.WAITING_APPROVAL, RunStatus.COMPLETED),
        (RunStatus.PAUSED_APPROVAL, RunStatus.COMPLETED),
    ]
    for src, dst in named:
        run = RunState(
            run_id="run_named",
            task_id="task_named",
            tenant_id="tenant-logic-01",
            user_id="user-logic-01",
            status=src,
        )
        with pytest.raises(ValueError):
            run.transition_to(dst)
        assert run.status == src
        with pytest.raises(ValueError):
            run.status = dst
        assert run.status == src


def test_self_assignment_is_idempotent_noop() -> None:
    for status in RunStatus:
        run = RunState(
            run_id="run_self",
            task_id="task_self",
            tenant_id="tenant-logic-01",
            user_id="user-logic-01",
            status=status,
        )
        run.status = status  # identical re-assignment changes nothing
        assert run.status == status


@pytest.mark.asyncio
async def test_transition_matrix_survives_checkpoint_roundtrip() -> None:
    checkpoint_mgr = CheckpointManager()
    run = RunState(
        run_id="run_cp_terminal",
        task_id="task_cp",
        tenant_id="tenant-logic-01",
        user_id="user-logic-01",
        status=RunStatus.EXECUTING,
    )
    run.transition_to(RunStatus.FAILED, reason="step failed")

    await checkpoint_mgr.save_checkpoint(run)
    restored = await checkpoint_mgr.resume_run_from_checkpoint(
        run_id="run_cp_terminal", tenant_id="tenant-logic-01"
    )
    assert restored.status == RunStatus.FAILED
    with pytest.raises(ValueError):
        restored.status = RunStatus.EXECUTING
    assert restored.status == RunStatus.FAILED


# ===========================================================================
# ST-A/ST-G — Task status machine
# ===========================================================================


def test_task_matrix_is_enforced_on_assignment() -> None:
    """TaskStatus writes are matrix-validated (RL01-F-07).

    EXPECTED: illegal task transitions raise; terminal tasks re-open only via
    the explicit new-attempt start (terminal→RUNNING).
    ACTUAL (pre-fix): TaskState.status was a free enum field with no machine.
    """
    for src in TaskStatus:
        for dst in TaskStatus:
            allowed = dst in EXPECTED_TASK_MATRIX.get(src, set()) or (
                src in TERMINAL_TASK_STATES and dst == TaskStatus.RUNNING
            )
            if allowed or dst == src:
                continue
            task = TaskState(
                task_id="task_forbidden",
                tenant_id="tenant-logic-01",
                user_id="user-logic-01",
                goal="goal",
                status=src,
            )
            with pytest.raises(ValueError):
                task.status = dst
            assert task.status == src

    # Terminal task re-opens explicitly for a bounded new attempt only.
    completed = TaskState(
        task_id="task_reopen",
        tenant_id="tenant-logic-01",
        user_id="user-logic-01",
        goal="goal",
        status=TaskStatus.COMPLETED,
    )
    completed.status = TaskStatus.RUNNING
    assert completed.status == TaskStatus.RUNNING


def test_task_happy_path_sequence_is_accepted() -> None:
    task = TaskState(
        task_id="task_happy",
        tenant_id="tenant-logic-01",
        user_id="user-logic-01",
        goal="goal",
    )
    assert task.status == TaskStatus.PENDING
    task.status = TaskStatus.RUNNING
    task.status = TaskStatus.PAUSED_APPROVAL
    task.status = TaskStatus.RUNNING
    task.status = TaskStatus.COMPLETED
    assert task.status == TaskStatus.COMPLETED


# ===========================================================================
# ST-C — Late cancellation must not corrupt terminal state (RL01-F-02)
# ===========================================================================


@pytest.mark.asyncio
async def test_late_cancellation_after_completion_preserves_terminal_state() -> None:
    """A cancel delivered after the run reached COMPLETED must not flip it.

    EXPECTED: run stays COMPLETED; the CancelledError is propagated but the
    terminal record is immutable.
    ACTUAL (pre-fix): runner.start_run's asyncio.CancelledError handler
    unconditionally overwrote status with CANCELLED.
    """
    planner = ScriptedActionPlanner(
        MockControllableBackend(),
        [NextAction(action_type=NextActionType.FINISH, final_output="done")],
    )
    ckpt_mgr = CheckpointManager()
    runner = AgentRunner(
        planner=planner,
        tool_registry=ToolRegistry(),
        memory_manager=AgentMemoryManager(),
        checkpoint_manager=ckpt_mgr,
        approval_manager=ApprovalManager(),
        config=AgentConfig(max_iterations=3),
    )

    task = TaskState(
        task_id="task_race",
        tenant_id="tenant-logic-01",
        user_id="user-logic-01",
        goal="finish immediately",
    )
    run = RunState(
        run_id="run_race",
        task_id="task_race",
        tenant_id="tenant-logic-01",
        user_id="user-logic-01",
    )

    original_save = ckpt_mgr.save_checkpoint

    async def racing_save(run_state: RunState, *args: Any, **kwargs: Any) -> str:
        # Cancellation lands after the loop assigned COMPLETED but before the
        # run finishes returning — the exact corruption window.
        runner.request_cancellation(run.run_id)
        await asyncio.sleep(0)
        return await original_save(run_state, *args, **kwargs)

    ckpt_mgr.save_checkpoint = racing_save  # type: ignore[method-assign]

    bg = asyncio.create_task(runner.start_run(task, run))
    with pytest.raises(asyncio.CancelledError):
        await bg
    await asyncio.sleep(0)

    assert run.status == RunStatus.COMPLETED, (
        f"terminal state corrupted to {run.status} by late cancellation"
    )
    assert task.status == TaskStatus.COMPLETED
    assert run.completed_at is not None


# ===========================================================================
# ST-D — VERIFYING / REPLANNING lifecycle observability (RL01-F-03)
# ===========================================================================


@pytest.mark.asyncio
async def test_engine_traverses_verifying_and_replanning_states() -> None:
    """The documented VERIFYING/REPLANNING states are actually entered.

    EXPECTED: status is VERIFYING when verification starts, REPLANNING when a
    replan starts, back to EXECUTING when revised execution resumes, and
    COMPLETED after a PASSED verification of a complete plan.
    ACTUAL (pre-fix): the engine never left EXECUTING; the machine's
    VERIFYING/REPLANNING states were unreachable dead states.
    """
    plan = Plan(
        task_id="task_verify",
        goal="Verify orchestration state machine",
        steps=[
            make_engine_step("s1"),
            make_engine_step("s2", dependencies=["s1"]),
        ],
    )
    verifier = ScriptedVerifier(
        [VerificationVerdict.NEEDS_REVISION, VerificationVerdict.PASS]
    )
    engine, _ckpt = fresh_engine(plan=plan, verifier=verifier)
    spec = make_task_spec()
    run_id = "run_verifying"

    snapshots: list[tuple[str, RunStatus]] = []
    final_status: RunStatus | None = None
    async for event in engine.execute_task(spec, run_id=run_id):
        active = engine.get_active_run(run_id)
        if active is None:
            # Pre-registration events (task_created / planning_started) fire
            # before the RunState exists.
            continue
        snapshots.append((event.event_type, active.status))
    final_status = engine.get_active_run(run_id).status  # type: ignore[union-attr]

    by_event = dict(snapshots)
    assert by_event.get("verification_started") == RunStatus.VERIFYING, (
        f"verification_started observed at {by_event.get('verification_started')}"
    )
    assert by_event.get("replan_started") == RunStatus.REPLANNING, (
        f"replan_started observed at {by_event.get('replan_started')}"
    )
    # Every status observed after the replan must be a legal machine state;
    # with enforcement active, surviving the whole run proves each hop
    # (including REPLANNING→EXECUTING) was matrix-valid.
    legal_post_replan = set(RunStatus) - {
        RunStatus.CREATED,
        RunStatus.READY,
        RunStatus.PLANNING,
    }
    replan_idx = [evt for evt, _ in snapshots].index("replan_started")
    post_replan = snapshots[replan_idx + 1 :]
    assert post_replan, "no events observed after replanning"
    assert all(status in legal_post_replan for _, status in post_replan)
    assert final_status == RunStatus.COMPLETED
    assert verifier.calls == 2


@pytest.mark.asyncio
async def test_engine_rejected_verdict_terminates_from_verifying() -> None:
    """A REJECTED verification terminates REJECTED out of VERIFYING state."""
    plan = Plan(task_id="task_rej", goal="goal", steps=[make_engine_step("s1")])
    verifier = ScriptedVerifier([VerificationVerdict.REJECTED])
    engine, _ckpt = fresh_engine(plan=plan, verifier=verifier)
    spec = make_task_spec()
    run_id = "run_rejected"

    async for _ in engine.execute_task(spec, run_id=run_id):
        pass
    run = engine.get_active_run(run_id)
    assert run is not None and run.status == RunStatus.REJECTED
    assert run.completed_at is not None

    # Terminal integrity after rejection.
    with pytest.raises(ValueError):
        run.status = RunStatus.EXECUTING


@pytest.mark.asyncio
async def test_engine_revision_ceiling_terminates_failed() -> None:
    """Verification NEEDS_REVISION is bounded: run terminates FAILED."""
    plan = Plan(task_id="task_rev", goal="goal", steps=[make_engine_step("s1")])
    verifier = ScriptedVerifier([VerificationVerdict.NEEDS_REVISION])
    engine, _ckpt = fresh_engine(plan=plan, verifier=verifier)
    spec = make_task_spec()
    run_id = "run_revisions"

    events = [event async for event in engine.execute_task(spec, run_id=run_id)]
    replans = [e for e in events if e.event_type == "replan_started"]
    assert len(replans) <= 2, f"unbounded replanning: {len(replans)} cycles"
    run = engine.get_active_run(run_id)
    assert run is not None and run.status == RunStatus.FAILED


# ===========================================================================
# ST-E — Retry bounding
# ===========================================================================


@pytest.mark.asyncio
async def test_step_retry_is_bounded_and_terminates_failed() -> None:
    """A permanently failing step with no alternative agent terminates FAILED
    after a bounded number of retry attempts."""
    tracker: dict[str, int] = {"executions": 0}
    registry = ToolRegistry()
    registry.register(AlwaysFailingTool(tracker))

    plan = Plan(
        task_id="task_retry",
        goal="execute failing step",
        steps=[make_engine_step("s_fail", tool_name="always_fails")],
    )
    engine, _ckpt = fresh_engine(plan=plan, tool_registry=registry)
    spec = make_task_spec(timeout_seconds=5.0)
    run_id = "run_retry"

    events = [event async for event in engine.execute_task(spec, run_id=run_id)]
    retries = [e for e in events if e.event_type == "step_retrying"]
    max_retries = RecoveryLimits().MAX_STEP_RETRIES
    assert len(retries) <= max_retries, (
        f"unbounded step retries: {len(retries)} > {max_retries}"
    )
    run = engine.get_active_run(run_id)
    assert run is not None and run.status in (RunStatus.FAILED, RunStatus.TIMEOUT)
    assert run.status != RunStatus.COMPLETED


@pytest.mark.asyncio
async def test_agent_switch_recovery_is_bounded_in_attempt_count() -> None:
    """Agent-switching recovery is bounded: a permanently failing step with
    alternative agents terminates FAILED after a bounded number of switches
    instead of alternating agents until the run timeout (RL01-F-05).

    EXPECTED: bounded switch count, terminal FAILED, execution count bounded.
    ACTUAL (pre-fix): the exhaustion branch re-selected another agent on every
    failure — with 2+ eligible agents the step alternated A↔B indefinitely,
    bounded only by the run wall-clock timeout.
    """
    tracker: dict[str, int] = {"executions": 0}
    registry = ToolRegistry()
    registry.register(AlwaysFailingTool(tracker))

    plan = Plan(
        task_id="task_switch",
        goal="execute failing step",
        steps=[make_engine_step("s_switch", tool_name="always_fails")],
    )
    engine, _ckpt = fresh_engine(plan=plan, tool_registry=registry)
    spec = make_task_spec(timeout_seconds=2.0)
    run_id = "run_switch"

    events = [event async for event in engine.execute_task(spec, run_id=run_id)]
    switches = [e for e in events if e.event_type == "agent_switched"]
    max_switches = RecoveryLimits().MAX_AGENT_SWITCHES
    assert len(switches) <= max_switches, (
        f"unbounded agent switching: {len(switches)} switches > {max_switches}"
    )
    run = engine.get_active_run(run_id)
    assert run is not None and run.status in (RunStatus.FAILED, RunStatus.TIMEOUT)
    # Each attempt cycle costs at most (MAX_STEP_RETRIES + 1) executions.
    ceiling = (RecoveryLimits().MAX_STEP_RETRIES + 1) * (max_switches + 2)
    assert tracker["executions"] <= ceiling, (
        f"unbounded recovery executions: {tracker['executions']} > {ceiling}"
    )


# ===========================================================================
# ST-E/ST-G — Terminal failure can only be retried as a NEW run
# ===========================================================================


@pytest.mark.asyncio
async def test_terminal_failed_run_refuses_resume_and_new_run_is_fresh() -> None:
    plan = Plan(task_id="task_retry_new", goal="goal", steps=[make_engine_step("s1")])
    verifier = ScriptedVerifier([VerificationVerdict.FAILED])
    engine, _ckpt = fresh_engine(plan=plan, verifier=verifier)
    spec = make_task_spec()
    run_id = "run_failed_terminal"

    async for _ in engine.execute_task(spec, run_id=run_id):
        pass
    run = engine.get_active_run(run_id)
    assert run is not None and run.status == RunStatus.FAILED

    refused: list[str] = []
    async for event in engine.resume_run(run_id, spec.tenant_id, approved=True):
        refused.append(event.event_type)
    assert "resume_refused" in refused

    # Bounded new attempt: a brand-new run re-executes the goal cleanly.
    verifier2 = ScriptedVerifier([VerificationVerdict.PASS])
    engine2, _ = fresh_engine(plan=plan, verifier=verifier2)
    events = [
        event async for event in engine2.execute_task(spec, run_id="run_retry_fresh")
    ]
    assert any(e.event_type == "completed" for e in events)


# ===========================================================================
# ST-F — Approval & cancellation semantics at the HTTP boundary
# ===========================================================================


@pytest.mark.asyncio
async def test_http_approval_gate_rejection_marks_run_rejected() -> None:
    """Rejecting an approval via the decisions API terminates the run REJECTED.

    EXPECTED: WAITING/PAUSED→REJECTED (terminal), consistent with the canonical
    engine's rejection semantics.
    ACTUAL (pre-fix): the manager set the run back to RUNNING with nothing left
    executing — an immortal zombie state that could neither progress nor be
    reported terminal.
    """
    tenant = f"tenant-logic-01-{uuid.uuid4().hex[:8]}"
    headers = {"Authorization": f"Bearer {make_agent_jwt(tenant)}"}

    with patch(
        "app.agent.backends.jakeai.call_upstream_llm_detailed",
        new_callable=AsyncMock,
        side_effect=[
            tool_call_payload("terminal_exec", {"command": "rm -rf /tmp/cache"}),
            finish_payload("done after reject"),
        ],
    ):
        async with AsyncClient(
            transport=ASGITransport(app=app), base_url="http://testserver"
        ) as client:
            res = await client.post(
                "/api/v1/agent/tasks",
                headers=headers,
                json={"goal": "run dangerous command"},
            )
            assert res.status_code == 201, res.text
            task_id = res.json()["task_id"]

            res = await client.post(
                f"/api/v1/agent/tasks/{task_id}/runs",
                headers=headers,
                json={"async_execution": False},
            )
            assert res.status_code == 201, res.text
            run_id = res.json()["run_id"]
            assert res.json()["status"] == TaskStatus.PAUSED_APPROVAL.value

            res = await client.get("/api/v1/agent/approvals/pending", headers=headers)
            pending = res.json()
            assert len(pending) == 1
            approval_id = pending[0]["approval_id"]

            res = await client.post(
                f"/api/v1/agent/tasks/{task_id}/runs/{run_id}/approvals/{approval_id}",
                headers=headers,
                json={"approved": False, "reason": "not authorized"},
            )
            assert res.status_code == 200, res.text
            assert res.json()["status"] == ApprovalStatus.REJECTED.value

            res = await client.get(
                f"/api/v1/agent/tasks/{task_id}/runs/{run_id}", headers=headers
            )
            assert res.status_code == 200
            assert res.json()["status"] == RunStatus.REJECTED.value, (
                f"run ended in {res.json()['status']} after approval rejection"
            )

            # A second decision on the finalized approval is refused.
            res = await client.post(
                f"/api/v1/agent/tasks/{task_id}/runs/{run_id}/approvals/{approval_id}",
                headers=headers,
                json={"approved": True, "reason": "late approve"},
            )
            assert res.status_code == 409, res.text


@pytest.mark.asyncio
async def test_http_approval_approve_resumes_to_completed() -> None:
    """Approving the gate resumes execution; the run terminates COMPLETED and
    the approval is consumed (single-use)."""
    tenant = f"tenant-logic-01-{uuid.uuid4().hex[:8]}"
    headers = {"Authorization": f"Bearer {make_agent_jwt(tenant)}"}

    with patch(
        "app.agent.backends.jakeai.call_upstream_llm_detailed",
        new_callable=AsyncMock,
        side_effect=[
            tool_call_payload("terminal_exec", {"command": "rm -rf /tmp/cache"}),
            finish_payload("approved and completed"),
        ],
    ):
        async with AsyncClient(
            transport=ASGITransport(app=app), base_url="http://testserver"
        ) as client:
            res = await client.post(
                "/api/v1/agent/tasks",
                headers=headers,
                json={"goal": "run dangerous command"},
            )
            task_id = res.json()["task_id"]
            res = await client.post(
                f"/api/v1/agent/tasks/{task_id}/runs",
                headers=headers,
                json={"async_execution": False},
            )
            assert res.status_code == 201
            run_id = res.json()["run_id"]
            assert res.json()["status"] == TaskStatus.PAUSED_APPROVAL.value

            res = await client.get("/api/v1/agent/approvals/pending", headers=headers)
            approval_id = res.json()[0]["approval_id"]

            res = await client.post(
                f"/api/v1/agent/tasks/{task_id}/runs/{run_id}/approvals/{approval_id}",
                headers=headers,
                json={"approved": True, "reason": "authorized"},
            )
            assert res.status_code == 200, res.text
            assert res.json()["status"] == ApprovalStatus.APPROVED.value

            res = await client.get(
                f"/api/v1/agent/tasks/{task_id}/runs/{run_id}", headers=headers
            )
            assert res.json()["status"] == RunStatus.COMPLETED.value


@pytest.mark.asyncio
async def test_http_cancel_during_approval_wait_is_terminal_and_final() -> None:
    """Cancelling a paused run persists CANCELLED; a later approval decision
    cannot resurrect the cancelled run."""
    tenant = f"tenant-logic-01-{uuid.uuid4().hex[:8]}"
    headers = {"Authorization": f"Bearer {make_agent_jwt(tenant)}"}

    with patch(
        "app.agent.backends.jakeai.call_upstream_llm_detailed",
        new_callable=AsyncMock,
        side_effect=[
            tool_call_payload("terminal_exec", {"command": "rm -rf /tmp/cache"}),
            finish_payload("should never run"),
        ],
    ):
        async with AsyncClient(
            transport=ASGITransport(app=app), base_url="http://testserver"
        ) as client:
            res = await client.post(
                "/api/v1/agent/tasks",
                headers=headers,
                json={"goal": "run dangerous command"},
            )
            task_id = res.json()["task_id"]
            res = await client.post(
                f"/api/v1/agent/tasks/{task_id}/runs",
                headers=headers,
                json={"async_execution": False},
            )
            run_id = res.json()["run_id"]
            assert res.json()["status"] == TaskStatus.PAUSED_APPROVAL.value

            res = await client.post(
                f"/api/v1/agent/tasks/{task_id}/runs/{run_id}/cancel",
                headers=headers,
            )
            assert res.status_code == 200, res.text
            assert res.json()["status"] == RunStatus.CANCELLED.value

            res = await client.get(
                f"/api/v1/agent/tasks/{task_id}/runs/{run_id}", headers=headers
            )
            assert res.json()["status"] == RunStatus.CANCELLED.value

            # Late approval on the cancelled run must not resurrect it.
            res = await client.get("/api/v1/agent/approvals/pending", headers=headers)
            pending = [p for p in res.json() if p["run_id"] == run_id]
            assert pending, "approval gate lost after cancel"
            approval_id = pending[0]["approval_id"]
            res = await client.post(
                f"/api/v1/agent/tasks/{task_id}/runs/{run_id}/approvals/{approval_id}",
                headers=headers,
                json={"approved": True, "reason": "late"},
            )
            assert res.status_code == 200, res.text
            res = await client.get(
                f"/api/v1/agent/tasks/{task_id}/runs/{run_id}", headers=headers
            )
            assert res.json()["status"] == RunStatus.CANCELLED.value, (
                f"cancelled run resurrected to {res.json()['status']}"
            )


@pytest.mark.asyncio
async def test_http_cancel_of_completed_run_is_noop() -> None:
    """Cancel of an already-terminal run preserves its terminal status."""
    tenant = f"tenant-logic-01-{uuid.uuid4().hex[:8]}"
    headers = {"Authorization": f"Bearer {make_agent_jwt(tenant)}"}

    with patch(
        "app.agent.backends.jakeai.call_upstream_llm_detailed",
        new_callable=AsyncMock,
        side_effect=[finish_payload("fast finish")],
    ):
        async with AsyncClient(
            transport=ASGITransport(app=app), base_url="http://testserver"
        ) as client:
            res = await client.post(
                "/api/v1/agent/tasks",
                headers=headers,
                json={"goal": "finish fast"},
            )
            task_id = res.json()["task_id"]
            res = await client.post(
                f"/api/v1/agent/tasks/{task_id}/runs",
                headers=headers,
                json={"async_execution": False},
            )
            run_id = res.json()["run_id"]
            res = await client.get(
                f"/api/v1/agent/tasks/{task_id}/runs/{run_id}", headers=headers
            )
            assert res.json()["status"] == RunStatus.COMPLETED.value

            res = await client.post(
                f"/api/v1/agent/tasks/{task_id}/runs/{run_id}/cancel",
                headers=headers,
            )
            assert res.status_code == 200
            assert res.json()["status"] == RunStatus.COMPLETED.value


# ===========================================================================
# ST-G — Checkpoint / resume normalization (RL01-F-04)
# ===========================================================================


@pytest.mark.asyncio
async def test_resume_from_ready_checkpoint_completes_legally() -> None:
    """A run restored from a READY-state checkpoint (crash window between
    planning and dispatch) re-enters the machine legally and completes.

    EXPECTED: resume normalizes READY→EXECUTING before executing so every
    downstream terminal transition is matrix-valid.
    ACTUAL (pre-fix): the loop drove the restored run straight to terminal
    states via transitions absent from the matrix (READY→COMPLETED).
    """
    plan = Plan(task_id="task_ready_cp", goal="goal", steps=[make_engine_step("s1")])
    engine, ckpt = fresh_engine(plan=plan)

    spec = make_task_spec()
    restored = RunState(
        run_id="run_ready_cp",
        task_id=spec.task_id,
        tenant_id=spec.tenant_id,
        user_id=spec.user_id,
        status=RunStatus.READY,
        prompt=spec.goal,
        plan=plan.model_dump(),
        roles=spec.roles,
        permissions=spec.permissions,
    )
    await ckpt.save_checkpoint(restored)

    events = [
        event
        async for event in engine.resume_run(
            "run_ready_cp", spec.tenant_id, cancellation_token=None
        )
    ]
    run = engine.get_active_run("run_ready_cp")
    assert run is not None
    assert run.status == RunStatus.COMPLETED
    assert any(e.event_type == "completed" for e in events)


@pytest.mark.asyncio
async def test_resume_from_running_checkpoint_completes_legally() -> None:
    plan = Plan(task_id="task_run_cp", goal="goal", steps=[make_engine_step("s1")])
    engine, ckpt = fresh_engine(plan=plan)

    spec = make_task_spec()
    restored = RunState(
        run_id="run_running_cp",
        task_id=spec.task_id,
        tenant_id=spec.tenant_id,
        user_id=spec.user_id,
        status=RunStatus.RUNNING,
        prompt=spec.goal,
        plan=plan.model_dump(),
        roles=spec.roles,
        permissions=spec.permissions,
    )
    await ckpt.save_checkpoint(restored)

    async for _ in engine.resume_run("run_running_cp", spec.tenant_id):
        pass
    run = engine.get_active_run("run_running_cp")
    assert run is not None and run.status == RunStatus.COMPLETED


# ===========================================================================
# ST-F — Manager-level cancellation semantics
# ===========================================================================


@pytest.mark.asyncio
async def test_manager_cancel_of_created_run_is_legal_and_terminal() -> None:
    manager = AgentRuntimeManager(backend=MockControllableBackend(), engine=None)
    task = manager.create_task(
        goal="cancel me", tenant_id="tenant-logic-01", user_id="user-logic-01"
    )
    run = manager.create_run(task.task_id, "tenant-logic-01", "user-logic-01")
    assert run.status == RunStatus.CREATED

    cancelled = manager.cancel_run(task.task_id, run.run_id, "tenant-logic-01")
    assert cancelled.status == RunStatus.CANCELLED
    assert cancelled.completed_at is not None

    with pytest.raises(ValueError):
        await manager.execute_run(
            task_id=task.task_id, run_id=run.run_id, tenant_id="tenant-logic-01"
        )


@pytest.mark.asyncio
async def test_retry_as_new_run_does_not_corrupt_task_history() -> None:
    """A failed attempt is terminal; the retry is a NEW run that legally
    re-opens the task and completes it."""
    manager = AgentRuntimeManager(backend=MockControllableBackend(), engine=None)

    class FailingActionPlanner(ScriptedActionPlanner):
        pass

    # Attempt 1 fails; attempt 2 finishes.
    manager.runner.loop.planner = ScriptedActionPlanner(
        MockControllableBackend(),
        [NextAction(action_type=NextActionType.FAIL, error="boom")],
    )
    task = manager.create_task(
        goal="retry semantics", tenant_id="tenant-logic-01", user_id="user-logic-01"
    )
    run1 = manager.create_run(task.task_id, "tenant-logic-01", "user-logic-01")
    await manager.execute_run(
        task_id=task.task_id, run_id=run1.run_id, tenant_id="tenant-logic-01"
    )
    assert run1.status == RunStatus.FAILED
    assert task.status == TaskStatus.FAILED

    manager.runner.loop.planner = ScriptedActionPlanner(
        MockControllableBackend(),
        [NextAction(action_type=NextActionType.FINISH, final_output="second try")],
    )
    run2 = manager.create_run(task.task_id, "tenant-logic-01", "user-logic-01")
    await manager.execute_run(
        task_id=task.task_id, run_id=run2.run_id, tenant_id="tenant-logic-01"
    )
    assert run2.status == RunStatus.COMPLETED
    assert task.status == TaskStatus.COMPLETED
    # Attempt 1 history remains terminal-failed.
    assert run1.status == RunStatus.FAILED
