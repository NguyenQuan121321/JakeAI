"""Unit and regression tests for REPAIR-02: TOK-02 Canonical Token Accounting.

Verifies:
1. Model-visible input envelope accounting across system, history, user query, tools, and RAG context.
2. Given system=2000, history=3000, query=50, accounting layer must NOT report raw input as 50.
3. Accounting dimensions: raw_input_tokens, optimized_input_tokens, provider_cached_input_tokens,
   completion_tokens, physical_tokens_pruned, response_cache_avoided_tokens, effective_billed_tokens.
4. Upstream provider telemetry usage reconciliation.
5. Exact response cache hit token avoidance.
6. Conservation of tokens invariant.
"""

from __future__ import annotations

import json
from unittest.mock import AsyncMock, patch

import pytest

from app.optimizer.semantic_cache import SemanticCacheEntry
from app.optimizer.token_accounting import (
    TokenAccounting,
    TokenUsageRecord,
)
from app.optimizer.token_pruner import estimate_tokens
from app.providers.base import (
    ChatMessage,
    ProviderCacheTelemetry,
    UpstreamLLMResponse,
)
from app.services.ai_gateway import (
    GatewayChatRequest,
    GatewayInferenceProxy,
    QuotaManager,
)


def test_accounting_envelope_system_history_query() -> None:
    """CRITICAL REQUIREMENT: Given system=2000, history=3000, query=50,

    the accounting layer MUST NOT report raw input as 50.
    """
    # System: ~2000 tokens
    sys_content = "system instruction content rule policy " * 400
    assert estimate_tokens(sys_content) >= 2000

    # History: ~3000 tokens across 4 turns
    turn1_user = "historical user turn one context information " * 150
    turn1_asst = "historical assistant turn one answer explanation " * 150
    turn2_user = "historical user turn two context details " * 150
    turn2_asst = "historical assistant turn two follow up reply " * 150
    history_total = (
        estimate_tokens(turn1_user)
        + estimate_tokens(turn1_asst)
        + estimate_tokens(turn2_user)
        + estimate_tokens(turn2_asst)
    )
    assert history_total >= 3000

    # Query: ~50 tokens
    query_content = "current user question regarding the financial metrics summary now"
    query_tokens = estimate_tokens(query_content)
    assert 5 <= query_tokens <= 100

    messages = [
        ChatMessage(role="system", content=sys_content),
        ChatMessage(role="user", content=turn1_user),
        ChatMessage(role="assistant", content=turn1_asst),
        ChatMessage(role="user", content=turn2_user),
        ChatMessage(role="assistant", content=turn2_asst),
        ChatMessage(role="user", content=query_content),
    ]

    # Compute envelope tokens
    envelope_tokens = TokenAccounting.calculate_envelope_tokens(messages=messages)

    # Invariant: Must reflect system (2000) + history (3000) + query (50) + framing
    assert envelope_tokens >= 5050
    assert envelope_tokens != query_tokens
    assert envelope_tokens > 5000


def test_accounting_with_tools() -> None:
    """Verifies tool definitions schema participates in model-visible input envelope."""
    tools = [
        {
            "type": "function",
            "function": {
                "name": "get_portfolio_valuation",
                "description": "Calculate total portfolio market valuation for a given client ID",
                "parameters": {
                    "type": "object",
                    "properties": {
                        "client_id": {
                            "type": "string",
                            "description": "Client identifier",
                        },
                        "include_accrued_interest": {
                            "type": "boolean",
                            "default": True,
                        },
                    },
                    "required": ["client_id"],
                },
            },
        },
        {
            "type": "function",
            "function": {
                "name": "execute_hedging_order",
                "description": "Submit a delta hedging order to the execution broker",
                "parameters": {
                    "type": "object",
                    "properties": {
                        "symbol": {"type": "string"},
                        "quantity": {"type": "number"},
                        "order_type": {"type": "string", "enum": ["market", "limit"]},
                    },
                    "required": ["symbol", "quantity"],
                },
            },
        },
    ]

    messages = [
        ChatMessage(role="system", content="You are a financial assistant."),
        ChatMessage(role="user", content="Value the portfolio for client 123"),
    ]

    base_tokens = TokenAccounting.calculate_envelope_tokens(messages=messages)
    tokens_with_tools = TokenAccounting.calculate_envelope_tokens(
        messages=messages, tools=tools
    )

    from app.optimizer.bpe_tokenizer import get_bpe_tokenizer

    tools_json_tokens = get_bpe_tokenizer().count_tokens(json.dumps(tools))
    assert tools_json_tokens > 50
    assert tokens_with_tools > base_tokens
    assert tokens_with_tools >= base_tokens + tools_json_tokens


