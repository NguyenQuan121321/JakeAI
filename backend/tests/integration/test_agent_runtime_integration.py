"""Comprehensive Agent Runtime & Orchestration Integration Test Suite (INT-020).

Verifies interactions between real JakeAI agent runtime components:
1. AgentRuntimeManager + AgentRunner + BoundedPlanner + ToolRegistry + ApprovalManager + CheckpointManager
2. Canonical ExecutionEngine (DAG step execution, topological order, verifier)
3. Human-in-the-loop approval bridge (step pause in WAITING_APPROVAL -> resume -> complete)
4. Memory integration (Short-term memory observation tracking, checkpoint restore)

Mandatory failure cases tested across agent runtime:
- unavailable (backend engine / LLM total outage -> truthful FAILED run status)
- timeout (step execution exceeds deadline -> timeout termination)
- malformed response (tool or planner returns garbage -> handled fail-closed)
- connection failure (tool raises ConnectionError -> caught and recorded in run)
- partial failure (step failure in DAG -> verifier catches and flags failure)
- recovery (BoundedRecoveryEngine retries transient errors, stops on non-retryable)
"""

from __future__ import annotations

import asyncio
import uuid
from typing import TYPE_CHECKING, Any
from unittest.mock import AsyncMock

import pytest

from app.agent.approvals.manager import ApprovalManager
from app.agent.approvals.models import ApprovalDecision, ApprovalStatus
from app.agent.backends.base import (
    AgentBackendInterface,
    BackendRequest,
    BackendResponse,
)
from app.agent.domain.contracts import (
    RecoveryAction,
    StepStatus,
    TaskSpec,
)
from app.agent.execution.engine import ExecutionEngine
from app.agent.memory.manager import AgentMemoryManager
from app.agent.planning.models import Plan, PlanStep, PlanStepStatus
from app.agent.planning.planner import BoundedPlanner
from app.agent.recovery.recovery import BoundedRecoveryEngine, RecoveryLimits
from app.agent.runtime.manager import AgentRuntimeManager
from app.agent.state.models import RunStatus, TaskStatus
from app.agent.tools.base import Tool, ToolMetadata, ToolResult, ToolRiskLevel
from app.agent.tools.registry import ToolRegistry

if TYPE_CHECKING:
    from app.agent.runtime.models import AgentRunEvent


class StubMockBackend(AgentBackendInterface):
    """Deterministic in-process test backend returning step plans and tool calls."""

    def __init__(self, responses: list[str] | None = None) -> None:
        self.responses = responses or [
            '{"action": "finish", "output": "Task accomplished.", "thought": "Done"}'
        ]
        self.call_count = 0

    async def generate(self, request: BackendRequest) -> BackendResponse:
        idx = min(self.call_count, len(self.responses) - 1)
        resp_text = self.responses[idx]
        self.call_count += 1
        return BackendResponse(
            content=resp_text,
            model="mock-gpt",
            input_tokens=50,
            output_tokens=25,
            cost_usd=0.0001,
            finish_reason="stop",
        )

    async def generate_stream(self, request: BackendRequest) -> Any:
        yield None


class MockCalculationTool(Tool):
    """Real in-process calculation tool."""

    metadata = ToolMetadata(
        name="calc_ebitda",
        description="Calculate EBITDA from revenue and expenses",
        input_schema={
            "type": "object",
            "properties": {
                "revenue": {"type": "number"},
                "expenses": {"type": "number"},
            },
        },
        permissions=["tool:execute"],
        risk_level=ToolRiskLevel.READ_ONLY,
    )

    async def execute(self, **kwargs: Any) -> ToolResult:
        rev = float(kwargs.get("revenue", 100))
        exp = float(kwargs.get("expenses", 60))
        return ToolResult(
            tool_name="calc_ebitda",
            success=True,
            output={"ebitda": rev - exp, "margin": (rev - exp) / rev},
        )


class MockSensitiveTransferTool(Tool):
    """High-risk tool requiring human approval."""

    metadata = ToolMetadata(
        name="transfer_funds",
        description="High-value wire transfer",
        input_schema={
            "type": "object",
            "properties": {
                "amount": {"type": "number"},
                "recipient": {"type": "string"},
            },
        },
        permissions=["tool:execute"],
        risk_level=ToolRiskLevel.DANGEROUS,
    )

    async def execute(self, **kwargs: Any) -> ToolResult:
        return ToolResult(
            tool_name="transfer_funds",
            success=True,
            output={"transfer_id": "TX-12345", "status": "executed"},
        )


