"""Canonical Dynamic Agent Selector matching tasks and steps to optimal agents."""

from __future__ import annotations

import logging
import re
from typing import TYPE_CHECKING, Any

from app.agent.domain.contracts import (
    AgentCapability,
    AgentSelection,
    ExecutionContext,
    PlanStep,
    TaskSpec,
)
from app.agent.registry.agent_registry import AgentMetadata, get_agent_registry

if TYPE_CHECKING:
    from app.agent.registry.agent_registry import AgentRegistry

logger = logging.getLogger(__name__)


# Heuristic patterns for degraded mode fallback
_FINANCIAL_PATTERNS = re.compile(
    r"(?i)\b(?:ebitda|margin|revenue|expense|profit|operating income|financial|ratio|tax|ledger|cost)\b|\$\d+"
)
_BANKING_PATTERNS = re.compile(
    r"(?i)\b(?:finnapi|account balance|bank|transaction|transfer|invoice|limit|account_id)\b"
)
_RETRIEVAL_PATTERNS = re.compile(
    r"(?i)\b(?:search|retrieve|lookup|query docs|find document|rag|cite)\b"
)
_VERIFICATION_PATTERNS = re.compile(
    r"(?i)\b(?:verify|audit|check consistency|critique|groundedness|validate math)\b"
)
_SYNTHESIS_PATTERNS = re.compile(
    r"(?i)\b(?:summarize|synthesize|report|markdown table|compile summary)\b"
)


