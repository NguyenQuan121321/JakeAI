"""R-FUNC-04 — Provider Behavior verification suite.

Verifies the provider abstraction at the provider-contract boundary (real httpx
client against controlled HTTP doubles):

1. Provider/model resolution reaches the wire (selected provider + model invoked).
2. Request transformation (messages, structured output, tools, temperature).
3. Credential selection: tenant BYOK / platform key, and zero cross-provider
   credential reuse during failover (verified at the HTTP wire level).
4. Success response and provider-reported usage reconciliation to accounting.
5. Real incremental streaming through the dispatcher.
6. Error normalization and classification: 401/403/429/500/502/503, timeout,
   malformed response, connection failure.
7. Failover: provider A failure -> provider B selection under production
   defaults; provider B receives provider B credentials.
"""

from __future__ import annotations

import json
from typing import Any
from unittest.mock import patch

import httpx
import pytest

from app.core.config import Settings
from app.core.llm_provider import call_upstream_llm_detailed, call_upstream_llm_stream
from app.providers.anthropic import AnthropicAdapter
from app.providers.base import ProviderRequest
from app.providers.deepseek import DeepSeekAdapter
from app.providers.errors import (
    ProviderError,
    ProviderRateLimitError,
    ProviderTimeoutError,
    ProviderUnavailableError,
)
from app.providers.gemini import GeminiAdapter
from app.providers.groq import GroqAdapter
from app.providers.openai import OpenAIAdapter
from app.routing.failover import FailoverConfig, FailoverManager
from app.routing.router import RoutingDecision

# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

OPENAI_OK_BODY: dict[str, Any] = {
    "choices": [
        {"message": {"role": "assistant", "content": "ok"}, "finish_reason": "stop"}
    ],
    "usage": {"prompt_tokens": 5, "completion_tokens": 2},
}


def make_openai_sse(*deltas: str) -> str:
    events = [
        f"data: {json.dumps({'choices': [{'delta': {'content': d}}]})}\n\n"
        for d in deltas
    ]
    events.append("data: [DONE]\n\n")
    return "".join(events)


GEMINI_OK_BODY: dict[str, Any] = {
    "candidates": [
        {"content": {"parts": [{"text": "gemini ok"}]}, "finishReason": "STOP"}
    ],
    "usageMetadata": {"promptTokenCount": 10, "candidatesTokenCount": 3},
}


class RecordingTransport(httpx.MockTransport):
    """Controlled provider-contract double: records every upstream request and
    dispatches responses via the caller-assigned ``route`` function."""

    def __init__(self) -> None:
        self.requests: list[httpx.Request] = []
        self.route: Any = lambda request: httpx.Response(404)
        super().__init__(self._handler)

    def _handler(self, request: httpx.Request) -> httpx.Response:
        self.requests.append(request)
        return self.route(request)


def raise_in_handler(exc: Exception):
    def handler(request: httpx.Request) -> httpx.Response:
        raise exc

    return handler


# ---------------------------------------------------------------------------
# 1. Selected provider/model is actually invoked (wire-level proof)
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_dispatch_invokes_selected_provider_and_model_on_the_wire() -> None:
    """Routing decision (anthropic, claude-3-5-sonnet) must produce a real HTTP
    request to api.anthropic.com for exactly that model and credential."""
    transport = RecordingTransport()

    def route(request: httpx.Request) -> httpx.Response:
        assert request.url.host == "api.anthropic.com"
        assert request.url.path == "/v1/messages"
        assert request.headers["x-api-key"] == "sk-ant-platform-test"
        body = json.loads(request.content)
        assert body["model"] == "claude-3-5-sonnet"
        return httpx.Response(
            200,
            json={
                "content": [{"type": "text", "text": "anthropic wire"}],
                "usage": {"input_tokens": 12, "output_tokens": 4},
                "stop_reason": "end_turn",
            },
        )

    transport.route = route
    real_client = httpx.AsyncClient

    with (
        patch(
            "app.core.llm_provider.httpx.AsyncClient",
            lambda *a, **kw: real_client(transport=transport),
        ),
        patch("app.core.llm_provider.get_settings") as mock_settings,
    ):
        settings_obj = Settings()
        settings_obj.ANTHROPIC_API_KEY = "sk-ant-platform-test"
        mock_settings.return_value = settings_obj

        # Coding workload classification preserves the premium requested model
        # (cost-aware down-tiering only applies to simple_chat workloads).
        res = await call_upstream_llm_detailed(
            prompt="def solve(values):\n    return sorted(values)",
            model="claude-3-5-sonnet",
        )

    assert res is not None
    assert res.provider == "anthropic"
    assert res.text == "anthropic wire"
    assert res.model == "claude-3-5-sonnet"


