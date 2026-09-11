"""Cost Attribution Engine for Phase 05 AI FinOps.

Mathematically guarantees non-overlapping, zero double-counting cost attribution across:
1. Cache Hit (Tier 1 & Tier 2 JakeAI response cache)
2. Physical Context Reduction (Token pruner, two-zone compilation, RAG context selection)
3. Provider Prompt Caching (Upstream prompt KV cache read discounts net of write fees)
4. Model Routing (Down-tiering to cheaper capable model)
5. Avoided Retries (Circuit breaker protection)
"""

from __future__ import annotations

from app.finops.models import SavingsAttribution
from app.finops.pricing import (
    calculate_model_routing_savings,
    calculate_provider_cache_savings,
    get_pricing,
)


def compute_savings_attribution(
    model: str,
    raw_tokens: int,
    optimized_tokens: int,
    output_tokens: int,
    is_cache_hit: bool = False,
    provider_cached_tokens: int = 0,
    provider_cache_write_tokens: int = 0,
    requested_model: str | None = None,
    avoided_retries_cost_usd: float = 0.0,
) -> SavingsAttribution:
    """Calculate mathematically proven non-overlapping savings attribution.

    Case 1: JakeAI Response Cache Hit (Tier 1 / Tier 2)
      - Upstream execution is 100% avoided.
      - cache_hit_usd = baseline_cost (raw_tokens + output_tokens at model rate)
      - physical_reduction_usd = 0.0 (no upstream payload was sent)
      - provider_cache_usd = 0.0 (no upstream provider was contacted)
      - model_routing_usd = 0.0
      - avoided_retries_usd = 0.0
      - Total Savings = cache_hit_usd

    Case 2: Cache Miss (Upstream execution completed)
      - cache_hit_usd = 0.0
      - model_routing_usd: If requested_model was provided and differs from model:
          routing_delta = (raw_tokens * (rate_requested - rate_selected)) / 1M
      - physical_reduction_usd: Tokens pruned before upstream transmission
          (raw_tokens - optimized_tokens) * rate_selected / 1M
      - provider_cache_usd: Upstream KV cache discounts applied strictly to the
          optimized_tokens sent upstream:
          cached_tokens * (input_rate - cache_read_rate) - write_surcharge
      - avoided_retries_usd: Circuit breaker avoided retry costs
      - Total Savings = sum of all disjoint components (no double counting).
    """
    pricing = get_pricing(model)

    if is_cache_hit:
        # Full inference avoided by JakeAI response cache
        baseline_cost = (
            (raw_tokens * pricing.input_per_million)
            + (output_tokens * pricing.output_per_million)
        ) / 1_000_000.0

        cache_saved = round(max(0.0, baseline_cost), 6)
        return SavingsAttribution(
            cache_hit_usd=cache_saved,
            physical_reduction_usd=0.0,
            provider_cache_usd=0.0,
            model_routing_usd=0.0,
            avoided_retries_usd=0.0,
            total_savings_usd=cache_saved,
        )

    # 1. Model Routing Savings (if router down-tiered from a more expensive requested model)
    routing_saved = 0.0
    effective_req_model = requested_model or model
    if effective_req_model.lower().strip() != model.lower().strip():
        routing_saved = calculate_model_routing_savings(
            requested_model=effective_req_model,
            selected_model=model,
            input_tokens=raw_tokens,
            output_tokens=output_tokens,
        )

    # 2. Physical Context Reduction Savings (evaluated at selected model pricing)
    tokens_pruned = max(0, raw_tokens - optimized_tokens)
    physical_saved = round((tokens_pruned * pricing.input_per_million) / 1_000_000.0, 6)

    # 3. Provider Prompt Caching Savings (evaluated strictly on optimized tokens sent)
    prov_cache_saved = calculate_provider_cache_savings(
        model=model,
        cached_input_tokens=provider_cached_tokens,
        cache_write_tokens=provider_cache_write_tokens,
    )

    # 4. Avoided Retries Savings
    retries_saved = round(max(0.0, avoided_retries_cost_usd), 6)

    # 5. Total Non-Overlapping Sum
    total_savings = round(
        max(0.0, routing_saved + physical_saved + prov_cache_saved + retries_saved),
        6,
    )

    return SavingsAttribution(
        cache_hit_usd=0.0,
        physical_reduction_usd=physical_saved,
        provider_cache_usd=prov_cache_saved,
        model_routing_usd=routing_saved,
        avoided_retries_usd=retries_saved,
        total_savings_usd=total_savings,
    )
