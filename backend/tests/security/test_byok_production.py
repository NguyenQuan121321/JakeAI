"""J03 regressions at the real configuration, storage and HTTP seams."""

import base64
import json
import secrets
import traceback
from unittest.mock import AsyncMock

import pytest
from httpx import ASGITransport, AsyncClient

from app.core import byok
from app.core.byok import BYOKManager
from app.core.config import Settings, get_settings
from app.main import app
from tests.fixtures.auth import create_test_jwt


@pytest.fixture(autouse=True)
def synthetic_config(monkeypatch):
    monkeypatch.setenv(
        "BYOK_MASTER_KEY", base64.b64encode(secrets.token_bytes(32)).decode()
    )
    monkeypatch.setenv("BYOK_STORAGE_BACKEND", "memory")
    monkeypatch.setenv("BYOK_MASTER_KEY_ID", "synthetic-current")
    monkeypatch.setenv("JWT_SECRET_KEY", secrets.token_hex(32))
    get_settings.cache_clear()
    monkeypatch.setattr(byok, "_byok_manager", None)
    yield
    get_settings.cache_clear()


def test_production_rejects_missing_required_secrets():
    with pytest.raises(ValueError):
        Settings(_env_file=None, ENVIRONMENT="production")


@pytest.mark.asyncio
async def test_default_manager_roundtrip():
    manager = BYOKManager()
    canary = secrets.token_urlsafe(24)
    await manager.store_key("roundtrip", "openai", canary)
    assert await manager.get_decrypted_key("roundtrip", "openai") == canary


@pytest.mark.asyncio
async def test_provider_substitution_is_rejected():
    manager = BYOKManager()
    await manager.store_key("substitution", "openai", secrets.token_urlsafe(24))
    raw = await manager._get_raw_val("substitution", "openai")
    await manager._save_raw_val("substitution", "anthropic", raw)
    with pytest.raises(ValueError):
        await manager.get_decrypted_key("substitution", "anthropic")


@pytest.mark.asyncio
async def test_corruption_is_not_not_configured():
    manager = BYOKManager()
    await manager._save_raw_val("corrupt", "openai", "invalid ciphertext")
    with pytest.raises(ValueError):
        await manager.get_decrypted_key("corrupt", "openai")


@pytest.mark.asyncio
async def test_test_named_keys_require_actual_validation(monkeypatch):
    manager = BYOKManager()
    client = AsyncMock()
    client.__aenter__.return_value.get.side_effect = OSError("offline")
    monkeypatch.setattr("app.core.byok.httpx.AsyncClient", lambda **kwargs: client)
    valid, _ = await manager.validate_key(
        "openai", "sk-test-" + secrets.token_urlsafe(24)
    )
    assert valid is False


@pytest.mark.asyncio
async def test_real_http_admin_role_cannot_replace_exact_permission():
    token = create_test_jwt(tenant_id="policy", roles=["admin"], permissions=[])
    async with AsyncClient(
        transport=ASGITransport(app=app), base_url="http://test"
    ) as client:
        response = await client.post(
            "/api/v1/byok/keys",
            json={"provider": "openai", "api_key": secrets.token_urlsafe(24)},
            headers={"Authorization": f"Bearer {token}"},
        )
    assert response.status_code == 403


@pytest.mark.asyncio
async def test_real_http_validation_errors_do_not_echo_nested_short_secrets():
    token = create_test_jwt(tenant_id="errors", permissions=["byok:write"])
    canary = secrets.token_hex(2)
    async with AsyncClient(
        transport=ASGITransport(app=app), base_url="http://test"
    ) as client:
        response = await client.post(
            "/api/v1/byok/keys",
            json={
                "provider": "openai",
                "api_key": canary,
                "nested": {"api_key": canary},
            },
            headers={"Authorization": f"Bearer {token}"},
        )
    assert response.status_code == 422
    assert canary not in json.dumps(response.json())


@pytest.mark.asyncio
@pytest.mark.parametrize("fault", ["nested", "timeout"])
async def test_actual_provider_injection_and_error_diagnostics_mask_canary(fault):
    import httpx

    from app.providers.base import ProviderRequest
    from app.providers.errors import ProviderError
    from app.providers.openai import OpenAIAdapter

    canary = secrets.token_urlsafe(24)
    manager = byok.get_byok_manager()
    await manager.store_key("injection", "openai", canary)

    def handler(request):
        assert request.headers["Authorization"] == f"Bearer {canary}"
        if fault == "timeout":
            raise httpx.ReadTimeout(canary, request=request)
        return httpx.Response(
            401, json={"error": {"message": canary, "nested": {"credential": canary}}}
        )

    async with httpx.AsyncClient(transport=httpx.MockTransport(handler)) as client:
        with pytest.raises(ProviderError) as caught:
            await OpenAIAdapter().complete(
                ProviderRequest(
                    tenant_id="injection", model="gpt-4o-mini", prompt="synthetic"
                ),
                client=client,
            )
    diagnostics = (
        str(caught.value)
        + repr(vars(caught.value))
        + "".join(traceback.format_exception(caught.value))
    )
    assert canary not in diagnostics, (
        "Provider diagnostics leaked the synthetic credential"
    )


def test_injected_credential_is_absent_from_request_exports():
    from app.providers.base import ProviderRequest

    canary = secrets.token_urlsafe(24)
    request = ProviderRequest(model="synthetic", api_key=canary)
    assert canary not in repr(request) + request.model_dump_json(), (
        "Credential leaked through request diagnostics/export"
    )


@pytest.mark.asyncio
async def test_storage_outage_never_acknowledges_process_memory_write(monkeypatch):
    monkeypatch.setenv("BYOK_STORAGE_BACKEND", "redis")
    monkeypatch.setenv("BYOK_REDIS_URL", "redis://127.0.0.1:1/0")
    monkeypatch.setenv("REDIS_URL", "redis://127.0.0.1:1/0")
    get_settings.cache_clear()
    manager = BYOKManager()
    with pytest.raises(ValueError):
        await manager.store_key("outage", "openai", secrets.token_urlsafe(24))
    if hasattr(manager, "store"):
        await manager.store.client.aclose()
