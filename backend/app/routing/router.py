"""Observable Policy-Driven Intelligent Model Router (COST-10).

Provides:
1. RoutingPolicy: Explicit multi-objective routing criteria (requested model, provider, capabilities,
   context tokens, cost budget, workload class, and multi-objective weights).
2. RoutingDecision: Verifiable, observable telemetry object recording the selected provider,
   model, fallback chain, step-by-step decision reasons, and estimated cost savings.
3. ModelRouter: Deterministic multi-objective routing engine with:
   - Hard candidate pre-filtering (context limits, capability flags, provider policy, cost budget).
   - Quality floor guardrail (forbids choosing inferior models solely for low cost).
   - Multi-objective soft scoring:
     Score = w_quality * Q + w_capability * C + w_latency * L - w_cost * Cost_norm
   - Non-loopback cross-provider fallback chain construction.
"""

from __future__ import annotations

import logging
from typing import Any

from pydantic import BaseModel, Field

from app.providers.base import ModelCapabilities, ModelCapabilityCatalog
from app.providers.registry import get_provider_registry

logger = logging.getLogger(__name__)


# Benchmark Quality Index (0.0 to 1.0)
MODEL_QUALITY_MAP: dict[str, float] = {
    "o1": 1.0,
    "claude-3-5-sonnet": 0.96,
    "o3-mini": 0.95,
    "gpt-4o": 0.94,
    "claude-3-opus": 0.93,
    "deepseek-reasoner": 0.93,
    "gemini-1.5-pro": 0.92,
    "gemini-2.0-flash": 0.88,
    "deepseek-chat": 0.85,
    "llama-3.3-70b-versatile": 0.84,
    "gpt-4o-mini": 0.78,
    "gemini-1.5-flash": 0.77,
    "claude-3-haiku": 0.75,
    "local-model": 0.72,
    "llama-3.1-8b-instant": 0.65,
    "openrouter/auto": 0.80,
}

# Latency Performance Index (0.0 to 1.0, where 1.0 is fastest)
MODEL_LATENCY_SCORE: dict[str, float] = {
    "llama-3.1-8b-instant": 0.98,
    "gemini-1.5-flash": 0.95,
    "gemini-2.0-flash": 0.95,
    "gpt-4o-mini": 0.92,
    "claude-3-haiku": 0.90,
    "local-model": 0.85,
    "deepseek-chat": 0.80,
    "llama-3.3-70b-versatile": 0.78,
    "gpt-4o": 0.75,
    "claude-3-5-sonnet": 0.72,
    "gemini-1.5-pro": 0.70,
    "o3-mini": 0.55,
    "deepseek-reasoner": 0.50,
    "claude-3-opus": 0.35,
    "o1": 0.30,
    "openrouter/auto": 0.70,
}


class RoutingPolicy(BaseModel):
    """Input policy criteria guiding the provider routing decision."""

    requested_model: str = Field(
        ..., description="User or application requested model name"
    )
    preferred_provider: str | None = Field(
        default=None, description="Explicit preferred provider"
    )
    required_capabilities: list[str] = Field(
        default_factory=list,
        description="Capabilities required: supports_tools, supports_prompt_cache, supports_reasoning, supports_json",
    )
    max_input_cost_per_million: float | None = Field(
        default=None, description="Maximum allowed input cost in USD per 1M tokens"
    )
    tenant_id: str = Field(default="default", description="Tenant context")
    workload_class: str | None = Field(
        default=None,
        description="Class of workload: simple_chat, coding, financial_reasoning, reasoning, rag, structured_json",
    )
    allow_fallback: bool = Field(
        default=True, description="Whether to compute a fallback chain"
    )
    allowed_providers: list[str] | None = Field(
        default=None, description="Whitelist of provider names"
    )
    disallowed_providers: list[str] = Field(
        default_factory=list, description="Blacklist of provider names"
    )
    cost_aware_routing: bool = Field(
        default=False,
        description="Enable minimum cost routing subject to quality constraints",
    )
    force_model: bool = Field(
        default=False,
        description="Bypass cost optimization down-tiering if requested model is compatible",
    )
    context_tokens: int = Field(
        default=0,
        description="Estimated token count required by the prompt and history",
    )
    quality_requirement: float | None = Field(
        default=None,
        description="Explicit minimum quality index required (0.0 to 1.0)",
    )
    quality_weight: float = Field(
        default=0.40, description="Weight of model quality in soft score"
    )
    capability_weight: float = Field(
        default=0.25, description="Weight of capability match in soft score"
    )
    latency_weight: float = Field(
        default=0.15, description="Weight of latency performance in soft score"
    )
    cost_weight: float = Field(
        default=0.20, description="Weight of cost avoidance in soft score"
    )
    correlation_id: str | None = Field(
        default=None, description="Request correlation identifier (TASK OPS-04)"
    )


