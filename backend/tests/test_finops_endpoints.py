"""REST API Contract and Integration Tests for AI FinOps Endpoints."""

import pytest
from httpx import ASGITransport, AsyncClient

from app.core.context import TenantContext
from app.core.security import exchange_obo_token
from app.finops.service import get_finops_service
from app.main import app


@pytest.fixture
def finops_auth_headers() -> dict[str, str]:
    context = TenantContext(
        tenant_id="tenant-finops-endpoint-test",
        user_id="user-finops-123",
        roles=["admin"],
        scopes=["chat:write", "gateway:use", "finops:read"],
        permissions=["quotas:write", "billing:read", "finops:admin"],
    )
    token = exchange_obo_token(context)
    return {"Authorization": f"Bearer {token}"}


@pytest.mark.asyncio
async def test_finops_endpoints_summary_and_budget(finops_auth_headers: dict[str, str]):
    """Verify GET /api/v1/finops/summary and /budget endpoints."""
    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test") as client:
        # 1. Get initial budget
        budget_res = await client.get(
            "/api/v1/finops/budget", headers=finops_auth_headers
        )
        assert budget_res.status_code == 200
        budget_data = budget_res.json()
        assert "token_quota" in budget_data
        assert "tokens_used" in budget_data
        assert "is_suspended" in budget_data

        # 2. Update budget
        update_res = await client.post(
            "/api/v1/finops/budget",
            json={
                "token_quota": 500_000,
                "dollar_budget_usd": 25.0,
                "warning_threshold": 0.85,
            },
            headers=finops_auth_headers,
        )
        assert update_res.status_code == 200
        up_data = update_res.json()
        assert up_data["token_quota"] == 500_000
        assert up_data["dollar_budget_usd"] == 25.0
        assert up_data["warning_threshold"] == 0.85

        # 3. Seed a transaction via finops service to verify summary
        svc = get_finops_service()
        await svc.record_upstream_inference(
            request_id="req-ep-test-01",
            tenant_id="tenant-finops-endpoint-test",
            provider="openai",
            model="gpt-4o",
            raw_tokens=1500,
            optimized_tokens=1000,
            output_tokens=150,
            provider_usage={
                "prompt_tokens": 1000,
                "completion_tokens": 150,
                "total_tokens": 1150,
            },
        )

        # 4. Get Summary
        summary_res = await client.get(
            "/api/v1/finops/summary", headers=finops_auth_headers
        )
        assert summary_res.status_code == 200
        summary_data = summary_res.json()
        assert summary_data["total_requests"] >= 1
        assert "savings_attribution" in summary_data
        assert "total_savings_usd" in summary_data
        assert summary_data["budget_status"]["token_quota"] == 500_000


@pytest.mark.asyncio
async def test_finops_endpoints_transactions_and_reconciliation(
    finops_auth_headers: dict[str, str],
):
    """Verify GET /api/v1/finops/transactions and /reconciliation."""
    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test") as client:
        # 1. Get transactions list
        tx_res = await client.get(
            "/api/v1/finops/transactions?limit=10", headers=finops_auth_headers
        )
        assert tx_res.status_code == 200
        tx_list = tx_res.json()
        assert isinstance(tx_list, list)

        # 2. Get reconciliation report
        rec_res = await client.get(
            "/api/v1/finops/reconciliation", headers=finops_auth_headers
        )
        assert rec_res.status_code == 200
        rec_data = rec_res.json()
        assert "total_reconciled" in rec_data
        assert "net_token_variance" in rec_data
        assert "anomalous_requests_count" in rec_data


@pytest.mark.asyncio
async def test_finops_unauthorized_access():
    """Verify 401 Unauthorized when no valid Bearer token is provided."""
    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test") as client:
        res = await client.get("/api/v1/finops/summary")
        assert res.status_code == 401
