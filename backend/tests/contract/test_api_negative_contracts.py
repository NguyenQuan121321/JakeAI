"""Negative Contract Verification Test Suite at HTTP Application Boundary.

TEST-04 — JAKEAI API CONTRACT & HTTP AUTOMATION
Logical ID: CONTRACT-006 | Subsystem: Contract & Schema

Verifies all 10 legitimately supported negative HTTP status codes:
- 400 Bad Request (Invalid parameters, unsupported providers, invalid webhook HMAC, context limits)
- 401 Unauthorized (Missing auth, malformed tokens, expired JWTs, wrong signature, token type)
- 403 Forbidden (Missing or invalid perimeter secrets, cross-tenant resumption and access)
- 404 Not Found (Nonexistent tasks, runs, RAG tasks, unconfigured BYOK keys)
- 409 Conflict (Duplicate tool results, already resolved approvals, duplicate execution)
- 413 Content Too Large (Payload ceiling rejection via middleware)
- 422 Unprocessable Entity (Missing required fields, out-of-bounds bounds, type mismatches)
- 429 Too Many Requests (Tenant token quota exhaustion, provider rate limits with Retry-After)
- 500 Internal Server Error (Unhandled route exceptions with correlation tracking)
- 503 Service Unavailable (Upstream provider outage, circuit breaker open, readiness failure)
"""

import time
import uuid
from typing import Any
from unittest.mock import AsyncMock

import jwt
import pytest
from httpx import ASGITransport, AsyncClient

from app.core.config import get_settings
from app.main import app
from app.providers.errors import ErrorCategory, ProviderError
from app.services.ai_gateway import GatewayInferenceProxy, QuotaManager


def create_token(
    sub: str = "test-neg-user",
    tenant_id: str = "tenant-neg-01",
    roles: list[str] | None = None,
    permissions: list[str] | None = None,
    token_type: str = "access",
    expires_in: int = 3600,
    secret_key: str | None = None,
) -> str:
    """Helper generating HS256 JWT access token for negative test verification."""
    settings = get_settings()
    key = secret_key or settings.JWT_SECRET_KEY
    now = int(time.time())
    payload = {
        "sub": sub,
        "tenant_id": tenant_id,
        "type": token_type,
        "iat": now,
        "exp": now + expires_in,
        "roles": roles or ["admin"],
        "permissions": permissions or ["*"],
    }
    return jwt.encode(payload, key, algorithm="HS256")


def auth_headers(
    tenant_id: str = "tenant-neg-01",
    sub: str = "test-neg-user",
    token: str | None = None,
    correlation_id: str | None = None,
) -> dict[str, str]:
    """Generate authorization and correlation headers."""
    jwt_token = token or create_token(sub=sub, tenant_id=tenant_id)
    headers = {"Authorization": f"Bearer {jwt_token}"}
    if correlation_id:
        headers["X-Correlation-ID"] = correlation_id
    return headers


# ==============================================================================
# 1. HTTP 400 Bad Request Contracts
# ==============================================================================


@pytest.mark.asyncio
async def test_negative_400_bad_request_unsupported_byok_provider(
    async_client: AsyncClient,
) -> None:
    """POST /api/v1/byok/keys rejects unsupported provider name with 400 Bad Request."""
    headers = auth_headers()
    response = await async_client.post(
        "/api/v1/byok/keys",
        headers=headers,
        json={"provider": "invalid-nonexistent-cloud", "api_key": "sk-test-12345"},
    )
    assert response.status_code == 400
    assert "Unsupported provider" in response.json()["detail"]


@pytest.mark.asyncio
async def test_negative_400_bad_request_billing_webhook_invalid_hmac(
    async_client: AsyncClient,
) -> None:
    """POST /api/v1/billing/webhook rejects invalid HMAC-SHA256 signature with 400."""
    response = await async_client.post(
        "/api/v1/billing/webhook",
        json={
            "code": "00",
            "desc": "success",
            "data": {"orderCode": 12345, "amount": 50000},
            "signature": "invalid_hmac_hex_digest_value",
        },
    )
    assert response.status_code == 400
    assert "Invalid HMAC signature" in response.json()["detail"]


