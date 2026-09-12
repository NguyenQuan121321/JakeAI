"""OpenAI LLM Provider Adapter with Tier 5 Automatic Prefix Caching.

Owns:
1. Credential injection (BYOK tenant key with platform key fallback).
2. Request translation with JSON mode / structured output schema support.
3. Response & SSE streaming translation.
4. Telemetry extraction (prompt_tokens_details.cached_tokens).
5. Error normalization into typed ProviderErrors with zero credential leakage.
"""

from __future__ import annotations

import json
import time
from typing import TYPE_CHECKING, Any

import httpx

if TYPE_CHECKING:
    from collections.abc import AsyncIterator

from app.core.byok import get_byok_manager
from app.core.config import get_settings
from app.optimizer.provider_cache_policy import CacheMissReason
from app.optimizer.provider_pricing import calculate_provider_costs
from app.optimizer.two_zone_compiler import get_two_zone_compiler
from app.providers.base import (
    LLMProvider,
    ModelCapabilities,
    ModelCapabilityCatalog,
    ProviderCacheTelemetry,
    ProviderRequest,
    ProviderResponse,
    StreamChunk,
    format_openai_chat_messages,
)
from app.providers.errors import (
    ProviderAuthenticationError,
    ProviderTimeoutError,
    ProviderUnavailableError,
    normalize_provider_error,
)


