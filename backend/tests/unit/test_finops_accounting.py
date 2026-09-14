"""Unit and Integration Tests for Phase 05 AI FinOps & Cost Truth.

Validates:
1. Separate Metrics: Never collapsing estimated tokens, physical removed tokens,
   provider cached tokens, provider uncached tokens, output tokens, provider reported total,
   actual billed cost, and estimated cost.
2. Accounting Model: Per-request ledger record consistency.
3. Billing Truth: Upstream provider reported usage is authoritative reconciliation source.
4. Cost Attribution: Strict non-overlapping separation of savings (no double counting).
5. Budget & Quota Governance: Soft warning (80%) and hard suspension (100%), token & USD limits.
6. Multi-Tenant Boundary Isolation: Strict partition preventing cross-tenant leakage.
7. Zero Secret Leakage: Sensitive keys/tokens scrubbed from records and logs.
"""

import pytest

from app.finops.attribution import compute_savings_attribution
from app.finops.budget import FinOpsBudgetManager
from app.finops.ledger import FinOpsLedger
from app.finops.models import (
    FinOpsRecord,
    ReconciliationStatus,
    SavingsAttribution,
)
from app.finops.pricing import (
    calculate_baseline_cost,
    calculate_billed_cost,
    calculate_model_routing_savings,
    calculate_provider_cache_savings,
    get_pricing,
)
from app.finops.reconciler import BillingReconciler
from app.finops.service import FinOpsService


def test_finops_pricing_matrix():
    """Verify official pricing definitions across providers."""
    claude_pricing = get_pricing("claude-3-5-sonnet")
    assert claude_pricing.provider == "anthropic"
    assert claude_pricing.input_per_million == 3.00
    assert claude_pricing.cache_read_per_million == 0.30  # 90% discount
    assert claude_pricing.cache_write_per_million == 3.75  # 1.25x surcharge
    assert claude_pricing.output_per_million == 15.00

    gpt4o_pricing = get_pricing("gpt-4o")
    assert gpt4o_pricing.provider == "openai"
    assert gpt4o_pricing.input_per_million == 2.50
    assert gpt4o_pricing.cache_read_per_million == 1.25  # 50% discount

    gemini_pricing = get_pricing("gemini-1.5-flash")
    assert gemini_pricing.provider == "gemini"
    assert gemini_pricing.input_per_million == 0.075

    deepseek_pricing = get_pricing("deepseek-chat")
    assert deepseek_pricing.provider == "deepseek"
    assert deepseek_pricing.cache_read_per_million == 0.014


def test_baseline_and_billed_cost_calculation():
    """Verify baseline and actual billed cost formulas."""
    # Baseline: 10,000 raw prompt + 2,000 completion on gpt-4o ($2.50 in, $10.00 out)
    # in: 10000 * 2.50 / 1M = 0.0250, out: 2000 * 10.0 / 1M = 0.0200 -> total = 0.0450
    base_cost = calculate_baseline_cost(
        "gpt-4o", raw_input_tokens=10_000, output_tokens=2_000
    )
    assert base_cost == 0.045

    # Actual Billed: 4,000 uncached ($2.50) + 6,000 cached ($1.25) + 2,000 output ($10.00)
    # uncached in: 4000 * 2.50 / 1M = 0.0100
    # cached in: 6000 * 1.25 / 1M = 0.0075
    # output: 2000 * 10.0 / 1M = 0.0200
    # total = 0.0375
    billed_cost = calculate_billed_cost(
        "gpt-4o",
        uncached_input_tokens=4_000,
        cached_input_tokens=6_000,
        cache_write_tokens=0,
        output_tokens=2_000,
    )
    assert billed_cost == 0.0375


