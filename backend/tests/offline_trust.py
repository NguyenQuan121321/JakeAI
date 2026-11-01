"""Provision before importing app/fixture packages with eager initializers."""

import base64
import os
import secrets


def provision_offline_trust() -> None:
    if os.environ.get("ENVIRONMENT", "development").lower() not in {
        "test",
        "development",
    }:
        raise RuntimeError("Offline trust cannot configure production")
    # Never consume repository signing/encryption secrets in offline tests.
    for name in ("JWT_SECRET_KEY", "BYOK_MASTER_KEY"):
        os.environ[name] = base64.b64encode(secrets.token_bytes(32)).decode()
    for name in (
        "INTERNAL_GATEWAY_SECRET",
        "FINNAPIGO_SERVICE_SECRET",
        "AUDIT_HMAC_KEY",
    ):
        os.environ[name] = secrets.token_hex(32)
    os.environ.update(
        JWT_KEY_ID="offline-current",
        JWT_ALGORITHM="HS256",
        JWT_ISSUER="finnapigo",
        JWT_AUDIENCE="jakeai-service",
        BYOK_MASTER_KEY_ID="offline-vault",
        BYOK_STORAGE_BACKEND="memory",
    )
    for name in (
        "JWT_SECRET_PREVIOUS",
        "JWT_PREVIOUS_KEY_ID",
        "JWT_PREVIOUS_LAST_ISSUED_AT",
        "FINNAPIGO_JWT_SECRET",
        "FINNAPIGO_SECRET_KEY",
    ):
        os.environ.pop(name, None)
