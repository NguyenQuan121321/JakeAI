"""Canonical Agent Registry managing machine-readable agent metadata and capabilities."""

from __future__ import annotations

import logging
from typing import Any

from pydantic import BaseModel, Field

from app.agent.domain.contracts import AgentCapability

logger = logging.getLogger(__name__)


class AgentMetadata(BaseModel):
    """Machine-readable specification defining an agent's operational capabilities."""

    agent_id: str = Field(..., description="Unique agent identifier")
    name: str = Field(..., description="Human-readable agent name")
    description: str = Field(default="")
    capabilities: list[str] = Field(
        default_factory=list,
        description="Machine-readable capabilities supported by this agent",
    )
    supported_tools: list[str] = Field(
        default_factory=list,
        description="List of tool names this agent is authorized and equipped to operate",
    )
    supported_workloads: list[str] = Field(
        default_factory=list,
        description="Workload domains (e.g. financial_reasoning, reasoning, rag, simple_chat, coding)",
    )
    required_model_capabilities: list[str] = Field(
        default_factory=list,
        description="Underlying model capabilities required (e.g. supports_tools, supports_reasoning)",
    )
    risk_level: str = Field(
        default="safe",
        description="Operational risk classification: safe, normal, sensitive, dangerous",
    )
    availability: bool = Field(
        default=True,
        description="Whether this agent is currently active and healthy",
    )
    version: str = Field(default="1.0.0")
    system_prompt: str | None = None
    metadata: dict[str, Any] = Field(default_factory=dict)


class AgentRegistry:
    """Canonical registry holding all registered JakeAI agents."""

    def __init__(self) -> None:
        self._agents: dict[str, AgentMetadata] = {}

    def register(self, metadata: AgentMetadata) -> None:
        """Register an agent specification."""
        self._agents[metadata.agent_id] = metadata
        logger.debug("Registered agent in AgentRegistry: %s", metadata.agent_id)

    def unregister(self, agent_id: str) -> None:
        """Unregister an agent by ID."""
        self._agents.pop(agent_id, None)

    def get(self, agent_id: str) -> AgentMetadata | None:
        """Look up an agent by ID."""
        return self._agents.get(agent_id)

    def list_agents(self) -> list[AgentMetadata]:
        """Return all registered agents."""
        return list(self._agents.values())

    def find_by_capability(self, capability: AgentCapability | str) -> list[AgentMetadata]:
        """Convenience query for agents matching a specific capability."""
        cap_val = capability.value if hasattr(capability, "value") else str(capability)
        return self.find_eligible(required_capabilities=[cap_val])

    def find_eligible(
        self,
        required_capabilities: list[str] | None = None,
        required_tools: list[str] | None = None,
        workload_class: str | None = None,
    ) -> list[AgentMetadata]:
        """Filter agents matching capability, tool, and workload requirements."""
        req_caps = set(required_capabilities or [])
        req_tools = set(required_tools or [])
        eligible: list[AgentMetadata] = []

        for agent in self._agents.values():
            if not agent.availability:
                continue

            # Check capabilities
            agent_caps = set(agent.capabilities)
            if req_caps and not req_caps.issubset(agent_caps) and not (req_caps & agent_caps):
                continue

            # Check tools: if step requires specific tools, agent must support them
            agent_tools = set(agent.supported_tools)
            if req_tools and not req_tools.issubset(agent_tools):
                continue

            # Check workload compatibility
            if (
                workload_class
                and agent.supported_workloads
                and workload_class not in agent.supported_workloads
                and "general" not in agent.supported_workloads
            ):
                continue

            eligible.append(agent)

        return eligible


_default_agent_registry: AgentRegistry | None = None


