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
from app.providers.errors import (
    ErrorCategory,
    ProviderAuthenticationError,
    ProviderContextLimitError,
    ProviderPolicyError,
    ProviderQuotaError,
    ProviderRateLimitError,
    ProviderTimeoutError,
    ProviderUnavailableError,
    normalize_provider_error,
    sanitize_error_message,
)
from app.providers.openai import OpenAIAdapter
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
    assert reg.resolve_provider_name_for_model("meta-llama/llama-3.1-70b") == "openrouter"


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
    e1 = normalize_provider_error("anthropic", 401, {"error": {"message": "invalid x-api-key"}})
    assert isinstance(e1, ProviderAuthenticationError)
    assert e1.category == ErrorCategory.AUTHENTICATION
    assert e1.is_retryable is False

    # 2. Quota / Billing Exceeded (402 or 429 quota)
    e2 = normalize_provider_error("openai", 429, {"error": {"message": "You exceeded your current quota"}})
    assert isinstance(e2, ProviderQuotaError)
    assert e2.category == ErrorCategory.QUOTA
    assert e2.is_retryable is False

    # 3. Rate Limit (429 with retry_after)
    e3 = normalize_provider_error("openai", 429, {"error": {"message": "Rate limit reached"}}, retry_after=2.5)
    assert isinstance(e3, ProviderRateLimitError)
    assert e3.category == ErrorCategory.RETRYABLE
    assert e3.is_retryable is True
    assert e3.retry_after_seconds == 2.5

    # 4. Context Limit Exceeded (400 token length)
    e4 = normalize_provider_error("gemini", 400, {"error": {"message": "Maximum context length exceeded: 130000 > 128000"}})
    assert isinstance(e4, ProviderContextLimitError)
    assert e4.category == ErrorCategory.CONTEXT_LIMIT
    assert e4.is_retryable is False

    # 5. Provider Unavailable (503 / 502 / 529)
    e5 = normalize_provider_error("anthropic", 529, {"error": {"message": "Overloaded"}})
    assert isinstance(e5, ProviderUnavailableError)
    assert e5.category == ErrorCategory.PROVIDER_UNAVAILABLE
    assert e5.is_retryable is True

    # 6. Policy / Safety Rejection (400 safety)
    e6 = normalize_provider_error("gemini", 400, {"error": {"message": "Blocked due to safety harm_category"}})
    assert isinstance(e6, ProviderPolicyError)
    assert e6.category == ErrorCategory.POLICY_REJECTED
    assert e6.is_retryable is False

    # 7. Network / Timeout
    e7 = normalize_provider_error("groq", 408, {"error": {"message": "Request timeout"}})
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
        async def complete(self, request: ProviderRequest, client: httpx.AsyncClient | None = None) -> ProviderResponse:
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
        async def complete(self, request: ProviderRequest, client: httpx.AsyncClient | None = None) -> ProviderResponse:
            nonlocal calls
            calls += 1
            if calls == 1:
                raise ProviderUnavailableError(
                    message="Service overloaded (503)", provider="openai", status_code=503
                )
            return ProviderResponse(
                text="Success on retry",
                model=request.model,
                provider="openai",
                telemetry=ProviderCacheTelemetry(provider="openai", model=request.model),
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
        async def complete(self, request: ProviderRequest, client: httpx.AsyncClient | None = None) -> ProviderResponse:
            raise ProviderUnavailableError("Anthropic endpoint down", provider="anthropic")

    class WorkingSecondaryAdapter(OpenAIAdapter):
        async def complete(self, request: ProviderRequest, client: httpx.AsyncClient | None = None) -> ProviderResponse:
            return ProviderResponse(
                text="Response from secondary fallback",
                model=request.model,
                provider="openai",
                telemetry=ProviderCacheTelemetry(provider="openai", model=request.model),
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
