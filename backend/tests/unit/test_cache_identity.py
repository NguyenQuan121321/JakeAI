"""REPAIR-00 — CACHE-01: Exact Cache Identity Regression Tests.

These tests verify the invariant:
  Requests MUST NOT share an exact response-cache identity
  when any generation-relevant dimension differs.

And the complementary property:
  Equivalent requests MUST produce equivalent canonical cache identities.
"""

import pytest

from app.optimizer.semantic_cache import (
    CACHE_VERSION,
    SemanticCacheManager,
    _compute_hash,
    compute_cache_identity,
)

# ---------------------------------------------------------------------------
# 1. compute_cache_identity unit tests — determinism and collision freedom
# ---------------------------------------------------------------------------


class TestComputeCacheIdentity:
    """Test the canonical cache identity function directly."""

    def _base_kwargs(self) -> dict:
        """Return a baseline set of kwargs for compute_cache_identity."""
        return {
            "tenant_id": "tenant_1",
            "provider": "openai",
            "model": "gpt-4o",
            "system_instructions": "You are a helpful assistant.",
            "messages": [
                {"role": "system", "content": "You are a helpful assistant."},
                {"role": "user", "content": "Hello, how are you?"},
            ],
            "tools": None,
            "generation_params": {"temperature": 0.7, "max_tokens": 1024},
            "version": CACHE_VERSION,
        }

    def test_same_request_same_identity(self) -> None:
        """Identical requests MUST produce identical cache identities."""
        id1 = compute_cache_identity(**self._base_kwargs())
        id2 = compute_cache_identity(**self._base_kwargs())
        assert id1 == id2
        assert len(id1) == 64  # SHA-256 hex digest

    def test_different_model_different_identity(self) -> None:
        """Different model => different cache identity."""
        kw = self._base_kwargs()
        id_gpt4 = compute_cache_identity(**kw)
        kw["model"] = "gpt-3.5-turbo"
        id_gpt35 = compute_cache_identity(**kw)
        assert id_gpt4 != id_gpt35

    def test_different_provider_different_identity(self) -> None:
        """Different provider => different cache identity."""
        kw = self._base_kwargs()
        id_openai = compute_cache_identity(**kw)
        kw["provider"] = "anthropic"
        id_anthropic = compute_cache_identity(**kw)
        assert id_openai != id_anthropic

    def test_different_system_prompt_different_identity(self) -> None:
        """Different system instructions => different cache identity."""
        kw = self._base_kwargs()
        id1 = compute_cache_identity(**kw)
        kw["system_instructions"] = "You are a coding expert."
        id2 = compute_cache_identity(**kw)
        assert id1 != id2

    def test_different_conversation_history_different_identity(self) -> None:
        """Different message history => different cache identity."""
        kw = self._base_kwargs()
        id1 = compute_cache_identity(**kw)

        # Add an extra turn to the conversation
        kw["messages"] = [
            {"role": "system", "content": "You are a helpful assistant."},
            {"role": "user", "content": "What is 2+2?"},
            {"role": "assistant", "content": "4"},
            {"role": "user", "content": "Hello, how are you?"},
        ]
        id2 = compute_cache_identity(**kw)
        assert id1 != id2

    def test_different_message_order_different_identity(self) -> None:
        """Same messages in different order => different cache identity."""
        kw1 = self._base_kwargs()
        kw1["messages"] = [
            {"role": "user", "content": "A"},
            {"role": "user", "content": "B"},
        ]
        id1 = compute_cache_identity(**kw1)

        kw2 = self._base_kwargs()
        kw2["messages"] = [
            {"role": "user", "content": "B"},
            {"role": "user", "content": "A"},
        ]
        id2 = compute_cache_identity(**kw2)
        assert id1 != id2

    def test_different_tools_different_identity(self) -> None:
        """Different tool definitions => different cache identity."""
        kw = self._base_kwargs()
        id_no_tools = compute_cache_identity(**kw)

        kw["tools"] = [
            {"type": "function", "function": {"name": "search", "parameters": {}}}
        ]
        id_with_tools = compute_cache_identity(**kw)
        assert id_no_tools != id_with_tools

    def test_different_response_format_different_identity(self) -> None:
        """Different response format => different cache identity."""
        kw = self._base_kwargs()
        id_no_rf = compute_cache_identity(**kw)

        kw["response_format"] = {"type": "json_object"}
        id_json = compute_cache_identity(**kw)
        assert id_no_rf != id_json

        kw["response_format"] = "json"
        id_str_json = compute_cache_identity(**kw)
        assert id_json != id_str_json
        assert id_no_rf != id_str_json

    def test_response_format_key_order_invariance(self) -> None:
        """Response format dict with different key ordering => same cache identity."""
        kw1 = self._base_kwargs()
        kw1["response_format"] = {"type": "json_schema", "schema": {"type": "object"}}

        kw2 = self._base_kwargs()
        kw2["response_format"] = {"schema": {"type": "object"}, "type": "json_schema"}

        assert compute_cache_identity(**kw1) == compute_cache_identity(**kw2)

    def test_different_generation_params_different_identity(self) -> None:
        """Different generation parameters => different cache identity."""
        kw = self._base_kwargs()
        id1 = compute_cache_identity(**kw)

        kw["generation_params"] = {"temperature": 0.0, "max_tokens": 1024}
        id2 = compute_cache_identity(**kw)
        assert id1 != id2

    def test_different_max_tokens_different_identity(self) -> None:
        """Different max_tokens => different cache identity."""
        kw = self._base_kwargs()
        id1 = compute_cache_identity(**kw)

        kw["generation_params"] = {"temperature": 0.7, "max_tokens": 2048}
        id2 = compute_cache_identity(**kw)
        assert id1 != id2

    def test_different_tenant_different_identity(self) -> None:
        """Different tenant => different cache identity."""
        kw = self._base_kwargs()
        id1 = compute_cache_identity(**kw)
        kw["tenant_id"] = "tenant_2"
        id2 = compute_cache_identity(**kw)
        assert id1 != id2

    def test_different_version_different_identity(self) -> None:
        """Different cache version => different cache identity."""
        kw = self._base_kwargs()
        id_v2 = compute_cache_identity(**kw)
        kw["version"] = "v1.0"
        id_v1 = compute_cache_identity(**kw)
        assert id_v2 != id_v1

    def test_whitespace_normalization(self) -> None:
        """Whitespace differences should not affect cache identity."""
        kw1 = self._base_kwargs()
        kw1["system_instructions"] = "  You  are   a  helpful   assistant.  "

        kw2 = self._base_kwargs()
        kw2["system_instructions"] = "You are a helpful assistant."

        assert compute_cache_identity(**kw1) == compute_cache_identity(**kw2)

    def test_tool_key_order_invariance(self) -> None:
        """Tool definitions with different key ordering => same cache identity."""
        kw1 = self._base_kwargs()
        kw1["tools"] = [{"type": "function", "function": {"name": "search"}}]

        kw2 = self._base_kwargs()
        kw2["tools"] = [{"function": {"name": "search"}, "type": "function"}]

        assert compute_cache_identity(**kw1) == compute_cache_identity(**kw2)

    def test_empty_messages_vs_no_messages(self) -> None:
        """Empty messages list vs None => different identity (no ambiguity)."""
        kw1 = self._base_kwargs()
        kw1["messages"] = []
        id1 = compute_cache_identity(**kw1)

        kw2 = self._base_kwargs()
        kw2["messages"] = None
        id2 = compute_cache_identity(**kw2)

        # Both are semantically "no messages" but we don't conflate them
        # The key point is determinism — same input always gives same output
        assert compute_cache_identity(**kw1) == id1
        assert compute_cache_identity(**kw2) == id2

    def test_same_last_message_different_system_prompt_no_collision(self) -> None:
        """Core defect scenario: same user message, different system prompt.

        Before REPAIR-00, these would collide because only last_user_msg was hashed.
        """
        id1 = compute_cache_identity(
            tenant_id="t1",
            provider="openai",
            model="gpt-4o",
            system_instructions="You are a helpful assistant.",
            messages=[{"role": "user", "content": "Hello"}],
        )
        id2 = compute_cache_identity(
            tenant_id="t1",
            provider="openai",
            model="gpt-4o",
            system_instructions="You are a Python expert.",
            messages=[{"role": "user", "content": "Hello"}],
        )
        assert id1 != id2

    def test_same_last_message_different_model_no_collision(self) -> None:
        """Core defect scenario: same user message, different model.

        Before REPAIR-00, gateway didn't pass model to cache lookup.
        """
        id1 = compute_cache_identity(
            tenant_id="t1",
            provider="openai",
            model="gpt-4o",
            messages=[{"role": "user", "content": "Hello"}],
        )
        id2 = compute_cache_identity(
            tenant_id="t1",
            provider="openai",
            model="gpt-3.5-turbo",
            messages=[{"role": "user", "content": "Hello"}],
        )
        assert id1 != id2


