"""Groq LPU LLM Provider Adapter for High-Velocity Inference.

Owns:
1. Credential injection (BYOK tenant key with platform key fallback).
2. Request translation to Groq OpenAI-compatible chat completion schema.
3. Response & SSE streaming translation.
4. Error normalization into typed ProviderErrors with zero credential leakage.
5. Explicit zero prompt-cache policy (LPU hardware architecture).
"""

from __future__ import annotations

import contextlib
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
    format_openai_chat_messages,
)
from app.providers.errors import (
    ProviderAuthenticationError,
    normalize_provider_error,
)


class GroqAdapter(LLMProvider):
    """Production adapter for Groq LPU models (Llama 3, Mixtral)."""

    provider_name: str = "groq"

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
        platform_key = getattr(settings, "GROQ_API_KEY", None) or os.environ.get(
            "GROQ_API_KEY"
        )
        if platform_key:
            return platform_key
        raise ProviderAuthenticationError(
            message="No Groq API key configured (neither tenant BYOK nor platform default)",
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

        groq_model = (
            request.model
            if "llama" in request.model.lower()
            else "llama-3.3-70b-versatile"
        )

        messages = format_openai_chat_messages(
            request=request,
            default_system=default_system,
            compiled=compiled,
        )

        payload: dict[str, Any] = {
            "model": groq_model,
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
        url = "https://api.groq.com/openai/v1/chat/completions"
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
                retry_after = None
                raw_retry = res.headers.get("retry-after")
                if raw_retry:
                    with contextlib.suppress(ValueError):
                        retry_after = float(raw_retry)
                raise normalize_provider_error(
                    provider=self.provider_name,
                    status_code=res.status_code,
                    response_body=body,
                    model=payload["model"],
                    retry_after=retry_after,
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
        url = "https://api.groq.com/openai/v1/chat/completions"

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
