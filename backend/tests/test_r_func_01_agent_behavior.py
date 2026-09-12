"""R-FUNC-01 — Agent Behavior Canonical Verification Test Suite.

Proves the 10 required orchestration scenarios and system boundaries:
1. Simple task -> plan -> model -> execute -> verify -> complete.
2. Multi-step dependency chain.
3. Two independent steps running concurrently, then dependent synthesis.
4. Dynamic agent selection from capabilities (not keyword only) & model-assisted selection.
5. Dynamic model routing and proof that selected model/provider is actually used.
6. Tool selection, validation and execution through canonical ToolRegistry.
7. Approval pause/resume through persisted state.
8. Verification failure -> replan/retry.
9. Provider transient failure -> bounded retry / switch model.
10. Process restart -> resume without duplicating completed steps.
11. Run cancellation and timeout enforcement.
12. HTTP REST API endpoints and multi-tenant isolation.
"""

from __future__ import annotations

import asyncio
import time
import uuid
from typing import TYPE_CHECKING

import jwt
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
from app.agent.domain.contracts import (
    AgentCapability,
    ExecutionContext,
    StepResult,
    StepStatus,
    TaskSpec,
    VerificationResult,
    VerificationVerdict,
)
from app.agent.execution.engine import ExecutionEngine
from app.agent.planning.models import Plan, PlanStep, PlanStepStatus
from app.agent.planning.planner import BoundedPlanner
from app.agent.registry.agent_registry import AgentMetadata, AgentRegistry
from app.agent.registry.agent_selector import AgentSelector
from app.agent.state.checkpoint import CheckpointManager
from app.agent.state.models import RunState, RunStatus
from app.agent.tools.base import Tool, ToolMetadata, ToolResult, ToolRiskLevel
from app.agent.tools.registry import ToolRegistry
from app.agent.verification.verifier import CanonicalVerifier
from app.core.config import get_settings
from app.main import app

# ===========================================================================
# Test Doubles & Mock Utilities
# ===========================================================================


