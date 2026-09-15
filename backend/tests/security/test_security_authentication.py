"""SEC-006: Dedicated Authentication Runtime Security Regression Test Suite.

Automated verification covering:
- Missing token
- Malformed token
- Invalid token (missing subject, invalid payload)
- Expired token
- Wrong token type (refresh / id_token)
- Invalid signature and tampered payloads
- Key rotation and kid matching
- Wrong issuer and audience validations
- Revoked token and session denylist
- Internal perimeter mutual auth and timestamp replay defense
- Webhook HMAC signature verification
"""

import hashlib
import hmac
import time
from typing import Any
from unittest.mock import AsyncMock

import jwt
import pytest
from fastapi import HTTPException
from httpx import ASGITransport, AsyncClient

from app.core.config import get_settings
from app.core.context import TenantContext
from app.core.security import (
    check_token_denylist,
    exchange_obo_token,
    verify_finnapigo_jwt,
    verify_internal_perimeter_secret,
)
from app.main import app


def _mint_jwt(
    payload_overrides: dict[str, Any] | None = None,
    secret: str | None = None,
    algorithm: str = "HS256",
    headers: dict[str, Any] | None = None,
) -> str:
    """Helper to mint deterministic synthetic JWTs for security tests (no hardcoded secrets)."""
    settings = get_settings()
    key = secret or settings.JWT_SECRET_KEY
    now = int(time.time())
    payload: dict[str, Any] = {
        "sub": "user-sec-auth",
        "tenant_id": "tenant-sec-auth",
        "type": "access",
        "roles": ["developer"],
        "permissions": ["chat:read", "agent:read"],
        "iat": now,
        "exp": now + 3600,
        "iss": "finnapigo-idp",
        "aud": "jakeai-api",
    }
    if payload_overrides:
        payload.update(payload_overrides)
    return jwt.encode(payload, key, algorithm=algorithm, headers=headers)


# ==============================================================================
# 1. Missing Token Tests
# ==============================================================================


@pytest.mark.asyncio
@pytest.mark.parametrize(
    "method,path",
    [
        ("GET", "/api/v1/byok/keys"),
        ("POST", "/api/v1/agent/tasks"),
        ("POST", "/api/v1/rag/ingest"),
        ("POST", "/api/v1/gateway/chat/completions"),
        ("GET", "/api/v1/finops/summary"),
        ("GET", "/api/v1/agent/tasks/task-fake-1234"),
    ],
)
async def test_auth_missing_token_returns_401(method: str, path: str) -> None:
    """Protected endpoints reject requests missing Authorization header with HTTP 401."""
    async with AsyncClient(
        transport=ASGITransport(app=app), base_url="http://test"
    ) as client:
        if method == "GET":
            resp = await client.get(path)
        else:
            resp = await client.post(path, json={})
        assert resp.status_code == 401
        assert "detail" in resp.json()
        assert resp.headers.get("www-authenticate", "").startswith("Bearer")


# ==============================================================================
# 2. Malformed Token Tests
# ==============================================================================


@pytest.mark.asyncio
@pytest.mark.parametrize(
    "auth_header",
    [
        "Bearer not-a-jwt",
        "Bearer header.payload",  # Missing signature segment
        "Bearer ...",
        "Bearer eyJhbGciOiJIUzI1NiJ9",  # Single segment
        "Bearer %%%invalid_base64$$$",
        "Basic dXNlcjpwYXNz",  # Wrong scheme
        "Bearer ",  # Empty credentials
        "Token some-random-token",  # Unsupported scheme
    ],
)
async def test_auth_malformed_token_rejected_with_401(auth_header: str) -> None:
    """Malformed Authorization headers and corrupted JWTs reject with HTTP 401."""
    async with AsyncClient(
        transport=ASGITransport(app=app), base_url="http://test"
    ) as client:
        resp = await client.get(
            "/api/v1/byok/keys", headers={"Authorization": auth_header}
        )
        assert resp.status_code == 401
        assert "detail" in resp.json()


# ==============================================================================
# 3. Invalid Token Payload (Missing Subject / Wrong Types)
# ==============================================================================


