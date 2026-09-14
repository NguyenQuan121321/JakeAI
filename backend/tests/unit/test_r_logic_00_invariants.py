"""R-LOGIC-00 — Invariants Verification Test Suite.

Proves the critical system invariants at the highest realistic boundary:

INV-A  Terminal-state integrity: a run in a terminal state (COMPLETED, FAILED,
       CANCELLED, REJECTED, TIMEOUT) can never transition to a different state;
       an incomplete plan can never be reported as COMPLETED without
       verification.
INV-B  Approval requirements: every dangerous tool execution is bound to its
       own approved approval record; approvals are single-use per step,
       run-bound, and cannot be reused across runs or tools.
INV-C  Token conservation & quota limits: one gateway request settles quota
       exactly once (tokens and dollars); quota counters never lose updates and
       never go negative; the cache-hit path settles zero.
INV-D  Cache identity: a cached response may only be served when tenant, model,
       provider, system instructions, tools, response format, generation
       parameters AND the full conversation history all match.
INV-E  Tenant isolation at the HTTP boundary (agent runs, RAG, BYOK).
INV-F  RAG evidence integrity: only evidence-backed claims survive grounding;
       uncertain claims are explicitly caveated.
INV-G  Tool authorization: permission-gated and dangerous tools fail closed.
INV-H  Selected model actually used: FinOps ledger records the model that
       actually served the request, not just the requested one.

Classification notes: provider/upstream calls are controlled test doubles at
the module boundary; persistence (checkpoints, caches, quota counters) runs on
the real in-process managers (Redis/Qdrant paths activate in CI).
"""

from __future__ import annotations

import asyncio
import time
import uuid
from typing import TYPE_CHECKING, Any

import jwt as pyjwt
import pytest
from httpx import ASGITransport, AsyncClient

if TYPE_CHECKING:
    from collections.abc import AsyncGenerator

    from app.agent.runtime.models import AgentRunEvent

from app.agent.approvals.manager import ApprovalManager
from app.agent.approvals.models import ApprovalDecision
from app.agent.backends.base import (
    AgentBackendInterface,
    BackendRequest,
    BackendResponse,
    BackendStreamChunk,
)
from app.agent.domain.contracts import TaskSpec
from app.agent.execution.engine import ExecutionEngine
from app.agent.planning.models import Plan, PlanStep, PlanStepStatus
from app.agent.planning.planner import BoundedPlanner
from app.agent.runtime.manager import AgentRuntimeManager
from app.agent.runtime.runner import AgentRunner
from app.agent.state.checkpoint import CheckpointManager
from app.agent.state.models import RunState, RunStatus
from app.agent.tools.base import Tool, ToolMetadata, ToolResult, ToolRiskLevel
from app.agent.tools.registry import ToolRegistry
from app.core.byok import get_byok_manager
from app.core.config import get_settings
from app.finops.budget import FinOpsBudgetManager
from app.main import app
from app.optimizer.semantic_cache import SemanticCacheManager
from app.providers.base import ProviderCacheTelemetry, UpstreamLLMResponse
from app.rag.grounding import GroundingVerifier
from app.rag.models import DocumentChunk

# ===========================================================================
# Shared test doubles
# ===========================================================================


class MockControllableBackend(AgentBackendInterface):
    """Deterministic backend that never touches the network."""

    def __init__(
        self,
        content: str = "Analysis verified and mathematically sound.",
        model_name: str = "gemini-1.5-flash",
        provider_name: str = "google",
    ) -> None:
        super().__init__()
        self.content = content
        self.model_name = model_name
        self.provider_name = provider_name
        self.calls: list[BackendRequest] = []

    async def generate(self, request: BackendRequest) -> BackendResponse:
        self.calls.append(request)
        return BackendResponse(
            content=self.content,
            model=self.model_name,
            provider=self.provider_name,
            input_tokens=42,
            output_tokens=18,
            cost_usd=0.00012,
        )

    async def generate_stream(
        self, request: BackendRequest
    ) -> AsyncGenerator[BackendStreamChunk, None]:
        resp = await self.generate(request)
        yield BackendStreamChunk(delta_content=resp.content or "", is_complete=True)


class CountingDangerousTool(Tool):
    """Dangerous tool recording every execution for approval-boundary proofs."""

    def __init__(self, name: str, tracker: dict[str, int]) -> None:
        self._name = name
        self._tracker = tracker

    @property
    def metadata(self) -> ToolMetadata:
        return ToolMetadata(
            name=self._name,
            description="Privileged operation requiring approval",
            input_schema={
                "type": "object",
                "properties": {"command": {"type": "string"}},
                "required": ["command"],
            },
            risk_level=ToolRiskLevel.DANGEROUS,
            requires_approval=True,
        )

    async def execute(self, arguments: dict, context=None) -> ToolResult:
        self._tracker[self._name] = self._tracker.get(self._name, 0) + 1
        return ToolResult(
            success=True,
            output=f"Executed {self._name} with {arguments}",
        )


class SimpleStepPlanner(BoundedPlanner):
    """Planner yielding a caller-supplied deterministic plan."""

    def __init__(self, backend: AgentBackendInterface, plan: Plan) -> None:
        super().__init__(backend=backend)
        self._plan = plan

    async def plan_task(self, task_spec: TaskSpec, available_tools=None) -> Plan:
        self._plan.task_id = task_spec.task_id
        return self._plan.model_copy(deep=True)


def make_step(
    step_id: str,
    *,
    tool_name: str | None = None,
    tool_args: dict[str, Any] | None = None,
    dependencies: list[str] | None = None,
    status: PlanStepStatus = PlanStepStatus.PENDING,
) -> PlanStep:
    return PlanStep(
        step_id=step_id,
        description=f"Step {step_id}",
        candidate_agents=["general_agent"],
        required_tools=[tool_name] if tool_name else [],
        tool_name=tool_name,
        tool_args=tool_args or {},
        dependencies=dependencies or [],
        status=status,
    )


def make_task_spec(tenant: str = "tenant-logic-00") -> TaskSpec:
    return TaskSpec(
        task_id=f"task_{uuid.uuid4().hex[:10]}",
        tenant_id=tenant,
        user_id="user-logic-00",
        goal="Run invariant verification scenario",
        roles=["operator"],
        permissions=["agent:execute", "tools:execute"],
    )


def make_agent_jwt(tenant_id: str, user_id: str = "user-logic-00") -> str:
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


async def collect(engine_events: AsyncGenerator[AgentRunEvent, None]) -> list:
    return [event async for event in engine_events]


def fresh_engine(
    backend: AgentBackendInterface | None = None,
    plan: Plan | None = None,
    approval_manager: ApprovalManager | None = None,
    tool_registry: ToolRegistry | None = None,
) -> tuple[ExecutionEngine, CheckpointManager]:
    """Build an ExecutionEngine with isolated checkpoint/approval state."""
    checkpoint_mgr = CheckpointManager()
    backend = backend or MockControllableBackend()
    kwargs: dict[str, Any] = {
        "backend": backend,
        "checkpoint_manager": checkpoint_mgr,
    }
    if plan is not None:
        kwargs["planner"] = SimpleStepPlanner(backend, plan)
    if approval_manager is not None:
        kwargs["approval_manager"] = approval_manager
    if tool_registry is not None:
        kwargs["tool_registry"] = tool_registry
    return ExecutionEngine(**kwargs), checkpoint_mgr