class RoutingDecision(BaseModel):
    """Observable outcome of a routing evaluation."""

    selected_provider: str
    selected_model: str
    fallback_chain: list[tuple[str, str]] = Field(
        default_factory=list,
        description="Ordered list of (provider, model) fallback candidates",
    )
    policy_applied: str = "intelligent_multi_objective_policy"
    decision_reasons: list[str] = Field(default_factory=list)
    estimated_input_cost: float = 0.0
    estimated_output_cost: float = 0.0
    cost_savings_usd_per_million: float = 0.0
    is_observable: bool = True
    correlation_id: str | None = Field(
        default=None, description="Request correlation identifier (TASK OPS-04)"
    )

    def to_dict(self) -> dict[str, Any]:
        """Convert decision to telemetry dictionary."""
        return {
            "selected_provider": self.selected_provider,
            "selected_model": self.selected_model,
            "fallback_chain": self.fallback_chain,
            "policy_applied": self.policy_applied,
            "decision_reasons": self.decision_reasons,
            "estimated_input_cost": self.estimated_input_cost,
            "estimated_output_cost": self.estimated_output_cost,
            "cost_savings_usd_per_million": self.cost_savings_usd_per_million,
            "correlation_id": self.correlation_id,
        }


class ModelRouter:
    """Intelligent multi-objective model and provider routing engine."""

    def __init__(self) -> None:
        self.registry = get_provider_registry()

    def _compute_candidate_score(
        self,
        candidate: ModelCapabilities,
        policy: RoutingPolicy,
    ) -> float:
        """Compute multi-objective score for a candidate model.

        Score = w_quality * Q + w_capability * C + w_latency * L - w_cost * Cost_norm
        """
        q = MODEL_QUALITY_MAP.get(candidate.model, 0.75)

        caps = [
            candidate.supports_streaming,
            candidate.supports_tools,
            candidate.supports_json,
            candidate.supports_prompt_cache,
            candidate.supports_reasoning,
        ]
        c = sum(1.0 for cap in caps if cap) / len(caps)

        l_score = MODEL_LATENCY_SCORE.get(candidate.model, 0.70)
        cost_norm = min(1.0, candidate.input_pricing / 15.0)

        w_q = policy.quality_weight
        w_c = policy.capability_weight
        w_l = policy.latency_weight
        w_cost = policy.cost_weight

        if policy.cost_aware_routing or policy.workload_class == "simple_chat":
            w_cost = 0.40
            w_q = 0.30
            w_c = 0.15
            w_l = 0.15

        return (w_q * q) + (w_c * c) + (w_l * l_score) - (w_cost * cost_norm)

    def route(self, policy: RoutingPolicy) -> RoutingDecision:
        """Evaluate routing policy and return fully observable RoutingDecision."""
        reasons: list[str] = []
        model = policy.requested_model.strip()
        reasons.append(
            f"Received request for model '{model}' with workload '{policy.workload_class or 'standard'}'"
        )

        # 1. Resolve default/preferred provider
        provider_name = (
            policy.preferred_provider
            or self.registry.resolve_provider_name_for_model(model)
        )
        reasons.append(
            f"Initial provider resolution mapped '{model}' -> '{provider_name}'"
        )

        # Check provider constraints (allowed/disallowed)
        if policy.allowed_providers and provider_name not in policy.allowed_providers:
            reasons.append(
                f"Provider '{provider_name}' not in allowed list {policy.allowed_providers}; falling back to first allowed"
            )
            provider_name = policy.allowed_providers[0]

        if provider_name in policy.disallowed_providers:
            reasons.append(
                f"Provider '{provider_name}' is disallowed; switching to alternative"
            )
            for alt in ("openai", "gemini", "anthropic", "groq"):
                if alt not in policy.disallowed_providers:
                    provider_name = alt
                    break

        all_catalog_models = ModelCapabilityCatalog.list_all()
        requested_cap = ModelCapabilityCatalog.get(model, provider=provider_name)
        if all(c.model != requested_cap.model for c in all_catalog_models):
            all_catalog_models.append(requested_cap)

        # Determine effective quality requirement
        min_quality = policy.quality_requirement
        if min_quality is None:
            if policy.workload_class in ("coding", "coding_context"):
                min_quality = 0.85
            elif policy.workload_class in ("reasoning", "financial_reasoning"):
                min_quality = 0.90
            elif policy.workload_class == "simple_chat":
                min_quality = 0.40
            else:
                min_quality = 0.60

        # 2. Hard Candidate Pre-filtering
        compatible_candidates: list[tuple[ModelCapabilities, float]] = []

        for candidate in all_catalog_models:
            # Policy allowed / disallowed providers
            if (
                policy.allowed_providers
                and candidate.provider not in policy.allowed_providers
            ):
                continue
            if candidate.provider in policy.disallowed_providers:
                continue

            # Context window limit
            if (
                policy.context_tokens > 0
                and candidate.context_window < policy.context_tokens
            ):
                reasons.append(
                    f"Candidate '{candidate.model}' rejected: context window {candidate.context_window} < {policy.context_tokens}"
                )
                continue

            # Required capability flags
            lacks_cap = False
            for req_cap in policy.required_capabilities:
                if not getattr(candidate, req_cap, False):
                    lacks_cap = True
                    break
            if lacks_cap:
                continue

            # Cost budget filter
            if (
                policy.max_input_cost_per_million is not None
                and candidate.input_pricing > policy.max_input_cost_per_million
            ):
                continue

            # Quality Floor Guardrail: never choose an inferior model solely for cost
            if candidate.model != model:
                candidate_q = MODEL_QUALITY_MAP.get(candidate.model, 0.75)
                if candidate_q < min_quality:
                    continue

            # Local model provider check (W-COST-06)
            if candidate.provider == "local":
                from app.core.config import get_settings

                settings = get_settings()
                if not getattr(settings, "LOCAL_MODEL_ENABLED", True):
                    continue
                local_prov = self.registry.get("local")
                if (
                    local_prov
                    and hasattr(local_prov, "_is_healthy")
                    and not local_prov._is_healthy
                ):
                    continue

            score = self._compute_candidate_score(candidate, policy)
            compatible_candidates.append((candidate, score))

        # Sort compatible candidates descending by multi-objective score
        compatible_candidates.sort(key=lambda x: x[1], reverse=True)

        selected_cap: ModelCapabilities
        selected_model: str
        selected_provider: str

        if not compatible_candidates:
            # Fallback to requested model or emergency base capability
            reasons.append(
                "Warning: Strict criteria eliminated all candidates; falling back to requested model."
            )
            selected_cap = requested_cap
            selected_model = model
            selected_provider = provider_name
        else:
            # 3. Model Selection
            # Case A: Budget exceeded on requested model
            if (
                policy.max_input_cost_per_million is not None
                and requested_cap.input_pricing > policy.max_input_cost_per_million
            ):
                reasons.append(
                    f"Model '{model}' input cost ${requested_cap.input_pricing}/M exceeds budget ${policy.max_input_cost_per_million}/M"
                )
                # Prefer canonical cost-efficient tiers within the provider
                if provider_name == "gemini" and any(
                    c[0].model == "gemini-1.5-flash" for c in compatible_candidates
                ):
                    selected_cap = next(
                        c[0]
                        for c in compatible_candidates
                        if c[0].model == "gemini-1.5-flash"
                    )
                elif provider_name == "openai" and any(
                    c[0].model == "gpt-4o-mini" for c in compatible_candidates
                ):
                    selected_cap = next(
                        c[0]
                        for c in compatible_candidates
                        if c[0].model == "gpt-4o-mini"
                    )
                elif provider_name == "anthropic" and any(
                    c[0].model == "claude-3-haiku" for c in compatible_candidates
                ):
                    selected_cap = next(
                        c[0]
                        for c in compatible_candidates
                        if c[0].model == "claude-3-haiku"
                    )
                else:
                    same_prov = [
                        c
                        for c in compatible_candidates
                        if c[0].provider == provider_name
                    ]
                    chosen = same_prov[0] if same_prov else compatible_candidates[0]
                    selected_cap, _ = chosen
                selected_model = selected_cap.model
                selected_provider = selected_cap.provider
                reasons.append(
                    f"Down-tiered to cost-compliant model '{selected_model}' (${selected_cap.input_pricing}/M)"
                )

            # Case B: Reasoning required and requested model lacked it
            elif (
                "supports_reasoning" in policy.required_capabilities
                and not requested_cap.supports_reasoning
            ):
                reasons.append(
                    f"Model '{model}' lacks required capability 'supports_reasoning'"
                )
                reasoning_candidates = [
                    c for c in compatible_candidates if c[0].supports_reasoning
                ]
                same_prov = [
                    c for c in reasoning_candidates if c[0].provider == provider_name
                ]
                if same_prov:
                    chosen = same_prov[0]
                elif any(c[0].model == "o3-mini" for c in reasoning_candidates):
                    chosen = next(
                        c for c in reasoning_candidates if c[0].model == "o3-mini"
                    )
                else:
                    chosen = (
                        reasoning_candidates[0]
                        if reasoning_candidates
                        else compatible_candidates[0]
                    )
                selected_cap, _ = chosen
                selected_model = selected_cap.model
                selected_provider = selected_cap.provider
                reasons.append(
                    f"Re-routed to reasoning model '{selected_model}' under '{selected_provider}'"
                )

            # Case C: Cost-aware routing on simple_chat
            elif (
                policy.cost_aware_routing
                and policy.workload_class == "simple_chat"
                and requested_cap.input_pricing > 0.50
            ):
                cost_candidates = [
                    c
                    for c in compatible_candidates
                    if c[0].provider == provider_name and c[0].input_pricing <= 0.50
                ]
                if cost_candidates:
                    chosen = cost_candidates[0]
                    selected_cap, _ = chosen
                    selected_model = selected_cap.model
                    selected_provider = selected_cap.provider
                    reasons.append(
                        f"Cost-Aware Routing: Workload 'simple_chat' meets quality threshold under cost-optimized model '{selected_model}' (${selected_cap.input_pricing}/M)"
                    )
                else:
                    match = next(
                        c for c in compatible_candidates if c[0].model == model
                    )
                    selected_cap = match[0]
                    selected_model = selected_cap.model
                    selected_provider = selected_cap.provider
                    reasons.append(
                        f"Requested model '{selected_model}' preserved: no cheaper candidate within provider '{selected_provider}'."
                    )

            # Case D: Specific requested model requested and survived hard filters
            elif any(c[0].model == model for c in compatible_candidates):
                match = next(c for c in compatible_candidates if c[0].model == model)
                selected_cap = match[0]
                selected_model = selected_cap.model
                selected_provider = selected_cap.provider
                reasons.append(
                    f"Requested model '{selected_model}' preserved under '{selected_provider}'."
                )

            # Case E: Autonomous / intelligent multi-objective top score
            else:
                selected_cap, top_score = compatible_candidates[0]
                selected_model = selected_cap.model
                selected_provider = selected_cap.provider
                reasons.append(
                    f"Multi-objective scoring selected '{selected_model}' under '{selected_provider}' (score: {top_score:.3f})"
                )

        # 4. Construct Cross-Provider Non-Loopback Fallback Chain
        fallback_chain: list[tuple[str, str]] = []
        if policy.allow_fallback:
            # Deterministic fallback mapping for canonical providers ensuring stable failover
            canonical_fallbacks: dict[str, list[tuple[str, str]]] = {
                "anthropic": [("openai", "gpt-4o"), ("gemini", "gemini-1.5-flash")],
                "openai": (
                    [("gemini", "gemini-1.5-flash"), ("groq", "llama-3.1-8b-instant")]
                    if "mini" in selected_model
                    else [
                        ("anthropic", "claude-3-5-sonnet"),
                        ("gemini", "gemini-1.5-pro"),
                    ]
                ),
                "gemini": [
                    ("openai", "gpt-4o-mini"),
                    ("groq", "llama-3.3-70b-versatile"),
                ],
                "groq": [("openai", "gpt-4o-mini"), ("gemini", "gemini-1.5-flash")],
                "deepseek": [("openai", "gpt-4o-mini"), ("gemini", "gemini-1.5-flash")],
                "local": [("openai", "gpt-4o-mini"), ("gemini", "gemini-1.5-flash")],
            }

            candidates_from_map = canonical_fallbacks.get(
                selected_provider,
                [("openai", "gpt-4o-mini"), ("gemini", "gemini-1.5-flash")],
            )

            for p, m in candidates_from_map:
                if (
                    p not in policy.disallowed_providers
                    and p != selected_provider
                    and (p, m) not in fallback_chain
                ):
                    fallback_chain.append((p, m))

            # Augment with remaining compatible candidates from other providers if chain has room
            for cand, _ in compatible_candidates:
                if (
                    cand.provider != selected_provider
                    and cand.provider not in policy.disallowed_providers
                    and (cand.provider, cand.model) not in fallback_chain
                ):
                    fallback_chain.append((cand.provider, cand.model))
                if len(fallback_chain) >= 3:
                    break

            reasons.append(
                f"Constructed {len(fallback_chain)}-candidate fallback chain: {fallback_chain}"
            )

        reasons.append(
            f"Final routing choice: '{selected_provider}' using model '{selected_model}'"
        )

        cost_savings = max(
            0.0, requested_cap.input_pricing - selected_cap.input_pricing
        )

        return RoutingDecision(
            selected_provider=selected_provider,
            selected_model=selected_model,
            fallback_chain=fallback_chain,
            policy_applied="intelligent_multi_objective_policy",
            decision_reasons=reasons,
            estimated_input_cost=selected_cap.input_pricing,
            estimated_output_cost=selected_cap.output_pricing,
            cost_savings_usd_per_million=cost_savings,
            is_observable=True,
            correlation_id=policy.correlation_id,
        )


_global_router: ModelRouter | None = None


def get_model_router() -> ModelRouter:
    """Retrieve singleton ModelRouter instance."""
    global _global_router
    if _global_router is None:
        _global_router = ModelRouter()
    return _global_router
