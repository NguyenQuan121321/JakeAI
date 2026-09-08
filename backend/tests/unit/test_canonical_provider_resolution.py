"""REPAIR-03 — DUP-02: Canonical Provider Resolution Regression Tests.

Invariant:
  Every model-to-provider resolution on an active request path must originate
  from the single authoritative resolver
  (``ProviderRegistry.resolve_provider_name_for_model``), which is the same
  mechanism consumed by the ModelRouter/failover execution path.

  Consequently, for the same requested model:
  - the AI Gateway's exact-cache identity provider,
  - the AI Gateway's BYOK credential injection,
  - the upstream dispatcher's BYOK credential selection, and
  - the routing/failover execution provider
  must all resolve identically. No active request path may carry an
  independent substring-based provider-resolution rule.
"""

from typing import Any
from unittest.mock import AsyncMock, patch

import pytest

from app.core.llm_provider import call_upstream_llm_detailed
from app.providers.base import ChatMessage, ProviderCacheTelemetry, ProviderResponse
from app.providers.registry import get_provider_registry
from app.services.ai_gateway import (
    GatewayChatRequest,
    GatewayInferenceProxy,
    QuotaManager,
)

# ---------------------------------------------------------------------------
# Shared fixtures and helpers
# ---------------------------------------------------------------------------

# Authoritative resolution matrix: every ModelCapabilityCatalog model plus the
# registry default. Previously the AI Gateway resolved groq/deepseek/o1/o3
# models and unknown models to "openrouter" via an independent ternary
# heuristic, and the upstream dispatcher resolved slash-form models
# (e.g. "meta-llama/llama-3.1-70b") to the wrong BYOK credential provider.
PROVIDER_RESOLUTION_MATRIX: list[tuple[str, str]] = [
    # OpenAI
    ("gpt-4o", "openai"),
    ("gpt-4o-mini", "openai"),
    ("o1", "openai"),
    ("o3-mini", "openai"),
    # Anthropic
    ("claude-3-5-sonnet", "anthropic"),
    ("claude-3-haiku", "anthropic"),
    # Gemini
    ("gemini-1.5-flash", "gemini"),
    ("gemini-1.5-pro", "gemini"),
    # Groq
    ("llama-3.3-70b-versatile", "groq"),
    ("llama-3.1-8b-instant", "groq"),
    # DeepSeek
    ("deepseek-chat", "deepseek"),
    ("deepseek-reasoner", "deepseek"),
    # OpenRouter
    ("openrouter/auto", "openrouter"),
    ("meta-llama/llama-3.1-70b", "openrouter"),
]

TENANT = "tenant-prov-resolution"


class ProviderCapturingCache:
    """Semantic-cache stand-in that records the provider used in cache identity."""

    def __init__(self) -> None:
        self.get_calls: list[dict[str, Any]] = []
        self.set_calls: list[dict[str, Any]] = []

    async def get(self, prompt: str, **kwargs: Any) -> None:
        self.get_calls.append({"prompt": prompt, **kwargs})
        return None

    async def set(self, prompt: str, **kwargs: Any) -> None:
        self.set_calls.append({"prompt": prompt, **kwargs})


class RecordingByokManager:
    """BYOK manager stand-in recording provider lookups (resolves no keys)."""

    def __init__(self) -> None:
        self.lookups: list[tuple[str, str]] = []

    async def get_decrypted_key(self, tenant_id: str, provider: str) -> None:
        self.lookups.append((tenant_id, provider))
        return None


class KeyedByokManager:
    """BYOK manager stand-in returning a provider-tagged fake decrypted key."""

    def __init__(self) -> None:
        self.lookups: list[tuple[str, str]] = []

    async def get_decrypted_key(self, tenant_id: str, provider: str) -> str:
        self.lookups.append((tenant_id, provider))
        return f"byok-{provider}-key-123"


class CapturingFailoverManager:
    """Failover manager stand-in capturing the executed ProviderRequest."""

    def __init__(self) -> None:
        self.requests: list[tuple[Any, Any]] = []

    async def execute_with_failover(
        self, request: Any, decision: Any, client: Any = None
    ) -> ProviderResponse:
        self.requests.append((request, decision))
        return ProviderResponse(
            text="canonical resolution response",
            model=request.model,
            provider=decision.selected_provider,
            telemetry=ProviderCacheTelemetry(
                provider=decision.selected_provider,
                model=request.model,
            ),
        )


