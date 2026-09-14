"""Unit and architecture invariant tests for JakeAI Orchestration Capability (WORK-01).

Validates the core structural invariants of the consolidated orchestration platform:
1. Single authoritative Task & Run contracts with bidirectional adapter mappings.
2. Single Model Routing Authority via ModelRouter.
3. Single Tool Registry Authority via ToolRegistry.
4. Single Verification Authority via CanonicalVerifier.
5. Non-Degradable Multi-Tenant Isolation: cross-tenant access is a hard PermissionError.
6. Bounded Execution Ceilings: strict loop and timeout boundaries prevent infinite recursion.
"""

from __future__ import annotations

from typing import TYPE_CHECKING

import pytest

from app.agent.domain.contracts import (
    AgentCapability,
    ExecutionContext,
    PlanStep,
    StepStatus,
)
from app.agent.recovery.recovery import BoundedRecoveryEngine, RecoveryLimits
from app.agent.registry.agent_selector import AgentSelector
from app.agent.state.models import RunState, RunStatus
from app.agent.tools.registry import get_tool_registry
from app.agent.verification.verifier import CanonicalVerifier, get_canonical_verifier
from app.agents.verifier import verifier_node
from app.routing.router import ModelRouter, RoutingPolicy

if TYPE_CHECKING:
    from app.agents.state import AgentState


class TestArchitectureInvariants:
    def test_invariant_1_single_task_and_run_contracts(self) -> None:
        """Invariant 1: Exactly ONE authoritative TaskSpec and RunState, with lossless translation to AgentState."""
        run = RunState(
            run_id="run_inv_1",
            task_id="task_inv_1",
            tenant_id="tenant_inv",
            user_id="user_inv",
            status=RunStatus.RUNNING,
            roles=["analyst"],
            permissions=["read:all"],
            prompt="Analyze portfolio risk",
            verification_verdict="PASS",
            current_agent="financial_specialist",
        )

        # Map to LangGraph AgentState
        agent_state = run.to_agent_state()
        assert agent_state["tenant_id"] == "tenant_inv"
        assert agent_state["user_id"] == "user_inv"
        assert agent_state["conversation_id"] == "task_inv_1"
        assert agent_state["workflow_phase"] == "running"
        assert agent_state["current_agent"] == "financial_specialist"

        # Reconstruct canonical RunState from AgentState
        restored = RunState.from_agent_state(
            state=agent_state,
            task_id="task_inv_1",
            run_id="run_inv_1",
        )
        assert restored.run_id == "run_inv_1"
        assert restored.tenant_id == "tenant_inv"
        assert restored.status == RunStatus.RUNNING
        assert restored.current_agent == "financial_specialist"

    def test_invariant_2_single_model_router_authority(self) -> None:
        """Invariant 2: ModelRouter is the sole routing authority across all execution paths."""
        router = ModelRouter()
        policy = RoutingPolicy(
            requested_model="default",
            tenant_id="tenant_sec",
            workload_class="financial_reasoning",
            cost_aware_routing=True,
        )
        decision = router.route(policy)

        # Verifies intelligent model routing outcome
        assert decision.selected_model is not None
        assert decision.selected_provider is not None
        assert decision.policy_applied is not None
        assert isinstance(decision.decision_reasons, list)

    def test_invariant_3_single_tool_registry_authority(self) -> None:
        """Invariant 3: ToolRegistry is the sole registry and policy gateway for all tools."""
        registry = get_tool_registry()

        # Tools are discovered and filtered strictly via ToolRegistry
        analyst_tools = registry.discover(
            user_roles=["analyst"],
            user_permissions=["finnapigo:read"],
        )
        tool_names = [t.name for t in analyst_tools]
        assert "get_account_balance" in tool_names

        # Unauthorized user cannot discover privileged banking tools
        unprivileged_tools = registry.discover(
            user_roles=["guest"],
            user_permissions=[],
        )
        unpriv_names = [t.name for t in unprivileged_tools]
        assert "get_account_balance" not in unpriv_names
        assert "list_transactions" not in unpriv_names

    @pytest.mark.asyncio
    async def test_invariant_4_single_verification_authority(self) -> None:
        """Invariant 4: CanonicalVerifier is the sole verification authority, used directly by LangGraph."""
        verifier = get_canonical_verifier()
        assert isinstance(verifier, CanonicalVerifier)

        # Verify LangGraph verifier_node delegates directly to CanonicalVerifier
        state: AgentState = {
            "prompt": "Summarize Q3 earnings",
            "tenant_id": "tenant_a",
            "user_id": "user_a",
            "roles": [],
            "permissions": [],
            "conversation_id": "conv_v4",
            "correlation_id": "corr_v4",
            "obo_token": "",
            "messages": [],
            "tool_calls": [
                {"tool_name": "db", "tenant_id": "tenant_b"}
            ],  # Cross-tenant breach!
            "financial_analysis": {},
            "revision_count": 0,
            "mascot_state": "thinking",
            "citations": [],
            "execution_plan": {},
        }
        res_state = await verifier_node(state)
        assert res_state["verification_verdict"] == "REJECTED"
        assert res_state["workflow_phase"] == "verification_failed"

    def test_invariant_5_non_degradable_multi_tenant_isolation(self) -> None:
        """Invariant 5: Multi-tenant boundary mismatch is a non-degradable hard PermissionError."""
        context = ExecutionContext(
            tenant_id="tenant_primary",
            user_id="user_test",
            roles=["member"],
            permissions=["read"],
        )

        # Strict assertion raises PermissionError
        with pytest.raises(PermissionError) as exc_info:
            context.assert_tenant_match("tenant_foreign")
        assert "Multi-tenant boundary violation" in str(exc_info.value)

        # AgentSelector boundary enforcement raises PermissionError
        selector = AgentSelector()
        step = PlanStep(
            step_id="step_t",
            description="Tenant action",
            required_capabilities=[AgentCapability.GENERAL_REASONING.value],
        )
        with pytest.raises(PermissionError) as exc_info:
            selector.select_agent_for_step(
                step=step,
                context=context,
                expected_tenant_id="tenant_foreign",
            )
        assert "Tenant boundary violation" in str(exc_info.value)

    def test_invariant_6_bounded_execution_ceilings(self) -> None:
        """Invariant 6: Strict iteration and retry bounds prevent unbounded execution or infinite loops."""
        engine = BoundedRecoveryEngine(
            limits=RecoveryLimits(
                max_step_retries=2,
                max_replan_cycles=1,
                max_total_recovery_seconds=10.0,
            )
        )
        step = PlanStep(
            step_id="step_bound",
            description="Failing step",
            status=StepStatus.FAILED,
        )

        # Retry 0: allowed
        dec0 = engine.evaluate_step_failure(
            step=step,
            error_message="Network glitch",
            current_step_retries=0,
            elapsed_time_seconds=1.0,
        )
        assert dec0.action.value in ("retry", "switch_model")

        # Retry 2 (step limit): switch agent or terminate
        dec_exhausted = engine.evaluate_step_failure(
            step=step,
            error_message="Persistent failure",
            current_step_retries=2,
            elapsed_time_seconds=2.0,
        )
        assert dec_exhausted.action.value in ("switch_agent", "terminate_failed")

        # Total execution time exceeded: hard termination required
        dec_timeout = engine.evaluate_step_failure(
            step=step,
            error_message="Timeout failure",
            current_step_retries=2,
            elapsed_time_seconds=15.0,
        )
        assert dec_timeout.action.value == "terminate_failed"
        assert "exceeded limit" in dec_timeout.reason
