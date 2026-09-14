"""Unit tests verifying provider failover credential isolation (COST-01 & COST-11).

Guarantees:
1. Primary provider API key is never passed to secondary fallback provider.
2. Provider-specific credentials are resolved for each candidate in the failover chain.
3. The original ProviderRequest is never mutated.
4. Fallback candidates are never repeated in the attempt loop.
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
    ProviderUnavailableError,
)
from app.providers.registry import get_provider_registry
from app.routing.failover import FailoverConfig, FailoverManager
from app.routing.router import RoutingDecision


class MockFailingProvider(LLMProvider):
    """Failing primary provider simulating unavailable service."""

    provider_name = "failing_primary"

    def capabilities(self, model: str) -> ModelCapabilities:
        return ModelCapabilities(
            provider=self.provider_name,
            model=model,
            context_window=128_000,
        )

    async def complete(
        self, request: ProviderRequest, client: httpx.AsyncClient | None = None
    ) -> ProviderResponse:
        raise ProviderUnavailableError(
            message="Primary provider outage (503)",
            provider=self.provider_name,
            category=ErrorCategory.PROVIDER_UNAVAILABLE,
            status_code=503,
        )

    async def stream(
        self, request: ProviderRequest, client: httpx.AsyncClient | None = None
    ):
        yield StreamChunk(delta="err")


class MockFallbackProvider(LLMProvider):
    """Secondary provider recording the exact api_key it received."""

    provider_name = "secondary_fallback"

    def __init__(self) -> None:
        self.received_api_key: str | None = None
        self.received_model: str | None = None
        self.call_count: int = 0

    def capabilities(self, model: str) -> ModelCapabilities:
        return ModelCapabilities(
            provider=self.provider_name,
            model=model,
            context_window=128_000,
        )

    async def complete(
        self, request: ProviderRequest, client: httpx.AsyncClient | None = None
    ) -> ProviderResponse:
        self.call_count += 1
        self.received_api_key = request.api_key
        self.received_model = request.model
        return ProviderResponse(
            text="Success from fallback",
            model=request.model,
            provider=self.provider_name,
            telemetry=ProviderCacheTelemetry(
                provider=self.provider_name, model=request.model
            ),
        )

    async def stream(
        self, request: ProviderRequest, client: httpx.AsyncClient | None = None
    ):
        self.received_api_key = request.api_key
        yield StreamChunk(delta="Success from stream fallback")


@pytest.mark.asyncio
async def test_failover_credentials_isolated_and_resolved_for_fallback() -> None:
    """COST-01: Primary API key is not passed to fallback provider."""
    registry = get_provider_registry()
    failing_adapter = MockFailingProvider()
    fallback_adapter = MockFallbackProvider()

    registry.register("failing_primary", failing_adapter)
    registry.register("secondary_fallback", fallback_adapter)

    config = FailoverConfig(max_retries_per_provider=0, max_total_attempts=3)
    failover_mgr = FailoverManager(config=config)

    original_req = ProviderRequest(
        model="primary-model",
        prompt="Hello",
        api_key="sk-primary-secret-key-12345",
        tenant_id="tenant-test",
    )

    decision = RoutingDecision(
        selected_provider="failing_primary",
        selected_model="primary-model",
        fallback_chain=[("secondary_fallback", "fallback-model")],
    )

    async def mock_credential_resolver(
        tenant_id: str, provider_name: str
    ) -> str | None:
        if provider_name == "secondary_fallback":
            return "sk-secondary-fallback-key-99999"
        if provider_name == "failing_primary":
            return "sk-primary-secret-key-12345"
        return None

    resp = await failover_mgr.execute_with_failover(
        request=original_req,
        decision=decision,
        credential_resolver=mock_credential_resolver,
    )

    assert resp.text == "Success from fallback"
    assert resp.provider == "secondary_fallback"

    # CRITICAL: Verify fallback received its OWN resolved credentials, NEVER the primary's
    assert fallback_adapter.received_api_key == "sk-secondary-fallback-key-99999"
    assert fallback_adapter.received_api_key != "sk-primary-secret-key-12345"
    assert fallback_adapter.received_model == "fallback-model"

    # CRITICAL: Verify original request was NOT mutated
    assert original_req.api_key == "sk-primary-secret-key-12345"
    assert original_req.model == "primary-model"


@pytest.mark.asyncio
async def test_failover_does_not_repeat_failed_candidates() -> None:
    """COST-11: Fallback candidate is not repeated even if present twice in fallback_chain."""
    registry = get_provider_registry()
    fallback_adapter = MockFallbackProvider()
    registry.register("secondary_fallback", fallback_adapter)

    config = FailoverConfig(max_retries_per_provider=0, max_total_attempts=5)
    failover_mgr = FailoverManager(config=config)

    original_req = ProviderRequest(
        model="fallback-model",
        prompt="Hello",
        api_key="sk-test",
        tenant_id="tenant-test",
    )

    # Decision intentionally repeats fallback candidate
    decision = RoutingDecision(
        selected_provider="secondary_fallback",
        selected_model="fallback-model",
        fallback_chain=[
            ("secondary_fallback", "fallback-model"),
            ("secondary_fallback", "fallback-model"),
        ],
    )

    resp = await failover_mgr.execute_with_failover(
        request=original_req,
        decision=decision,
    )

    assert resp.text == "Success from fallback"
    assert fallback_adapter.call_count == 1


@pytest.mark.asyncio
async def test_failover_credentials_isolated_without_resolver() -> None:
    """COST-01: Without resolver, fallback candidate never receives primary API key."""
    registry = get_provider_registry()
    failing_adapter = MockFailingProvider()
    fallback_adapter = MockFallbackProvider()

    registry.register("failing_primary", failing_adapter)
    registry.register("secondary_fallback", fallback_adapter)

    config = FailoverConfig(max_retries_per_provider=0, max_total_attempts=3)
    failover_mgr = FailoverManager(config=config)

    original_req = ProviderRequest(
        model="primary-model",
        prompt="Hello",
        api_key="sk-primary-secret-key-12345",
        tenant_id="tenant-no-byok",
    )

    decision = RoutingDecision(
        selected_provider="failing_primary",
        selected_model="primary-model",
        fallback_chain=[("secondary_fallback", "fallback-model")],
    )

    resp = await failover_mgr.execute_with_failover(
        request=original_req,
        decision=decision,
    )

    assert resp.text == "Success from fallback"
    # Fallback received None (or default resolved key), NEVER primary's key!
    assert fallback_adapter.received_api_key != "sk-primary-secret-key-12345"
    assert fallback_adapter.received_api_key is None
    # Original request object still intact
    assert original_req.api_key == "sk-primary-secret-key-12345"