def test_provider_cache_savings_calculation():
    """Verify provider prompt caching net discount."""
    # Anthropic Claude-3-5-Sonnet: 100,000 cached read tokens ($3.00 standard -> $0.30 cached read)
    # gross saved = 100,000 * (3.00 - 0.30) / 1M = 0.2700 USD
    savings = calculate_provider_cache_savings(
        "claude-3-5-sonnet", cached_input_tokens=100_000
    )
    assert savings == 0.27

    # With write surcharge: 10,000 write creation tokens ($3.75 write vs $3.00 standard = 0.75 surcharge)
    # surcharge = 10,000 * 0.75 / 1M = 0.0075 USD
    # net saved = 0.2700 - 0.0075 = 0.2625 USD
    net_savings = calculate_provider_cache_savings(
        "claude-3-5-sonnet", cached_input_tokens=100_000, cache_write_tokens=10_000
    )
    assert net_savings == 0.2625


def test_model_routing_savings():
    """Verify intelligent routing cost delta."""
    # Requested gpt-4o ($2.50 / $10.00), routed to gpt-4o-mini ($0.15 / $0.60)
    # 50,000 input, 5,000 output
    # req cost: (50000 * 2.5 + 5000 * 10) / 1M = 0.125 + 0.050 = 0.175
    # sel cost: (50000 * 0.15 + 5000 * 0.6) / 1M = 0.0075 + 0.0030 = 0.0105
    # savings: 0.175 - 0.0105 = 0.1645 USD
    saved = calculate_model_routing_savings(
        requested_model="gpt-4o",
        selected_model="gpt-4o-mini",
        input_tokens=50_000,
        output_tokens=5_000,
    )
    assert saved == 0.1645


def test_separate_metrics_never_collapsed():
    """Phase 05 Section 1 Mandate: All 8 metrics must be distinct and non-collapsed."""
    record = FinOpsRecord(
        request_id="req-metric-001",
        tenant_id="tenant-alpha",
        provider="openai",
        model="gpt-4o",
        estimated_local_tokens=1200,
        raw_tokens=1000,
        optimized_tokens=600,
        physical_tokens_removed=400,
        cached_tokens=200,
        uncached_tokens=400,
        output_tokens=250,
        provider_reported_total=850,
        baseline_cost_usd=0.005,
        estimated_cost_usd=0.0035,
        actual_billed_cost_usd=0.00325,
        effective_cost_usd=0.00325,
        total_savings_usd=0.00175,
        savings_percentage=35.0,
    )

    # 1. Verify estimated local tokens vs provider reported total are separate
    assert record.estimated_local_tokens == 1200
    assert record.provider_reported_total == 850
    assert record.estimated_local_tokens != record.provider_reported_total

    # 2. Verify physical tokens removed vs provider cached tokens are separate
    assert record.physical_tokens_removed == 400
    assert record.cached_tokens == 200
    assert record.physical_tokens_removed != record.cached_tokens

    # 3. Verify provider uncached vs output tokens are separate
    assert record.uncached_tokens == 400
    assert record.output_tokens == 250
    assert record.uncached_tokens != record.output_tokens

    # 4. Verify actual billed cost vs estimated cost are separate
    assert record.actual_billed_cost_usd == 0.00325
    assert record.estimated_cost_usd == 0.0035
    assert record.actual_billed_cost_usd != record.estimated_cost_usd


def test_non_overlapping_savings_attribution_cache_hit():
    """Verify that JakeAI response cache hit attributes 100% to cache_hit_usd with zero double-counting."""
    attr = compute_savings_attribution(
        model="gpt-4o",
        raw_tokens=5000,
        optimized_tokens=0,
        output_tokens=500,
        is_cache_hit=True,
    )

    assert attr.cache_hit_usd > 0.0
    assert attr.physical_reduction_usd == 0.0
    assert attr.provider_cache_usd == 0.0
    assert attr.model_routing_usd == 0.0
    assert attr.avoided_retries_usd == 0.0
    assert attr.total_savings_usd == attr.cache_hit_usd