class OpenAIAdapter(LLMProvider):
    """Production adapter for OpenAI GPT/o-series models."""

    provider_name: str = "openai"

    def capabilities(self, model: str) -> ModelCapabilities:
        return ModelCapabilityCatalog.get(model, provider=self.provider_name)

    async def _resolve_api_key(self, request: ProviderRequest) -> str:
        if request.api_key:
            return request.api_key
        byok_mgr = get_byok_manager()
        key = await byok_mgr.get_decrypted_key(request.tenant_id, self.provider_name)
        if key:
            return key
        settings = get_settings()
        if settings.OPENAI_API_KEY:
            return settings.OPENAI_API_KEY
        raise ProviderAuthenticationError(
            message="No OpenAI API key configured (neither tenant BYOK nor platform default)",
            provider=self.provider_name,
            model=request.model,
        )

    def _prepare_payload(
        self, request: ProviderRequest, stream: bool = False
    ) -> tuple[dict[str, str], dict[str, Any]]:
        default_system = (
            request.system_instruction
            or "You are JakeAI, an enterprise financial and operational AI companion. "
            "Respond helpfully, concisely, and professionally in the same language as the user's prompt."
        )

        compiled = request.compiled_prompt
        if compiled is None:
            compiler = get_two_zone_compiler()
            compiled = compiler.compile(
                system_instruction=default_system,
                tools=request.tools,
                user_query=request.prompt,
            )

        headers = {
            "Content-Type": "application/json",
        }
        if request.extra_headers:
            headers.update(request.extra_headers)

        openai_model = (
            request.model
            if any(k in request.model.lower() for k in ("gpt", "o1", "o3"))
            else "gpt-4o-mini"
        )

        messages = format_openai_chat_messages(
            request=request,
            default_system=default_system,
            compiled=compiled,
        )

        payload: dict[str, Any] = {
            "model": openai_model,
            "messages": messages,
            "temperature": request.temperature,
            "max_tokens": request.max_tokens,
            "stream": stream,
        }
        if request.tools:
            payload["tools"] = request.tools
        if request.response_format:
            payload["response_format"] = request.response_format
        if request.extra_params:
            payload.update(request.extra_params)

        return headers, payload

    async def complete(
        self,
        request: ProviderRequest,
        client: httpx.AsyncClient | None = None,
    ) -> ProviderResponse:
        api_key = await self._resolve_api_key(request)
        headers, payload = self._prepare_payload(request, stream=False)
        headers["Authorization"] = f"Bearer {api_key}"

        compiled = request.compiled_prompt or get_two_zone_compiler().compile(
            system_instruction=request.system_instruction or "",
            tools=request.tools,
            user_query=request.prompt,
        )
        prefix_hash = compiled.static_prefix_hash if compiled.static_prefix else None
        url = "https://api.openai.com/v1/chat/completions"
        start_t = time.perf_counter()

        async def _exec(c: httpx.AsyncClient) -> ProviderResponse:
            try:
                res = await c.post(url, headers=headers, json=payload)
            except httpx.TimeoutException as exc:
                raise ProviderTimeoutError(
                    message=f"Provider request timed out: {exc}",
                    provider=self.provider_name,
                    model=payload["model"],
                    raw_error=exc,
                ) from exc
            except httpx.TransportError as exc:
                raise ProviderUnavailableError(
                    message=f"Provider endpoint unreachable: {exc}",
                    provider=self.provider_name,
                    model=payload["model"],
                    raw_error=exc,
                ) from exc
            latency = (time.perf_counter() - start_t) * 1000.0

            if res.status_code != 200:
                body = None
                try:
                    body = res.json()
                except Exception:
                    body = res.text
                raise normalize_provider_error(
                    provider=self.provider_name,
                    status_code=res.status_code,
                    response_body=body,
                    model=payload["model"],
                )

            try:
                data = res.json()
            except Exception as exc:
                raise ProviderUnavailableError(
                    message=f"Provider returned a malformed JSON response: {exc}",
                    provider=self.provider_name,
                    model=payload["model"],
                    status_code=res.status_code,
                    raw_error=exc,
                ) from exc
            choices = data.get("choices", [])
            text_output = (
                choices[0].get("message", {}).get("content", "") if choices else ""
            )
            tool_calls = (
                choices[0].get("message", {}).get("tool_calls") if choices else None
            )

            usage = data.get("usage", {})
            total_prompt_tokens = usage.get("prompt_tokens", 0)
            prompt_details = usage.get("prompt_tokens_details", {})
            cached_tokens = prompt_details.get("cached_tokens", 0)
            uncached = max(0, total_prompt_tokens - cached_tokens)
            out_tokens = usage.get("completion_tokens", 0)

            cache_hit = cached_tokens > 0
            miss_reason = CacheMissReason.NONE.value
            if not cache_hit:
                if not compiled.is_cache_eligible:
                    miss_reason = CacheMissReason.BELOW_MINIMUM_SIZE.value
                else:
                    miss_reason = CacheMissReason.COLD_START.value

            costs = calculate_provider_costs(
                model=payload["model"],
                uncached_input_tokens=uncached,
                cached_input_tokens=cached_tokens,
                cache_write_tokens=0,
                output_tokens=out_tokens,
            )

            telemetry = ProviderCacheTelemetry(
                is_cache_eligible=compiled.is_cache_eligible,
                cache_hit=cache_hit,
                cached_tokens=cached_tokens,
                uncached_input_tokens=uncached,
                cache_write_tokens=0,
                output_tokens=out_tokens,
                prefix_hash=prefix_hash,
                miss_reason=miss_reason,
                provider=self.provider_name,
                model=payload["model"],
                latency_ms=round(latency, 2),
                estimated_baseline_cost_usd=costs.baseline_cost_usd,
                actual_cost_usd=costs.actual_cost_usd,
                estimated_savings_usd=costs.savings_usd,
                savings_percentage=costs.savings_percentage,
            )

            return ProviderResponse(
                text=str(text_output).strip(),
                model=payload["model"],
                provider=self.provider_name,
                telemetry=telemetry,
                finish_reason=choices[0].get("finish_reason") if choices else "stop",
                raw_usage=usage,
                tool_calls=tool_calls,
            )

        if client is not None:
            return await _exec(client)
        async with httpx.AsyncClient(timeout=30.0) as c:
            return await _exec(c)

    async def stream(
        self,
        request: ProviderRequest,
        client: httpx.AsyncClient | None = None,
    ) -> AsyncIterator[StreamChunk]:
        api_key = await self._resolve_api_key(request)
        headers, payload = self._prepare_payload(request, stream=True)
        headers["Authorization"] = f"Bearer {api_key}"
        url = "https://api.openai.com/v1/chat/completions"

        async def _stream_runner(c: httpx.AsyncClient) -> AsyncIterator[StreamChunk]:
            try:
                async with c.stream("POST", url, headers=headers, json=payload) as res:
                    if res.status_code != 200:
                        body = await res.aread()
                        raise normalize_provider_error(
                            provider=self.provider_name,
                            status_code=res.status_code,
                            response_body=body.decode(errors="replace"),
                            model=payload["model"],
                        )
                    async for line in res.aiter_lines():
                        if line.startswith("data: "):
                            data_str = line[6:].strip()
                            if data_str == "[DONE]":
                                break
                            try:
                                event_data = json.loads(data_str)
                                choices = event_data.get("choices", [])
                                if choices:
                                    delta = choices[0].get("delta", {})
                                    content = delta.get("content", "")
                                    finish = choices[0].get("finish_reason")
                                    tool_chunks = delta.get("tool_calls")
                                    if content or finish or tool_chunks:
                                        yield StreamChunk(
                                            delta_text=content or "",
                                            model=payload["model"],
                                            provider=self.provider_name,
                                            finish_reason=finish,
                                            tool_call_chunks=tool_chunks,
                                        )
                            except json.JSONDecodeError:
                                continue
            except httpx.TimeoutException as exc:
                raise ProviderTimeoutError(
                    message=f"Provider stream timed out: {exc}",
                    provider=self.provider_name,
                    model=payload["model"],
                    raw_error=exc,
                ) from exc
            except httpx.TransportError as exc:
                raise ProviderUnavailableError(
                    message=f"Provider stream endpoint unreachable: {exc}",
                    provider=self.provider_name,
                    model=payload["model"],
                    raw_error=exc,
                ) from exc

        if client is not None:
            async for chunk in _stream_runner(client):
                yield chunk
        else:
            async with httpx.AsyncClient(timeout=60.0) as c:
                async for chunk in _stream_runner(c):
                    yield chunk