# ===========================================================================
# INV-A — Terminal-state integrity
# ===========================================================================


@pytest.mark.asyncio
async def test_inv_a1_cancel_of_terminal_run_preserves_terminal_state() -> None:
    """Cancelling a run that already reached a terminal state must be a no-op.

    EXPECTED: COMPLETED run stays COMPLETED after cancel.
    ACTUAL (pre-fix): manager.cancel_run unconditionally overwrites the status,
    flipping a COMPLETED run to CANCELLED (terminal-state violation reachable
    via POST /api/v1/agent/tasks/{id}/runs/{id}/cancel).
    """
    backend = MockControllableBackend()
    manager = AgentRuntimeManager(backend=backend, engine=None)

    class _NoopEngine:
        _runs: dict[str, RunState] = {}

    manager.engine = _NoopEngine()  # type: ignore[assignment]

    task = manager.create_task(goal="done already", tenant_id="tenant-a", user_id="u")
    run = manager.create_run(task_id=task.task_id, tenant_id="tenant-a", user_id="u")
    # Arrange a terminal run through legal machine transitions (RL01-F-01
    # enforcement rejects the old CREATED→COMPLETED fixture shortcut).
    run.status = RunStatus.RUNNING
    run.status = RunStatus.COMPLETED
    run.completed_at = time.time()

    cancelled = manager.cancel_run(task.task_id, run.run_id, "tenant-a")
    assert cancelled.status == RunStatus.COMPLETED, (
        f"Terminal COMPLETED run was mutated by cancel to {cancelled.status}"
    )
    assert task.status.value != "cancelled"


@pytest.mark.asyncio
async def test_inv_a2_resume_of_completed_run_must_not_reexecute() -> None:
    """Resuming a COMPLETED run must not re-execute steps or re-complete it.

    EXPECTED: resume is refused (no new step execution, no second completion).
    ACTUAL (pre-fix): resume_run re-enters the execution loop, re-verifies and
    emits a second 'completed' event for an already-terminal run.
    """
    plan = Plan(
        goal="Deliver a simple answer",
        steps=[make_step("step_ok")],
    )
    backend = MockControllableBackend(content="Simple verified answer.")
    engine, _cp = fresh_engine(backend=backend, plan=plan)
    spec = make_task_spec()

    first_events = await collect(engine.execute_task(spec))
    completed = [e for e in first_events if e.event_type == "completed"]
    assert len(completed) == 1
    run_id = completed[0].run_id

    resume_events = await collect(
        engine.resume_run(run_id=run_id, tenant_id=spec.tenant_id)
    )

    step_starts = [e for e in resume_events if e.event_type == "step_started"]
    second_completions = [e for e in resume_events if e.event_type == "completed"]
    assert not step_starts, (
        f"Terminal COMPLETED run re-executed {len(step_starts)} steps on resume"
    )
    assert not second_completions, (
        "Terminal COMPLETED run was completed a second time on resume"
    )


@pytest.mark.asyncio
async def test_inv_a3_resume_of_cancelled_run_must_not_complete() -> None:
    """A CANCELLED run with an unfinished plan must never resume into COMPLETED.

    EXPECTED: resume of a cancelled (terminal) run is refused.
    ACTUAL (pre-fix): resume_run accepts any state, re-executes remaining
    steps and marks the run COMPLETED (failure/cancel to success transition).
    """
    plan = Plan(
        goal="Two step cancelled task",
        steps=[make_step("s1"), make_step("s2", dependencies=["s1"])],
    )
    backend = MockControllableBackend()
    engine, cp = fresh_engine(backend=backend, plan=plan)
    spec = make_task_spec()

    run_id = f"run_{uuid.uuid4().hex[:10]}"
    run_state = RunState(
        run_id=run_id,
        task_id=spec.task_id,
        tenant_id=spec.tenant_id,
        user_id=spec.user_id,
        status=RunStatus.CANCELLED,
        prompt=spec.goal,
        plan=plan.model_dump(),
    )
    await cp.save_checkpoint(run_state)

    resume_events = await collect(
        engine.resume_run(run_id=run_id, tenant_id=spec.tenant_id)
    )
    completions = [e for e in resume_events if e.event_type == "completed"]
    step_starts = [e for e in resume_events if e.event_type == "step_started"]
    assert not completions, "Cancelled run was resumed into COMPLETED"
    assert not step_starts, "Cancelled run re-executed steps on resume"


@pytest.mark.asyncio
async def test_inv_a4_incomplete_plan_never_completes_without_verification() -> None:
    """A run whose plan did not finish (stuck step) must not be COMPLETED.

    EXPECTED: the run terminates FAILED (no verification of an incomplete
    plan, no silent success).
    ACTUAL (pre-fix): the execution loop's fall-through marks the run
    COMPLETED unconditionally, bypassing the verifier entirely.
    """
    plan = Plan(
        goal="Crashed mid-execution task",
        steps=[
            make_step("s1", status=PlanStepStatus.RUNNING),
            make_step("s2", dependencies=["s1"]),
        ],
    )
    backend = MockControllableBackend()
    engine, cp = fresh_engine(backend=backend, plan=plan)
    spec = make_task_spec()

    run_id = f"run_{uuid.uuid4().hex[:10]}"
    run_state = RunState(
        run_id=run_id,
        task_id=spec.task_id,
        tenant_id=spec.tenant_id,
        user_id=spec.user_id,
        status=RunStatus.EXECUTING,
        prompt=spec.goal,
        plan=plan.model_dump(),
    )
    await cp.save_checkpoint(run_state)

    resume_events = await collect(
        engine.resume_run(run_id=run_id, tenant_id=spec.tenant_id)
    )
    completions = [e for e in resume_events if e.event_type == "completed"]
    failures = [e for e in resume_events if e.event_type == "failed"]
    assert not completions, (
        "Run with an incomplete plan was reported COMPLETED without verification"
    )
    assert failures, "Run with an incomplete plan must terminate FAILED"


@pytest.mark.asyncio
async def test_inv_a5_execute_run_refuses_terminal_run() -> None:
    """manager.execute_run on a terminal run must not reset it to RUNNING.

    EXPECTED: explicit error; status stays COMPLETED.
    ACTUAL (pre-fix): AgentExecutionLoop.execute unconditionally sets
    status=RUNNING, resurrecting a terminal run.
    """
    backend = MockControllableBackend()
    manager = AgentRuntimeManager(backend=backend)
    task = manager.create_task(goal="terminal run", tenant_id="tenant-a", user_id="u")
    run = manager.create_run(task_id=task.task_id, tenant_id="tenant-a", user_id="u")
    run.status = RunStatus.FAILED
    run.error = "previous failure"

    with pytest.raises((ValueError, RuntimeError)):
        await manager.execute_run(
            task_id=task.task_id, run_id=run.run_id, tenant_id="tenant-a"
        )
    assert run.status == RunStatus.FAILED, (
        f"Terminal FAILED run was mutated to {run.status} by execute_run"
    )

    # Defense-in-depth: the loop itself must also refuse terminal runs when
    # invoked directly, bypassing the manager guard.
    with pytest.raises(ValueError):
        async for _ in manager.runner.loop.execute(task, run):
            pass
    assert run.status == RunStatus.FAILED


