"""Strict policy and real application route regressions; state transport is synthetic here.

The separate hosted rehearsal supplies actual Finn/MySQL/Redis/TLS evidence.
"""

import base64
import hashlib
import hmac
import json
import secrets
import time

import httpx
import jwt
import pytest
from fastapi import HTTPException

from app.core.config import Settings, get_settings
from app.core.identity import MANDATORY, configured_keys, verify_access
from app.core.identity_state import IdentityStateClient
from app.core.route_policy import policy_for
from app.main import create_application


@pytest.fixture
def policy(monkeypatch):
    for name, value in {
        "JWT_SECRET_KEY": base64.b64encode(secrets.token_bytes(32)).decode(),
        "JWT_KEY_ID": "sign-current",
        "JWT_ALGORITHM": "HS256",
        "JWT_ISSUER": "finnapigo",
        "JWT_AUDIENCE": "jakeai-service",
        "JWT_SECRET_PREVIOUS": "",
        "JWT_PREVIOUS_KEY_ID": "",
        "IDENTITY_STATE_URL": "https://identity.test/api/v1/identity/introspect",
        "IDENTITY_STATE_KEY_ID": "state-current",
        "IDENTITY_STATE_SECRET": base64.b64encode(secrets.token_bytes(32)).decode(),
        "ENVIRONMENT": "test",
        "BYOK_STORAGE_BACKEND": "memory",
    }.items():
        monkeypatch.setenv(name, value)
    get_settings.cache_clear()
    yield get_settings()
    get_settings.cache_clear()


def claims(**changes):
    now = int(time.time())
    result = {
        "contract_ver": 1,
        "iss": "finnapigo",
        "aud": ["finnapigo-api", "jakeai-service"],
        "sub": "42",
        "uid": 42,
        "tid": "tenant-a",
        "type": "access",
        "iat": now,
        "nbf": now,
        "exp": now + 900,
        "sid": "session",
        "jti": "token",
        "pwdver": 0,
        "auth_epoch": 0,
        "perms": ["chat:read"],
    }
    return {**result, **changes}


def encode(policy, payload=None, header=None):
    return jwt.encode(
        payload or claims(),
        base64.b64decode(policy.JWT_SECRET_KEY),
        algorithm="HS256",
        headers=header or {"kid": policy.JWT_KEY_ID},
    )


def test_actual_finn_key_bytes_and_empty_grants(policy):
    assert verify_access(encode(policy, claims(perms=[])), policy)["perms"] == []
    wrong = jwt.encode(
        claims(),
        policy.JWT_SECRET_KEY,
        algorithm="HS256",
        headers={"kid": policy.JWT_KEY_ID},
    )
    with pytest.raises(jwt.PyJWTError):
        verify_access(wrong, policy)


@pytest.mark.parametrize("name", sorted(MANDATORY))
@pytest.mark.parametrize("replacement", ["missing", None])
def test_every_mandatory_claim_is_explicit(policy, name, replacement):
    payload = claims()
    if replacement == "missing":
        del payload[name]
    else:
        payload[name] = replacement
    with pytest.raises((ValueError, TypeError, jwt.PyJWTError)):
        verify_access(encode(policy, payload), policy)


@pytest.mark.parametrize(
    "changes",
    [
        {"uid": True},
        {"uid": "42"},
        {"sub": 42},
        {"sub": "042"},
        {"pwdver": False},
        {"auth_epoch": -1},
        {"exp": 1.5},
        {"tid": " "},
        {"sid": ""},
        {"jti": None},
        {"perms": None},
        {"perms": "chat:read"},
        {"perms": [True]},
        {"role": ["admin"]},
        {"email": 5},
        {"iss": "FINNAPIGO"},
        {"contract_ver": 2},
        {"type": "service"},
        {"type": "sudo"},
        {"type": "mfa_pending"},
        {"type": "reset"},
        {"type": "email"},
        {"type": "refresh"},
        {"type": "obo"},
        {"aud": ["jakeai-service"]},
        {"aud": ["finnapigo-api", "jakeai-service", "attacker"]},
        {"aud": ["finnapigo-api", "jakeai-service", "jakeai-service"]},
        {"aud": "jakeai-service"},
        {"permissions": []},
        {"tenant_id": "tenant-a"},
        {"roles": []},
        {"scopes": []},
        {"id": "token"},
        {"UID": 42},
        {"ſub": "42"},  # noqa: RUF001 - deliberate Go/Python Unicode authority alias
    ],
)
def test_wrong_types_purpose_aliases_and_audiences(policy, changes):
    with pytest.raises((ValueError, TypeError, jwt.PyJWTError)):
        verify_access(encode(policy, claims(**changes)), policy)


