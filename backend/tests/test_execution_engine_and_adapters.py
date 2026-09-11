"""Integration tests for Canonical ExecutionEngine and LangGraphExecutionAdapter.

Tests the 5 canonical orchestration scenarios:
1. Simple question resolution
2. Tool banking analysis
3. Parallel execution over independent subproblems via asyncio.gather
4. Tool requiring operator approval boundary
5. Failure recovery and tenant boundary verification
Plus LangGraphExecutionAdapter parity.
"""

from collections.abc import AsyncGenerator
from typing import Any

import pytest

from app.agent.backends.base import (
    AgentBackendInterface,
    BackendRequest,
    BackendResponse,
    BackendStreamChunk,
)
from app.agent.domain.contracts import (
    ExecutionContext,
    RecoveryAction,
    TaskSpec,
    VerificationResult,
    VerificationVerdict,
)
from app.agent.execution.engine import ExecutionEngine
from app.agent.planning.models import Plan, PlanStep, PlanStepStatus
from app.agent.planning.planner import BoundedPlanner
from app.agent.state.checkpoint import CheckpointManager
from app.agent.state.models import RunStatus
from app.agent.tools.base import Tool, ToolMetadata, ToolResult, ToolRiskLevel
from app.agent.tools.registry import ToolRegistry
from app.agent.verification.verifier import CanonicalVerifier
from app.agents.graph import LangGraphExecutionAdapter


class MockStreamingBackend(AgentBackendInterface):
    """Deterministic mock backend for orchestration tests."""

    def __init__(self, default_model: str = "gemini-1.5-flash") -> None:
        super().__init__()
        self.default_model = default_model
        self.calls: list[BackendRequest] = []

    async def generate(self, request: BackendRequest) -> BackendResponse:
        self.calls.append(request)
        return BackendResponse(
            content="The analysis is verified and mathematically sound.",
            tool_calls=[],
        )

    async def generate_stream(
        self, request: BackendRequest
    ) -> AsyncGenerator[BackendStreamChunk, None]:
        resp = await self.generate(request)
        yield BackendStreamChunk(delta_content=resp.content or "", is_complete=True)


class MockFailingOnceBackend(AgentBackendInterface):
    """Backend that fails with rate limit 429 on first call, then succeeds."""

    def __init__(self) -> None:
        super().__init__()
        self.call_count = 0

    async def generate(self, request: BackendRequest) -> BackendResponse:
        self.call_count += 1
        if self.call_count == 1:
            raise RuntimeError("Rate limit 429: Provider overloaded")
        return BackendResponse(
            content="The analysis is verified and mathematically sound.",
            tool_calls=[],
        )

    async def generate_stream(
        self, request: BackendRequest
    ) -> AsyncGenerator[BackendStreamChunk, None]:
        resp = await self.generate(request)
        yield BackendStreamChunk(delta_content=resp.content or "", is_complete=True)


class MockBalanceTool(Tool):
    @property
    def metadata(self) -> ToolMetadata:
        return ToolMetadata(
            name="get_account_balance",
            description="Get banking balance",
            input_schema={},
            risk_level=ToolRiskLevel.READ_ONLY,
        )

    async def execute(self, arguments: dict, context=None) -> ToolResult:
        return ToolResult(
            success=True,
            output={"balance": 50000.0, "currency": "USD"},
        )


class MockPrivilegedTool(Tool):
    @property
    def metadata(self) -> ToolMetadata:
        return ToolMetadata(
            name="terminal_exec",
            description="Dangerous shell command",
            input_schema={"command": {"type": "string"}},
            risk_level=ToolRiskLevel.DANGEROUS,
            requires_approval=True,
        )

    async def execute(self, arguments: dict, context=None) -> ToolResult:
        return ToolResult(
            success=True,
            output="Executed privileged command safely.",
        )


class MockSearchTool(Tool):
    @property
    def metadata(self) -> ToolMetadata:
        return ToolMetadata(
            name="search_symbols",
            description="Search symbols or filings",
            input_schema={},
            risk_level=ToolRiskLevel.READ_ONLY,
        )

    async def execute(self, arguments: dict, context=None) -> ToolResult:
        return ToolResult(
            success=True,
            output=[{"symbol": "AAPL", "filing": "10-K", "revenue": 1500000.0}],
        )


