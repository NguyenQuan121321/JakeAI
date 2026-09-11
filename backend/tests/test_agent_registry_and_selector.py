"""Unit tests for AgentRegistry and AgentSelector."""

import pytest

from app.agent.domain.contracts import (
    AgentCapability,
    ExecutionContext,
    PlanStep,
)
from app.agent.registry.agent_registry import (
    AgentRegistry,
    get_agent_registry,
)
from app.agent.registry.agent_selector import AgentSelector
from app.agent.tools.registry import ToolRegistry, get_tool_registry


class TestAgentRegistryAndSelector:
    @pytest.fixture
    def registry(self) -> AgentRegistry:
        return get_agent_registry()

    @pytest.fixture
    def tool_registry(self) -> ToolRegistry:
        return get_tool_registry()

    def test_default_built_in_agents(self, registry: AgentRegistry) -> None:
        expected_agents = [
            "supervisor",
            "financial_specialist",
            "finnapigo_specialist",
            "retrieval_specialist",
            "verifier",
            "synthesizer",
            "general_agent",
        ]
        for agent_id in expected_agents:
            agent = registry.get(agent_id)
            assert agent is not None
            assert agent.agent_id == agent_id
            assert len(agent.capabilities) > 0

    def test_find_by_capability(self, registry: AgentRegistry) -> None:
        financial_agents = registry.find_by_capability(AgentCapability.FINANCIAL_ANALYSIS)
        assert len(financial_agents) >= 1
        assert any(a.agent_id == "financial_specialist" for a in financial_agents)

        banking_agents = registry.find_by_capability(AgentCapability.BANKING_API)
        assert len(banking_agents) >= 1
        assert any(a.agent_id == "finnapigo_specialist" for a in banking_agents)

    def test_selector_matches_financial_step(
        self, registry: AgentRegistry, tool_registry: ToolRegistry
    ) -> None:
        selector = AgentSelector(agent_registry=registry, tool_registry=tool_registry)
        step = PlanStep(
            step_id="step_fin_1",
            description="Calculate EBITDA and operating ratio",
            required_capabilities=[AgentCapability.FINANCIAL_ANALYSIS.value],
            candidate_agents=["financial_specialist"],
        )
        context = ExecutionContext(
            tenant_id="tenant_fin",
            user_id="user_fin",
            roles=["analyst"],
            permissions=["banking:read"],
        )

        selection = selector.select_agent_for_step(step=step, context=context)
        assert selection.agent_id == "financial_specialist"
        assert not selection.fallback_used
        assert AgentCapability.FINANCIAL_ANALYSIS.value in selection.matched_capabilities

    def test_selector_falls_back_to_general_agent_for_unknown_capability(
        self, registry: AgentRegistry, tool_registry: ToolRegistry
    ) -> None:
        selector = AgentSelector(agent_registry=registry, tool_registry=tool_registry)
        step = PlanStep(
            step_id="step_unknown",
            description="Perform specialized exotic task",
            required_capabilities=["exotic_quantum_calculation"],
            candidate_agents=["non_existent_specialist"],
        )
        context = ExecutionContext(
            tenant_id="tenant_gen",
            user_id="user_gen",
        )

        selection = selector.select_agent_for_step(step=step, context=context)
        assert selection.agent_id == "general_agent"
        assert selection.fallback_used is True
        assert "degraded mode" in selection.reasoning.lower()

    def test_selector_enforces_tenant_boundary(
        self, registry: AgentRegistry, tool_registry: ToolRegistry
    ) -> None:
        selector = AgentSelector(agent_registry=registry, tool_registry=tool_registry)
        step = PlanStep(
            step_id="step_tenant",
            description="Access tenant vault",
            required_capabilities=[AgentCapability.GENERAL_REASONING.value],
        )
        context = ExecutionContext(
            tenant_id="tenant_alpha",
            user_id="user_alpha",
        )

        # Calling with mismatched tenant must raise PermissionError
        with pytest.raises(PermissionError) as exc_info:
            selector.select_agent_for_step(
                step=step,
                context=context,
                expected_tenant_id="tenant_beta",
            )
        assert "Tenant boundary violation" in str(exc_info.value)
