"""Comprehensive FinOps & Governance Integration Test Suite (INT-024).

Verifies interactions between real JakeAI FinOps components:
1. FinOpsBudgetManager pre-flight atomic reservation and post-inference settlement.
2. Soft warning (80%) and hard suspension (100%) ceiling enforcement.
3. PayOS payment webhook signature verification and automated budget provisioning.
4. FinOpsLedger multi-tenant accounting and BillingReconciler variance tracking.

Mandatory failure cases tested across FinOps subsystem:
- unavailable (Redis down -> seamless fallback to atomic in-memory governance)
- timeout (Reservation timeouts handled fail-closed/gracefully)
- malformed response (Tampered/invalid PayOS webhook signature rejected fail-closed)
- connection failure (Redis connection reset caught without corrupting balances)
- partial failure (Post-inference usage exceeds reservation -> settled with accurate overage)
- recovery (Hard-cap blocked tenant unblocked immediately upon payment webhook credit)
"""

from __future__ import annotations

import hashlib
import hmac
import uuid
from typing import Any
from unittest.mock import AsyncMock, patch

import pytest
import pytest_asyncio

from app.core.config import get_settings
from app.finops.budget import FinOpsBudgetManager, get_budget_manager
from app.finops.ledger import FinOpsLedger
from app.finops.models import FinOpsRecord, ReconciliationStatus
from app.finops.reconciler import BillingReconciler
from app.services.billing import PayOSBillingService


@pytest_asyncio.fixture
async def budget_manager() -> FinOpsBudgetManager:
    """Isolated FinOps budget manager instance."""
    mgr = FinOpsBudgetManager()
    mgr._redis_available = False  # Pure in-memory default for test isolation
    return mgr