class AgentSelector:
    """Selects the most suitable agent for a task or plan step based on machine-readable metadata."""

    def __init__(
        self,
        registry: AgentRegistry | None = None,
        agent_registry: AgentRegistry | None = None,
        tool_registry: Any = None,
    ) -> None:
        self.registry = registry or agent_registry or get_agent_registry()
        self.tool_registry = tool_registry

    def select_agent_for_step(
        self,
        step: PlanStep,
        context: ExecutionContext,
        expected_tenant_id: str | None = None,
    ) -> AgentSelection:
        """Convenience method to select an agent directly for an individual PlanStep."""
        if expected_tenant_id is not None and context.tenant_id != expected_tenant_id:
            raise PermissionError(
                f"Tenant boundary violation: context tenant '{context.tenant_id}' "
                f"does not match expected tenant '{expected_tenant_id}'."
            )
        task_spec = TaskSpec(
            task_id="step_task",
            tenant_id=context.tenant_id,
            user_id=context.user_id,
            goal=step.description,
            roles=context.roles,
            permissions=context.permissions,
        )
        return self.select_agent(task_spec=task_spec, plan_step=step, context=context)

    def select_agent(
        self,
        task_spec: TaskSpec,
        plan_step: PlanStep | None = None,
        context: ExecutionContext | None = None,
    ) -> AgentSelection:
        """Select an agent using metadata matching, policy filtering, and degraded fallback."""
        # 1. Enforce strict multi-tenant boundary check if context provided
        if context is not None:
            context.assert_tenant_match(task_spec.tenant_id)

        # 2. Extract step requirements or fall back to task-level goal
        step_caps = plan_step.required_capabilities if plan_step else []
        step_tools = plan_step.required_tools if plan_step else []
        candidate_agents = plan_step.candidate_agents if plan_step else []
        workload = (
            plan_step.model_requirements.get("workload_class") if plan_step else None
        )

        # 3. Retrieve eligible candidates from registry
        eligible = self.registry.find_eligible(
            required_capabilities=step_caps,
            required_tools=step_tools,
            workload_class=workload,
        )

        # 4. If step specified candidate_agents, restrict to those
        if candidate_agents:
            candidate_set = set(candidate_agents)
            eligible = [a for a in eligible if a.agent_id in candidate_set]

        # 5. Score and rank candidates
        ranked_candidates: list[tuple[float, AgentMetadata, list[str]]] = []
        for agent in eligible:
            score = 1.0
            matched_caps: list[str] = []

            # Capability match score
            if step_caps:
                for cap in step_caps:
                    if cap in agent.capabilities:
                        score += 2.0
                        matched_caps.append(cap)
            else:
                # Infer capability from goal or step description
                text_to_eval = (
                    f"{task_spec.goal} {plan_step.description if plan_step else ''}"
                )
                if (
                    _FINANCIAL_PATTERNS.search(text_to_eval)
                    and AgentCapability.FINANCIAL_ANALYSIS.value in agent.capabilities
                ):
                    score += 3.0
                    matched_caps.append(AgentCapability.FINANCIAL_ANALYSIS.value)
                if (
                    _BANKING_PATTERNS.search(text_to_eval)
                    and AgentCapability.BANKING_API.value in agent.capabilities
                ):
                    score += 3.0
                    matched_caps.append(AgentCapability.BANKING_API.value)
                if (
                    _RETRIEVAL_PATTERNS.search(text_to_eval)
                    and AgentCapability.RAG_RETRIEVAL.value in agent.capabilities
                ):
                    score += 2.5
                    matched_caps.append(AgentCapability.RAG_RETRIEVAL.value)
                if (
                    _VERIFICATION_PATTERNS.search(text_to_eval)
                    and AgentCapability.VERIFICATION.value in agent.capabilities
                ):
                    score += 3.0
                    matched_caps.append(AgentCapability.VERIFICATION.value)
                if (
                    _SYNTHESIS_PATTERNS.search(text_to_eval)
                    and AgentCapability.SYNTHESIS.value in agent.capabilities
                ):
                    score += 2.5
                    matched_caps.append(AgentCapability.SYNTHESIS.value)

            # Tool match score
            for t in step_tools:
                if t in agent.supported_tools:
                    score += 1.5

            ranked_candidates.append((score, agent, matched_caps))

        if ranked_candidates:
            # Sort descending by score
            ranked_candidates.sort(key=lambda x: x[0], reverse=True)
            top_score, best_agent, matched = ranked_candidates[0]
            confidence = min(0.99, max(0.60, top_score / 5.0))
            return AgentSelection(
                agent_id=best_agent.agent_id,
                reasoning=(
                    f"Selected '{best_agent.name}' (score: {top_score:.1f}) matching "
                    f"capabilities: {matched or ['general']}."
                ),
                confidence=confidence,
                matched_capabilities=matched,
                risk_level=best_agent.risk_level,
                fallback_used=False,
            )

        # 6. Explicit Degraded Mode Fallback
        fallback_agent_id, fallback_reason = self._degraded_heuristic_fallback(
            task_spec=task_spec,
            plan_step=plan_step,
        )
        fallback_meta = self.registry.get(fallback_agent_id)
        return AgentSelection(
            agent_id=fallback_agent_id,
            reasoning=f"DEGRADED MODE: {fallback_reason}",
            confidence=0.50,
            matched_capabilities=[],
            risk_level=fallback_meta.risk_level if fallback_meta else "safe",
            fallback_used=True,
        )

    def _degraded_heuristic_fallback(
        self,
        task_spec: TaskSpec,
        plan_step: PlanStep | None,
    ) -> tuple[str, str]:
        """Explicit deterministic fallback rule when capability matching yields zero candidates."""
        content = f"{task_spec.goal} {plan_step.description if plan_step else ''}"

        if _BANKING_PATTERNS.search(content):
            return "finnapigo_specialist", "Matched banking/FinnApiGo keywords"
        if _FINANCIAL_PATTERNS.search(content):
            return "financial_specialist", "Matched quantitative financial keywords"
        if _RETRIEVAL_PATTERNS.search(content):
            return "retrieval_specialist", "Matched search/retrieval keywords"
        if _VERIFICATION_PATTERNS.search(content):
            return "verifier", "Matched verification keywords"
        if _SYNTHESIS_PATTERNS.search(content):
            return "synthesizer", "Matched synthesis keywords"

        return "general_agent", "Defaulted to general agent"


_default_selector: AgentSelector | None = None


def get_agent_selector() -> AgentSelector:
    """Singleton accessor for canonical AgentSelector."""
    global _default_selector
    if _default_selector is None:
        _default_selector = AgentSelector()
    return _default_selector
