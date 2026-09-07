"""Anthropic Claude LLM Provider Adapter with Tier 5 Prompt Caching.

Owns:
1. Credential injection (BYOK tenant key with platform key fallback).
2. Request translation with explicit ephemeral cache_control breakpoints on Zone 1 static prefixes.
3. Response & SSE streaming translation.
4. Telemetry extraction (cache_read_input_tokens, cache_creation_input_tokens).
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
)
from app.providers.errors import (
    ProviderAuthenticationError,
    normalize_provider_error,
)


class AnthropicAdapter(LLMProvider):
    """Production adapter for Anthropic Claude models."""

    provider_name: str = "anthropic"

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
        if settings.ANTHROPIC_API_KEY:
            return settings.ANTHROPIC_API_KEY
        raise ProviderAuthenticationError(
            message="No Anthropic API key configured (neither tenant BYOK nor platform default)",
            provider=self.provider_name,
            model=request.model,
        )

    def _prepare_payload(
        self, request: ProviderRequest, stream: bool = False
    ) -> tuple[dict[str, str], dict[str, Any]]:
        settings = get_settings()
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
            "anthropic-version": "2023-06-01",
            "anthropic-beta": "prompt-caching-2024-07-31",
            "content-type": "application/json",
        }
        if request.extra_headers:
            headers.update(request.extra_headers)

        cache_enabled = (
            request.extra_params.get("prompt_cache_enabled")
            if (request.extra_params and "prompt_cache_enabled" in request.extra_params)
            else settings.PROVIDER_PROMPT_CACHE_ENABLED
        )
        system_blocks: list[dict[str, Any]] = []
        static_text = compiled.static_prefix or default_system
        if compiled.is_cache_eligible and cache_enabled:
            system_blocks.append(
                {
                    "type": "text",
                    "text": static_text,
                    "cache_control": {"type": "ephemeral"},
                }
            )
        else:
            system_blocks.append({"type": "text", "text": static_text})

        user_content = compiled.dynamic_suffix or request.prompt
        anthropic_model = (
            request.model
            if "claude" in request.model.lower()
            else "claude-3-5-sonnet-20241022"
        )

        payload: dict[str, Any] = {
            "model": anthropic_model,
            "system": system_blocks,
            "messages": [{"role": "user", "content": user_content}],
            "temperature": request.temperature,
            "max_tokens": request.max_tokens,
            "stream": stream,
        }
        if request.tools:
            payload["tools"] = request.tools
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
        headers["x-api-key"] = api_key

        compiled = request.compiled_prompt or get_two_zone_compiler().compile(
            system_instruction=request.system_instruction,
            tools=request.tools,
            user_query=request.prompt,
        )
        prefix_hash = compiled.static_prefix_hash if compiled.static_prefix else None
        url = "https://api.anthropic.com/v1/messages"
        start_t = time.perf_counter()

        async def _exec(c: httpx.AsyncClient) -> ProviderResponse:
            res = await c.post(url, headers=headers, json=payload)
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

            data = res.json()
            content_list = data.get("content", [])
            text_output = ""
            tool_calls: list[dict[str, Any]] = []

            for block in content_list:
                btype = block.get("type")
                if btype == "text":
                    text_output += block.get("text", "")
                elif btype == "tool_use":
                    tool_calls.append(block)

            usage = data.get("usage", {})
            cache_read = usage.get("cache_read_input_tokens", 0)
            cache_write = usage.get("cache_creation_input_tokens", 0)
            uncached = usage.get("input_tokens", 0)
            out_tokens = usage.get("output_tokens", 0)

            cache_hit = cache_read > 0
            miss_reason = CacheMissReason.NONE.value
            if not cache_hit:
                if cache_write > 0:
                    miss_reason = CacheMissReason.COLD_START.value
                elif not compiled.is_cache_eligible:
                    miss_reason = CacheMissReason.BELOW_MINIMUM_SIZE.value
                else:
                    miss_reason = CacheMissReason.PREFIX_CHANGED.value

            costs = calculate_provider_costs(
                model=payload["model"],
                uncached_input_tokens=uncached,
                cached_input_tokens=cache_read,
                cache_write_tokens=cache_write,
                output_tokens=out_tokens,
            )

            telemetry = ProviderCacheTelemetry(
                is_cache_eligible=compiled.is_cache_eligible,
                cache_hit=cache_hit,
                cached_tokens=cache_read,
                uncached_input_tokens=uncached,
                cache_write_tokens=cache_write,
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
                text=text_output.strip(),
                model=payload["model"],
                provider=self.provider_name,
                telemetry=telemetry,
                finish_reason=data.get("stop_reason") or "stop",
                raw_usage=usage,
                tool_calls=tool_calls if tool_calls else None,
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
        headers["x-api-key"] = api_key
        url = "https://api.anthropic.com/v1/messages"

        async def _stream_runner(c: httpx.AsyncClient) -> AsyncIterator[StreamChunk]:
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
                            etype = event_data.get("type")
                            if etype == "content_block_delta":
                                delta = event_data.get("delta", {})
                                if delta.get("type") == "text_delta":
                                    yield StreamChunk(
                                        delta_text=delta.get("text", ""),
                                        model=payload["model"],
                                        provider=self.provider_name,
                                    )
                            elif etype == "message_delta":
                                stop_reason = event_data.get("delta", {}).get("stop_reason")
                                yield StreamChunk(
                                    delta_text="",
                                    model=payload["model"],
                                    provider=self.provider_name,
                                    finish_reason=stop_reason,
                                )
                        except json.JSONDecodeError:
                            continue

        if client is not None:
            async for chunk in _stream_runner(client):
                yield chunk
        else:
            async with httpx.AsyncClient(timeout=60.0) as c:
                async for chunk in _stream_runner(c):
                    yield chunk
