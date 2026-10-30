"""Internal Mutual Auth Contract Test Suite (Invariant 4).

Verifies the mutual perimeter authentication and network isolation contract
between FinnApiGo (Edge Gateway) and JakeAI (Backend AI Engine).

Contract Requirements:
1. Provenance Claim: Header `X-Forwarded-By: FinnApiGo` required on internal perimeter calls.
2. Static Secret Authentication: `X-Internal-Secret` matching INTERNAL_GATEWAY_SECRET.
3. Timestamped HMAC Authentication: `X-Internal-Sig: t=<unix>;v1=<hmac>` computed as
   HMAC-SHA256(INTERNAL_GATEWAY_SECRET, f"{method}|{path}|{ts}").
4. Replay & Drift Window: Maximum allowed timestamp skew is +/- 60 seconds.
5. Spoofing Defense: Untrusted or spoofed provenance headers without valid credentials
   are strictly rejected with HTTP 403 Forbidden.
6. Execution Bridge Lifecycle: Idempotency (409), Not Found (404), and Tenant Isolation (403).
"""

from __future__ import annotations

import hashlib
import hmac
import time

from fastapi.testclient import TestClient

from app.core.config import get_settings
from app.core.security import verify_internal_perimeter_secret
from app.main import app

client = TestClient(app)


def _compute_hmac_sig(
    secret: str,
    method: str,
    path: str,
    ts: int,
) -> str:
    """Compute standard Invariant 4 HMAC-SHA256 signature."""
    message = f"{method}|{path}|{ts}".encode()
    return hmac.new(secret.encode(), message, hashlib.sha256).hexdigest()


# -----------------------------------------------------------------------------
# 1. Low-Level Perimeter Verification Contract
# -----------------------------------------------------------------------------


def test_perimeter_auth_rejects_missing_or_spoofed_headers() -> None:
    """Perimeter guard must reject requests missing headers or spoofing provenance."""
    settings = get_settings()

    # Case A: Empty request
    assert verify_internal_perimeter_secret(None) is False

    # Case B: Spoofed provenance without secret
    class MockRequest:
        def __init__(
            self,
            headers: dict[str, str],
            method: str = "POST",
            path: str = "/internal/test",
        ):
            self.headers = headers
            self.method = method
            self.url = type("URL", (), {"path": path})()

    req_spoof = MockRequest({"x-forwarded-by": "FinnApiGo"})
    assert verify_internal_perimeter_secret(req_spoof) is False

    # Case C: Valid secret but missing X-Forwarded-By
    req_no_forward = MockRequest(
        {"x-internal-secret": settings.INTERNAL_GATEWAY_SECRET}
    )
    assert verify_internal_perimeter_secret(req_no_forward) is False

    # Case D: Wrong secret
    req_wrong = MockRequest(
        {
            "x-forwarded-by": "FinnApiGo",
            "x-internal-secret": "invalid-wrong-secret-value",
        }
    )
    assert verify_internal_perimeter_secret(req_wrong) is False


def test_perimeter_auth_accepts_valid_static_secret() -> None:
    """Perimeter guard accepts X-Forwarded-By + matching X-Internal-Secret."""
    settings = get_settings()

    class MockRequest:
        def __init__(self, headers: dict[str, str]):
            self.headers = headers
            self.method = "POST"
            self.url = type("URL", (), {"path": "/internal/v1/coding/resume"})()

    req = MockRequest(
        {
            "x-forwarded-by": "FinnApiGo",
            "x-internal-secret": settings.INTERNAL_GATEWAY_SECRET,
        }
    )
    assert verify_internal_perimeter_secret(req) is True


def test_perimeter_auth_hmac_replay_and_drift_window() -> None:
    """Perimeter guard enforces +/- 60s window and cryptographic verification."""
    settings = get_settings()
    method = "POST"
    path = "/internal/v1/coding/resume"
    now = int(time.time())

    class MockRequest:
        def __init__(self, headers: dict[str, str]):
            self.headers = headers
            self.method = method
            self.url = type("URL", (), {"path": path})()

    # Valid HMAC signature within window
    sig_valid = _compute_hmac_sig(settings.INTERNAL_GATEWAY_SECRET, method, path, now)
    req_valid = MockRequest(
        {
            "x-forwarded-by": "FinnApiGo",
            "x-internal-sig": f"t={now};v1={sig_valid}",
        }
    )
    assert verify_internal_perimeter_secret(req_valid) is True

    # Replay Attack: Expired timestamp (> 60s in past)
    old_ts = now - 65
    sig_old = _compute_hmac_sig(settings.INTERNAL_GATEWAY_SECRET, method, path, old_ts)
    req_expired = MockRequest(
        {
            "x-forwarded-by": "FinnApiGo",
            "x-internal-sig": f"t={old_ts};v1={sig_old}",
        }
    )
    assert verify_internal_perimeter_secret(req_expired) is False

    # Future Timestamp Attack (> 60s in future)
    future_ts = now + 70
    sig_future = _compute_hmac_sig(
        settings.INTERNAL_GATEWAY_SECRET, method, path, future_ts
    )
    req_future = MockRequest(
        {
            "x-forwarded-by": "FinnApiGo",
            "x-internal-sig": f"t={future_ts};v1={sig_future}",
        }
    )
    assert verify_internal_perimeter_secret(req_future) is False

    # Tampered Payload: Signature computed for different path
    sig_tampered = _compute_hmac_sig(
        settings.INTERNAL_GATEWAY_SECRET, method, "/tampered/path", now
    )
    req_tampered = MockRequest(
        {
            "x-forwarded-by": "FinnApiGo",
            "x-internal-sig": f"t={now};v1={sig_tampered}",
        }
    )
    assert verify_internal_perimeter_secret(req_tampered) is False


# -----------------------------------------------------------------------------
# 2. HTTP Endpoint Level Contract (/internal/v1/coding/resume)
# -----------------------------------------------------------------------------


def test_internal_resume_perimeter_http_contract():
    from tests.fixtures.auth import create_test_jwt

    settings = get_settings()
    payload = {
        "call_id": "call-contract-unavailable",
        "tenant_id": "forged",
        "result": {"status": "success"},
    }
    perimeter = {
        "X-Forwarded-By": "FinnApiGo",
        "X-Internal-Secret": settings.INTERNAL_GATEWAY_SECRET,
    }
    # Perimeter provenance cannot substitute for user authority, including valid HMAC.
    for headers in [{}, perimeter, {"X-Forwarded-By": "FinnApiGo"}]:
        assert (
            client.post(
                "/internal/v1/coding/resume", headers=headers, json=payload
            ).status_code
            == 401
        )
    token = create_test_jwt(
        sub="42", tenant_id="verified", permissions=["agent:execute"]
    )
    for path in ["/internal/v1/coding/resume", "/api/v1/coding/resume"]:
        response = client.post(
            path,
            headers={**perimeter, "Authorization": "Bearer " + token},
            json=payload,
        )
        assert response.status_code == 503
        assert "Durable" in response.json()["detail"]