def test_accounting_with_rag_context() -> None:
    """Verifies RAG context passages participate in model-visible input envelope."""
    rag_passages = (
        "Document: SEC 10-K filing excerpt for Corp XYZ. "
        "Revenue for fiscal year 2025 was $4.2B with net margin of 18.5%. "
        "Operating cash flows totaled $920M. " * 20
    )
    rag_tokens = estimate_tokens(rag_passages)
    assert rag_tokens >= 400

    messages = [
        ChatMessage(
            role="system",
            content=f"Use the following reference material:\n{rag_passages}",
        ),
        ChatMessage(role="user", content="What was the net margin?"),
    ]

    envelope_tokens = TokenAccounting.calculate_envelope_tokens(messages=messages)
    assert envelope_tokens > rag_tokens
    assert envelope_tokens >= 400


def test_accounting_with_optimized_context() -> None:
    """Verifies tracking of raw_input_tokens, optimized_input_tokens, and physical_tokens_pruned."""
    raw_input = 1200
    optimized_input = 800
    completion = 200

    record = TokenAccounting.record_transaction(
        request_id="req-opt-test",
        tenant_id="tenant-fin",
        model="gpt-4o",
        raw_input_tokens=raw_input,
        optimized_input_tokens=optimized_input,
        completion_tokens=completion,
        cache_hit=False,
    )

    assert record.raw_input_tokens == 1200
    assert record.optimized_input_tokens == 800
    assert record.physical_tokens_pruned == 400
    assert record.completion_tokens == 200
    assert record.response_cache_avoided_tokens == 0
    assert record.effective_billed_tokens == 1000  # 800 optimized + 200 completion
    assert record.tokens_saved == 400
    assert record.reduction_percentage == round((400 / 1400) * 100, 2)


def test_accounting_provider_cache_telemetry_reconciliation() -> None:
    """Verifies provider KV prompt cache telemetry reconciliation."""
    raw_input = 5000
    optimized_input = 4500  # 500 tokens locally pruned
    telemetry = ProviderCacheTelemetry(
        is_cache_eligible=True,
        cache_hit=True,
        cached_tokens=3000,
        uncached_input_tokens=1500,
        output_tokens=250,
        provider="anthropic",
        model="claude-3-5-sonnet",
        estimated_savings_usd=0.009,
        actual_cost_usd=0.006,
    )

    record = TokenAccounting.record_transaction(
        request_id="req-prov-telemetry",
        tenant_id="tenant-fin",
        model="claude-3-5-sonnet",
        raw_input_tokens=raw_input,
        optimized_input_tokens=optimized_input,
        completion_tokens=200,  # estimated before upstream
        cache_hit=False,
        provider_telemetry=telemetry,
    )

    # Reconciled metrics
    assert record.reconciled_with_provider is True
    assert record.provider_cache_hit is True
    assert record.provider_cached_input_tokens == 3000
    assert record.optimized_input_tokens == 4500  # 1500 uncached + 3000 cached
    assert record.raw_input_tokens == 5000  # 4500 provider input + 500 pruned
    assert record.physical_tokens_pruned == 500
    assert record.completion_tokens == 250  # reconciled from upstream output_tokens
    # Effective billed: uncached input (1500) + cached discount (3000 * 10% = 300) + completion (250) = 2050
    assert record.effective_billed_tokens == 2050
    assert record.provider_cost_savings_usd == 0.009
    assert record.provider_actual_cost_usd == 0.006


def test_accounting_tier1_response_cache_hit() -> None:
    """Verifies Layer A exact response cache hit accounts 100% tokens saved and 0 billed."""
    raw_input = 4000
    completion = 350

    record = TokenAccounting.record_transaction(
        request_id="req-exact-hit",
        tenant_id="tenant-fin",
        model="gpt-4o",
        raw_input_tokens=raw_input,
        optimized_input_tokens=0,
        completion_tokens=completion,
        cache_hit=True,
        cache_type="exact",
    )

    assert record.raw_input_tokens == 4000
    assert record.optimized_input_tokens == 0
    assert record.effective_billed_tokens == 0
    assert record.response_cache_avoided_tokens == 4350
    assert record.tokens_saved == 4350
    assert record.reduction_percentage == 100.0


