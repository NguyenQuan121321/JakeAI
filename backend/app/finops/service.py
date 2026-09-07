"""Unified FinOps Service Facade for Phase 05.

Coordinating:
- Billing Truth Reconciler
- Non-overlapping Cost Attribution
- Multi-tenant Transaction Ledger
- Token Quota & USD Budget Governance
"""

from __future__ import annotations

import logging
from typing import Any

from app.finops.attribution import compute_savings_attribution
from app.finops.budget import FinOpsBudgetManager, get_budget_manager
from app.finops.ledger import FinOpsLedger, get_finops_ledger
from app.finops.models import (
    FinOpsRecord,
    FinOpsSummary,
    ReconciliationReport,
    ReconciliationStatus,
    TenantBudget,
)
from app.finops.pricing import (
    calculate_baseline_cost,
    get_pricing,
)
from app.finops.reconciler import BillingReconciler

logger = logging.getLogger(__name__)


class FinOpsService:
    """Enterprise FinOps coordinator providing complete cost and token truth."""

    def __init__(
        self,
        ledger: FinOpsLedger | None = None,
        budget_mgr: FinOpsBudgetManager | None = None,
        reconciler: BillingReconciler | None = None,
    ) -> None:
        self.ledger = ledger or get_finops_ledger()
        self.budget_mgr = budget_mgr or get_budget_manager()
        self.reconciler = reconciler or BillingReconciler()

    async def check_budget(
        self,
        tenant_id: str,
        estimated_tokens: int = 100,
        estimated_cost_usd: float = 0.0,
    ) -> tuple[bool, str | None]:
        """Pre-flight budget check before running inference."""
        return await self.budget_mgr.check_budget(
            tenant_id=tenant_id,
            estimated_tokens=estimated_tokens,
            estimated_cost_usd=estimated_cost_usd,
        )

    async def record_cache_hit(
        self,
        request_id: str,
        tenant_id: str,
        model: str,
        raw_tokens: int,
        output_tokens: int = 50,
        cache_type: str = "exact",
        metadata: dict[str, Any] | None = None,
    ) -> FinOpsRecord:
        """Record zero-cost response cache hit (Tier 1 Redis or Tier 2 Qdrant)."""
        baseline_cost = calculate_baseline_cost(
            model=model,
            raw_input_tokens=raw_tokens,
            output_tokens=output_tokens,
        )

        attribution = compute_savings_attribution(
            model=model,
            raw_tokens=raw_tokens,
            optimized_tokens=0,
            output_tokens=output_tokens,
            is_cache_hit=True,
        )

        record = FinOpsRecord(
            request_id=request_id,
            tenant_id=tenant_id,
            provider="jakeai_cache",
            model=model,
            estimated_local_tokens=raw_tokens + output_tokens,
            raw_tokens=raw_tokens,
            optimized_tokens=0,
            physical_tokens_removed=raw_tokens,
            cached_tokens=raw_tokens,
            uncached_tokens=0,
            output_tokens=output_tokens,
            provider_reported_total=0,
            baseline_cost_usd=baseline_cost,
            estimated_cost_usd=0.0,
            actual_billed_cost_usd=0.0,
            effective_cost_usd=0.0,
            total_savings_usd=baseline_cost,
            savings_percentage=100.0,
            savings_attribution=attribution,
            reconciliation_status=ReconciliationStatus.AUTHORITATIVE,
            variance_tokens=-(raw_tokens + output_tokens),
            variance_cost_usd=-baseline_cost,
            is_cache_hit=True,
            cache_type=cache_type,
            metadata=metadata or {},
        )

        self.ledger.record(record)
        return record

    async def record_upstream_inference(
        self,
        request_id: str,
        tenant_id: str,
        provider: str,
        model: str,
        raw_tokens: int,
        optimized_tokens: int,
        output_tokens: int,
        provider_usage: dict[str, Any] | None = None,
        requested_model: str | None = None,
        provider_cached_tokens: int = 0,
        provider_cache_write_tokens: int = 0,
        avoided_retries_cost_usd: float = 0.0,
        metadata: dict[str, Any] | None = None,
    ) -> FinOpsRecord:
        """Record upstream LLM inference with authoritative reconciliation and non-overlapping attribution."""
        pricing = get_pricing(model)
        requested = requested_model or model

        # 1. Baseline cost (unoptimized input + requested model rates)
        baseline_cost = calculate_baseline_cost(
            model=requested,
            raw_input_tokens=raw_tokens,
            output_tokens=output_tokens,
        )

        # 2. Local Planning Cost Estimate
        estimated_local_tokens = raw_tokens + output_tokens
        uncached_opt = max(0, optimized_tokens - provider_cached_tokens)
        estimated_cost = (
            (uncached_opt * pricing.input_per_million)
            + (provider_cached_tokens * pricing.cache_read_per_million)
            + (provider_cache_write_tokens * pricing.cache_write_per_million)
            + (output_tokens * pricing.output_per_million)
        ) / 1_000_000.0
        estimated_cost = round(max(0.0, estimated_cost), 6)

        # 3. Authoritative Billing Reconciliation
        rec_result = self.reconciler.reconcile(
            model=model,
            estimated_local_tokens=estimated_local_tokens,
            estimated_cost_usd=estimated_cost,
            provider_usage=provider_usage,
            cached_tokens=provider_cached_tokens,
            cache_write_tokens=provider_cache_write_tokens,
        )

        effective_cost = (
            rec_result.actual_billed_cost_usd
            if rec_result.is_authoritative
            and rec_result.actual_billed_cost_usd is not None
            else estimated_cost
        )

        total_savings = round(max(0.0, baseline_cost - effective_cost), 6)
        savings_pct = (
            round((total_savings / baseline_cost * 100.0), 2)
            if baseline_cost > 0.0
            else 0.0
        )

        # 4. Strict Non-Overlapping Attribution
        attribution = compute_savings_attribution(
            model=model,
            raw_tokens=raw_tokens,
            optimized_tokens=optimized_tokens,
            output_tokens=output_tokens,
            is_cache_hit=False,
            provider_cached_tokens=provider_cached_tokens,
            provider_cache_write_tokens=provider_cache_write_tokens,
            requested_model=requested_model,
            avoided_retries_cost_usd=avoided_retries_cost_usd,
        )

        # 5. Build Final Accounting Record
        tokens_pruned = max(0, raw_tokens - optimized_tokens)
        record = FinOpsRecord(
            request_id=request_id,
            tenant_id=tenant_id,
            provider=provider,
            model=model,
            requested_model=requested_model,
            estimated_local_tokens=estimated_local_tokens,
            raw_tokens=raw_tokens,
            optimized_tokens=optimized_tokens,
            physical_tokens_removed=tokens_pruned,
            cached_tokens=provider_cached_tokens,
            uncached_tokens=max(0, optimized_tokens - provider_cached_tokens),
            output_tokens=output_tokens,
            provider_reported_total=rec_result.provider_reported_total,
            baseline_cost_usd=baseline_cost,
            estimated_cost_usd=estimated_cost,
            actual_billed_cost_usd=rec_result.actual_billed_cost_usd,
            effective_cost_usd=effective_cost,
            total_savings_usd=total_savings,
            savings_percentage=savings_pct,
            savings_attribution=attribution,
            reconciliation_status=rec_result.status,
            variance_tokens=rec_result.variance_tokens,
            variance_cost_usd=rec_result.variance_cost_usd,
            is_cache_hit=False,
            cache_type="none",
            metadata=metadata or {},
        )

        # 6. Persist to Ledger
        self.ledger.record(record)

        # 7. Settle Budget Atomically
        billed_tokens = (
            rec_result.provider_reported_total
            if rec_result.provider_reported_total is not None
            else (optimized_tokens + output_tokens)
        )
        await self.budget_mgr.settle_request(
            tenant_id=tenant_id,
            billed_tokens=billed_tokens,
            billed_cost_usd=effective_cost,
        )

        return record

    async def get_summary(
        self, tenant_id: str, period: str | None = None
    ) -> FinOpsSummary:
        """Retrieve aggregated summary for a tenant."""
        return await self.ledger.get_summary(tenant_id, period)

    def get_transactions(
        self,
        tenant_id: str,
        period: str | None = None,
        limit: int = 50,
        offset: int = 0,
    ) -> list[FinOpsRecord]:
        """Retrieve paginated per-request accounting records."""
        return self.ledger.get_records(
            tenant_id=tenant_id, period=period, limit=limit, offset=offset
        )

    async def get_budget(self, tenant_id: str) -> TenantBudget:
        """Retrieve current budget and quota status."""
        return await self.budget_mgr.get_budget_status(tenant_id)

    async def set_budget(
        self,
        tenant_id: str,
        token_quota: int | None = None,
        dollar_budget_usd: float | None = None,
        warning_threshold: float | None = None,
    ) -> TenantBudget:
        """Configure budget limits for tenant."""
        return await self.budget_mgr.set_budget(
            tenant_id=tenant_id,
            token_quota=token_quota,
            dollar_budget_usd=dollar_budget_usd,
            warning_threshold=warning_threshold,
        )

    def get_reconciliation_report(
        self, tenant_id: str, period: str | None = None
    ) -> ReconciliationReport:
        """Retrieve variance and anomaly reconciliation report."""
        return self.ledger.get_reconciliation_report(tenant_id, period)


_finops_service: FinOpsService | None = None


def get_finops_service() -> FinOpsService:
    """Singleton getter for FinOpsService."""
    global _finops_service
    if _finops_service is None:
        _finops_service = FinOpsService()
    return _finops_service