def test_non_overlapping_savings_attribution_cache_miss():
    """Verify cache miss partitions physical reduction, provider prompt cache, and model routing."""
    # Model: gpt-4o-mini (selected) vs gpt-4o (requested)
    # raw: 10,000, opt: 6,000, provider_cached: 4,000, output: 1,000
    attr = compute_savings_attribution(
        model="gpt-4o-mini",
        raw_tokens=10_000,
        optimized_tokens=6_000,
        output_tokens=1_000,
        is_cache_hit=False,
        provider_cached_tokens=4_000,
        requested_model="gpt-4o",
    )

    assert attr.cache_hit_usd == 0.0
    assert attr.model_routing_usd > 0.0
    assert attr.physical_reduction_usd > 0.0
    assert attr.provider_cache_usd > 0.0

    # Mathematical identity check: total == sum of individual categories
    expected_sum = round(
        attr.model_routing_usd
        + attr.physical_reduction_usd
        + attr.provider_cache_usd
        + attr.avoided_retries_usd,
        6,
    )
    assert attr.total_savings_usd == expected_sum


def test_savings_attribution_validator_consistency():
    """Pydantic model validator ensures total_savings_usd is consistent."""
    attr = SavingsAttribution(
        cache_hit_usd=0.015,
        physical_reduction_usd=0.0,
        provider_cache_usd=0.0,
        model_routing_usd=0.0,
        avoided_retries_usd=0.0,
    )
    assert attr.total_savings_usd == 0.015


def test_billing_truth_reconciliation_with_provider_usage():
    """Phase 05 Section 3: Provider-reported usage is authoritative reconciliation source."""
    reconciler = BillingReconciler(anomaly_threshold_pct=25.0)

    provider_usage = {
        "prompt_tokens": 1200,
        "completion_tokens": 300,
        "total_tokens": 1500,
        "cached_tokens": 500,
    }

    result = reconciler.reconcile(
        model="gpt-4o",
        estimated_local_tokens=1400,
        estimated_cost_usd=0.005,
        provider_usage=provider_usage,
    )

    assert result.status == ReconciliationStatus.AUTHORITATIVE
    assert result.is_authoritative is True
    assert result.provider_reported_total == 1500
    assert result.actual_billed_cost_usd is not None
    # variance = 1500 - 1400 = 100 tokens
    assert result.variance_tokens == 100
    assert result.is_anomalous is False


def test_billing_truth_reconciliation_anomaly_detection():
    """Detect billing anomaly when provider bills significantly higher than local estimate (>25%)."""
    reconciler = BillingReconciler(anomaly_threshold_pct=25.0)

    # Provider reports 2,000 tokens when local estimated 1,000 (100% variance)
    provider_usage = {
        "prompt_tokens": 1800,
        "completion_tokens": 200,
        "total_tokens": 2000,
    }

    result = reconciler.reconcile(
        model="gpt-4o",
        estimated_local_tokens=1000,
        estimated_cost_usd=0.004,
        provider_usage=provider_usage,
    )

    assert result.status == ReconciliationStatus.AUTHORITATIVE
    assert result.variance_tokens == 1000
    assert result.variance_percentage == 100.0
    assert result.is_anomalous is True


def test_billing_truth_reconciliation_offline_fallback():
    """When provider usage is not available, status remains ESTIMATED."""
    reconciler = BillingReconciler()

    result = reconciler.reconcile(
        model="gemini-1.5-flash",
        estimated_local_tokens=500,
        estimated_cost_usd=0.0001,
        provider_usage=None,
    )

    assert result.status == ReconciliationStatus.ESTIMATED
    assert result.is_authoritative is False
    assert result.provider_reported_total is None
    assert result.actual_billed_cost_usd is None


