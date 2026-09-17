"""PROV-001 (CAT-134) — Real Provider Smoke & Triad Verification Suite.

Strictly separates and verifies:
1. MOCKED: Simulated/mocked provider adapters with synthetic payloads (PASS).
2. LOCAL: In-process local adapters (LocalModelAdapter) and local embeddings (PASS).
3. LIVE: Real external upstream providers (OpenAI, Gemini, Anthropic, DeepSeek, Groq, OpenRouter).
   - Only executed when credentials are deliberately provided through secure CI secrets.
   - A live-provider test with missing credentials must become BLOCKED, NOT PASS.
"""

from __future__ import annotations

import os
from unittest.mock import AsyncMock, MagicMock, patch

import httpx
import pytest

from app.core.config import get_settings
from app.providers.anthropic import AnthropicAdapter
from app.providers.base import (
    ProviderRequest,
    ProviderResponse,
)
from app.providers.deepseek import DeepSeekAdapter
from app.providers.errors import ProviderAuthenticationError
from app.providers.gemini import GeminiAdapter
from app.providers.groq import GroqAdapter
from app.providers.local import LocalModelAdapter
from app.providers.openai import OpenAIAdapter
from app.providers.openrouter import OpenRouterAdapter

# ---------------------------------------------------------------------------
# 1. MOCKED Provider Tests (Zero Network, Pure In-Memory / Mocked Wire)
# ---------------------------------------------------------------------------


@pytest.mark.mocked
@pytest.mark.integration
@pytest.mark.asyncio
async def test_mocked_provider_completion_returns_valid_response() -> None:
    """MOCKED: Verify mocked LLM provider returns compliant response (PASS)."""
    adapter = OpenAIAdapter()
    req = ProviderRequest(
        model="gpt-4o-mini",
        prompt="Hello mock test",
        tenant_id="tenant-mock-01",
        api_key="mock-api-key",
    )

    mock_resp = MagicMock()
    mock_resp.status_code = 200
    mock_resp.json.return_value = {
        "choices": [
            {
                "message": {"role": "assistant", "content": "Mocked OpenAI response"},
                "finish_reason": "stop",
            }
        ],
        "usage": {
            "prompt_tokens": 10,
            "completion_tokens": 5,
            "total_tokens": 15,
            "prompt_tokens_details": {"cached_tokens": 0},
        },
    }

    mock_client = AsyncMock()
    mock_client.post.return_value = mock_resp

    res = await adapter.complete(req, client=mock_client)

    assert isinstance(res, ProviderResponse)
    assert res.text == "Mocked OpenAI response"
    assert res.provider == "openai"
    assert res.telemetry.output_tokens == 5


# ---------------------------------------------------------------------------
# 2. LOCAL Provider Tests (In-Process / On-Premise Local Models)
# ---------------------------------------------------------------------------


@pytest.mark.local_provider
@pytest.mark.integration
def test_local_model_provider_capabilities_and_cost() -> None:
    """LOCAL: Verify local model adapter operates in-process with non-zero compute cost."""
    adapter = LocalModelAdapter(
        endpoint="http://localhost:11434/v1",
        model_name="local-model",
        context_limit=32_768,
        concurrency_limit=4,
        input_pricing=0.10,
        output_pricing=0.20,
    )

    caps = adapter.capabilities("local-model")
    assert caps.provider == "local"
    assert caps.model == "local-model"
    assert caps.context_window == 32_768
    assert caps.input_pricing == 0.10
    assert caps.output_pricing == 0.20


@pytest.mark.local_provider
@pytest.mark.integration
@pytest.mark.asyncio
async def test_local_model_health_probe_evaluation() -> None:
    """LOCAL: Verify local model health probe correctly checks local socket/port."""
    adapter = LocalModelAdapter(
        endpoint="http://localhost:11434/v1",
        model_name="local-llama",
    )

    mock_client = AsyncMock()
    mock_client.get.return_value = MagicMock(status_code=200)

    is_healthy = await adapter.check_health(client=mock_client)
    assert is_healthy is True