@pytest.mark.asyncio
async def test_inv_a6_cancel_of_active_run_still_cancels() -> None:
    """Pin accepted behavior: cancelling a genuinely active run works.

    The terminal-state guard must only neutralize cancels of runs that have
    already finished; in-flight runs are still cancellable.
    """
    backend = MockControllableBackend()
    manager = AgentRuntimeManager(backend=backend)

    class _NoopEngine:
        _runs: dict[str, RunState] = {}

    manager.engine = _NoopEngine()  # type: ignore[assignment]

    task = manager.create_task(goal="long running", tenant_id="tenant-a", user_id="u")
    run = manager.create_run(task_id=task.task_id, tenant_id="tenant-a", user_id="u")
    run.status = RunStatus.RUNNING

    cancelled = manager.cancel_run(task.task_id, run.run_id, "tenant-a")
    assert cancelled.status == RunStatus.CANCELLED
    assert task.status.value == "cancelled"


@pytest.mark.asyncio
async def test_inv_b10_rejection_on_paused_run_terminates_rejected() -> None:
    """Rejecting a gate on a genuinely paused run terminates it REJECTED.

    Updated by R-LOGIC-01 (RL01-F-06): the previous accepted behavior moved
    the paused run back to RUNNING, but nothing ever re-entered the loop — an
    immortal zombie state. Rejection now terminates the run REJECTED,
    consistent with the canonical engine's rejection semantics and the run
    state machine (WAITING/PAUSED→REJECTED).
    """
    backend = MockControllableBackend()
    manager = AgentRuntimeManager(backend=backend)

    class _NoopEngine:
        _runs: dict[str, RunState] = {}

    manager.engine = _NoopEngine()  # type: ignore[assignment]

    task = manager.create_task(goal="paused task", tenant_id="tenant-a", user_id="u")
    run = manager.create_run(task_id=task.task_id, tenant_id="tenant-a", user_id="u")
    # Arrange the approval pause through legal machine transitions.
    run.status = RunStatus.RUNNING
    run.status = RunStatus.PAUSED_APPROVAL
    run.pending_approval_id = "appr_x"
    appr = manager.approval_manager.create_request(
        task_id=task.task_id,
        run_id=run.run_id,
        tenant_id="tenant-a",
        tool_name="tool_x",
        tool_args={},
        reason="dangerous",
    )
    run.pending_approval_id = appr.approval_id

    await manager.decide_approval(
        task_id=task.task_id,
        run_id=run.run_id,
        approval_id=appr.approval_id,
        decision=ApprovalDecision(approved=False, reason="no"),
        tenant_id="tenant-a",
        user_id="op",
    )
    assert run.status == RunStatus.REJECTED, (
        f"Rejected run must terminate REJECTED, got {run.status}"
    )
    assert run.completed_at is not None
    assert run.pending_approval_id is None


# ===========================================================================
# INV-B — Approval requirements
# ===========================================================================


@pytest.mark.asyncio
async def test_inv_b1_approving_one_tool_does_not_unlock_sibling_tool() -> None:
    """Each dangerous tool call requires its own approved approval record.

    EXPECTED: with two paused dangerous steps, approving step A's approval and
    resuming executes only A; step B stays paused awaiting its own approval.
    ACTUAL (pre-fix): resume_run scans for ANY approved approval of the run and
    passes a blanket grant, executing both tools after a single approval.
    """
    tracker: dict[str, int] = {}
    registry = ToolRegistry()
    registry.register(CountingDangerousTool("privileged_tool_a", tracker))
    registry.register(CountingDangerousTool("privileged_tool_b", tracker))

    plan = Plan(
        goal="Two privileged operations",
        steps=[
            make_step(
                "s_a",
                tool_name="privileged_tool_a",
                tool_args={"command": "op_a"},
            ),
            make_step(
                "s_b",
                tool_name="privileged_tool_b",
                tool_args={"command": "op_b"},
            ),
        ],
    )
    approval_mgr = ApprovalManager()
    backend = MockControllableBackend()
    engine, _cp = fresh_engine(
        backend=backend,
        plan=plan,
        approval_manager=approval_mgr,
        tool_registry=registry,
    )
    spec = make_task_spec()

    first_events = await collect(engine.execute_task(spec))
    approvals = [e for e in first_events if e.event_type == "approval_required"]
    assert len(approvals) >= 1, "Dangerous steps must pause for approval"
    run_id = approvals[0].run_id

    # Both steps created their own approval gates; approve ONLY tool A's gate
    # (identified by its tool binding, not by event order).
    pending = approval_mgr.list_pending(spec.tenant_id, run_id=run_id)
    tools_pending = sorted(p.tool_name for p in pending)
    assert tools_pending == ["privileged_tool_a", "privileged_tool_b"], (
        f"Both dangerous tools must have their own pending gates: {tools_pending}"
    )
    appr_a = next(p for p in pending if p.tool_name == "privileged_tool_a")
    approval_mgr.decide(
        approval_id=appr_a.approval_id,
        decision=ApprovalDecision(approved=True, reason="Only tool A is approved"),
        tenant_id=spec.tenant_id,
        user_id="operator-1",
    )

    await collect(engine.resume_run(run_id=run_id, tenant_id=spec.tenant_id))
    assert tracker.get("privileged_tool_a") == 1, "Approved tool A must execute"
    assert tracker.get("privileged_tool_b") is None, (
        "Tool B executed without its own approval "
        f"(execution count: {tracker.get('privileged_tool_b')})"
    )
    final_state = await engine.checkpoint_manager.load_checkpoint(
        run_id, spec.tenant_id
    )
    assert final_state is not None, "Resumed run must persist state"
    assert final_state.status == RunStatus.WAITING_APPROVAL, (
        f"Run must remain paused awaiting tool B's own approval, got {final_state.status}"
    )


@pytest.mark.asyncio
async def test_inv_b2_resume_without_approval_stays_waiting() -> None:
    """Resuming a paused run with no approved approval must not execute tools."""
    tracker: dict[str, int] = {}
    registry = ToolRegistry()
    registry.register(CountingDangerousTool("solo_tool", tracker))

    plan = Plan(
        goal="Single privileged operation",
        steps=[make_step("s1", tool_name="solo_tool", tool_args={"command": "x"})],
    )
    approval_mgr = ApprovalManager()
    backend = MockControllableBackend()
    engine, _cp = fresh_engine(
        backend=backend,
        plan=plan,
        approval_manager=approval_mgr,
        tool_registry=registry,
    )
    spec = make_task_spec()

    first_events = await collect(engine.execute_task(spec))
    approvals = [e for e in first_events if e.event_type == "approval_required"]
    assert len(approvals) == 1

    resume_events = await collect(
        engine.resume_run(run_id=approvals[0].run_id, tenant_id=spec.tenant_id)
    )
    assert tracker.get("solo_tool") is None, "Tool executed without approval"
    waiting = [e for e in resume_events if e.event_type == "waiting_approval"]
    assert waiting, "Run must remain waiting for approval"


