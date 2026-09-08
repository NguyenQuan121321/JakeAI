"""OpenRouter Multi-Provider Aggregator Adapter.

Owns:
1. Credential injection (BYOK tenant key with platform key fallback).
2. Request translation to OpenRouter unified OpenAI-compatible endpoint.
3. Response & SSE streaming translation.
4. Error normalization into typed ProviderErrors with zero credential leakage.
"""

from __future__ import annotations

import json
import os
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


class OpenRouterAdapter(LLMProvider):
    """Production adapter for OpenRouter gateway."""

    provider_name: str = "openrouter"

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
        platform_key = getattr(settings, "OPENROUTER_API_KEY", None) or os.environ.get(
            "OPENROUTER_API_KEY"
        )
        if platform_key:
            return platform_key
        raise ProviderAuthenticationError(
            message="No OpenRouter API key configured (neither tenant BYOK nor platform default)",
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
            "HTTP-Referer": "https://jakeai.local",
            "X-Title": "JakeAI Platform",
        }
        if request.extra_headers:
            headers.update(request.extra_headers)

        openrouter_model = (
            request.model if "/" in request.model else f"openai/{request.model}"
        )

        messages: list[dict[str, Any]] = []
        static_sys = compiled.static_prefix or default_system
        if request.messages:
            has_system = any(
                m.role in ("system", "developer") for m in request.messages
            )
            if not has_system and static_sys.strip():
                messages.append({"role": "system", "content": static_sys.strip()})
            for m in request.messages:
                entry: dict[str, Any] = {"role": m.role, "content": m.content}
                if m.name:
                    entry["name"] = m.name
                messages.append(entry)
        else:
            if static_sys.strip():
                messages.append({"role": "system", "content": static_sys.strip()})
            messages.append(
                {"role": "user", "content": compiled.dynamic_suffix or request.prompt}
            )

        payload: dict[str, Any] = {
            "model": openrouter_model,
            "messages": messages,
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
        headers["Authorization"] = f"Bearer {api_key}"

        compiled = request.compiled_prompt or get_two_zone_compiler().compile(
            system_instruction=request.system_instruction or "",
            tools=request.tools,
            user_query=request.prompt,
        )
        url = "https://openrouter.ai/api/v1/chat/completions"
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
            choices = data.get("choices", [])
            text_output = (
                choices[0].get("message", {}).get("content", "") if choices else ""
            )
            tool_calls = (
                choices[0].get("message", {}).get("tool_calls") if choices else None
            )

            usage = data.get("usage", {})
            prompt_tokens = usage.get("prompt_tokens", 0)
            completion_tokens = usage.get("completion_tokens", 0)

            costs = calculate_provider_costs(
                model=payload["model"],
                uncached_input_tokens=prompt_tokens,
                cached_input_tokens=0,
                cache_write_tokens=0,
                output_tokens=completion_tokens,
            )

            telemetry = ProviderCacheTelemetry(
                is_cache_eligible=False,
                cache_hit=False,
                cached_tokens=0,
                uncached_input_tokens=prompt_tokens,
                cache_write_tokens=0,
                output_tokens=completion_tokens,
                prefix_hash=compiled.static_prefix_hash
                if compiled.static_prefix
                else None,
                miss_reason=CacheMissReason.PROVIDER_UNSUPPORTED.value,
                provider=self.provider_name,
                model=payload["model"],
                latency_ms=round(latency, 2),
                estimated_baseline_cost_usd=costs.baseline_cost_usd,
                actual_cost_usd=costs.actual_cost_usd,
                estimated_savings_usd=0.0,
                savings_percentage=0.0,
                turn_count=len(request.messages) if request.messages else 1,
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
        url = "https://openrouter.ai/api/v1/chat/completions"

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

        if client is not None:
            async for chunk in _stream_runner(client):
                yield chunk
        else:
            async with httpx.AsyncClient(timeout=60.0) as c:
                async for chunk in _stream_runner(c):
                    yield chunk