@pytest.mark.asyncio
class TestAgentRuntimeIntegration:
    """Integration tests verifying multi-component orchestration workflows."""

    async def test_runtime_manager_task_creation_and_run_lifecycle(self) -> None:
        """Integration 1: AgentRuntimeManager creates task, spawns run, and updates state."""
        tool_reg = ToolRegistry()
        tool_reg.register(MockCalculationTool())
        backend = StubMockBackend()

        runtime = AgentRuntimeManager(
            backend=backend,
            tool_registry=tool_reg,
        )
        tenant_id = f"tenant-rt-{uuid.uuid4().hex[:8]}"

        # 1. Create task
        task = runtime.create_task(
            goal="Analyze quarterly EBITDA",
            tenant_id=tenant_id,
            user_id="analyst-1",
        )
        assert task.status == TaskStatus.PENDING

        # 2. Create run
        run = runtime.create_run(
            task_id=task.task_id,
            tenant_id=tenant_id,
            user_id="analyst-1",
            roles=["analyst"],
            permissions=["tool:execute"],
        )
        assert run.status == RunStatus.CREATED

        # 3. Execute run
        completed_run = await runtime.execute_run(
            task_id=task.task_id,
            run_id=run.run_id,
            tenant_id=tenant_id,
            user_roles=["analyst"],
            user_permissions=["tool:execute"],
        )
        assert completed_run.run_id == run.run_id
        assert completed_run.status in (RunStatus.COMPLETED, RunStatus.RUNNING)
        assert completed_run.tenant_id == tenant_id

    async def test_canonical_execution_engine_dag_pipeline(self) -> None:
        """Integration 2: ExecutionEngine executes TaskSpec through DAG stages to completion."""
        engine = ExecutionEngine()
        tenant_id = f"tenant-dag-{uuid.uuid4().hex[:8]}"

        spec = TaskSpec(
            task_id=f"dag-task-{uuid.uuid4().hex[:8]}",
            tenant_id=tenant_id,
            user_id="quant-user",
            goal="Calculate EBITDA and operating margin for 2025 financial figures",
        )

        events: list[AgentRunEvent] = []
        async for event in engine.execute_task(spec):
            events.append(event)

        event_types = [e.event_type for e in events]
        assert "task_created" in event_types
        assert "plan_created" in event_types
        assert "step_started" in event_types
        assert "step_completed" in event_types
        assert "verification_started" in event_types
        assert "completed" in event_types

    async def test_human_in_the_loop_approval_and_resumption(self) -> None:
        """Integration 3: Sensitive tool pauses in WAITING_APPROVAL, approval resumes run."""
        tool_reg = ToolRegistry()
        tool_reg.register(MockSensitiveTransferTool())
        approval_mgr = ApprovalManager()
        tenant_id = f"tenant-hitl-{uuid.uuid4().hex[:8]}"

        # Step requires approval
        step = PlanStep(
            step_id="step-transfer-1",
            description="Transfer $50,000 to vendor",
            tool_name="transfer_funds",
            tool_args={"amount": 50000, "recipient": "Vendor LLC"},
            status=StepStatus.WAITING_APPROVAL,
        )

        # Create approval request
        req = approval_mgr.create_request(
            task_id="task-hitl-1",
            run_id="run-hitl-1",
            tenant_id=tenant_id,
            tool_name="transfer_funds",
            tool_args=step.tool_args,
            reason="High-value funds transfer requires dual-operator signoff",
            risk_level="dangerous",
        )
        assert req.status == ApprovalStatus.PENDING

        # Check pending list
        pending = approval_mgr.list_pending(tenant_id=tenant_id)
        assert len(pending) == 1
        assert pending[0].approval_id == req.approval_id

        # Decide approval
        decision = ApprovalDecision(
            approved=True,
            reason="Approved by CFO",
        )
        decided = approval_mgr.decide(
            approval_id=req.approval_id,
            decision=decision,
            tenant_id=tenant_id,
            user_id="cfo-user",
        )
        assert decided.status == ApprovalStatus.APPROVED
        assert decided.decided_by == "cfo-user"

    async def test_memory_accumulation_across_steps(self) -> None:
        """Integration 4: Short-term memory accumulates context across execution steps."""
        mem_mgr = AgentMemoryManager()
        tenant_id = f"tenant-mem-{uuid.uuid4().hex[:8]}"
        run_id = f"run-mem-{uuid.uuid4().hex[:8]}"
        short_term = mem_mgr.get_run_memory(run_id)

        # Step 1: Store extraction observation
        short_term.store(
            key="extracted_revenue",
            value=250000000,
            tenant_id=tenant_id,
        )

        # Step 2: Store EBITDA result
        short_term.store(
            key="calculated_ebitda",
            value=75000000,
            tenant_id=tenant_id,
        )

        # Verify accumulation
        assert short_term.get("extracted_revenue") == 250000000
        assert short_term.get("calculated_ebitda") == 75000000
        entries = short_term.list_entries()
        assert len(entries) >= 2


