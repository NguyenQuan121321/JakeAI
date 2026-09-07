"""Unit and integration tests for BYOK (Bring Your Own Key) & AES-256-GCM encryption."""

import json

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


@pytest.fixture
def auth_headers_tenant_b() -> dict[str, str]:
    context = TenantContext(
        tenant_id="tenant-byok-victim-beta",
        user_id="user-456",
        roles=["admin"],
        scopes=["chat:write", "keys:write"],
        permissions=["byok:manage"],
    )
    token = exchange_obo_token(context)
    return {"Authorization": f"Bearer {token}"}


@pytest.mark.asyncio
async def test_byok_all_six_providers_lifecycle():
    """Verify full key lifecycle across all 6 supported providers: openai, anthropic, gemini, groq, deepseek, openrouter."""
    manager = BYOKManager()
    tenant = "tenant-six-providers"

    providers_and_keys = {
        "openai": "sk-test-openai-key-alpha-9999",
        "anthropic": "sk-ant-test-claude-key-beta-8888",
        "gemini": "AIzaSyTestGeminiKeyGamma-7777",
        "groq": "gsk_test-groq-lpu-key-delta-6666",
        "deepseek": "sk-test-deepseek-r1-key-epsilon-5555",
        "openrouter": "sk-or-test-openrouter-key-zeta-4444",
    }

    # 1. Create / Store all 6 keys
    for prov, key in providers_and_keys.items():
        res = await manager.store_key(tenant, prov, key, validate=True)
        assert res["provider"] == prov
        assert res["status"] == "configured"
        assert res["validation_status"] == "valid"
        assert res["masked_key"] != key

    # 2. Use / Transiently decrypt all 6 keys
    for prov, key in providers_and_keys.items():
        decrypted = await manager.get_decrypted_key(tenant, prov)
        assert decrypted == key

    # 3. Rotate a key (groq)
    new_groq_key = "gsk_test-groq-rotated-key-new-1111"
    rotate_res = await manager.rotate_key(tenant, "groq", new_groq_key, validate=True)
    assert rotate_res["provider"] == "groq"
    assert rotate_res["status"] == "configured"
    assert "1111" in rotate_res["masked_key"]
    assert await manager.get_decrypted_key(tenant, "groq") == new_groq_key

    # 4. Revoke a key (deepseek) - runtime inference blocked
    revoke_res = await manager.revoke_key(tenant, "deepseek")
    assert revoke_res["status"] == "revoked"
    assert await manager.get_decrypted_key(tenant, "deepseek") is None

    # 5. List keys - verify statuses
    keys_list = await manager.list_keys(tenant)
    by_prov = {k["provider"]: k for k in keys_list}
    assert len(by_prov) == 6
    assert by_prov["openai"]["configured"] is True
    assert by_prov["openai"]["status"] == "active"
    assert by_prov["deepseek"]["status"] == "revoked"

    # 6. Delete keys
    for prov in providers_and_keys:
        deleted = await manager.delete_key(tenant, prov)
        assert deleted is True
        assert await manager.get_decrypted_key(tenant, prov) is None


@pytest.mark.asyncio
async def test_byok_strict_tenant_isolation():
    """Verify strict multi-tenant isolation: Tenant B cannot read, invoke, or mutate Tenant A's keys."""
    manager = BYOKManager()
    tenant_a = "tenant-company-a"
    tenant_b = "tenant-company-b"

    # Tenant A registers OpenAI and Anthropic keys
    await manager.store_key(tenant_a, "openai", "sk-test-company-a-secret-1234")
    await manager.store_key(tenant_a, "anthropic", "sk-ant-test-company-a-secret-5678")

    # Tenant B tries to get decrypted keys -> must return None
    assert await manager.get_decrypted_key(tenant_b, "openai") is None
    assert await manager.get_decrypted_key(tenant_b, "anthropic") is None

    # Tenant B listing keys must show configured=False for all
    b_keys = await manager.list_keys(tenant_b)
    for k in b_keys:
        assert k["configured"] is False
        assert k["masked_key"] is None

    # Tenant B cannot revoke or rotate Tenant A's key
    with pytest.raises(ValueError, match="No key found"):
        await manager.revoke_key(tenant_b, "openai")

    with pytest.raises(ValueError, match="No existing key found"):
        await manager.rotate_key(tenant_b, "openai", "sk-test-rogue-b-new-key-0000")

    # Tenant B deleting returns False
    assert await manager.delete_key(tenant_b, "openai") is False

    # Tenant A's key remains completely unaffected and active
    assert (
        await manager.get_decrypted_key(tenant_a, "openai")
        == "sk-test-company-a-secret-1234"
    )