@pytest.mark.parametrize(
    "header",
    [
        {},
        {"kid": "unknown"},
        {"kid": "sign-current", "jku": "https://attacker.test"},
        {"kid": "sign-current", "jwk": {}},
        {"kid": "sign-current", "b64": False},
        {"kid": "sign-current", "KID": "sign-current"},
    ],
)
def test_header_cannot_select_trust(policy, header):
    token = jwt.encode(
        claims(),
        base64.b64decode(policy.JWT_SECRET_KEY),
        algorithm="HS256",
        headers=header,
    )
    with pytest.raises((ValueError, jwt.PyJWTError)):
        verify_access(token, policy)


def test_duplicates_rejected_and_benign_extensions_preserved(policy):
    header = jwt.utils.base64url_encode(
        json.dumps({"alg": "HS256", "kid": policy.JWT_KEY_ID}).encode()
    )
    body = json.dumps(claims())[:-1] + ',"uid":42}'
    payload = jwt.utils.base64url_encode(body.encode())
    signing = header + b"." + payload
    signature = hmac.new(
        base64.b64decode(policy.JWT_SECRET_KEY), signing, hashlib.sha256
    ).digest()
    token = (signing + b"." + jwt.utils.base64url_encode(signature)).decode()
    with pytest.raises(ValueError):
        verify_access(token, policy)
    extension = claims(Extension="one", extension="two")
    assert verify_access(encode(policy, extension), policy)["Extension"] == "one"


def test_ttl_skew_and_immutable_retirement(policy):
    now = int(time.time())
    for payload in [
        claims(exp=now + 901),
        claims(iat=now + 31, nbf=now + 31),
        claims(nbf=now - 1),
        claims(exp=now),
        claims(exp=now - 31, iat=now - 900, nbf=now - 900),
    ]:
        with pytest.raises(ValueError):
            verify_access(encode(policy, payload), policy)
    previous = base64.b64encode(secrets.token_bytes(32)).decode()
    rotated = policy.model_copy(
        update={
            "JWT_SECRET_PREVIOUS": previous,
            "JWT_PREVIOUS_KEY_ID": "old",
            "JWT_PREVIOUS_LAST_ISSUED_AT": now - 929,
        }
    )
    assert "old" in configured_keys(rotated)
    retired = rotated.model_copy(update={"JWT_PREVIOUS_LAST_ISSUED_AT": now - 930})
    assert "old" not in configured_keys(retired)
    recreated = Settings(
        _env_file=None,
        **retired.model_dump(),
        JWT_SECRET_KEY=policy.JWT_SECRET_KEY,
        JWT_SECRET_PREVIOUS=previous,
        IDENTITY_STATE_SECRET=policy.IDENTITY_STATE_SECRET,
    )
    assert "old" not in configured_keys(recreated)


def state_response(payload, **changes):
    result = {
        k: payload[k]
        for k in ("contract_ver", "tid", "sub", "sid", "jti", "pwdver", "auth_epoch")
    }
    return {
        **result,
        "active": True,
        "checked_at": int(time.time()),
        "max_cache_seconds": 15,
        **changes,
    }


