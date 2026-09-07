"""Comprehensive Unit and Contract Tests for Phase 01 — Provider Foundation.

Verifies the complete Definition of Done for Phase 01:
1. Provider Interface Protocol contract (LLMProvider, complete, stream, capabilities).
2. Isolated provider adapters (Anthropic, OpenAI, Gemini, Groq, DeepSeek, OpenRouter).
3. Explicit ModelCapabilities schema and catalog (no guessing).
4. Normalized Error Taxonomy (retryable vs non-retryable, auth, quota, context_limit, unavailable, policy).
5. Zero Credential Leakage security invariant (all keys and auth tokens redacted).
6. Observable policy-driven ModelRouter and observable RoutingDecision.
7. Bounded FailoverManager with exponential backoff, jitter, retry budget, and fallback chaining.
8. Backward-compatible integration with call_upstream_llm_detailed.
"""

from __future__ import annotations

from unittest.mock import patch

import httpx
import pytest

from app.core.config import Settings
from app.core.llm_provider import (
    ProviderCacheTelemetry,
    UpstreamLLMResponse,
    call_upstream_llm,
    call_upstream_llm_detailed,
)
from app.providers.anthropic import AnthropicAdapter
from app.providers.base import (
    LLMProvider,
    ProviderRequest,
    ProviderResponse,
    get_model_capabilities,
)
from app.providers.deepseek import DeepSeekAdapter
from app.providers.errors import (
    ErrorCategory,
    ProviderAuthenticationError,
    ProviderContextLimitError,
    ProviderError,
    ProviderInvalidRequestError,
    ProviderPolicyError,
    ProviderQuotaError,
    ProviderRateLimitError,
    ProviderTimeoutError,
    ProviderUnavailableError,
    normalize_provider_error,
    sanitize_error_message,
)
from app.providers.gemini import GeminiAdapter
from app.providers.groq import GroqAdapter
from app.providers.openai import OpenAIAdapter
from app.providers.openrouter import OpenRouterAdapter
from app.providers.registry import get_provider_registry
from app.routing.failover import (
    FailoverConfig,
    FailoverManager,
)
from app.routing.router import (
    RoutingDecision,
    RoutingPolicy,
    get_model_router,
)

# ==============================================================================
# 1. Provider Interface & Registry Contract Tests
# ==============================================================================


def test_provider_protocol_conformance() -> None:
    """Verify all 6 provider adapters adhere to the LLMProvider protocol."""
    registry = get_provider_registry()

    adapters = [
        registry.get("anthropic"),
        registry.get("openai"),
        registry.get("gemini"),
        registry.get("groq"),
        registry.get("deepseek"),
        registry.get("openrouter"),
    ]

    for adapter in adapters:
        assert adapter is not None
        assert isinstance(adapter, LLMProvider)
        assert hasattr(adapter, "provider_name")
        assert callable(getattr(adapter, "complete", None))
        assert callable(getattr(adapter, "stream", None))
        assert callable(getattr(adapter, "capabilities", None))


def test_provider_registry_resolution() -> None:
    """Verify ProviderRegistry correctly resolves models to their respective adapters."""
    reg = get_provider_registry()

    assert reg.resolve_provider_name_for_model("claude-3-5-sonnet") == "anthropic"
    assert reg.resolve_provider_name_for_model("gpt-4o") == "openai"
    assert reg.resolve_provider_name_for_model("o1") == "openai"
    assert reg.resolve_provider_name_for_model("gemini-1.5-pro") == "gemini"
    assert reg.resolve_provider_name_for_model("llama-3.3-70b-versatile") == "groq"
    assert reg.resolve_provider_name_for_model("deepseek-chat") == "deepseek"
    assert (
        reg.resolve_provider_name_for_model("meta-llama/llama-3.1-70b") == "openrouter"
    )


# ==============================================================================
# 2. Explicit Provider Capability Model Tests
# ==============================================================================


def test_model_capabilities_explicit_catalog() -> None:
    """Verify explicit capabilities are returned without relying on string matching."""
    claude = get_model_capabilities("claude-3-5-sonnet")
    assert claude.provider == "anthropic"
    assert claude.context_window == 200_000
    assert claude.supports_streaming is True
    assert claude.supports_tools is True
    assert claude.supports_prompt_cache is True
    assert claude.input_pricing == 3.00
    assert claude.output_pricing == 15.00
    assert claude.cache_pricing == 0.30
    assert claude.min_cache_tokens == 1024

    gpt4o = get_model_capabilities("gpt-4o")
    assert gpt4o.provider == "openai"
    assert gpt4o.context_window == 128_000
    assert gpt4o.supports_prompt_cache is True
    assert gpt4o.input_pricing == 2.50
    assert gpt4o.cache_pricing == 1.25

    o1 = get_model_capabilities("o1")
    assert o1.supports_reasoning is True

    groq = get_model_capabilities("llama-3.3-70b-versatile")
    assert groq.provider == "groq"
    assert groq.supports_prompt_cache is False

    deepseek = get_model_capabilities("deepseek-chat")
    assert deepseek.provider == "deepseek"
    assert deepseek.supports_prompt_cache is True
    assert deepseek.min_cache_tokens == 64

    gemini = get_model_capabilities("gemini-1.5-pro")
    assert gemini.provider == "gemini"
    assert gemini.min_cache_tokens == 32768
    assert gemini.context_window == 2_097_152


