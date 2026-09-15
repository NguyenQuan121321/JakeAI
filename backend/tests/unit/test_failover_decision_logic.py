"""Unit tests for FailoverManager decision logic, exponential backoff, and credential isolation (UNIT-057).

Covers:
1. FailoverConfig parameters and defaults.
2. _calculate_backoff: exponential formula, jitter, retry_after honoring, and max_delay cap.
3. execute_with_failover: candidate deduplication in fallback chain.
4. execute_with_failover: max_total_attempts ceiling enforcement.
5. execute_with_failover: credential isolation between primary and fallback candidates.
6. execute_with_failover: non-retryable error aborts provider retries immediately.
7. execute_with_failover: unexpected exception wrapping into NON_RETRYABLE ProviderError.
8. execute_with_failover: complete chain exhaustion error.
9. stream_with_failover: stream delegation and missing stream method handling.
"""

from __future__ import annotations

from typing import TYPE_CHECKING

import pytest

if TYPE_CHECKING:
    import httpx

from app.providers.base import (
    LLMProvider,
    ModelCapabilities,
    ProviderCacheTelemetry,
    ProviderRequest,
    ProviderResponse,
    StreamChunk,
)
from app.providers.errors import (
    ErrorCategory,
    ProviderAuthenticationError,
    ProviderQuotaError,
    ProviderUnavailableError,
)
from app.providers.registry import ProviderRegistry
from app.routing.failover import FailoverConfig, FailoverManager
from app.routing.router import RoutingDecision

# ==============================================================================
# Helper Mock Providers
# ==============================================================================


class StubProvider(LLMProvider):
    """Configurable provider for testing failover decision paths."""

    def __init__(
        self,
        name: str,
        fail_times: int = 0,
        error_to_raise: Exception | None = None,
        return_text: str = "success",
    ) -> None:
        self.provider_name = name
        self.fail_times = fail_times
        self.error_to_raise = error_to_raise
        self.return_text = return_text
        self.attempts = 0
        self.received_api_keys: list[str | None] = []

    def capabilities(self, model: str) -> ModelCapabilities:
        return ModelCapabilities(
            provider=self.provider_name,
            model=model,
            context_window=128_000,
        )

    async def complete(
        self, request: ProviderRequest, client: httpx.AsyncClient | None = None
    ) -> ProviderResponse:
        self.attempts += 1
        self.received_api_keys.append(request.api_key)
        if self.attempts <= self.fail_times:
            if self.error_to_raise is not None:
                raise self.error_to_raise
            raise ProviderUnavailableError(
                message=f"{self.provider_name} unavailable",
                provider=self.provider_name,
            )
        return ProviderResponse(
            text=self.return_text,
            model=request.model,
            provider=self.provider_name,
            telemetry=ProviderCacheTelemetry(
                provider=self.provider_name, model=request.model
            ),
        )

    async def stream(
        self, request: ProviderRequest, client: httpx.AsyncClient | None = None
    ):
        yield StreamChunk(
            delta_text=self.return_text,
            model=request.model,
            provider=self.provider_name,
        )


# ==============================================================================
# 1. FailoverConfig & Backoff Calculation
# ==============================================================================


def test_failover_config_defaults() -> None:
    """FailoverConfig enforces valid default parameters."""
    cfg = FailoverConfig()
    assert cfg.max_retries_per_provider == 1
    assert cfg.max_total_attempts == 3
    assert cfg.base_delay_seconds == 0.2
    assert cfg.backoff_factor == 1.5
    assert cfg.max_delay_seconds == 3.0
    assert ErrorCategory.RETRYABLE in cfg.retryable_categories
    assert ErrorCategory.PROVIDER_UNAVAILABLE in cfg.retryable_categories


def test_calculate_backoff_exponential_growth_and_cap() -> None:
    """_calculate_backoff scales exponentially with attempt and caps at max_delay_seconds."""
    fm = FailoverManager(
        FailoverConfig(
            base_delay_seconds=0.1, backoff_factor=2.0, max_delay_seconds=1.0
        )
    )

    # Attempt 0: delay ~ 0.1 (+ jitter <= 0.01)
    b0 = fm._calculate_backoff(attempt=0)
    assert 0.1 <= b0 <= 0.12

    # Attempt 1: delay ~ 0.2 (+ jitter <= 0.02)
    b1 = fm._calculate_backoff(attempt=1)
    assert 0.2 <= b1 <= 0.23

    # Attempt 10: would be 102.4, must be clamped at max_delay_seconds 1.0
    b10 = fm._calculate_backoff(attempt=10)
    assert b10 == 1.0


def test_calculate_backoff_honors_retry_after() -> None:
    """When retry_after is specified, it takes precedence up to max_delay_seconds."""
    fm = FailoverManager(FailoverConfig(max_delay_seconds=5.0))

    # retry_after 2.5s within cap
    assert fm._calculate_backoff(attempt=0, retry_after=2.5) == 2.5

    # retry_after 60.0s exceeds cap 5.0s -> clamped
    assert fm._calculate_backoff(attempt=0, retry_after=60.0) == 5.0


