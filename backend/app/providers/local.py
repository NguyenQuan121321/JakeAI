"""Local Model Provider Adapter for self-hosted OpenAI-compatible inference engines.

Supports runtimes such as vLLM, Ollama, LM Studio, and LocalAI via OpenAI-compatible
chat completion endpoints without coupling to any specific runtime vendor.

Features:
- Configurable endpoint, model name, context window, concurrency limit, and pricing.
- Bounded concurrency semaphore.
- Proactive health probing with cached cooldown.
- Full SSE streaming support.
- Non-zero operational cost accounting (energy + compute modeling).
"""

from __future__ import annotations

import asyncio
import json
import logging
import time
from typing import TYPE_CHECKING, Any

import httpx

if TYPE_CHECKING:
    from collections.abc import AsyncIterator

from app.core.config import get_settings
from app.providers.base import (
    LLMProvider,
    ModelCapabilities,
    ProviderCacheTelemetry,
    ProviderRequest,
    ProviderResponse,
    StreamChunk,
    format_openai_chat_messages,
)
from app.providers.errors import (
    ProviderTimeoutError,
    ProviderUnavailableError,
    normalize_provider_error,
)

logger = logging.getLogger(__name__)


class LocalModelAdapter(LLMProvider):
    """Production provider adapter for self-hosted / local OpenAI-compatible inference."""

    provider_name: str = "local"

    def __init__(
        self,
        endpoint: str | None = None,
        model_name: str | None = None,
        context_limit: int | None = None,
        concurrency_limit: int | None = None,
        input_pricing: float | None = None,
        output_pricing: float | None = None,
    ) -> None:
        settings = get_settings()
        self.endpoint = (endpoint or settings.LOCAL_MODEL_ENDPOINT).rstrip("/")
        self.default_model = model_name or settings.LOCAL_MODEL_NAME
        self.context_limit = context_limit or settings.LOCAL_MODEL_CONTEXT_LIMIT
        self.concurrency_limit = (
            concurrency_limit or settings.LOCAL_MODEL_CONCURRENCY_LIMIT
        )
        self.input_pricing = (
            input_pricing
            if input_pricing is not None
            else settings.LOCAL_MODEL_INPUT_PRICING
        )
        self.output_pricing = (
            output_pricing
            if output_pricing is not None
            else settings.LOCAL_MODEL_OUTPUT_PRICING
        )
        self._semaphore = asyncio.Semaphore(self.concurrency_limit)
        self._is_healthy: bool = True
        self._last_health_check: float = 0.0
        self._health_cache_ttl: float = 15.0

    def capabilities(self, model: str) -> ModelCapabilities:
        """Return explicit model capabilities for local model."""
        return ModelCapabilities(
            provider=self.provider_name,
            model=model or self.default_model,
            context_window=self.context_limit,
            supports_streaming=True,
            supports_tools=True,
            supports_json=True,
            supports_prompt_cache=False,
            supports_embeddings=False,
            supports_reasoning=False,
            input_pricing=self.input_pricing,
            output_pricing=self.output_pricing,
            cache_pricing=self.input_pricing,
            cache_write_pricing=self.input_pricing,
            min_cache_tokens=0,
        )

    async def check_health(self, client: httpx.AsyncClient | None = None) -> bool:
        """Probe local endpoint health with response caching and bounded timeout."""
        now = time.time()
        if (now - self._last_health_check) < self._health_cache_ttl:
            return self._is_healthy

        probe_urls = [f"{self.endpoint}/models", f"{self.endpoint}/health"]
        owns_client = client is None
        http_client = client or httpx.AsyncClient(timeout=1.5)

        try:
            for url in probe_urls:
                try:
                    resp = await http_client.get(url)
                    if resp.status_code in (
                        200,
                        404,
                    ):  # 404 on /health with active server is reachable
                        self._is_healthy = True
                        self._last_health_check = now
                        return True
                except (httpx.ConnectError, httpx.ConnectTimeout):
                    continue
            self._is_healthy = False
            self._last_health_check = now
            return False
        except Exception:
            self._is_healthy = False
            self._last_health_check = now
            return False
        finally:
            if owns_client:
                await http_client.aclose()

    def _prepare_payload(
        self, request: ProviderRequest, stream: bool = False
    ) -> tuple[dict[str, str], dict[str, Any]]:
        """Construct standard OpenAI-compatible chat payload."""
        messages = format_openai_chat_messages(
            request, default_system="You are a helpful assistant."
        )
        target_model = request.model or self.default_model

        payload: dict[str, Any] = {
            "model": target_model,
            "messages": messages,
            "stream": stream,
        }

        if request.temperature is not None:
            payload["temperature"] = request.temperature
        if request.max_tokens is not None:
            payload["max_tokens"] = request.max_tokens

        if request.tools:
            payload["tools"] = request.tools
            payload["tool_choice"] = "auto"

        if request.response_format:
            payload["response_format"] = request.response_format

        headers = {
            "Content-Type": "application/json",
            "Accept": "application/json",
        }
        if request.api_key:
            headers["Authorization"] = f"Bearer {request.api_key}"

        return headers, payload

    async def complete(
        self, request: ProviderRequest, client: httpx.AsyncClient | None = None
    ) -> ProviderResponse:
        """Execute synchronous / complete call against local OpenAI-compatible endpoint."""
        headers, payload = self._prepare_payload(request, stream=False)
        url = f"{self.endpoint}/chat/completions"
        owns_client = client is None
        http_client = client or httpx.AsyncClient(timeout=30.0)

        async with self._semaphore:
            try:
                resp = await http_client.post(url, json=payload, headers=headers)
                if resp.is_error:
                    raise normalize_provider_error(
                        provider=self.provider_name,
                        status_code=resp.status_code,
                        response_body=resp.text,
                        model=request.model,
                    )
                data = resp.json()
            except httpx.TimeoutException as exc:
                self._is_healthy = False
                raise ProviderTimeoutError(
                    message=f"Local model call timed out: {exc}",
                    provider=self.provider_name,
                    model=request.model,
                ) from exc
            except (httpx.ConnectError, httpx.NetworkError) as exc:
                self._is_healthy = False
                raise ProviderUnavailableError(
                    message=f"Local model endpoint unreachable at {self.endpoint}: {exc}",
                    provider=self.provider_name,
                    model=request.model,
                ) from exc
            finally:
                if owns_client:
                    await http_client.aclose()

        self._is_healthy = True
        choices = data.get("choices", [])
        if not choices:
            raise normalize_provider_error(
                provider=self.provider_name,
                status_code=500,
                response_body="Local model returned empty choices array",
                model=request.model,
            )

        message = choices[0].get("message", {})
        content = message.get("content") or ""
        tool_calls = message.get("tool_calls")

        usage = data.get("usage", {})
        prompt_tokens = int(usage.get("prompt_tokens", 0))
        comp_tokens = int(usage.get("completion_tokens", 0))

        # Operational compute cost calculation
        cost_usd = (
            (prompt_tokens * self.input_pricing) + (comp_tokens * self.output_pricing)
        ) / 1_000_000.0

        telemetry = ProviderCacheTelemetry(
            is_cache_eligible=False,
            cache_hit=False,
            cached_tokens=0,
            uncached_input_tokens=prompt_tokens,
            cache_write_tokens=0,
            output_tokens=comp_tokens,
            provider=self.provider_name,
            model=request.model or self.default_model,
            actual_cost_usd=round(cost_usd, 6),
        )

        return ProviderResponse(
            text=content,
            provider=self.provider_name,
            model=request.model or self.default_model,
            telemetry=telemetry,
            finish_reason=choices[0].get("finish_reason", "stop"),
            raw_usage=usage,
            tool_calls=tool_calls,
        )

    async def stream(
        self, request: ProviderRequest, client: httpx.AsyncClient | None = None
    ) -> AsyncIterator[StreamChunk]:
        """Stream chat completions from local OpenAI-compatible endpoint."""
        headers, payload = self._prepare_payload(request, stream=True)
        headers["Accept"] = "text/event-stream"
        url = f"{self.endpoint}/chat/completions"
        owns_client = client is None
        http_client = client or httpx.AsyncClient(timeout=60.0)

        prompt_tokens = 0
        comp_tokens = 0

        try:
            async with (
                self._semaphore,
                http_client.stream(
                    "POST", url, json=payload, headers=headers
                ) as response,
            ):
                if response.is_error:
                    body = await response.aread()
                    raise normalize_provider_error(
                        provider=self.provider_name,
                        status_code=response.status_code,
                        response_body=body.decode(),
                        model=request.model,
                    )

                async for line in response.aiter_lines():
                    if not line or not line.startswith("data:"):
                        continue
                    line_data = line[5:].strip()
                    if line_data == "[DONE]":
                        break

                    try:
                        chunk_json = json.loads(line_data)
                    except json.JSONDecodeError:
                        continue

                    choices = chunk_json.get("choices", [])
                    if not choices:
                        continue

                    delta = choices[0].get("delta", {})
                    text_delta = delta.get("content", "")
                    finish_reason = choices[0].get("finish_reason")

                    usage = chunk_json.get("usage")
                    if usage:
                        prompt_tokens = int(usage.get("prompt_tokens", prompt_tokens))
                        comp_tokens = int(usage.get("completion_tokens", comp_tokens))

                    if text_delta or finish_reason:
                        yield StreamChunk(
                            delta_text=text_delta or "",
                            finish_reason=finish_reason,
                            provider=self.provider_name,
                            model=request.model or self.default_model,
                        )
        except httpx.TimeoutException as exc:
            self._is_healthy = False
            raise ProviderTimeoutError(
                message=f"Local model stream timed out: {exc}",
                provider=self.provider_name,
                model=request.model,
            ) from exc
        except (httpx.ConnectError, httpx.NetworkError) as exc:
            self._is_healthy = False
            raise ProviderUnavailableError(
                message=f"Local model endpoint unreachable: {exc}",
                provider=self.provider_name,
                model=request.model,
            ) from exc
        finally:
            if owns_client:
                await http_client.aclose()

        # Operational compute cost calculation
        cost_usd = (
            (prompt_tokens * self.input_pricing) + (comp_tokens * self.output_pricing)
        ) / 1_000_000.0

        telemetry = ProviderCacheTelemetry(
            is_cache_eligible=False,
            cache_hit=False,
            cached_tokens=0,
            uncached_input_tokens=prompt_tokens,
            cache_write_tokens=0,
            output_tokens=comp_tokens,
            provider=self.provider_name,
            model=request.model or self.default_model,
            actual_cost_usd=round(cost_usd, 6),
        )

        yield StreamChunk(
            delta_text="",
            finish_reason="stop",
            provider=self.provider_name,
            model=request.model or self.default_model,
            telemetry=telemetry,
        )
