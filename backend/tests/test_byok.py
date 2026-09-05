"""Unit and integration tests for BYOK (Bring Your Own Key) & AES-256-GCM encryption."""

import pytest
from httpx import ASGITransport, AsyncClient

from app.core.byok import BYOKManager
from app.core.context import TenantContext
from app.core.security import exchange_obo_token
from app.main import app


@pytest.fixture
def auth_headers() -> dict[str, str]:
    context = TenantContext(
        tenant_id="tenant-byok-test",
        user_id="user-123",
        roles=["admin"],
        scopes=["chat:write", "keys:write"],
        permissions=["byok:manage"],
    )
    token = exchange_obo_token(context)
    return {"Authorization": f"Bearer {token}"}


@pytest.mark.asyncio
async def test_byok_aes256_gcm_roundtrip():
    """Verify AES-256-GCM encryption and decryption roundtrip."""
    manager = BYOKManager(master_key="test-master-secret-key-32-chars!")
    tenant_id = "tenant-alpha"
    api_key = "sk-proj-abc123xyz789SECRETKEY000"

    encrypted = manager.encrypt_key(api_key, tenant_id)
    assert encrypted != api_key
    assert len(encrypted) > 20

    decrypted = manager.decrypt_key(encrypted, tenant_id)
    assert decrypted == api_key


@pytest.mark.asyncio
async def test_byok_cross_tenant_isolation_fails():
    """Verify decryption fails when attempted by an unauthorized tenant (AAD mismatch)."""
    manager = BYOKManager()
    tenant_alpha = "tenant-alpha"
    tenant_beta = "tenant-beta"
    api_key = "sk-proj-super-secret-key-12345"

    encrypted = manager.encrypt_key(api_key, tenant_alpha)

    # Attempt decrypting with wrong tenant must raise ValueError
    with pytest.raises(ValueError, match="Failed to decrypt key"):
        manager.decrypt_key(encrypted, tenant_beta)


@pytest.mark.asyncio
async def test_byok_corrupt_payload_fails():
    """Verify corrupt or truncated payload fails gracefully."""
    manager = BYOKManager()
    with pytest.raises(ValueError):
        manager.decrypt_key("dG9vc2hvcnQ=", "tenant-1")  # too short

    with pytest.raises(ValueError):
        manager.encrypt_key("", "tenant-1")


def test_byok_key_masking():
    """Verify provider key masking preserves privacy."""
    assert BYOKManager.mask_key("sk-proj-1234567890abcdef") == "sk-...cdef"
    assert BYOKManager.mask_key("AIzaSyB1234567890") == "AI...7890"
    assert BYOKManager.mask_key("short") == "sk-***"
    assert BYOKManager.mask_key("") == ""


@pytest.mark.asyncio
async def test_byok_store_and_retrieve():
    """Verify storing and retrieving provider keys via BYOKManager."""
    manager = BYOKManager()
    tenant_id = "tenant-storage-test"

    # Store
    res = await manager.store_key(tenant_id, "openai", "sk-test-secret-key-999")
    assert res["provider"] == "openai"
    assert res["status"] == "configured"
    assert res["masked_key"] == "sk-...-999"

    # Retrieve decrypted
    decrypted = await manager.get_decrypted_key(tenant_id, "openai")
    assert decrypted == "sk-test-secret-key-999"

    # List
    keys_list = await manager.list_keys(tenant_id)
    openai_item = next(k for k in keys_list if k["provider"] == "openai")
    assert openai_item["configured"] is True
    assert openai_item["masked_key"] == "sk-...-999"

    # Unsupported provider
    with pytest.raises(ValueError, match="Unsupported provider"):
        await manager.store_key(tenant_id, "unsupported_ai", "key123")

    # Delete
    deleted = await manager.delete_key(tenant_id, "openai")
    assert deleted is True

    # After delete
    assert await manager.get_decrypted_key(tenant_id, "openai") is None


@pytest.mark.asyncio
async def test_byok_api_endpoints(auth_headers: dict[str, str]):
    """Verify BYOK REST endpoints: POST, GET, DELETE."""
    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test") as client:
        # 1. Register key
        post_res = await client.post(
            "/api/v1/byok/keys",
            json={"provider": "gemini", "api_key": "AIzaSyTestApiKey987654321"},
            headers=auth_headers,
        )
        assert post_res.status_code == 201
        data = post_res.json()
        assert data["provider"] == "gemini"
        assert data["status"] == "configured"
        assert "4321" in data["masked_key"]

        # 2. List keys
        get_res = await client.get("/api/v1/byok/keys", headers=auth_headers)
        assert get_res.status_code == 200
        list_data = get_res.json()
        assert list_data["tenant_id"] == "tenant-byok-test"
        gemini_item = next(k for k in list_data["keys"] if k["provider"] == "gemini")
        assert gemini_item["configured"] is True

        # 3. Delete key
        del_res = await client.delete("/api/v1/byok/keys/gemini", headers=auth_headers)
        assert del_res.status_code == 200
        assert del_res.json()["status"] == "revoked"

        # 4. Delete non-existent key
        del_res2 = await client.delete("/api/v1/byok/keys/gemini", headers=auth_headers)
        assert del_res2.status_code == 404

        # 5. Invalid provider
        bad_res = await client.post(
            "/api/v1/byok/keys",
            json={"provider": "unknown_ai", "api_key": "somekey123456"},
            headers=auth_headers,
        )
        assert bad_res.status_code == 400
