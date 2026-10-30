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

import base64
import binascii
import hashlib
import hmac
import json
import time
from typing import Any

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
    try:
        key = base64.b64decode(secret or settings.JWT_SECRET_KEY)
    except binascii.Error:
        key = (secret or settings.JWT_SECRET_KEY).encode()
    now = int(time.time())
    payload: dict[str, Any] = {
        "contract_ver": 1,
        "iss": "finnapigo",
        "aud": ["finnapigo-api", "jakeai-service"],
        "sub": "42",
        "uid": 42,
        "tid": "tenant-sec-auth",
        "type": "access",
        "role": "developer",
        "perms": ["chat:read", "agent:read"],
        "iat": now,
        "nbf": now,
        "exp": now + 900,
        "sid": "session",
        "jti": "token",
        "pwdver": 0,
        "auth_epoch": 0,
    }
    if payload_overrides:
        payload.update(payload_overrides)
    return jwt.encode(
        payload,
        key,
        algorithm=algorithm,
        headers=headers or {"kid": settings.JWT_KEY_ID},
    )


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
    assert "invalid access credential" in exc_info.value.detail.lower()

    # Token with empty string subject
    empty_sub_token = _mint_jwt(payload_overrides={"sub": "", "uid": ""})
    with pytest.raises(HTTPException) as exc_info:
        verify_finnapigo_jwt(empty_sub_token)
    assert exc_info.value.status_code == 401
    assert "invalid access credential" in exc_info.value.detail.lower()


def test_auth_wrong_token_type_rejected() -> None:
    """Tokens with type != 'access' (e.g., refresh or id_token) fail closed with HTTP 401."""
    # Refresh token passed as access token
    refresh_token = _mint_jwt(payload_overrides={"type": "refresh"})
    with pytest.raises(HTTPException) as exc_info:
        verify_finnapigo_jwt(refresh_token)
    assert exc_info.value.status_code == 401
    assert "invalid access credential" in exc_info.value.detail.lower()

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
    assert "invalid access credential" in exc_info.value.detail.lower()


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
        assert "invalid access credential" in resp.json()["detail"].lower()


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
    assert "invalid access credential" in exc_info.value.detail.lower()


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


def test_auth_key_rotation_accepts_previous_secret(monkeypatch):
    import secrets

    settings = get_settings()
    previous = base64.b64encode(secrets.token_bytes(32)).decode()
    monkeypatch.setattr(settings, "JWT_SECRET_PREVIOUS", previous)
    monkeypatch.setattr(settings, "JWT_PREVIOUS_KEY_ID", "previous")
    monkeypatch.setattr(settings, "JWT_PREVIOUS_LAST_ISSUED_AT", int(time.time()))
    token = _mint_jwt(secret=previous, headers={"kid": "previous"})
    context = verify_finnapigo_jwt(token)
    assert context.user_id == "42" and context.tenant_id == "tenant-sec-auth"


def test_auth_kid_header_matching():
    assert verify_finnapigo_jwt(_mint_jwt()).user_id == "42"
    with pytest.raises(HTTPException) as error:
        verify_finnapigo_jwt(_mint_jwt(headers={"kid": "unknown"}))
    assert error.value.status_code == 401


# ==============================================================================
# 7. Issuer and Audience Verification in OBO Token Exchange
# ==============================================================================


def test_auth_obo_token_exchange_and_claims_verification():
    caller = TenantContext(
        tenant_id="tenant-obo-sec", user_id="42", roles=["admin"], permissions=["*"]
    )
    with pytest.raises(HTTPException) as error:
        exchange_obo_token(caller, target_audience="finnapigo-api")
    assert error.value.status_code == 503


def test_auth_wrong_audience_rejected_when_audience_enforced():
    with pytest.raises(HTTPException) as error:
        verify_finnapigo_jwt(_mint_jwt({"aud": ["finnapigo-api"]}))
    assert error.value.status_code == 401


def test_auth_wrong_issuer_rejected_when_issuer_enforced():
    with pytest.raises(HTTPException) as error:
        verify_finnapigo_jwt(_mint_jwt({"iss": "rogue"}))
    assert error.value.status_code == 401


# ==============================================================================
# 8. Token Revocation & Redis Denylist Tests
# ==============================================================================


@pytest.mark.asyncio
async def test_auth_revoked_token_jti_rejected():
    from app.core.identity import verify_access
    from app.core.identity_state import AuthorityLease, current_authority

    token = _mint_jwt({"jti": "revoked"})

    class State:
        settings = get_settings()

        async def check(self, candidate, claims):
            assert candidate == token and claims["jti"] == "revoked"
            raise HTTPException(401, "Inactive access credential")

    binding = current_authority.set(
        AuthorityLease(token, verify_access(token, get_settings()), State())
    )
    try:
        with pytest.raises(HTTPException) as error:
            await check_token_denylist(token)
        assert error.value.status_code == 401
    finally:
        current_authority.reset(binding)


@pytest.mark.asyncio
async def test_auth_revoked_session_sid_rejected():
    from app.core.identity import verify_access
    from app.core.identity_state import AuthorityLease, current_authority

    token = _mint_jwt({"sid": "revoked"})

    class State:
        settings = get_settings()

        async def check(self, candidate, claims):
            assert candidate == token and claims["sid"] == "revoked"
            raise HTTPException(401, "Inactive access credential")

    binding = current_authority.set(
        AuthorityLease(token, verify_access(token, get_settings()), State())
    )
    try:
        with pytest.raises(HTTPException) as error:
            await check_token_denylist(token)
        assert error.value.status_code == 401
    finally:
        current_authority.reset(binding)


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


@pytest.mark.parametrize("environment", ["development", "test", "local", "production"])
@pytest.mark.parametrize("padding", ["", "="])
@pytest.mark.parametrize(
    "explicit_key", [None, "unrelated-short-lived-test-signing-key"]
)
def test_retired_playground_token_is_inert(
    environment: str,
    padding: str,
    explicit_key: str | None,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Retired synthetic demo credential is rejected even with base64 padding variants."""
    settings = get_settings()
    monkeypatch.setattr(settings, "ENVIRONMENT", environment)
    header = jwt.utils.base64url_encode(b'{"alg":"HS256","typ":"JWT"}').decode()
    payload = {
        "sub": "user-demo-001",
        "uid": 101,
        "tid": "tenant-demo",
        "role": "admin",
        "perms": ["chat:write", "rag:read"],
        "type": "access",
        "exp": 253402300799,
    }
    body = jwt.utils.base64url_encode(
        json.dumps(payload, separators=(",", ":")).encode()
    ).decode()
    # Original signature only, retained to regress explicit revocation; no signing key.
    signature = "vjTAyaIxrc6JwGmere5k8Up9kADaamq27HPSVU6wi3c"
    retired = f"{header}.{body}.{signature}{padding}"
    with pytest.raises(HTTPException, match="Invalid access credential") as error:
        verify_finnapigo_jwt(retired, secret_key=explicit_key)
    assert error.value.status_code == 401