@pytest.mark.asyncio
async def test_byok_quota_preserving_probe_and_format_validation():
    """Verify validation performs fast format check and lightweight probe without burning quota."""
    manager = BYOKManager()

    # 1. Invalid short key
    valid, err = await manager.validate_key("openai", "short")
    assert valid is False
    assert "at least 8 characters" in (err or "")

    # 2. Invalid prefix for Anthropic
    valid, err = await manager.validate_key("anthropic", "sk-wrong-prefix-key-12345")
    assert valid is False
    assert "expected prefix 'sk-ant-'" in (err or "")

    # 3. Invalid prefix for Groq
    valid, err = await manager.validate_key("groq", "wrong-groq-key-1234567")
    assert valid is False
    assert "expected prefix 'gsk_'" in (err or "")

    # 4. Valid mock key passes fast check
    valid, err = await manager.validate_key("groq", "gsk_test-mock-valid-groq-key-9999")
    assert valid is True
    assert err is None


@pytest.mark.asyncio
async def test_byok_api_extended_lifecycle(
    auth_headers: dict[str, str],
    auth_headers_tenant_b: dict[str, str],
):
    """Verify extended REST API: validate candidate, store with validation, rotate, revoke, delete."""
    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test") as client:
        # 1. Candidate validation endpoint
        val_res = await client.post(
            "/api/v1/byok/keys/validate",
            json={"provider": "groq", "api_key": "gsk_test-mock-key-12345678"},
            headers=auth_headers,
        )
        assert val_res.status_code == 200
        assert val_res.json()["is_valid"] is True

        # 2. Store with live validation flag
        store_res = await client.post(
            "/api/v1/byok/keys",
            json={
                "provider": "openrouter",
                "api_key": "sk-or-test-mock-key-abcdef123456",
                "validate_key": True,
            },
            headers=auth_headers,
        )
        assert store_res.status_code == 201
        assert store_res.json()["validation_status"] == "valid"

        # 3. Validate stored key endpoint
        val_stored = await client.post(
            "/api/v1/byok/keys/openrouter/validate",
            headers=auth_headers,
        )
        assert val_stored.status_code == 200
        assert val_stored.json()["is_valid"] is True

        # 4. Rotate key endpoint
        rot_res = await client.post(
            "/api/v1/byok/keys/openrouter/rotate",
            json={
                "new_api_key": "sk-or-test-mock-rotated-key-998877",
                "validate_key": True,
            },
            headers=auth_headers,
        )
        assert rot_res.status_code == 200
        assert "8877" in rot_res.json()["masked_key"]

        # 5. Cross-tenant access: Tenant B cannot revoke Tenant A's key
        b_revoke = await client.post(
            "/api/v1/byok/keys/openrouter/revoke",
            headers=auth_headers_tenant_b,
        )
        assert b_revoke.status_code == 404

        # 6. Tenant A revokes key
        a_revoke = await client.post(
            "/api/v1/byok/keys/openrouter/revoke",
            headers=auth_headers,
        )
        assert a_revoke.status_code == 200
        assert a_revoke.json()["status"] == "revoked"

        # 7. Validating a revoked key returns 404
        val_revoked = await client.post(
            "/api/v1/byok/keys/openrouter/validate",
            headers=auth_headers,
        )
        assert val_revoked.status_code == 404

        # 8. Clean up / delete key
        del_res = await client.delete(
            "/api/v1/byok/keys/openrouter",
            headers=auth_headers,
        )
        assert del_res.status_code == 200
        assert del_res.json()["status"] == "revoked"


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


@pytest.mark.asyncio
async def test_byok_network_probe_mocked(monkeypatch: pytest.MonkeyPatch):
    """Verify live HTTP probe responses (200, 401, 429, 500, timeout, network error)."""
    from unittest.mock import AsyncMock

    import httpx

    manager = BYOKManager()
    real_key = "sk-live-synthetic-sample-key-12345678"

    # 1. Mock 200 OK
    mock_resp_200 = httpx.Response(
        200, request=httpx.Request("GET", "https://api.openai.com/v1/models")
    )
    mock_client = AsyncMock()
    mock_client.__aenter__.return_value.get.return_value = mock_resp_200
    monkeypatch.setattr(httpx, "AsyncClient", lambda **kwargs: mock_client)

    is_valid, err = await manager.validate_key("openai", real_key)
    assert is_valid is True
    assert err is None

    # 2. Mock 401 Unauthorized
    mock_resp_401 = httpx.Response(
        401, request=httpx.Request("GET", "https://api.openai.com/v1/models")
    )
    mock_client.__aenter__.return_value.get.return_value = mock_resp_401
    is_valid, err = await manager.validate_key("openai", real_key)
    assert is_valid is False
    assert "Authentication failed" in (err or "")

    # 3. Mock 429 Rate Limit
    mock_resp_429 = httpx.Response(
        429, request=httpx.Request("GET", "https://api.openai.com/v1/models")
    )
    mock_client.__aenter__.return_value.get.return_value = mock_resp_429
    is_valid, err = await manager.validate_key("openai", real_key)
    assert is_valid is True
    assert "rate limit or quota" in (err or "")

    # 4. Mock 500 Server Error
    mock_resp_500 = httpx.Response(
        500, request=httpx.Request("GET", "https://api.openai.com/v1/models")
    )
    mock_client.__aenter__.return_value.get.return_value = mock_resp_500
    is_valid, err = await manager.validate_key("openai", real_key)
    assert is_valid is False
    assert "status code 500" in (err or "")

    # 5. Mock TimeoutException
    mock_client.__aenter__.return_value.get.side_effect = httpx.TimeoutException(
        "timeout"
    )
    is_valid, err = await manager.validate_key("openai", real_key)
    assert is_valid is False
    assert "timed out" in (err or "")

    # 6. Mock RequestError
    mock_client.__aenter__.return_value.get.side_effect = httpx.RequestError(
        "connect fail"
    )
    is_valid, err = await manager.validate_key("openai", real_key)
    assert is_valid is False
    assert "unreachable" in (err or "")