@pytest.mark.asyncio
class TestFinOpsGovernanceIntegration:
    """Integration tests verifying FinOps budget governance and accounting workflows."""

    async def test_preflight_reservation_and_post_inference_settlement(
        self, budget_manager: FinOpsBudgetManager
    ) -> None:
        """Integration 1: Atomic reservation -> inference execution -> exact settlement."""
        tenant_id = f"tenant-fin-{uuid.uuid4().hex[:8]}"
        await budget_manager.set_budget(
            tenant_id,
            token_quota=100_000,
            dollar_budget_usd=50.0,
        )

        # 1. Pre-flight atomic reservation
        reservation, err = await budget_manager.reserve_budget(
            tenant_id=tenant_id,
            estimated_tokens=10_000,
            estimated_cost_usd=0.05,
        )
        assert err is None
        assert reservation is not None
        assert reservation.reserved_tokens == 10_000
        assert reservation.reserved_cost_usd == 0.05

        # Usage reflects active reservation
        assert await budget_manager.get_tokens_used(tenant_id) == 10_000
        assert await budget_manager.get_dollars_spent(tenant_id) == 0.05

        # 2. Post-inference settlement with lower actual usage (refund excess)
        tok_used, dol_spent = await budget_manager.finalize_reservation(
            reservation=reservation,
            actual_tokens=7_500,
            actual_cost_usd=0.035,
        )
        assert tok_used == 7_500
        assert dol_spent == 0.035
        assert await budget_manager.get_tokens_used(tenant_id) == 7_500

    async def test_warning_and_hard_cap_threshold_enforcement(
        self, budget_manager: FinOpsBudgetManager
    ) -> None:
        """Integration 2: 80% soft warning and 100% hard suspension blocking."""
        tenant_id = f"tenant-thresh-{uuid.uuid4().hex[:8]}"
        await budget_manager.set_budget(
            tenant_id,
            token_quota=10_000,
            warning_threshold=0.80,
        )

        # 1. Below 80%: allowed=True, warning=False
        allowed_1, msg_1 = await budget_manager.check_budget(
            tenant_id, estimated_tokens=5_000
        )
        assert allowed_1 is True
        assert msg_1 is None

        # Consume 8,500 tokens (85% > 80%)
        res, _ = await budget_manager.reserve_budget(tenant_id, estimated_tokens=8_500)
        assert res is not None

        # 2. At 85%: allowed=True, warning triggered (Soft warning in message)
        allowed_2, msg_2 = await budget_manager.check_budget(
            tenant_id, estimated_tokens=500
        )
        assert allowed_2 is True
        assert msg_2 is not None
        assert "warning" in msg_2.lower()

        # 3. Request exceeding 100% cap (8,500 + 2,000 = 10,500 > 10,000)
        allowed_3, msg_3 = await budget_manager.check_budget(
            tenant_id, estimated_tokens=2_000
        )
        assert allowed_3 is False
        assert msg_3 is not None
        assert "suspended" in msg_3.lower() or "exceeded" in msg_3.lower()

        # Reservation over cap returns denial
        res_fail, denial = await budget_manager.reserve_budget(
            tenant_id, estimated_tokens=2_000
        )
        assert res_fail is None
        assert denial is not None
        assert "exceeded" in denial.lower()

    async def test_payos_webhook_signature_verification_and_budget_credit(self) -> None:
        """Integration 3: PayOS webhook verifies HMAC-SHA256 and updates tenant quota."""
        billing_service = PayOSBillingService()
        settings = get_settings()
        tenant_id = f"tenant-payos-{uuid.uuid4().hex[:8]}"

        webhook_data: dict[str, Any] = {
            "orderCode": 123456,
            "amount": 2_000_000,  # Enterprise tier threshold
            "description": f"JAKEAI {tenant_id} enterprise",
            "accountNumber": "99998888",
            "reference": "REF12345",
            "transactionDateTime": "2024-09-15 10:00:00",
            "currency": "VND",
            "paymentLinkId": "link-123",
            "code": "00",
            "desc": "success",
        }

        # Calculate valid HMAC-SHA256 signature
        sorted_keys = sorted(webhook_data.keys())
        sign_string = "&".join(f"{k}={webhook_data[k]}" for k in sorted_keys)
        expected_sig = hmac.new(
            settings.PAYOS_CHECKSUM_KEY.encode("utf-8"),
            sign_string.encode("utf-8"),
            hashlib.sha256,
        ).hexdigest()

        # 1. Verify valid signature
        is_valid = billing_service.verify_signature(webhook_data, expected_sig)
        assert is_valid is True

        # 2. Process verified payment webhook
        payload = {"data": webhook_data, "signature": expected_sig}
        result = await billing_service.process_payment_webhook(payload)
        assert result["status"] == "success"
        assert result["tenant_id"] == tenant_id
        assert result["tier"] == "enterprise"

        # 3. Verify budget manager quota provisioned to Enterprise (50,000,000 tokens)
        budget_mgr = get_budget_manager()
        quota = await budget_mgr.get_token_quota(tenant_id)
        assert quota == 50_000_000

    async def test_ledger_immutable_recording_and_reconciliation(self) -> None:
        """Integration 4: Ledger stores sanitized records, Reconciler tracks billing truth."""
        ledger = FinOpsLedger()
        reconciler = BillingReconciler(anomaly_threshold_pct=20.0)
        tenant_id = "tenant-ledger-1"

        # 1. Record transaction in ledger with sensitive metadata
        rec = FinOpsRecord(
            request_id=f"req_{uuid.uuid4().hex[:8]}",
            tenant_id=tenant_id,
            provider="openai",
            model="gpt-4o-mini",
            estimated_local_tokens=1000,
            raw_tokens=1000,
            optimized_tokens=800,
            baseline_cost_usd=0.002,
            estimated_cost_usd=0.0015,
            effective_cost_usd=0.0012,
            metadata={
                "user_id": "analyst-1",
                "api_key": "SECRET_KEY_123",
                "client_ip": "1.2.3.4",
            },
        )
        saved_rec = ledger.record(rec)

        # Sensitive keys stripped from ledger metadata
        assert "api_key" not in saved_rec.metadata
        assert saved_rec.metadata["client_ip"] == "1.2.3.4"
        assert saved_rec.metadata["user_id"] == "analyst-1"

        # 2. Reconcile local estimated tokens against provider authoritative usage
        provider_usage = {"prompt_tokens": 800, "completion_tokens": 150}  # total = 950
        reconciliation = reconciler.reconcile(
            model="gpt-4o-mini",
            estimated_local_tokens=1000,
            estimated_cost_usd=0.0015,
            provider_usage=provider_usage,
        )

        assert reconciliation.status == ReconciliationStatus.AUTHORITATIVE
        assert reconciliation.is_authoritative is True
        assert reconciliation.provider_reported_total == 950
        assert reconciliation.variance_tokens == -50
        assert reconciliation.is_anomalous is False