@pytest.mark.asyncio
async def test_selected_model_reaches_provider_payload() -> None:
    """The adapter payload must carry the routed model, not a silent substitute."""
    captured: dict[str, Any] = {}

    def handler(request: httpx.Request) -> httpx.Response:
        captured["url"] = str(request.url)
        captured["body"] = json.loads(request.content)
        captured["authorization"] = request.headers.get("authorization")
        return httpx.Response(200, json=OPENAI_OK_BODY)

    adapter = OpenAIAdapter()
    req = ProviderRequest(
        model="gpt-4o",
        prompt="Hi",
        api_key="sk-openai-test",
        temperature=0.2,
        max_tokens=256,
    )
    client = httpx.AsyncClient(transport=httpx.MockTransport(handler))
    res = await adapter.complete(req, client=client)

    assert captured["url"].startswith("https://api.openai.com/v1/chat/completions")
    assert captured["body"]["model"] == "gpt-4o"
    assert captured["body"]["temperature"] == 0.2
    assert captured["body"]["max_tokens"] == 256
    assert captured["authorization"] == "Bearer sk-openai-test"
    assert res.model == "gpt-4o"
    await client.aclose()


@pytest.mark.asyncio
async def test_structured_output_forwarded_to_provider() -> None:
    """response_format (structured output / JSON mode) must be forwarded intact."""
    captured: dict[str, Any] = {}

    def handler(request: httpx.Request) -> httpx.Response:
        captured["body"] = json.loads(request.content)
        return httpx.Response(200, json=OPENAI_OK_BODY)

    adapter = OpenAIAdapter()
    response_format = {
        "type": "json_schema",
        "json_schema": {
            "name": "invoice",
            "schema": {"type": "object", "properties": {"total": {"type": "number"}}},
        },
    }
    req = ProviderRequest(
        model="gpt-4o",
        prompt="Extract invoice total",
        api_key="sk-openai-test",
        response_format=response_format,
    )
    client = httpx.AsyncClient(transport=httpx.MockTransport(handler))
    res = await adapter.complete(req, client=client)

    assert captured["body"]["response_format"] == response_format
    assert res.text == "ok"
    await client.aclose()


# ---------------------------------------------------------------------------
# 2. Provider-reported usage reconciles to accounting
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_provider_reported_usage_reconciles_to_accounting() -> None:
    """Usage reported by the provider must flow unmodified into telemetry
    (cached + uncached == provider prompt tokens; output == provider completion
    tokens) and cost must be derived from those reported tokens."""
    provider_usage = {
        "prompt_tokens": 100,
        "completion_tokens": 20,
        "prompt_tokens_details": {"cached_tokens": 50},
    }
    body = {
        "choices": [{"message": {"content": "usage ok"}, "finish_reason": "stop"}],
        "usage": provider_usage,
    }

    adapter = OpenAIAdapter()
    req = ProviderRequest(model="gpt-4o", prompt="Hi", api_key="sk-openai-test")
    client = httpx.AsyncClient(
        transport=httpx.MockTransport(lambda r: httpx.Response(200, json=body))
    )
    res = await adapter.complete(req, client=client)
    await client.aclose()

    assert res.telemetry.cached_tokens == 50
    assert res.telemetry.uncached_input_tokens == 50
    assert res.telemetry.output_tokens == 20
    # Reconciliation invariant: accounting input equals provider-reported input.
    assert res.telemetry.uncached_input_tokens + res.telemetry.cached_tokens == 100
    assert res.telemetry.output_tokens == provider_usage["completion_tokens"]
    assert res.raw_usage == provider_usage
    # gpt-4o: 50 uncached @ $2.50/M + 50 cached @ $1.25/M + 20 output @ $10/M
    assert res.telemetry.actual_cost_usd == pytest.approx(0.0003875, abs=1e-6)
    assert res.telemetry.estimated_baseline_cost_usd == pytest.approx(
        100 * 2.50 / 1e6 + 20 * 10.00 / 1e6, abs=1e-6
    )