@pytest.mark.asyncio
async def test_inv_b3_rejection_via_resume_marks_rejected() -> None:
    """Explicit rejection through resume terminates the run as REJECTED."""
    tracker: dict[str, int] = {}
    registry = ToolRegistry()
    registry.register(CountingDangerousTool("reject_tool", tracker))

    plan = Plan(
        goal="Rejected privileged op",
        steps=[make_step("s1", tool_name="reject_tool", tool_args={"command": "x"})],
    )
    approval_mgr = ApprovalManager()
    backend = MockControllableBackend()
    engine, cp = fresh_engine(
        backend=backend,
        plan=plan,
        approval_manager=approval_mgr,
        tool_registry=registry,
    )
    spec = make_task_spec()

    first_events = await collect(engine.execute_task(spec))
    approvals = [e for e in first_events if e.event_type == "approval_required"]
    run_id = approvals[0].run_id

    resume_events = await collect(
        engine.resume_run(run_id=run_id, tenant_id=spec.tenant_id, approved=False)
    )
    assert tracker.get("reject_tool") is None
    failures = [e for e in resume_events if e.event_type == "failed"]
    assert failures, "Rejection must terminate the run"
    final = await cp.load_checkpoint(run_id, spec.tenant_id)
    assert final is not None and final.status == RunStatus.REJECTED


@pytest.mark.asyncio
async def test_inv_b4_cross_run_approval_rejected_in_resume() -> None:
    """An approval bound to run A must not authorize resuming run B.

    EXPECTED: resume_after_approval raises; run B never executes run A's tool.
    ACTUAL (pre-fix): AgentRunner.resume_after_approval only checks approval
    status, executing run A's approved tool in the context of run B.
    """
    tracker: dict[str, int] = {}
    registry = ToolRegistry()
    registry.register(CountingDangerousTool("cross_run_tool", tracker))

    approval_mgr = ApprovalManager()
    memory = None
    from app.agent.memory.manager import AgentMemoryManager

    memory = AgentMemoryManager()
    planner = BoundedPlanner(backend=MockControllableBackend())
    runner = AgentRunner(
        planner=planner,
        tool_registry=registry,
        memory_manager=memory,
        checkpoint_manager=CheckpointManager(),
        approval_manager=approval_mgr,
    )

    appr = approval_mgr.create_request(
        task_id="task_other",
        run_id="run_theirs",
        tenant_id="tenant-a",
        tool_name="cross_run_tool",
        tool_args={"command": "foreign"},
        reason="dangerous",
    )
    approval_mgr.decide(
        approval_id=appr.approval_id,
        decision=ApprovalDecision(approved=True),
        tenant_id="tenant-a",
        user_id="op",
    )

    task_b = None
    from app.agent.state.models import TaskState

    task_b = TaskState(
        task_id="task_mine",
        tenant_id="tenant-a",
        user_id="u",
        goal="my goal",
    )
    run_b = RunState(
        run_id="run_mine",
        task_id="task_mine",
        tenant_id="tenant-a",
        user_id="u",
        status=RunStatus.PAUSED_APPROVAL,
    )
    with pytest.raises(ValueError):
        await runner.resume_after_approval(task_b, run_b, appr.approval_id)
    assert tracker.get("cross_run_tool") is None, (
        "Cross-run approval executed a tool in the context of another run"
    )


@pytest.mark.asyncio
async def test_inv_b5_late_approval_decision_preserves_terminal_run() -> None:
    """A late rejection on an already-terminal run must not resurrect it.

    EXPECTED: run stays COMPLETED; only the approval record is finalized.
    ACTUAL (pre-fix): decide_approval's rejection branch unconditionally sets
    status=RUNNING, violating terminal-state integrity.
    """
    backend = MockControllableBackend()
    manager = AgentRuntimeManager(backend=backend)

    class _NoopEngine:
        _runs: dict[str, RunState] = {}

    manager.engine = _NoopEngine()  # type: ignore[assignment]

    task = manager.create_task(goal="late decision", tenant_id="tenant-a", user_id="u")
    run = manager.create_run(task_id=task.task_id, tenant_id="tenant-a", user_id="u")
    run.status = RunStatus.RUNNING
    run.status = RunStatus.COMPLETED
    appr = manager.approval_manager.create_request(
        task_id=task.task_id,
        run_id=run.run_id,
        tenant_id="tenant-a",
        tool_name="some_tool",
        tool_args={},
        reason="dangerous",
    )

    await manager.decide_approval(
        task_id=task.task_id,
        run_id=run.run_id,
        approval_id=appr.approval_id,
        decision=ApprovalDecision(approved=False, reason="too late"),
        tenant_id="tenant-a",
        user_id="op",
    )
    assert run.status == RunStatus.COMPLETED, (
        f"Terminal run resurrected to {run.status} by late rejection"
    )


@pytest.mark.asyncio
async def test_inv_b6_restart_resume_with_lost_approval_records_unlocks_explicitly() -> (
    None
):
    """Restart recovery: an isolated ApprovalManager (records lost) can still
    resume via explicit approved=True, executing the bound tool exactly once.

    Guards the record-missing unlock path: the step must be pre-approved
    WITHOUT recreating a duplicate approval gate.
    """
    tracker: dict[str, int] = {}
    registry = ToolRegistry()
    registry.register(CountingDangerousTool("restart_tool", tracker))

    plan = Plan(
        goal="Restart recovery privileged op",
        steps=[make_step("s1", tool_name="restart_tool", tool_args={"command": "x"})],
    )
    approval_mgr = ApprovalManager()
    backend = MockControllableBackend()
    engine, cp = fresh_engine(
        backend=backend,
        plan=plan,
        approval_manager=approval_mgr,
        tool_registry=registry,
    )
    spec = make_task_spec()

    first_events = await collect(engine.execute_task(spec))
    approvals = [e for e in first_events if e.event_type == "approval_required"]
    assert len(approvals) == 1
    run_id = approvals[0].run_id

    # Simulate process restart: fresh engine, fresh (empty) approval manager,
    # same checkpoint store.
    fresh_approvals = ApprovalManager()
    engine_2, _ = fresh_engine(
        backend=backend,
        plan=plan,
        approval_manager=fresh_approvals,
        tool_registry=registry,
    )
    engine_2.checkpoint_manager = cp

    resume_events = await collect(
        engine_2.resume_run(run_id=run_id, tenant_id=spec.tenant_id, approved=True)
    )
    resolved = [e for e in resume_events if e.event_type == "approval_resolved"]
    assert resolved, "Explicit approved=True must unlock the paused step"
    assert tracker.get("restart_tool") == 1, "Approved tool must execute once"
    # No duplicate gate must be created by the restart path.
    assert len(fresh_approvals.list_pending(spec.tenant_id)) == 0, (
        "Restart resume must not mint duplicate approval gates"
    )
    completions = [e for e in resume_events if e.event_type == "completed"]
    assert len(completions) == 1


