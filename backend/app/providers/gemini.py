"""Google Gemini LLM Provider Adapter with Context Caching Telemetry.

Owns:
1. Credential injection (BYOK tenant key with platform key fallback).
2. Request translation to Google Generative Language schema.
3. Response & SSE streaming translation.
4. Telemetry extraction (cachedContentTokenCount, promptTokenCount, candidatesTokenCount).
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
from app.optimizer.provider_cache_policy import (
    CacheMissReason,
    get_provider_cache_policy,
)
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


class GeminiAdapter(LLMProvider):
    """Production adapter for Google Gemini models."""

    provider_name: str = "gemini"

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
        if settings.GEMINI_API_KEY:
            return settings.GEMINI_API_KEY
        raise ProviderAuthenticationError(
            message="No Google Gemini API key configured (neither tenant BYOK nor platform default)",
            provider=self.provider_name,
            model=request.model,
        )

    def _prepare_payload(self, request: ProviderRequest) -> tuple[str, dict[str, Any]]:
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

        gemini_model = (
            request.model if "gemini" in request.model.lower() else "gemini-1.5-flash"
        )

        contents: list[dict[str, Any]] = []
        if request.messages:
            for m in request.messages:
                if m.role in ("system", "developer"):
                    continue
                role = "model" if m.role == "assistant" else "user"
                contents.append({"role": role, "parts": [{"text": m.content}]})
            if not contents:
                contents = [
                    {"parts": [{"text": compiled.dynamic_suffix or request.prompt}]}
                ]
        else:
            contents = [
                {"parts": [{"text": compiled.dynamic_suffix or request.prompt}]}
            ]

        payload: dict[str, Any] = {
            "contents": contents,
            "systemInstruction": {
                "parts": [{"text": compiled.static_prefix or default_system}]
            },
            "generationConfig": {
                "temperature": request.temperature,
                "maxOutputTokens": request.max_tokens,
            },
        }
        if request.extra_params:
            payload.update(request.extra_params)

        return gemini_model, payload

    async def complete(
        self,
        request: ProviderRequest,
        client: httpx.AsyncClient | None = None,
    ) -> ProviderResponse:
        gemini_key = await self._resolve_api_key(request)
        model_name, payload = self._prepare_payload(request)

        compiled = request.compiled_prompt or get_two_zone_compiler().compile(
            system_instruction=request.system_instruction or "",
            tools=request.tools,
            user_query=request.prompt,
        )
        policy = get_provider_cache_policy(model_name)
        prefix_hash = compiled.static_prefix_hash if compiled.static_prefix else None

        url = (
            f"https://generativelanguage.googleapis.com/v1beta/models/"
            f"{model_name}:generateContent?key={gemini_key}"
        )
        start_t = time.perf_counter()

        async def _exec(c: httpx.AsyncClient) -> ProviderResponse:
            res = await c.post(url, json=payload)
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
                    model=model_name,
                )

            data = res.json()
            candidates = data.get("candidates", [])
            text_output = ""
            finish_reason = "stop"
            if candidates:
                parts = candidates[0].get("content", {}).get("parts", [])
                if parts:
                    text_output = str(parts[0].get("text", "")).strip()
                finish_reason = candidates[0].get("finishReason", "stop").lower()

            usage_meta = data.get("usageMetadata", {})
            prompt_count = usage_meta.get("promptTokenCount", 0)
            cached_count = usage_meta.get("cachedContentTokenCount", 0)
            uncached = max(0, prompt_count - cached_count)
            out_tokens = usage_meta.get("candidatesTokenCount", 0)

            cache_hit = cached_count > 0
            miss_reason = CacheMissReason.NONE.value
            if not cache_hit:
                if prompt_count < policy.min_cache_tokens:
                    miss_reason = CacheMissReason.BELOW_MINIMUM_SIZE.value
                else:
                    miss_reason = CacheMissReason.COLD_START.value

            costs = calculate_provider_costs(
                model=model_name,
                uncached_input_tokens=uncached,
                cached_input_tokens=cached_count,
                cache_write_tokens=0,
                output_tokens=out_tokens,
            )

            telemetry = ProviderCacheTelemetry(
                is_cache_eligible=(prompt_count >= policy.min_cache_tokens),
                cache_hit=cache_hit,
                cached_tokens=cached_count,
                uncached_input_tokens=uncached,
                cache_write_tokens=0,
                output_tokens=out_tokens,
                prefix_hash=prefix_hash,
                miss_reason=miss_reason,
                provider=self.provider_name,
                model=model_name,
                latency_ms=round(latency, 2),
                estimated_baseline_cost_usd=costs.baseline_cost_usd,
                actual_cost_usd=costs.actual_cost_usd,
                estimated_savings_usd=costs.savings_usd,
                savings_percentage=costs.savings_percentage,
                turn_count=len(request.messages) if request.messages else 1,
            )

            return ProviderResponse(
                text=text_output,
                model=model_name,
                provider=self.provider_name,
                telemetry=telemetry,
                finish_reason=finish_reason,
                raw_usage={
                    "prompt_tokens": prompt_count,
                    "completion_tokens": out_tokens,
                    "cached_tokens": cached_count,
                },
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
        gemini_key = await self._resolve_api_key(request)
        model_name, payload = self._prepare_payload(request)
        url = (
            f"https://generativelanguage.googleapis.com/v1beta/models/"
            f"{model_name}:streamGenerateContent?alt=sse&key={gemini_key}"
        )

        async def _stream_runner(c: httpx.AsyncClient) -> AsyncIterator[StreamChunk]:
            async with c.stream("POST", url, json=payload) as res:
                if res.status_code != 200:
                    body = await res.aread()
                    raise normalize_provider_error(
                        provider=self.provider_name,
                        status_code=res.status_code,
                        response_body=body.decode(errors="replace"),
                        model=model_name,
                    )
                async for line in res.aiter_lines():
                    if line.startswith("data: "):
                        data_str = line[6:].strip()
                        try:
                            event_data = json.loads(data_str)
                            candidates = event_data.get("candidates", [])
                            if candidates:
                                parts = (
                                    candidates[0].get("content", {}).get("parts", [])
                                )
                                if parts:
                                    text_chunk = parts[0].get("text", "")
                                    finish = candidates[0].get("finishReason")
                                    yield StreamChunk(
                                        delta_text=text_chunk,
                                        model=model_name,
                                        provider=self.provider_name,
                                        finish_reason=finish,
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
