"""Unit tests for canonical orchestration domain contracts and state machine."""

import pytest
from pydantic import ValidationError

from app.agent.domain.contracts import (
    AgentCapability,
    ExecutionContext,
    ExecutionPlan,
    ExecutionStateStatus,
    PlanStep,
    RecoveryAction,
    RecoveryDecision,
    StepResult,
    StepStatus,
    TaskSpec,
    TerminalState,
    VerificationResult,
    VerificationVerdict,
)
from app.agent.state.models import RunState, RunStatus


class TestTaskSpecContract:
    def test_valid_task_spec(self) -> None:
        spec = TaskSpec(
            task_id="task_123",
            tenant_id="tenant_alpha",
            user_id="user_456",
            goal="Analyze quarterly financial reports",
            roles=["analyst"],
            permissions=["read:financials"],
            correlation_id="corr_999",
            metadata={"priority": "high"},
        )
        assert spec.task_id == "task_123"
        assert spec.tenant_id == "tenant_alpha"
        assert spec.goal == "Analyze quarterly financial reports"
        assert "analyst" in spec.roles
        assert spec.correlation_id == "corr_999"

    def test_task_spec_empty_goal_fails(self) -> None:
        with pytest.raises(ValidationError):
            TaskSpec(
                task_id="task_1",
                tenant_id="t1",
                user_id="u1",
                goal="",
            )

    def test_task_spec_empty_tenant_fails(self) -> None:
        with pytest.raises(ValidationError):
            TaskSpec(
                task_id="task_1",
                tenant_id="",
                user_id="u1",
                goal="Valid goal",
            )


class TestExecutionPlanContract:
    def test_plan_dependency_and_runnable_steps(self) -> None:
        step1 = PlanStep(
            step_id="step_fetch",
            description="Fetch stock price",
            objective="Retrieve market data",
            dependencies=[],
            candidate_agents=["financial_specialist"],
            required_capabilities=[AgentCapability.FINANCIAL_ANALYSIS.value],
        )
        step2 = PlanStep(
            step_id="step_synthesize",
            description="Format report",
            objective="Synthesize findings",
            dependencies=["step_fetch"],
            candidate_agents=["synthesizer"],
            required_capabilities=[AgentCapability.SYNTHESIS.value],
        )
        plan = ExecutionPlan(
            plan_id="plan_001",
            task_id="task_123",
            tenant_id="tenant_alpha",
            goal="Fetch and synthesize stock data",
            steps=[step1, step2],
        )

        assert plan.get_step("step_fetch") == step1
        assert plan.get_step("non_existent") is None
        assert not plan.is_complete()

        # Step 1 should be immediately runnable
        ready = plan.get_runnable_steps()
        assert len(ready) == 1
        assert ready[0].step_id == "step_fetch"

        # Mark step 1 completed
        plan.mark_step_status(
            "step_fetch", StepStatus.COMPLETED, observation="Price is $150"
        )
        assert step1.status == StepStatus.COMPLETED
        assert step1.observation == "Price is $150"

        # Now step 2 should be runnable
        ready2 = plan.get_runnable_steps()
        assert len(ready2) == 1
        assert ready2[0].step_id == "step_synthesize"

        # Mark step 2 completed
        plan.mark_step_status(
            "step_synthesize", StepStatus.COMPLETED, observation="Report ready"
        )
        assert plan.is_complete()

    def test_plan_independent_step_tiers(self) -> None:
        step_a = PlanStep(step_id="A", description="A", dependencies=[])
        step_b = PlanStep(step_id="B", description="B", dependencies=[])
        step_c = PlanStep(step_id="C", description="C", dependencies=["A", "B"])

        plan = ExecutionPlan(
            plan_id="plan_tiers",
            task_id="task_t",
            goal="Test parallel tiers",
            steps=[step_a, step_b, step_c],
        )

        tiers = plan.get_independent_step_groups()
        assert len(tiers) == 2
        assert {s.step_id for s in tiers[0]} == {"A", "B"}
        assert {s.step_id for s in tiers[1]} == {"C"}


class TestExecutionContextContract:
    def test_tenant_matching_assertion(self) -> None:
        ctx = ExecutionContext(
            tenant_id="tenant_secure",
            user_id="user_admin",
            roles=["admin"],
            permissions=["all"],
            correlation_id="corr_sec_1",
        )
        # Matching tenant passes
        ctx.assert_tenant_match("tenant_secure")

        # Mismatch must raise PermissionError
        with pytest.raises(PermissionError) as exc_info:
            ctx.assert_tenant_match("tenant_intruder")
        assert "Multi-tenant boundary violation" in str(exc_info.value)


