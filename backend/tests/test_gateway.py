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
from app.core.security import (
    exchange_obo_token,
    require_permissions,
    verify_finnapigo_jwt,
)


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
    token = create_test_jwt(
        secret_key="wrong-forged-secret-key-at-least-32-chars-long",  # gitleaks:allow
    )

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


def test_exchange_obo_token() -> None:
    """Verify On-Behalf-Of (OBO) token exchange produces valid delegation JWT."""
    ctx = TenantContext(
        tenant_id="tenant_obo_99",
        user_id="user_obo_123",
        org_id="org_enterprise",
        roles=["financial_analyst"],
        scopes=["reports:read", "transactions:read"],
        permissions=["ledger:access"],
    )

    obo_token = exchange_obo_token(
        context=ctx,
        target_audience="finnapigo-api",
        algorithm="HS256",
        secret_key="test-key-for-ci-pipeline-min-32-chars-long",
    )
    assert obo_token is not None

    # Decode and verify claims
    decoded: dict[str, Any] = jwt.decode(
        obo_token,
        "test-key-for-ci-pipeline-min-32-chars-long",
        algorithms=["HS256"],
        audience="finnapigo-api",
    )
    assert decoded["sub"] == "user_obo_123"
    assert decoded["tenant_id"] == "tenant_obo_99"
    assert decoded["org_id"] == "org_enterprise"
    assert decoded["aud"] == "finnapigo-api"
    assert decoded["act"]["sub"] == "jakeai-platform"
    assert "financial_analyst" in decoded["roles"]
    assert "reports:read" in decoded["scopes"]


def test_verify_finnapigo_compact_enterprise_claims() -> None:
    """Verify FinnApiGo compact enterprise token (tid, uid, perms, role) parses correctly."""
    settings = get_settings()
    payload = {
        "uid": 42,
        "tid": "tenant-corp-42",
        "role": "admin",
        "perms": ["chat:stream", "reports:read"],
        "type": "access",
        "exp": int(time.time()) + 3600,
    }
    token = jwt.encode(payload, settings.JWT_SECRET_KEY, algorithm="HS256")
    context = verify_finnapigo_jwt(token, algorithm="HS256")

    assert context.user_id == "42"
    assert context.tenant_id == "tenant-corp-42"
    assert context.roles == ["admin"]
    assert "chat:stream" in context.permissions
    assert "reports:read" in context.permissions


def test_verify_token_type_isolation() -> None:
    """Verify non-access token types (e.g. reset or email verify) are rejected with 401."""
    settings = get_settings()
    payload = {
        "sub": "user-reset-01",
        "tenant_id": "tenant-01",
        "type": "reset",
        "exp": int(time.time()) + 3600,
    }
    token = jwt.encode(payload, settings.JWT_SECRET_KEY, algorithm="HS256")

    with pytest.raises(HTTPException) as exc_info:
        verify_finnapigo_jwt(token, algorithm="HS256")

    assert exc_info.value.status_code == 401
    assert "expected access token" in exc_info.value.detail


def test_verify_internal_perimeter_secret_validation() -> None:
    """Verify Invariant 4 perimeter provenance validation via X-Internal-Secret and HMAC."""
    import hashlib
    import hmac

    from starlette.requests import Request

    from app.core.security import verify_internal_perimeter_secret

    settings = get_settings()

    # 1. No headers -> False
    req_empty = Request(
        {"type": "http", "method": "POST", "path": "/api/v1/chat/stream", "headers": []}
    )
    assert verify_internal_perimeter_secret(req_empty) is False

    # 2. X-Forwarded-By only (spoofing attempt) -> False
    req_spoof = Request(
        {
            "type": "http",
            "method": "POST",
            "path": "/api/v1/chat/stream",
            "headers": [(b"x-forwarded-by", b"finnapigo")],
        }
    )
    assert verify_internal_perimeter_secret(req_spoof) is False

    # 3. Valid X-Internal-Secret -> True
    req_valid_secret = Request(
        {
            "type": "http",
            "method": "POST",
            "path": "/api/v1/chat/stream",
            "headers": [
                (b"x-forwarded-by", b"finnapigo"),
                (b"x-internal-secret", settings.INTERNAL_GATEWAY_SECRET.encode()),
            ],
        }
    )
    assert verify_internal_perimeter_secret(req_valid_secret) is True

    # 4. Wrong X-Internal-Secret -> False
    req_wrong_secret = Request(
        {
            "type": "http",
            "method": "POST",
            "path": "/api/v1/chat/stream",
            "headers": [
                (b"x-forwarded-by", b"finnapigo"),
                (b"x-internal-secret", b"wrong-secret-value"),
            ],
        }
    )
    assert verify_internal_perimeter_secret(req_wrong_secret) is False

    # 5. Valid HMAC signature -> True
    ts = int(time.time())
    sig = hmac.new(
        settings.INTERNAL_GATEWAY_SECRET.encode(),
        f"POST|/api/v1/chat/stream|{ts}".encode(),
        hashlib.sha256,
    ).hexdigest()
    req_valid_sig = Request(
        {
            "type": "http",
            "method": "POST",
            "path": "/api/v1/chat/stream",
            "headers": [
                (b"x-forwarded-by", b"finnapigo"),
                (b"x-internal-sig", f"t={ts};v1={sig}".encode()),
            ],
        }
    )
    assert verify_internal_perimeter_secret(req_valid_sig) is True