@pytest.mark.parametrize(
    "fault,expected",
    [
        ("inactive", 401),
        ("service", 503),
        ("outage", 503),
        ("redirect", 503),
        ("foreign", 503),
        ("stale", 503),
        ("bool", 503),
        ("oversize", 503),
    ],
)
async def test_state_adapter_fails_closed(policy, fault, expected):
    payload = claims()
    adapter = IdentityStateClient(policy)
    await adapter.client.aclose()

    def response(request):
        assert request.headers["X-Service-Key-ID"] == policy.IDENTITY_STATE_KEY_ID
        assert (
            request.headers["Authorization"] == "Bearer " + policy.IDENTITY_STATE_SECRET
        )
        if fault == "inactive":
            return httpx.Response(401, json={"active": False})
        if fault == "service":
            return httpx.Response(401, json={"error": "invalid_service_credential"})
        if fault == "redirect":
            return httpx.Response(
                302, headers={"Location": "https://attacker.test"}, json={}
            )
        if fault == "outage":
            raise httpx.ConnectError("synthetic outage")
        if fault == "oversize":
            return httpx.Response(200, content=b"x" * 4097)
        changes = {
            "foreign": {"sub": "43"},
            "stale": {"checked_at": int(time.time()) - 16},
            "bool": {"pwdver": False},
        }[fault]
        return httpx.Response(200, json=state_response(payload, **changes))

    adapter.client = httpx.AsyncClient(transport=httpx.MockTransport(response))
    with pytest.raises(HTTPException) as error:
        await adapter.check(encode(policy), payload)
    assert error.value.status_code == expected
    await adapter.close()


async def application(policy):
    app = create_application()
    adapter = IdentityStateClient(policy)
    await adapter.client.aclose()

    def response(request):
        payload = jwt.decode(
            json.loads(request.content)["token"], options={"verify_signature": False}
        )
        return httpx.Response(200, json=state_response(payload))

    adapter.client = httpx.AsyncClient(transport=httpx.MockTransport(response))
    app.state.identity_client = adapter
    return app, adapter


async def test_every_actual_protected_route_denies_empty_grants(policy):
    app, adapter = await application(policy)
    total = 0
    async with httpx.AsyncClient(
        transport=httpx.ASGITransport(app=app), base_url="http://test"
    ) as client:
        for path, operations in app.openapi()["paths"].items():
            for method in operations:
                rule = policy_for(method.upper(), path)
                assert rule is not None, (method, path)
                if not isinstance(rule, tuple):
                    continue
                total += 1
                url = (
                    path.replace("{task_id}", "absent")
                    .replace("{run_id}", "absent")
                    .replace("{approval_id}", "absent")
                    .replace("{provider}", "openai")
                )
                for role in ("member", "admin", "tenant_admin", "approver"):
                    token = encode(policy, claims(perms=[], role=role))
                    response = await client.request(
                        method, url, headers={"Authorization": "Bearer " + token}
                    )
                    assert response.status_code == 403, (
                        method,
                        path,
                        role,
                        response.status_code,
                    )
    assert total >= 40
    await adapter.close()


async def test_actual_owner_default_and_alias_paths(policy):
    app, adapter = await application(policy)
    async with httpx.AsyncClient(
        transport=httpx.ASGITransport(app=app), base_url="http://test"
    ) as client:
        token = encode(
            policy,
            claims(tid="default", perms=["agent:write", "agent:read", "chat:read"]),
        )
        headers = {"Authorization": "Bearer " + token, "X-Tenant-ID": "attacker"}
        created = await client.post(
            "/api/v1/agent/tasks",
            json={"goal": "synthetic read-only task"},
            headers=headers,
        )
        assert created.status_code == 201
        task = created.json()
        assert task["tenant_id"] == "default" and task["user_id"] == "42"
        url = "/api/v1/agent/tasks/" + task["task_id"]
        assert (await client.get(url, headers=headers)).status_code == 200
        for changes in ({"sub": "43", "uid": 43}, {"tid": "tenant-b"}):
            foreign = (
                encode(policy, claims(tid="default", perms=["agent:read"], **changes))
                if "tid" not in changes
                else encode(policy, claims(perms=["agent:read"], **changes))
            )
            assert (
                await client.get(url, headers={"Authorization": "Bearer " + foreign})
            ).status_code == 404
        assert (await client.get("/v1/models", headers=headers)).status_code == 200
        assert (
            await client.get("/api/v1/gateway/models", headers=headers)
        ).status_code == 200
        assert (await client.get("/metrics", headers=headers)).status_code == 404
        assert (
            await client.post(
                "/internal/v1/coding/resume",
                json={"tenant_id": "attacker"},
                headers=headers,
            )
        ).status_code == 403
    await adapter.close()
