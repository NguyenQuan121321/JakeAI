"""Unit and integration tests for AI Gateway, PayOS Billing, and Analytics Dashboard."""

import hashlib
import hmac

import pytest
from httpx import ASGITransport, AsyncClient

from app.core.config import get_settings
from app.core.context import TenantContext
from app.core.security import exchange_obo_token
from app.main import app
from app.services.ai_gateway import (
    GatewayChatRequest,
    GatewayInferenceProxy,
    QuotaManager,
)
from app.services.billing import PayOSBillingService


@pytest.fixture
def auth_headers() -> dict[str, str]:
    context = TenantContext(
        tenant_id="tenant-commercial-test",
        user_id="user-comm-789",
        roles=["admin"],
        scopes=["chat:write", "gateway:use"],
        permissions=["quotas:write", "billing:read"],
    )
    token = exchange_obo_token(context)
    return {"Authorization": f"Bearer {token}"}


@pytest.mark.asyncio
async def test_quota_manager_lifecycle():
    """Verify quota tracking, soft alerting at 80%, and hard suspension at 100%."""
    quota_mgr = QuotaManager()
    tenant_id = "tenant-quota-lifecycle"

    # Set quota to 1000 tokens
    await quota_mgr.set_quota_limit(tenant_id, 1000)
    assert await quota_mgr.get_quota_limit(tenant_id) == 1000

    # Initial usage
    allowed, warning = await quota_mgr.check_quota(tenant_id)
    assert allowed is True
    assert warning is None

    # Record 850 tokens (85% - soft alert)
    await quota_mgr.record_usage(tenant_id, 500, 350)
    allowed, warning = await quota_mgr.check_quota(tenant_id)
    assert allowed is True
    assert warning is not None
    assert "85.0%" in warning

    # Record another 200 tokens (105% - hard suspension)
    await quota_mgr.record_usage(tenant_id, 100, 100)
    allowed, err = await quota_mgr.check_quota(tenant_id)
    assert allowed is False
    assert "exceeded" in err

    # Status check
    status = await quota_mgr.get_status(tenant_id)
    assert status.is_suspended is True
    assert status.tokens_used == 1050


@pytest.mark.asyncio
async def test_gateway_inference_proxy_caching():
    """Verify inference proxy caches responses via Tier 1 exact match cache."""
    quota_mgr = QuotaManager()
    proxy = GatewayInferenceProxy(quota_mgr)
    tenant_id = "tenant-proxy-caching"
    await quota_mgr.set_quota_limit(tenant_id, 100_000)

    req = GatewayChatRequest(
        model="gemini-1.5-flash",
        messages=[{"role": "user", "content": "What is the capital of Vietnam?"}],
    )

    # 1. First execution - cache MISS
    res1 = await proxy.chat_completions(tenant_id, req)
    assert res1.cached is False
    assert res1.usage["total_tokens"] > 0
    assert (
        "Hanoi" in res1.choices[0]["message"]["content"]
        or "Vietnam" in res1.choices[0]["message"]["content"]
    )

    # 2. Second execution - cache HIT
    res2 = await proxy.chat_completions(tenant_id, req)
    assert res2.cached is True
    assert res2.tokens_saved > 0
    assert res2.usage["total_tokens"] == 0