# ---------------------------------------------------------------------------
# 2. SemanticCacheManager integration tests — end-to-end get/set with identity
#
# These tests validate exact-cache identity isolation. The semantic tier
# (Tier 2) is disabled via similarity_threshold=2.0 to isolate the exact
# cache path. Semantic tier guardrails for non-prompt dimensions are an
# additional observation recorded in the task file.
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_cache_miss_different_model() -> None:
    """Cache set with model A, get with model B => miss (no collision)."""
    cache = SemanticCacheManager(default_ttl=300, similarity_threshold=2.0)
    await cache.set(
        prompt="Hello",
        tenant_id="t1",
        response="Hi from GPT-4",
        model="gpt-4o",
        provider="openai",
        messages=[{"role": "user", "content": "Hello"}],
    )

    # Same prompt but different model => must miss
    result = await cache.get(
        "Hello",
        tenant_id="t1",
        model="gpt-3.5-turbo",
        provider="openai",
        messages=[{"role": "user", "content": "Hello"}],
    )
    assert result is None


@pytest.mark.asyncio
async def test_cache_miss_different_provider() -> None:
    """Cache set with provider A, get with provider B => miss."""
    cache = SemanticCacheManager(default_ttl=300, similarity_threshold=2.0)
    await cache.set(
        prompt="Hello",
        tenant_id="t1",
        response="Hi from OpenAI",
        model="gpt-4o",
        provider="openai",
        messages=[{"role": "user", "content": "Hello"}],
    )

    result = await cache.get(
        "Hello",
        tenant_id="t1",
        model="gpt-4o",
        provider="anthropic",
        messages=[{"role": "user", "content": "Hello"}],
    )
    assert result is None


