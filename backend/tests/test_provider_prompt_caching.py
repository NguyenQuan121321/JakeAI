"""Comprehensive Unit and Contract Tests for Tier 5: Provider Prompt Caching.

Verifies:
1. Provider capability matrix and policy classification.
2. Anthropic explicit cache_control insertion at Zone 1 breakpoint.
3. Upstream usage metadata extraction (Anthropic cache_read/write, OpenAI cached_tokens).
4. Rule 1: Zero fake cache hits (upstream telemetry only, local hash match is not a hit).
5. Strict separation of Layer A (JakeAI response cache) and Layer B (Provider prompt cache).
6. Cache miss reason attribution.
7. Accurate FinOps cost calculations and savings discounts.
"""

from __future__ import annotations

import json
from unittest.mock import AsyncMock, patch

import httpx
import pytest

from app.core.config import Settings
from app.core.llm_provider import call_upstream_llm_detailed
from app.optimizer.provider_cache_policy import (
    CacheMissReason,
    ProviderCacheStatus,
    evaluate_cache_eligibility,
    get_provider_adapter,
    get_provider_cache_policy,
)
from app.optimizer.provider_pricing import (
    calculate_provider_costs,
    get_model_pricing,
)
from app.optimizer.two_zone_compiler import TwoZonePromptCompiler
from app.services.ai_gateway import (
    GatewayChatRequest,
    GatewayChatResponse,
    GatewayInferenceProxy,
    QuotaManager,
)

_RealAsyncClient = httpx.AsyncClient


def test_provider_cache_policy_classification() -> None:
    """Verifies that all provider families are correctly categorized per Tier 5 specs."""
    anthropic = get_provider_cache_policy("claude-3-5-sonnet-20241022")
    assert anthropic.status == ProviderCacheStatus.SUPPORTED
    assert anthropic.min_cache_tokens == 1024
    assert anthropic.explicit_breakpoint_required is True
    assert anthropic.supports_cache_write_telemetry is True
    assert anthropic.supports_cache_read_telemetry is True

    openai = get_provider_cache_policy("gpt-4o")
    assert openai.status == ProviderCacheStatus.SUPPORTED
    assert openai.min_cache_tokens == 1024
    assert openai.explicit_breakpoint_required is False
    assert openai.supports_cache_read_telemetry is True

    deepseek = get_provider_cache_policy("deepseek-chat")
    assert deepseek.status == ProviderCacheStatus.SUPPORTED
    assert deepseek.min_cache_tokens == 64
    assert deepseek.explicit_breakpoint_required is False

    gemini = get_provider_cache_policy("gemini-1.5-pro")
    assert gemini.status == ProviderCacheStatus.PARTIALLY_SUPPORTED
    assert gemini.min_cache_tokens == 32768

    groq = get_provider_cache_policy("groq")
    assert groq.status == ProviderCacheStatus.NOT_SUPPORTED


def test_cache_miss_reason_attribution() -> None:
    """Verifies fine-grained cache miss reason attribution."""
    anthropic_policy = get_provider_cache_policy("claude-3-5-sonnet")
    groq_policy = get_provider_cache_policy("groq")

    # 1. Provider unsupported
    eligible, reason = evaluate_cache_eligibility(groq_policy, static_token_count=2000)
    assert eligible is False
    assert reason == CacheMissReason.PROVIDER_UNSUPPORTED

    # 2. Below minimum size
    eligible, reason = evaluate_cache_eligibility(
        anthropic_policy, static_token_count=500
    )
    assert eligible is False
    assert reason == CacheMissReason.BELOW_MINIMUM_SIZE

    # 3. Dynamic contamination
    eligible, reason = evaluate_cache_eligibility(
        anthropic_policy, static_token_count=2000, has_contamination=True
    )
    assert eligible is False
    assert reason == CacheMissReason.DYNAMIC_DATA_CONTAMINATION

    # 4. Prefix changed
    eligible, reason = evaluate_cache_eligibility(
        anthropic_policy,
        static_token_count=2000,
        previous_prefix_hash="hash_a",
        current_prefix_hash="hash_b",
    )
    assert eligible is True
    assert reason == CacheMissReason.PREFIX_CHANGED