# ---------------------------------------------------------------------------
# 3. Real incremental streaming through the dispatcher
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_streaming_dispatcher_yields_incremental_deltas() -> None:
    """call_upstream_llm_stream must yield provider deltas incrementally as
    StreamChunk.delta_text (never collapse to nothing or one blob)."""
    sse = make_openai_sse("Chunk 1 ", "Chunk 2")
    real_client = httpx.AsyncClient

    with (
        patch(
            "app.core.llm_provider.httpx.AsyncClient",
            lambda *a, **kw: real_client(
                transport=httpx.MockTransport(lambda r: httpx.Response(200, text=sse))
            ),
        ),
        patch("app.core.llm_provider.get_settings") as mock_settings,
    ):
        settings_obj = Settings()
        settings_obj.OPENAI_API_KEY = "sk-stream-test"
        mock_settings.return_value = settings_obj

        deltas = [
            delta
            async for delta in call_upstream_llm_stream(prompt="Hi", model="gpt-4o")
        ]

    assert deltas == ["Chunk 1 ", "Chunk 2"]


# ---------------------------------------------------------------------------
# 4. Network-level failure classification (timeout, connect, malformed)
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_cloud_adapter_timeout_normalized_to_typed_error() -> None:
    """httpx read timeout must surface as retryable ProviderTimeoutError."""
    adapter = OpenAIAdapter()
    req = ProviderRequest(model="gpt-4o", prompt="Hi", api_key="sk-openai-test")
    client = httpx.AsyncClient(
        transport=httpx.MockTransport(
            raise_in_handler(httpx.ReadTimeout("read timed out", request=None))  # type: ignore[arg-type]
        )
    )
    with pytest.raises(ProviderTimeoutError) as exc_info:
        await adapter.complete(req, client=client)
    assert exc_info.value.is_retryable is True
    assert exc_info.value.category.value == "retryable"
    await client.aclose()


@pytest.mark.asyncio
async def test_cloud_adapter_connect_error_normalized_to_unavailable() -> None:
    """Connection failure must surface as retryable ProviderUnavailableError."""
    adapter = AnthropicAdapter()
    req = ProviderRequest(model="claude-3-5-sonnet", prompt="Hi", api_key="sk-ant-test")
    client = httpx.AsyncClient(
        transport=httpx.MockTransport(
            raise_in_handler(httpx.ConnectError("connection refused", request=None))  # type: ignore[arg-type]
        )
    )
    with pytest.raises(ProviderUnavailableError) as exc_info:
        await adapter.complete(req, client=client)
    assert exc_info.value.is_retryable is True
    assert exc_info.value.category.value == "provider_unavailable"
    await client.aclose()


@pytest.mark.asyncio
async def test_cloud_adapter_malformed_response_normalized() -> None:
    """HTTP 200 with unparseable body must surface as a typed ProviderError,
    not a raw JSONDecodeError."""
    adapter = GroqAdapter()
    req = ProviderRequest(
        model="llama-3.3-70b-versatile", prompt="Hi", api_key="gsk-test"
    )
    client = httpx.AsyncClient(
        transport=httpx.MockTransport(
            lambda r: httpx.Response(200, text="<html>not json {{{</html>")
        )
    )
    with pytest.raises(ProviderError) as exc_info:
        await adapter.complete(req, client=client)
    assert not isinstance(exc_info.value, ProviderTimeoutError)
    # Provider-side protocol violation is a provider availability problem.
    assert exc_info.value.category.value == "provider_unavailable"
    await client.aclose()


