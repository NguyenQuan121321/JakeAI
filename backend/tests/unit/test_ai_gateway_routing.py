"""Regression tests for TASK-R1-01 / DUP-02: Canonical Model-to-Provider Resolution.

Validates:
1. Model-to-provider resolution in AI Gateway routes through ProviderRegistry.
2. Models such as deepseek-chat and llama-3.3-70b-versatile resolve to 'deepseek'
   and 'groq' respectively (not openrouter).
3. BYOK key injection requests keys for the canonical provider.
"""

from unittest.mock import AsyncMock, patch

import pytest

from app.providers.registry import get_provider_registry
from app.services.ai_gateway import (
    ChatMessage,
    GatewayChatRequest,
    GatewayInferenceProxy,
    QuotaManager,
)


def test_provider_registry_canonical_resolution() -> None:
    """Verify ProviderRegistry resolves model families to canonical provider names."""
    registry = get_provider_registry()

    assert registry.resolve_provider_name_for_model("deepseek-chat") == "deepseek"
    assert registry.resolve_provider_name_for_model("deepseek-reasoner") == "deepseek"
    assert registry.resolve_provider_name_for_model("llama-3.3-70b-versatile") == "groq"
    assert registry.resolve_provider_name_for_model("llama-3.1-8b-instant") == "groq"
    assert registry.resolve_provider_name_for_model("gpt-4o") == "openai"
    assert registry.resolve_provider_name_for_model("claude-3-5-sonnet") == "anthropic"
    assert registry.resolve_provider_name_for_model("gemini-1.5-flash") == "gemini"


@pytest.mark.asyncio
async def test_ai_gateway_routes_deepseek_to_deepseek_byok() -> None:
    """Verify ai_gateway routes deepseek-chat to 'deepseek' BYOK key, not 'openrouter'."""
    quota_mgr = QuotaManager()
    proxy = GatewayInferenceProxy(quota_mgr)
    tenant_id = "tenant-deepseek-test"

    mock_byok = AsyncMock()
    mock_byok.get_decrypted_key = AsyncMock(return_value="test-deepseek-key")

    req = GatewayChatRequest(
        model="deepseek-chat",
        messages=[ChatMessage(role="user", content="Hello DeepSeek")],
    )

    with patch("app.services.ai_gateway.get_byok_manager", return_value=mock_byok):
        # Invalidate cache to ensure it reaches BYOK injection
        await proxy.cache_mgr.invalidate(tenant_id)
        await proxy.chat_completions(tenant_id, req)

        # Assert BYOK was queried for 'deepseek', NOT 'openrouter'
        mock_byok.get_decrypted_key.assert_awaited_with(tenant_id, "deepseek")


@pytest.mark.asyncio
async def test_ai_gateway_routes_llama_to_groq_byok() -> None:
    """Verify ai_gateway routes llama-3.3-70b-versatile to 'groq' BYOK key, not 'openrouter'."""
    quota_mgr = QuotaManager()
    proxy = GatewayInferenceProxy(quota_mgr)
    tenant_id = "tenant-groq-test"

    mock_byok = AsyncMock()
    mock_byok.get_decrypted_key = AsyncMock(return_value="test-groq-key")

    req = GatewayChatRequest(
        model="llama-3.3-70b-versatile",
        messages=[ChatMessage(role="user", content="Hello Groq Llama")],
    )

    with patch("app.services.ai_gateway.get_byok_manager", return_value=mock_byok):
        await proxy.cache_mgr.invalidate(tenant_id)
        await proxy.chat_completions(tenant_id, req)

        # Assert BYOK was queried for 'groq', NOT 'openrouter'
        mock_byok.get_decrypted_key.assert_awaited_with(tenant_id, "groq")
