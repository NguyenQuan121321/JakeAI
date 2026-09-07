"""Token Accounting Ledger and Telemetry for FinOps Optimization.

Implements rigorous token accounting across:
- Raw prompt tokens (unpruned baseline).
- Pruned prompt tokens (heuristic compression).
- Cache hit tokens saved (Tier 1 & Tier 2 Layer A response cache).
- Provider Prompt Caching (Tier 5 Layer B Anthropic/OpenAI KV prompt cache).
- Net token reduction percentage, dollar costs, and provider savings.
"""

from __future__ import annotations

import time

from pydantic import BaseModel, Field


class TokenUsageRecord(BaseModel):
    """Accounting entry for a single inference request."""

    request_id: str
    tenant_id: str
    model: str
    raw_prompt_tokens: int
    pruned_prompt_tokens: int
    completion_tokens: int
    cache_hit: bool  # Layer A (JakeAI Redis exact / Qdrant semantic response cache)
    cache_type: str = "none"  # "none", "exact", "semantic"
    tokens_saved: int
    actual_billed_tokens: int
    reduction_percentage: float = Field(
        ...,
        description="Percentage of tokens saved: (tokens_saved / total_baseline) * 100",
    )
    timestamp: float = Field(default_factory=time.time)

    # Tier 5: Provider Prompt Caching (Layer B) Telemetry
    provider_cache_hit: bool = Field(
        default=False,
        description="Layer B: True strictly if upstream provider reported cached tokens > 0",
    )
    provider_cached_tokens: int = Field(
        default=0,
        description="Layer B: Input tokens served from upstream KV cache",
    )
    provider_uncached_tokens: int = Field(
        default=0,
        description="Layer B: Input tokens processed normally without cache hit",
    )
    provider_cache_write_tokens: int = Field(
        default=0,
        description="Layer B: Input tokens written to upstream cache (Anthropic cache_creation)",
    )
    provider_miss_reason: str = Field(
        default="none",
        description="Layer B: Attribution for upstream prompt cache miss",
    )
    provider_cost_savings_usd: float = Field(
        default=0.0,
        description="Layer B: Dollar amount saved from prompt cache discounts",
    )
    provider_actual_cost_usd: float = Field(
        default=0.0,
        description="Layer B: Incurred upstream cost after cache discounts",
    )
    provider_name: str = Field(default="generic")


class TokenBenchmarkSummary(BaseModel):
    """Aggregated benchmark report proving empirical token savings."""

    total_requests: int
    cache_hits: int
    cache_hit_rate: float
    total_baseline_tokens: int
    total_actual_billed_tokens: int
    total_tokens_saved: int
    net_reduction_percentage: float
    context_pruning_avg_savings_pct: float
    is_claim_verified: bool = Field(
        ..., description="True if net_reduction_percentage >= 40.0%"
    )

    # Aggregated Tier 5 metrics
    provider_cache_hits: int = Field(default=0)
    provider_cache_hit_rate: float = Field(default=0.0)
    total_provider_cached_tokens: int = Field(default=0)
    total_provider_cost_savings_usd: float = Field(default=0.0)