@pytest.mark.asyncio
async def test_payos_signature_and_webhook():
    """Verify PayOS HMAC-SHA256 signature verification and automatic subscription provisioning."""
    billing_svc = PayOSBillingService()
    settings = get_settings()

    webhook_data = {
        "amount": 2_500_000,
        "description": "JAKEAI tenant-payos-corp enterprise plan",
        "orderCode": 123456,
    }

    # Generate valid signature matching PayOS algorithm (alphabetical key sorting)
    sorted_keys = sorted(webhook_data.keys())
    sign_str = "&".join(f"{k}={webhook_data[k]}" for k in sorted_keys)
    valid_sig = hmac.new(
        settings.PAYOS_CHECKSUM_KEY.encode("utf-8"),
        sign_str.encode("utf-8"),
        hashlib.sha256,
    ).hexdigest()

    # Verify signature
    assert billing_svc.verify_signature(webhook_data, valid_sig) is True
    assert billing_svc.verify_signature(webhook_data, "invalidsignature") is False

    # Process webhook
    result = await billing_svc.process_payment_webhook({"data": webhook_data})
    assert result["status"] == "success"
    assert result["tier"] == "enterprise"
    assert result["allocated_quota"] == 50_000_000

    # Verify subscription details
    sub = billing_svc.get_subscription("tenant-payos-corp")
    assert sub.tier == "enterprise"
    assert sub.is_active is True

    # Verify analytics telemetry
    metrics = await billing_svc.get_dashboard_metrics("tenant-payos-corp")
    assert metrics.subscription_tier == "enterprise"
    assert metrics.savings_percentage > 0


@pytest.mark.asyncio
async def test_commercial_api_endpoints(auth_headers: dict[str, str]):
    """Verify REST endpoints for Gateway proxy, quotas, billing, and analytics."""
    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test") as client:
        # 1. Gateway Chat Completion
        chat_res = await client.post(
            "/api/v1/gateway/chat/completions",
            json={
                "model": "gemini-1.5-flash",
                "messages": [
                    {"role": "user", "content": "Explain microservices in 1 sentence."}
                ],
            },
            headers=auth_headers,
        )
        assert chat_res.status_code == 200
        data = chat_res.json()
        assert "choices" in data

        # 2. Get Quota Status
        quota_res = await client.get("/api/v1/gateway/quotas", headers=auth_headers)
        assert quota_res.status_code == 200
        assert "quota_limit" in quota_res.json()

        # 3. Update Quota
        update_res = await client.post(
            "/api/v1/gateway/quotas",
            json={"new_limit": 5_000_000},
            headers=auth_headers,
        )
        assert update_res.status_code == 200
        assert update_res.json()["quota_limit"] == 5_000_000

        # 4. Get Subscription
        sub_res = await client.get("/api/v1/billing/subscription", headers=auth_headers)
        assert sub_res.status_code == 200
        assert sub_res.json()["tier"] in ("free", "starter", "pro", "enterprise")

        # 5. Get Analytics Dashboard
        dash_res = await client.get("/api/v1/analytics/dashboard", headers=auth_headers)
        assert dash_res.status_code == 200
        dash_data = dash_res.json()
        assert "tokens_processed" in dash_data
        assert "avg_ttft_ms" in dash_data
        assert "cost_savings_usd" in dash_data

        # 6. Post Billing Webhook (Invalid Signature -> 400 Bad Request)
        bad_webhook_res = await client.post(
            "/api/v1/billing/webhook",
            json={
                "code": "00",
                "desc": "success",
                "data": {
                    "amount": 149_000,
                    "description": "JAKEAI tenant-comm-pro pro",
                },
                "signature": "invalidsignature123",
            },
        )
        assert bad_webhook_res.status_code == 400

        # 7. Post Billing Webhook (Valid Signature -> 200 OK)
        settings = get_settings()
        webhook_data = {
            "amount": 149_000,
            "description": "JAKEAI tenant-comm-pro pro",
            "orderCode": 987654,
        }
        sorted_keys = sorted(webhook_data.keys())
        sign_str = "&".join(f"{k}={webhook_data[k]}" for k in sorted_keys)
        valid_sig = hmac.new(
            settings.PAYOS_CHECKSUM_KEY.encode("utf-8"),
            sign_str.encode("utf-8"),
            hashlib.sha256,
        ).hexdigest()

        good_webhook_res = await client.post(
            "/api/v1/billing/webhook",
            json={
                "code": "00",
                "desc": "success",
                "data": webhook_data,
                "signature": valid_sig,
            },
        )
        assert good_webhook_res.status_code == 200
        assert good_webhook_res.json()["status"] == "success"
        assert good_webhook_res.json()["tier"] == "pro"
