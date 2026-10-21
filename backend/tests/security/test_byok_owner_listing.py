"""Independent credential owners retain metadata access without foreign disclosure."""

import base64
import os
import secrets
import uuid

import httpx
import pytest

from app.core import byok
from app.core.byok import BYOKManager
from app.core.byok_storage import MemoryStore, RedisStore
from app.core.config import get_settings
from app.main import create_application
from tests.fixtures.auth import create_test_jwt


@pytest.fixture(params=["memory", "redis"])
async def vault(request, monkeypatch):
    monkeypatch.setenv("JWT_SECRET_KEY", secrets.token_hex(32))
    monkeypatch.setenv(
        "BYOK_MASTER_KEY", base64.b64encode(secrets.token_bytes(32)).decode()
    )
    monkeypatch.setenv("BYOK_MASTER_KEY_ID", "owner-listing")
    get_settings.cache_clear()
    if request.param == "redis":
        url = os.getenv("J03_REDIS_URL")
        if not url:
            pytest.skip(
                "BLOCKED: isolated J03_REDIS_URL required for actual Redis owner listing"
            )
        store = RedisStore(url)
        await store.check()
    else:
        store = MemoryStore()
    manager = BYOKManager(store=store)
    monkeypatch.setattr(byok, "_byok_manager", manager)
    tenant = "owners-" + uuid.uuid4().hex
    try:
        yield manager, tenant
    finally:
        for provider in ["openai", "gemini"]:
            await manager.delete_key(tenant, provider)
        if isinstance(store, RedisStore):
            await store.client.aclose()
        get_settings.cache_clear()


async def test_mixed_owners_read_only_their_own_masks(vault):
    _, tenant = vault
    app = create_application()

    def headers(user, *, other=False, delegate=False, permissions=None):
        token = create_test_jwt(
            sub=user,
            tenant_id=tenant + "-foreign" if other else tenant,
            roles=["tenant_admin"] if delegate else ["member"],
            permissions=["byok:read", "byok:write"]
            if permissions is None
            else permissions,
        )
        return {"Authorization": "Bearer " + token, "X-Tenant-ID": tenant}

    async with httpx.AsyncClient(
        transport=httpx.ASGITransport(app=app), base_url="http://test"
    ) as client:
        for owner, provider in [("alice", "openai"), ("bob", "gemini")]:
            response = await client.post(
                "/api/v1/byok/keys",
                headers=headers(owner),
                json={"provider": provider, "api_key": secrets.token_urlsafe(24)},
            )
            assert response.status_code == 201
        for owner, provider in [("alice", "openai"), ("bob", "gemini")]:
            response = await client.get("/api/v1/byok/keys", headers=headers(owner))
            assert response.status_code == 200
            rows = response.json()["keys"]
            assert [row["provider"] for row in rows] == [provider]
            assert rows[0]["masked_key"] == "********"
            assert rows[0]["configured"] is True
        for identity in [headers("member"), headers("alice", other=True)]:
            response = await client.get("/api/v1/byok/keys", headers=identity)
            assert response.status_code == 200
            assert response.json()["keys"] == []
        assert (
            await client.get(
                "/api/v1/byok/keys",
                headers=headers("admin", delegate=True, permissions=[]),
            )
        ).status_code == 403
        admin = await client.get(
            "/api/v1/byok/keys", headers=headers("admin", delegate=True)
        )
        assert admin.status_code == 200
        assert {
            row["provider"] for row in admin.json()["keys"] if row["configured"]
        } == {"openai", "gemini"}
        assert (
            await client.delete("/api/v1/byok/keys/openai", headers=headers("bob"))
        ).status_code == 403
        assert (
            await client.delete(
                "/api/v1/byok/keys/gemini", headers=headers("alice", other=True)
            )
        ).status_code == 404
        # Foreign existence must not change the member's list or manufacture an
        # unconfigured entry which distinguishes hidden from nonexistent slots.
        assert (
            await client.delete("/api/v1/byok/keys/gemini", headers=headers("bob"))
        ).status_code == 200
        assert (
            await client.get("/api/v1/byok/keys", headers=headers("member"))
        ).json()["keys"] == []