def get_agent_registry() -> AgentRegistry:
    """Singleton accessor for the canonical AgentRegistry with built-in agents."""
    global _default_agent_registry
    if _default_agent_registry is None:
        reg = AgentRegistry()

        # 1. Supervisor Agent
        reg.register(
            AgentMetadata(
                agent_id="supervisor",
                name="Supervisor Agent",
                description="Orchestrates high-level workflow decomposition, dispatching, and task supervision",
                capabilities=[
                    AgentCapability.SUPERVISION.value,
                    AgentCapability.PLANNING.value,
                ],
                supported_workloads=["reasoning", "general"],
                required_model_capabilities=["supports_reasoning"],
                risk_level="safe",
            )
        )

        # 2. Financial Specialist
        reg.register(
            AgentMetadata(
                agent_id="financial_specialist",
                name="Financial Specialist Agent",
                description="Performs quantitative financial analysis, EBITDA, margins, and variance computation",
                capabilities=[
                    AgentCapability.FINANCIAL_ANALYSIS.value,
                    AgentCapability.GENERAL_REASONING.value,
                ],
                supported_tools=["calculator"],
                supported_workloads=["financial_reasoning", "reasoning"],
                required_model_capabilities=["supports_reasoning"],
                risk_level="safe",
            )
        )

        # 3. FinnApiGo Specialist (Banking Tool Executor)
        reg.register(
            AgentMetadata(
                agent_id="finnapigo_specialist",
                name="FinnApiGo Banking Specialist",
                description="Interacts with upstream FinnApiGo banking systems for balances, limits, and transactions",
                capabilities=[
                    AgentCapability.BANKING_API.value,
                ],
                supported_tools=[
                    "get_account_balance",
                    "list_transactions",
                    "get_tenant_limits",
                ],
                supported_workloads=["structured_json", "general"],
                required_model_capabilities=["supports_tools"],
                risk_level="normal",
            )
        )

        # 4. Retrieval Specialist (RAG)
        reg.register(
            AgentMetadata(
                agent_id="retrieval_specialist",
                name="RAG Retrieval Specialist",
                description="Queries hybrid retrieval systems, vector stores, and contextual documents",
                capabilities=[
                    AgentCapability.RAG_RETRIEVAL.value,
                ],
                supported_tools=["search_symbols", "read_file"],
                supported_workloads=["rag", "long_context"],
                required_model_capabilities=["supports_prompt_cache"],
                risk_level="safe",
            )
        )

        # 5. Verifier Agent
        reg.register(
            AgentMetadata(
                agent_id="verifier",
                name="Verification and Safety Agent",
                description="Evaluates mathematical invariants, multi-tenant boundaries, and RAG grounding",
                capabilities=[
                    AgentCapability.VERIFICATION.value,
                ],
                supported_tools=["calculator"],
                supported_workloads=["reasoning", "rag"],
                required_model_capabilities=["supports_reasoning"],
                risk_level="safe",
            )
        )

        # 6. Synthesizer Agent
        reg.register(
            AgentMetadata(
                agent_id="synthesizer",
                name="Synthesis and Reporting Agent",
                description="Synthesizes structured multi-agent outputs, executive tables, and citations",
                capabilities=[
                    AgentCapability.SYNTHESIS.value,
                ],
                supported_tools=[],
                supported_workloads=["general", "simple_chat", "long_context"],
                required_model_capabilities=[],
                risk_level="safe",
            )
        )

        # 7. General ReAct Agent
        reg.register(
            AgentMetadata(
                agent_id="general_agent",
                name="General ReAct Agent",
                description="Autonomous problem solver for general queries, file reading, and calculations",
                capabilities=[
                    AgentCapability.GENERAL_REASONING.value,
                    AgentCapability.CODE_EXECUTION.value,
                ],
                supported_tools=[
                    "read_file",
                    "search_symbols",
                    "calculator",
                    "system_time",
                ],
                supported_workloads=["simple_chat", "general", "coding"],
                required_model_capabilities=[],
                risk_level="normal",
            )
        )

        _default_agent_registry = reg

    return _default_agent_registry