@pytest.mark.asyncio
async def test_rate_limiter_perimeter_spoofing_defense() -> None:
    """Verify rate limiter blocks spoofed X-Forwarded-By and allows authenticated edge requests."""
    from starlette.requests import Request

    from app.core.rate_limiter import enforce_rate_limit

    settings = get_settings()

    # Create exhausted rate limiter
    limiter = TokenBucketRateLimiter(rate_per_minute=60, burst=0, enable_redis=False)

    # Spoofed request without secret must be throttled with 429
    req_spoof = Request(
        {
            "type": "http",
            "method": "POST",
            "path": "/api/v1/chat/stream",
            "client": ("192.168.1.100", 5000),
            "headers": [(b"x-forwarded-by", b"finnapigo")],
        }
    )
    with pytest.raises(HTTPException) as exc_info:
        await enforce_rate_limit(req_spoof, "tenant-spoof", limiter=limiter)
    assert exc_info.value.status_code == 429

    # Authenticated edge request with valid secret must bypass rate limiter
    req_auth = Request(
        {
            "type": "http",
            "method": "POST",
            "path": "/api/v1/chat/stream",
            "client": ("192.168.1.100", 5000),
            "headers": [
                (b"x-forwarded-by", b"finnapigo"),
                (b"x-internal-secret", settings.INTERNAL_GATEWAY_SECRET.encode()),
            ],
        }
    )
    # Should not raise any exception
    await enforce_rate_limit(req_auth, "tenant-spoof", limiter=limiter)


@pytest.mark.asyncio
async def test_check_token_denylist_revoked_jti(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Verify check_token_denylist blocks revoked JTI tokens."""
    import redis.asyncio as aioredis

    from app.core.security import check_token_denylist

    settings = get_settings()
    token = jwt.encode(
        {"sub": "u1", "jti": "revoked-jti-123"},
        settings.JWT_SECRET_KEY,
        algorithm="HS256",
    )

    class FakeRedisClient:
        async def exists(self, key: str) -> bool:
            return "denylist:jti:revoked-jti-123" in key

        async def aclose(self) -> None:
            pass

    monkeypatch.setattr(aioredis, "from_url", lambda *args, **kwargs: FakeRedisClient())

    with pytest.raises(HTTPException) as exc_info:
        await check_token_denylist(token)
    assert exc_info.value.status_code == 401
    assert "Token has been revoked" in exc_info.value.detail


@pytest.mark.asyncio
async def test_check_token_denylist_revoked_sid(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Verify check_token_denylist blocks revoked session SID tokens."""
    import redis.asyncio as aioredis

    from app.core.security import check_token_denylist

    settings = get_settings()
    token = jwt.encode(
        {"sub": "u1", "sid": "revoked-sid-456"},
        settings.JWT_SECRET_KEY,
        algorithm="HS256",
    )

    class FakeRedisClient:
        async def exists(self, key: str) -> bool:
            return "denylist:sid:revoked-sid-456" in key

        async def aclose(self) -> None:
            pass

    monkeypatch.setattr(aioredis, "from_url", lambda *args, **kwargs: FakeRedisClient())

    with pytest.raises(HTTPException) as exc_info:
        await check_token_denylist(token)
    assert exc_info.value.status_code == 401
    assert "Session has been revoked" in exc_info.value.detail


@pytest.mark.asyncio
async def test_check_token_denylist_malformed_and_resilient(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Verify check_token_denylist handles malformed tokens and Redis connection drop."""
    import redis.asyncio as aioredis

    from app.core.security import check_token_denylist

    # 1. Malformed token returns without error
    await check_token_denylist("malformed.token.format")

    # 2. Redis failure fails open bounded by token TTL
    settings = get_settings()
    token = jwt.encode(
        {"sub": "u1", "jti": "some-jti"},
        settings.JWT_SECRET_KEY,
        algorithm="HS256",
    )

    def failing_from_url(*args: Any, **kwargs: Any) -> Any:
        raise ConnectionError("Redis unreachable")

    monkeypatch.setattr(aioredis, "from_url", failing_from_url)

    # Must not raise
    await check_token_denylist(token)


def test_verify_internal_perimeter_secret_edge_cases() -> None:
    """Verify perimeter secret checks for None request and malformed HMAC signatures."""
    from starlette.requests import Request

    from app.core.security import verify_internal_perimeter_secret

    # 1. None request
    assert verify_internal_perimeter_secret(None) is False

    # 2. Malformed HMAC signature with invalid timestamp format
    req_malformed_sig = Request(
        {
            "type": "http",
            "method": "POST",
            "path": "/api/v1/chat/stream",
            "headers": [
                (b"x-forwarded-by", b"finnapigo"),
                (b"x-internal-sig", b"t=invalid_timestamp;v1=bad"),
            ],
        }
    )
    assert verify_internal_perimeter_secret(req_malformed_sig) is False