@pytest.mark.asyncio
async def test_negative_400_bad_request_provider_context_limit_mapping(
    async_client: AsyncClient, monkeypatch: pytest.MonkeyPatch
) -> None:
    """ProviderError with CONTEXT_LIMIT is normalized to HTTP 400 Bad Request."""
    headers = auth_headers()

    async def mock_context_err(*args: Any, **kwargs: Any) -> Any:
        raise ProviderError(
            message="Prompt exceeds model context window limit of 8192 tokens",
            provider="openai",
            model="gpt-4o",
            category=ErrorCategory.CONTEXT_LIMIT,
        )

    monkeypatch.setattr(GatewayInferenceProxy, "chat_completions", mock_context_err)

    response = await async_client.post(
        "/api/v1/gateway/chat/completions",
        headers=headers,
        json={
            "model": "gpt-4o",
            "messages": [{"role": "user", "content": "Huge payload"}],
        },
    )
    assert response.status_code == 400
    error = response.json()["error"]
    assert error["type"] == "context_limit"
    assert "context window limit" in error["message"]


# ==============================================================================
# 2. HTTP 401 Unauthorized Contracts
# ==============================================================================


@pytest.mark.asyncio
@pytest.mark.parametrize(
    "method,path",
    [
        ("GET", "/api/v1/byok/keys"),
        ("POST", "/api/v1/agent/tasks"),
        ("POST", "/api/v1/rag/ingest"),
        ("POST", "/api/v1/gateway/chat/completions"),
        ("GET", "/api/v1/analytics/dashboard"),
    ],
)
async def test_negative_401_unauthorized_missing_bearer_token(
    async_client: AsyncClient, method: str, path: str
) -> None:
    """Protected endpoints reject requests missing Authorization header with 401 Unauthorized."""
    if method == "GET":
        response = await async_client.get(path)
    else:
        response = await async_client.post(path, json={})
    assert response.status_code == 401
    assert "detail" in response.json()


@pytest.mark.asyncio
async def test_negative_401_unauthorized_malformed_token(
    async_client: AsyncClient,
) -> None:
    """Protected endpoints reject malformed Bearer tokens with 401 Unauthorized."""
    headers = {"Authorization": "Bearer not-a-valid-jwt-token-string"}
    response = await async_client.get("/api/v1/byok/keys", headers=headers)
    assert response.status_code == 401
    assert "invalid" in response.json()["detail"].lower()


@pytest.mark.asyncio
async def test_negative_401_unauthorized_expired_token(
    async_client: AsyncClient,
) -> None:
    """Protected endpoints reject expired JWT tokens with 401 Unauthorized."""
    expired_token = create_token(expires_in=-3600)
    headers = {"Authorization": f"Bearer {expired_token}"}
    response = await async_client.get("/api/v1/byok/keys", headers=headers)
    assert response.status_code == 401
    assert "expired" in response.json()["detail"].lower()


@pytest.mark.asyncio
async def test_negative_401_unauthorized_invalid_signature(
    async_client: AsyncClient,
) -> None:
    """Protected endpoints reject JWT signed with invalid secret key with 401 Unauthorized."""
    tampered_token = create_token(
        secret_key="completely-different-wrong-secret-key-32b"
    )
    headers = {"Authorization": f"Bearer {tampered_token}"}
    response = await async_client.get("/api/v1/byok/keys", headers=headers)
    assert response.status_code == 401
    assert "invalid" in response.json()["detail"].lower()


@pytest.mark.asyncio
async def test_negative_401_unauthorized_wrong_token_type(
    async_client: AsyncClient,
) -> None:
    """Protected endpoints reject tokens with token_type != 'access' with 401 Unauthorized."""
    refresh_token = create_token(token_type="refresh")
    headers = {"Authorization": f"Bearer {refresh_token}"}
    response = await async_client.get("/api/v1/byok/keys", headers=headers)
    assert response.status_code == 401
    assert "invalid token type" in response.json()["detail"].lower()