@pytest.mark.asyncio
async def test_byok_zero_secret_leakage():
    """Verify raw API keys are never exposed in list responses or exception messages."""
    manager = BYOKManager()
    tenant = "tenant-leak-audit"
    secret_key = "sk-ant-test-super-secret-production-key-99999"

    # Store key
    res = await manager.store_key(tenant, "anthropic", secret_key)
    assert secret_key not in json.dumps(res)
    assert res["masked_key"] != secret_key

    # List keys
    keys_list = await manager.list_keys(tenant)
    serialized_list = json.dumps(keys_list)
    assert secret_key not in serialized_list

    # Attempt decrypting with wrong tenant: exception must not contain secret
    encrypted = manager.encrypt_key(secret_key, tenant)
    try:
        manager.decrypt_key(encrypted, "wrong-tenant-id")
    except ValueError as exc:
        assert secret_key not in str(exc)


@pytest.mark.asyncio
async def test_byok_legacy_plain_ciphertext_backward_compat():
    """Verify backward compatibility when storage contains legacy raw base64 ciphertext."""
    manager = BYOKManager()
    tenant = "tenant-legacy-test"
    raw_key = "sk-test-legacy-secret-key-1111"

    # Encrypt directly without JSON record wrapper
    raw_ciphertext = manager.encrypt_key(raw_key, tenant)
    redis = await manager._get_redis()
    if redis is not None:
        await redis.set(f"byok:{tenant}:openai", raw_ciphertext)
    manager._memory_store.setdefault(tenant, {})["openai"] = raw_ciphertext

    try:
        # get_decrypted_key must unpack and decrypt correctly
        assert await manager.get_decrypted_key(tenant, "openai") == raw_key

        # list_keys must report configured=True with valid masked key
        keys = await manager.list_keys(tenant)
        openai_item = next(k for k in keys if k["provider"] == "openai")
        assert openai_item["configured"] is True
        assert "1111" in (openai_item["masked_key"] or "")
    finally:
        await manager.delete_key(tenant, "openai")


@pytest.mark.asyncio
async def test_byok_corrupt_data_in_store_handled_gracefully():
    """Verify corrupt ciphertext in storage reports configured=False and status=corrupt without crashing."""
    manager = BYOKManager()
    tenant = "tenant-corrupt-test"

    # Insert corrupt non-decryptable string
    corrupt_val = "not-a-valid-ciphertext"
    redis = await manager._get_redis()
    if redis is not None:
        await redis.set(f"byok:{tenant}:openai", corrupt_val)
    manager._memory_store.setdefault(tenant, {})["openai"] = corrupt_val

    try:
        keys = await manager.list_keys(tenant)
        openai_item = next(k for k in keys if k["provider"] == "openai")
        assert openai_item["configured"] is False
        assert openai_item["status"] == "corrupt"
        assert openai_item["masked_key"] == "sk-corrupt"
    finally:
        await manager.delete_key(tenant, "openai")


@pytest.mark.asyncio
async def test_byok_redis_fallback_to_memory_when_redis_empty_or_errors():
    """Verify that when Redis is queried and returns None or errors, manager falls back to _memory_store."""
    manager = BYOKManager()
    tenant = "tenant-fallback-test"
    key = "sk-test-fallback-openai-key-2222"

    # Store only in memory, not in Redis
    packed = manager._pack_record(
        ciphertext=manager.encrypt_key(key, tenant),
        masked_key=manager.mask_key(key),
        status="active",
        created_at=None,
        updated_at=None,
        last_validated_at=None,
        validation_status="untested",
    )
    manager._memory_store.setdefault(tenant, {})["openai"] = packed

    try:
        # Ensure get_decrypted_key falls back to memory
        decrypted = await manager.get_decrypted_key(tenant, "openai")
        assert decrypted == key

        # Ensure list_keys falls back to memory
        keys = await manager.list_keys(tenant)
        openai_item = next(k for k in keys if k["provider"] == "openai")
        assert openai_item["configured"] is True
        assert "2222" in (openai_item["masked_key"] or "")
    finally:
        await manager.delete_key(tenant, "openai")