@pytest.mark.asyncio
async def test_cloud_adapter_stream_timeout_normalized() -> None:
    """Mid-stream read timeout must surface as ProviderTimeoutError."""
    adapter = DeepSeekAdapter()
    req = ProviderRequest(model="deepseek-chat", prompt="Hi", api_key="sk-ds-test")
    client = httpx.AsyncClient(
        transport=httpx.MockTransport(
            raise_in_handler(httpx.ReadTimeout("stream timed out", request=None))  # type: ignore[arg-type]
        )
    )
    with pytest.raises(ProviderTimeoutError):
        async for _ in adapter.stream(req, client=client):
            pass
    await client.aclose()


@pytest.mark.asyncio
async def test_cloud_adapter_stream_connect_error_normalized() -> None:
    """Stream connect failure must surface as ProviderUnavailableError."""
    adapter = GeminiAdapter()
    req = ProviderRequest(model="gemini-1.5-flash", prompt="Hi", api_key="g-key")
    client = httpx.AsyncClient(
        transport=httpx.MockTransport(
            raise_in_handler(httpx.ConnectError("unreachable", request=None))  # type: ignore[arg-type]
        )
    )
    with pytest.raises(ProviderUnavailableError):
        async for _ in adapter.stream(req, client=client):
            pass
    await client.aclose()


@pytest.mark.asyncio
@pytest.mark.parametrize(
    ("status", "body", "expected_category", "retryable"),
    [
        (401, {"error": {"message": "invalid api key"}}, "authentication", False),
        (403, {"error": {"message": "permission denied"}}, "authentication", False),
        (429, {"error": {"message": "rate limit reached"}}, "retryable", True),
        (500, {"error": {"message": "internal server error"}}, "non_retryable", False),
        (502, {"error": {"message": "bad gateway"}}, "provider_unavailable", True),
        (
            503,
            {"error": {"message": "service unavailable"}},
            "provider_unavailable",
            True,
        ),
    ],
)
async def test_error_status_matrix_classification(
    status: int, body: dict, expected_category: str, retryable: bool
) -> None:
    """Every provider HTTP failure status must be normalized into the correct
    typed category with the right retryability."""
    adapter = OpenAIAdapter()
    req = ProviderRequest(model="gpt-4o", prompt="Hi", api_key="sk-openai-test")
    client = httpx.AsyncClient(
        transport=httpx.MockTransport(lambda r: httpx.Response(status, json=body))
    )
    with pytest.raises(ProviderError) as exc_info:
        await adapter.complete(req, client=client)
    assert exc_info.value.status_code == status
    assert exc_info.value.category.value == expected_category
    assert exc_info.value.is_retryable is retryable
    await client.aclose()


@pytest.mark.asyncio
async def test_429_with_quota_message_maps_to_quota_error() -> None:
    adapter = OpenAIAdapter()
    req = ProviderRequest(model="gpt-4o", prompt="Hi", api_key="sk-openai-test")
    client = httpx.AsyncClient(
        transport=httpx.MockTransport(
            lambda r: httpx.Response(
                429, json={"error": {"message": "You exceeded your current quota"}}
            )
        )
    )
    with pytest.raises(ProviderError) as exc_info:
        await adapter.complete(req, client=client)
    assert exc_info.value.category.value == "quota"
    assert exc_info.value.is_retryable is False
    await client.aclose()