# ==============================================================================
# 3. Normalized Error Taxonomy & Secret Redaction Tests
# ==============================================================================


def test_error_normalization_classification() -> None:
    """Verify exact categorization across all required error classes."""
    # 1. Authentication (401/403)
    e1 = normalize_provider_error(
        "anthropic", 401, {"error": {"message": "invalid x-api-key"}}
    )
    assert isinstance(e1, ProviderAuthenticationError)
    assert e1.category == ErrorCategory.AUTHENTICATION
    assert e1.is_retryable is False

    # 2. Quota / Billing Exceeded (402 or 429 quota)
    e2 = normalize_provider_error(
        "openai", 429, {"error": {"message": "You exceeded your current quota"}}
    )
    assert isinstance(e2, ProviderQuotaError)
    assert e2.category == ErrorCategory.QUOTA
    assert e2.is_retryable is False

    # 3. Rate Limit (429 with retry_after)
    e3 = normalize_provider_error(
        "openai", 429, {"error": {"message": "Rate limit reached"}}, retry_after=2.5
    )
    assert isinstance(e3, ProviderRateLimitError)
    assert e3.category == ErrorCategory.RETRYABLE
    assert e3.is_retryable is True
    assert e3.retry_after_seconds == 2.5

    # 4. Context Limit Exceeded (400 token length)
    e4 = normalize_provider_error(
        "gemini",
        400,
        {"error": {"message": "Maximum context length exceeded: 130000 > 128000"}},
    )
    assert isinstance(e4, ProviderContextLimitError)
    assert e4.category == ErrorCategory.CONTEXT_LIMIT
    assert e4.is_retryable is False

    # 5. Provider Unavailable (503 / 502 / 529)
    e5 = normalize_provider_error(
        "anthropic", 529, {"error": {"message": "Overloaded"}}
    )
    assert isinstance(e5, ProviderUnavailableError)
    assert e5.category == ErrorCategory.PROVIDER_UNAVAILABLE
    assert e5.is_retryable is True

    # 6. Policy / Safety Rejection (400 safety)
    e6 = normalize_provider_error(
        "gemini", 400, {"error": {"message": "Blocked due to safety harm_category"}}
    )
    assert isinstance(e6, ProviderPolicyError)
    assert e6.category == ErrorCategory.POLICY_REJECTED
    assert e6.is_retryable is False

    # 7. Network / Timeout
    e7 = normalize_provider_error(
        "groq", 408, {"error": {"message": "Request timeout"}}
    )
    assert isinstance(e7, ProviderTimeoutError)
    assert e7.category == ErrorCategory.RETRYABLE
    assert e7.is_retryable is True


def test_zero_credential_leakage_invariant() -> None:
    """Verify API keys, tokens, and authorization headers are scrubbed from all errors."""
    raw_leak = (
        "Failed request with header Authorization: Bearer sk-proj-1234567890abcdefghijklmnop "
        "and key=AIzaSyA1234567890123456789012345678901 and x-api-key: sk-ant-secret12345678"
    )

    clean = sanitize_error_message(raw_leak)
    assert "sk-proj-1234567890abcdefghijklmnop" not in clean
    assert "AIzaSyA1234567890123456789012345678901" not in clean
    assert "sk-ant-secret12345678" not in clean
    assert "[REDACTED_SECRET]" in clean

    err = ProviderAuthenticationError(
        message="Invalid key: sk-ant-api03-abcdef1234567890",
        provider="anthropic",
    )
    assert "sk-ant-api03" not in str(err)
    assert "sk-ant-api03" not in err.message
    assert "[REDACTED_SECRET]" in str(err)


# ==============================================================================
# 4. Observable Model Routing Tests
# ==============================================================================


def test_model_router_observable_decision() -> None:
    """Verify ModelRouter generates explicit, observable RoutingDecisions with reasons."""
    router = get_model_router()

    # 1. Standard request
    policy = RoutingPolicy(requested_model="claude-3-5-sonnet")
    decision = router.route(policy)

    assert decision.selected_provider == "anthropic"
    assert decision.selected_model == "claude-3-5-sonnet"
    assert len(decision.fallback_chain) > 0
    assert ("openai", "gpt-4o") in decision.fallback_chain
    assert len(decision.decision_reasons) > 0
    assert decision.is_observable is True

    telemetry = decision.to_dict()
    assert "selected_provider" in telemetry
    assert "decision_reasons" in telemetry
    assert len(telemetry["decision_reasons"]) >= 3


def test_model_router_reasoning_workload() -> None:
    """Verify router selects reasoning model when required capability is specified."""
    router = get_model_router()

    policy = RoutingPolicy(
        requested_model="gpt-4o",
        required_capabilities=["supports_reasoning"],
    )
    decision = router.route(policy)
    assert decision.selected_model == "o3-mini"
    assert any("reasoning" in r for r in decision.decision_reasons)


