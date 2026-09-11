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

import pytest

from app.agent.backends.base import (
    AgentBackendInterface,
    BackendRequest,
    BackendResponse,
    BackendStreamChunk,
)
from app.agent.domain.contracts import (
    TaskSpec,
    VerificationVerdict,
)
from app.agent.execution.engine import ExecutionEngine
from app.agent.planning.planner import BoundedPlanner
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
async def test_scenario_5_verifier_failure_recovery() -> None:
    """Scenario 5: Multi-tenant boundary breach detected by Verifier results in immediate REJECTED."""
    verifier = CanonicalVerifier()
    bad_result = verifier.verify_execution(
        tenant_id="tenant_rev",
        goal="Test security boundary",
        step_outputs=[],
        tool_calls=[{"tool_name": "vault_read", "tenant_id": "tenant_intruder"}],
        retrieved_chunks=[],
    )
    assert bad_result.verdict == VerificationVerdict.REJECTED
    assert bad_result.recoverability is False
    assert "tenant_intruder" in bad_result.reason


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
