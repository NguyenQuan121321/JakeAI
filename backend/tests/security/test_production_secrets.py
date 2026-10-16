"""Production provisioning negatives without reading host/live credentials."""

import base64
import hashlib
import json
import secrets

import pytest

from app.core.config import Settings


def provisioned():
    return {
        "ENVIRONMENT": "production",
        "JWT_SECRET_KEY": secrets.token_hex(32),
        "INTERNAL_GATEWAY_SECRET": secrets.token_hex(32),
        "FINNAPIGO_SERVICE_SECRET": secrets.token_hex(32),
        "AUDIT_HMAC_KEY": secrets.token_hex(32),
        "BYOK_MASTER_KEY": base64.b64encode(secrets.token_bytes(32)).decode(),
        "BYOK_MASTER_KEY_ID": "synthetic-current",
        "BYOK_STORAGE_BACKEND": "redis",
        "BYOK_REDIS_URL": "redis://synthetic-only:6379/0",
        "BYOK_PREVIOUS_KEYS": {},
        "BYOK_RETIRED_KEY_IDS": [],
        "BYOK_RETIRED_KEY_HASHES": [],
    }


def test_provisioned_production_and_masked_configuration_diagnostics():
    values = provisioned()
    settings = Settings(_env_file=None, **values)
    diagnostics = (
        repr(settings)
        + str(settings)
        + json.dumps(settings.model_dump())
        + settings.model_dump_json()
    )
    for field in [
        "JWT_SECRET_KEY",
        "INTERNAL_GATEWAY_SECRET",
        "FINNAPIGO_SERVICE_SECRET",
        "AUDIT_HMAC_KEY",
        "BYOK_MASTER_KEY",
    ]:
        assert values[field] not in diagnostics


@pytest.mark.parametrize(
    "field",
    [
        "JWT_SECRET_KEY",
        "INTERNAL_GATEWAY_SECRET",
        "FINNAPIGO_SERVICE_SECRET",
        "AUDIT_HMAC_KEY",
        "BYOK_MASTER_KEY",
    ],
)
@pytest.mark.parametrize(
    "invalid",
    ["", "replace-with-prod-secret-min-32-chars", "a" * 64, "00" * 32, "not-a-key"],
)
def test_required_production_material_rejected(field, invalid):
    values = provisioned()
    values[field] = invalid
    with pytest.raises(ValueError) as caught:
        Settings(_env_file=None, **values)
    if invalid:
        assert invalid not in str(caught.value)


@pytest.mark.parametrize(
    "field",
    [
        "INTERNAL_GATEWAY_SECRET",
        "FINNAPIGO_SERVICE_SECRET",
        "AUDIT_HMAC_KEY",
        "JWT_SECRET_PREVIOUS",
    ],
)
def test_purpose_separation_rejects_reuse(field):
    values = provisioned()
    values[field] = values["JWT_SECRET_KEY"]
    with pytest.raises(ValueError):
        Settings(_env_file=None, **values)


def test_purpose_separation_compares_decoded_bytes_and_previous_keys():
    values = provisioned()
    values["BYOK_MASTER_KEY"] = base64.b64encode(
        bytes.fromhex(values["JWT_SECRET_KEY"])
    ).decode()
    with pytest.raises(ValueError):
        Settings(_env_file=None, **values)
    values = provisioned()
    values["BYOK_PREVIOUS_KEYS"] = {"old": values["BYOK_MASTER_KEY"]}
    with pytest.raises(ValueError):
        Settings(_env_file=None, **values)


@pytest.mark.parametrize(
    "change",
    [
        {"BYOK_MASTER_KEY_ID": ""},
        {"BYOK_STORAGE_BACKEND": "memory"},
        {"BYOK_REDIS_URL": ""},
        {"BYOK_RETIRED_KEY_IDS": ["synthetic-current"]},
        {"BYOK_PREVIOUS_KEYS": {"old": "placeholder"}},
    ],
)
def test_production_key_ring_and_storage_constraints(change):
    with pytest.raises(ValueError):
        Settings(_env_file=None, **(provisioned() | change))


def test_compromised_master_cannot_be_renamed_or_reactivated():
    values = provisioned()
    values["BYOK_RETIRED_KEY_HASHES"] = [
        hashlib.sha256(base64.b64decode(values["BYOK_MASTER_KEY"])).hexdigest()
    ]
    with pytest.raises(ValueError):
        Settings(_env_file=None, **values)


def test_legacy_compose_name_cannot_configure_actual_master(monkeypatch):
    values = provisioned()
    values["BYOK_MASTER_KEY"] = ""
    monkeypatch.setenv(
        "BYOK_ENCRYPTION_MASTER_KEY", base64.b64encode(secrets.token_bytes(32)).decode()
    )
    with pytest.raises(ValueError):
        Settings(_env_file=None, **values)


def test_signing_retirement_guard_has_no_explicit_key_or_environment_bypass(
    monkeypatch,
):
    import time

    import jwt
    from fastapi import HTTPException

    from app.core import secret_material
    from app.core.config import get_settings
    from app.core.security import verify_finnapigo_jwt

    # Add a synthetic compromised key to the real retirement inventory. This
    # exercises all verifier paths without publishing credentials or depending
    # on historical Git objects absent from shallow CI checkouts. Actual public
    # key probes and reviewed immutable digests are recorded in J01/J03 evidence.
    published = secrets.token_hex(32)
    monkeypatch.setattr(
        secret_material,
        "RETIRED_SIGNING_KEY_SHA256",
        secret_material.RETIRED_SIGNING_KEY_SHA256
        | {hashlib.sha256(published.encode()).hexdigest()},
    )
    token = jwt.encode(
        {"sub": "synthetic", "tid": "synthetic", "exp": int(time.time()) + 60},
        published,
        algorithm="HS256",
    )
    for environment in ["production", "development", "test", "local"]:
        monkeypatch.setattr(get_settings(), "ENVIRONMENT", environment)
        with pytest.raises(HTTPException) as caught:
            verify_finnapigo_jwt(token, secret_key=published, algorithm="HS256")
        assert caught.value.status_code == 401
    with pytest.raises(ValueError):
        Settings(_env_file=None, JWT_SECRET_KEY=published, ENVIRONMENT="development")