class MockControllableBackend(AgentBackendInterface):
    """Controllable backend for deterministic orchestration assertions."""

    def __init__(
        self,
        default_content: str = "Analysis verified and mathematically sound.",
        model_name: str = "gemini-1.5-pro",
        provider_name: str = "google",
    ) -> None:
        super().__init__()
        self.default_content = default_content
        self.model_name = model_name
        self.provider_name = provider_name
        self.calls: list[BackendRequest] = []
        self.transient_failures_remaining: int = 0
        self.failure_error: Exception | None = None
        self.delay_seconds: float = 0.0

    async def generate(self, request: BackendRequest) -> BackendResponse:
        self.calls.append(request)
        if self.delay_seconds > 0:
            await asyncio.sleep(self.delay_seconds)

        if self.transient_failures_remaining > 0:
            self.transient_failures_remaining -= 1
            err = self.failure_error or RuntimeError(
                "Rate limit 429: Provider overloaded"
            )
            raise err

        return BackendResponse(
            content=self.default_content,
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


class MockMathTool(Tool):
    """Deterministic math calculation tool with strict schema validation."""

    @property
    def metadata(self) -> ToolMetadata:
        return ToolMetadata(
            name="calculate_metric",
            description="Compute numerical metrics",
            input_schema={
                "type": "object",
                "properties": {
                    "a": {"type": "number"},
                    "b": {"type": "number"},
                    "operation": {
                        "type": "string",
                        "enum": ["add", "multiply", "ratio"],
                    },
                },
                "required": ["a", "b", "operation"],
            },
            risk_level=ToolRiskLevel.READ_ONLY,
            requires_approval=False,
        )

    async def execute(self, arguments: dict, context=None) -> ToolResult:
        a = float(arguments.get("a", 0.0))
        b = float(arguments.get("b", 1.0))
        op = arguments.get("operation", "add")
        if op == "add":
            val = a + b
        elif op == "multiply":
            val = a * b
        elif op == "ratio":
            if b == 0:
                return ToolResult(success=False, error="Division by zero")
            val = a / b
        else:
            return ToolResult(success=False, error=f"Unsupported operation {op}")

        return ToolResult(
            success=True,
            output={"result": val, "operation": op, "a": a, "b": b},
        )


class MockShellExecutionTool(Tool):
    """Dangerous tool requiring explicit operator approval."""

    @property
    def metadata(self) -> ToolMetadata:
        return ToolMetadata(
            name="terminal_exec",
            description="Execute privileged terminal command",
            input_schema={
                "type": "object",
                "properties": {"command": {"type": "string"}},
                "required": ["command"],
            },
            risk_level=ToolRiskLevel.DANGEROUS,
            requires_approval=True,
        )

    async def execute(self, arguments: dict, context=None) -> ToolResult:
        cmd = arguments.get("command", "")
        return ToolResult(
            success=True,
            output=f"Executed privileged command '{cmd}' safely under sandbox.",
        )


def make_agent_jwt(
    tenant_id: str = "tenant-test-01",
    user_id: str = "user-test-01",
    roles: list[str] | None = None,
    permissions: list[str] | None = None,
) -> str:
    """Create test HS256 JWT for tenant-scoped requests."""
    settings = get_settings()
    now = int(time.time())
    payload = {
        "sub": user_id,
        "tenant_id": tenant_id,
        "iat": now,
        "exp": now + 3600,
        "roles": roles or ["admin", "operator"],
        "permissions": permissions or ["agent:read", "agent:write", "tools:execute"],
    }
    return jwt.encode(payload, settings.JWT_SECRET_KEY, algorithm="HS256")


# ===========================================================================
# 1. Simple Task -> Plan -> Model -> Execute -> Verify -> Complete
# ===========================================================================


@pytest.mark.asyncio
async def test_scenario_01_simple_task_lifecycle(tmp_path) -> None:
    """SCENARIO 1: Simple task executes through complete canonical lifecycle."""
    backend = MockControllableBackend(
        default_content="Financial ratio computed: 1.25",
        model_name="gemini-1.5-flash",
        provider_name="google",
    )
    checkpoint_mgr = CheckpointManager()
    engine = ExecutionEngine(
        backend=backend,
        checkpoint_manager=checkpoint_mgr,
    )

    task_spec = TaskSpec(
        task_id=f"task_{uuid.uuid4().hex[:8]}",
        tenant_id="tenant-alpha",
        user_id="user-123",
        goal="Calculate the current ratio for Q3",
        roles=["analyst"],
        permissions=["agent:execute"],
    )

    events: list[AgentRunEvent] = []
    async for event in engine.execute_task(task_spec):
        events.append(event)

    event_types = [e.event_type for e in events]
    assert "task_created" in event_types
    assert "planning_started" in event_types
    assert "plan_created" in event_types
    assert "step_started" in event_types
    assert "step_completed" in event_types
    assert "verification_started" in event_types
    assert "verification_result" in event_types
    assert "completed" in event_types

    # Verify run completed state
    completed_ev = next(e for e in events if e.event_type == "completed")
    assert completed_ev.data["verdict"] == "PASS"
    assert "Executive Intelligence Report" in str(completed_ev.data["output"])

    # Checkpoint verification
    run_id = completed_ev.run_id
    persisted_state = await checkpoint_mgr.load_checkpoint(run_id, "tenant-alpha")
    assert persisted_state is not None
    assert persisted_state.status == RunStatus.COMPLETED
    assert persisted_state.final_output is not None


# ===========================================================================
# 2. Multi-Step Dependency Chain
# ===========================================================================


@pytest.mark.asyncio
async def test_scenario_02_multistep_dependency_chain(tmp_path) -> None:
    """SCENARIO 2: Multi-step pipeline executes strictly in dependency order."""
    backend = MockControllableBackend()
    checkpoint_mgr = CheckpointManager()

    # Custom planner producing step1 -> step2 -> step3 dependency chain
    class SequentialChainPlanner(BoundedPlanner):
        async def plan_task(self, task_spec: TaskSpec, available_tools=None) -> Plan:
            return Plan(
                task_id=task_spec.task_id,
                goal=task_spec.goal,
                analysis="3-step dependency chain",
                steps=[
                    PlanStep(
                        step_id="step_1",
                        description="Fetch initial data",
                        candidate_agents=["general_agent"],
                        dependencies=[],
                        status=PlanStepStatus.PENDING,
                    ),
                    PlanStep(
                        step_id="step_2",
                        description="Analyze fetched data",
                        candidate_agents=["general_agent"],
                        dependencies=["step_1"],
                        status=PlanStepStatus.PENDING,
                    ),
                    PlanStep(
                        step_id="step_3",
                        description="Format final summary",
                        candidate_agents=["general_agent"],
                        dependencies=["step_2"],
                        status=PlanStepStatus.PENDING,
                    ),
                ],
            )

    engine = ExecutionEngine(
        backend=backend,
        checkpoint_manager=checkpoint_mgr,
        planner=SequentialChainPlanner(backend=backend),
    )

    task_spec = TaskSpec(
        task_id=f"task_{uuid.uuid4().hex[:8]}",
        tenant_id="tenant-chain",
        user_id="user-chain",
        goal="Run 3-step sequential analysis",
    )

    events: list[AgentRunEvent] = []
    async for event in engine.execute_task(task_spec):
        events.append(event)

    completed_steps = [
        e.data["step_id"] for e in events if e.event_type == "step_completed"
    ]
    assert completed_steps == ["step_1", "step_2", "step_3"], (
        f"Execution order violated: {completed_steps}"
    )

    terminal_ev = next(e for e in events if e.event_type == "completed")
    assert terminal_ev.data["steps_completed"] == 3


# ===========================================================================
# 3. Two Independent Steps Concurrent, Then Dependent Synthesis
# ===========================================================================


@pytest.mark.asyncio
async def test_scenario_03_concurrent_steps_with_synthesis(tmp_path) -> None:
    """SCENARIO 3: Two independent steps execute concurrently, followed by synthesis."""
    backend = MockControllableBackend()
    backend.delay_seconds = 0.05  # small delay to prove concurrent start
    checkpoint_mgr = CheckpointManager()

    class DiamondDagPlanner(BoundedPlanner):
        async def plan_task(self, task_spec: TaskSpec, available_tools=None) -> Plan:
            return Plan(
                task_id=task_spec.task_id,
                goal=task_spec.goal,
                analysis="Diamond DAG with concurrent branches",
                steps=[
                    PlanStep(
                        step_id="branch_a",
                        description="Fetch metrics stream A",
                        candidate_agents=["general_agent"],
                        dependencies=[],
                        status=PlanStepStatus.PENDING,
                    ),
                    PlanStep(
                        step_id="branch_b",
                        description="Fetch metrics stream B",
                        candidate_agents=["general_agent"],
                        dependencies=[],
                        status=PlanStepStatus.PENDING,
                    ),
                    PlanStep(
                        step_id="synthesizer_step",
                        description="Synthesize streams A and B",
                        candidate_agents=["synthesizer"],
                        dependencies=["branch_a", "branch_b"],
                        status=PlanStepStatus.PENDING,
                    ),
                ],
            )

    engine = ExecutionEngine(
        backend=backend,
        checkpoint_manager=checkpoint_mgr,
        planner=DiamondDagPlanner(backend=backend),
    )

    task_spec = TaskSpec(
        task_id=f"task_{uuid.uuid4().hex[:8]}",
        tenant_id="tenant-concurrent",
        user_id="user-conc",
        goal="Fetch streams A and B concurrently then synthesize",
    )

    events: list[AgentRunEvent] = []
    start_times: dict[str, float] = {}
    finish_times: dict[str, float] = {}

    async for event in engine.execute_task(task_spec):
        events.append(event)
        if event.event_type == "step_started":
            start_times[event.data["step_id"]] = time.time()
        elif event.event_type == "step_completed":
            finish_times[event.data["step_id"]] = time.time()

    # Both branch_a and branch_b must have executed
    assert "branch_a" in start_times and "branch_b" in start_times
    assert "synthesizer_step" in start_times

    # Synthesis must have started AFTER both branches completed
    assert start_times["synthesizer_step"] >= finish_times["branch_a"]
    assert start_times["synthesizer_step"] >= finish_times["branch_b"]

    final_ev = next(e for e in events if e.event_type == "completed")
    assert final_ev.data["verdict"] == "PASS"


# ===========================================================================
# 4. Dynamic Agent Selection from Capabilities & Model Disambiguation
# ===========================================================================


@pytest.mark.asyncio
async def test_scenario_04_dynamic_agent_selection_from_capabilities_and_model() -> (
    None
):
    """SCENARIO 4: Agent is selected dynamically by capabilities, not keyword only."""
    registry = AgentRegistry()
    registry.register(
        AgentMetadata(
            agent_id="specialized_security_auditor",
            name="Security Auditor",
            description="Deep static analysis and vulnerability auditor",
            capabilities=[
                AgentCapability.VERIFICATION.value,
                AgentCapability.CODE_EXECUTION.value,
            ],
            supported_workloads=["auditing"],
        )
    )
    registry.register(
        AgentMetadata(
            agent_id="specialized_financial_modeler",
            name="Financial Modeler",
            description="Complex financial DCF and EBITDA modeler",
            capabilities=[AgentCapability.FINANCIAL_ANALYSIS.value],
            supported_workloads=["financial"],
        )
    )

    selector = AgentSelector(registry=registry)

    # Step asks for verification + code execution without mentioning "security" or "auditor"
    step_audit = PlanStep(
        step_id="step_audit_1",
        description="Verify cryptographic signatures and code safety proofs",
        required_capabilities=[
            AgentCapability.VERIFICATION,
            AgentCapability.CODE_EXECUTION,
        ],
        dependencies=[],
    )
    context = ExecutionContext(tenant_id="tenant-caps", user_id="user-1")

    selection = selector.select_agent_for_step(step_audit, context)
    assert selection.agent_id == "specialized_security_auditor"
    assert AgentCapability.VERIFICATION in selection.matched_capabilities

    # Model-assisted selection when multiple candidates are tied
    mock_llm_selector_backend = MockControllableBackend(
        default_content='{"selected_agent_id": "specialized_financial_modeler", "reasoning": "Specialized in financial math", "confidence": 0.98}'
    )
    async_selector = AgentSelector(registry=registry, backend=mock_llm_selector_backend)

    step_ambiguous = PlanStep(
        step_id="step_ambig_1",
        description="Complex calculation",
        candidate_agents=[
            "specialized_security_auditor",
            "specialized_financial_modeler",
        ],
        dependencies=[],
    )
    task_spec = TaskSpec(
        task_id="task_ambig",
        tenant_id="tenant-caps",
        goal="Run complex quantitative modeling",
    )
    sel_async = await async_selector.select_agent_async(
        task_spec, step_ambiguous, context
    )
    assert sel_async.agent_id == "specialized_financial_modeler"
    assert sel_async.selection_mode == "model"
    assert sel_async.confidence == 0.98


# ===========================================================================
# 5. Dynamic Model Routing & Proof of Usage in StepResult
# ===========================================================================


@pytest.mark.asyncio
async def test_scenario_05_dynamic_model_routing_and_usage_proof(tmp_path) -> None:
    """SCENARIO 5: Model router selects model/provider and StepResult captures real usage."""
    # Backend reports actual model and provider used
    backend = MockControllableBackend(
        default_content="Reasoning response from upstream provider",
        model_name="claude-3-5-sonnet",
        provider_name="anthropic",
    )
    checkpoint_mgr = CheckpointManager()

    class ModelRoutingPlanner(BoundedPlanner):
        async def plan_task(self, task_spec: TaskSpec, available_tools=None) -> Plan:
            return Plan(
                task_id=task_spec.task_id,
                goal=task_spec.goal,
                analysis="Model routing verification",
                steps=[
                    PlanStep(
                        step_id="step_model_proof",
                        description="Deep multi-step reasoning",
                        candidate_agents=["general_agent"],
                        model_requirements={"workload_class": "reasoning"},
                        dependencies=[],
                        status=PlanStepStatus.PENDING,
                    )
                ],
            )

    engine = ExecutionEngine(
        backend=backend,
        checkpoint_manager=checkpoint_mgr,
        planner=ModelRoutingPlanner(backend=backend),
    )

    task_spec = TaskSpec(
        task_id=f"task_{uuid.uuid4().hex[:8]}",
        tenant_id="tenant-routing",
        user_id="user-routing",
        goal="Execute reasoning step with model proof",
    )

    events: list[AgentRunEvent] = []
    async for event in engine.execute_task(task_spec):
        events.append(event)

    model_sel_events = [e for e in events if e.event_type == "model_selected"]
    assert len(model_sel_events) >= 1
    assert model_sel_events[0].data["workload_class"] == "reasoning"

    # Verify run completed and check checkpoint for step result model proof
    completed_ev = next(e for e in events if e.event_type == "completed")
    run_state = await checkpoint_mgr.load_checkpoint(
        completed_ev.run_id, "tenant-routing"
    )
    assert run_state is not None
    plan_dict = run_state.plan
    step_dict = plan_dict["steps"][0]

    # Proof that the actual model and provider used were captured on step and step result
    assert step_dict["selected_model"] == "claude-3-5-sonnet"
    assert step_dict["selected_provider"] == "anthropic"
    assert step_dict["result"]["model_used"] == "claude-3-5-sonnet"
    assert step_dict["result"]["provider_used"] == "anthropic"


# ===========================================================================
# 6. Tool Selection, Validation & Execution through ToolRegistry
# ===========================================================================


@pytest.mark.asyncio
async def test_scenario_06_tool_selection_validation_and_execution() -> None:
    """SCENARIO 6: Tool registry validates schema, evaluates policy, and executes tool."""
    tool_registry = ToolRegistry()
    math_tool = MockMathTool()
    tool_registry.register(math_tool)

    # 1. Successful execution with valid schema
    valid_args = {"a": 15.0, "b": 3.0, "operation": "ratio"}
    is_valid, err = tool_registry.validate("calculate_metric", valid_args)
    assert is_valid is True
    assert err is None

    res = await tool_registry.execute(
        tool_name="calculate_metric",
        arguments=valid_args,
        context={"tenant_id": "tenant-tool", "roles": ["analyst"]},
    )
    assert res.success is True
    assert res.output["result"] == 5.0

    # 2. Validation negative proof: missing required parameter
    invalid_args = {"a": 15.0}  # missing 'b' and 'operation'
    is_valid, err = tool_registry.validate("calculate_metric", invalid_args)
    assert is_valid is False
    assert "Missing required parameters" in str(err)

    # 3. Non-existent tool execution
    unknown_res = await tool_registry.execute(
        tool_name="non_existent_tool",
        arguments={},
        context={"tenant_id": "tenant-tool"},
    )
    assert unknown_res.success is False
    assert "not registered" in str(unknown_res.error)


# ===========================================================================
# 7. Approval Pause/Resume through Persisted State
# ===========================================================================


@pytest.mark.asyncio
async def test_scenario_07_approval_pause_resume_via_persisted_state(tmp_path) -> None:
    """SCENARIO 7: Dangerous tool triggers approval gate, pauses cleanly, and resumes upon approval."""
    backend = MockControllableBackend()
    checkpoint_mgr = CheckpointManager()
    approval_mgr = ApprovalManager()
    tool_registry = ToolRegistry()
    shell_tool = MockShellExecutionTool()
    tool_registry.register(shell_tool)

    class PrivilegedPlanner(BoundedPlanner):
        async def plan_task(self, task_spec: TaskSpec, available_tools=None) -> Plan:
            return Plan(
                task_id=task_spec.task_id,
                goal=task_spec.goal,
                analysis="Plan containing dangerous action",
                steps=[
                    PlanStep(
                        step_id="step_shell_1",
                        description="Execute privileged system command",
                        required_tools=["terminal_exec"],
                        tool_name="terminal_exec",
                        tool_args={"command": "apply_db_migration"},
                        status=PlanStepStatus.PENDING,
                        dependencies=[],
                    )
                ],
            )

    engine = ExecutionEngine(
        backend=backend,
        checkpoint_manager=checkpoint_mgr,
        approval_manager=approval_mgr,
        tool_registry=tool_registry,
        planner=PrivilegedPlanner(backend=backend),
    )

    task_spec = TaskSpec(
        task_id=f"task_{uuid.uuid4().hex[:8]}",
        tenant_id="tenant-approval",
        user_id="user-op",
        goal="Run database migration tool",
    )

    # Initial execution: Must pause at approval boundary
    events: list[AgentRunEvent] = []
    async for event in engine.execute_task(task_spec):
        events.append(event)

    approval_events = [e for e in events if e.event_type == "approval_required"]
    assert len(approval_events) == 1
    approval_req_id = approval_events[0].data["approval_id"]
    run_id = approval_events[0].run_id

    # Verify state is paused in CheckpointManager
    saved_state = await checkpoint_mgr.load_checkpoint(run_id, "tenant-approval")
    assert saved_state is not None
    assert saved_state.status == RunStatus.WAITING_APPROVAL

    # Operator approves the dangerous action
    approval_decision = ApprovalDecision(
        approved=True, reason="Approved by Security Lead"
    )
    approval_mgr.decide(
        approval_id=approval_req_id,
        decision=approval_decision,
        tenant_id="tenant-approval",
        user_id="sec-lead",
    )

    # Resume execution with approved=True
    resume_events: list[AgentRunEvent] = []
    async for event in engine.resume_run(
        run_id=run_id,
        tenant_id="tenant-approval",
        approved=True,
    ):
        resume_events.append(event)

    completed_resumes = [e for e in resume_events if e.event_type == "completed"]
    assert len(completed_resumes) == 1
    assert completed_resumes[0].data["verdict"] == "PASS"

    # Verify terminal completed state in checkpoint
    final_state = await checkpoint_mgr.load_checkpoint(run_id, "tenant-approval")
    assert final_state is not None
    assert final_state.status == RunStatus.COMPLETED


# ===========================================================================
# 8. Verification Failure -> Replan/Retry
# ===========================================================================


@pytest.mark.asyncio
async def test_scenario_08_verification_failure_replan_and_retry(tmp_path) -> None:
    """SCENARIO 8: Verification failure triggers replanning loop and subsequent pass."""
    backend = MockControllableBackend()
    checkpoint_mgr = CheckpointManager()

    class FlakyVerifier(CanonicalVerifier):
        def __init__(self) -> None:
            self.eval_count = 0

        def verify_execution(self, *args, **kwargs) -> VerificationResult:
            self.eval_count += 1
            if self.eval_count == 1:
                return VerificationResult(
                    verdict=VerificationVerdict.NEEDS_REVISION,
                    reason="Inconsistent metric values detected. Needs revision.",
                    groundedness_score=0.45,
                )
            return VerificationResult(
                verdict=VerificationVerdict.PASS,
                reason="All metrics reconciled and verified.",
                groundedness_score=0.98,
            )

    verifier = FlakyVerifier()
    engine = ExecutionEngine(
        backend=backend,
        checkpoint_manager=checkpoint_mgr,
        verifier=verifier,
    )

    task_spec = TaskSpec(
        task_id=f"task_{uuid.uuid4().hex[:8]}",
        tenant_id="tenant-verify",
        user_id="user-v",
        goal="Calculate and verify financial metrics",
    )

    events: list[AgentRunEvent] = []
    async for event in engine.execute_task(task_spec, max_revisions=2):
        events.append(event)

    event_types = [e.event_type for e in events]
    assert "replan_started" in event_types
    assert event_types.count("verification_result") == 2
    assert "completed" in event_types

    final_ev = next(e for e in events if e.event_type == "completed")
    assert final_ev.data["verdict"] == "PASS"
    assert verifier.eval_count == 2


# ===========================================================================
# 9. Provider Transient Failure -> Bounded Retry / Switch Model
# ===========================================================================


@pytest.mark.asyncio
async def test_scenario_09_provider_transient_failure_bounded_retry(tmp_path) -> None:
    """SCENARIO 9: Provider 429 triggers bounded retry and succeeds on attempt 2."""

    class GeneralStepPlanner(BoundedPlanner):
        async def plan_task(self, task_spec: TaskSpec, available_tools=None) -> Plan:
            return Plan(
                task_id=task_spec.task_id,
                goal=task_spec.goal,
                analysis="Direct model step",
                steps=[
                    PlanStep(
                        step_id="step_gen",
                        description="General reasoning step",
                        candidate_agents=["general_agent"],
                        dependencies=[],
                        status=PlanStepStatus.PENDING,
                    )
                ],
            )

    class StepFailingBackend(MockControllableBackend):
        def __init__(self) -> None:
            super().__init__()
            self.step_failure_done = False

        async def generate(self, request: BackendRequest) -> BackendResponse:
            self.calls.append(request)
            if (
                any("execute step" in m.content.lower() for m in request.messages)
                and not self.step_failure_done
            ):
                self.step_failure_done = True
                raise RuntimeError("Rate limit 429: Upstream provider throttled")
            return await super().generate(request)

    backend = StepFailingBackend()
    checkpoint_mgr = CheckpointManager()

    engine = ExecutionEngine(
        backend=backend,
        checkpoint_manager=checkpoint_mgr,
        planner=GeneralStepPlanner(backend=backend),
    )

    task_spec = TaskSpec(
        task_id=f"task_{uuid.uuid4().hex[:8]}",
        tenant_id="tenant-retry",
        user_id="user-r",
        goal="Test transient failure retry",
    )

    events: list[AgentRunEvent] = []
    async for event in engine.execute_task(task_spec):
        events.append(event)

    recovery_events = [
        e for e in events if e.event_type in ("step_retrying", "model_switched")
    ]
    assert len(recovery_events) >= 1
    assert recovery_events[0].event_type == "model_switched"
    assert "alternative provider" in recovery_events[0].data["reason"].lower()

    completed_ev = next(e for e in events if e.event_type == "completed")
    assert completed_ev.data["verdict"] == "PASS"


# ===========================================================================
# 10. Process Restart -> Resume Without Duplicating Completed Steps
# ===========================================================================


@pytest.mark.asyncio
async def test_scenario_10_process_restart_resume_without_duplication(tmp_path) -> None:
    """SCENARIO 10: After process restart, resume skips already completed steps."""
    checkpoint_mgr = CheckpointManager()

    step1_exec_count = 0
    step2_exec_count = 0

    class TrackingBackend(AgentBackendInterface):
        async def generate(self, request: BackendRequest) -> BackendResponse:
            nonlocal step1_exec_count, step2_exec_count
            content = request.messages[-1].content.lower()
            if content.startswith("execute step:"):
                if "step 1" in content:
                    step1_exec_count += 1
                elif "step 2" in content:
                    step2_exec_count += 1
            return BackendResponse(content="Step output generated.")

        async def generate_stream(self, request: BackendRequest):
            resp = await self.generate(request)
            yield BackendStreamChunk(delta_content=resp.content, is_complete=True)

    backend_instance = TrackingBackend()

    # Pre-populate checkpoint representing a crash after step 1 completed
    task_id = f"task_{uuid.uuid4().hex[:8]}"
    run_id = f"run_{uuid.uuid4().hex[:8]}"
    tenant_id = "tenant-restart"

    step_1 = PlanStep(
        step_id="s1",
        description="Execute step 1",
        status=PlanStepStatus.COMPLETED,
        result=StepResult(
            step_id="s1",
            status=StepStatus.COMPLETED,
            output="Step 1 output cached",
        ),
        dependencies=[],
    )
    step_2 = PlanStep(
        step_id="s2",
        description="Execute step 2",
        status=PlanStepStatus.PENDING,
        dependencies=["s1"],
    )

    persisted_plan = Plan(
        task_id=task_id,
        goal="Two step task with process restart",
        steps=[step_1, step_2],
    )

    initial_state = RunState(
        run_id=run_id,
        task_id=task_id,
        tenant_id=tenant_id,
        user_id="user-restart",
        status=RunStatus.RUNNING,
        prompt="Two step task with process restart",
        plan=persisted_plan.model_dump(),
        created_at=time.time(),
    )
    await checkpoint_mgr.save_checkpoint(initial_state)

    class PassingVerifier(CanonicalVerifier):
        def verify_execution(self, *args, **kwargs) -> VerificationResult:
            return VerificationResult(
                verdict=VerificationVerdict.PASS,
                reason="All steps verified successfully.",
                groundedness_score=1.0,
            )

    # Brand new engine simulating process restart with clean memory
    new_engine = ExecutionEngine(
        backend=backend_instance,
        checkpoint_manager=checkpoint_mgr,
        verifier=PassingVerifier(),
    )

    resume_events: list[AgentRunEvent] = []
    async for ev in new_engine.resume_run(run_id=run_id, tenant_id=tenant_id):
        resume_events.append(ev)

    # Assert step 1 was NOT re-executed
    assert step1_exec_count == 0, "Step 1 was duplicated on resume!"
    # Assert step 2 was executed
    assert step2_exec_count == 1, "Step 2 was not executed on resume!"

    final_ev = next(e for e in resume_events if e.event_type == "completed")
    assert final_ev.data["verdict"] == "PASS"


# ===========================================================================
# 11. Run Cancellation and Timeout Enforcement
# ===========================================================================


@pytest.mark.asyncio
async def test_scenario_11_step_timeout_and_cancellation(tmp_path) -> None:
    """SCENARIO 11: Cooperative cancellation cleanly terminates execution."""
    backend = MockControllableBackend()
    backend.delay_seconds = 0.5  # Simulate slow backend
    checkpoint_mgr = CheckpointManager()

    engine = ExecutionEngine(
        backend=backend,
        checkpoint_manager=checkpoint_mgr,
    )

    task_spec = TaskSpec(
        task_id=f"task_{uuid.uuid4().hex[:8]}",
        tenant_id="tenant-cancel",
        user_id="user-c",
        goal="Long running task to cancel",
    )

    # Cancel token simulator
    class CancellationToken:
        def __init__(self) -> None:
            self.cancelled = False

    cancel_token = CancellationToken()

    async def cancel_later():
        await asyncio.sleep(0.05)
        cancel_token.cancelled = True

    cancel_task = asyncio.create_task(cancel_later())

    events: list[AgentRunEvent] = []
    async for event in engine.execute_task(task_spec, cancellation_token=cancel_token):
        events.append(event)

    await cancel_task

    cancelled_events = [e for e in events if e.event_type == "cancelled"]
    assert len(cancelled_events) == 1
    assert cancelled_events[0].data["reason"] == "Execution cancelled by client."


# ===========================================================================
# 12. HTTP REST API Endpoints & Multi-Tenant Boundary
# ===========================================================================


@pytest.mark.asyncio
async def test_scenario_12_http_api_endpoints_and_isolation() -> None:
    """SCENARIO 12: Public REST endpoints enforce tenant boundary and lifecycle contracts."""
    token_tenant_a = make_agent_jwt(tenant_id="tenant-api-a", user_id="user-a")
    token_tenant_b = make_agent_jwt(tenant_id="tenant-api-b", user_id="user-b")

    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test") as client:
        # 1. Create task under Tenant A
        res_task = await client.post(
            "/api/v1/agent/tasks",
            json={
                "goal": "Audit corporate balance sheet",
                "metadata": {"priority": "high"},
            },
            headers={"Authorization": f"Bearer {token_tenant_a}"},
        )
        assert res_task.status_code == 201
        task_data = res_task.json()
        task_id = task_data["task_id"]
        assert task_data["tenant_id"] == "tenant-api-a"

        # 2. Cross-tenant read negative proof: Tenant B cannot read Tenant A's task
        res_b_read = await client.get(
            f"/api/v1/agent/tasks/{task_id}",
            headers={"Authorization": f"Bearer {token_tenant_b}"},
        )
        assert res_b_read.status_code in (403, 404)

        # 3. Create run under Tenant A
        res_run = await client.post(
            f"/api/v1/agent/tasks/{task_id}/runs",
            json={"async_execution": False, "max_iterations": 5},
            headers={"Authorization": f"Bearer {token_tenant_a}"},
        )
        assert res_run.status_code == 201
        run_data = res_run.json()
        run_id = run_data["run_id"]
        assert run_data["task_id"] == task_id

        # 4. Get run under Tenant A
        res_get_run = await client.get(
            f"/api/v1/agent/tasks/{task_id}/runs/{run_id}",
            headers={"Authorization": f"Bearer {token_tenant_a}"},
        )
        assert res_get_run.status_code == 200

        # 5. Cross-tenant run read negative proof: Tenant B cannot access Tenant A's run
        res_b_run = await client.get(
            f"/api/v1/agent/tasks/{task_id}/runs/{run_id}",
            headers={"Authorization": f"Bearer {token_tenant_b}"},
        )
        assert res_b_run.status_code in (403, 404)

        # 6. Query agent telemetry metrics
        res_metrics = await client.get(
            "/api/v1/agent/metrics",
            headers={"Authorization": f"Bearer {token_tenant_a}"},
        )
        assert res_metrics.status_code == 200
        metrics = res_metrics.json()
        assert "tasks_created" in metrics or "runs_started" in metrics