class MockFailingOnceTool(Tool):
    """Tool that fails with timeout once, then succeeds on retry."""

    def __init__(self) -> None:
        super().__init__()
        self.call_count = 0

    @property
    def metadata(self) -> ToolMetadata:
        return ToolMetadata(
            name="flaky_banking_api",
            description="Flaky banking tool",
            input_schema={},
            risk_level=ToolRiskLevel.READ_ONLY,
        )

    async def execute(self, arguments: dict, context=None) -> ToolResult:
        self.call_count += 1
        if self.call_count == 1:
            return ToolResult(
                success=False,
                error="Connection timeout to banking gateway",
            )
        return ToolResult(
            success=True,
            output={"balance": 50000.0, "currency": "USD"},
        )


class MockGeneralPlanner(BoundedPlanner):
    async def plan_task(
        self,
        task_spec: TaskSpec,
        available_tools: list[ToolMetadata] | None = None,
    ) -> Plan:
        return Plan(
            task_id=task_spec.task_id,
            goal=task_spec.goal,
            analysis="General reasoning task",
            steps=[
                PlanStep(
                    step_id="step_gen_1",
                    description="General reasoning step",
                    candidate_agents=["general_agent"],
                    dependencies=[],
                    status=PlanStepStatus.PENDING,
                )
            ],
            planner_mode="structured",
        )


class MockToolPlanner(BoundedPlanner):
    async def plan_task(
        self,
        task_spec: TaskSpec,
        available_tools: list[ToolMetadata] | None = None,
    ) -> Plan:
        return Plan(
            task_id=task_spec.task_id,
            goal=task_spec.goal,
            analysis="Tool retry task",
            steps=[
                PlanStep(
                    step_id="step_tool_retry",
                    description="Fetch banking with flaky api",
                    required_tools=["flaky_banking_api"],
                    dependencies=[],
                    status=PlanStepStatus.PENDING,
                )
            ],
            planner_mode="structured",
        )


class RevisingVerifier(CanonicalVerifier):
    """Verifier that requests revision once for math variance, then passes."""

    def __init__(self) -> None:
        super().__init__(max_revisions=2)
        self.call_count = 0

    def verify_execution(self, *args: Any, **kwargs: Any) -> VerificationResult:
        self.call_count += 1
        if self.call_count == 1:
            return VerificationResult(
                verdict=VerificationVerdict.NEEDS_REVISION,
                reason="Self-RAG Critique: Operating income variance detected. Recompute accurately.",
                recoverability=True,
                recommended_recovery_action=RecoveryAction.REPLAN,
            )
        return super().verify_execution(*args, **kwargs)


@pytest.fixture
def execution_env():
    backend = MockStreamingBackend()
    tool_registry = ToolRegistry()
    tool_registry.register(MockBalanceTool())
    tool_registry.register(MockPrivilegedTool())
    tool_registry.register(MockSearchTool())

    planner = BoundedPlanner(backend=backend)
    engine = ExecutionEngine(
        planner=planner,
        tool_registry=tool_registry,
        backend=backend,
    )
    return engine, backend, tool_registry


@pytest.mark.asyncio
async def test_scenario_1_simple_question(execution_env) -> None:
    """Scenario 1: Simple direct question complete lifecycle."""
    engine, _, _ = execution_env

    task_spec = TaskSpec(
        task_id="task_simple_1",
        tenant_id="tenant_sim",
        user_id="user_sim",
        goal="What is EBITDA in corporate accounting?",
    )

    events = []
    async for event in engine.execute_task(task_spec):
        events.append(event)

    event_types = [e.event_type for e in events]
    assert "task_created" in event_types
    assert "planning_started" in event_types
    assert "step_started" in event_types
    assert "step_completed" in event_types
    assert "completed" in event_types

    final_event = next(e for e in events if e.event_type == "completed")
    assert final_event.data.get("verdict") == "PASS"


@pytest.mark.asyncio
async def test_scenario_2_tool_banking_analysis(execution_env) -> None:
    """Scenario 2: Tool-required banking analysis with FinnApiGo."""
    engine, _, _ = execution_env

    task_spec = TaskSpec(
        task_id="task_bank_2",
        tenant_id="tenant_bank",
        user_id="user_bank",
        goal="Fetch account balance and calculate financial margin with $500 transfer",
    )

    events = []
    async for event in engine.execute_task(task_spec):
        events.append(event)

    event_types = [e.event_type for e in events]
    assert "task_created" in event_types
    assert "step_started" in event_types
    assert "completed" in event_types


