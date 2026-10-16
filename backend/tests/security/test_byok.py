"""BYOK cryptographic, provider and HTTP lifecycle security regressions."""

import json
import secrets

import httpx
import pytest

from app.core import byok
from app.core.byok import SUPPORTED_PROVIDERS, BYOKManager
from app.core.byok_storage import BYOKError, MemoryStore
from app.main import app
from tests.fixtures.auth import create_test_jwt


@pytest.fixture
def manager(monkeypatch):
    value = BYOKManager(store=MemoryStore())
    monkeypatch.setattr(byok, "_byok_manager", value)
    return value


@pytest.fixture
def controlled_probe(monkeypatch):
    original = httpx.AsyncClient

    def factory(**kwargs):
        if "transport" not in kwargs:
            kwargs["transport"] = httpx.MockTransport(lambda _: httpx.Response(200))
        return original(**kwargs)

    monkeypatch.setattr(httpx, "AsyncClient", factory)


@pytest.mark.parametrize("provider", sorted(SUPPORTED_PROVIDERS))
async def test_all_provider_lifecycles(manager, controlled_probe, provider):
    canary, replacement = secrets.token_urlsafe(24), secrets.token_urlsafe(24)
    created = await manager.store_key(
        "lifecycle", provider, canary, validate=True, actor_id="owner"
    )
    assert created["masked_key"] == "********"
    assert created["validation_status"] == "valid"
    assert await manager.get_decrypted_key("lifecycle", provider) == canary
    assert canary not in await manager._get_raw_val("lifecycle", provider)
    assert await manager.validate_stored_key("lifecycle", provider) == (True, None)
    changed = await manager.rotate_key(
        "lifecycle", provider, replacement, validate=True
    )
    assert changed["created_at"] == created["created_at"]
    assert await manager.get_decrypted_key("lifecycle", provider) == replacement
    assert (await manager.revoke_key("lifecycle", provider))["status"] == "revoked"
    with pytest.raises(BYOKError, match="BYOK_REVOKED"):
        await manager.get_decrypted_key("lifecycle", provider)
    with pytest.raises(BYOKError, match="BYOK_REVOKED"):
        await manager.validate_stored_key("lifecycle", provider)
    listed = await manager.list_keys("lifecycle")
    item = next(x for x in listed if x["provider"] == provider)
    assert item["configured"] is False
    assert canary not in json.dumps(listed) and replacement not in json.dumps(listed)
    assert await manager.delete_key("lifecycle", provider)
    assert not await manager.delete_key("lifecycle", provider)
    assert await manager.get_decrypted_key("lifecycle", provider) is None


@pytest.mark.parametrize(
    "field,value",
    [
        ("tenant", "other"),
        ("provider", "anthropic"),
        ("revision", 2),
        ("version", 2),
        ("kid", "unknown"),
        ("payload", "invalid"),
    ],
)
async def test_authenticated_envelope_substitution(manager, field, value):
    canary = secrets.token_urlsafe(24)
    raw = manager.encrypt_key(canary, "bound")
    envelope = json.loads(raw)
    envelope[field] = value
    with pytest.raises(BYOKError):
        manager.decrypt_key(json.dumps(envelope), "bound")
    with pytest.raises(BYOKError):
        manager.decrypt_key(raw, "other")
    other = BYOKManager(
        master_key=__import__("base64").b64encode(secrets.token_bytes(32)).decode(),
        store=MemoryStore(),
    )
    with pytest.raises(BYOKError, match="BYOK_RECORD_CORRUPT"):
        other.decrypt_key(raw, "bound")


@pytest.mark.parametrize(
    "status,valid,error",
    [
        (200, True, None),
        (401, False, "BYOK_PROVIDER_REJECTED"),
        (403, False, "BYOK_PROVIDER_REJECTED"),
        (429, False, "BYOK_PROVIDER_UNAVAILABLE"),
        (500, False, "BYOK_PROVIDER_UNAVAILABLE"),
    ],
)
async def test_provider_validation_is_observed_not_inferred(
    manager, monkeypatch, status, valid, error
):
    original = httpx.AsyncClient
    canary = secrets.token_urlsafe(24)
    monkeypatch.setattr(
        httpx,
        "AsyncClient",
        lambda **kwargs: original(
            transport=httpx.MockTransport(
                lambda _: httpx.Response(status, json={"nested": {"error": canary}})
            ),
            **kwargs,
        ),
    )
    assert await manager.validate_key("openai", canary) == (valid, error)