# ---------------------------------------------------------------------------
# 3. LIVE Provider Smoke Tests (Real External APIs via Secure CI Secrets)
# ---------------------------------------------------------------------------


@pytest.mark.live_provider(provider="gemini")
@pytest.mark.integration
@pytest.mark.asyncio
async def test_live_gemini_provider_smoke() -> None:
    """LIVE: Real Gemini provider smoke test.

    If GEMINI_API_KEY is not provided via CI secrets, pytest_runtest_setup
    intercepts this test and transitions it strictly to BLOCKED (not PASS).
    """
    settings = get_settings()
    api_key = os.getenv("GEMINI_API_KEY") or settings.GEMINI_API_KEY
    if not api_key:
        pytest.skip("BLOCKED: Missing GEMINI_API_KEY for live provider smoke test.")

    adapter = GeminiAdapter()
    req = ProviderRequest(
        model="gemini-1.5-flash",
        prompt="Respond with the word 'PONG' and nothing else.",
        tenant_id="tenant-live-gemini",
        api_key=api_key,
        max_tokens=10,
    )

    async with httpx.AsyncClient(timeout=10.0) as client:
        with patch.object(adapter, "_get_client", return_value=client):
            res = await adapter.complete(req)

    assert isinstance(res, ProviderResponse)
    assert len(res.text.strip()) > 0
    assert res.provider == "gemini"


@pytest.mark.live_provider(provider="openai")
@pytest.mark.integration
@pytest.mark.asyncio
async def test_live_openai_provider_smoke() -> None:
    """LIVE: Real OpenAI provider smoke test.

    If OPENAI_API_KEY is not provided via CI secrets, pytest_runtest_setup
    intercepts this test and transitions it strictly to BLOCKED (not PASS).
    """
    settings = get_settings()
    api_key = os.getenv("OPENAI_API_KEY") or settings.OPENAI_API_KEY
    if not api_key:
        pytest.skip("BLOCKED: Missing OPENAI_API_KEY for live provider smoke test.")

    adapter = OpenAIAdapter()
    req = ProviderRequest(
        model="gpt-4o-mini",
        prompt="Respond with the word 'PONG' and nothing else.",
        tenant_id="tenant-live-openai",
        api_key=api_key,
        max_tokens=10,
    )

    async with httpx.AsyncClient(timeout=10.0) as client:
        with patch.object(adapter, "_get_client", return_value=client):
            res = await adapter.complete(req)

    assert isinstance(res, ProviderResponse)
    assert len(res.text.strip()) > 0
    assert res.provider == "openai"


@pytest.mark.live_provider(provider="anthropic")
@pytest.mark.integration
@pytest.mark.asyncio
async def test_live_anthropic_provider_smoke() -> None:
    """LIVE: Real Anthropic provider smoke test."""
    settings = get_settings()
    api_key = os.getenv("ANTHROPIC_API_KEY") or getattr(
        settings, "ANTHROPIC_API_KEY", ""
    )
    if not api_key:
        pytest.skip("BLOCKED: Missing ANTHROPIC_API_KEY for live provider smoke test.")

    adapter = AnthropicAdapter()
    req = ProviderRequest(
        model="claude-3-5-sonnet-20241022",
        prompt="Respond with 'PONG'.",
        tenant_id="tenant-live-anthropic",
        api_key=api_key,
        max_tokens=10,
    )

    async with httpx.AsyncClient(timeout=10.0) as client:
        with patch.object(adapter, "_get_client", return_value=client):
            res = await adapter.complete(req)

    assert isinstance(res, ProviderResponse)
    assert len(res.text.strip()) > 0