def _make_proxy(cache_stub: ProviderCapturingCache) -> GatewayInferenceProxy:
    proxy = GatewayInferenceProxy(quota_manager=QuotaManager())
    proxy.cache_mgr = cache_stub  # type: ignore[assignment]
    return proxy


def _make_request(model: str, stream: bool = False) -> GatewayChatRequest:
    return GatewayChatRequest(
        model=model,
        messages=[ChatMessage(role="user", content="Analyze Q3 margin trends.")],
        stream=stream,
    )


# ---------------------------------------------------------------------------
# 1. Authoritative registry resolution (reference mechanism)
# ---------------------------------------------------------------------------


class TestAuthoritativeRegistryResolution:
    """Pin the authoritative model-to-provider mapping for all 6 providers."""

    @pytest.mark.parametrize(
        ("model", "expected_provider"),
        PROVIDER_RESOLUTION_MATRIX,
    )
    def test_registry_resolves_required_providers(
        self, model: str, expected_provider: str
    ) -> None:
        assert (
            get_provider_registry().resolve_provider_name_for_model(model)
            == expected_provider
        )

    def test_registry_default_fallback_is_gemini(self) -> None:
        """Unknown models default to gemini, matching routing behavior."""
        assert (
            get_provider_registry().resolve_provider_name_for_model(
                "totally-unknown-model"
            )
            == "gemini"
        )


# ---------------------------------------------------------------------------
# 2. Gateway non-streaming path resolves through the authoritative resolver
# ---------------------------------------------------------------------------


class TestGatewayChatCompletionsCanonicalResolution:
    """Gateway cache identity and BYOK injection must use the canonical provider."""

    @pytest.mark.parametrize(
        ("model", "expected_provider"),
        PROVIDER_RESOLUTION_MATRIX,
    )
    @pytest.mark.asyncio
    async def test_cache_identity_uses_authoritative_provider(
        self, model: str, expected_provider: str
    ) -> None:
        cache_stub = ProviderCapturingCache()
        proxy = _make_proxy(cache_stub)
        byok_stub = RecordingByokManager()

        with (
            patch("app.services.ai_gateway.get_byok_manager", return_value=byok_stub),
            patch(
                "app.services.ai_gateway.call_upstream_llm_detailed",
                new=AsyncMock(return_value=None),
            ),
            patch(
                "app.services.ai_gateway.call_upstream_llm",
                new=AsyncMock(return_value=None),
            ),
        ):
            response = await proxy.chat_completions(
                tenant_id=TENANT, request=_make_request(model)
            )

        assert response.cached is False
        assert cache_stub.get_calls, "Exact cache lookup must be attempted"
        assert cache_stub.set_calls, "Exact cache population must occur"
        assert cache_stub.get_calls[-1]["provider"] == expected_provider
        assert cache_stub.set_calls[-1]["provider"] == expected_provider

    @pytest.mark.parametrize(
        ("model", "expected_provider"),
        PROVIDER_RESOLUTION_MATRIX,
    )
    @pytest.mark.asyncio
    async def test_byok_injection_targets_authoritative_provider(
        self, model: str, expected_provider: str
    ) -> None:
        cache_stub = ProviderCapturingCache()
        proxy = _make_proxy(cache_stub)
        byok_stub = RecordingByokManager()

        with (
            patch("app.services.ai_gateway.get_byok_manager", return_value=byok_stub),
            patch(
                "app.services.ai_gateway.call_upstream_llm_detailed",
                new=AsyncMock(return_value=None),
            ),
            patch(
                "app.services.ai_gateway.call_upstream_llm",
                new=AsyncMock(return_value=None),
            ),
        ):
            await proxy.chat_completions(tenant_id=TENANT, request=_make_request(model))

        assert byok_stub.lookups[-1] == (TENANT, expected_provider)

    @pytest.mark.parametrize(
        ("model", "expected_provider"),
        PROVIDER_RESOLUTION_MATRIX,
    )
    @pytest.mark.asyncio
    async def test_gateway_resolution_matches_authoritative_resolver(
        self, model: str, expected_provider: str
    ) -> None:
        """Gateway-resolved provider must equal the authoritative resolver output."""
        cache_stub = ProviderCapturingCache()
        proxy = _make_proxy(cache_stub)

        with (
            patch(
                "app.services.ai_gateway.get_byok_manager",
                return_value=RecordingByokManager(),
            ),
            patch(
                "app.services.ai_gateway.call_upstream_llm_detailed",
                new=AsyncMock(return_value=None),
            ),
            patch(
                "app.services.ai_gateway.call_upstream_llm",
                new=AsyncMock(return_value=None),
            ),
        ):
            await proxy.chat_completions(tenant_id=TENANT, request=_make_request(model))

        authoritative = get_provider_registry().resolve_provider_name_for_model(model)
        assert authoritative == expected_provider
        assert cache_stub.get_calls[-1]["provider"] == authoritative


