"""FinOps Pricing Catalog and Calculation Engine.

Provides versioned official pricing matrices across OpenAI, Anthropic, Gemini, Groq,
DeepSeek, and OpenRouter with support for:
- Standard uncached input token rates ($/1M tokens)
- Upstream prompt cache read discount rates ($/1M tokens)
- Upstream prompt cache creation/write surcharges ($/1M tokens)
- Output/completion token rates ($/1M tokens)
"""

from __future__ import annotations

from app.optimizer.provider_pricing import (
    ModelPricing,
    get_model_pricing,
)


def get_pricing(model: str) -> ModelPricing:
    """Retrieve pricing specification for a model name."""
    return get_model_pricing(model)


def calculate_baseline_cost(
    model: str,
    raw_input_tokens: int,
    output_tokens: int,
) -> float:
    """Calculate unoptimized baseline cost assuming standard uncached input rate."""
    pricing = get_model_pricing(model)
    cost = (
        (raw_input_tokens * pricing.input_per_million)
        + (output_tokens * pricing.output_per_million)
    ) / 1_000_000.0
    return round(max(0.0, cost), 6)


def calculate_billed_cost(
    model: str,
    uncached_input_tokens: int,
    cached_input_tokens: int = 0,
    cache_write_tokens: int = 0,
    output_tokens: int = 0,
) -> float:
    """Calculate actual billed cost using provider discount rates for cached input."""
    pricing = get_model_pricing(model)
    cost = (
        (uncached_input_tokens * pricing.input_per_million)
        + (cached_input_tokens * pricing.cache_read_per_million)
        + (cache_write_tokens * pricing.cache_write_per_million)
        + (output_tokens * pricing.output_per_million)
    ) / 1_000_000.0
    return round(max(0.0, cost), 6)


def calculate_provider_cache_savings(
    model: str,
    cached_input_tokens: int,
    cache_write_tokens: int = 0,
) -> float:
    """Calculate net dollar savings from upstream provider prompt caching.

    Formula:
      Gross Savings = cached_input_tokens * (standard_input_rate - cache_read_rate)
      Write Surcharge = cache_write_tokens * cache_write_rate (or delta above standard input)
      Net Savings = Gross Savings - Surcharge (can be negative if writing but not reading)
    """
    if cached_input_tokens <= 0 and cache_write_tokens <= 0:
        return 0.0

    pricing = get_model_pricing(model)
    gross_savings = (
        cached_input_tokens
        * (pricing.input_per_million - pricing.cache_read_per_million)
    ) / 1_000_000.0

    # For Anthropic, cache write costs 1.25x standard input (extra 0.25x surcharge)
    surcharge = 0.0
    if (
        cache_write_tokens > 0
        and pricing.cache_write_per_million > pricing.input_per_million
    ):
        surcharge = (
            cache_write_tokens
            * (pricing.cache_write_per_million - pricing.input_per_million)
        ) / 1_000_000.0

    net_savings = gross_savings - surcharge
    return round(net_savings, 6)


def calculate_model_routing_savings(
    requested_model: str,
    selected_model: str,
    input_tokens: int,
    output_tokens: int,
) -> float:
    """Calculate dollar savings from intelligent model routing to a lower-cost model.

    If selected_model is cheaper than requested_model, savings = requested_cost - selected_cost.
    If selected_model is equal or more expensive, returns 0.0.
    """
    if requested_model.lower().strip() == selected_model.lower().strip():
        return 0.0

    req_pricing = get_model_pricing(requested_model)
    sel_pricing = get_model_pricing(selected_model)

    req_cost = (
        (input_tokens * req_pricing.input_per_million)
        + (output_tokens * req_pricing.output_per_million)
    ) / 1_000_000.0

    sel_cost = (
        (input_tokens * sel_pricing.input_per_million)
        + (output_tokens * sel_pricing.output_per_million)
    ) / 1_000_000.0

    savings = max(0.0, req_cost - sel_cost)
    return round(savings, 6)