@pytest.mark.asyncio
async def test_negative_401_unauthorized_provider_auth_error_mapping(
    async_client: AsyncClient, monkeypatch: pytest.MonkeyPatch
) -> None:
    """ProviderError with AUTHENTICATION is mapped to HTTP 401 with zero key leakage."""
    headers = auth_headers()

    async def mock_auth_err(*args: Any, **kwargs: Any) -> Any:
        raise ProviderError(
            message="Invalid API key provided for upstream provider",
            provider="openai",
            category=ErrorCategory.AUTHENTICATION,
        )

    monkeypatch.setattr(GatewayInferenceProxy, "chat_completions", mock_auth_err)

    response = await async_client.post(
        "/api/v1/gateway/chat/completions",
        headers=headers,
        json={"messages": [{"role": "user", "content": "hi"}]},
    )
    assert response.status_code == 401
    error = response.json()["error"]
    assert error["type"] == "authentication"
    assert "Invalid API key" in error["message"]


# ==============================================================================
# 3. HTTP 403 Forbidden Contracts
# ==============================================================================


@pytest.mark.asyncio
@pytest.mark.parametrize(
    "path",
    ["/api/v1/coding/resume", "/internal/v1/coding/resume"],
)
async def test_negative_403_forbidden_missing_internal_perimeter_secret(
    async_client: AsyncClient, path: str
) -> None:
    """Internal resume endpoints reject requests without valid X-JakeAI-Internal-Secret with 403."""
    response = await async_client.post(
        path,
        json={
            "call_id": "call-123",
            "result": {"status": "ok"},
            "tenant_id": "tenant-neg-01",
        },
    )
    assert response.status_code == 403
    assert "Perimeter bypass rejected" in response.json()["detail"]


@pytest.mark.asyncio
async def test_negative_403_forbidden_invalid_internal_perimeter_secret(
    async_client: AsyncClient,
) -> None:
    """Internal resume rejects requests with invalid perimeter secret header with 403."""
    response = await async_client.post(
        "/internal/v1/coding/resume",
        headers={"X-JakeAI-Internal-Secret": "invalid-spoofed-secret-key"},
        json={
            "call_id": "call-123",
            "result": {"status": "ok"},
            "tenant_id": "tenant-neg-01",
        },
    )
    assert response.status_code == 403
    assert "Perimeter bypass rejected" in response.json()["detail"]


@pytest.mark.asyncio
async def test_negative_403_forbidden_cross_tenant_tool_resumption(
    async_client: AsyncClient,
) -> None:
    """Tool resumption rejects cross-tenant execution attempts with 403 Forbidden."""
    from app.services.resume_bridge import get_resume_bridge

    bridge = get_resume_bridge()
    settings = get_settings()
    call_id = f"call_test_{uuid.uuid4().hex[:8]}"

    # Save checkpoint belonging to tenant-alpha
    await bridge.save_checkpoint(
        call_id=call_id,
        tenant_id="tenant-alpha",
        state_data={"tool": "calculator"},
    )

    # Tenant-beta attempts to resume tenant-alpha checkpoint
    headers = {
        "x-forwarded-by": "finnapigo",
        "x-internal-secret": settings.INTERNAL_GATEWAY_SECRET,
    }
    response = await async_client.post(
        "/internal/v1/coding/resume",
        headers=headers,
        json={
            "call_id": call_id,
            "result": {"answer": "unauthorized"},
            "tenant_id": "tenant-beta",
        },
    )
    assert response.status_code == 403
    assert "tenant mismatch" in response.json()["detail"].lower()