def test_auth_invalid_token_missing_subject() -> None:
    """Token missing mandatory subject (sub / uid) fails verification with HTTP 401."""
    # Token with no sub or uid key in payload
    settings = get_settings()
    now = int(time.time())
    payload = {
        "tenant_id": "tenant-sec-auth",
        "type": "access",
        "iat": now,
        "exp": now + 3600,
    }
    token = jwt.encode(payload, settings.JWT_SECRET_KEY, algorithm="HS256")
    with pytest.raises(HTTPException) as exc_info:
        verify_finnapigo_jwt(token)
    assert exc_info.value.status_code == 401
    assert "missing mandatory subject" in exc_info.value.detail.lower()

    # Token with empty string subject
    empty_sub_token = _mint_jwt(payload_overrides={"sub": "", "uid": ""})
    with pytest.raises(HTTPException) as exc_info:
        verify_finnapigo_jwt(empty_sub_token)
    assert exc_info.value.status_code == 401
    assert "missing mandatory subject" in exc_info.value.detail.lower()


def test_auth_wrong_token_type_rejected() -> None:
    """Tokens with type != 'access' (e.g., refresh or id_token) fail closed with HTTP 401."""
    # Refresh token passed as access token
    refresh_token = _mint_jwt(payload_overrides={"type": "refresh"})
    with pytest.raises(HTTPException) as exc_info:
        verify_finnapigo_jwt(refresh_token)
    assert exc_info.value.status_code == 401
    assert "invalid token type" in exc_info.value.detail.lower()

    # ID token passed
    id_token = _mint_jwt(payload_overrides={"type": "id_token"})
    with pytest.raises(HTTPException) as exc_info:
        verify_finnapigo_jwt(id_token)
    assert exc_info.value.status_code == 401


# ==============================================================================
# 4. Expired Token Tests
# ==============================================================================


def test_auth_expired_token_rejected_with_401() -> None:
    """Tokens with past expiration timestamp fail with HTTP 401 expired message."""
    expired_token = _mint_jwt(payload_overrides={"exp": int(time.time()) - 3600})
    with pytest.raises(HTTPException) as exc_info:
        verify_finnapigo_jwt(expired_token)
    assert exc_info.value.status_code == 401
    assert "expired" in exc_info.value.detail.lower()


@pytest.mark.asyncio
async def test_auth_expired_token_http_boundary() -> None:
    """HTTP boundary returns 401 for expired token."""
    expired_token = _mint_jwt(payload_overrides={"exp": int(time.time()) - 60})
    async with AsyncClient(
        transport=ASGITransport(app=app), base_url="http://test"
    ) as client:
        resp = await client.get(
            "/api/v1/byok/keys",
            headers={"Authorization": f"Bearer {expired_token}"},
        )
        assert resp.status_code == 401
        assert "expired" in resp.json()["detail"].lower()


# ==============================================================================
# 5. Invalid Signature & Tampered Payload Tests
# ==============================================================================


def test_auth_invalid_signature_fails_closed() -> None:
    """Tokens signed with untrusted foreign secrets fail verification."""
    untrusted_secret = "untrusted-adversary-secret-key-that-does-not-match-32b"
    token = _mint_jwt(secret=untrusted_secret)
    with pytest.raises(HTTPException) as exc_info:
        verify_finnapigo_jwt(token)
    assert exc_info.value.status_code == 401
    assert "invalid authentication token" in exc_info.value.detail.lower()


def test_auth_tampered_payload_fails_signature_check() -> None:
    """Altering payload claims after token generation invalidates signature."""
    valid_token = _mint_jwt(payload_overrides={"roles": ["developer"]})
    header_b64, _payload_b64, sig_b64 = valid_token.split(".")

    # Adversary attempts to tamper payload to grant admin role
    tampered_payload = (
        '{"sub":"user-sec-auth","tenant_id":"tenant-sec-auth","roles":["admin"]}'
    )
    import base64

    tampered_payload_b64 = (
        base64.urlsafe_b64encode(tampered_payload.encode()).decode().rstrip("=")
    )
    tampered_token = f"{header_b64}.{tampered_payload_b64}.{sig_b64}"

    with pytest.raises(HTTPException) as exc_info:
        verify_finnapigo_jwt(tampered_token)
    assert exc_info.value.status_code == 401


def test_auth_algorithm_none_rejected() -> None:
    """Algorithm 'none' attack is rejected."""
    payload = {"sub": "attacker", "tenant_id": "evil", "exp": int(time.time()) + 3600}
    # PyJWT refuses algorithm='none' by default without unsecure flag
    token_none = jwt.encode(payload, key="", algorithm="none")
    with pytest.raises(HTTPException) as exc_info:
        verify_finnapigo_jwt(token_none)
    assert exc_info.value.status_code == 401


