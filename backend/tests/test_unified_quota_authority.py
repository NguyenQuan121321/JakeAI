"""Unit tests for TASK COST-05: Unified Quota & Budget Authority.

Verifies zero state divergence between QuotaManager (ai_gateway) and FinOpsBudgetManager (finops).
"""

import pytest

from app.finops.budget import get_budget_manager
from app.services.ai_gateway import QuotaManager, get_quota_manager
from app.services.billing import PayOSBillingService


@pytest.mark.asyncio
async def test_quota_manager_delegates_to_finops_budget_manager() -> None:
    """Verify QuotaManager delegates all reads, updates, and checks to FinOpsBudgetManager."""
    tenant_id = "tenant-unified-quota-test"
    budget_mgr = get_budget_manager()
    quota_mgr = QuotaManager(budget_manager=budget_mgr)

    # 1. Set limit via QuotaManager
    await quota_mgr.set_quota_limit(tenant_id, 2_500_000)

    # FinOpsBudgetManager reflects the exact limit
    assert await budget_mgr.get_token_quota(tenant_id) == 2_500_000
    assert await quota_mgr.get_quota_limit(tenant_id) == 2_500_000

    # 2. Update limit via FinOpsBudgetManager
    await budget_mgr.set_budget(tenant_id, token_quota=7_000_000)
    assert await quota_mgr.get_quota_limit(tenant_id) == 7_000_000

    # 3. Record usage via QuotaManager
    new_used = await quota_mgr.record_usage(
        tenant_id, prompt_tokens=1500, completion_tokens=500
    )
    assert new_used == 2000

    # Both report identical usage
    assert await quota_mgr.get_tokens_used(tenant_id) == 2000
    assert await budget_mgr.get_tokens_used(tenant_id) == 2000

    # 4. Record tokens saved via QuotaManager
    saved = await quota_mgr.record_tokens_saved(tenant_id, tokens_saved=800)
    assert saved == 800
    assert await quota_mgr.get_tokens_saved(tenant_id) == 800
    assert await budget_mgr.get_tokens_saved(tenant_id) == 800

    # 5. Check quota pre-flight evaluation matches
    allowed_q, _msg_q = await quota_mgr.check_quota(tenant_id, estimated_tokens=1000)
    allowed_b, _msg_b = await budget_mgr.check_budget(tenant_id, estimated_tokens=1000)
    assert allowed_q is True
    assert allowed_b is True
    assert allowed_q == allowed_b


@pytest.mark.asyncio
async def test_payos_billing_provisions_unified_budget() -> None:
    """Verify PayOS billing webhook provisions both QuotaManager and FinOpsBudgetManager synchronously."""
    tenant_id = "tenant-payos-sync"
    billing = PayOSBillingService()
    budget_mgr = get_budget_manager()
    quota_mgr = get_quota_manager()

    # Payload for Pro upgrade (5,000,000 quota)
    payload = {
        "orderCode": 888999,
        "amount": 149_000,
        "description": f"JAKEAI {tenant_id} pro upgrade",
    }

    result = await billing.process_payment_webhook({"data": payload})
    assert result["status"] == "success"
    assert result["tier"] == "pro"
    assert result["allocated_quota"] == 5_000_000

    # Verify both authorities report 5,000,000
    assert await budget_mgr.get_token_quota(tenant_id) == 5_000_000
    assert await quota_mgr.get_quota_limit(tenant_id) == 5_000_000


@pytest.mark.asyncio
async def test_unified_quota_suspension_thresholds() -> None:
    """Verify soft warning and hard suspension behave identically."""
    tenant_id = "tenant-suspension-test"
    budget_mgr = get_budget_manager()
    quota_mgr = QuotaManager(budget_manager=budget_mgr)

    # Set quota to 10,000
    await budget_mgr.set_budget(tenant_id, token_quota=10_000)

    # Consume 8,500 tokens (85% > 80% soft warning threshold)
    await quota_mgr.record_usage(tenant_id, 8000, 500)

    allowed, warning = await quota_mgr.check_quota(tenant_id, estimated_tokens=100)
    assert allowed is True
    assert warning is not None
    assert "warning" in warning.lower() or "85" in warning

    # Consume remaining 1,500 tokens (100% hard limit)
    await quota_mgr.record_usage(tenant_id, 1000, 500)

    # Over quota check -> must be suspended
    allowed, err = await quota_mgr.check_quota(tenant_id, estimated_tokens=50)
    assert allowed is False
    assert "exceeded" in err.lower() or "suspended" in err.lower()

    status = await quota_mgr.get_status(tenant_id)
    assert status.is_suspended is True