class TokenAccounting:
    """Ledger computing and recording token optimization metrics."""

    @staticmethod
    def record_transaction(
        request_id: str,
        tenant_id: str,
        model: str,
        raw_prompt_tokens: int,
        pruned_prompt_tokens: int,
        completion_tokens: int,
        cache_hit: bool = False,
        cache_type: str = "none",
        provider_cache_hit: bool = False,
        provider_cached_tokens: int = 0,
        provider_uncached_tokens: int = 0,
        provider_cache_write_tokens: int = 0,
        provider_miss_reason: str = "none",
        provider_cost_savings_usd: float = 0.0,
        provider_actual_cost_usd: float = 0.0,
        provider_name: str = "generic",
    ) -> TokenUsageRecord:
        """Calculate exact token accounting and savings for an inference call.

        Formulas:
          Baseline Total = raw_prompt_tokens + completion_tokens
          If Layer A Cache Hit:
            tokens_saved = Baseline Total
            actual_billed = 0
            reduction_percentage = 100.0%
          If Layer A Cache Miss:
            tokens_saved = max(0, raw_prompt_tokens - pruned_prompt_tokens)
            actual_billed = pruned_prompt_tokens + completion_tokens
            reduction_percentage = (tokens_saved / Baseline Total) * 100
        """
        baseline_total = max(1, raw_prompt_tokens + completion_tokens)

        if cache_hit:
            tokens_saved = baseline_total
            actual_billed = 0
            reduction_pct = 100.0
        else:
            tokens_saved = max(0, raw_prompt_tokens - pruned_prompt_tokens)
            actual_billed = pruned_prompt_tokens + completion_tokens
            reduction_pct = round((tokens_saved / baseline_total) * 100.0, 2)

        return TokenUsageRecord(
            request_id=request_id,
            tenant_id=tenant_id,
            model=model,
            raw_prompt_tokens=raw_prompt_tokens,
            pruned_prompt_tokens=pruned_prompt_tokens,
            completion_tokens=completion_tokens,
            cache_hit=cache_hit,
            cache_type=cache_type,
            tokens_saved=tokens_saved,
            actual_billed_tokens=actual_billed,
            reduction_percentage=reduction_pct,
            provider_cache_hit=provider_cache_hit,
            provider_cached_tokens=provider_cached_tokens,
            provider_uncached_tokens=provider_uncached_tokens,
            provider_cache_write_tokens=provider_cache_write_tokens,
            provider_miss_reason=provider_miss_reason,
            provider_cost_savings_usd=provider_cost_savings_usd,
            provider_actual_cost_usd=provider_actual_cost_usd,
            provider_name=provider_name,
        )

    @staticmethod
    def aggregate_benchmark(
        records: list[TokenUsageRecord],
    ) -> TokenBenchmarkSummary:
        """Compute statistical summary across an evaluation corpus."""
        if not records:
            return TokenBenchmarkSummary(
                total_requests=0,
                cache_hits=0,
                cache_hit_rate=0.0,
                total_baseline_tokens=0,
                total_actual_billed_tokens=0,
                total_tokens_saved=0,
                net_reduction_percentage=0.0,
                context_pruning_avg_savings_pct=0.0,
                is_claim_verified=False,
            )

        total_reqs = len(records)
        cache_hits = sum(1 for r in records if r.cache_hit)
        cache_hit_rate = round((cache_hits / total_reqs) * 100.0, 2)

        total_baseline = sum(r.raw_prompt_tokens + r.completion_tokens for r in records)
        total_billed = sum(r.actual_billed_tokens for r in records)
        total_saved = sum(r.tokens_saved for r in records)

        net_reduction_pct = (
            round((total_saved / total_baseline) * 100.0, 2)
            if total_baseline > 0
            else 0.0
        )

        # Context pruning stats on cache-miss requests
        miss_records = [
            r for r in records if not r.cache_hit and r.raw_prompt_tokens > 0
        ]
        if miss_records:
            prune_savings = [
                ((r.raw_prompt_tokens - r.pruned_prompt_tokens) / r.raw_prompt_tokens)
                * 100.0
                for r in miss_records
            ]
            avg_prune_savings = round(sum(prune_savings) / len(prune_savings), 2)
        else:
            avg_prune_savings = 0.0

        # Tier 5 Provider Cache aggregations
        prov_hits = sum(1 for r in records if r.provider_cache_hit)
        prov_hit_rate = round((prov_hits / total_reqs) * 100.0, 2)
        total_prov_cached = sum(r.provider_cached_tokens for r in records)
        total_prov_savings = round(sum(r.provider_cost_savings_usd for r in records), 4)

        is_verified = net_reduction_pct >= 40.0

        return TokenBenchmarkSummary(
            total_requests=total_reqs,
            cache_hits=cache_hits,
            cache_hit_rate=cache_hit_rate,
            total_baseline_tokens=total_baseline,
            total_actual_billed_tokens=total_billed,
            total_tokens_saved=total_saved,
            net_reduction_percentage=net_reduction_pct,
            context_pruning_avg_savings_pct=avg_prune_savings,
            is_claim_verified=is_verified,
            provider_cache_hits=prov_hits,
            provider_cache_hit_rate=prov_hit_rate,
            total_provider_cached_tokens=total_prov_cached,
            total_provider_cost_savings_usd=total_prov_savings,
        )