@pytest.mark.asyncio
async def test_scenario_3_parallel_independent_steps(execution_env) -> None:
    """Scenario 3: Multi-source independent steps run concurrently via asyncio.gather."""
    engine, _, _ = execution_env

    task_spec = TaskSpec(
        task_id="task_multi_3",
        tenant_id="tenant_multi",
        user_id="user_multi",
        goal="Compare two independent financial statements and combine results",
    )

    events = []
    async for event in engine.execute_task(task_spec):
        events.append(event)

    step_started_events = [e for e in events if e.event_type == "step_started"]
    assert len(step_started_events) >= 2

    final_event = next(e for e in events if e.event_type == "completed")
    assert final_event.data.get("verdict") == "PASS"


@pytest.mark.asyncio
async def test_scenario_4_approval_pause_boundary(execution_env) -> None:
    """Scenario 4: Dangerous tool execution triggers approval pause boundary."""
    engine, _, _ = execution_env

    task_spec = TaskSpec(
        task_id="task_approval_4",
        tenant_id="tenant_admin",
        user_id="user_admin",
        goal="Execute privileged terminal shell command to clean up system cache",
    )

    events = []
    async for event in engine.execute_task(task_spec):
        events.append(event)
        # Stop consuming as soon as approval required is emitted
        if event.event_type == "approval_required":
            break

    approval_events = [e for e in events if e.event_type == "approval_required"]
    assert len(approval_events) == 1
    approval_data = approval_events[0].data
    assert "approval_id" in approval_data

    # Verify run state transitioned to WAITING_APPROVAL
    run = engine.get_active_run(approval_events[0].run_id)
    assert run is not None
    assert run.status == RunStatus.WAITING_APPROVAL


@pytest.mark.asyncio
async def test_scenario_4_approval_resume_to_completion(execution_env) -> None:
    """Scenario 4: Dangerous tool execution pauses, then resumes to completion upon approval."""
    engine, _, _ = execution_env

    task_spec = TaskSpec(
        task_id="task_approval_resume_4",
        tenant_id="tenant_admin",
        user_id="user_admin",
        goal="Execute privileged terminal shell command to clean up system cache",
    )

    events = []
    active_run_id = None
    async for event in engine.execute_task(task_spec):
        events.append(event)
        if event.event_type == "approval_required":
            active_run_id = event.run_id
            break

    assert active_run_id is not None
    run = engine.get_active_run(active_run_id)
    assert run is not None
    assert run.status == RunStatus.WAITING_APPROVAL

    resume_events = []
    async for event in engine.resume_run(
        run_id=active_run_id,
        tenant_id="tenant_admin",
        approved=True,
    ):
        resume_events.append(event)

    resume_types = [e.event_type for e in resume_events]
    assert "approval_resolved" in resume_types
    assert "step_completed" in resume_types
    assert "completed" in resume_types

    final_run = engine.get_active_run(active_run_id)
    assert final_run is not None
    assert final_run.status == RunStatus.COMPLETED


@pytest.mark.asyncio
async def test_scenario_5_model_failure_and_switch() -> None:
    """Scenario 5: Model provider rate-limit failure triggers model switch and recovery."""
    backend = MockFailingOnceBackend()
    planner = MockGeneralPlanner(backend=backend)
    engine = ExecutionEngine(planner=planner, backend=backend)

    task_spec = TaskSpec(
        task_id="task_model_fail_5",
        tenant_id="tenant_rec",
        user_id="user_rec",
        goal="Provide architectural summary",
    )

    events = []
    async for event in engine.execute_task(task_spec):
        events.append(event)

    event_types = [e.event_type for e in events]
    assert "model_switched" in event_types
    assert "completed" in event_types
    final_event = next(e for e in events if e.event_type == "completed")
    assert final_event.data.get("verdict") == "PASS"


@pytest.mark.asyncio
async def test_scenario_6_tool_failure_and_retry() -> None:
    """Scenario 6: Tool execution failure triggers step retry and self-healing recovery."""
    backend = MockStreamingBackend()
    tool = MockFailingOnceTool()
    tool_registry = ToolRegistry()
    tool_registry.register(tool)
    planner = MockToolPlanner(backend=backend)
    engine = ExecutionEngine(
        planner=planner,
        tool_registry=tool_registry,
        backend=backend,
    )

    task_spec = TaskSpec(
        task_id="task_tool_fail_6",
        tenant_id="tenant_flaky",
        user_id="user_flaky",
        goal="Fetch account balance with retry",
    )

    events = []
    async for event in engine.execute_task(task_spec):
        events.append(event)

    event_types = [e.event_type for e in events]
    assert "step_retrying" in event_types
    assert "completed" in event_types
    assert tool.call_count == 2