# ==============================================================================
# 6. Key Rotation and Key Identifier (KID) Verification
# ==============================================================================


def test_auth_key_rotation_accepts_previous_secret(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """JWT signed with previous valid secret is verified during rolling rotation."""
    settings = get_settings()
    prev_secret = "previous-rolling-secret-key-for-rotation-audit-32b"
    monkeypatch.setattr(settings, "JWT_SECRET_PREVIOUS", prev_secret)

    token = _mint_jwt(secret=prev_secret)
    context = verify_finnapigo_jwt(token)
    assert context.user_id == "user-sec-auth"
    assert context.tenant_id == "tenant-sec-auth"


def test_auth_kid_header_matching(monkeypatch: pytest.MonkeyPatch) -> None:
    """JWT carrying kid header correctly sorts and resolves matching candidate secret."""
    settings = get_settings()
    current_key = settings.JWT_SECRET_KEY
    current_kid = hashlib.sha256(current_key.encode("utf-8")).hexdigest()[:8]

    token = _mint_jwt(headers={"kid": current_kid})
    context = verify_finnapigo_jwt(token)
    assert context.user_id == "user-sec-auth"


# ==============================================================================
# 7. Issuer and Audience Verification in OBO Token Exchange
# ==============================================================================


def test_auth_obo_token_exchange_and_claims_verification() -> None:
    """OBO token exchange produces valid RFC 8693 tokens with canonical issuer, audience, and actor."""
    caller_ctx = TenantContext(
        tenant_id="tenant-obo-sec",
        user_id="user-obo-sec",
        roles=["financial_analyst"],
        scopes=["reports:read"],
        permissions=["accounts:read"],
        correlation_id="corr-obo-12345",
    )
    token = exchange_obo_token(
        context=caller_ctx,
        target_audience="finnapigo-api",
        expires_in_seconds=300,
    )

    settings = get_settings()
    # Decode and verify exact OBO claims
    decoded = jwt.decode(
        token,
        settings.JWT_SECRET_KEY,
        algorithms=["HS256"],
        audience="finnapigo-api",
        issuer="jakeai-gateway",
    )
    assert decoded["iss"] == "jakeai-gateway"
    assert decoded["aud"] == "finnapigo-api"
    assert decoded["sub"] == "user-obo-sec"
    assert decoded["tenant_id"] == "tenant-obo-sec"
    assert decoded["act"]["sub"] == "jakeai-platform"
    assert decoded["act"]["client_id"] == "jakeai-gateway"


def test_auth_wrong_audience_rejected_when_audience_enforced() -> None:
    """Token with wrong audience fails audience verification."""
    caller_ctx = TenantContext(
        tenant_id="tenant-aud-sec",
        user_id="user-aud-sec",
    )
    token = exchange_obo_token(caller_ctx, target_audience="finnapigo-api")

    settings = get_settings()
    # Decoding expecting a different audience should raise InvalidAudienceError
    with pytest.raises(jwt.InvalidAudienceError):
        jwt.decode(
            token,
            settings.JWT_SECRET_KEY,
            algorithms=["HS256"],
            audience="unauthorized-foreign-service",
        )


def test_auth_wrong_issuer_rejected_when_issuer_enforced() -> None:
    """Token with wrong issuer fails issuer verification."""
    token = _mint_jwt(payload_overrides={"iss": "untrusted-rogue-issuer"})
    settings = get_settings()
    with pytest.raises(jwt.InvalidIssuerError):
        jwt.decode(
            token,
            settings.JWT_SECRET_KEY,
            algorithms=["HS256"],
            issuer="trusted-finnapigo-authority",
            options={"verify_aud": False},
        )


# ==============================================================================
# 8. Token Revocation & Redis Denylist Tests
# ==============================================================================


@pytest.mark.asyncio
async def test_auth_revoked_token_jti_rejected(monkeypatch: pytest.MonkeyPatch) -> None:
    """Revoked token with JTI in Redis denylist raises HTTP 401."""
    revoked_token = _mint_jwt(payload_overrides={"jti": "revoked-token-jti-9999"})

    # Mock Redis client
    mock_redis = AsyncMock()
    mock_redis.exists.side_effect = lambda key: (
        key == "denylist:jti:revoked-token-jti-9999"
    )

    import redis.asyncio as aioredis

    monkeypatch.setattr(aioredis, "from_url", lambda *a, **kw: mock_redis)

    with pytest.raises(HTTPException) as exc_info:
        await check_token_denylist(revoked_token)
    assert exc_info.value.status_code == 401
    assert "revoked" in exc_info.value.detail.lower()


@pytest.mark.asyncio
async def test_auth_revoked_session_sid_rejected(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Revoked session SID in Redis denylist raises HTTP 401."""
    revoked_token = _mint_jwt(payload_overrides={"sid": "revoked-session-sid-5555"})

    mock_redis = AsyncMock()
    mock_redis.exists.side_effect = lambda key: (
        key == "denylist:sid:revoked-session-sid-5555"
    )

    import redis.asyncio as aioredis

    monkeypatch.setattr(aioredis, "from_url", lambda *a, **kw: mock_redis)

    with pytest.raises(HTTPException) as exc_info:
        await check_token_denylist(revoked_token)
    assert exc_info.value.status_code == 401
    assert "session has been revoked" in exc_info.value.detail.lower()


# ==============================================================================
# 9. Internal Perimeter Mutual Authentication Tests
# ==============================================================================


def test_auth_internal_perimeter_secret_validation() -> None:
    """Perimeter credential check enforces Invariant 4 mutual authentication."""
    settings = get_settings()
    configured_secret = settings.INTERNAL_GATEWAY_SECRET

    class MockReq:
        def __init__(
            self,
            headers: dict[str, str],
            method: str = "POST",
            path: str = "/internal/v1/coding/resume",
        ) -> None:
            self.headers = headers
            self.method = method
            self.url = type("URL", (), {"path": path})()

    # 1. Missing x-forwarded-by header fails
    req_no_fwd = MockReq({"x-internal-secret": configured_secret})
    assert verify_internal_perimeter_secret(req_no_fwd) is False

    # 2. Wrong x-forwarded-by header fails
    req_wrong_fwd = MockReq(
        {"x-forwarded-by": "untrusted-proxy", "x-internal-secret": configured_secret}
    )
    assert verify_internal_perimeter_secret(req_wrong_fwd) is False

    # 3. Invalid secret fails
    req_bad_sec = MockReq(
        {"x-forwarded-by": "finnapigo", "x-internal-secret": "wrong-secret-value"}
    )
    assert verify_internal_perimeter_secret(req_bad_sec) is False

    # 4. Valid static secret succeeds
    req_valid = MockReq(
        {"x-forwarded-by": "finnapigo", "x-internal-secret": configured_secret}
    )
    assert verify_internal_perimeter_secret(req_valid) is True

    # 5. Timestamped HMAC signature within 60s window succeeds
    now = int(time.time())
    sig = hmac.new(
        configured_secret.encode(),
        f"POST|/internal/v1/coding/resume|{now}".encode(),
        hashlib.sha256,
    ).hexdigest()
    req_hmac = MockReq(
        {
            "x-forwarded-by": "finnapigo",
            "x-internal-sig": f"t={now};v1={sig}",
        }
    )
    assert verify_internal_perimeter_secret(req_hmac) is True

    # 6. Replay attack with expired timestamp (>60s) fails
    old_ts = now - 120
    old_sig = hmac.new(
        configured_secret.encode(),
        f"POST|/internal/v1/coding/resume|{old_ts}".encode(),
        hashlib.sha256,
    ).hexdigest()
    req_replay = MockReq(
        {
            "x-forwarded-by": "finnapigo",
            "x-internal-sig": f"t={old_ts};v1={old_sig}",
        }
    )
    assert verify_internal_perimeter_secret(req_replay) is False


# ==============================================================================
# 10. Billing Webhook HMAC Authentication
# ==============================================================================


@pytest.mark.asyncio
async def test_auth_payos_webhook_invalid_signature_rejected() -> None:
    """PayOS webhook rejects invalid HMAC signatures with HTTP 400."""
    async with AsyncClient(
        transport=ASGITransport(app=app), base_url="http://test"
    ) as client:
        resp = await client.post(
            "/api/v1/billing/webhook",
            json={
                "code": "00",
                "desc": "success",
                "data": {"orderCode": 99999, "amount": 100000},
                "signature": "forged_or_invalid_signature_hex",
            },
        )
        assert resp.status_code == 400
        assert "invalid" in resp.json()["detail"].lower()