# ==============================================================================
# 2. execute_with_failover: Candidate Chains & Ceilings
# ==============================================================================


@pytest.fixture
def custom_registry() -> ProviderRegistry:
    return ProviderRegistry()


@pytest.mark.asyncio
async def test_failover_skips_duplicate_candidates(
    custom_registry: ProviderRegistry,
) -> None:
    """Duplicate provider-model pairs in fallback chain are attempted only once."""
    p_fail = StubProvider(name="prov_fail", fail_times=5)
    p_ok = StubProvider(name="prov_ok", fail_times=0, return_text="ok")

    custom_registry.register("prov_fail", p_fail)
    custom_registry.register("prov_ok", p_ok)

    fm = FailoverManager(
        FailoverConfig(max_retries_per_provider=0, max_total_attempts=5)
    )
    fm.registry = custom_registry

    # Decision specifies duplicates: (prov_fail, m1) repeated
    decision = RoutingDecision(
        selected_provider="prov_fail",
        selected_model="model_fail",
        fallback_chain=[
            ("prov_fail", "model_fail"),  # duplicate, must be skipped
            ("prov_ok", "model_ok"),
        ],
    )
    req = ProviderRequest(model="model_fail", prompt="test", tenant_id="t1")

    res = await fm.execute_with_failover(request=req, decision=decision)
    assert res.text == "ok"
    # prov_fail should only have been attempted once
    assert p_fail.attempts == 1
    assert p_ok.attempts == 1


@pytest.mark.asyncio
async def test_failover_max_total_attempts_ceiling(
    custom_registry: ProviderRegistry,
) -> None:
    """When total_attempts reaches max_total_attempts ceiling, aborts chain."""
    p1 = StubProvider(name="prov_1", fail_times=10)
    p2 = StubProvider(name="prov_2", fail_times=10)
    p3 = StubProvider(name="prov_3", fail_times=0, return_text="never reached")

    custom_registry.register("prov_1", p1)
    custom_registry.register("prov_2", p2)
    custom_registry.register("prov_3", p3)

    # Allow 1 retry per provider, total attempts ceiling 2
    fm = FailoverManager(
        FailoverConfig(
            max_retries_per_provider=1,
            max_total_attempts=2,
            base_delay_seconds=0.01,
        )
    )
    fm.registry = custom_registry

    decision = RoutingDecision(
        selected_provider="prov_1",
        selected_model="m1",
        fallback_chain=[("prov_2", "m2"), ("prov_3", "m3")],
    )
    req = ProviderRequest(model="m1", prompt="test", tenant_id="t1")

    with pytest.raises(ProviderUnavailableError):
        await fm.execute_with_failover(request=req, decision=decision)

    # prov_1 took 2 attempts (initial + 1 retry) which reached total ceiling 2
    assert p1.attempts == 2
    # prov_2 and prov_3 never attempted because ceiling was exhausted
    assert p2.attempts == 0
    assert p3.attempts == 0


@pytest.mark.asyncio
async def test_failover_credential_isolation_between_candidates(
    custom_registry: ProviderRegistry,
) -> None:
    """Primary API key is NEVER passed to secondary fallback provider."""
    p_primary = StubProvider(name="openai", fail_times=1)
    p_secondary = StubProvider(
        name="anthropic", fail_times=0, return_text="anthropic_ok"
    )

    custom_registry.register("openai", p_primary)
    custom_registry.register("anthropic", p_secondary)

    fm = FailoverManager(
        FailoverConfig(max_retries_per_provider=0, max_total_attempts=3)
    )
    fm.registry = custom_registry

    decision = RoutingDecision(
        selected_provider="openai",
        selected_model="gpt-4o",
        fallback_chain=[("anthropic", "claude-3-5-sonnet")],
    )
    req = ProviderRequest(
        model="gpt-4o",
        prompt="hello",
        tenant_id="tenant_123",
        api_key="sk-primary-openai-secret-key",
    )

    async def mock_credential_resolver(tenant: str, provider: str) -> str | None:
        if provider == "openai":
            return "sk-primary-openai-secret-key"
        if provider == "anthropic":
            return "sk-ant-resolved-fallback-key"
        return None

    res = await fm.execute_with_failover(
        request=req, decision=decision, credential_resolver=mock_credential_resolver
    )
    assert res.text == "anthropic_ok"
    assert p_primary.received_api_keys == ["sk-primary-openai-secret-key"]
    # Anthropic received its own resolved key, NEVER the primary openai key
    assert p_secondary.received_api_keys == ["sk-ant-resolved-fallback-key"]