def test_conservation_of_tokens_invariant() -> None:
    """Verifies mathematical conservation law across cache miss, provider cache, and response cache hit:

    baseline_total == effective_billed_tokens + tokens_saved
    """
    # 1. Pure Cache Miss without provider caching
    rec1 = TokenAccounting.record_transaction(
        request_id="c1",
        tenant_id="t1",
        model="gpt-4o",
        raw_input_tokens=1000,
        optimized_input_tokens=700,
        completion_tokens=300,
        cache_hit=False,
    )
    baseline1 = 1000 + 300
    assert baseline1 == rec1.effective_billed_tokens + rec1.tokens_saved
    assert rec1.effective_billed_tokens == 1000
    assert rec1.tokens_saved == 300

    # 2. Response Cache Hit
    rec2 = TokenAccounting.record_transaction(
        request_id="c2",
        tenant_id="t1",
        model="gpt-4o",
        raw_input_tokens=2500,
        optimized_input_tokens=0,
        completion_tokens=500,
        cache_hit=True,
    )
    baseline2 = 2500 + 500
    assert baseline2 == rec2.effective_billed_tokens + rec2.tokens_saved
    assert rec2.effective_billed_tokens == 0
    assert rec2.tokens_saved == baseline2

    # 3. Provider Prompt Cache Hit
    telem = ProviderCacheTelemetry(
        is_cache_eligible=True,
        cache_hit=True,
        cached_tokens=1500,
        uncached_input_tokens=500,
        output_tokens=200,
    )
    rec3 = TokenAccounting.record_transaction(
        request_id="c3",
        tenant_id="t1",
        model="gpt-4o",
        raw_input_tokens=2000,
        optimized_input_tokens=2000,
        completion_tokens=200,
        cache_hit=False,
        provider_telemetry=telem,
    )
    baseline3 = 2000 + 200
    assert rec3.provider_cached_input_tokens == 1500
    # Effective billed: 500 uncached + (1500 * 50% = 750) cached + 200 completion = 1450
    assert rec3.effective_billed_tokens == 1450
    assert baseline3 == rec3.effective_billed_tokens + rec3.tokens_saved


@pytest.mark.asyncio
async def test_gateway_chat_completions_multi_turn_accounting() -> None:
    """E2E Gateway test: multi-turn input must NOT report raw prompt tokens as last_user_msg."""
    quota_mgr = QuotaManager()
    proxy = GatewayInferenceProxy(quota_mgr)
    tenant_id = "tenant-gateway-accounting-test"
    await quota_mgr.set_quota_limit(tenant_id, 1_000_000)

    # Multi-turn messages: system (~500), user1 (~400), asst1 (~400), user2 (~30)
    messages = [
        ChatMessage(role="system", content="corporate treasury policy rules " * 100),
        ChatMessage(
            role="user", content="previous financial conversation history turn " * 80
        ),
        ChatMessage(
            role="assistant",
            content="previous financial assistant response details " * 80,
        ),
        ChatMessage(role="user", content="what is current liquidity ratio?"),
    ]
    query_tokens = estimate_tokens("what is current liquidity ratio?")
    assert query_tokens < 15

    req = GatewayChatRequest(
        model="gemini-1.5-flash",
        messages=messages,
    )

    mock_resp = UpstreamLLMResponse(
        text="Current liquidity ratio is 1.85.",
        model="gemini-1.5-flash",
        provider="gemini",
        telemetry=ProviderCacheTelemetry(
            is_cache_eligible=False,
            cache_hit=False,
            cached_tokens=0,
            uncached_input_tokens=1350,
            output_tokens=20,
            provider="gemini",
            model="gemini-1.5-flash",
        ),
    )

    with patch(
        "app.services.ai_gateway.call_upstream_llm_detailed",
        AsyncMock(return_value=mock_resp),
    ):
        resp = await proxy.chat_completions(tenant_id, req)

        # Invariant: prompt_tokens MUST NOT be query_tokens (which is < 15)
        assert resp.usage["prompt_tokens"] > 1000
        assert resp.usage["prompt_tokens"] != query_tokens
        assert resp.usage["total_tokens"] > 1000


@pytest.mark.asyncio
async def test_gateway_chat_completions_cache_hit_accounting() -> None:
    """E2E Gateway test: cache hit must account the entire model-visible envelope for tokens_saved."""
    quota_mgr = QuotaManager()
    proxy = GatewayInferenceProxy(quota_mgr)
    tenant_id = "tenant-gateway-cache-hit-test"
    await quota_mgr.set_quota_limit(tenant_id, 1_000_000)

    messages = [
        ChatMessage(
            role="system", content="system corporate rules instructions " * 100
        ),
        ChatMessage(role="user", content="previous context dialogue message " * 80),
        ChatMessage(role="assistant", content="previous assistant reply details " * 80),
        ChatMessage(role="user", content="exact query to cache"),
    ]
    query_tokens = estimate_tokens("exact query to cache")

    req = GatewayChatRequest(
        model="gemini-1.5-flash",
        messages=messages,
    )

    cached_entry = SemanticCacheEntry(
        tenant_id=tenant_id,
        prompt="exact query to cache",
        response="Immediate cached financial analysis result.",
        model="gemini-1.5-flash",
        tokens_saved=500,
        latency_ms=1.2,
        cache_type="exact",
    )

    with patch.object(proxy.cache_mgr, "get", AsyncMock(return_value=cached_entry)):
        resp = await proxy.chat_completions(tenant_id, req)

        assert resp.cached is True
        assert resp.usage["total_tokens"] == 0
        # Invariant: tokens_saved must represent entire envelope (> 1000 tokens), not just query_tokens (~5 tokens)
        assert resp.tokens_saved > 1000
        assert resp.tokens_saved != query_tokens