@pytest.mark.live_provider(provider="deepseek")
@pytest.mark.integration
@pytest.mark.asyncio
async def test_live_deepseek_provider_smoke() -> None:
    """LIVE: Real DeepSeek provider smoke test."""
    settings = get_settings()
    api_key = os.getenv("DEEPSEEK_API_KEY") or getattr(settings, "DEEPSEEK_API_KEY", "")
    if not api_key:
        pytest.skip("BLOCKED: Missing DEEPSEEK_API_KEY for live provider smoke test.")

    adapter = DeepSeekAdapter()
    req = ProviderRequest(
        model="deepseek-chat",
        prompt="Ping.",
        tenant_id="tenant-live-deepseek",
        api_key=api_key,
        max_tokens=10,
    )

    async with httpx.AsyncClient(timeout=10.0) as client:
        with patch.object(adapter, "_get_client", return_value=client):
            res = await adapter.complete(req)

    assert isinstance(res, ProviderResponse)
    assert len(res.text.strip()) > 0


@pytest.mark.live_provider(provider="groq")
@pytest.mark.integration
@pytest.mark.asyncio
async def test_live_groq_provider_smoke() -> None:
    """LIVE: Real Groq provider smoke test."""
    settings = get_settings()
    api_key = os.getenv("GROQ_API_KEY") or getattr(settings, "GROQ_API_KEY", "")
    if not api_key:
        pytest.skip("BLOCKED: Missing GROQ_API_KEY for live provider smoke test.")

    adapter = GroqAdapter()
    req = ProviderRequest(
        model="llama-3.3-70b-versatile",
        prompt="Ping.",
        tenant_id="tenant-live-groq",
        api_key=api_key,
        max_tokens=10,
    )

    async with httpx.AsyncClient(timeout=10.0) as client:
        with patch.object(adapter, "_get_client", return_value=client):
            res = await adapter.complete(req)

    assert isinstance(res, ProviderResponse)
    assert len(res.text.strip()) > 0


@pytest.mark.live_provider(provider="openrouter")
@pytest.mark.integration
@pytest.mark.asyncio
async def test_live_openrouter_provider_smoke() -> None:
    """LIVE: Real OpenRouter provider smoke test."""
    settings = get_settings()
    api_key = os.getenv("OPENROUTER_API_KEY") or getattr(
        settings, "OPENROUTER_API_KEY", ""
    )
    if not api_key:
        pytest.skip("BLOCKED: Missing OPENROUTER_API_KEY for live provider smoke test.")

    adapter = OpenRouterAdapter()
    req = ProviderRequest(
        model="openai/gpt-4o-mini",
        prompt="Ping.",
        tenant_id="tenant-live-openrouter",
        api_key=api_key,
        max_tokens=10,
    )

    async with httpx.AsyncClient(timeout=10.0) as client:
        with patch.object(adapter, "_get_client", return_value=client):
            res = await adapter.complete(req)

    assert isinstance(res, ProviderResponse)
    assert len(res.text.strip()) > 0


# ---------------------------------------------------------------------------
# 4. Invariant: Missing Credentials Must Become BLOCKED, Not PASS
# ---------------------------------------------------------------------------


@pytest.mark.unit
@pytest.mark.asyncio
async def test_live_provider_missing_credentials_fails_with_auth_error_not_pass() -> (
    None
):
    """Verify live provider resolution with zero credentials raises ProviderAuthenticationError.

    A test expecting live credentials must NEVER silently pass if credentials are empty.
    """
    adapter = OpenAIAdapter()
    req = ProviderRequest(
        model="gpt-4o-mini",
        prompt="Ping without credentials",
        tenant_id="tenant-empty-creds",
        api_key="",
    )

    # Empty settings and no BYOK
    with patch("app.core.config.get_settings") as mock_settings:
        mock_settings.return_value.OPENAI_API_KEY = ""
        with pytest.raises(ProviderAuthenticationError) as exc_info:
            await adapter._resolve_api_key(req)

    assert "No OpenAI API key configured" in str(exc_info.value)