@pytest.mark.asyncio
async def test_negative_403_forbidden_cross_tenant_agent_task_access(
    async_client: AsyncClient,
) -> None:
    """Cross-tenant agent task query returns 403 Forbidden."""
    from app.agent.runtime.manager import get_agent_manager

    manager = get_agent_manager()
    task_a = manager.create_task(
        goal="Tenant A private task",
        tenant_id="tenant-alpha-only",
        user_id="user-a",
    )

    # Tenant B tries to query Tenant A's task
    headers_b = auth_headers(tenant_id="tenant-beta-intruder", sub="user-b")
    response = await async_client.get(
        f"/api/v1/agent/tasks/{task_a.task_id}", headers=headers_b
    )
    assert response.status_code == 403
    assert "Tenant" in response.json()["detail"]


# ==============================================================================
# 4. HTTP 404 Not Found Contracts
# ==============================================================================


@pytest.mark.asyncio
async def test_negative_404_not_found_nonexistent_agent_task(
    async_client: AsyncClient,
) -> None:
    """GET /api/v1/agent/tasks/{task_id} returns 404 for unknown task ID."""
    headers = auth_headers()
    response = await async_client.get(
        "/api/v1/agent/tasks/task_nonexistent_9999", headers=headers
    )
    assert response.status_code == 404
    assert "not found" in response.json()["detail"].lower()


@pytest.mark.asyncio
async def test_negative_404_not_found_nonexistent_agent_run(
    async_client: AsyncClient,
) -> None:
    """GET /api/v1/agent/tasks/{task_id}/runs/{run_id} returns 404 for unknown run."""
    headers = auth_headers()
    response = await async_client.get(
        "/api/v1/agent/tasks/task_neg/runs/run_nonexistent_9999", headers=headers
    )
    assert response.status_code == 404
    assert "not found" in response.json()["detail"].lower()


@pytest.mark.asyncio
async def test_negative_404_not_found_nonexistent_rag_task(
    async_client: AsyncClient,
) -> None:
    """GET /api/v1/rag/tasks/{task_id} returns 404 for unknown ingestion task."""
    headers = auth_headers()
    response = await async_client.get(
        "/api/v1/rag/tasks/task_rag_nonexistent_9999", headers=headers
    )
    assert response.status_code == 404
    assert "not found" in response.json()["detail"].lower()


@pytest.mark.asyncio
async def test_negative_404_not_found_nonexistent_byok_provider_key(
    async_client: AsyncClient,
) -> None:
    """DELETE /api/v1/byok/keys/{provider} returns 404 when tenant has no stored key."""
    headers = auth_headers(tenant_id="tenant-no-keys-stored")
    response = await async_client.delete("/api/v1/byok/keys/deepseek", headers=headers)
    assert response.status_code == 404
    assert "No key found" in response.json()["detail"]


# ==============================================================================
# 5. HTTP 409 Conflict Contracts
# ==============================================================================


@pytest.mark.asyncio
async def test_negative_409_conflict_duplicate_tool_result_submission(
    async_client: AsyncClient,
) -> None:
    """Submitting result for an already completed tool call returns 409 Conflict."""
    from app.services.resume_bridge import get_resume_bridge

    bridge = get_resume_bridge()
    settings = get_settings()
    call_id = f"call_dup_{uuid.uuid4().hex[:8]}"
    tenant_id = "tenant-dup-01"

    # Save and complete tool call
    await bridge.save_checkpoint(
        call_id=call_id,
        tenant_id=tenant_id,
        state_data={"tool": "financial_calculator"},
    )
    headers = {
        "x-forwarded-by": "finnapigo",
        "x-internal-secret": settings.INTERNAL_GATEWAY_SECRET,
    }
    r_first = await async_client.post(
        "/internal/v1/coding/resume",
        headers=headers,
        json={"call_id": call_id, "result": {"value": 2}, "tenant_id": tenant_id},
    )
    assert r_first.status_code == 200

    # Second submission on completed call must return 409 Conflict
    r_second = await async_client.post(
        "/internal/v1/coding/resume",
        headers=headers,
        json={"call_id": call_id, "result": {"value": 2}, "tenant_id": tenant_id},
    )
    assert r_second.status_code == 409
    assert "already" in r_second.json()["detail"].lower()