def test_model_router_budget_enforcement() -> None:
    """Verify router automatically down-tiers when input cost exceeds budget."""
    router = get_model_router()

    # gpt-4o is $2.50/M input; set budget at $1.00/M
    policy = RoutingPolicy(
        requested_model="gpt-4o",
        max_input_cost_per_million=1.00,
    )
    decision = router.route(policy)
    assert decision.selected_model == "gpt-4o-mini"
    assert decision.estimated_input_cost == 0.15
    assert any("Down-tiered" in r for r in decision.decision_reasons)


def test_model_router_disallowed_provider() -> None:
    """Verify router respects disallowed providers and avoids them in primary and fallback."""
    router = get_model_router()

    policy = RoutingPolicy(
        requested_model="claude-3-5-sonnet",
        disallowed_providers=["anthropic"],
    )
    decision = router.route(policy)
    assert decision.selected_provider != "anthropic"
    for p, _ in decision.fallback_chain:
        assert p != "anthropic"


# ==============================================================================
# 5. Bounded Failover Manager Tests
# ==============================================================================


@pytest.mark.asyncio
async def test_failover_non_retryable_aborts_retries() -> None:
    """Verify non-retryable error (e.g. 401 Auth) terminates provider attempts immediately."""
    config = FailoverConfig(max_retries_per_provider=2, max_total_attempts=3)
    failover_mgr = FailoverManager(config=config)

    attempt_count = 0

    class MockFailingAuthAdapter(AnthropicAdapter):
        async def complete(
            self, request: ProviderRequest, client: httpx.AsyncClient | None = None
        ) -> ProviderResponse:
            nonlocal attempt_count
            attempt_count += 1
            raise ProviderAuthenticationError(
                message="Bad API key", provider="anthropic", status_code=401
            )

    registry = get_provider_registry()
    original_adapter = registry.get("anthropic")
    registry.register("anthropic", MockFailingAuthAdapter())

    try:
        req = ProviderRequest(model="claude-3-5-sonnet", prompt="Hello")
        decision = RoutingDecision(
            selected_provider="anthropic",
            selected_model="claude-3-5-sonnet",
            fallback_chain=[],  # No fallback
        )

        with pytest.raises(ProviderAuthenticationError):
            await failover_mgr.execute_with_failover(req, decision)

        # Must have attempted exactly once (NO retries on auth failure)
        assert attempt_count == 1
    finally:
        if original_adapter:
            registry.register("anthropic", original_adapter)


@pytest.mark.asyncio
async def test_failover_retryable_recovers_with_backoff() -> None:
    """Verify retryable 503 error retries up to threshold and succeeds on retry."""
    config = FailoverConfig(
        max_retries_per_provider=2,
        base_delay_seconds=0.01,  # Fast for unit test
        backoff_factor=1.0,
    )
    failover_mgr = FailoverManager(config=config)
    calls = 0

    class MockTransientFailAdapter(OpenAIAdapter):
        async def complete(
            self, request: ProviderRequest, client: httpx.AsyncClient | None = None
        ) -> ProviderResponse:
            nonlocal calls
            calls += 1
            if calls == 1:
                raise ProviderUnavailableError(
                    message="Service overloaded (503)",
                    provider="openai",
                    status_code=503,
                )
            return ProviderResponse(
                text="Success on retry",
                model=request.model,
                provider="openai",
                telemetry=ProviderCacheTelemetry(
                    provider="openai", model=request.model
                ),
            )

    registry = get_provider_registry()
    original_adapter = registry.get("openai")
    registry.register("openai", MockTransientFailAdapter())

    try:
        req = ProviderRequest(model="gpt-4o", prompt="Hello")
        decision = RoutingDecision(
            selected_provider="openai",
            selected_model="gpt-4o",
            fallback_chain=[],
        )

        res = await failover_mgr.execute_with_failover(req, decision)
        assert res.text == "Success on retry"
        assert calls == 2  # 1 failure + 1 successful retry
    finally:
        if original_adapter:
            registry.register("openai", original_adapter)