@pytest.mark.asyncio
async def test_gateway_chat_completions_stream_accounting() -> None:
    """E2E Gateway Streaming: verifies streaming usage deduction accounts the full envelope."""
    quota_mgr = QuotaManager()
    proxy = GatewayInferenceProxy(quota_mgr)
    tenant_id = "tenant-stream-accounting-test"
    await quota_mgr.set_quota_limit(tenant_id, 1_000_000)

    messages = [
        ChatMessage(
            role="system", content="treasury streaming risk management policy " * 80
        ),
        ChatMessage(role="user", content="previous dialogue context turn " * 60),
        ChatMessage(
            role="assistant", content="previous response details from assistant " * 60
        ),
        ChatMessage(role="user", content="stream analysis please"),
    ]
    query_tokens = estimate_tokens("stream analysis please")
    assert query_tokens < 10

    req = GatewayChatRequest(
        model="gemini-1.5-flash",
        messages=messages,
        stream=True,
    )

    with patch(
        "app.core.llm_provider.call_upstream_llm",
        AsyncMock(return_value="Streamed chunk financial summary result."),
    ):
        chunks: list[str] = []
        async for chunk in proxy.chat_completions_stream(tenant_id, req):
            chunks.append(chunk)

        assert len(chunks) > 0
        used = await quota_mgr.get_tokens_used(tenant_id)
        # Invariant: quota deduction must represent the entire multi-turn envelope (> 800 tokens)
        assert used > 800
        assert used != query_tokens


@pytest.mark.asyncio
async def test_gateway_chat_completions_stream_cache_hit_accounting() -> None:
    """E2E Gateway Streaming Cache Hit: verifies tokens_saved accounts the full envelope."""
    quota_mgr = QuotaManager()
    proxy = GatewayInferenceProxy(quota_mgr)
    tenant_id = "tenant-stream-hit-test"
    await quota_mgr.set_quota_limit(tenant_id, 1_000_000)

    messages = [
        ChatMessage(
            role="system", content="corporate investment policy streaming rules " * 80
        ),
        ChatMessage(
            role="user", content="prior dialogue history for stream cache " * 60
        ),
        ChatMessage(
            role="assistant", content="prior response content from assistant " * 60
        ),
        ChatMessage(role="user", content="query for cached stream"),
    ]
    query_tokens = estimate_tokens("query for cached stream")

    req = GatewayChatRequest(
        model="gemini-1.5-flash",
        messages=messages,
        stream=True,
    )

    cached_entry = SemanticCacheEntry(
        tenant_id=tenant_id,
        prompt="query for cached stream",
        response="Immediate cached streaming financial output.",
        model="gemini-1.5-flash",
        tokens_saved=500,
        latency_ms=1.1,
        cache_type="exact",
    )

    with patch.object(proxy.cache_mgr, "get", AsyncMock(return_value=cached_entry)):
        chunks: list[str] = []
        async for chunk in proxy.chat_completions_stream(tenant_id, req):
            chunks.append(chunk)

        assert len(chunks) > 0
        # Check tokens saved in quota manager (Redis or memory backed)
        tokens_saved = await quota_mgr.get_tokens_saved(tenant_id)
        assert tokens_saved > 800
        assert tokens_saved != query_tokens