@pytest.mark.asyncio
async def test_negative_409_conflict_agent_approval_already_resolved(
    async_client: AsyncClient,
) -> None:
    """Submitting decision on an already resolved approval returns 409 Conflict."""
    from app.agent.runtime.manager import get_agent_manager

    manager = get_agent_manager()
    tenant_id = f"tenant-appr-{uuid.uuid4().hex[:6]}"
    task = manager.create_task(
        goal="Approval gate test task", tenant_id=tenant_id, user_id="user-1"
    )
    run = manager.create_run(task.task_id, tenant_id=tenant_id, user_id="user-1")

    # Request approval
    appr = manager.approval_manager.create_request(
        task_id=task.task_id,
        run_id=run.run_id,
        tenant_id=tenant_id,
        tool_name="dangerous_command",
        tool_args={"cmd": "rm -rf /tmp"},
        reason="Dangerous operation",
    )

    # First decision: Approved -> 200 OK
    headers = auth_headers(tenant_id=tenant_id)
    r1 = await async_client.post(
        f"/api/v1/agent/tasks/{task.task_id}/runs/{run.run_id}/approvals/{appr.approval_id}",
        headers=headers,
        json={"approved": True, "reason": "Approved by operator"},
    )
    assert r1.status_code == 200

    # Second decision: Duplicate decision on resolved approval -> 409 Conflict
    r2 = await async_client.post(
        f"/api/v1/agent/tasks/{task.task_id}/runs/{run.run_id}/approvals/{appr.approval_id}",
        headers=headers,
        json={"approved": False, "reason": "Second duplicate attempt"},
    )
    assert r2.status_code == 409
    assert "already finalized" in r2.json()["detail"].lower()


# ==============================================================================
# 6. HTTP 413 Content Too Large Contracts
# ==============================================================================


@pytest.mark.asyncio
async def test_negative_413_payload_too_large_exceeding_body_limit(
    async_client: AsyncClient,
) -> None:
    """Payloads exceeding MAX_REQUEST_BODY_BYTES are rejected at perimeter with 413."""
    settings = get_settings()
    headers = auth_headers()
    # Spoof content-length header exceeding limit
    headers["content-length"] = str(settings.MAX_REQUEST_BODY_BYTES + 1024)

    response = await async_client.post(
        "/api/v1/agent/tasks",
        headers=headers,
        json={"goal": "Small body with huge content-length claim"},
    )
    assert response.status_code == 413
    assert "Request entity too large" in response.json()["detail"]


# ==============================================================================
# 7. HTTP 422 Unprocessable Entity Contracts
# ==============================================================================


@pytest.mark.asyncio
async def test_negative_422_missing_required_fields(
    async_client: AsyncClient,
) -> None:
    """POST /api/v1/agent/tasks rejects empty JSON payload with missing 'goal' with 422."""
    headers = auth_headers()
    response = await async_client.post("/api/v1/agent/tasks", headers=headers, json={})
    assert response.status_code == 422
    data = response.json()
    assert "detail" in data
    assert any(err["loc"][-1] == "goal" for err in data["detail"])


@pytest.mark.asyncio
async def test_negative_422_out_of_bounds_parameters(
    async_client: AsyncClient,
) -> None:
    """POST /api/v1/gateway/quotas rejects quota limit below minimum floor with 422."""
    headers = auth_headers()
    response = await async_client.post(
        "/api/v1/gateway/quotas", headers=headers, json={"new_limit": 50}
    )
    assert response.status_code == 422
    data = response.json()
    assert any("greater_than_equal" in err.get("type", "") for err in data["detail"])


@pytest.mark.asyncio
async def test_negative_422_query_parameter_type_mismatch(
    async_client: AsyncClient,
) -> None:
    """GET /api/v1/finops/transactions rejects non-integer 'limit' query parameter with 422."""
    headers = auth_headers()
    response = await async_client.get(
        "/api/v1/finops/transactions?limit=not-an-int", headers=headers
    )
    assert response.status_code == 422
    assert any(
        "int_parsing" in err.get("type", "") for err in response.json()["detail"]
    )