@pytest.mark.asyncio
async def test_failover_cross_provider_fallback_chain() -> None:
    """Verify execution falls back to secondary provider candidate when primary fails."""
    config = FailoverConfig(
        max_retries_per_provider=0,  # Fail immediately to fallback
        max_total_attempts=3,
    )
    failover_mgr = FailoverManager(config=config)

    class FailingPrimaryAdapter(AnthropicAdapter):
        async def complete(
            self, request: ProviderRequest, client: httpx.AsyncClient | None = None
        ) -> ProviderResponse:
            raise ProviderUnavailableError(
                "Anthropic endpoint down", provider="anthropic"
            )

    class WorkingSecondaryAdapter(OpenAIAdapter):
        async def complete(
            self, request: ProviderRequest, client: httpx.AsyncClient | None = None
        ) -> ProviderResponse:
            return ProviderResponse(
                text="Response from secondary fallback",
                model=request.model,
                provider="openai",
                telemetry=ProviderCacheTelemetry(
                    provider="openai", model=request.model
                ),
            )

    registry = get_provider_registry()
    orig_anthropic = registry.get("anthropic")
    orig_openai = registry.get("openai")

    registry.register("anthropic", FailingPrimaryAdapter())
    registry.register("openai", WorkingSecondaryAdapter())

    try:
        req = ProviderRequest(model="claude-3-5-sonnet", prompt="Execute task")
        decision = RoutingDecision(
            selected_provider="anthropic",
            selected_model="claude-3-5-sonnet",
            fallback_chain=[("openai", "gpt-4o")],
        )

        res = await failover_mgr.execute_with_failover(req, decision)
        assert res.provider == "openai"
        assert res.text == "Response from secondary fallback"
    finally:
        if orig_anthropic:
            registry.register("anthropic", orig_anthropic)
        if orig_openai:
            registry.register("openai", orig_openai)


# ==============================================================================
# 6. End-to-End Dispatcher & Backward Compatibility Tests
# ==============================================================================


@pytest.mark.asyncio
async def test_call_upstream_llm_detailed_backward_compatibility() -> None:
    """Verify call_upstream_llm_detailed dispatches through new provider foundation."""
    mock_payload = {
        "choices": [
            {"message": {"role": "assistant", "content": "Backward compatible output."}}
        ],
        "usage": {
            "prompt_tokens": 100,
            "completion_tokens": 20,
            "prompt_tokens_details": {"cached_tokens": 50},
        },
    }

    def mock_handler(request: httpx.Request) -> httpx.Response:
        return httpx.Response(200, json=mock_payload)

    transport = httpx.MockTransport(mock_handler)
    real_async_client = httpx.AsyncClient

    with (
        patch(
            "app.core.llm_provider.httpx.AsyncClient",
            lambda *args, **kwargs: real_async_client(transport=transport),
        ),
        patch("app.core.llm_provider.get_settings") as mock_settings,
    ):
        settings_obj = Settings()
        settings_obj.OPENAI_API_KEY = "sk-test-openai-backward-compat"
        mock_settings.return_value = settings_obj

        res = await call_upstream_llm_detailed(
            prompt="Test prompt",
            model="gpt-4o",
        )

    assert res is not None
    assert isinstance(res, UpstreamLLMResponse)
    assert res.text == "Backward compatible output."
    assert res.provider == "openai"
    assert res.telemetry.cached_tokens == 50
    assert res.telemetry.cache_hit is True
    assert res.telemetry.uncached_input_tokens == 50


@pytest.mark.asyncio
async def test_call_upstream_llm_convenience_wrapper() -> None:
    """Verify call_upstream_llm string convenience wrapper functions seamlessly."""
    mock_payload = {
        "choices": [
            {"message": {"role": "assistant", "content": "Simple text response."}}
        ],
        "usage": {"prompt_tokens": 20, "completion_tokens": 10},
    }

    transport = httpx.MockTransport(lambda req: httpx.Response(200, json=mock_payload))
    real_async_client = httpx.AsyncClient

    with (
        patch(
            "app.core.llm_provider.httpx.AsyncClient",
            lambda *args, **kwargs: real_async_client(transport=transport),
        ),
        patch("app.core.llm_provider.get_settings") as mock_settings,
    ):
        settings_obj = Settings()
        settings_obj.OPENAI_API_KEY = "sk-test-simple"
        mock_settings.return_value = settings_obj

        text = await call_upstream_llm(prompt="Hello", model="gpt-4o")

    assert text == "Simple text response."


# ==============================================================================
# 7. Comprehensive Provider Adapter Execution & Streaming Coverage
# ==============================================================================


@pytest.mark.asyncio
async def test_anthropic_adapter_complete_and_stream() -> None:
    """Test AnthropicAdapter execution, caching metrics, and streaming."""
    adapter = AnthropicAdapter()

    # 1. Complete Success with Cache Write & Read
    resp_body = {
        "content": [{"type": "text", "text": "Anthropic response"}],
        "model": "claude-3-5-sonnet-20241022",
        "usage": {
            "input_tokens": 100,
            "output_tokens": 25,
            "cache_read_input_tokens": 80,
            "cache_creation_input_tokens": 20,
        },
        "stop_reason": "end_turn",
    }
    client = httpx.AsyncClient(
        transport=httpx.MockTransport(lambda req: httpx.Response(200, json=resp_body))
    )
    req = ProviderRequest(
        model="claude-3-5-sonnet",
        prompt="Hi Claude",
        system_instruction="You are Claude.",
        api_key="sk-ant-test",
    )
    res = await adapter.complete(req, client=client)
    assert res.text == "Anthropic response"
    assert res.provider == "anthropic"
    assert res.telemetry.cache_hit is True
    assert res.telemetry.cached_tokens == 80
    assert res.telemetry.cache_write_tokens == 20

    # 2. Complete Failure -> Raises Normalized Error
    err_client = httpx.AsyncClient(
        transport=httpx.MockTransport(
            lambda req: httpx.Response(
                401, json={"error": {"message": "invalid api key"}}
            )
        )
    )
    with pytest.raises(ProviderAuthenticationError):
        await adapter.complete(req, client=err_client)

    # 3. Streaming Success
    sse_data = (
        'data: {"type": "content_block_delta", "delta": {"type": "text_delta", "text": "Hello "}}\n\n'
        'data: {"type": "content_block_delta", "delta": {"type": "text_delta", "text": "streaming!"}}\n\n'
        'data: {"type": "message_delta", "delta": {"stop_reason": "end_turn"}}\n\n'
        "data: [DONE]\n\n"
    )
    stream_client = httpx.AsyncClient(
        transport=httpx.MockTransport(lambda req: httpx.Response(200, text=sse_data))
    )
    chunks = []
    async for chunk in adapter.stream(req, client=stream_client):
        chunks.append(chunk.delta_text)
    assert "".join(chunks) == "Hello streaming!"

    # 4. Streaming Failure
    err_stream_client = httpx.AsyncClient(
        transport=httpx.MockTransport(
            lambda req: httpx.Response(529, json={"error": {"message": "overloaded"}})
        )
    )
    with pytest.raises(ProviderUnavailableError):
        async for _ in adapter.stream(req, client=err_stream_client):
            pass


