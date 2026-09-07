"""Provider Pricing Matrix and Cost Accounting for Tier 5.

Accurately computes baseline costs, actual incurred upstream costs, and FinOps savings
leveraging official token pricing across Anthropic, OpenAI, DeepSeek, and Gemini:
- Anthropic: ~90% cache read discount, 1.25x cache write creation surcharge.
- OpenAI: ~50% automatic prefix cache read discount.
- DeepSeek: ~90% context cache read discount.
- Gemini: ~75% cached context discount.
"""

from __future__ import annotations

from pydantic import BaseModel, Field


class ModelPricing(BaseModel):
    """Token pricing rates per 1,000,000 tokens in USD."""

    model_id: str
    provider: str
    input_per_million: float
    cache_read_per_million: float
    cache_write_per_million: float
    output_per_million: float


class CostMeasurement(BaseModel):
    """Normalized internal cost record as required by Phase 00 Section 7."""

    provider: str
    model: str
    raw_input_tokens: int
    optimized_input_tokens: int
    cached_input_tokens: int
    output_tokens: int
    baseline_cost_usd: float
    actual_cost_usd: float | None = None
    estimated_savings_usd: float
    savings_percentage: float


class ProviderCostBreakdown(BaseModel):
    """Calculated cost metrics for an upstream inference request."""

    model_id: str
    provider: str
    uncached_input_tokens: int
    cached_input_tokens: int
    cache_write_tokens: int
    output_tokens: int
    baseline_cost_usd: float = Field(
        ..., description="Cost if prompt caching was not utilized"
    )
    actual_cost_usd: float = Field(
        ..., description="Actual cost incurred with cache discounts and write charges"
    )
    savings_usd: float = Field(
        ..., description="Dollar amount saved: max(0, baseline - actual)"
    )
    savings_percentage: float = Field(
        ..., description="Percentage saved: (savings_usd / baseline_cost_usd) * 100"
    )


PRICING_CATALOG: dict[str, ModelPricing] = {
    # Anthropic
    "claude-3-5-sonnet": ModelPricing(
        model_id="claude-3-5-sonnet",
        provider="anthropic",
        input_per_million=3.00,
        cache_read_per_million=0.30,  # 90% discount
        cache_write_per_million=3.75,  # 1.25x creation
        output_per_million=15.00,
    ),
    "claude-3-haiku": ModelPricing(
        model_id="claude-3-haiku",
        provider="anthropic",
        input_per_million=0.25,
        cache_read_per_million=0.025,  # 90% discount
        cache_write_per_million=0.30,
        output_per_million=1.25,
    ),
    "claude-3-opus": ModelPricing(
        model_id="claude-3-opus",
        provider="anthropic",
        input_per_million=15.00,
        cache_read_per_million=1.50,
        cache_write_per_million=18.75,
        output_per_million=75.00,
    ),
    # OpenAI
    "gpt-4o": ModelPricing(
        model_id="gpt-4o",
        provider="openai",
        input_per_million=2.50,
        cache_read_per_million=1.25,  # 50% discount
        cache_write_per_million=2.50,
        output_per_million=10.00,
    ),
    "gpt-4o-mini": ModelPricing(
        model_id="gpt-4o-mini",
        provider="openai",
        input_per_million=0.15,
        cache_read_per_million=0.075,  # 50% discount
        cache_write_per_million=0.15,
        output_per_million=0.60,
    ),
    "o1": ModelPricing(
        model_id="o1",
        provider="openai",
        input_per_million=15.00,
        cache_read_per_million=7.50,
        cache_write_per_million=15.00,
        output_per_million=60.00,
    ),
    "o3-mini": ModelPricing(
        model_id="o3-mini",
        provider="openai",
        input_per_million=1.10,
        cache_read_per_million=0.55,
        cache_write_per_million=1.10,
        output_per_million=4.40,
    ),
    # Gemini
    "gemini-1.5-flash": ModelPricing(
        model_id="gemini-1.5-flash",
        provider="gemini",
        input_per_million=0.075,
        cache_read_per_million=0.01875,  # 75% discount
        cache_write_per_million=0.075,
        output_per_million=0.30,
    ),
    "gemini-1.5-pro": ModelPricing(
        model_id="gemini-1.5-pro",
        provider="gemini",
        input_per_million=3.50,
        cache_read_per_million=0.875,
        cache_write_per_million=3.50,
        output_per_million=10.50,
    ),
    # DeepSeek
    "deepseek-chat": ModelPricing(
        model_id="deepseek-chat",
        provider="deepseek",
        input_per_million=0.14,
        cache_read_per_million=0.014,  # 90% discount
        cache_write_per_million=0.14,
        output_per_million=0.28,
    ),
    # Groq
    "llama-3.3-70b-versatile": ModelPricing(
        model_id="llama-3.3-70b-versatile",
        provider="groq",
        input_per_million=0.59,
        cache_read_per_million=0.59,
        cache_write_per_million=0.59,
        output_per_million=0.79,
    ),
    "llama-3.1-8b-instant": ModelPricing(
        model_id="llama-3.1-8b-instant",
        provider="groq",
        input_per_million=0.05,
        cache_read_per_million=0.05,
        cache_write_per_million=0.05,
        output_per_million=0.08,
    ),
}

