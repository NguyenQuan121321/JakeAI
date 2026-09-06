"""Tests verifying cross-layer architectural harmonization and synchronization.

Guarantees consistent singleton usage, unified upstream LLM dispatching,
and shared in-memory retriever/cache state across agents and endpoints.
"""

from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from app.agents import supervisor
from app.api.v1.endpoints import chat
from app.core.config import get_settings
from app.core.llm_provider import call_upstream_llm
from app.optimizer.semantic_cache import get_semantic_cache_manager
from app.rag.retriever import default_hybrid_retriever, get_hybrid_retriever
from app.services.ai_gateway import GatewayChatRequest, get_gateway_proxy


def test_singleton_harmonization() -> None:
    """Verify that all components share identical singleton instances."""
    # 1. Hybrid Retriever Singleton
    assert get_hybrid_retriever() is default_hybrid_retriever
    assert supervisor._retriever is default_hybrid_retriever

    # 2. Semantic Cache Singleton
    cache_mgr = get_semantic_cache_manager()
    assert chat._semantic_cache is cache_mgr
    proxy = get_gateway_proxy()
    assert proxy.cache_mgr is cache_mgr


@pytest.mark.asyncio
async def test_call_upstream_llm_gemini_success() -> None:
    """Verify call_upstream_llm dispatches correctly to Google Gemini."""
    mock_resp = MagicMock()
    mock_resp.status_code = 200
    mock_resp.json.return_value = {
        "candidates": [{"content": {"parts": [{"text": "Gemini Financial Analysis"}]}}]
    }

    settings = get_settings()
    with (
        patch("httpx.AsyncClient.post", new_callable=AsyncMock, return_value=mock_resp),
        patch.object(settings, "GEMINI_API_KEY", "fake-gemini-key"),
    ):
        res = await call_upstream_llm(
            prompt="Analyze EBITDA",
            tenant_id="tenant-test",
            model="gemini-1.5-flash",
        )
        assert res == "Gemini Financial Analysis"


@pytest.mark.asyncio
async def test_call_upstream_llm_openai_success() -> None:
    """Verify call_upstream_llm dispatches correctly to OpenAI."""
    mock_resp = MagicMock()
    mock_resp.status_code = 200
    mock_resp.json.return_value = {
        "choices": [{"message": {"content": "OpenAI Market Report"}}]
    }

    settings = get_settings()
    with (
        patch("httpx.AsyncClient.post", new_callable=AsyncMock, return_value=mock_resp),
        patch.object(settings, "OPENAI_API_KEY", "fake-openai-key"),
    ):
        res = await call_upstream_llm(
            prompt="Market report",
            tenant_id="tenant-test",
            model="gpt-4o-mini",
        )
        assert res == "OpenAI Market Report"


@pytest.mark.asyncio
async def test_call_upstream_llm_network_error_graceful_fallback() -> None:
    """Verify call_upstream_llm gracefully returns None on network failures."""
    settings = get_settings()
    with (
        patch("httpx.AsyncClient.post", side_effect=Exception("Connection timed out")),
        patch.object(settings, "GEMINI_API_KEY", "fake-gemini-key"),
    ):
        res = await call_upstream_llm(
            prompt="Test prompt",
            tenant_id="tenant-test",
            model="gemini-1.5-flash",
        )
        assert res is None


@pytest.mark.asyncio
async def test_ai_gateway_calls_upstream_llm_when_available() -> None:
    """Verify AI Gateway proxy leverages call_upstream_llm for live model inference."""
    proxy = get_gateway_proxy()
    req = GatewayChatRequest(
        model="gemini-1.5-flash",
        messages=[{"role": "user", "content": "Unique query for gateway live test"}],
    )

    with patch(
        "app.services.ai_gateway.call_upstream_llm",
        return_value="Live upstream generation from provider",
    ):
        res = await proxy.chat_completions(tenant_id="tenant-gw-llm", request=req)
        assert (
            res.choices[0]["message"]["content"]
            == "Live upstream generation from provider"
        )
