"""AI FinOps Domain Models & Telemetry Contracts.

Implements Phase 05 - AI FinOps & Cost Truth specifications:
1. Separate Metrics: Never collapse estimated tokens, physical pruned tokens,
   provider cached tokens, uncached tokens, output tokens, provider-reported total,
   actual billed cost, and estimated cost.
2. Per-Request Accounting Model: Comprehensive ledger records.
3. Billing Truth: Upstream provider usage is authoritative reconciliation source.
4. Non-Double-Counting Savings Attribution: Explicit breakdown into cache hit,
   physical reduction, provider prompt caching, model routing, and avoided retries.
5. Budget & Quota Governance: Dual token quota and dollar budget tracking with
   soft warnings (80%) and hard suspension (100%).
"""

from __future__ import annotations

import time
from enum import StrEnum
from typing import Any

from pydantic import BaseModel, Field, model_validator


class ReconciliationStatus(StrEnum):
    """Reconciliation state of an inference transaction."""

    AUTHORITATIVE = "authoritative"  # Authoritative provider-reported usage reconciled
    ESTIMATED = "estimated"  # Local tokenizer / planning estimate used as fallback


class SavingsAttribution(BaseModel):
    """Attribution breakdown of dollar savings per request.

    Guarantees no double-counting by strictly partitioning savings sources:
    - cache_hit_usd: Savings from JakeAI Tier 1 (exact Redis) or Tier 2 (semantic Qdrant)
      avoiding upstream inference completely.
    - physical_reduction_usd: Savings from pre-inference token pruning, two-zone compilation,
      or RAG context selection reducing input tokens sent to the provider.
    - provider_cache_usd: Savings from upstream prompt KV cache discounts (Anthropic/OpenAI/DeepSeek)
      net of cache creation surcharges.
    - model_routing_usd: Savings when ModelRouter routes to a lower-cost model fulfilling the task
      compared to the user's requested model.
    - avoided_retries_usd: Estimated cost avoided by circuit-breaker / failover avoidance.
    """

    cache_hit_usd: float = Field(
        default=0.0,
        ge=0.0,
        description="Savings from JakeAI exact or semantic response cache hit (100% baseline saved)",
    )
    physical_reduction_usd: float = Field(
        default=0.0,
        ge=0.0,
        description="Savings from physical token pruning before sending upstream",
    )
    provider_cache_usd: float = Field(
        default=0.0,
        description="Savings from upstream KV prompt cache discounts net of write surcharges",
    )
    model_routing_usd: float = Field(
        default=0.0,
        ge=0.0,
        description="Savings achieved by intelligent model routing to a lower-tier model",
    )
    avoided_retries_usd: float = Field(
        default=0.0,
        ge=0.0,
        description="Savings from circuit breaker preventing cascading retry expenditures",
    )
    total_savings_usd: float = Field(
        default=0.0,
        ge=0.0,
        description="Authoritative non-overlapping sum of all savings categories",
    )

    @model_validator(mode="after")
    def validate_non_overlapping_sum(self) -> SavingsAttribution:
        """Validate that total savings strictly matches the sum of attribution categories."""
        expected_total = max(
            0.0,
            round(
                self.cache_hit_usd
                + self.physical_reduction_usd
                + self.provider_cache_usd
                + self.model_routing_usd
                + self.avoided_retries_usd,
                6,
            ),
        )
        if self.total_savings_usd == 0.0 and expected_total > 0.0:
            self.total_savings_usd = expected_total
        return self


class FinOpsRecord(BaseModel):
    """Immutable per-request token & cost accounting record.

    Phase 05 Section 1 Mandate: Never collapse these metrics:
    - estimated_local_tokens
    - physical_tokens_removed
    - provider_cached_tokens
    - provider_uncached_tokens
    - output_tokens
    - provider_reported_total
    - actual_billed_cost_usd
    - estimated_cost_usd
    """

    request_id: str
    tenant_id: str
    provider: str
    model: str
    requested_model: str | None = None
    timestamp: float = Field(default_factory=time.time)

    # 1. Separated Token Metrics (Phase 05 Section 1)
    estimated_local_tokens: int = Field(
        ...,
        description="Local planning estimate before upstream execution (raw prompt + estimated completion)",
    )
    raw_tokens: int = Field(
        ...,
        ge=0,
        description="Baseline raw input prompt tokens before any optimization",
    )
    optimized_tokens: int = Field(
        ...,
        ge=0,
        description="Actual input tokens sent upstream after physical pruning and compilation",
    )
    physical_tokens_removed: int = Field(
        default=0,
        ge=0,
        description="Physical tokens pruned: max(0, raw_tokens - optimized_tokens)",
    )
    cached_tokens: int = Field(
        default=0,
        ge=0,
        description="Input tokens served from upstream prompt cache (or raw tokens on JakeAI cache hit)",
    )
    uncached_tokens: int = Field(
        default=0,
        ge=0,
        description="Input tokens processed normally without upstream cache hit",
    )
    output_tokens: int = Field(
        default=0,
        ge=0,
        description="Completion / output tokens generated by the provider",
    )
    provider_reported_total: int | None = Field(
        default=None,
        description="Authoritative total tokens reported by upstream provider usage API (if returned)",
    )

    # 2. Separated Cost Metrics (Phase 05 Section 1)
    baseline_cost_usd: float = Field(
        ...,
        ge=0.0,
        description="Baseline cost if unoptimized prompt & requested model were processed with zero cache",
    )
    estimated_cost_usd: float = Field(
        ...,
        ge=0.0,
        description="Planning cost estimate computed before or without provider usage",
    )
    actual_billed_cost_usd: float | None = Field(
        default=None,
        ge=0.0,
        description="Authoritative billed cost incurred from provider-reported usage",
    )
    effective_cost_usd: float = Field(
        ...,
        ge=0.0,
        description="Effective cost: actual_billed_cost_usd if available, else estimated_cost_usd",
    )
    total_savings_usd: float = Field(
        default=0.0,
        ge=0.0,
        description="Total cost saved: max(0.0, baseline_cost_usd - effective_cost_usd)",
    )
    savings_percentage: float = Field(
        default=0.0,
        ge=0.0,
        le=100.0,
        description="Percentage of cost saved relative to baseline cost",
    )

    # 3. Attribution & Reconciliation (Phase 05 Section 3 & 4)
    savings_attribution: SavingsAttribution = Field(default_factory=SavingsAttribution)
    reconciliation_status: ReconciliationStatus = Field(
        default=ReconciliationStatus.ESTIMATED
    )
    variance_tokens: int | None = Field(
        default=None,
        description="Variance between provider reported total and local estimate: provider - local",
    )
    variance_cost_usd: float | None = Field(
        default=None,
        description="Variance between actual billed cost and estimated cost: actual - estimated",
    )

    # 4. Context & Safe Metadata (Zero secret leakage)
    is_cache_hit: bool = Field(
        default=False,
        description="True if JakeAI Tier 1 or Tier 2 response cache hit occurred",
    )
    cache_type: str = Field(default="none", description="'none', 'exact', 'semantic'")
    metadata: dict[str, Any] = Field(
        default_factory=dict,
        description="Sanitized contextual metadata (workload type, route tags)",
    )