@pytest.mark.asyncio
async def test_inv_b7_repausing_step_reuses_pending_gate_without_duplicates() -> None:
    """A step re-entering execution with an undecided bound gate must keep
    waiting on the SAME approval id (no duplicate gates minted)."""
    tracker: dict[str, int] = {}
    registry = ToolRegistry()
    registry.register(CountingDangerousTool("rewait_tool", tracker))

    approval_mgr = ApprovalManager()
    # Pre-create the gate the crashed run was paused on.
    gate = approval_mgr.create_request(
        task_id="task_crash",
        run_id="run_crash",
        tenant_id="tenant-crash",
        tool_name="rewait_tool",
        tool_args={"command": "x"},
        reason="dangerous",
    )
    plan = Plan(
        goal="Crashed before executing the privileged step",
        steps=[
            make_step(
                "s1",
                tool_name="rewait_tool",
                tool_args={"command": "x"},
            )
        ],
    )
    plan.steps[0].pending_approval_id = gate.approval_id
    backend = MockControllableBackend()
    engine, cp = fresh_engine(
        backend=backend,
        plan=plan,
        approval_manager=approval_mgr,
        tool_registry=registry,
    )

    run_id = "run_crash"
    run_state = RunState(
        run_id=run_id,
        task_id="task_crash",
        tenant_id="tenant-crash",
        user_id="u",
        status=RunStatus.EXECUTING,
        prompt="crash recovery",
        plan=plan.model_dump(),
    )
    await cp.save_checkpoint(run_state)

    events = await collect(engine.resume_run(run_id=run_id, tenant_id="tenant-crash"))
    rewait = [
        e
        for e in events
        if e.event_type == "approval_required"
        and e.data.get("approval_id") == gate.approval_id
    ]
    assert rewait, "Step must re-emit its existing bound gate"
    assert tracker.get("rewait_tool") is None, "Tool executed while gate undecided"
    gates = approval_mgr.list_pending("tenant-crash", run_id=run_id)
    assert [g.approval_id for g in gates] == [gate.approval_id], (
        "A duplicate approval gate was created for the same step"
    )


@pytest.mark.asyncio
async def test_inv_b8_rejected_gate_fails_step_closed() -> None:
    """A step whose bound approval was rejected must fail closed, never execute."""
    tracker: dict[str, int] = {}
    registry = ToolRegistry()
    registry.register(CountingDangerousTool("denied_tool", tracker))

    approval_mgr = ApprovalManager()
    gate = approval_mgr.create_request(
        task_id="task_denied",
        run_id="run_denied",
        tenant_id="tenant-denied",
        tool_name="denied_tool",
        tool_args={"command": "x"},
        reason="dangerous",
    )
    approval_mgr.decide(
        approval_id=gate.approval_id,
        decision=ApprovalDecision(approved=False, reason="denied by operator"),
        tenant_id="tenant-denied",
        user_id="op",
    )
    plan = Plan(
        goal="Denied privileged op",
        steps=[make_step("s1", tool_name="denied_tool", tool_args={"command": "x"})],
    )
    plan.steps[0].pending_approval_id = gate.approval_id
    backend = MockControllableBackend()
    engine, cp = fresh_engine(
        backend=backend,
        plan=plan,
        approval_manager=approval_mgr,
        tool_registry=registry,
    )
    run_id = "run_denied"
    run_state = RunState(
        run_id=run_id,
        task_id="task_denied",
        tenant_id="tenant-denied",
        user_id="u",
        status=RunStatus.EXECUTING,
        prompt="denied op",
        plan=plan.model_dump(),
    )
    await cp.save_checkpoint(run_state)

    events = await collect(engine.resume_run(run_id=run_id, tenant_id="tenant-denied"))
    assert tracker.get("denied_tool") is None, (
        "Tool executed despite a rejected approval record"
    )
    failures = [e for e in events if e.event_type == "failed"]
    assert failures, "Rejected gate must fail the run closed"


@pytest.mark.asyncio
async def test_inv_b9_legacy_checkpoint_unlocked_only_by_explicit_approval() -> None:
    """Legacy checkpoint (no step-gate binding) with an explicit approved=True
    resumes; without explicit approval it stays waiting and executes nothing."""
    tracker: dict[str, int] = {}
    registry = ToolRegistry()
    registry.register(CountingDangerousTool("legacy_tool", tracker))

    plan = Plan(
        goal="Legacy paused privileged op",
        steps=[make_step("s1", tool_name="legacy_tool", tool_args={"command": "x"})],
    )
    plan.steps[0].status = PlanStepStatus.WAITING_APPROVAL
    backend = MockControllableBackend()
    approval_mgr = ApprovalManager()
    engine, cp = fresh_engine(
        backend=backend,
        plan=plan,
        approval_manager=approval_mgr,
        tool_registry=registry,
    )
    run_id = f"run_{uuid.uuid4().hex[:10]}"
    run_state = RunState(
        run_id=run_id,
        task_id=make_task_spec().task_id,
        tenant_id="tenant-legacy",
        user_id="u",
        status=RunStatus.WAITING_APPROVAL,
        prompt="legacy pause",
        plan=plan.model_dump(),
    )
    await cp.save_checkpoint(run_state)

    quiet = await collect(engine.resume_run(run_id=run_id, tenant_id="tenant-legacy"))
    assert tracker.get("legacy_tool") is None, "Executed without any approval"
    assert [e for e in quiet if e.event_type == "waiting_approval"], (
        "Run must remain waiting without explicit approval"
    )

    engine_2, _ = fresh_engine(
        backend=backend,
        plan=plan,
        approval_manager=approval_mgr,
        tool_registry=registry,
    )
    engine_2.checkpoint_manager = cp
    approved_events = await collect(
        engine_2.resume_run(run_id=run_id, tenant_id="tenant-legacy", approved=True)
    )
    assert tracker.get("legacy_tool") == 1, (
        "Explicit approved=True must authorize the legacy paused step"
    )
    assert [e for e in approved_events if e.event_type == "completed"]


# ===========================================================================
# INV-C — Token conservation & quota limits
# ===========================================================================


@pytest.fixture
def fresh_finops_stack(monkeypatch):
    """Isolate budget manager, finops service and gateway singletons per test."""
    import app.finops.budget as budget_mod
    import app.finops.service as finops_service_mod
    import app.services.ai_gateway as gateway_mod

    budget = FinOpsBudgetManager()
    budget.redis_client = None
    budget._redis_available = False
    monkeypatch.setattr(budget_mod, "_budget_manager", budget)

    import app.finops.ledger as ledger_mod

    ledger_mod._finops_ledger = None
    monkeypatch.setattr(finops_service_mod, "_finops_service", None)
    monkeypatch.setattr(gateway_mod, "_quota_manager", None)
    monkeypatch.setattr(gateway_mod, "_gateway_proxy", None)
    return budget