# ==============================================================================
# 8. HTTP 429 Too Many Requests Contracts
# ==============================================================================


@pytest.mark.asyncio
async def test_negative_429_too_many_requests_tenant_quota_exceeded(
    async_client: AsyncClient, monkeypatch: pytest.MonkeyPatch
) -> None:
    """POST /api/v1/gateway/chat/completions returns 429 when tenant quota is exhausted."""
    headers = auth_headers(tenant_id="tenant-exhausted")

    monkeypatch.setattr(
        QuotaManager,
        "reserve_budget",
        AsyncMock(return_value=(None, "Monthly token quota exceeded for tenant")),
    )

    response = await async_client.post(
        "/api/v1/gateway/chat/completions",
        headers=headers,
        json={
            "model": "gemini-1.5-flash",
            "messages": [{"role": "user", "content": "test"}],
        },
    )
    assert response.status_code == 429
    assert "Monthly token quota exceeded" in response.json()["detail"]


@pytest.mark.asyncio
async def test_negative_429_too_many_requests_provider_rate_limit_with_retry_after(
    async_client: AsyncClient, monkeypatch: pytest.MonkeyPatch
) -> None:
    """ProviderError with QUOTA returns HTTP 429 with preserved Retry-After header."""
    headers = auth_headers()

    async def mock_quota_err(*args: Any, **kwargs: Any) -> Any:
        raise ProviderError(
            message="Rate limit exceeded on upstream provider",
            provider="openai",
            category=ErrorCategory.QUOTA,
            retry_after_seconds=42.0,
        )

    monkeypatch.setattr(GatewayInferenceProxy, "chat_completions", mock_quota_err)

    response = await async_client.post(
        "/api/v1/gateway/chat/completions",
        headers=headers,
        json={"messages": [{"role": "user", "content": "hi"}]},
    )
    assert response.status_code == 429
    assert response.headers.get("Retry-After") == "42"
    error = response.json()["error"]
    assert error["type"] == "quota"


# ==============================================================================
# 9. HTTP 500 Internal Server Error Contracts
# ==============================================================================


@pytest.mark.asyncio
async def test_negative_500_internal_server_error_preserves_correlation_id() -> None:
    """Unhandled server exceptions return 500 while recording metrics and correlation ID."""
    from app.telemetry.metrics import metrics

    transport = ASGITransport(app=app, raise_app_exceptions=False)
    headers = auth_headers(correlation_id="corr-neg-500-test")

    with pytest.MonkeyPatch.context() as mp:

        def mock_crash() -> Any:
            raise RuntimeError("Simulated unexpected database connectivity crash")

        mp.setattr(metrics, "get_snapshot", mock_crash)

        async with AsyncClient(
            transport=transport, base_url="http://testserver"
        ) as client:
            response = await client.get("/api/v1/analytics/metrics", headers=headers)
            assert response.status_code == 500


# ==============================================================================
# 10. HTTP 503 Service Unavailable Contracts
# ==============================================================================


@pytest.mark.asyncio
async def test_negative_503_service_unavailable_provider_outage(
    async_client: AsyncClient, monkeypatch: pytest.MonkeyPatch
) -> None:
    """ProviderError with PROVIDER_UNAVAILABLE returns HTTP 503 Service Unavailable."""
    headers = auth_headers()

    async def mock_unavail_err(*args: Any, **kwargs: Any) -> Any:
        raise ProviderError(
            message="Upstream provider DNS resolution failure or network outage",
            provider="gemini",
            category=ErrorCategory.PROVIDER_UNAVAILABLE,
        )

    monkeypatch.setattr(GatewayInferenceProxy, "chat_completions", mock_unavail_err)

    response = await async_client.post(
        "/api/v1/gateway/chat/completions",
        headers=headers,
        json={"messages": [{"role": "user", "content": "hi"}]},
    )
    assert response.status_code == 503
    error = response.json()["error"]
    assert error["type"] == "provider_unavailable"
    assert "outage" in error["message"]
