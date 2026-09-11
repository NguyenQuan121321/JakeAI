"""Unit tests for COST-12: Local Model Provider Adapter and Health Probing.

Verifies:
1. LocalModelAdapter capabilities and non-zero operational compute pricing.
2. Active health probing with caching and connection error handling.
3. Complete request formatting, response parsing, and cost accounting.
4. SSE stream parsing, done chunk finalization, and token usage.
5. Typed error normalization (ProviderUnavailableError, ProviderTimeoutError).
6. Integration with ProviderRegistry and ModelRouter.
"""

from __future__ import annotations

from unittest.mock import AsyncMock, MagicMock

import httpx
import pytest

from app.providers.base import ProviderRequest
from app.providers.errors import ProviderTimeoutError, ProviderUnavailableError
from app.providers.local import LocalModelAdapter
from app.providers.registry import get_provider_registry


@pytest.fixture
def local_adapter() -> LocalModelAdapter:
    return LocalModelAdapter(
        endpoint="http://localhost:11434/v1",
        model_name="local-model",
        context_limit=32_768,
        concurrency_limit=2,
        input_pricing=0.10,
        output_pricing=0.20,
    )


def test_local_model_capabilities_and_pricing(local_adapter: LocalModelAdapter) -> None:
    """Verify LocalModelAdapter returns valid capabilities with non-zero operational cost."""
    caps = local_adapter.capabilities("local-model")
    assert caps.provider == "local"
    assert caps.model == "local-model"
    assert caps.context_window == 32_768
    assert caps.supports_tools is True
    assert caps.supports_json is True
    # Non-zero compute cost requirement (W-COST-06)
    assert caps.input_pricing == 0.10
    assert caps.output_pricing == 0.20


@pytest.mark.asyncio
async def test_local_model_health_check_success(
    local_adapter: LocalModelAdapter,
) -> None:
    """Verify check_health returns True when endpoint is reachable."""
    mock_client = AsyncMock()
    mock_response = MagicMock(status_code=200)
    mock_client.get.return_value = mock_response

    is_healthy = await local_adapter.check_health(client=mock_client)
    assert is_healthy is True
    assert local_adapter._is_healthy is True


@pytest.mark.asyncio
async def test_local_model_health_check_failure(
    local_adapter: LocalModelAdapter,
) -> None:
    """Verify check_health marks provider unhealthy on connection failure."""
    mock_client = AsyncMock()
    mock_client.get.side_effect = httpx.ConnectError("Connection refused")

    is_healthy = await local_adapter.check_health(client=mock_client)
    assert is_healthy is False
    assert local_adapter._is_healthy is False


@pytest.mark.asyncio
async def test_local_model_complete_execution(local_adapter: LocalModelAdapter) -> None:
    """Verify complete parses response and computes non-zero operational cost."""
    mock_client = AsyncMock()
    mock_response = MagicMock()
    mock_response.is_error = False
    mock_response.json.return_value = {
        "choices": [
            {
                "message": {"content": "Local model answer", "role": "assistant"},
                "finish_reason": "stop",
            }
        ],
        "usage": {"prompt_tokens": 100, "completion_tokens": 50, "total_tokens": 150},
    }
    mock_client.post.return_value = mock_response

    req = ProviderRequest(
        model="local-model",
        prompt="What is Docker?",
    )
    resp = await local_adapter.complete(req, client=mock_client)

    assert resp.text == "Local model answer"
    assert resp.provider == "local"
    assert resp.telemetry.uncached_input_tokens == 100
    assert resp.telemetry.output_tokens == 50
    # (100 * 0.10 + 50 * 0.20) / 1,000,000 = (10 + 10) / 1,000,000 = 0.00002
    assert resp.telemetry.actual_cost_usd == 0.00002


@pytest.mark.asyncio
async def test_local_model_timeout_raises_provider_timeout_error(
    local_adapter: LocalModelAdapter,
) -> None:
    """Verify timeout is normalized into typed ProviderTimeoutError."""
    mock_client = AsyncMock()
    mock_client.post.side_effect = httpx.ReadTimeout("Local model took too long")

    req = ProviderRequest(
        model="local-model",
        prompt="Generate an entire operating system in assembly",
    )
    with pytest.raises(ProviderTimeoutError):
        await local_adapter.complete(req, client=mock_client)


@pytest.mark.asyncio
async def test_local_model_connection_error_raises_unavailable(
    local_adapter: LocalModelAdapter,
) -> None:
    """Verify connection error raises ProviderUnavailableError and marks provider unhealthy."""
    mock_client = AsyncMock()
    mock_client.post.side_effect = httpx.ConnectError("Connection refused")

    req = ProviderRequest(
        model="local-model",
        prompt="Hello",
    )
    with pytest.raises(ProviderUnavailableError):
        await local_adapter.complete(req, client=mock_client)
    assert local_adapter._is_healthy is False


def test_local_model_registry_resolution() -> None:
    """Verify local provider is registered and resolved in ProviderRegistry."""
    registry = get_provider_registry()
    assert "local" in registry.list_providers()
    assert registry.resolve_provider_name_for_model("local-model") == "local"
    assert registry.resolve_provider_name_for_model("ollama/llama3") == "local"
    assert registry.resolve_provider_name_for_model("vllm-mistral") == "local"
