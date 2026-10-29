"""Credential-source canaries through adapters and the real HTTP error boundary."""

import base64
import importlib
import logging
import secrets
import traceback
from types import SimpleNamespace

import httpx
import pytest
from fastapi import Depends

from app.core import byok
from app.core.byok import BYOKManager
from app.core.byok_storage import MemoryStore
from app.core.config import get_settings
from app.core.security import get_current_tenant
from app.main import create_application
from app.providers.base import ProviderRequest
from app.providers.errors import ProviderError
from tests.fixtures.auth import create_test_jwt


@pytest.fixture
def vault(monkeypatch):
    monkeypatch.setenv("JWT_SECRET_KEY", secrets.token_hex(32))
    monkeypatch.setenv(
        "BYOK_MASTER_KEY", base64.b64encode(secrets.token_bytes(32)).decode()
    )
    monkeypatch.setenv("BYOK_MASTER_KEY_ID", "source-canary")
    monkeypatch.setenv("BYOK_STORAGE_BACKEND", "memory")
    monkeypatch.setenv("ENVIRONMENT", "test")
    monkeypatch.setenv("REDIS_URL", "redis://127.0.0.1:1/0")
    for name in ["GROQ_API_KEY", "DEEPSEEK_API_KEY", "OPENROUTER_API_KEY"]:
        monkeypatch.delenv(name, raising=False)
    get_settings.cache_clear()
    manager = BYOKManager(store=MemoryStore())
    monkeypatch.setattr(byok, "_byok_manager", manager)
    yield manager
    get_settings.cache_clear()


@pytest.mark.parametrize(
    "provider,adapter_name",
    [
        ("groq", "GroqAdapter"),
        ("deepseek", "DeepSeekAdapter"),
        ("openrouter", "OpenRouterAdapter"),
    ],
)
@pytest.mark.parametrize("source", ["explicit", "byok", "configured", "environment"])
@pytest.mark.parametrize("method", ["complete", "stream"])
@pytest.mark.parametrize("fault", ["nested", "timeout"])
async def test_every_credential_source_is_redacted_through_http(
    vault, monkeypatch, caplog, provider, adapter_name, source, method, fault
):
    module = importlib.import_module("app.providers." + provider)
    adapter = getattr(module, adapter_name)()
    # Deliberately lacks a regex-recognizable provider prefix.
    canary = "credential." + secrets.token_urlsafe(24)
    name = provider.upper() + "_API_KEY"
    if source == "byok":
        await vault.store_key(
            "source-tenant",
            provider,
            canary,
            actor_id=str(
                int(__import__("hashlib").sha256(b"owner").hexdigest()[:12], 16) + 1
            ),
        )
    elif source == "configured":
        # Exercise the adapter's configured-provider boundary independently of
        # its existing raw-environment fallback. Authentication is not replaced.
        monkeypatch.setattr(
            module, "get_settings", lambda: SimpleNamespace(**{name: canary})
        )
    elif source == "environment":
        monkeypatch.setenv(name, canary)

    observed = []

    def upstream(request):
        if request.headers.get("Authorization") != "Bearer " + canary:
            pytest.fail(
                "Resolved credential was not injected into the controlled request"
            )
        observed.append(True)
        if fault == "timeout":
            raise httpx.ReadTimeout(canary, request=request)
        return httpx.Response(
            401, json={"error": {"message": canary, "nested": {"credential": canary}}}
        )

    from app.core.route_policy import USER_POLICY

    monkeypatch.setitem(
        USER_POLICY, ("GET", "/_fixture/provider-error"), ("chat:write",)
    )
    app = create_application()
    diagnostics = []

    @app.get("/_fixture/provider-error", dependencies=[Depends(get_current_tenant)])
    async def provider_probe():
        request = ProviderRequest(
            tenant_id="source-tenant",
            model="synthetic",
            prompt="fixture",
            api_key=canary if source == "explicit" else None,
        )
        async with httpx.AsyncClient(transport=httpx.MockTransport(upstream)) as client:
            try:
                if method == "complete":
                    await adapter.complete(request, client=client)
                else:
                    async for _ in adapter.stream(request, client=client):
                        pytest.fail("An upstream error produced a success chunk")
            except ProviderError as error:
                diagnostics.append(
                    str(error)
                    + repr(vars(error))
                    + "".join(traceback.format_exception(error))
                )
                logging.getLogger("credential-regression").error("%s", error)
                raise
        pytest.fail("An upstream error produced success")

    token = create_test_jwt(
        sub="owner", tenant_id="source-tenant", permissions=["chat:write"]
    )
    async with httpx.AsyncClient(
        transport=httpx.ASGITransport(app=app), base_url="http://test"
    ) as client:
        response = await client.get(
            "/_fixture/provider-error", headers={"Authorization": "Bearer " + token}
        )
    assert observed and diagnostics
    assert response.status_code == (401 if fault == "nested" else 408)
    assert response.json()["error"]["provider"] == provider
    if any(canary in value for value in [*diagnostics, response.text, caplog.text]):
        pytest.fail(
            "Credential canary leaked through normalized diagnostics, HTTP body or logs"
        )