DEFAULT_FALLBACK_PRICING = ModelPricing(
    model_id="default-llm",
    provider="generic",
    input_per_million=2.00,
    cache_read_per_million=1.00,
    cache_write_per_million=2.00,
    output_per_million=8.00,
)


def get_model_pricing(model: str) -> ModelPricing:
    """Retrieve pricing definition for model name, falling back to closest match or default."""
    m_lower = model.lower().strip()
    if m_lower in PRICING_CATALOG:
        return PRICING_CATALOG[m_lower]

    # Check longest keys first so specific models (e.g. gpt-4o-mini) match before broader prefixes (gpt-4o)
    for key, pricing in sorted(
        PRICING_CATALOG.items(), key=lambda x: len(x[0]), reverse=True
    ):
        if key in m_lower or m_lower in key:
            return pricing

    # Fallback heuristic
    if "claude" in m_lower:
        return PRICING_CATALOG["claude-3-5-sonnet"]
    if "gemini" in m_lower:
        return PRICING_CATALOG["gemini-1.5-flash"]
    if "deepseek" in m_lower:
        return PRICING_CATALOG["deepseek-chat"]
    if "llama" in m_lower or "groq" in m_lower:
        return PRICING_CATALOG["llama-3.3-70b-versatile"]
    if "mini" in m_lower:
        return PRICING_CATALOG["gpt-4o-mini"]
    if "gpt" in m_lower:
        return PRICING_CATALOG["gpt-4o"]

    return DEFAULT_FALLBACK_PRICING


def calculate_provider_costs(
    model: str,
    uncached_input_tokens: int,
    cached_input_tokens: int,
    cache_write_tokens: int = 0,
    output_tokens: int = 0,
) -> ProviderCostBreakdown:
    """Calculate exact FinOps baseline, actual cost, and net savings for an inference call."""
    pricing = get_model_pricing(model)

    total_input = uncached_input_tokens + cached_input_tokens
    # Baseline assumes all prompt tokens were billed as standard uncached input with 0 write cost
    baseline_cost = (
        (total_input * pricing.input_per_million)
        + (output_tokens * pricing.output_per_million)
    ) / 1_000_000.0

    # Actual cost applies cached read discount + cache write surcharge
    actual_cost = (
        (uncached_input_tokens * pricing.input_per_million)
        + (cached_input_tokens * pricing.cache_read_per_million)
        + (cache_write_tokens * pricing.cache_write_per_million)
        + (output_tokens * pricing.output_per_million)
    ) / 1_000_000.0

    savings = max(0.0, baseline_cost - actual_cost)
    savings_pct = (
        round((savings / baseline_cost) * 100.0, 2) if baseline_cost > 0.0 else 0.0
    )

    return ProviderCostBreakdown(
        model_id=pricing.model_id,
        provider=pricing.provider,
        uncached_input_tokens=uncached_input_tokens,
        cached_input_tokens=cached_input_tokens,
        cache_write_tokens=cache_write_tokens,
        output_tokens=output_tokens,
        baseline_cost_usd=round(baseline_cost, 6),
        actual_cost_usd=round(actual_cost, 6),
        savings_usd=round(savings, 6),
        savings_percentage=savings_pct,
    )


def measure_cost(
    model: str,
    raw_input_tokens: int,
    optimized_input_tokens: int,
    cached_input_tokens: int = 0,
    output_tokens: int = 0,
    actual_cost_usd: float | None = None,
    provider: str | None = None,
) -> CostMeasurement:
    """Compute normalized CostMeasurement comparing unoptimized raw baseline vs optimized execution.

    Implements Phase 00 Section 7 requirements.
    Baseline cost assumes unoptimized raw input tokens + output tokens at standard uncached rate.
    Optimized cost accounts for physically reduced tokens and cached input token discounts.
    """
    pricing = get_model_pricing(model)
    resolved_provider = provider or pricing.provider

    # 1. Baseline: raw unoptimized input at standard rate
    baseline_cost = (
        (raw_input_tokens * pricing.input_per_million)
        + (output_tokens * pricing.output_per_million)
    ) / 1_000_000.0

    # 2. Optimized estimated cost: uncached optimized tokens + cached discount
    uncached_opt = max(0, optimized_input_tokens - cached_input_tokens)
    computed_opt_cost = (
        (uncached_opt * pricing.input_per_million)
        + (cached_input_tokens * pricing.cache_read_per_million)
        + (output_tokens * pricing.output_per_million)
    ) / 1_000_000.0

    effective_actual = (
        actual_cost_usd if actual_cost_usd is not None else computed_opt_cost
    )

    estimated_savings = max(0.0, baseline_cost - effective_actual)
    savings_pct = (
        round((estimated_savings / baseline_cost) * 100.0, 2)
        if baseline_cost > 0.0
        else 0.0
    )

    return CostMeasurement(
        provider=resolved_provider,
        model=pricing.model_id,
        raw_input_tokens=raw_input_tokens,
        optimized_input_tokens=optimized_input_tokens,
        cached_input_tokens=cached_input_tokens,
        output_tokens=output_tokens,
        baseline_cost_usd=round(baseline_cost, 6),
        actual_cost_usd=round(effective_actual, 6)
        if actual_cost_usd is not None
        else None,
        estimated_savings_usd=round(estimated_savings, 6),
        savings_percentage=savings_pct,
    )
