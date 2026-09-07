"""Observable Policy-Driven Model Router for Phase 01.

Provides:
1. RoutingPolicy: explicit constraints (requested model, provider, capabilities, cost, workload class).
2. RoutingDecision: verifiable, observable telemetry object recording the selected provider,
   model, fallback chain, and step-by-step decision reasons (zero magic heuristics).
3. ModelRouter: deterministic evaluation engine resolving requests to optimal providers.
"""

from __future__ import annotations

import logging
from typing import Any

from pydantic import BaseModel, Field

from app.providers.base import ModelCapabilityCatalog
from app.providers.registry import get_provider_registry

logger = logging.getLogger(__name__)


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
        description="Capabilities required, e.g. supports_tools, supports_prompt_cache, supports_reasoning",
    )
    max_input_cost_per_million: float | None = Field(
        default=None, description="Maximum allowed input cost in USD per 1M tokens"
    )
    tenant_id: str = Field(default="default", description="Tenant context")
    workload_class: str | None = Field(
        default=None,
        description="Class of workload: simple_chat, coding, financial_reasoning, rag, structured_json",
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


class RoutingDecision(BaseModel):
    """Observable outcome of a routing evaluation as required by Phase 01 Section 5."""

    selected_provider: str
    selected_model: str
    fallback_chain: list[tuple[str, str]] = Field(
        default_factory=list,
        description="Ordered list of (provider, model) fallback candidates",
    )
    policy_applied: str = "default_mapping"
    decision_reasons: list[str] = Field(default_factory=list)
    estimated_input_cost: float = 0.0
    estimated_output_cost: float = 0.0
    cost_savings_usd_per_million: float = 0.0
    is_observable: bool = True

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
        }


class ModelRouter:
    """Policy-based model and provider routing engine."""

    def __init__(self) -> None:
        self.registry = get_provider_registry()

    def route(self, policy: RoutingPolicy) -> RoutingDecision:
        """Evaluate routing policy and return fully observable RoutingDecision."""
        reasons: list[str] = []
        model = policy.requested_model.strip()
        reasons.append(
            f"Received request for model '{model}' with workload '{policy.workload_class or 'standard'}'"
        )

        # 1. Resolve default provider
        provider_name = (
            policy.preferred_provider
            or self.registry.resolve_provider_name_for_model(model)
        )
        reasons.append(
            f"Initial provider resolution mapped '{model}' -> '{provider_name}'"
        )

        # 2. Check provider constraints (allowed/disallowed)
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

        # 3. Retrieve model capabilities
        cap = ModelCapabilityCatalog.get(model, provider=provider_name)
        selected_model = model

        # 4. Check capability requirements
        for req_cap in policy.required_capabilities:
            has_cap = getattr(cap, req_cap, False)
            if not has_cap:
                reasons.append(
                    f"Model '{selected_model}' lacks required capability '{req_cap}'"
                )
                # If reasoning required, route to reasoning-capable model
                if req_cap == "supports_reasoning":
                    if provider_name == "openai":
                        selected_model = "o3-mini"
                    elif provider_name == "deepseek":
                        selected_model = "deepseek-reasoner"
                    else:
                        provider_name = "openai"
                        selected_model = "o3-mini"
                    cap = ModelCapabilityCatalog.get(
                        selected_model, provider=provider_name
                    )
                    reasons.append(
                        f"Re-routed to reasoning model '{selected_model}' under '{provider_name}'"
                    )

        initial_cap = cap

        # 5. Cost-Aware Model Routing (Phase 03 Section 2 Layer 8)
        if (
            (policy.cost_aware_routing or policy.workload_class == "simple_chat")
            and policy.workload_class == "simple_chat"
            and cap.input_pricing > 0.50
        ):
            if provider_name == "openai" and "mini" not in selected_model:
                selected_model = "gpt-4o-mini"
            elif provider_name == "anthropic" and "haiku" not in selected_model:
                selected_model = "claude-3-haiku"
            elif provider_name == "gemini" and "flash" not in selected_model:
                selected_model = "gemini-1.5-flash"
            cap = ModelCapabilityCatalog.get(selected_model, provider=provider_name)
            reasons.append(
                f"Cost-Aware Routing: Workload 'simple_chat' meets quality threshold under cost-optimized model '{selected_model}' (${cap.input_pricing}/M)"
            )

        # 6. Cost budget check
        if (
            policy.max_input_cost_per_million is not None
            and cap.input_pricing > policy.max_input_cost_per_million
        ):
            reasons.append(
                f"Model '{selected_model}' input cost ${cap.input_pricing}/M exceeds budget ${policy.max_input_cost_per_million}/M"
            )
            # Downgrade to cost-efficient tier within same or compatible provider
            if provider_name == "openai":
                selected_model = "gpt-4o-mini"
            elif provider_name == "anthropic":
                selected_model = "claude-3-haiku"
            elif provider_name == "gemini":
                selected_model = "gemini-1.5-flash"
            cap = ModelCapabilityCatalog.get(selected_model, provider=provider_name)
            reasons.append(
                f"Down-tiered to cost-compliant model '{selected_model}' (${cap.input_pricing}/M)"
            )

        # 7. Build Cross-Provider Fallback Chain
        fallback_chain: list[tuple[str, str]] = []
        if policy.allow_fallback:
            if provider_name == "anthropic":
                fallback_chain = [("openai", "gpt-4o"), ("gemini", "gemini-1.5-flash")]
            elif provider_name == "openai":
                if "mini" in selected_model:
                    fallback_chain = [
                        ("gemini", "gemini-1.5-flash"),
                        ("groq", "llama-3.1-8b-instant"),
                    ]
                else:
                    fallback_chain = [
                        ("anthropic", "claude-3-5-sonnet"),
                        ("gemini", "gemini-1.5-pro"),
                    ]
            elif provider_name == "gemini":
                fallback_chain = [
                    ("openai", "gpt-4o-mini"),
                    ("groq", "llama-3.3-70b-versatile"),
                ]
            elif provider_name == "groq" or provider_name == "deepseek":
                fallback_chain = [
                    ("openai", "gpt-4o-mini"),
                    ("gemini", "gemini-1.5-flash"),
                ]
            else:
                fallback_chain = [
                    ("openai", "gpt-4o-mini"),
                    ("gemini", "gemini-1.5-flash"),
                ]

            # Filter out any disallowed providers from fallback chain
            fallback_chain = [
                (p, m)
                for p, m in fallback_chain
                if p not in policy.disallowed_providers
            ]
            reasons.append(
                f"Constructed {len(fallback_chain)}-candidate fallback chain: {fallback_chain}"
            )

        reasons.append(
            f"Final routing choice: '{provider_name}' using model '{selected_model}'"
        )

        cost_savings = max(0.0, initial_cap.input_pricing - cap.input_pricing)

        return RoutingDecision(
            selected_provider=provider_name,
            selected_model=selected_model,
            fallback_chain=fallback_chain,
            policy_applied="explicit_capability_and_budget_policy",
            decision_reasons=reasons,
            estimated_input_cost=cap.input_pricing,
            estimated_output_cost=cap.output_pricing,
            cost_savings_usd_per_million=cost_savings,
            is_observable=True,
        )


_global_router: ModelRouter | None = None


def get_model_router() -> ModelRouter:
    global _global_router
    if _global_router is None:
        _global_router = ModelRouter()
    return _global_router
