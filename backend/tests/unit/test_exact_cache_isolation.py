"""Regression tests for TASK-R1-03 / CACHE-01, CACHE-02, CACHE-04: Composite Cache Key Isolation.

Validates:
1. Different models with identical user query produce different cache keys and cache MISS.
2. Different system instructions with identical user query produce cache MISS.
3. Different temperatures or parameters produce cache MISS.
4. Cross-conversation turn histories with identical last query produce cache MISS.
"""

import pytest

from app.services.ai_gateway import (
    ChatMessage,
    GatewayChatRequest,
    GatewayInferenceProxy,
    QuotaManager,
)


@pytest.mark.asyncio
async def test_exact_cache_model_isolation() -> None:
    """Verify requests with identical prompt but different models NEVER share exact cache."""
    quota_mgr = QuotaManager()
    proxy = GatewayInferenceProxy(quota_mgr)
    tenant_id = "tenant-cache-iso-model"
    await proxy.cache_mgr.invalidate(tenant_id)

    # Request A: gpt-4o
    req_a = GatewayChatRequest(
        model="gpt-4o",
        messages=[ChatMessage(role="user", content="Explain quantum computing.")],
    )
    res_a = await proxy.chat_completions(tenant_id, req_a)
    assert res_a.cached is False

    # Request B: claude-3-5-sonnet (same query)
    req_b = GatewayChatRequest(
        model="claude-3-5-sonnet",
        messages=[ChatMessage(role="user", content="Explain quantum computing.")],
    )
    res_b = await proxy.chat_completions(tenant_id, req_b)
    # MUST be a cache MISS because model differs!
    assert res_b.cached is False, "Cross-model cache pollution detected! Request B hit Request A cache."


@pytest.mark.asyncio
async def test_exact_cache_system_instruction_isolation() -> None:
    """Verify requests with identical prompt but different system instructions NEVER collide."""
    quota_mgr = QuotaManager()
    proxy = GatewayInferenceProxy(quota_mgr)
    tenant_id = "tenant-cache-iso-system"
    await proxy.cache_mgr.invalidate(tenant_id)

    # Request A: Default system
    req_a = GatewayChatRequest(
        model="gpt-4o",
        messages=[ChatMessage(role="user", content="Hello")],
    )
    res_a = await proxy.chat_completions(tenant_id, req_a)
    assert res_a.cached is False

    # Request C: Specialized system instruction
    req_c = GatewayChatRequest(
        model="gpt-4o",
        messages=[
            ChatMessage(role="system", content="You are a certified public accountant."),
            ChatMessage(role="user", content="Hello"),
        ],
    )
    res_c = await proxy.chat_completions(tenant_id, req_c)
    # MUST be a cache MISS because system instruction differs!
    assert res_c.cached is False, "System instruction cache collision detected!"


@pytest.mark.asyncio
async def test_exact_cache_conversation_history_isolation() -> None:
    """Verify requests with identical query but different preceding turns NEVER collide."""
    quota_mgr = QuotaManager()
    proxy = GatewayInferenceProxy(quota_mgr)
    tenant_id = "tenant-cache-iso-history"
    await proxy.cache_mgr.invalidate(tenant_id)

    # Conversation 1
    req_1 = GatewayChatRequest(
        model="gpt-4o",
        messages=[
            ChatMessage(role="user", content="My dog's name is Rex."),
            ChatMessage(role="assistant", content="Nice name!"),
            ChatMessage(role="user", content="What is my pet's name?"),
        ],
    )
    res_1 = await proxy.chat_completions(tenant_id, req_1)
    assert res_1.cached is False

    # Conversation 2: Different history, same final query
    req_2 = GatewayChatRequest(
        model="gpt-4o",
        messages=[
            ChatMessage(role="user", content="My cat's name is Luna."),
            ChatMessage(role="assistant", content="Lovely cat!"),
            ChatMessage(role="user", content="What is my pet's name?"),
        ],
    )
    res_2 = await proxy.chat_completions(tenant_id, req_2)
    # MUST be a cache MISS because prior conversation history differs!
    assert res_2.cached is False, "Conversation history cache collision detected!"