class TestStepResultContract:
    def test_step_result_creation(self) -> None:
        result = StepResult(
            step_id="step_calc",
            status=StepStatus.COMPLETED,
            output="Operating margin is 22.5%",
            agent_id="financial_specialist",
            model_used="gemini-1.5-pro",
            provider_used="gemini",
            execution_time_ms=1450.0,
            tokens_consumed=180,
            cost_usd=0.00045,
        )
        assert result.step_id == "step_calc"
        assert result.status == StepStatus.COMPLETED
        assert result.agent_id == "financial_specialist"
        assert result.cost_usd == 0.00045


class TestVerificationResultContract:
    def test_verification_result_verdicts(self) -> None:
        verified = VerificationResult(
            verdict=VerificationVerdict.PASS,
            reason="All calculations and citations verified.",
            groundedness_score=0.95,
            evidence={"rag_faithfulness": 0.95},
        )
        assert verified.verdict == VerificationVerdict.PASS

        rejected = VerificationResult(
            verdict=VerificationVerdict.REJECTED,
            reason="Tenant boundary breach detected.",
            violated_invariant="cross_tenant_query",
            recommended_recovery_action=RecoveryAction.TERMINATE_REJECTED,
        )
        assert rejected.verdict == VerificationVerdict.REJECTED
        assert rejected.recommended_recovery_action == RecoveryAction.TERMINATE_REJECTED


class TestRecoveryDecisionContract:
    def test_recovery_decision_actions(self) -> None:
        rec = RecoveryDecision(
            action=RecoveryAction.SWITCH_MODEL,
            step_id="step_failed_llm",
            reason="Primary model rate limited, switching to fallback",
            alternative_model="gemini-1.5-flash",
            attempt=1,
            max_attempts=3,
        )
        assert rec.action == RecoveryAction.SWITCH_MODEL
        assert rec.alternative_model == "gemini-1.5-flash"


class TestTerminalStateContract:
    def test_terminal_state_model(self) -> None:
        terminal = TerminalState(
            status=ExecutionStateStatus.COMPLETED,
            final_output="Financial report generated successfully.",
            duration_ms=3200.0,
            tokens_consumed=450,
            cost_usd=0.0012,
        )
        assert terminal.status == ExecutionStateStatus.COMPLETED
        assert terminal.tokens_consumed == 450
        assert terminal.duration_ms == 3200.0

    def test_non_terminal_state_raises_validation_error(self) -> None:
        with pytest.raises(ValidationError):
            TerminalState(
                status=ExecutionStateStatus.EXECUTING,
                final_output="In progress",
            )


class TestRunStateTransitions:
    def test_valid_and_invalid_state_transitions(self) -> None:
        run = RunState(
            run_id="run_test",
            task_id="task_test",
            tenant_id="tenant_1",
            user_id="user_1",
            status=RunStatus.CREATED,
        )

        # Transition to PLANNING
        run.transition_to(RunStatus.PLANNING)
        assert run.status == RunStatus.PLANNING

        # Transition to READY
        run.transition_to(RunStatus.READY)
        assert run.status == RunStatus.READY

        # Transition to RUNNING
        run.transition_to(RunStatus.RUNNING)
        assert run.status == RunStatus.RUNNING

        # Transition to EXECUTING
        run.transition_to(RunStatus.EXECUTING)
        assert run.status == RunStatus.EXECUTING

        # Transition to WAITING_APPROVAL
        run.transition_to(RunStatus.WAITING_APPROVAL)
        assert run.status == RunStatus.WAITING_APPROVAL

        # Resume to RUNNING
        run.transition_to(RunStatus.RUNNING)
        assert run.status == RunStatus.RUNNING

        # Transition to VERIFYING
        run.transition_to(RunStatus.VERIFYING)
        assert run.status == RunStatus.VERIFYING

        # Replan loop: VERIFYING -> REPLANNING -> PLANNING -> READY -> RUNNING
        run.transition_to(RunStatus.REPLANNING)
        assert run.status == RunStatus.REPLANNING
        run.transition_to(RunStatus.PLANNING)
        assert run.status == RunStatus.PLANNING
        run.transition_to(RunStatus.READY)
        run.transition_to(RunStatus.RUNNING)
        run.transition_to(RunStatus.VERIFYING)

        # Progress to terminal COMPLETED
        run.transition_to(RunStatus.COMPLETED)
        assert run.status == RunStatus.COMPLETED
        assert run.completed_at is not None

        # Terminal state cannot transition to any other state
        with pytest.raises(ValueError) as exc_info:
            run.transition_to(RunStatus.RUNNING)
        assert "cannot transition from terminal state" in str(exc_info.value)