@pytest.mark.asyncio
async def test_429_respects_retry_after_header() -> None:
    adapter = GroqAdapter()
    req = ProviderRequest(
        model="llama-3.3-70b-versatile", prompt="Hi", api_key="gsk-test"
    )
    client = httpx.AsyncClient(
        transport=httpx.MockTransport(
            lambda r: httpx.Response(
                429,
                json={"error": {"message": "rate limit"}},
                headers={"retry-after": "5"},
            )
        )
    )
    with pytest.raises(ProviderRateLimitError) as exc_info:
        await adapter.complete(req, client=client)
    assert exc_info.value.retry_after_seconds == 5.0
    await client.aclose()


# ---------------------------------------------------------------------------
# 5. Failover: provider A failure -> provider B selection + credentials
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_failover_reaches_provider_b_under_default_config() -> None:
    """With production default config, a primary persistently failing with a
    retryable error (503) must still hand off to the fallback provider instead
    of exhausting the total attempt ceiling on the dead primary."""
    transport = RecordingTransport()
    openai_attempts = 0

    def route(request: httpx.Request) -> httpx.Response:
        nonlocal openai_attempts
        if request.url.host == "api.openai.com":
            openai_attempts += 1
            return httpx.Response(503, json={"error": {"message": "overloaded"}})
        if request.url.host == "generativelanguage.googleapis.com":
            return httpx.Response(200, json=GEMINI_OK_BODY)
        return httpx.Response(404)

    transport.route = route

    async def resolver(tenant_id: str, provider: str) -> str | None:
        return {
            "openai": "sk-openai-test",
            "gemini": "gemini-secondary-key",
        }.get(provider)

    failover_mgr = FailoverManager(config=FailoverConfig(base_delay_seconds=0.01))
    req = ProviderRequest(
        model="gpt-4o-mini", prompt="Hi", api_key="sk-openai-test", tenant_id="t1"
    )
    decision = RoutingDecision(
        selected_provider="openai",
        selected_model="gpt-4o-mini",
        fallback_chain=[("gemini", "gemini-1.5-flash")],
    )

    res = await failover_mgr.execute_with_failover(
        req,
        decision,
        client=httpx.AsyncClient(transport=transport),
        credential_resolver=resolver,
    )

    assert res.provider == "gemini"
    assert openai_attempts >= 1
    assert any(
        r.url.host == "generativelanguage.googleapis.com" for r in transport.requests
    )


@pytest.mark.asyncio
async def test_failover_wire_credentials_are_provider_specific() -> None:
    """After provider A fails, provider B's real HTTP request must carry
    provider B's credential (resolved for B) and never provider A's secret."""
    transport = RecordingTransport()

    def route(request: httpx.Request) -> httpx.Response:
        if request.url.host == "api.openai.com":
            return httpx.Response(401, json={"error": {"message": "bad key"}})
        if request.url.host == "generativelanguage.googleapis.com":
            return httpx.Response(200, json=GEMINI_OK_BODY)
        return httpx.Response(404)

    transport.route = route

    async def resolver(tenant_id: str, provider: str) -> str | None:
        return {
            "openai": "sk-openai-credential-A",
            "gemini": "gemini-credential-B",
        }.get(provider)

    failover_mgr = FailoverManager()
    req = ProviderRequest(
        model="gpt-4o-mini",
        prompt="Hi",
        api_key="sk-openai-credential-A",
        tenant_id="t1",
    )
    decision = RoutingDecision(
        selected_provider="openai",
        selected_model="gpt-4o-mini",
        fallback_chain=[("gemini", "gemini-1.5-flash")],
    )

    res = await failover_mgr.execute_with_failover(
        req,
        decision,
        client=httpx.AsyncClient(transport=transport),
        credential_resolver=resolver,
    )

    assert res.provider == "gemini"
    openai_reqs = [r for r in transport.requests if r.url.host == "api.openai.com"]
    gemini_reqs = [
        r
        for r in transport.requests
        if r.url.host == "generativelanguage.googleapis.com"
    ]
    assert openai_reqs, "provider A must have been invoked"
    assert gemini_reqs, "provider B must have been invoked"

    # Provider A received A's credential.
    assert openai_reqs[0].headers["authorization"] == "Bearer sk-openai-credential-A"
    # Provider B received B's credential in its own scheme (query param key=).
    assert "key=gemini-credential-B" in str(gemini_reqs[0].url)
    # ZERO cross-provider credential reuse at the wire level.
    assert "sk-openai-credential-A" not in str(gemini_reqs[0].url)
    assert (
        "sk-openai-credential-A" not in dict(gemini_reqs[0].headers).values().__str__()
    )