@pytest.mark.asyncio
async def test_scenario_7_verification_failure_and_replan(execution_env) -> None:
    """Scenario 7: Verification critique triggers replan loop and self-correction."""
    _, backend, tool_registry = execution_env
    revising_verifier = RevisingVerifier()
    planner = BoundedPlanner(backend=backend)
    engine = ExecutionEngine(
        planner=planner,
        tool_registry=tool_registry,
        backend=backend,
        verifier=revising_verifier,
    )

    task_spec = TaskSpec(
        task_id="task_replan_7",
        tenant_id="tenant_sim",
        user_id="user_sim",
        goal="What is EBITDA in corporate accounting?",
    )

    events = []
    async for event in engine.execute_task(task_spec):
        events.append(event)

    event_types = [e.event_type for e in events]
    assert "replan_started" in event_types
    assert "completed" in event_types
    assert revising_verifier.call_count == 2


@pytest.mark.asyncio
async def test_scenario_8_cross_tenant_isolation_rejected() -> None:
    """Scenario 8: Cross-tenant isolation breach attempt is immediately REJECTED."""
    verifier = CanonicalVerifier()
    bad_result = verifier.verify_execution(
        tenant_id="tenant_alpha",
        goal="Access data",
        step_outputs=[],
        tool_calls=[{"tool_name": "vault_read", "tenant_id": "tenant_beta"}],
        retrieved_chunks=[],
    )
    assert bad_result.verdict == VerificationVerdict.REJECTED
    assert bad_result.recoverability is False
    assert "tenant_beta" in bad_result.reason

    context = ExecutionContext(
        tenant_id="tenant_alpha",
        user_id="user_alpha",
    )
    with pytest.raises(PermissionError):
        context.assert_tenant_match("tenant_beta")


@pytest.mark.asyncio
async def test_scenario_9_checkpoint_recovery_process_restart() -> None:
    """Scenario 9: Process restart recovery from durable checkpoint via resume_run."""
    checkpoint_mgr = CheckpointManager()
    backend = MockStreamingBackend()
    tool_registry = ToolRegistry()
    tool_registry.register(MockBalanceTool())
    tool_registry.register(MockPrivilegedTool())
    planner = BoundedPlanner(backend=backend)

    # First engine instance runs until approval pause and checkpoints
    engine_1 = ExecutionEngine(
        planner=planner,
        tool_registry=tool_registry,
        checkpoint_manager=checkpoint_mgr,
        backend=backend,
    )

    task_spec = TaskSpec(
        task_id="task_crash_recovery_9",
        tenant_id="tenant_crash",
        user_id="user_crash",
        goal="Execute privileged terminal shell command to clean up system cache",
    )

    run_id = None
    async for event in engine_1.execute_task(task_spec):
        if event.event_type == "approval_required":
            run_id = event.run_id
            break

    assert run_id is not None
    saved_state = await checkpoint_mgr.load_checkpoint(run_id)
    assert saved_state is not None
    assert saved_state.status == RunStatus.WAITING_APPROVAL

    # Fresh engine instance 2 simulates process restart and resumes
    engine_2 = ExecutionEngine(
        planner=planner,
        tool_registry=tool_registry,
        checkpoint_manager=checkpoint_mgr,
        backend=backend,
    )

    resume_events = []
    async for event in engine_2.resume_run(
        run_id=run_id,
        tenant_id="tenant_crash",
        approved=True,
    ):
        resume_events.append(event)

    event_types = [e.event_type for e in resume_events]
    assert "approval_resolved" in event_types
    assert "step_completed" in event_types
    assert "completed" in event_types

    resumed_state = engine_2.get_active_run(run_id)
    assert resumed_state is not None
    assert resumed_state.status == RunStatus.COMPLETED


@pytest.mark.asyncio
async def test_langgraph_execution_adapter_parity() -> None:
    """Test LangGraphExecutionAdapter executes canonical TaskSpec and yields canonical events."""
    adapter = LangGraphExecutionAdapter()
    spec = TaskSpec(
        task_id="task_lg_1",
        tenant_id="tenant_lg",
        user_id="user_lg",
        goal="Explain return on equity ratio",
    )

    events = []
    async for event in adapter.execute_task_spec(spec):
        events.append(event)

    event_types = [e.event_type for e in events]
    assert "task_created" in event_types
    assert "completed" in event_types
    final_event = next(e for e in events if e.event_type == "completed")
    assert final_event.data.get("verdict") == "PASS"