def test_accounting_with_assistant_tool_calls_and_tool_results() -> None:
    """Verifies that assistant turns with tool_calls and role='tool' results are counted in envelope."""
    tool_calls_payload = [
        {
            "id": "call_abc123",
            "type": "function",
            "function": {
                "name": "calculate_irr",
                "arguments": '{"cash_flows": [-1000, 200, 300, 400, 500]}',
            },
        }
    ]
    tool_result_content = '{"irr": 0.128, "npv_at_10pct": 68.32, "status": "computed"}'

    messages = [
        ChatMessage(role="system", content="You are a financial modeler."),
        ChatMessage(role="user", content="Calculate IRR for project Alpha."),
        ChatMessage(
            role="assistant",
            content=None,
            tool_calls=tool_calls_payload,
        ),
        ChatMessage(
            role="tool",
            name="calculate_irr",
            tool_call_id="call_abc123",
            content=tool_result_content,
        ),
        ChatMessage(role="assistant", content="The project IRR is 12.8%."),
    ]

    envelope = TokenAccounting.calculate_envelope_tokens(messages=messages)
    tc_tokens = estimate_tokens(json.dumps(tool_calls_payload))
    tr_tokens = estimate_tokens(tool_result_content)

    assert envelope > (tc_tokens + tr_tokens)
    assert envelope > 40


def test_accounting_dict_messages_compatibility() -> None:
    """Verifies backward compatibility with plain dictionary message objects."""
    dict_messages = [
        {"role": "system", "content": "You are a financial analyst."},
        {"role": "user", "content": "Analyze quarterly earnings."},
    ]
    envelope = TokenAccounting.calculate_envelope_tokens(messages=dict_messages)
    assert envelope > 10


def test_token_usage_record_bidirectional_synchronization() -> None:
    """Verifies Pydantic model validator ensures legacy and canonical dimensions stay in sync."""
    # Instantiation via legacy fields
    rec1 = TokenUsageRecord(
        request_id="r1",
        tenant_id="t1",
        model="m1",
        raw_prompt_tokens=1500,
        pruned_prompt_tokens=1000,
        completion_tokens=200,
        actual_billed_tokens=1200,
        tokens_saved=500,
        reduction_percentage=29.4,
        cache_hit=False,
    )
    assert rec1.raw_input_tokens == 1500
    assert rec1.optimized_input_tokens == 1000
    assert rec1.effective_billed_tokens == 1200
    assert rec1.physical_tokens_pruned == 500

    # Instantiation via canonical fields
    rec2 = TokenUsageRecord(
        request_id="r2",
        tenant_id="t2",
        model="m2",
        raw_input_tokens=2500,
        optimized_input_tokens=2000,
        completion_tokens=300,
        effective_billed_tokens=2300,
        tokens_saved=500,
        reduction_percentage=17.9,
        cache_hit=False,
    )
    assert rec2.raw_prompt_tokens == 2500
    assert rec2.pruned_prompt_tokens == 2000
    assert rec2.actual_billed_tokens == 2300
    assert rec2.physical_tokens_pruned == 500


def test_provider_reconciliation_zero_tokens_fallback() -> None:
    """Verifies that if provider telemetry reports 0 tokens, local envelope tokens are safely preserved."""
    telemetry_empty = ProviderCacheTelemetry(
        is_cache_eligible=False,
        cache_hit=False,
        cached_tokens=0,
        uncached_input_tokens=0,
        output_tokens=0,
    )

    record = TokenAccounting.record_transaction(
        request_id="req-fallback",
        tenant_id="tenant-fin",
        model="gpt-4o",
        raw_input_tokens=1500,
        optimized_input_tokens=1500,
        completion_tokens=150,
        cache_hit=False,
        provider_telemetry=telemetry_empty,
    )

    assert record.raw_input_tokens == 1500
    assert record.optimized_input_tokens == 1500
    assert record.completion_tokens == 150
    assert record.effective_billed_tokens == 1650
    assert record.reconciled_with_provider is False


@pytest.mark.asyncio
async def test_quota_manager_get_tokens_saved_redis_and_memory() -> None:
    """Verifies QuotaManager.get_tokens_saved works seamlessly via Redis and fallback memory."""
    qm = QuotaManager()
    tenant = "tenant-qm-tokens-saved"

    # In-memory test (no redis)
    with patch.object(qm, "_get_redis", AsyncMock(return_value=None)):
        await qm.record_tokens_saved(tenant, 450)
        saved = await qm.get_tokens_saved(tenant)
        assert saved == 450

    # Redis test
    mock_redis = AsyncMock()
    mock_redis.get = AsyncMock(return_value=b"1250")
    with patch.object(qm, "_get_redis", AsyncMock(return_value=mock_redis)):
        saved_redis = await qm.get_tokens_saved(tenant)
        assert saved_redis == 1250

    # Redis error fallback to memory
    mock_redis_err = AsyncMock()
    mock_redis_err.get = AsyncMock(side_effect=Exception("Redis connection error"))
    with patch.object(qm, "_get_redis", AsyncMock(return_value=mock_redis_err)):
        saved_fallback = await qm.get_tokens_saved(tenant)
        assert saved_fallback == 450