def _stub_upstream(monkeypatch, served_model: str, uncached: int, output: int):
    """Replace the upstream LLM boundary with a controlled provider double."""
    import app.services.ai_gateway as gateway_mod

    async def fake_detailed(**kwargs):
        return UpstreamLLMResponse(
            text="Stubbed upstream answer for invariant verification.",
            model=served_model,
            provider="openai",
            telemetry=ProviderCacheTelemetry(
                uncached_input_tokens=uncached,
                cached_tokens=0,
                output_tokens=output,
                provider="openai",
                model=served_model,
                actual_cost_usd=0.0004,
            ),
        )

    async def fake_legacy(**kwargs):
        return None

    monkeypatch.setattr(gateway_mod, "call_upstream_llm_detailed", fake_detailed)
    monkeypatch.setattr(gateway_mod, "call_upstream_llm", fake_legacy)


def _gateway_request():
    from app.providers.base import ChatMessage
    from app.services.ai_gateway import GatewayChatRequest

    return GatewayChatRequest(
        model="gpt-4o",
        messages=[ChatMessage(role="user", content="Invariant probe question")],
        temperature=0.1,
        max_tokens=64,
    )


@pytest.mark.asyncio
async def test_inv_c1_gateway_miss_settles_quota_exactly_once(
    fresh_finops_stack, monkeypatch
) -> None:
    """One gateway inference must settle quota once, not twice.

    EXPECTED: tokens_used increases by the authoritative billed amount
    (provider-reported total) and dollars by the effective cost, exactly once.
    ACTUAL (pre-fix): the gateway settles via QuotaManager.record_usage AND
    FinOpsService.record_upstream_inference settles again — quota double-count.
    """
    from app.services.ai_gateway import GatewayInferenceProxy, QuotaManager

    _stub_upstream(
        monkeypatch, served_model="gpt-4o-2024-08-13", uncached=120, output=30
    )
    proxy = GatewayInferenceProxy(quota_manager=QuotaManager())
    tenant = f"tenant-quota-{uuid.uuid4().hex[:8]}"

    budget = fresh_finops_stack
    await budget.set_budget(tenant, token_quota=1_000_000)

    before_tokens = await budget.get_tokens_used(tenant)
    before_dollars = await budget.get_dollars_spent(tenant)

    response = await proxy.chat_completions(
        tenant_id=tenant, request=_gateway_request()
    )

    assert response.cached is False
    after_tokens = await budget.get_tokens_used(tenant)
    after_dollars = await budget.get_dollars_spent(tenant)

    settled_tokens = after_tokens - before_tokens
    settled_dollars = after_dollars - before_dollars

    # Provider reported 120 uncached input + 30 output = 150 total tokens.
    assert settled_tokens == 150, (
        f"Quota settled {settled_tokens} tokens for a 150-token request "
        "(expected exactly one settlement)"
    )
    assert settled_dollars > 0, "Dollar budget must be settled exactly once"
    assert settled_dollars < 0.01


@pytest.mark.asyncio
async def test_inv_c2_gateway_cache_hit_settles_zero_quota(
    fresh_finops_stack, monkeypatch
) -> None:
    """A Tier 1 exact cache hit must not consume quota."""
    from app.services.ai_gateway import GatewayInferenceProxy, QuotaManager

    tenant = f"tenant-quota-{uuid.uuid4().hex[:8]}"
    budget = fresh_finops_stack
    await budget.set_budget(tenant, token_quota=1_000_000)

    _stub_upstream(monkeypatch, served_model="gpt-4o", uncached=120, output=30)
    proxy = GatewayInferenceProxy(quota_manager=QuotaManager())

    first = await proxy.chat_completions(tenant_id=tenant, request=_gateway_request())
    assert first.cached is False
    used_after_miss = await budget.get_tokens_used(tenant)

    second = await proxy.chat_completions(tenant_id=tenant, request=_gateway_request())
    assert second.cached is True
    used_after_hit = await budget.get_tokens_used(tenant)

    assert used_after_hit == used_after_miss, "Cache hit must settle zero quota tokens"


@pytest.mark.asyncio
async def test_inv_c3_quota_never_negative_and_hard_stops_at_limit(
    fresh_finops_stack,
) -> None:
    """Boundary + concurrency: quota counters never lose updates, never go
    negative, and the hard cap blocks further spend."""
    budget = fresh_finops_stack
    tenant = f"tenant-quota-{uuid.uuid4().hex[:8]}"
    await budget.set_budget(tenant, token_quota=10_000)

    allowed, _msg = await budget.check_budget(tenant, estimated_tokens=10_000)
    assert allowed is True

    await budget.settle_request(tenant, billed_tokens=10_000, billed_cost_usd=0.5)
    status = await budget.get_budget_status(tenant)
    assert status.is_suspended is True
    assert status.tokens_remaining == 0

    allowed, _msg = await budget.check_budget(tenant, estimated_tokens=1)
    assert allowed is False, "Hard cap must block further inference"

    # Concurrent settlements must not lose updates (Redis INCRBY semantics).
    results = await asyncio.gather(
        *[
            budget.settle_request(tenant, billed_tokens=10, billed_cost_usd=0.001)
            for _ in range(25)
        ]
    )
    final_usage = await budget.get_tokens_used(tenant)
    assert final_usage == 10_000 + 250, (
        f"Concurrent settlement lost updates: {final_usage} != {10_250}"
    )
    assert results[-1][0] == final_usage
    remaining = await budget.get_budget_status(tenant)
    assert remaining.tokens_remaining == 0


# ===========================================================================
# INV-D — Cache identity
# ===========================================================================


def _cache_kwargs(**overrides: Any) -> dict[str, Any]:
    base: dict[str, Any] = {
        "model": "gpt-4o",
        "provider": "openai",
        "system_instructions": "You are a precise assistant.",
        "tools": [{"type": "function", "function": {"name": "calc"}}],
        "response_format": None,
        "generation_params": {"temperature": 0.2, "max_tokens": 128},
    }
    base.update(overrides)
    return base