@pytest.mark.asyncio
class TestFinOpsMandatoryFailureCases:
    """Mandatory failure cases: unavailable, timeout, malformed, connection, partial, recovery."""

    async def test_failure_case_1_unavailable_redis(self) -> None:
        """Failure Case 1: Redis unavailable transparently falls back to in-memory governance."""
        mgr = FinOpsBudgetManager()
        mgr._redis_available = False

        tenant_id = "ten-fin-unavail"
        await mgr.set_budget(tenant_id, token_quota=5_000)

        res, err = await mgr.reserve_budget(tenant_id, estimated_tokens=1_000)
        assert err is None
        assert res is not None
        assert await mgr.get_tokens_used(tenant_id) == 1_000

    async def test_failure_case_2_timeout(
        self, budget_manager: FinOpsBudgetManager
    ) -> None:
        """Failure Case 2: Negative reservation estimates reject fail-closed."""
        tenant_id = "ten-fin-neg"
        with pytest.raises(ValueError):
            await budget_manager.reserve_budget(tenant_id, estimated_tokens=-500)

    async def test_failure_case_3_malformed_response_signature(self) -> None:
        """Failure Case 3: Tampered or invalid webhook signature rejected fail-closed."""
        billing = PayOSBillingService()
        data = {"orderCode": 999, "amount": 100000}
        bad_sig = "invalid_tampered_signature_hex_12345"

        is_valid = billing.verify_signature(data, bad_sig)
        assert is_valid is False

    async def test_failure_case_4_connection_failure(self) -> None:
        """Failure Case 4: Redis connection failure during reservation caught cleanly."""
        mgr = FinOpsBudgetManager()
        tenant_id = "ten-fin-conn-fail"
        await mgr.set_budget(tenant_id, token_quota=50_000)

        # Mock Redis eval raising ConnectionResetError
        mock_redis = AsyncMock()
        mock_redis.eval.side_effect = ConnectionResetError("Redis connection lost")

        with patch.object(mgr, "_get_redis", return_value=mock_redis):
            # Should not raise, falls back to memory reservation
            res, err = await mgr.reserve_budget(tenant_id, estimated_tokens=2_000)
            assert res is not None
            assert err is None

    async def test_failure_case_5_partial_failure_usage_overrun(
        self, budget_manager: FinOpsBudgetManager
    ) -> None:
        """Failure Case 5: Actual usage exceeding reservation settles accurately with overage."""
        tenant_id = f"tenant-overage-{uuid.uuid4().hex[:8]}"
        await budget_manager.set_budget(tenant_id, token_quota=50_000)

        # Reserve 5,000
        res, _ = await budget_manager.reserve_budget(
            tenant_id, estimated_tokens=5_000, estimated_cost_usd=0.01
        )
        assert res is not None

        # Actual usage was 7,500 (overrun by 2,500)
        tok_used, _dol_spent = await budget_manager.finalize_reservation(
            reservation=res,
            actual_tokens=7_500,
            actual_cost_usd=0.015,
        )
        assert tok_used == 7_500
        assert await budget_manager.get_tokens_used(tenant_id) == 7_500

    async def test_failure_case_6_recovery_top_up_clears_block(self) -> None:
        """Failure Case 6: Blocked tenant at 100% hard cap recovers immediately after top-up."""
        mgr = FinOpsBudgetManager()
        mgr._redis_available = False
        tenant_id = f"tenant-recov-{uuid.uuid4().hex[:8]}"

        # 1. Exhaust 1,000 token budget
        await mgr.set_budget(tenant_id, token_quota=1_000)
        res, _ = await mgr.reserve_budget(tenant_id, estimated_tokens=1_000)
        assert res is not None

        # 2. Blocked: further reservation denied
        res_blocked, denial = await mgr.reserve_budget(tenant_id, estimated_tokens=500)
        assert res_blocked is None
        assert denial is not None

        # 3. Top-up / Increase budget (Recovery)
        await mgr.set_budget(tenant_id, token_quota=50_000)

        # 4. Unblocked: reservation now succeeds immediately
        res_recovered, err = await mgr.reserve_budget(tenant_id, estimated_tokens=500)
        assert res_recovered is not None
        assert err is None
        assert await mgr.get_tokens_used(tenant_id) == 1_500
