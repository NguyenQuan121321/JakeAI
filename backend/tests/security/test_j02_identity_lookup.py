"""Security equivalence at the real decoder, signed JWT and ASGI request seams."""

import base64
import hashlib
import hmac
import json
import random
import secrets
import time

import httpx
import jwt
import pytest

from app.core.config import get_settings
from app.core.identity import CLAIMS, HEADERS, unique_object, verify_access
from app.core.identity_state import IdentityStateClient
from app.main import create_application
from tests.fixtures.identity_reference import original_unique_object


def outcome(decoder, raw, names):
    try:
        return ("return", json.dumps(decoder(raw, names), sort_keys=True))
    except (ValueError, UnicodeError, RecursionError) as error:
        return (type(error).__name__, str(error))


def adversarial_objects():
    raw = [
        "{}",
        "[]",
        "null",
        "1",
        "{",
        '{"a":1,"a":2}',
        '{"nested":{"a":1,"a":2}}',
        '{"nested":[{"a":1,"a":2}]}',
        '{"value":NaN}',
        '{"value":Infinity}',
        '{"value":-Infinity}',
        '{"value":1e999}',
        '{"nested":{"value":NaN}}',
        '{"a":01}',
        '{"extension":' + "[" * 2000 + "0" + "]" * 2000 + "}",
    ]
    keys = set(CLAIMS | HEADERS) | {
        "Extension",
        "extension",
        "\u017fub",
        "\u212aID",
        "ss",
        "\u00df",
        "\u03a3",
        "\u03c2",
        "\u03c3",
    }
    for name in sorted(keys):
        for variant in (name, name.upper(), name.title(), name.swapcase()):
            raw.append(json.dumps({variant: {"extension": [0, True, None, "value"]}}))
    rng = random.Random(407)
    ordered = sorted(keys)
    for _ in range(100):
        chosen = rng.sample(ordered, 4)
        raw.append(json.dumps({name: rng.randrange(100) for name in chosen}))
    return raw


@pytest.mark.parametrize(
    "names",
    [
        CLAIMS,
        HEADERS,
        frozenset(),
        frozenset({"a", "A"}),
        frozenset({"ss", "\u00df"}),
        frozenset({"k", "\u212a"}),
        frozenset({"custom", "\u017fub", "Stra\u00dfe"}),
        frozenset({"extension", "Extension", "\u03c3"}),
    ],
)
def test_adversarial_corpus_matches_frozen_preoptimization_decoder(names):
    cases = adversarial_objects()
    for raw in cases:
        for encoded in (raw, raw.encode(), raw.encode("utf-16")):
            assert outcome(unique_object, encoded, names) == outcome(
                original_unique_object, encoded, names
            )
    for raw in (b"\xff", b'{"a":"\xff"}', b"\x00"):
        assert outcome(unique_object, raw, names) == outcome(
            original_unique_object, raw, names
        )


@pytest.mark.parametrize(
    "key,names,allowed",
    [
        ("\u00df", frozenset({"\u00df"}), True),
        ("ss", frozenset({"\u00df"}), False),
        ("ss", frozenset({"ss", "\u00df"}), False),
        ("\u00df", frozenset({"ss", "\u00df"}), False),
        ("\u017fub", CLAIMS, False),
        ("\u212aID", HEADERS, False),
        ("Extension", CLAIMS, True),
    ],
)
def test_custom_name_sets_preserve_unicode_and_colliding_canonical_names(
    key, names, allowed
):
    raw = json.dumps({key: 42})
    if allowed:
        assert unique_object(raw, names) == {key: 42}
    else:
        with pytest.raises(ValueError, match="Ambiguous authority member"):
            unique_object(raw, names)


def test_arbitrary_name_sets_do_not_reuse_another_sets_authority():
    assert unique_object('{"UID":1}', frozenset({"unrelated"})) == {"UID": 1}
    with pytest.raises(ValueError, match="Ambiguous authority member"):
        unique_object('{"UID":1}', frozenset({"uid"}))
    assert unique_object('{"UID":1}', frozenset({"UID"})) == {"UID": 1}


@pytest.fixture
def policy(monkeypatch):
    for name, value in {
        "JWT_SECRET_KEY": base64.b64encode(secrets.token_bytes(32)).decode(),
        "JWT_KEY_ID": "lookup-current",
        "JWT_ALGORITHM": "HS256",
        "JWT_ISSUER": "finnapigo",
        "JWT_AUDIENCE": "jakeai-service",
        "JWT_SECRET_PREVIOUS": "",
        "JWT_PREVIOUS_KEY_ID": "",
        "IDENTITY_STATE_URL": "https://identity.test/api/v1/identity/introspect",
        "IDENTITY_STATE_KEY_ID": "lookup-state",
        "IDENTITY_STATE_SECRET": base64.b64encode(secrets.token_bytes(32)).decode(),
        "ENVIRONMENT": "test",
        "BYOK_STORAGE_BACKEND": "memory",
    }.items():
        monkeypatch.setenv(name, value)
    monkeypatch.delenv("JWT_PREVIOUS_LAST_ISSUED_AT", raising=False)
    get_settings.cache_clear()
    yield get_settings()
    get_settings.cache_clear()


def claims(**changes):
    now = int(time.time())
    return {
        "contract_ver": 1,
        "iss": "finnapigo",
        "aud": ["finnapigo-api", "jakeai-service"],
        "sub": "42",
        "uid": 42,
        "tid": "lookup-tenant",
        "type": "access",
        "iat": now,
        "nbf": now,
        "exp": now + 900,
        "sid": "lookup-session",
        "jti": "lookup-token",
        "pwdver": 0,
        "auth_epoch": 0,
        "perms": ["chat:read", "chat:write"],
        **changes,
    }


