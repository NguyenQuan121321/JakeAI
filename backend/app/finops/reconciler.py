"""Billing Truth Reconciler for Phase 05 AI FinOps.

Reconciles local planning estimates with authoritative provider-reported usage:
- When provider returns usage metrics, provider usage becomes the sole authoritative source.
- Local estimates remain retained as planning metrics.
- Computes token variance (provider - local) and dollar cost variance.
- Detects billing anomalies where variance exceeds allowable tolerance (e.g. 25%).
"""

from __future__ import annotations

from typing import Any

from pydantic import BaseModel, Field

from app.finops.models import ReconciliationStatus
from app.finops.pricing import calculate_billed_cost


class ReconciliationResult(BaseModel):
    """Result of reconciling a transaction against upstream provider reports."""

    status: ReconciliationStatus
    is_authoritative: bool
    provider_reported_total: int | None = None
    actual_billed_cost_usd: float | None = None
    variance_tokens: int | None = None
    variance_cost_usd: float | None = None
    variance_percentage: float = 0.0
    is_anomalous: bool = False
    details: dict[str, Any] = Field(default_factory=dict)


class BillingReconciler:
    """Authoritative reconciliation engine for LLM inference requests."""

    def __init__(self, anomaly_threshold_pct: float = 25.0) -> None:
        self.anomaly_threshold_pct = anomaly_threshold_pct

    def reconcile(
        self,
        model: str,
        estimated_local_tokens: int,
        estimated_cost_usd: float,
        provider_usage: dict[str, Any] | None,
        cached_tokens: int = 0,
        cache_write_tokens: int = 0,
    ) -> ReconciliationResult:
        """Reconcile local planning estimates with provider-reported usage.

        If provider_usage is provided and contains valid token counts:
          - Reconciled as AUTHORITATIVE billing truth.
          - Calculates exact billed cost using provider pricing rates.
          - Computes delta against local estimate.
        If provider_usage is None or empty:
          - Remains ESTIMATED planning record.
        """
        if not provider_usage:
            return ReconciliationResult(
                status=ReconciliationStatus.ESTIMATED,
                is_authoritative=False,
                provider_reported_total=None,
                actual_billed_cost_usd=None,
                variance_tokens=0,
                variance_cost_usd=0.0,
                variance_percentage=0.0,
                is_anomalous=False,
                details={"reason": "No upstream provider usage telemetry returned"},
            )

        # Extract tokens from provider usage object
        prompt_tokens = int(
            provider_usage.get("prompt_tokens")
            or provider_usage.get("input_tokens")
            or provider_usage.get("uncached_tokens")
            or 0
        )
        completion_tokens = int(
            provider_usage.get("completion_tokens")
            or provider_usage.get("output_tokens")
            or 0
        )
        total_tokens = int(
            provider_usage.get("total_tokens") or (prompt_tokens + completion_tokens)
        )

        prov_cached = int(
            provider_usage.get("cached_tokens")
            or provider_usage.get("cached_prompt_tokens")
            or cached_tokens
        )
        prov_write = int(
            provider_usage.get("cache_write_tokens")
            or provider_usage.get("cache_creation_input_tokens")
            or cache_write_tokens
        )

        # Calculate authoritative billed cost
        uncached_input = max(0, prompt_tokens - prov_cached)
        actual_billed_cost = calculate_billed_cost(
            model=model,
            uncached_input_tokens=uncached_input,
            cached_input_tokens=prov_cached,
            cache_write_tokens=prov_write,
            output_tokens=completion_tokens,
        )

        # Variance calculations
        variance_tokens = total_tokens - estimated_local_tokens
        variance_cost = round(actual_billed_cost - estimated_cost_usd, 6)

        base_tokens = max(1, estimated_local_tokens)
        variance_pct = round(abs(variance_tokens) / base_tokens * 100.0, 2)
        is_anomalous = variance_pct > self.anomaly_threshold_pct

        return ReconciliationResult(
            status=ReconciliationStatus.AUTHORITATIVE,
            is_authoritative=True,
            provider_reported_total=total_tokens,
            actual_billed_cost_usd=actual_billed_cost,
            variance_tokens=variance_tokens,
            variance_cost_usd=variance_cost,
            variance_percentage=variance_pct,
            is_anomalous=is_anomalous,
            details={
                "provider_prompt_tokens": prompt_tokens,
                "provider_completion_tokens": completion_tokens,
                "provider_cached_tokens": prov_cached,
                "provider_write_tokens": prov_write,
            },
        )