@pytest.mark.asyncio
async def test_inv_d1_semantic_hit_requires_same_conversation_history() -> None:
    """Tier 2 must not serve an entry cached under a different history.

    EXPECTED: same final user prompt but a different earlier conversation is a
    MISS on the semantic tier (history is generation-relevant and part of the
    canonical cache identity used by the exact tier).
    ACTUAL (pre-fix): only the last prompt is embedded; compatibility check
    never compares history, so a different conversation can receive the cached
    answer.
    """
    cache = SemanticCacheManager(similarity_threshold=0.01)
    tenant = f"tenant-cache-{uuid.uuid4().hex[:8]}"
    await cache.invalidate(tenant)

    prompt = "What is our current ratio?"
    history_set = [
        {"role": "system", "content": "You are a precise assistant."},
        {"role": "user", "content": "My assets are 200 and liabilities 100."},
        {"role": "assistant", "content": "Noted, your balance sheet is stored."},
        {"role": "user", "content": prompt},
    ]
    history_other = [
        {"role": "system", "content": "You are a precise assistant."},
        {"role": "user", "content": "Completely unrelated prior conversation."},
        {"role": "assistant", "content": "Understood, unrelated context noted."},
        {"role": "user", "content": prompt},
    ]

    await cache.set(
        prompt=prompt,
        tenant_id=tenant,
        response="Cached answer for balance-sheet conversation",
        messages=history_set,
        **_cache_kwargs(),
    )

    same_history_hit = await cache.get(
        prompt,
        tenant_id=tenant,
        messages=history_set,
        **_cache_kwargs(),
    )
    assert same_history_hit is not None, (
        "Identical conversation must hit the semantic cache"
    )

    other_history_hit = await cache.get(
        prompt,
        tenant_id=tenant,
        messages=history_other,
        **_cache_kwargs(),
    )
    assert other_history_hit is None, (
        "Semantic cache served an entry cached under a DIFFERENT conversation "
        "history (cache identity violation)"
    )


@pytest.mark.asyncio
async def test_inv_d2_exact_cache_identity_boundaries() -> None:
    """Exact tier must isolate on tenant, model and message history."""
    cache = SemanticCacheManager(similarity_threshold=0.01)
    tenant_a = f"tenant-cache-{uuid.uuid4().hex[:8]}"
    tenant_b = f"tenant-cache-{uuid.uuid4().hex[:8]}"
    await cache.invalidate()

    messages = [{"role": "user", "content": "Exact identity probe"}]
    await cache.set(
        prompt="Exact identity probe",
        tenant_id=tenant_a,
        response="tenant-a exact answer",
        messages=messages,
        **_cache_kwargs(),
    )

    cross_tenant = await cache.get(
        "Exact identity probe",
        tenant_id=tenant_b,
        messages=messages,
        **_cache_kwargs(),
    )
    assert cross_tenant is None, "Exact cache served another tenant's entry"

    cross_model = await cache.get(
        "Exact identity probe",
        tenant_id=tenant_a,
        messages=messages,
        **_cache_kwargs(model="gpt-4o-mini"),
    )
    assert cross_model is None, "Exact cache served another model's entry"

    same = await cache.get(
        "Exact identity probe",
        tenant_id=tenant_a,
        messages=messages,
        **_cache_kwargs(),
    )
    assert same is not None and same.response == "tenant-a exact answer"


@pytest.mark.asyncio
async def test_inv_d3_concurrent_cache_writes_stay_tenant_isolated() -> None:
    """Concurrent set/get across tenants must never cross-contaminate."""
    cache = SemanticCacheManager(similarity_threshold=0.01)
    tenants = [f"tenant-conc-{i}-{uuid.uuid4().hex[:6]}" for i in range(12)]
    await cache.invalidate()

    async def setup(tenant: str) -> None:
        await cache.set(
            prompt="Concurrent probe",
            tenant_id=tenant,
            response=f"answer-for-{tenant}",
            messages=[{"role": "user", "content": "Concurrent probe"}],
            **_cache_kwargs(),
        )

    async def verify(tenant: str) -> None:
        entry = await cache.get(
            "Concurrent probe",
            tenant_id=tenant,
            messages=[{"role": "user", "content": "Concurrent probe"}],
            **_cache_kwargs(),
        )
        assert entry is not None, f"Tenant {tenant} lost its own entry"
        assert entry.response == f"answer-for-{tenant}", (
            f"Tenant {tenant} received foreign cached content: {entry.response}"
        )

    await asyncio.gather(*[setup(t) for t in tenants])
    await asyncio.gather(*[verify(t) for t in tenants])


# ===========================================================================
# INV-E — Tenant isolation (HTTP boundary)
# ===========================================================================


@pytest.mark.asyncio
async def test_inv_e1_cross_tenant_agent_run_access_forbidden(monkeypatch) -> None:
    """HTTP boundary: tenant B cannot read or cancel tenant A's runs."""
    import app.agent.runtime.manager as manager_mod

    manager = AgentRuntimeManager(backend=MockControllableBackend())

    class _NoopEngine:
        _runs: dict[str, RunState] = {}

    manager.engine = _NoopEngine()  # type: ignore[assignment]
    monkeypatch.setattr(manager_mod, "_agent_manager", manager)

    task = manager.create_task(goal="secret goal", tenant_id="tenant-a", user_id="u")
    run = manager.create_run(task_id=task.task_id, tenant_id="tenant-a", user_id="u")
    run.status = RunStatus.RUNNING
    run.status = RunStatus.COMPLETED

    jwt_a = make_agent_jwt("tenant-a")
    jwt_b = make_agent_jwt("tenant-b")
    async with AsyncClient(
        transport=ASGITransport(app=app), base_url="http://testserver"
    ) as client:
        ok = await client.get(
            f"/api/v1/agent/tasks/{task.task_id}",
            headers={"Authorization": f"Bearer {jwt_a}"},
        )
        assert ok.status_code == 200

        foreign_get = await client.get(
            f"/api/v1/agent/tasks/{task.task_id}/runs/{run.run_id}",
            headers={"Authorization": f"Bearer {jwt_b}"},
        )
        assert foreign_get.status_code in (403, 404), (
            f"Cross-tenant run read returned {foreign_get.status_code}"
        )

        foreign_cancel = await client.post(
            f"/api/v1/agent/tasks/{task.task_id}/runs/{run.run_id}/cancel",
            headers={"Authorization": f"Bearer {jwt_b}"},
        )
        assert foreign_cancel.status_code in (403, 404), (
            f"Cross-tenant cancel returned {foreign_cancel.status_code}"
        )
        assert run.status == RunStatus.COMPLETED


@pytest.mark.asyncio
async def test_inv_e2_byok_credentials_are_tenant_isolated() -> None:
    """Provider credential isolation: tenant B can never resolve tenant A's key."""
    import app.core.byok as byok_mod

    byok_mod._byok_manager = None
    vault = get_byok_manager()
    tenant_a = f"tenant-byok-{uuid.uuid4().hex[:8]}"
    tenant_b = f"tenant-byok-{uuid.uuid4().hex[:8]}"
    secret = f"sk-live-{uuid.uuid4().hex}"

    await vault.store_key(tenant_id=tenant_a, provider="openai", api_key=secret)
    resolved_a = await vault.get_decrypted_key(tenant_a, "openai")
    assert resolved_a == secret

    resolved_b = await vault.get_decrypted_key(tenant_b, "openai")
    assert resolved_b in (None, ""), "Tenant B resolved tenant A's provider credential!"