@pytest.mark.asyncio
async def test_openai_adapter_complete_and_stream() -> None:
    """Test OpenAIAdapter execution, structured tools, and streaming."""
    adapter = OpenAIAdapter()

    # 1. Complete Success with Tool Calls
    resp_body = {
        "choices": [
            {
                "message": {
                    "role": "assistant",
                    "content": "Using a tool",
                    "tool_calls": [
                        {
                            "id": "call_1",
                            "type": "function",
                            "function": {"name": "query"},
                        }
                    ],
                },
                "finish_reason": "tool_calls",
            }
        ],
        "model": "gpt-4o",
        "usage": {
            "prompt_tokens": 120,
            "completion_tokens": 15,
            "prompt_tokens_details": {"cached_tokens": 60},
        },
    }
    client = httpx.AsyncClient(
        transport=httpx.MockTransport(lambda req: httpx.Response(200, json=resp_body))
    )
    req = ProviderRequest(
        model="gpt-4o",
        prompt="Execute query",
        api_key="sk-proj-test",
        tools=[{"type": "function", "function": {"name": "query"}}],
    )
    res = await adapter.complete(req, client=client)
    assert res.text == "Using a tool"
    assert res.finish_reason == "tool_calls"
    assert res.tool_calls is not None
    assert res.telemetry.cached_tokens == 60

    # 2. Complete Failure -> Raises Normalized Error
    err_client = httpx.AsyncClient(
        transport=httpx.MockTransport(
            lambda req: httpx.Response(
                429, json={"error": {"message": "quota exceeded"}}
            )
        )
    )
    with pytest.raises(ProviderQuotaError):
        await adapter.complete(req, client=err_client)

    # 3. Streaming Success
    sse_data = (
        'data: {"choices": [{"delta": {"content": "Chunk 1 "}}]}\n\n'
        'data: {"choices": [{"delta": {"content": "Chunk 2"}, "finish_reason": "stop"}]}\n\n'
        "data: [DONE]\n\n"
    )
    stream_client = httpx.AsyncClient(
        transport=httpx.MockTransport(lambda req: httpx.Response(200, text=sse_data))
    )
    chunks = []
    async for chunk in adapter.stream(req, client=stream_client):
        chunks.append(chunk.delta_text)
    assert "".join(chunks) == "Chunk 1 Chunk 2"

    # 4. Streaming Failure
    err_stream_client = httpx.AsyncClient(
        transport=httpx.MockTransport(
            lambda req: httpx.Response(
                401, json={"error": {"message": "invalid token"}}
            )
        )
    )
    with pytest.raises(ProviderAuthenticationError):
        async for _ in adapter.stream(req, client=err_stream_client):
            pass