def test_provider_pricing_and_savings_calculation() -> None:
    """Verifies accurate FinOps token cost accounting and discount calculations."""
    # Anthropic Claude 3.5 Sonnet: Normal $3/M, Cache Read $0.30/M (90% off), Write $3.75/M
    # Scenario: 2,000 cached tokens read, 500 uncached tokens, 200 output tokens
    cost_claude = calculate_provider_costs(
        model="claude-3-5-sonnet",
        uncached_input_tokens=500,
        cached_input_tokens=2000,
        cache_write_tokens=0,
        output_tokens=200,
    )
    assert cost_claude.baseline_cost_usd == pytest.approx(0.0105, abs=1e-5)
    assert cost_claude.actual_cost_usd == pytest.approx(0.0051, abs=1e-5)
    assert cost_claude.savings_usd == pytest.approx(0.0054, abs=1e-5)
    assert cost_claude.savings_percentage > 50.0

    # OpenAI GPT-4o: Normal $2.50/M, Cache Read $1.25/M (50% off)
    # Scenario: 1,000 cached tokens, 1,000 uncached tokens, 100 output tokens
    cost_openai = calculate_provider_costs(
        model="gpt-4o",
        uncached_input_tokens=1000,
        cached_input_tokens=1000,
        cache_write_tokens=0,
        output_tokens=100,
    )
    assert cost_openai.baseline_cost_usd == pytest.approx(0.006, abs=1e-5)
    assert cost_openai.actual_cost_usd == pytest.approx(0.00475, abs=1e-5)
    assert cost_openai.savings_usd == pytest.approx(0.00125, abs=1e-5)


@pytest.mark.asyncio
async def test_anthropic_cache_control_and_telemetry() -> None:
    """Verifies Anthropic adapter sends cache_control and parses read/write usage."""
    compiler = TwoZonePromptCompiler(min_cache_tokens=50)
    compiled = compiler.compile(
        system_instruction="Static corporate rules " * 20,
        user_query="Audit financial records",
    )

    captured_requests: list[dict] = []

    def mock_handler(request: httpx.Request) -> httpx.Response:
        body = json.loads(request.content.decode("utf-8"))
        captured_requests.append({"headers": dict(request.headers), "body": body})
        resp_data = {
            "content": [{"type": "text", "text": "Audit complete. No issues found."}],
            "usage": {
                "input_tokens": 15,
                "output_tokens": 8,
                "cache_creation_input_tokens": 0,
                "cache_read_input_tokens": 1050,
            },
        }
        return httpx.Response(200, json=resp_data)

    transport = httpx.MockTransport(mock_handler)

    with (
        patch(
            "app.core.llm_provider.httpx.AsyncClient",
            lambda *args, **kwargs: _RealAsyncClient(transport=transport),
        ),
        patch("app.core.llm_provider.get_settings") as mock_settings,
    ):
        settings_obj = Settings()
        settings_obj.ANTHROPIC_API_KEY = "sk-ant-test-key-mock"
        settings_obj.PROVIDER_PROMPT_CACHE_ENABLED = True
        mock_settings.return_value = settings_obj

        res = await call_upstream_llm_detailed(
            prompt="Audit financial records",
            model="claude-3-5-sonnet",
            compiled_prompt=compiled,
        )

    assert res is not None
    assert res.provider == "anthropic"
    assert res.text == "Audit complete. No issues found."

    # Verify request payload
    assert len(captured_requests) == 1
    req = captured_requests[0]
    assert req["headers"].get("anthropic-beta") == "prompt-caching-2024-07-31"
    system_blocks = req["body"].get("system", [])
    assert len(system_blocks) > 0
    assert system_blocks[0].get("cache_control") == {"type": "ephemeral"}

    # Verify telemetry
    assert res.telemetry.cache_hit is True
    assert res.telemetry.cached_tokens == 1050
    assert res.telemetry.uncached_input_tokens == 15
    assert res.telemetry.cache_write_tokens == 0
    assert res.telemetry.estimated_savings_usd > 0.0


@pytest.mark.asyncio
async def test_openai_cached_tokens_telemetry() -> None:
    """Verifies OpenAI adapter correctly parses prompt_tokens_details.cached_tokens."""
    compiler = TwoZonePromptCompiler(min_cache_tokens=50)
    compiled = compiler.compile(
        system_instruction="Static corporate rules " * 20,
        user_query="Generate Q4 summary",
    )

    def mock_handler(request: httpx.Request) -> httpx.Response:
        resp_data = {
            "choices": [
                {"message": {"role": "assistant", "content": "Q4 summary generated."}}
            ],
            "usage": {
                "prompt_tokens": 1200,
                "completion_tokens": 50,
                "prompt_tokens_details": {"cached_tokens": 1024},
            },
        }
        return httpx.Response(200, json=resp_data)

    transport = httpx.MockTransport(mock_handler)

    with (
        patch(
            "app.core.llm_provider.httpx.AsyncClient",
            lambda *args, **kwargs: _RealAsyncClient(transport=transport),
        ),
        patch("app.core.llm_provider.get_settings") as mock_settings,
    ):
        settings_obj = Settings()
        settings_obj.OPENAI_API_KEY = "sk-test-openai-key"
        mock_settings.return_value = settings_obj

        res = await call_upstream_llm_detailed(
            prompt="Generate Q4 summary",
            model="gpt-4o",
            compiled_prompt=compiled,
        )

    assert res is not None
    assert res.provider == "openai"
    assert res.telemetry.cache_hit is True
    assert res.telemetry.cached_tokens == 1024
    assert res.telemetry.uncached_input_tokens == 176  # 1200 - 1024
    assert res.telemetry.estimated_savings_usd > 0.0