def signed(policy, header, body):
    message = b".".join(
        jwt.utils.base64url_encode(part.encode()) for part in (header, body)
    )
    signature = hmac.new(
        base64.b64decode(policy.JWT_SECRET_KEY), message, hashlib.sha256
    ).digest()
    return (message + b"." + jwt.utils.base64url_encode(signature)).decode()


def token_parts(policy):
    return json.dumps(
        {"alg": "HS256", "kid": policy.JWT_KEY_ID, "typ": "JWT"}
    ), json.dumps(claims())


BAD_MEMBERS = [
    ("header", '"KID":"lookup-current"'),
    ("header", '"\\u212aID":"lookup-current"'),
    ("header", '"kid":"lookup-current"'),
    ("header", '"alg":"HS256"'),
    ("header", '"extension":{"x":1,"x":2}'),
    ("header", '"extension":NaN'),
    ("claims", '"UID":42'),
    ("claims", '"\\u017fub":"42"'),
    ("claims", '"PerMs":["chat:read"]'),
    ("claims", '"uid":42'),
    ("claims", '"tenant_id":"lookup-tenant"'),
    ("claims", '"extension":{"x":1,"x":2}'),
    ("claims", '"extension":Infinity'),
]


@pytest.mark.parametrize("part,member", BAD_MEMBERS)
def test_actual_signed_ambiguous_headers_and_claims_are_denied(policy, part, member):
    header, body = token_parts(policy)
    if part == "header":
        header = header[:-1] + "," + member + "}"
    else:
        body = body[:-1] + "," + member + "}"
    with pytest.raises((ValueError, jwt.PyJWTError)):
        verify_access(signed(policy, header, body), policy)


def test_real_verifier_accepts_canonical_extensions_and_rechecks_signature_time_and_key(
    policy, monkeypatch
):
    header, body = token_parts(policy)
    token = signed(policy, header, body[:-1] + ',"Extension":1,"extension":2}')
    assert verify_access(token, policy)["uid"] == 42
    other = policy.model_copy(
        update={"JWT_SECRET_KEY": base64.b64encode(secrets.token_bytes(32)).decode()}
    )
    with pytest.raises(jwt.PyJWTError):
        verify_access(token, other)
    now = time.time()
    monkeypatch.setattr(time, "time", lambda: now + 931)
    with pytest.raises(ValueError, match="Invalid access lifetime"):
        verify_access(token, policy)


async def application(policy):
    app = create_application()
    adapter = IdentityStateClient(policy)
    await adapter.client.aclose()
    observed = []
    active = [True]

    def authority(request):
        payload = jwt.decode(
            json.loads(request.content)["token"], options={"verify_signature": False}
        )
        observed.append(payload["jti"])
        if not active[0]:
            return httpx.Response(401, json={"active": False})
        response = {
            name: payload[name]
            for name in (
                "contract_ver",
                "tid",
                "sub",
                "sid",
                "jti",
                "pwdver",
                "auth_epoch",
            )
        }
        return httpx.Response(
            200,
            json={
                **response,
                "active": True,
                "checked_at": int(time.time()),
                "max_cache_seconds": 15,
            },
        )

    adapter.client = httpx.AsyncClient(transport=httpx.MockTransport(authority))
    app.state.identity_client = adapter
    return app, adapter, observed, active


@pytest.mark.parametrize("part,member", BAD_MEMBERS)
async def test_actual_chat_request_rejects_signed_ambiguity_before_state_or_body_validation(
    policy, part, member
):
    app, adapter, observed, _ = await application(policy)
    header, body = token_parts(policy)
    if part == "header":
        header = header[:-1] + "," + member + "}"
    else:
        body = body[:-1] + "," + member + "}"
    try:
        async with httpx.AsyncClient(
            transport=httpx.ASGITransport(app=app), base_url="http://test"
        ) as client:
            response = await client.post(
                "/api/v1/gateway/chat/completions",
                headers={"Authorization": "Bearer " + signed(policy, header, body)},
                json={},
            )
        assert response.status_code == 401
        assert observed == []
    finally:
        await adapter.close()


async def test_real_request_accepts_canonical_token_but_never_reuses_a_positive_authorization(
    policy,
):
    app, adapter, observed, active = await application(policy)
    header, body = token_parts(policy)
    token = signed(policy, header, body)
    try:
        async with httpx.AsyncClient(
            transport=httpx.ASGITransport(app=app), base_url="http://test"
        ) as client:
            auth = {"Authorization": "Bearer " + token}
            for _ in range(2):
                assert (await client.get("/v1/models", headers=auth)).status_code == 200
            assert len(observed) >= 2
            no_grant = signed(policy, header, json.dumps(claims(perms=[])))
            assert (
                await client.post(
                    "/api/v1/gateway/chat/completions",
                    headers={"Authorization": "Bearer " + no_grant},
                    json={},
                )
            ).status_code == 403
            padded = token.split(".")
            padded[1] += "="
            assert (
                await client.get(
                    "/v1/models",
                    headers={"Authorization": "Bearer " + ".".join(padded)},
                )
            ).status_code == 401
            active[0] = False
            assert (await client.get("/v1/models", headers=auth)).status_code == 401
    finally:
        await adapter.close()