@pytest.mark.asyncio
async def test_finops_budget_manager_soft_warning_and_hard_suspension():
    """Phase 05 Section 5: Verify quota warnings (80%) and hard suspension (100%)."""
    mgr = FinOpsBudgetManager()
    tenant_id = "tenant-budget-test-01"

    # Set quota = 10,000 tokens and $0.05 budget
    await mgr.set_budget(
        tenant_id=tenant_id,
        token_quota=10_000,
        dollar_budget_usd=0.05,
        warning_threshold=0.80,
    )

    # 1. Initial State: Normal
    allowed, warn = await mgr.check_budget(tenant_id, estimated_tokens=100)
    assert allowed is True
    assert warn is None

    # 2. Settle 8,200 tokens (82% of quota -> soft warning)
    await mgr.settle_request(tenant_id, billed_tokens=8200, billed_cost_usd=0.02)
    allowed, warn = await mgr.check_budget(tenant_id, estimated_tokens=100)
    assert allowed is True
    assert warn is not None
    assert "82.0%" in warn

    # 3. Settle another 1,900 tokens (total 10,100 tokens -> 101% quota exceeded)
    await mgr.settle_request(tenant_id, billed_tokens=1900, billed_cost_usd=0.01)
    allowed, err = await mgr.check_budget(tenant_id, estimated_tokens=100)
    assert allowed is False
    assert "exceeded" in err.lower()

    # 4. Status inspection
    status = await mgr.get_budget_status(tenant_id)
    assert status.is_suspended is True
    assert status.tokens_used == 10_100
    assert status.tokens_remaining == 0


@pytest.mark.asyncio
async def test_finops_budget_manager_dollar_budget_suspension():
    """Verify hard suspension triggers if dollar budget is exceeded before token quota."""
    mgr = FinOpsBudgetManager()
    tenant_id = "tenant-dollar-budget-02"

    # Large token quota (1M), small dollar budget ($0.01)
    await mgr.set_budget(
        tenant_id=tenant_id,
        token_quota=1_000_000,
        dollar_budget_usd=0.01,
        warning_threshold=0.80,
    )

    # Settle $0.012 cost on 200 tokens
    await mgr.settle_request(tenant_id, billed_tokens=200, billed_cost_usd=0.012)
    allowed, err = await mgr.check_budget(tenant_id, estimated_tokens=100)
    assert allowed is False
    assert "dollar budget exceeded" in err.lower()

    status = await mgr.get_budget_status(tenant_id)
    assert status.is_suspended is True
    assert status.dollar_spent_usd == 0.012


@pytest.mark.asyncio
async def test_finops_service_end_to_end_lifecycle():
    """Verify end-to-end recording of cache hit and upstream call with FinOpsService."""
    ledger = FinOpsLedger()
    budget_mgr = FinOpsBudgetManager()
    svc = FinOpsService(ledger=ledger, budget_mgr=budget_mgr)
    tenant_id = "tenant-finops-lifecycle"

    await svc.set_budget(tenant_id, token_quota=100_000)

    # 1. Record Upstream Inference
    provider_usage = {
        "prompt_tokens": 1500,
        "completion_tokens": 200,
        "total_tokens": 1700,
        "cached_tokens": 500,
    }
    rec1 = await svc.record_upstream_inference(
        request_id="req-upstream-01",
        tenant_id=tenant_id,
        provider="anthropic",
        model="claude-3-5-sonnet",
        raw_tokens=2000,
        optimized_tokens=1500,
        output_tokens=200,
        provider_usage=provider_usage,
        provider_cached_tokens=500,
    )

    assert rec1.request_id == "req-upstream-01"
    assert rec1.reconciliation_status == ReconciliationStatus.AUTHORITATIVE
    assert rec1.physical_tokens_removed == 500
    assert rec1.total_savings_usd > 0.0
    assert rec1.savings_attribution.physical_reduction_usd > 0.0
    assert rec1.savings_attribution.provider_cache_usd > 0.0

    # 2. Record Cache Hit
    rec2 = await svc.record_cache_hit(
        request_id="req-cache-02",
        tenant_id=tenant_id,
        model="claude-3-5-sonnet",
        raw_tokens=2000,
        output_tokens=200,
        cache_type="exact",
    )
    assert rec2.is_cache_hit is True
    assert rec2.savings_percentage == 100.0
    assert rec2.effective_cost_usd == 0.0
    assert rec2.savings_attribution.cache_hit_usd == rec2.total_savings_usd

    # 3. Retrieve Summary
    summary = await svc.get_summary(tenant_id)
    assert summary.total_requests == 2
    assert summary.reconciled_requests == 2
    assert summary.reconciliation_rate == 100.0
    assert summary.total_savings_usd > 0.0
    assert summary.savings_attribution.cache_hit_usd > 0.0
    assert summary.savings_attribution.physical_reduction_usd > 0.0

    # 4. Reconciliation Report
    report = svc.get_reconciliation_report(tenant_id)
    assert report.total_reconciled == 2
    assert report.total_estimated_only == 0