# ---------------------------------------------------------------------------
# 3. Gateway streaming path resolves through the authoritative resolver
# ---------------------------------------------------------------------------


class TestGatewayStreamCanonicalResolution:
    """Streaming cache identity must use the canonical provider."""

    @pytest.mark.parametrize(
        ("model", "expected_provider"),
        PROVIDER_RESOLUTION_MATRIX,
    )
    @pytest.mark.asyncio
    async def test_stream_cache_identity_uses_authoritative_provider(
        self, model: str, expected_provider: str
    ) -> None:
        cache_stub = ProviderCapturingCache()
        proxy = _make_proxy(cache_stub)

        with patch(
            "app.core.llm_provider.call_upstream_llm",
            new=AsyncMock(return_value=None),
        ):
            chunks = [
                chunk
                async for chunk in proxy.chat_completions_stream(
                    tenant_id=TENANT, request=_make_request(model, stream=True)
                )
            ]

        assert chunks[-1] == "data: [DONE]\n\n"
        assert cache_stub.get_calls[-1]["provider"] == expected_provider
        assert cache_stub.set_calls[-1]["provider"] == expected_provider

    @pytest.mark.parametrize(
        ("model", "expected_provider"),
        PROVIDER_RESOLUTION_MATRIX,
    )
    @pytest.mark.asyncio
    async def test_stream_resolution_matches_authoritative_resolver(
        self, model: str, expected_provider: str
    ) -> None:
        """Stream-resolved provider must equal the authoritative resolver output."""
        cache_stub = ProviderCapturingCache()
        proxy = _make_proxy(cache_stub)

        with patch(
            "app.core.llm_provider.call_upstream_llm",
            new=AsyncMock(return_value=None),
        ):
            async for _ in proxy.chat_completions_stream(
                tenant_id=TENANT, request=_make_request(model, stream=True)
            ):
                pass

        authoritative = get_provider_registry().resolve_provider_name_for_model(model)
        assert authoritative == expected_provider
        assert cache_stub.get_calls[-1]["provider"] == authoritative


# ---------------------------------------------------------------------------
# 4. Upstream dispatcher BYOK credential selection follows the router decision
# ---------------------------------------------------------------------------


class TestDispatcherByokSelection:
    """call_upstream_llm_detailed must select BYOK credentials per the
    authoritative routing decision, not an independent substring heuristic."""

    @pytest.mark.parametrize(
        ("model", "expected_provider"),
        PROVIDER_RESOLUTION_MATRIX,
    )
    @pytest.mark.asyncio
    async def test_byok_key_matches_routing_decision_provider(
        self, model: str, expected_provider: str
    ) -> None:
        byok_stub = KeyedByokManager()
        failover_stub = CapturingFailoverManager()

        with (
            patch("app.core.llm_provider.get_byok_manager", return_value=byok_stub),
            patch(
                "app.core.llm_provider.get_failover_manager",
                return_value=failover_stub,
            ),
        ):
            response = await call_upstream_llm_detailed(
                prompt="Analyze Q3 margin trends.",
                tenant_id=TENANT,
                model=model,
            )

        assert response is not None
        assert failover_stub.requests, "Failover manager must be invoked"
        request, decision = failover_stub.requests[-1]
        assert decision.selected_provider == expected_provider
        # The credential handed to the executing adapter must belong to the
        # provider the router selected.
        assert request.api_key == f"byok-{expected_provider}-key-123"
        assert byok_stub.lookups[-1] == (TENANT, expected_provider)
        assert response.provider == expected_provider
