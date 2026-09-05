"""Unit and integration tests for Gateway security, PEP, and SSE streaming."""

import time
from typing import Any

import jwt
import pytest
from fastapi import HTTPException
from httpx import AsyncClient

from app.core.config import get_settings
from app.core.context import TenantContext
from app.core.rate_limiter import TokenBucketRateLimiter
from app.core.security import require_permissions, verify_finnapigo_jwt


def create_test_jwt(
    sub: str = "user-12345",
    tenant_id: str = "tenant-fin-corp",
    roles: list[str] | None = None,
    permissions: list[str] | None = None,
    expires_in: int = 3600,
    secret_key: str | None = None,
    algorithm: str = "HS256",
) -> str:
    """Generate a test JWT token for test assertions."""
    settings = get_settings()
    key = secret_key or settings.JWT_SECRET_KEY
    now = int(time.time())

    payload: dict[str, Any] = {
        "sub": sub,
        "tenant_id": tenant_id,
        "iat": now,
        "exp": now + expires_in,
        "roles": roles or ["user"],
        "permissions": permissions or ["chat:read", "chat:write"],
    }
    token: str = jwt.encode(payload, key, algorithm=algorithm)
    return token


def test_verify_valid_jwt() -> None:
    """Verify standard valid JWT parses correctly into TenantContext."""
    token = create_test_jwt(
        sub="user-fin-99",
        tenant_id="tenant-fin-99",
        roles=["financial_analyst"],
        permissions=["read:ledger", "execute:calc"],
    )
    context = verify_finnapigo_jwt(token, algorithm="HS256")

    assert context.user_id == "user-fin-99"
    assert context.tenant_id == "tenant-fin-99"
    assert "financial_analyst" in context.roles
    assert "read:ledger" in context.permissions
    assert context.correlation_id is not None


def test_verify_expired_jwt() -> None:
    """Verify expired token raises HTTP 401 Unauthorized."""
    token = create_test_jwt(expires_in=-100)

    with pytest.raises(HTTPException) as exc_info:
        verify_finnapigo_jwt(token, algorithm="HS256")

    assert exc_info.value.status_code == 401
    assert "expired" in exc_info.value.detail.lower()


def test_verify_invalid_signature() -> None:
    """Verify forged signature raises HTTP 401 Unauthorized."""
    token = create_test_jwt(secret_key="wrong-forged-secret-key-at-least-32-chars-long")

    with pytest.raises(HTTPException) as exc_info:
        verify_finnapigo_jwt(token, algorithm="HS256")

    assert exc_info.value.status_code == 401
    assert "invalid" in exc_info.value.detail.lower()


def test_verify_missing_claims() -> None:
    """Verify token missing sub or tenant_id raises HTTP 401."""
    settings = get_settings()
    payload = {"foo": "bar", "exp": int(time.time()) + 1000}
    token = jwt.encode(payload, settings.JWT_SECRET_KEY, algorithm="HS256")

    with pytest.raises(HTTPException) as exc_info:
        verify_finnapigo_jwt(token, algorithm="HS256")

    assert exc_info.value.status_code == 401


@pytest.mark.asyncio
async def test_require_permissions_dependency() -> None:
    """Verify require_permissions validator permits authorized tenants."""
    checker = require_permissions("ledger:read", "analytics:run")

    authorized_context = TenantContext(
        tenant_id="tenant-01",
        user_id="user-01",
        roles=["analyst"],
        permissions=["ledger:read", "analytics:run"],
    )
    result = await checker(authorized_context)
    assert result == authorized_context

    admin_context = TenantContext(
        tenant_id="tenant-01",
        user_id="user-02",
        roles=["admin"],
        permissions=[],
    )
    admin_result = await checker(admin_context)
    assert admin_result == admin_context

    unauthorized_context = TenantContext(
        tenant_id="tenant-01",
        user_id="user-03",
        roles=["user"],
        permissions=["ledger:read"],
    )
    with pytest.raises(HTTPException) as exc_info:
        await checker(unauthorized_context)
    assert exc_info.value.status_code == 403


@pytest.mark.asyncio
async def test_token_bucket_rate_limiter() -> None:
    """Verify token bucket rate limiter permits burst and exhausts tokens."""
    limiter = TokenBucketRateLimiter(rate_per_minute=60, burst=3, enable_redis=False)

    # First 3 tokens should pass
    for _ in range(3):
        allowed, remaining, _ = await limiter.check("tenant-test", "127.0.0.1")
        assert allowed is True

    # 4th token within the same second should be throttled
    allowed, remaining, retry_after = await limiter.check("tenant-test", "127.0.0.1")
    assert allowed is False
    assert remaining == 0
    assert retry_after > 0


@pytest.mark.asyncio
async def test_chat_stream_unauthorized(async_client: AsyncClient) -> None:
    """Verify /chat/stream rejects requests without Bearer token."""
    response = await async_client.post(
        "/api/v1/chat/stream",
        json={"prompt": "Calculate Q3 revenue."},
    )
    assert response.status_code == 401 or response.status_code == 403


@pytest.mark.asyncio
async def test_chat_stream_success(
    async_client: AsyncClient,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Verify /chat/stream validates JWT, injects context, and streams SSE."""
    token = create_test_jwt(
        sub="user-99",
        tenant_id="tenant-acme",
        permissions=["chat:stream"],
    )

    # Temporarily set algorithm to HS256 for unit test execution
    settings = get_settings()
    monkeypatch.setattr(settings, "JWT_ALGORITHM", "HS256")

    response = await async_client.post(
        "/api/v1/chat/stream",
        headers={"Authorization": f"Bearer {token}"},
        json={"prompt": "Calculate Q3 EBITDA", "conversation_id": "test-conv-01"},
    )

    assert response.status_code == 200
    assert "text/event-stream" in response.headers.get("content-type", "")
    assert response.headers.get("x-tenant-id") == "tenant-acme"

    body = response.text
    assert "event: status" in body
    assert "event: token" in body
    assert "event: done" in body
    assert "tenant-acme" in body