@pytest.mark.asyncio
async def test_finops_ledger_multi_tenant_isolation():
    """Negative proof test: Multi-tenant boundary isolation ensures cross-tenant data leakage is impossible."""
    ledger = FinOpsLedger()
    budget_mgr = FinOpsBudgetManager()
    svc = FinOpsService(ledger=ledger, budget_mgr=budget_mgr)

    tenant_a = "tenant-bank-a"
    tenant_b = "tenant-retail-b"

    await svc.record_upstream_inference(
        request_id="req-a-01",
        tenant_id=tenant_a,
        provider="openai",
        model="gpt-4o",
        raw_tokens=1000,
        optimized_tokens=800,
        output_tokens=100,
    )

    await svc.record_upstream_inference(
        request_id="req-b-01",
        tenant_id=tenant_b,
        provider="gemini",
        model="gemini-1.5-pro",
        raw_tokens=3000,
        optimized_tokens=2000,
        output_tokens=500,
    )

    # Tenant A must ONLY see Tenant A's transactions and summary
    records_a = svc.get_transactions(tenant_a)
    assert len(records_a) == 1
    assert records_a[0].request_id == "req-a-01"
    assert records_a[0].tenant_id == tenant_a

    summary_a = await svc.get_summary(tenant_a)
    assert summary_a.total_requests == 1
    assert summary_a.total_raw_tokens == 1000

    # Tenant B must ONLY see Tenant B's transactions and summary
    records_b = svc.get_transactions(tenant_b)
    assert len(records_b) == 1
    assert records_b[0].request_id == "req-b-01"
    assert records_b[0].tenant_id == tenant_b

    summary_b = await svc.get_summary(tenant_b)
    assert summary_b.total_requests == 1
    assert summary_b.total_raw_tokens == 3000


@pytest.mark.asyncio
async def test_finops_ledger_zero_secret_leakage():
    """Validate that API keys, auth tokens, and Bearer headers are scrubbed from FinOps records."""
    ledger = FinOpsLedger()
    budget_mgr = FinOpsBudgetManager()
    svc = FinOpsService(ledger=ledger, budget_mgr=budget_mgr)
    tenant_id = "tenant-secret-scrub"

    meta_with_secrets = {
        "workload": "rag",
        "api_key": "sk-proj-supersecretkey12345",
        "Authorization": "Bearer eyJhbGciOiJIUzI1NiIsInR5cCI6IkpXVCJ9...",
        "user_token": "token-xyz-secret",
        "route_tier": "fast",
    }

    record = await svc.record_upstream_inference(
        request_id="req-scrub-01",
        tenant_id=tenant_id,
        provider="openai",
        model="gpt-4o",
        raw_tokens=500,
        optimized_tokens=400,
        output_tokens=50,
        metadata=meta_with_secrets,
    )
    assert record.request_id == "req-scrub-01"

    stored_records = svc.get_transactions(tenant_id)
    assert len(stored_records) == 1
    stored_meta = stored_records[0].metadata

    assert "workload" in stored_meta
    assert "route_tier" in stored_meta
    assert "api_key" not in stored_meta
    assert "Authorization" not in stored_meta
    assert "user_token" not in stored_meta


