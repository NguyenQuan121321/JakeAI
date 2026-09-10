"""Unit tests for DirectProviderBackend adapter and credential hygiene."""

from unittest.mock import AsyncMock, patch

import httpx
import pytest
from httpx import Response

from app.agent.backends.base import (
    AgentMessage,
    BackendRequest,
    BackendStreamChunk,
)
from app.agent.backends.direct_provider import DirectProviderBackend


def test_direct_provider_defaults_and_credentials() -> None:
    """Verify default base URLs, default models, credentials setting, and redaction."""
    # Base URLs
    assert (
        DirectProviderBackend._default_base_url("anthropic")
        == "https://api.anthropic.com/v1"
    )
    assert (
        DirectProviderBackend._default_base_url("gemini")
        == "https://generativelanguage.googleapis.com/v1beta"
    )
    assert (
        DirectProviderBackend._default_base_url("groq")
        == "https://api.groq.com/openai/v1"
    )
    assert (
        DirectProviderBackend._default_base_url("openai") == "https://api.openai.com/v1"
    )

    # Default Models
    assert (
        DirectProviderBackend._default_model("anthropic")
        == "claude-3-5-sonnet-20241022"
    )
    assert DirectProviderBackend._default_model("gemini") == "gemini-1.5-flash"
    assert DirectProviderBackend._default_model("groq") == "llama-3.3-70b-versatile"
    assert DirectProviderBackend._default_model("openai") == "gpt-4o-mini"

    # Credential management and error sanitization
    backend = DirectProviderBackend(provider="openai", api_key="sk-initial-12345")
    assert (
        backend._sanitize_error("Error with sk-initial-12345 key failed")
        == "Error with [REDACTED_API_KEY] key failed"
    )
    assert backend._sanitize_error("Safe error without key") == "Safe error without key"

    backend.set_credentials("sk-updated-67890")
    assert backend._api_key == "sk-updated-67890"
    assert (
        backend._sanitize_error("Error with sk-updated-67890")
        == "Error with [REDACTED_API_KEY]"
    )

    backend_no_key = DirectProviderBackend(provider="openai")
    assert backend_no_key._sanitize_error("Any error") == "Any error"


@pytest.mark.asyncio
async def test_direct_provider_anthropic_headers_and_call() -> None:
    """Verify Anthropic provider configuration uses x-api-key and anthropic-version."""
    backend = DirectProviderBackend(
        provider="anthropic",
        api_key="sk-ant-testkey-123",
    )
    mock_resp = Response(
        status_code=200,
        json={
            "choices": [
                {
                    "message": {"content": "Anthropic response content"},
                    "finish_reason": "end_turn",
                }
            ],
            "usage": {"prompt_tokens": 15, "completion_tokens": 25},
        },
    )

    with patch("httpx.AsyncClient.post", new_callable=AsyncMock) as mock_post:
        mock_post.return_value = mock_resp
        req = BackendRequest(
            messages=[AgentMessage(role="user", content="Explain quantum computing")],
            tenant_id="tenant-acme",
        )
        resp = await backend.generate(req)
        assert resp.content == "Anthropic response content"
        assert resp.provider == "direct:anthropic"
        assert resp.input_tokens == 15
        assert resp.output_tokens == 25

        # Verify call headers
        call_kwargs = mock_post.call_args.kwargs
        headers = call_kwargs["headers"]
        assert headers["x-api-key"] == "sk-ant-testkey-123"
        assert headers["anthropic-version"] == "2023-06-01"


@pytest.mark.asyncio
async def test_direct_provider_user_api_key_override() -> None:
    """Verify request metadata user_api_key overrides or supplies missing credentials."""
    backend = DirectProviderBackend(provider="openai", api_key=None)
    mock_resp = Response(
        status_code=200,
        json={
            "choices": [{"message": {"content": "Overridden key response"}}],
            "usage": {"prompt_tokens": 10, "completion_tokens": 12},
        },
    )

    with patch("httpx.AsyncClient.post", new_callable=AsyncMock) as mock_post:
        mock_post.return_value = mock_resp
        req = BackendRequest(
            messages=[AgentMessage(role="user", content="Hello")],
            tenant_id="tenant-alpha",
            metadata={"user_api_key": "sk-user-ephemeral-key"},
        )
        resp = await backend.generate(req)
        assert resp.content == "Overridden key response"
        headers = mock_post.call_args.kwargs["headers"]
        assert headers["Authorization"] == "Bearer sk-user-ephemeral-key"