@pytest.mark.asyncio
async def test_gemini_adapter_complete_and_stream() -> None:
    """Test GeminiAdapter execution, cached content telemetry, and streaming."""
    adapter = GeminiAdapter()

    # 1. Complete Success with Context Caching
    resp_body = {
        "candidates": [
            {
                "content": {"parts": [{"text": "Gemini response text"}]},
                "finishReason": "STOP",
            }
        ],
        "usageMetadata": {
            "promptTokenCount": 2048,
            "cachedContentTokenCount": 1024,
            "candidatesTokenCount": 50,
        },
    }
    client = httpx.AsyncClient(
        transport=httpx.MockTransport(lambda req: httpx.Response(200, json=resp_body))
    )
    req = ProviderRequest(
        model="gemini-1.5-pro",
        prompt="Tell me about AI",
        api_key="AIzaSyTestKey",
    )
    res = await adapter.complete(req, client=client)
    assert res.text == "Gemini response text"
    assert res.telemetry.cached_tokens == 1024
    assert res.telemetry.cache_hit is True

    # 2. Complete Failure -> Raises Normalized Error
    err_client = httpx.AsyncClient(
        transport=httpx.MockTransport(
            lambda req: httpx.Response(
                400,
                json={
                    "error": {
                        "message": "maximum context length exceeded: 200000 > 128000"
                    }
                },
            )
        )
    )
    with pytest.raises(ProviderContextLimitError):
        await adapter.complete(req, client=err_client)

    # 3. Streaming Success
    sse_data = (
        'data: {"candidates": [{"content": {"parts": [{"text": "Streaming "}]}}]}\n\n'
        'data: {"candidates": [{"content": {"parts": [{"text": "Gemini!"}]}, "finishReason": "STOP"}]}\n\n'
    )
    stream_client = httpx.AsyncClient(
        transport=httpx.MockTransport(lambda req: httpx.Response(200, text=sse_data))
    )
    chunks = []
    async for chunk in adapter.stream(req, client=stream_client):
        chunks.append(chunk.delta_text)
    assert "".join(chunks) == "Streaming Gemini!"

    # 4. Streaming Failure
    err_stream_client = httpx.AsyncClient(
        transport=httpx.MockTransport(
            lambda req: httpx.Response(
                400, json={"error": {"message": "harm category blocked"}}
            )
        )
    )
    with pytest.raises(ProviderPolicyError):
        async for _ in adapter.stream(req, client=err_stream_client):
            pass


@pytest.mark.asyncio
async def test_groq_adapter_complete_and_stream() -> None:
    """Test GroqAdapter LPU inference and streaming."""
    adapter = GroqAdapter()

    # 1. Complete Success (Zero Prompt-Cache Policy)
    resp_body = {
        "choices": [
            {
                "message": {"role": "assistant", "content": "Fast LPU response"},
                "finish_reason": "stop",
            }
        ],
        "model": "llama-3.3-70b-versatile",
        "usage": {"prompt_tokens": 50, "completion_tokens": 12},
    }
    client = httpx.AsyncClient(
        transport=httpx.MockTransport(lambda req: httpx.Response(200, json=resp_body))
    )
    req = ProviderRequest(
        model="llama-3.3-70b-versatile",
        prompt="Speed test",
        api_key="gsk_test_groq_key",
    )
    res = await adapter.complete(req, client=client)
    assert res.text == "Fast LPU response"
    assert res.telemetry.is_cache_eligible is False
    assert res.telemetry.cached_tokens == 0

    # 2. Complete Failure -> Raises Normalized Error
    err_client = httpx.AsyncClient(
        transport=httpx.MockTransport(
            lambda req: httpx.Response(
                429,
                json={"error": {"message": "Rate limit reached"}},
                headers={"retry-after": "5"},
            )
        )
    )
    with pytest.raises(ProviderRateLimitError) as exc_info:
        await adapter.complete(req, client=err_client)
    assert exc_info.value.retry_after_seconds == 5.0

    # 3. Streaming Success
    sse_data = (
        'data: {"choices": [{"delta": {"content": "Fast "}}]}\n\n'
        'data: {"choices": [{"delta": {"content": "Groq"}, "finish_reason": "stop"}]}\n\n'
        "data: [DONE]\n\n"
    )
    stream_client = httpx.AsyncClient(
        transport=httpx.MockTransport(lambda req: httpx.Response(200, text=sse_data))
    )
    chunks = []
    async for chunk in adapter.stream(req, client=stream_client):
        chunks.append(chunk.delta_text)
    assert "".join(chunks) == "Fast Groq"

    # 4. Streaming Failure
    err_stream_client = httpx.AsyncClient(
        transport=httpx.MockTransport(
            lambda req: httpx.Response(503, text="Service Unavailable")
        )
    )
    with pytest.raises(ProviderUnavailableError):
        async for _ in adapter.stream(req, client=err_stream_client):
            pass


@pytest.mark.asyncio
async def test_deepseek_adapter_complete_and_stream() -> None:
    """Test DeepSeekAdapter 64-token prefix cache handling and streaming."""
    adapter = DeepSeekAdapter()

    # 1. Complete Success with 64-token cache hit
    resp_body = {
        "choices": [
            {
                "message": {"role": "assistant", "content": "DeepSeek answer"},
                "finish_reason": "stop",
            }
        ],
        "model": "deepseek-chat",
        "usage": {
            "prompt_tokens": 128,
            "completion_tokens": 20,
            "prompt_tokens_details": {"cached_tokens": 64},
        },
    }
    client = httpx.AsyncClient(
        transport=httpx.MockTransport(lambda req: httpx.Response(200, json=resp_body))
    )
    req = ProviderRequest(
        model="deepseek-chat",
        prompt="Explain KV caching",
        api_key="sk-deepseek-test",
    )
    res = await adapter.complete(req, client=client)
    assert res.text == "DeepSeek answer"
    assert res.telemetry.cached_tokens == 64
    assert res.telemetry.cache_hit is True

    # 2. Complete Failure -> Raises Normalized Error
    err_client = httpx.AsyncClient(
        transport=httpx.MockTransport(
            lambda req: httpx.Response(
                402, json={"error": {"message": "Insufficient balance"}}
            )
        )
    )
    with pytest.raises(ProviderQuotaError):
        await adapter.complete(req, client=err_client)

    # 3. Streaming Success
    sse_data = (
        'data: {"choices": [{"delta": {"content": "Deep"}}]}\n\n'
        'data: {"choices": [{"delta": {"content": "Seek"}, "finish_reason": "stop"}]}\n\n'
        "data: [DONE]\n\n"
    )
    stream_client = httpx.AsyncClient(
        transport=httpx.MockTransport(lambda req: httpx.Response(200, text=sse_data))
    )
    chunks = []
    async for chunk in adapter.stream(req, client=stream_client):
        chunks.append(chunk.delta_text)
    assert "".join(chunks) == "DeepSeek"

    # 4. Streaming Failure
    err_stream_client = httpx.AsyncClient(
        transport=httpx.MockTransport(
            lambda req: httpx.Response(503, text="Service Overloaded")
        )
    )
    with pytest.raises(ProviderUnavailableError):
        async for _ in adapter.stream(req, client=err_stream_client):
            pass