@pytest.mark.asyncio
async def test_rule_1_never_fake_cache_hits() -> None:
    """RULE 1 TEST: Identical local prefix hashes MUST NEVER be reported as a provider cache HIT

    if upstream usage metadata reports 0 cached tokens.
    """
    compiler = TwoZonePromptCompiler(min_cache_tokens=50)
    compiled = compiler.compile(
        system_instruction="Static system prompt " * 20,
        user_query="User prompt 1",
    )

    # First call: upstream returns 0 cached tokens (cache MISS / write)
    def mock_miss_handler(request: httpx.Request) -> httpx.Response:
        return httpx.Response(
            200,
            json={
                "choices": [{"message": {"role": "assistant", "content": "Resp 1"}}],
                "usage": {
                    "prompt_tokens": 1200,
                    "completion_tokens": 20,
                    "prompt_tokens_details": {"cached_tokens": 0},  # ZERO cached tokens
                },
            },
        )

    transport = httpx.MockTransport(mock_miss_handler)

    with (
        patch(
            "app.core.llm_provider.httpx.AsyncClient",
            lambda *args, **kwargs: _RealAsyncClient(transport=transport),
        ),
        patch("app.core.llm_provider.get_settings") as mock_settings,
    ):
        settings_obj = Settings()
        settings_obj.OPENAI_API_KEY = "sk-test-key"
        mock_settings.return_value = settings_obj

        res1 = await call_upstream_llm_detailed(
            prompt="User prompt 1",
            model="gpt-4o",
            compiled_prompt=compiled,
        )

    assert res1 is not None
    # Local prefix was eligible and hash was present, BUT provider returned 0 cached tokens
    assert res1.telemetry.is_cache_eligible is True
    assert res1.telemetry.cached_tokens == 0
    # RULE 1 ENFORCEMENT: cache_hit MUST BE FALSE!
    assert res1.telemetry.cache_hit is False
    assert res1.telemetry.miss_reason != CacheMissReason.NONE.value


@pytest.mark.asyncio
async def test_three_cache_systems_separation() -> None:
    """RULE 10 TEST: Strictly separates Layer A (JakeAI Redis/Qdrant) and Layer B (Provider Prompt Cache)."""
    proxy = GatewayInferenceProxy(QuotaManager())

    # Mock semantic cache get to return a Layer A exact hit
    from app.optimizer.semantic_cache import SemanticCacheEntry

    cached_entry = SemanticCacheEntry(
        tenant_id="tenant-123",
        prompt="cached query",
        response="Immediate Layer A Response",
        model="gpt-4o",
        tokens_saved=500,
        latency_ms=1.5,
        cache_type="exact",
    )

    with patch.object(proxy.cache_mgr, "get", AsyncMock(return_value=cached_entry)):
        req = GatewayChatRequest(
            model="gpt-4o",
            messages=[{"role": "user", "content": "cached query"}],
        )
        resp: GatewayChatResponse = await proxy.chat_completions("tenant-123", req)

        # Layer A hit properties
        assert resp.cached is True  # Layer A hit
        assert resp.choices[0]["message"]["content"] == "Immediate Layer A Response"
        # Layer B prompt cache was not invoked because Layer A answered at 0 tokens
        assert resp.provider_cache is None


def test_get_model_pricing_heuristics() -> None:
    """Verifies pricing model resolution and fallback heuristics."""
    assert get_model_pricing("custom-claude-test").model_id == "claude-3-5-sonnet"
    assert get_model_pricing("custom-mini-model").model_id == "gpt-4o-mini"
    assert get_model_pricing("custom-gpt-model").model_id == "gpt-4o"
    assert get_model_pricing("custom-gemini-model").model_id == "gemini-1.5-flash"
    assert get_model_pricing("custom-deepseek-model").model_id == "deepseek-chat"
    assert get_model_pricing("unknown-vendor-llm").model_id == "default-llm"