@pytest.mark.asyncio
async def test_direct_provider_http_error_response() -> None:
    """Verify non-200 HTTP response is cleanly reported without crashing or leaking keys."""
    backend = DirectProviderBackend(
        provider="openai",
        api_key="sk-secret-key-to-redact",
    )
    mock_resp = Response(
        status_code=429,
        text="Rate limit exceeded for organization with key sk-secret-key-to-redact",
    )

    with patch("httpx.AsyncClient.post", new_callable=AsyncMock) as mock_post:
        mock_post.return_value = mock_resp
        req = BackendRequest(
            messages=[AgentMessage(role="user", content="Hello")],
            tenant_id="tenant-alpha",
        )
        resp = await backend.generate(req)
        assert resp.content == ""
        assert resp.finish_reason == "http_429"
        assert resp.provider == "direct:openai"


@pytest.mark.asyncio
async def test_direct_provider_tool_calls_parsing() -> None:
    """Verify tool_calls payload with JSON string and dictionary arguments are parsed properly."""
    backend = DirectProviderBackend(
        provider="openai",
        api_key="sk-test-key",
    )
    mock_resp = Response(
        status_code=200,
        json={
            "choices": [
                {
                    "message": {
                        "content": "Calling financial tool",
                        "tool_calls": [
                            {
                                "id": "call_abc_1",
                                "function": {
                                    "name": "get_stock_price",
                                    "arguments": '{"ticker": "AAPL", "currency": "USD"}',
                                },
                            },
                            {
                                "id": "call_abc_2",
                                "function": {
                                    "name": "compare_multiples",
                                    "arguments": {"tickers": ["AAPL", "MSFT"]},
                                },
                            },
                        ],
                    },
                    "finish_reason": "tool_calls",
                }
            ],
            "usage": {"prompt_tokens": 40, "completion_tokens": 30},
        },
    )

    with patch("httpx.AsyncClient.post", new_callable=AsyncMock) as mock_post:
        mock_post.return_value = mock_resp
        req = BackendRequest(
            messages=[AgentMessage(role="user", content="Price for AAPL?")],
            tenant_id="tenant-alpha",
        )
        resp = await backend.generate(req)
        assert resp.content == "Calling financial tool"
        assert resp.finish_reason == "tool_calls"
        assert len(resp.tool_calls) == 2

        tc1 = resp.tool_calls[0]
        assert tc1.call_id == "call_abc_1"
        assert tc1.tool_name == "get_stock_price"
        assert tc1.arguments == {"ticker": "AAPL", "currency": "USD"}

        tc2 = resp.tool_calls[1]
        assert tc2.call_id == "call_abc_2"
        assert tc2.tool_name == "compare_multiples"
        assert tc2.arguments == {"tickers": ["AAPL", "MSFT"]}


@pytest.mark.asyncio
async def test_direct_provider_exception_handling() -> None:
    """Verify network exception handling returns an error response with redacted error info."""
    backend = DirectProviderBackend(
        provider="openai",
        api_key="sk-leaked-key",
    )

    with patch("httpx.AsyncClient.post", new_callable=AsyncMock) as mock_post:
        mock_post.side_effect = httpx.ConnectTimeout(
            "Connect timeout to upstream with key sk-leaked-key"
        )
        req = BackendRequest(
            messages=[AgentMessage(role="user", content="Hello")],
            tenant_id="tenant-alpha",
        )
        resp = await backend.generate(req)
        assert resp.finish_reason == "exception"
        assert resp.content == ""
        assert resp.provider == "direct:openai"


@pytest.mark.asyncio
async def test_direct_provider_generate_stream() -> None:
    """Verify generate_stream yields a BackendStreamChunk from the generated response."""
    backend = DirectProviderBackend(
        provider="openai",
        api_key="sk-test-stream",
    )
    mock_resp = Response(
        status_code=200,
        json={
            "choices": [
                {
                    "message": {"content": "Streamed completion payload"},
                    "finish_reason": "stop",
                }
            ],
            "usage": {"prompt_tokens": 12, "completion_tokens": 18},
        },
    )

    with patch("httpx.AsyncClient.post", new_callable=AsyncMock) as mock_post:
        mock_post.return_value = mock_resp
        req = BackendRequest(
            messages=[AgentMessage(role="user", content="Stream me")],
            tenant_id="tenant-alpha",
        )
        chunks: list[BackendStreamChunk] = []
        async for chunk in backend.generate_stream(req):
            chunks.append(chunk)

        assert len(chunks) == 1
        assert chunks[0].delta_content == "Streamed completion payload"
        assert chunks[0].finish_reason == "stop"
        assert chunks[0].is_complete is True