@pytest.mark.asyncio
async def test_failover_non_retryable_error_aborts_provider_retries(
    custom_registry: ProviderRegistry,
) -> None:
    """Non-retryable ProviderError (e.g. 401 Auth) immediately fails over without retrying same provider."""
    auth_err = ProviderAuthenticationError(
        message="Invalid API Key (HTTP 401)", provider="primary"
    )
    p_primary = StubProvider(name="primary", fail_times=5, error_to_raise=auth_err)
    p_fallback = StubProvider(name="fallback", fail_times=0, return_text="recovered")

    custom_registry.register("primary", p_primary)
    custom_registry.register("fallback", p_fallback)

    # max_retries_per_provider is 3, but because error is Auth (non-retryable), it should try primary only once
    fm = FailoverManager(
        FailoverConfig(max_retries_per_provider=3, max_total_attempts=5)
    )
    fm.registry = custom_registry

    decision = RoutingDecision(
        selected_provider="primary",
        selected_model="m_prim",
        fallback_chain=[("fallback", "m_fall")],
    )
    req = ProviderRequest(model="m_prim", prompt="test", tenant_id="t1")

    res = await fm.execute_with_failover(request=req, decision=decision)
    assert res.text == "recovered"
    # Primary attempted only once (retries aborted due to Auth error)
    assert p_primary.attempts == 1
    assert p_fallback.attempts == 1


@pytest.mark.asyncio
async def test_failover_unexpected_exception_wrapped_in_provider_error(
    custom_registry: ProviderRegistry,
) -> None:
    """Non-ProviderError exception is wrapped into ProviderError and progresses to fallback."""
    raw_exception = RuntimeError("Low-level OS socket error: api_key=sk-12345secret")
    p_bad = StubProvider(name="bad_prov", fail_times=1, error_to_raise=raw_exception)
    p_good = StubProvider(name="good_prov", fail_times=0, return_text="good_response")

    custom_registry.register("bad_prov", p_bad)
    custom_registry.register("good_prov", p_good)

    fm = FailoverManager(
        FailoverConfig(max_retries_per_provider=1, max_total_attempts=3)
    )
    fm.registry = custom_registry

    decision = RoutingDecision(
        selected_provider="bad_prov",
        selected_model="m1",
        fallback_chain=[("good_prov", "m2")],
    )
    req = ProviderRequest(model="m1", prompt="test", tenant_id="t1")

    res = await fm.execute_with_failover(request=req, decision=decision)
    assert res.text == "good_response"


@pytest.mark.asyncio
async def test_failover_complete_chain_exhausted_raises(
    custom_registry: ProviderRegistry,
) -> None:
    """When all providers fail, the last ProviderError is raised."""
    quota_err = ProviderQuotaError(message="Quota depleted (HTTP 429)", provider="p2")
    p1 = StubProvider(name="p1", fail_times=1)
    p2 = StubProvider(name="p2", fail_times=1, error_to_raise=quota_err)

    custom_registry.register("p1", p1)
    custom_registry.register("p2", p2)

    fm = FailoverManager(
        FailoverConfig(max_retries_per_provider=0, max_total_attempts=2)
    )
    fm.registry = custom_registry

    decision = RoutingDecision(
        selected_provider="p1",
        selected_model="m1",
        fallback_chain=[("p2", "m2")],
    )
    req = ProviderRequest(model="m1", prompt="test", tenant_id="t1")

    with pytest.raises(ProviderQuotaError, match="Quota depleted"):
        await fm.execute_with_failover(request=req, decision=decision)


# ==============================================================================
# 3. stream_with_failover
# ==============================================================================


@pytest.mark.asyncio
async def test_stream_with_failover_yields_chunks(
    custom_registry: ProviderRegistry,
) -> None:
    """stream_with_failover streams chunks from registered provider adapter."""
    p = StubProvider(name="stream_prov", return_text="streamed_chunk")
    custom_registry.register("stream_prov", p)

    fm = FailoverManager()
    fm.registry = custom_registry

    decision = RoutingDecision(selected_provider="stream_prov", selected_model="m1")
    req = ProviderRequest(model="m1", prompt="test")

    chunks = []
    async for chunk in fm.stream_with_failover(request=req, decision=decision):
        chunks.append(chunk)

    assert len(chunks) == 1
    assert chunks[0].delta_text == "streamed_chunk"


@pytest.mark.asyncio
async def test_stream_with_failover_missing_adapter_yields_nothing(
    custom_registry: ProviderRegistry,
) -> None:
    """stream_with_failover on unregistered provider adapter yields nothing without raising."""
    fm = FailoverManager()
    fm.registry = custom_registry  # empty

    decision = RoutingDecision(selected_provider="non_existent", selected_model="m1")
    req = ProviderRequest(model="m1", prompt="test")

    chunks = [c async for c in fm.stream_with_failover(request=req, decision=decision)]
    assert len(chunks) == 0