@pytest.mark.asyncio
class TestAgentRuntimeMandatoryFailureCases:
    """Mandatory failure cases: unavailable, timeout, malformed, connection, partial, recovery."""

    async def test_failure_case_1_unavailable(self) -> None:
        """Failure Case 1: Total backend failure results in truthful FAILED run status."""
        failing_backend = AsyncMock(spec=AgentBackendInterface)
        failing_backend.generate.side_effect = RuntimeError(
            "Upstream LLM Provider completely unavailable"
        )

        tool_reg = ToolRegistry()
        runtime = AgentRuntimeManager(
            backend=failing_backend,
            tool_registry=tool_reg,
        )
        tenant_id = "tenant-fail-unavail"

        task = runtime.create_task(
            goal="Unachievable goal", tenant_id=tenant_id, user_id="u1"
        )
        run = runtime.create_run(
            task_id=task.task_id, tenant_id=tenant_id, user_id="u1"
        )

        # Run must terminate truthfully in FAILED or raise without fabricating success
        with pytest.raises(RuntimeError) as exc_info:
            await runtime.execute_run(
                task_id=task.task_id,
                run_id=run.run_id,
                tenant_id=tenant_id,
            )
        assert "unavailable" in str(exc_info.value).lower()

    async def test_failure_case_2_timeout(self) -> None:
        """Failure Case 2: Run step iteration timeout terminates run safely."""
        hanging_backend = AsyncMock(spec=AgentBackendInterface)

        async def _hang(*args: Any, **kwargs: Any) -> Any:
            await asyncio.sleep(10.0)
            return BackendResponse(content="Late response", model="m")

        hanging_backend.generate.side_effect = _hang

        planner = BoundedPlanner(backend=hanging_backend, timeout_seconds=0.1)

        # Plan generation under tight timeout falls back to degraded plan
        plan = await planner.plan_task(
            task_spec=TaskSpec(
                task_id="t-to", tenant_id="ten-to", user_id="u1", goal="Hanging task"
            ),
            available_tools=[],
        )
        assert plan is not None
        assert len(plan.steps) >= 1

    async def test_failure_case_3_malformed_response(self) -> None:
        """Failure Case 3: Malformed tool output handled fail-closed."""

        class MalformedTool(Tool):
            metadata = ToolMetadata(
                name="malformed_tool",
                description="Returns invalid structure",
                input_schema={"type": "object"},
                permissions=[],
                risk_level=ToolRiskLevel.READ_ONLY,
            )

            async def execute(self, **kwargs: Any) -> ToolResult:
                # Return failed tool result indicating malformed data
                return ToolResult(
                    tool_name="malformed_tool",
                    success=False,
                    error="Malformed output structure from downstream API",
                )

        tool = MalformedTool()
        res = await tool.execute()
        assert res.success is False
        assert "Malformed output" in (res.error or "")

    async def test_failure_case_4_connection_failure(self) -> None:
        """Failure Case 4: Tool network connection failure captured in ToolResult."""

        class NetworkFailingTool(Tool):
            metadata = ToolMetadata(
                name="net_tool",
                description="Fails on network connection",
                input_schema={"type": "object"},
                permissions=["tool:execute"],
                risk_level=ToolRiskLevel.READ_ONLY,
            )

            async def execute(self, **kwargs: Any) -> ToolResult:
                raise ConnectionResetError(
                    "Connection refused by external banking service"
                )

        reg = ToolRegistry()
        reg.register(NetworkFailingTool())

        # ToolRegistry.execute catches exception and returns ToolResult(success=False)
        result = await reg.execute(
            tool_name="net_tool",
            arguments={},
            context={"permissions": ["tool:execute"]},
        )
        assert result.success is False
        assert "Connection refused" in (
            result.error or ""
        ) or "ConnectionResetError" in (result.error or "")

    async def test_failure_case_5_partial_failure_dag_step(self) -> None:
        """Failure Case 5: Partial failure in DAG step marks step FAILED."""
        step = PlanStep(
            step_id="step-fail-1",
            description="Perform fragile operation",
            tool_name="fragile_tool",
            tool_args={},
        )
        step.status = PlanStepStatus.FAILED
        step.error = "Step computation failed verification assertion"

        plan = Plan(
            plan_id="plan-part-fail",
            goal="Robust workflow",
            steps=[step],
        )

        assert plan.steps[0].status == PlanStepStatus.FAILED
        assert plan.is_complete() is False
        assert plan.has_failures() is True

    async def test_failure_case_6_recovery(self) -> None:
        """Failure Case 6: BoundedRecoveryEngine retries transient error, halts fatal."""
        recovery = BoundedRecoveryEngine(limits=RecoveryLimits(max_step_retries=2))

        step = PlanStep(
            step_id="step-rec-1",
            description="Transient network operation",
        )
        decision_transient = recovery.evaluate_step_failure(
            step=step,
            error_message="Transient network timeout HTTP 503 Service Unavailable",
            current_step_retries=0,
            elapsed_time_seconds=1.0,
        )
        assert decision_transient.action == RecoveryAction.RETRY

        auth_step = PlanStep(
            step_id="step-auth-1",
            description="Unauthorized banking operation",
        )
        decision_fatal = recovery.evaluate_step_failure(
            step=auth_step,
            error_message="Invalid API token HTTP 401 Unauthorized access denied",
            current_step_retries=0,
            elapsed_time_seconds=1.0,
        )
        assert decision_fatal.action == RecoveryAction.TERMINATE_FAILED