@pytest.mark.asyncio
async def test_openrouter_adapter_complete_and_stream() -> None:
    """Test OpenRouterAdapter headers, routing, and streaming."""
    adapter = OpenRouterAdapter()

    captured_headers: dict[str, str] = {}

    def mock_handler(req: httpx.Request) -> httpx.Response:
        nonlocal captured_headers
        captured_headers = dict(req.headers)
        return httpx.Response(
            200,
            json={
                "choices": [
                    {
                        "message": {
                            "role": "assistant",
                            "content": "OpenRouter output",
                        },
                        "finish_reason": "stop",
                    }
                ],
                "model": "meta-llama/llama-3.1-70b-instruct",
                "usage": {"prompt_tokens": 40, "completion_tokens": 10},
            },
        )

    client = httpx.AsyncClient(transport=httpx.MockTransport(mock_handler))
    req = ProviderRequest(
        model="meta-llama/llama-3.1-70b-instruct",
        prompt="Hi OpenRouter",
        api_key="sk-or-v1-test",
    )
    res = await adapter.complete(req, client=client)
    assert res.text == "OpenRouter output"
    assert "http-referer" in captured_headers
    assert "x-title" in captured_headers

    # 2. Complete Failure -> Raises Normalized Error
    err_client = httpx.AsyncClient(
        transport=httpx.MockTransport(
            lambda req: httpx.Response(
                408, json={"error": {"message": "Upstream timeout"}}
            )
        )
    )
    with pytest.raises(ProviderTimeoutError):
        await adapter.complete(req, client=err_client)

    # 3. Streaming Success
    sse_data = (
        'data: {"choices": [{"delta": {"content": "Open"}}]}\n\n'
        'data: {"choices": [{"delta": {"content": "Router"}, "finish_reason": "stop"}]}\n\n'
        "data: [DONE]\n\n"
    )
    stream_client = httpx.AsyncClient(
        transport=httpx.MockTransport(lambda req: httpx.Response(200, text=sse_data))
    )
    chunks = []
    async for chunk in adapter.stream(req, client=stream_client):
        chunks.append(chunk.delta_text)
    assert "".join(chunks) == "OpenRouter"

    # 4. Streaming Failure
    err_stream_client = httpx.AsyncClient(
        transport=httpx.MockTransport(
            lambda req: httpx.Response(
                400, json={"error": {"message": "context length 200000 > 128000"}}
            )
        )
    )
    with pytest.raises(ProviderContextLimitError):
        async for _ in adapter.stream(req, client=err_stream_client):
            pass


def test_registry_methods_extended() -> None:
    """Verify registry provider listing, capability retrieval, and fallback resolution."""
    reg = get_provider_registry()

    providers = reg.list_providers()
    assert "anthropic" in providers
    assert "openai" in providers
    assert "gemini" in providers
    assert "groq" in providers
    assert "deepseek" in providers
    assert "openrouter" in providers

    caps = reg.list_capabilities()
    assert len(caps) >= 14

    # Preferred provider override
    adapter = reg.resolve_for_model("gpt-4o", preferred_provider="gemini")
    assert isinstance(adapter, GeminiAdapter)

    # Unknown model fallback
    unknown_adapter = reg.resolve_for_model("some-unrecognized-model-name")
    assert unknown_adapter is not None