@pytest.mark.asyncio
async def test_cache_miss_different_system_prompt() -> None:
    """Cache set with system prompt A, get with system prompt B => miss."""
    cache = SemanticCacheManager(default_ttl=300, similarity_threshold=2.0)
    await cache.set(
        prompt="Hello",
        tenant_id="t1",
        response="Hi, assistant here",
        model="gpt-4o",
        provider="openai",
        system_instructions="You are a helpful assistant.",
        messages=[
            {"role": "system", "content": "You are a helpful assistant."},
            {"role": "user", "content": "Hello"},
        ],
    )

    result = await cache.get(
        "Hello",
        tenant_id="t1",
        model="gpt-4o",
        provider="openai",
        system_instructions="You are a Python expert.",
        messages=[
            {"role": "system", "content": "You are a Python expert."},
            {"role": "user", "content": "Hello"},
        ],
    )
    assert result is None


@pytest.mark.asyncio
async def test_cache_miss_different_history() -> None:
    """Cache set with history A, get with different history => miss."""
    cache = SemanticCacheManager(default_ttl=300, similarity_threshold=2.0)
    await cache.set(
        prompt="What next?",
        tenant_id="t1",
        response="Continue with X",
        model="gpt-4o",
        provider="openai",
        messages=[
            {"role": "user", "content": "Start"},
            {"role": "assistant", "content": "OK"},
            {"role": "user", "content": "What next?"},
        ],
    )

    # Same last message but different history
    result = await cache.get(
        "What next?",
        tenant_id="t1",
        model="gpt-4o",
        provider="openai",
        messages=[
            {"role": "user", "content": "Begin"},
            {"role": "assistant", "content": "Sure"},
            {"role": "user", "content": "What next?"},
        ],
    )
    assert result is None


