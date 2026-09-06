"""Token Accounting Ledger and Telemetry for FinOps Optimization.

Implements rigorous token accounting across:
- Raw prompt tokens (unpruned baseline).
- Pruned prompt tokens (heuristic compression).
- Cache hit tokens saved (Tier 1 & Tier 2).
- Net token reduction percentage and cost savings.
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
    cache_hit: bool
    cache_type: str = "none"  # "none", "exact", "semantic"
    tokens_saved: int
    actual_billed_tokens: int
    reduction_percentage: float = Field(
        ...,
        description="Percentage of tokens saved: (tokens_saved / total_baseline) * 100",
    )
    timestamp: float = Field(default_factory=time.time)


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
    ) -> TokenUsageRecord:
        """Calculate exact token accounting and savings for an inference call.

        Formulas:
          Baseline Total = raw_prompt_tokens + completion_tokens
          If Cache Hit:
            tokens_saved = Baseline Total
            actual_billed = 0
            reduction_percentage = 100.0%
          If Cache Miss:
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
        )