def test_router_constraints_and_downgrades_extended() -> None:
    """Verify router constraint enforcement, reasoning rerouting, and cost downgrading."""
    router = get_model_router()

    # 1. Allowed providers constraint (forces fallback to allowed provider)
    policy_allowed = RoutingPolicy(
        requested_model="gpt-4o",
        allowed_providers=["gemini", "groq"],
    )
    decision = router.route(policy_allowed)
    assert decision.selected_provider in ("gemini", "groq")

    # 2. Disallowed providers constraint (forces alternative)
    policy_disallowed = RoutingPolicy(
        requested_model="gpt-4o",
        disallowed_providers=["openai", "anthropic"],
    )
    decision = router.route(policy_disallowed)
    assert decision.selected_provider not in ("openai", "anthropic")

    # 3. Reasoning requirement with DeepSeek
    policy_deepseek_reason = RoutingPolicy(
        requested_model="deepseek-chat",
        required_capabilities=["supports_reasoning"],
    )
    decision = router.route(policy_deepseek_reason)
    assert decision.selected_model == "deepseek-reasoner"

    # 4. Reasoning requirement with non-reasoning provider (reroutes to o3-mini)
    policy_gemini_reason = RoutingPolicy(
        requested_model="gemini-1.5-flash",
        required_capabilities=["supports_reasoning"],
    )
    decision = router.route(policy_gemini_reason)
    assert decision.selected_model == "o3-mini"
    assert decision.selected_provider == "openai"

    # 5. Cost budget downgrade for Anthropic
    policy_cost_anthropic = RoutingPolicy(
        requested_model="claude-3-5-sonnet",
        max_input_cost_per_million=1.0,  # Below $3.0
    )
    decision = router.route(policy_cost_anthropic)
    assert decision.selected_model == "claude-3-haiku"

    # 6. Cost budget downgrade for Gemini
    policy_cost_gemini = RoutingPolicy(
        requested_model="gemini-1.5-pro",
        max_input_cost_per_million=0.5,  # Below $1.25
    )
    decision = router.route(policy_cost_gemini)
    assert decision.selected_model == "gemini-1.5-flash"

    # 7. Fallback chains for Gemini, Groq, DeepSeek
    decision_gem = router.route(
        RoutingPolicy(requested_model="gemini-1.5-pro", allow_fallback=True)
    )
    assert any(p == "openai" for p, m in decision_gem.fallback_chain)

    decision_groq = router.route(
        RoutingPolicy(requested_model="llama-3.3-70b-versatile", allow_fallback=True)
    )
    assert any(p == "openai" for p, m in decision_groq.fallback_chain)

    decision_deepseek = router.route(
        RoutingPolicy(requested_model="deepseek-chat", allow_fallback=True)
    )
    assert any(p == "openai" for p, m in decision_deepseek.fallback_chain)


@pytest.mark.asyncio
async def test_failover_limits_and_unexpected_errors() -> None:
    """Test skipping unregistered providers, unexpected crash wrapping, and total fallback exhaustion."""
    req = ProviderRequest(model="model_x", prompt="hi", api_key="test-key")
    client = httpx.AsyncClient(
        transport=httpx.MockTransport(
            lambda r: httpx.Response(
                200, json={"choices": [{"message": {"content": "ok"}}], "usage": {}}
            )
        )
    )

    # 1. Unknown provider in decision chain is skipped to next candidate
    decision = RoutingDecision(
        selected_provider="non_existent_provider",
        selected_model="model_x",
        fallback_chain=[("openai", "gpt-4o-mini")],
    )
    failover_mgr = FailoverManager(
        FailoverConfig(max_delay_seconds=0.5, base_delay_seconds=0.1)
    )
    res = await failover_mgr.execute_with_failover(req, decision, client=client)
    assert res.text == "ok"

    # 2. Unexpected non-ProviderError exception is wrapped into ProviderError
    class BuggyAdapter(AnthropicAdapter):
        async def complete(
            self, request: ProviderRequest, client: httpx.AsyncClient | None = None
        ) -> ProviderResponse:
            raise RuntimeError("Unexpected internal crash")

    reg = get_provider_registry()
    orig = reg.get("anthropic")
    reg.register("anthropic", BuggyAdapter())
    try:
        dec2 = RoutingDecision(
            selected_provider="anthropic", selected_model="claude-3-haiku"
        )
        with pytest.raises(ProviderError) as exc_info:
            await failover_mgr.execute_with_failover(req, dec2, client=client)
        assert "Unexpected internal crash" in exc_info.value.message
    finally:
        if orig:
            reg.register("anthropic", orig)

    # 3. All providers exhausted without last_error
    dec3 = RoutingDecision(
        selected_provider="non_existent_1",
        selected_model="m1",
        fallback_chain=[("non_existent_2", "m2")],
    )
    with pytest.raises(ProviderError) as exc_info2:
        await failover_mgr.execute_with_failover(req, dec3, client=client)
    assert exc_info2.value.category == ErrorCategory.PROVIDER_UNAVAILABLE


def test_errors_additional_branches() -> None:
    """Test 400 bad syntax, generic network error, and unmapped status fallback."""
    # Status 400 without specific error message -> ProviderInvalidRequestError
    e1 = normalize_provider_error("test", 400, "Bad syntax")
    assert isinstance(e1, ProviderInvalidRequestError)

    # General network exception
    class MockConnectionError(Exception):
        pass

    e2 = normalize_provider_error("test", None, exc=MockConnectionError("DNS failure"))
    assert isinstance(e2, ProviderUnavailableError)

    # Fallback ProviderError
    e3 = normalize_provider_error("test", 418, "I am a teapot")
    assert type(e3) is ProviderError