@pytest.mark.asyncio
async def test_failover_fallback_model_reaches_the_wire() -> None:
    """The fallback (provider B, model B) decision must be what is invoked."""
    captured_models: list[str] = []

    def route(request: httpx.Request) -> httpx.Response:
        if request.url.host == "api.anthropic.com":
            return httpx.Response(401, json={"error": {"message": "invalid x-api-key"}})
        if request.url.host == "api.openai.com":
            captured_models.append(json.loads(request.content)["model"])
            return httpx.Response(200, json=OPENAI_OK_BODY)
        return httpx.Response(404)

    transport = RecordingTransport()
    transport.route = route

    async def resolver(tenant_id: str, provider: str) -> str | None:
        return {
            "anthropic": "sk-ant-primary",
            "openai": "sk-openai-secondary",
        }.get(provider)

    failover_mgr = FailoverManager(
        config=FailoverConfig(
            max_retries_per_provider=0, max_total_attempts=3, base_delay_seconds=0.01
        )
    )
    req = ProviderRequest(
        model="claude-3-5-sonnet", prompt="Hi", api_key="sk-ant-primary", tenant_id="t1"
    )
    decision = RoutingDecision(
        selected_provider="anthropic",
        selected_model="claude-3-5-sonnet",
        fallback_chain=[("openai", "gpt-4o-mini")],
    )

    res = await failover_mgr.execute_with_failover(
        req,
        decision,
        client=httpx.AsyncClient(transport=transport),
        credential_resolver=resolver,
    )

    assert res.provider == "openai"
    assert captured_models == ["gpt-4o-mini"]
    # The fallback provider must receive its own credential, not the primary's.
    openai_auth = [
        r.headers["authorization"]
        for r in transport.requests
        if r.url.host == "api.openai.com"
    ]
    assert openai_auth == ["Bearer sk-openai-secondary"]


@pytest.mark.asyncio
async def test_failover_timeout_is_retried_then_fails_over() -> None:
    """A timeout on the primary (classified retryable after normalization) must
    be retried once under defaults, then the request must fail over to
    provider B and succeed."""
    transport = RecordingTransport()
    openai_attempts = 0

    def route(request: httpx.Request) -> httpx.Response:
        nonlocal openai_attempts
        if request.url.host == "api.openai.com":
            openai_attempts += 1
            raise httpx.ReadTimeout("timed out", request=request)
        if request.url.host == "generativelanguage.googleapis.com":
            return httpx.Response(200, json=GEMINI_OK_BODY)
        return httpx.Response(404)

    transport.route = route

    async def resolver(tenant_id: str, provider: str) -> str | None:
        return {
            "openai": "sk-openai-test",
            "gemini": "gemini-secondary-key",
        }.get(provider)

    failover_mgr = FailoverManager(config=FailoverConfig(base_delay_seconds=0.01))
    req = ProviderRequest(
        model="gpt-4o-mini", prompt="Hi", api_key="sk-openai-test", tenant_id="t1"
    )
    decision = RoutingDecision(
        selected_provider="openai",
        selected_model="gpt-4o-mini",
        fallback_chain=[("gemini", "gemini-1.5-flash")],
    )

    res = await failover_mgr.execute_with_failover(
        req,
        decision,
        client=httpx.AsyncClient(transport=transport),
        credential_resolver=resolver,
    )

    assert res.provider == "gemini"
    assert openai_attempts == 2  # initial attempt + 1 retry (default budget)