def test_finops_ledger_bounded_ring_buffer_eviction():
    """Verify bounded ring-buffer evicts oldest records when limit is reached."""
    ledger = FinOpsLedger(max_records_per_tenant=3)
    tenant_id = "tenant-ring-buffer"

    for i in range(5):
        ledger.record(
            FinOpsRecord(
                request_id=f"req-ring-{i}",
                tenant_id=tenant_id,
                provider="openai",
                model="gpt-4o",
                estimated_local_tokens=100,
                raw_tokens=100,
                optimized_tokens=100,
                baseline_cost_usd=0.001,
                estimated_cost_usd=0.001,
                effective_cost_usd=0.001,
            )
        )

    records = ledger.get_records(tenant_id, limit=10)
    assert len(records) == 3
    # Newest first: req-ring-4, req-ring-3, req-ring-2
    assert [r.request_id for r in records] == [
        "req-ring-4",
        "req-ring-3",
        "req-ring-2",
    ]


def test_finops_ledger_period_filter():
    """Verify get_records correctly filters by period (YYYY-MM)."""
    ledger = FinOpsLedger()
    tenant_id = "tenant-period-filter"

    # Record 1: September 2026 (timestamp ~ 1788700000)
    ledger.record(
        FinOpsRecord(
            request_id="req-sep-2026",
            tenant_id=tenant_id,
            provider="openai",
            model="gpt-4o",
            timestamp=1788700000.0,
            estimated_local_tokens=100,
            raw_tokens=100,
            optimized_tokens=100,
            baseline_cost_usd=0.001,
            estimated_cost_usd=0.001,
            effective_cost_usd=0.001,
        )
    )

    # Record 2: August 2026 (timestamp ~ 1786000000)
    ledger.record(
        FinOpsRecord(
            request_id="req-aug-2026",
            tenant_id=tenant_id,
            provider="openai",
            model="gpt-4o",
            timestamp=1786000000.0,
            estimated_local_tokens=100,
            raw_tokens=100,
            optimized_tokens=100,
            baseline_cost_usd=0.001,
            estimated_cost_usd=0.001,
            effective_cost_usd=0.001,
        )
    )

    sep_records = ledger.get_records(tenant_id, period="2026-09")
    aug_records = ledger.get_records(tenant_id, period="2026-08")
    jul_records = ledger.get_records(tenant_id, period="2026-07")

    assert len(sep_records) == 1
    assert sep_records[0].request_id == "req-sep-2026"
    assert len(aug_records) == 1
    assert aug_records[0].request_id == "req-aug-2026"
    assert len(jul_records) == 0


def test_model_routing_identical_model_savings_zero():
    """Verify calculate_model_routing_savings returns 0.0 when requested and selected models match."""
    savings = calculate_model_routing_savings(
        requested_model="gpt-4o",
        selected_model="gpt-4o",
        input_tokens=10_000,
        output_tokens=1_000,
    )
    assert savings == 0.0

    savings_case = calculate_model_routing_savings(
        requested_model=" Claude-3-5-Sonnet ",
        selected_model="claude-3-5-sonnet",
        input_tokens=10_000,
        output_tokens=1_000,
    )
    assert savings_case == 0.0


@pytest.mark.asyncio
async def test_finops_service_check_budget_delegation():
    """Verify FinOpsService.check_budget properly delegates to FinOpsBudgetManager."""
    svc = FinOpsService()
    tenant_id = "tenant-svc-check-delegation"

    await svc.set_budget(tenant_id, token_quota=1_000)
    allowed, warn = await svc.check_budget(tenant_id, estimated_tokens=100)
    assert allowed is True
    assert warn is None

    # Exceed limit
    allowed_fail, err = await svc.check_budget(tenant_id, estimated_tokens=2_000)
    assert allowed_fail is False
    assert "exceeded" in err.lower()


@pytest.mark.asyncio
async def test_finops_budget_status_soft_warning_text():
    """Verify get_budget_status sets actionable warning string when approaching budget limit."""
    mgr = FinOpsBudgetManager()
    tenant_id = "tenant-warn-status"

    await mgr.set_budget(tenant_id, token_quota=10_000, warning_threshold=0.80)
    await mgr.settle_request(tenant_id, billed_tokens=8500, billed_cost_usd=0.01)

    status = await mgr.get_budget_status(tenant_id)
    assert status.is_suspended is False
    assert status.percentage_tokens_used == 85.0
    assert status.warning is not None
    assert "Approaching budget limit (>80%)" in status.warning