@pytest.mark.asyncio
async def test_gemini_cached_tokens_telemetry() -> None:
    """Verifies Gemini adapter parses usageMetadata and cachedContentTokenCount."""
    compiler = TwoZonePromptCompiler(min_cache_tokens=50)
    compiled = compiler.compile(
        system_instruction="Static corporate rules " * 20,
        user_query="Analyze Gemini response",
    )

    def mock_gemini_handler(request: httpx.Request) -> httpx.Response:
        resp_data = {
            "candidates": [
                {"content": {"parts": [{"text": "Gemini analysis complete."}]}}
            ],
            "usageMetadata": {
                "promptTokenCount": 35000,
                "candidatesTokenCount": 60,
                "cachedContentTokenCount": 32768,
            },
        }
        return httpx.Response(200, json=resp_data)

    transport = httpx.MockTransport(mock_gemini_handler)

    with (
        patch(
            "app.core.llm_provider.httpx.AsyncClient",
            lambda *args, **kwargs: _RealAsyncClient(transport=transport),
        ),
        patch("app.core.llm_provider.get_settings") as mock_settings,
    ):
        settings_obj = Settings()
        settings_obj.GEMINI_API_KEY = "mock-gemini-key"
        mock_settings.return_value = settings_obj

        res = await call_upstream_llm_detailed(
            prompt="Analyze Gemini response",
            model="gemini-1.5-pro",
            compiled_prompt=compiled,
        )

    assert res is not None
    assert res.provider == "gemini"
    assert res.text == "Gemini analysis complete."
    assert res.telemetry.cache_hit is True
    assert res.telemetry.cached_tokens == 32768
    assert res.telemetry.uncached_input_tokens == 2232  # 35000 - 32768
    assert res.telemetry.estimated_savings_usd > 0.0


def test_provider_adapters_interface() -> None:
    """Verifies all provider adapters implement the ProviderPromptCacheAdapter contract."""
    anthropic_adapter = get_provider_adapter("claude-3-5-sonnet")
    openai_adapter = get_provider_adapter("gpt-4o")
    gemini_adapter = get_provider_adapter("gemini-1.5-pro")
    deepseek_adapter = get_provider_adapter("deepseek-chat")
    groq_adapter = get_provider_adapter("groq")

    # 1. Anthropic adapter verification
    ant_req = anthropic_adapter.prepare_request(
        static_prefix="System instructions",
        dynamic_suffix="User question",
        model="claude-3-5-sonnet",
        is_eligible=True,
    )
    assert ant_req["system"][0]["cache_control"] == {"type": "ephemeral"}
    ant_usage = anthropic_adapter.parse_usage(
        {
            "usage": {
                "input_tokens": 100,
                "output_tokens": 50,
                "cache_read_input_tokens": 800,
                "cache_creation_input_tokens": 0,
            }
        }
    )
    assert ant_usage["cached_input_tokens"] == 800
    assert ant_usage["uncached_input_tokens"] == 100

    # 2. OpenAI adapter verification
    oai_req = openai_adapter.prepare_request(
        static_prefix="System instructions",
        dynamic_suffix="User question",
        model="gpt-4o",
        is_eligible=True,
    )
    assert oai_req["messages"][0]["role"] == "system"
    oai_usage = openai_adapter.parse_usage(
        {
            "usage": {
                "prompt_tokens": 1000,
                "completion_tokens": 40,
                "prompt_tokens_details": {"cached_tokens": 500},
            }
        }
    )
    assert oai_usage["cached_input_tokens"] == 500
    assert oai_usage["uncached_input_tokens"] == 500

    # 3. Gemini adapter verification
    gem_req = gemini_adapter.prepare_request(
        static_prefix="System instructions",
        dynamic_suffix="User question",
        model="gemini-1.5-pro",
        is_eligible=True,
    )
    assert "systemInstruction" in gem_req
    gem_usage = gemini_adapter.parse_usage(
        {
            "usageMetadata": {
                "promptTokenCount": 35000,
                "candidatesTokenCount": 50,
                "cachedContentTokenCount": 32000,
            }
        }
    )
    assert gem_usage["cached_input_tokens"] == 32000

    # 4. DeepSeek adapter verification
    ds_usage = deepseek_adapter.parse_usage(
        {
            "usage": {
                "prompt_tokens": 200,
                "completion_tokens": 30,
                "prompt_tokens_details": {"cached_tokens": 150},
            }
        }
    )
    assert ds_usage["cached_input_tokens"] == 150

    # 5. Groq adapter verification
    assert groq_adapter.cache_capabilities().enabled is False