class TenantBudget(BaseModel):
    """Tenant token quota and dollar budget status."""

    tenant_id: str
    period: str = Field(..., description="Billing period formatted as YYYY-MM")
    token_quota: int = Field(
        default=1_000_000,
        ge=1,
        description="Monthly allocated token quota limit",
    )
    tokens_used: int = Field(
        default=0,
        ge=0,
        description="Authoritative tokens consumed in active period",
    )
    tokens_remaining: int = Field(
        default=1_000_000,
        ge=0,
        description="Remaining token quota: max(0, token_quota - tokens_used)",
    )
    percentage_tokens_used: float = Field(
        default=0.0,
        ge=0.0,
        description="Percentage of token quota consumed",
    )
    dollar_budget_usd: float | None = Field(
        default=None,
        ge=0.0,
        description="Optional monthly dollar budget ceiling in USD",
    )
    dollar_spent_usd: float = Field(
        default=0.0,
        ge=0.0,
        description="Total actual USD expenditure incurred in active period",
    )
    dollar_remaining_usd: float | None = Field(
        default=None,
        description="Remaining USD budget: max(0.0, dollar_budget_usd - dollar_spent_usd)",
    )
    percentage_dollars_used: float | None = Field(
        default=None,
        description="Percentage of dollar budget consumed (if configured)",
    )
    warning_threshold: float = Field(
        default=0.80,
        ge=0.1,
        le=0.99,
        description="Soft alert threshold ratio (default: 0.80 = 80%)",
    )
    is_suspended: bool = Field(
        default=False,
        description="True if token quota or dollar budget is exhausted (>= 100%)",
    )
    warning: str | None = Field(
        default=None,
        description="Actionable warning message if nearing or exceeding budget limits",
    )


class UpdateBudgetRequest(BaseModel):
    """Payload to configure tenant budget and quotas."""

    token_quota: int | None = Field(
        default=None,
        ge=10_000,
        description="New monthly token quota limit",
    )
    dollar_budget_usd: float | None = Field(
        default=None,
        ge=1.0,
        description="New monthly dollar budget limit in USD (or None to unset)",
    )
    warning_threshold: float | None = Field(
        default=None,
        ge=0.1,
        le=0.99,
        description="Soft warning threshold ratio (e.g. 0.8 for 80%)",
    )


class FinOpsSummary(BaseModel):
    """Aggregated FinOps analytics and cost efficiency summary for a tenant."""

    tenant_id: str
    period: str
    total_requests: int
    reconciled_requests: int
    reconciliation_rate: float = Field(
        ...,
        description="Percentage of requests with authoritative provider reconciliation",
    )
    total_raw_tokens: int
    total_optimized_tokens: int
    total_physical_tokens_removed: int
    total_cached_tokens: int
    total_uncached_tokens: int
    total_output_tokens: int
    total_baseline_cost_usd: float
    total_actual_cost_usd: float
    total_savings_usd: float
    overall_savings_percentage: float
    savings_attribution: SavingsAttribution
    budget_status: TenantBudget


class ReconciliationReport(BaseModel):
    """Telemetry report comparing local planning estimates with authoritative provider truth."""

    tenant_id: str
    period: str
    total_reconciled: int
    total_estimated_only: int
    net_token_variance: int = Field(
        ...,
        description="Net tokens delta: sum(provider_reported - estimated_local)",
    )
    net_cost_variance_usd: float = Field(
        ...,
        description="Net cost delta: sum(actual_billed - estimated_cost)",
    )
    avg_token_variance_pct: float = Field(
        ...,
        description="Average percentage variance between estimates and authoritative usage",
    )
    anomalous_requests_count: int = Field(
        default=0,
        description="Number of requests where variance exceeded 25%",
    )