@pytest.mark.asyncio
async def test_inv_e3_rag_answers_never_leak_foreign_tenant_evidence() -> None:
    """RAG pipeline: tenant B's query must not receive tenant A's evidence."""
    from app.rag.ingestion import DocumentIngestRequest
    from app.rag.pipeline import RAGPipeline

    pipeline = RAGPipeline()
    tenant_a = f"tenant-rag-{uuid.uuid4().hex[:8]}"
    tenant_b = f"tenant-rag-{uuid.uuid4().hex[:8]}"
    marker = "Zephyrion-Quantum-Project"

    await pipeline.ingest_document(
        request=DocumentIngestRequest(
            source="Confidential A",
            content=f"The {marker} uses titanium alloy chambers rated at 4000 psi.",
        ),
        tenant_id=tenant_a,
    )

    foreign = await pipeline.generate_grounded_answer(
        query="What does the Zephyrion-Quantum-Project use?",
        tenant_id=tenant_b,
    )
    assert marker not in foreign.answer, "Foreign tenant evidence leaked into answer"
    assert all(c.tenant_id == tenant_b for c in foreign.citations)

    own = await pipeline.generate_grounded_answer(
        query="What does the Zephyrion-Quantum-Project use?",
        tenant_id=tenant_a,
    )
    assert own.status == "SUCCESS"
    assert marker in own.answer or own.citations, (
        "Owner tenant should retrieve its own evidence"
    )


# ===========================================================================
# INV-F — RAG evidence integrity
# ===========================================================================


def _passages() -> list[DocumentChunk]:
    return [
        DocumentChunk(
            chunk_id="p1",
            content="ACME Corp reported $150,000,000 in revenue for Q3 2026.",
            tenant_id="tenant-corp",
            source="Q3 Earnings",
        )
    ]


def test_inv_f1_uncertain_claims_are_explicitly_caveated() -> None:
    """Claims that could not be verified must be visibly marked in the answer.

    EXPECTED: an UNCERTAIN claim kept in the verified answer carries an
    explicit caveat (the grounding module's documented intent).
    ACTUAL (pre-fix): the code comments 'Include uncertain claims with caveat'
    but appends the claim verbatim with no caveat, presenting unverified
    content as verified.
    """
    verifier = GroundingVerifier()
    text = (
        "ACME Corp reported $150,000,000 in revenue for Q3 2026. "
        "ACME Corp is exploring strategic partnerships across Europe."
    )
    result = verifier.verify(text, _passages(), tenant_id="tenant-corp")

    assert result.verified_answer, "Supported claim must survive"
    assert len(result.uncertain_claims) == 1, (
        "The modest-overlap qualitative claim must classify as UNCERTAIN"
    )
    assert "exploring strategic partnerships" in result.verified_answer, (
        "Uncertain claim is included, so it must be caveated"
    )
    lower = result.verified_answer.lower()
    assert "unverified" in lower or "uncertain" in lower or "not verified" in lower, (
        f"Uncertain claim presented without any caveat: {result.verified_answer!r}"
    )


def test_inv_f2_unsupported_claims_never_survive_grounding() -> None:
    """Fabricated claims are dropped; an all-fabricated answer yields nothing."""
    verifier = GroundingVerifier()
    text = (
        "ACME Corp reported $150,000,000 in revenue for Q3 2026. "
        "ACME Corp reported $999,000,000 in profit."
    )
    result = verifier.verify(text, _passages(), tenant_id="tenant-corp")

    assert "999,000,000" not in result.verified_answer
    assert result.unsupported_claims, "Fabricated claim must be flagged"
    assert "$150,000,000" in result.verified_answer


# ===========================================================================
# INV-G — Tool authorization
# ===========================================================================


class GatedTool(Tool):
    """Tool restricted to a specific permission."""

    @property
    def metadata(self) -> ToolMetadata:
        return ToolMetadata(
            name="gated_admin_tool",
            description="Requires admin permission",
            input_schema={"type": "object", "properties": {}},
            risk_level=ToolRiskLevel.READ_ONLY,
            permissions=["platform:admin"],
        )

    async def execute(self, arguments: dict, context=None) -> ToolResult:
        return ToolResult(success=True, output="admin op ok")


@pytest.mark.asyncio
async def test_inv_g1_permission_gated_tools_fail_closed() -> None:
    """ToolRegistry denies tools whose permissions the context lacks."""
    registry = ToolRegistry()
    registry.register(GatedTool())

    denied = await registry.execute(
        tool_name="gated_admin_tool",
        arguments={},
        context={"tenant_id": "t1", "user_id": "u", "roles": [], "permissions": []},
    )
    assert denied.success is False, "Permission-gated tool must fail closed"
    assert "Forbidden" in (denied.error or "")

    allowed = await registry.execute(
        tool_name="gated_admin_tool",
        arguments={},
        context={
            "tenant_id": "t1",
            "user_id": "u",
            "roles": ["admin"],
            "permissions": ["platform:admin"],
        },
    )
    assert allowed.success is True

    unknown = await registry.execute(
        tool_name="nonexistent_tool",
        arguments={},
        context={"tenant_id": "t1", "user_id": "u", "roles": [], "permissions": []},
    )
    assert unknown.success is False


@pytest.mark.asyncio
async def test_inv_g2_path_traversal_arguments_denied() -> None:
    """Argument-level attack patterns are denied by the policy engine."""
    registry = ToolRegistry()
    registry.register(GatedTool())

    malicious = await registry.execute(
        tool_name="gated_admin_tool",
        arguments={"path": "../../../etc/shadow"},
        context={
            "tenant_id": "t1",
            "user_id": "u",
            "roles": ["admin"],
            "permissions": ["platform:admin"],
        },
    )
    assert malicious.success is False, "Path traversal argument must be denied"


# ===========================================================================
# INV-H — Selected model actually used
# ===========================================================================


@pytest.mark.asyncio
async def test_inv_h1_ledger_records_actually_served_model(
    fresh_finops_stack, monkeypatch
) -> None:
    """FinOps ledger must record the model that actually served the request.

    EXPECTED: FinOpsRecord.model == served model; requested_model preserved.
    ACTUAL (pre-fix): the gateway passes request.model into the ledger, so a
    response served by a failover/rerouted model is billed and attributed
    under the requested model (routing savings permanently zero).
    """
    from app.services.ai_gateway import GatewayInferenceProxy, QuotaManager

    served_model = "gpt-4o-mini-served-variant"
    _stub_upstream(monkeypatch, served_model=served_model, uncached=90, output=25)
    proxy = GatewayInferenceProxy(quota_manager=QuotaManager())
    tenant = f"tenant-model-{uuid.uuid4().hex[:8]}"

    await proxy.chat_completions(tenant_id=tenant, request=_gateway_request())

    from app.finops.service import get_finops_service

    records = get_finops_service().get_transactions(tenant_id=tenant, limit=10)
    inference_records = [r for r in records if not r.is_cache_hit]
    assert inference_records, "Upstream inference must produce a ledger record"
    record = inference_records[0]
    assert record.model == served_model, (
        f"Ledger recorded model={record.model!r} but the upstream served "
        f"{served_model!r}"
    )
    assert record.requested_model == "gpt-4o", (
        "Requested model must be preserved for routing attribution"
    )
