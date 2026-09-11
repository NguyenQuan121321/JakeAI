"""Unit tests for canonical BoundedPlanner, DAG generation, dependency resolution, and replanning."""

import pytest

from app.agent.domain.contracts import StepStatus
from app.agent.planning.planner import BoundedPlanner
from app.agent.tools.registry import ToolMetadata


class TestOrchestrationPlanner:
    @pytest.fixture
    def mock_tool_registry(self) -> list[ToolMetadata]:
        return [
            ToolMetadata(
                name="finnapigo_balance_inquiry",
                description="Inquire account balance",
                input_schema={},
                required_permissions=["banking:read"],
            ),
            ToolMetadata(
                name="finnapigo_internal_transfer",
                description="Transfer funds internally",
                input_schema={},
                required_permissions=["banking:write"],
            ),
            ToolMetadata(
                name="rag_financial_search",
                description="Search financial disclosures and 10-K filings",
                input_schema={},
                required_permissions=["rag:search"],
            ),
            ToolMetadata(
                name="fetch_market_quote",
                description="Fetch real-time stock quotes",
                input_schema={},
                required_permissions=["market:read"],
            ),
        ]

    def test_single_step_direct_question(self, mock_tool_registry: list[ToolMetadata]) -> None:
        planner = BoundedPlanner()
        plan = planner.create_initial_plan(
            goal="What is a price-to-earnings ratio?",
            available_tools=mock_tool_registry,
            tenant_id="tenant_fin",
        )

        assert len(plan.steps) >= 1
        assert plan.steps[0].dependencies == []
        assert plan.steps[0].selected_model is not None
        assert plan.steps[0].selected_provider is not None

    def test_banking_transfer_dag_dependencies(self, mock_tool_registry: list[ToolMetadata]) -> None:
        planner = BoundedPlanner()
        plan = planner.create_initial_plan(
            goal="Transfer $500 to savings account after checking balance",
            available_tools=mock_tool_registry,
            tenant_id="tenant_bank",
        )

        assert len(plan.steps) >= 2
        step1 = plan.steps[0]
        step2 = plan.steps[1]

        # Verification/transfer step must depend on balance check
        assert step1.step_id in step2.dependencies
        assert "get_account_balance" in step1.required_tools
        assert step2.step_id == "step_compute_financials"

    def test_parallel_multi_source_dag(self, mock_tool_registry: list[ToolMetadata]) -> None:
        planner = BoundedPlanner()
        plan = planner.create_initial_plan(
            goal="Compare Apple stock price from market feed and internal bank balance",
            available_tools=mock_tool_registry,
            tenant_id="tenant_multi",
        )

        # Should generate 2 independent source fetching steps, a merge step, and a synthesis step
        assert len(plan.steps) >= 3
        merge_step = next(s for s in plan.steps if s.step_id == "step_merge_analyze")
        assert len(merge_step.dependencies) == 2
        assert "step_source_a" in merge_step.dependencies
        assert "step_source_b" in merge_step.dependencies

        # Verify topological independent groups (parallel tiers)
        tiers = plan.get_independent_step_groups()
        assert len(tiers) >= 2
        # Tier 0 has independent data fetching steps that run concurrently
        assert len(tiers[0]) == 2

    def test_replanning_after_verifier_critique(self, mock_tool_registry: list[ToolMetadata]) -> None:
        planner = BoundedPlanner()
        initial_plan = planner.create_initial_plan(
            goal="Analyze quarterly margin",
            available_tools=mock_tool_registry,
            tenant_id="tenant_analysis",
        )

        # Mark step 1 as failed
        step_1_id = initial_plan.steps[0].step_id
        initial_plan.steps[0].status = StepStatus.FAILED

        # Replan
        replanned = planner.replan(
            existing_plan=initial_plan,
            verifier_critique="Calculation failed due to missing denominator. Query full balance sheet first.",
            failed_step_id=step_1_id,
            tenant_id="tenant_analysis",
        )

        assert replanned.plan_id != initial_plan.plan_id
        assert len(replanned.steps) >= len(initial_plan.steps)
        # Verify critique is recorded in analysis
        assert "Calculation failed" in replanned.analysis
        # Revised step has retries_exhausted incremented
        assert any(s.retries_exhausted > 0 for s in replanned.steps)