@pytest.mark.parametrize("value", ["", "x", "short", "a" * 8, "a" * 100])
def test_masking_cannot_reveal_short_keys(value):
    masked = BYOKManager.mask_key(value)
    assert masked == ("********" if value else "")
    if value:
        assert value not in masked


async def test_http_owner_permissions_delegation_and_tenant_boundary(
    manager, controlled_probe, caplog
):
    def headers(user="owner", tenant="tenant-http", perms=None, roles=None):
        token = create_test_jwt(
            sub=user,
            tenant_id=tenant,
            roles=roles or ["member"],
            permissions=perms if perms is not None else ["byok:read", "byok:write"],
        )
        return {"Authorization": f"Bearer {token}", "X-Tenant-ID": "tenant-http"}

    canary = secrets.token_urlsafe(24)
    payload = {"provider": "openai", "api_key": canary, "validate_key": True}
    async with httpx.AsyncClient(
        transport=httpx.ASGITransport(app=app), base_url="http://test"
    ) as client:
        assert (
            await client.post("/api/v1/byok/keys", json=payload, headers=headers())
        ).status_code == 201
        for method, path, data in [
            ("GET", "/keys", None),
            ("POST", "/keys", payload),
            ("POST", "/keys/openai/rotate", {"new_api_key": canary}),
            ("POST", "/keys/openai/revoke", None),
            ("POST", "/keys/openai/validate", None),
            ("DELETE", "/keys/openai", None),
        ]:
            for denied_headers in [
                headers(user="member"),
                headers(roles=["admin"], perms=[]),
                headers(perms=["*"]),
                headers(perms=["byok:manage"]),
            ]:
                response = await client.request(
                    method, "/api/v1/byok" + path, json=data, headers=denied_headers
                )
                assert response.status_code == 403
                assert canary not in response.text
        assert (
            await client.get("/api/v1/byok/keys", headers=headers(perms=["byok:read"]))
        ).status_code == 200
        assert (
            await client.post(
                "/api/v1/byok/keys", json=payload, headers=headers(perms=["byok:read"])
            )
        ).status_code == 403
        assert (
            await client.get("/api/v1/byok/keys", headers=headers(perms=["byok:write"]))
        ).status_code == 403
        other = await client.get("/api/v1/byok/keys", headers=headers(tenant="other"))
        assert other.status_code == 200 and not any(
            x["configured"] for x in other.json()["keys"]
        )
        for suffix in ["/rotate", "/revoke", "/validate"]:
            result = await client.post(
                "/api/v1/byok/keys/openai" + suffix,
                json={"new_api_key": canary},
                headers=headers(tenant="other"),
            )
            assert result.status_code == 404
        assert (
            await client.delete(
                "/api/v1/byok/keys/openai", headers=headers(tenant="other")
            )
        ).status_code == 404
        delegated = headers(user="delegate", roles=["tenant_admin"])
        assert (
            await client.get("/api/v1/byok/keys", headers=delegated)
        ).status_code == 200
        assert (
            await client.post(
                "/api/v1/byok/keys/openai/rotate",
                json={"new_api_key": canary},
                headers=delegated,
            )
        ).status_code == 200
        assert (
            await client.post("/api/v1/byok/keys", json=payload, headers=headers())
        ).status_code == 201
        assert (
            await client.delete("/api/v1/byok/keys/openai", headers=delegated)
        ).status_code == 200
    assert canary not in caplog.text


async def test_bad_inputs_and_absent_key_are_distinct(manager):
    for method in [manager.store_key, manager.rotate_key]:
        with pytest.raises(BYOKError):
            await method("bad", "unknown", "short")
    with pytest.raises(BYOKError, match="BYOK_INVALID_KEY"):
        await manager.store_key("bad", "openai", "short")
    with pytest.raises(BYOKError, match="BYOK_NOT_CONFIGURED"):
        await manager.rotate_key("bad", "openai", "long-enough-synthetic")
    with pytest.raises(BYOKError, match="BYOK_NOT_CONFIGURED"):
        await manager.revoke_key("bad", "openai")
    assert await manager.validate_key("openai", "short") == (False, "BYOK_INVALID_KEY")
    with pytest.raises(BYOKError):
        manager.encrypt_key("", "bad")
    with pytest.raises(BYOKError):
        manager.encrypt_key("long-enough", "")