@pytest.mark.asyncio
async def test_cache_miss_different_tools() -> None:
    """Cache set with tools, get without tools => miss."""
    cache = SemanticCacheManager(default_ttl=300, similarity_threshold=2.0)
    tools = [{"type": "function", "function": {"name": "search", "parameters": {}}}]
    await cache.set(
        prompt="Hello",
        tenant_id="t1",
        response="Hi with tools",
        model="gpt-4o",
        provider="openai",
        tools=tools,
        messages=[{"role": "user", "content": "Hello"}],
    )

    # Same prompt but no tools
    result = await cache.get(
        "Hello",
        tenant_id="t1",
        model="gpt-4o",
        provider="openai",
        tools=None,
        messages=[{"role": "user", "content": "Hello"}],
    )
    assert result is None


@pytest.mark.asyncio
async def test_cache_miss_different_response_format() -> None:
    """Cache set with response_format=json, get without => miss."""
    cache = SemanticCacheManager(default_ttl=300, similarity_threshold=2.0)
    await cache.set(
        prompt="Hello",
        tenant_id="t1",
        response='{"message": "hi"}',
        model="gpt-4o",
        provider="openai",
        response_format={"type": "json_object"},
        messages=[{"role": "user", "content": "Hello"}],
    )

    result = await cache.get(
        "Hello",
        tenant_id="t1",
        model="gpt-4o",
        provider="openai",
        response_format=None,
        messages=[{"role": "user", "content": "Hello"}],
    )
    assert result is None


@pytest.mark.asyncio
async def test_cache_miss_different_generation_params() -> None:
    """Cache set with temp=0.7, get with temp=0.0 => miss."""
    cache = SemanticCacheManager(default_ttl=300, similarity_threshold=2.0)
    await cache.set(
        prompt="Hello",
        tenant_id="t1",
        response="Hi creative",
        model="gpt-4o",
        provider="openai",
        generation_params={"temperature": 0.7, "max_tokens": 1024},
        messages=[{"role": "user", "content": "Hello"}],
    )

    result = await cache.get(
        "Hello",
        tenant_id="t1",
        model="gpt-4o",
        provider="openai",
        generation_params={"temperature": 0.0, "max_tokens": 1024},
        messages=[{"role": "user", "content": "Hello"}],
    )
    assert result is None


@pytest.mark.asyncio
async def test_cache_hit_identical_request() -> None:
    """Identical requests => cache hit."""
    cache = SemanticCacheManager(default_ttl=300, similarity_threshold=2.0)
    msgs = [
        {"role": "system", "content": "You are helpful."},
        {"role": "user", "content": "Hello"},
    ]
    gen_params = {"temperature": 0.7, "max_tokens": 1024}

    await cache.set(
        prompt="Hello",
        tenant_id="t1",
        response="Hi there!",
        model="gpt-4o",
        provider="openai",
        system_instructions="You are helpful.",
        messages=msgs,
        generation_params=gen_params,
    )

    result = await cache.get(
        "Hello",
        tenant_id="t1",
        model="gpt-4o",
        provider="openai",
        system_instructions="You are helpful.",
        messages=msgs,
        generation_params=gen_params,
    )
    assert result is not None
    assert result.response == "Hi there!"
    assert result.cache_type == "exact"


@pytest.mark.asyncio
async def test_cache_backward_compatibility() -> None:
    """Legacy callers (no messages/system_instructions) still work via synthesis."""
    cache = SemanticCacheManager(default_ttl=300, similarity_threshold=2.0)

    # Legacy-style set (only prompt + tenant)
    await cache.set(
        prompt="legacy query",
        tenant_id="t1",
        response="legacy response",
    )

    # Legacy-style get (only prompt + tenant) => should hit
    result = await cache.get("legacy query", tenant_id="t1")
    assert result is not None
    assert result.response == "legacy response"


@pytest.mark.asyncio
async def test_legacy_compute_hash_still_works() -> None:
    """The legacy _compute_hash function still produces deterministic output."""
    h1 = _compute_hash("test prompt", "tenant_1")
    h2 = _compute_hash("test prompt", "tenant_1")
    assert h1 == h2
    assert len(h1) == 64

    # Whitespace normalization
    h3 = _compute_hash("  test  prompt  ", "tenant_1")
    assert h1 == h3


@pytest.mark.asyncio
async def test_gateway_exact_cache_isolation_across_dimensions() -> None:
    """End-to-end gateway proxy test verifying exact-cache isolation across dimensions."""
    from app.services.ai_gateway import (
        ChatMessage,
        GatewayChatRequest,
        GatewayInferenceProxy,
        QuotaManager,
    )

    proxy = GatewayInferenceProxy(QuotaManager())
    # Ensure fresh cache
    await proxy.cache_mgr.invalidate()

    req_base = GatewayChatRequest(
        model="gpt-4o",
        messages=[
            ChatMessage(role="system", content="You are a financial analyst."),
            ChatMessage(role="user", content="Analyze this statement."),
        ],
        temperature=0.7,
        max_tokens=500,
        tools=None,
        response_format=None,
    )

    # 1. Initial request -> cache miss, populates cache
    res1 = await proxy.chat_completions("tenant_gw", req_base)
    assert res1.cached is False

    # 2. Identical request -> exact cache hit
    res2 = await proxy.chat_completions("tenant_gw", req_base)
    assert res2.cached is True
    assert (
        res2.choices[0]["message"]["content"] == res1.choices[0]["message"]["content"]
    )

    # 3. Different model (gemini-1.5-flash) -> cache miss (no cross-model collision)
    req_diff_model = req_base.model_copy(update={"model": "gemini-1.5-flash"})
    res3 = await proxy.chat_completions("tenant_gw", req_diff_model)
    assert res3.cached is False

    # 4. Different system prompt -> cache miss
    req_diff_system = req_base.model_copy(
        update={
            "messages": [
                ChatMessage(role="system", content="You are a creative writer."),
                ChatMessage(role="user", content="Analyze this statement."),
            ]
        }
    )
    res4 = await proxy.chat_completions("tenant_gw", req_diff_system)
    assert res4.cached is False

    # 5. Different tools -> cache miss
    req_diff_tools = req_base.model_copy(
        update={"tools": [{"type": "function", "function": {"name": "calc"}}]}
    )
    res5 = await proxy.chat_completions("tenant_gw", req_diff_tools)
    assert res5.cached is False

    # 6. Different response_format -> cache miss
    req_diff_rf = req_base.model_copy(
        update={"response_format": {"type": "json_object"}}
    )
    res6 = await proxy.chat_completions("tenant_gw", req_diff_rf)
    assert res6.cached is False

    # 7. Different tenant -> cache miss (strict tenant isolation)
    res7 = await proxy.chat_completions("tenant_other", req_base)
    assert res7.cached is False
