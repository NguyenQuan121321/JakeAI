"""Centralized Upstream LLM Dispatcher with Tier 5 Provider Prompt Caching.

Handles upstream provider invocations (Google Gemini, OpenAI, Anthropic) with:
1. Tenant-scoped BYOK key prioritization and platform fallback keys.
2. Two-Zone prompt compilation with explicit Anthropic cache_control breakpoints.
3. Upstream cache telemetry extraction (Anthropic cache_read/creation, OpenAI cached_tokens).
4. Strict Rule 1 enforcement: Zero fake cache hits (upstream usage metadata only).
5. FinOps token pricing and cost savings calculation.
"""

from __future__ import annotations

import logging
import time
from typing import Any

import httpx
from pydantic import BaseModel, Field

from app.core.byok import get_byok_manager
from app.core.config import get_settings
from app.optimizer.provider_cache_policy import (
    CacheMissReason,
    get_provider_cache_policy,
)
from app.optimizer.provider_pricing import calculate_provider_costs
from app.optimizer.two_zone_compiler import CompiledPrompt, get_two_zone_compiler

logger = logging.getLogger(__name__)


class ProviderCacheTelemetry(BaseModel):
    """Fine-grained telemetry returned strictly from upstream provider usage metadata."""

    is_cache_eligible: bool = Field(
        default=False,
        description="Whether static prefix met minimum token size and provider policy",
    )
    cache_hit: bool = Field(
        default=False,
        description="Rule 1: ONLY True if upstream reported > 0 cached tokens",
    )
    cached_tokens: int = Field(
        default=0,
        description="Tokens read from upstream prompt cache (Anthropic cache_read, OpenAI cached_tokens)",
    )
    uncached_input_tokens: int = Field(
        default=0,
        description="Uncached input tokens processed by upstream provider",
    )
    cache_write_tokens: int = Field(
        default=0,
        description="Tokens written to upstream prompt cache (Anthropic cache_creation)",
    )
    output_tokens: int = Field(
        default=0, description="Tokens generated in upstream completion"
    )
    prefix_hash: str | None = Field(
        default=None, description="SHA-256 fingerprint of Zone 1 static prefix"
    )
    miss_reason: str = Field(
        default=CacheMissReason.NONE.value,
        description="Attribution reason for provider cache miss",
    )
    provider: str = Field(default="unknown")
    model: str = Field(default="unknown")
    latency_ms: float = Field(default=0.0)
    estimated_baseline_cost_usd: float = Field(default=0.0)
    actual_cost_usd: float = Field(default=0.0)
    estimated_savings_usd: float = Field(default=0.0)
    savings_percentage: float = Field(default=0.0)


class UpstreamLLMResponse(BaseModel):
    """Comprehensive upstream response with text completion and telemetry."""

    text: str
    model: str
    provider: str
    telemetry: ProviderCacheTelemetry


async def call_upstream_llm_detailed(
    prompt: str,
    tenant_id: str = "default",
    model: str = "gemini-1.5-flash",
    system_instruction: str | None = None,
    temperature: float = 0.7,
    max_tokens: int = 1024,
    compiled_prompt: CompiledPrompt | None = None,
    tools: list[dict[str, Any]] | None = None,
) -> UpstreamLLMResponse | None:
    """Call upstream LLM provider and capture full Tier 5 cache telemetry.

    Prioritizes decrypted tenant BYOK keys, falls back to platform keys.
    """
    settings = get_settings()
    byok_mgr = get_byok_manager()

    default_system = (
        system_instruction
        or "You are JakeAI, an enterprise financial and operational AI companion. "
        "Respond helpfully, concisely, and professionally in the same language as the user's prompt."
    )

    # Ensure two-zone compilation if not already provided
    if compiled_prompt is None:
        compiler = get_two_zone_compiler()
        compiled = compiler.compile(
            system_instruction=default_system,
            tools=tools,
            user_query=prompt,
        )
    else:
        compiled = compiled_prompt

    model_lower = model.lower()
    policy = get_provider_cache_policy(model)
    prefix_hash = compiled.static_prefix_hash if compiled.static_prefix else None

    # Determine provider family
    is_anthropic = "claude" in model_lower or "anthropic" in model_lower
    is_openai = any(k in model_lower for k in ("gpt", "o1", "o3"))
    is_gemini = "gemini" in model_lower or (not is_anthropic and not is_openai)

    # 1. Anthropic Provider (Claude)
    if is_anthropic:
        anthropic_key = (
            await byok_mgr.get_decrypted_key(tenant_id, "anthropic")
            or settings.ANTHROPIC_API_KEY
        )
        if anthropic_key:
            start_t = time.perf_counter()
            try:
                url = "https://api.anthropic.com/v1/messages"
                headers = {
                    "x-api-key": anthropic_key,
                    "anthropic-version": "2023-06-01",
                    "anthropic-beta": "prompt-caching-2024-07-31",
                    "content-type": "application/json",
                }

                anthropic_model = (
                    model if "claude" in model_lower else "claude-3-5-sonnet-20241022"
                )

                # Prepare payload with explicit cache_control on Zone 1 static prefix if eligible
                system_blocks: list[dict[str, Any]] = []
                static_text = compiled.static_prefix or default_system
                if (
                    compiled.is_cache_eligible
                    and settings.PROVIDER_PROMPT_CACHE_ENABLED
                ):
                    system_blocks.append(
                        {
                            "type": "text",
                            "text": static_text,
                            "cache_control": {"type": "ephemeral"},
                        }
                    )
                else:
                    system_blocks.append({"type": "text", "text": static_text})

                user_content = compiled.dynamic_suffix or prompt
                payload: dict[str, Any] = {
                    "model": anthropic_model,
                    "system": system_blocks,
                    "messages": [{"role": "user", "content": user_content}],
                    "temperature": temperature,
                    "max_tokens": max_tokens,
                }
                if tools:
                    payload["tools"] = tools

                async with httpx.AsyncClient(timeout=15.0) as client:
                    res = await client.post(url, headers=headers, json=payload)
                    latency = (time.perf_counter() - start_t) * 1000.0

                    if res.status_code == 200:
                        data = res.json()
                        content_list = data.get("content", [])
                        text_output = ""
                        for block in content_list:
                            if block.get("type") == "text":
                                text_output += block.get("text", "")

                        usage = data.get("usage", {})
                        cache_read = usage.get("cache_read_input_tokens", 0)
                        cache_write = usage.get("cache_creation_input_tokens", 0)
                        uncached = usage.get("input_tokens", 0)
                        out_tokens = usage.get("output_tokens", 0)

                        # Rule 1: cache_hit ONLY if upstream cache_read > 0
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
                            model=anthropic_model,
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
                            provider="anthropic",
                            model=anthropic_model,
                            latency_ms=round(latency, 2),
                            estimated_baseline_cost_usd=costs.baseline_cost_usd,
                            actual_cost_usd=costs.actual_cost_usd,
                            estimated_savings_usd=costs.savings_usd,
                            savings_percentage=costs.savings_percentage,
                        )

                        return UpstreamLLMResponse(
                            text=text_output.strip(),
                            model=anthropic_model,
                            provider="anthropic",
                            telemetry=telemetry,
                        )
                    else:
                        logger.debug(
                            "Anthropic call returned status %d: %s",
                            res.status_code,
                            res.text,
                        )
            except Exception as exc:
                logger.debug("Anthropic API call failed (%s), trying fallbacks", exc)

    # 2. OpenAI Provider
    if is_openai or not is_gemini:
        openai_key = (
            await byok_mgr.get_decrypted_key(tenant_id, "openai")
            or settings.OPENAI_API_KEY
        )
        if openai_key:
            start_t = time.perf_counter()
            try:
                url = "https://api.openai.com/v1/chat/completions"
                headers = {
                    "Authorization": f"Bearer {openai_key}",
                    "Content-Type": "application/json",
                }
                openai_model = (
                    model
                    if (
                        "gpt" in model_lower
                        or "o1" in model_lower
                        or "o3" in model_lower
                    )
                    else "gpt-4o-mini"
                )

                messages = [
                    {
                        "role": "system",
                        "content": compiled.static_prefix or default_system,
                    },
                    {"role": "user", "content": compiled.dynamic_suffix or prompt},
                ]

                payload = {
                    "model": openai_model,
                    "messages": messages,
                    "temperature": temperature,
                    "max_tokens": max_tokens,
                }
                if tools:
                    payload["tools"] = tools

                async with httpx.AsyncClient(timeout=15.0) as client:
                    res = await client.post(url, headers=headers, json=payload)
                    latency = (time.perf_counter() - start_t) * 1000.0

                    if res.status_code == 200:
                        data = res.json()
                        choices = data.get("choices", [])
                        text_output = (
                            choices[0].get("message", {}).get("content", "")
                            if choices
                            else ""
                        )

                        usage = data.get("usage", {})
                        total_prompt_tokens = usage.get("prompt_tokens", 0)
                        prompt_details = usage.get("prompt_tokens_details", {})
                        cached_tokens = prompt_details.get("cached_tokens", 0)
                        uncached = max(0, total_prompt_tokens - cached_tokens)
                        out_tokens = usage.get("completion_tokens", 0)

                        # Rule 1: cache_hit ONLY if upstream cached_tokens > 0
                        cache_hit = cached_tokens > 0
                        miss_reason = CacheMissReason.NONE.value
                        if not cache_hit:
                            if not compiled.is_cache_eligible:
                                miss_reason = CacheMissReason.BELOW_MINIMUM_SIZE.value
                            else:
                                miss_reason = CacheMissReason.COLD_START.value

                        costs = calculate_provider_costs(
                            model=openai_model,
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
                            provider="openai",
                            model=openai_model,
                            latency_ms=round(latency, 2),
                            estimated_baseline_cost_usd=costs.baseline_cost_usd,
                            actual_cost_usd=costs.actual_cost_usd,
                            estimated_savings_usd=costs.savings_usd,
                            savings_percentage=costs.savings_percentage,
                        )

                        return UpstreamLLMResponse(
                            text=text_output.strip(),
                            model=openai_model,
                            provider="openai",
                            telemetry=telemetry,
                        )
                    else:
                        logger.debug(
                            "OpenAI call returned status %d: %s",
                            res.status_code,
                            res.text,
                        )
            except Exception as exc:
                logger.debug("OpenAI API call failed (%s), trying fallbacks", exc)

    # 3. Google Gemini Provider
    gemini_key = (
        await byok_mgr.get_decrypted_key(tenant_id, "gemini") or settings.GEMINI_API_KEY
    )
    if gemini_key:
        start_t = time.perf_counter()
        try:
            gemini_model = model if "gemini" in model_lower else "gemini-1.5-flash"
            url = (
                f"https://generativelanguage.googleapis.com/v1beta/models/"
                f"{gemini_model}:generateContent?key={gemini_key}"
            )
            payload_gemini: dict[str, Any] = {
                "contents": [{"parts": [{"text": compiled.dynamic_suffix or prompt}]}],
                "systemInstruction": {
                    "parts": [{"text": compiled.static_prefix or default_system}]
                },
                "generationConfig": {
                    "temperature": temperature,
                    "maxOutputTokens": max_tokens,
                },
            }

            async with httpx.AsyncClient(timeout=15.0) as client:
                res = await client.post(url, json=payload_gemini)
                latency = (time.perf_counter() - start_t) * 1000.0

                if res.status_code == 200:
                    data = res.json()
                    candidates = data.get("candidates", [])
                    text_output = ""
                    if candidates:
                        parts = candidates[0].get("content", {}).get("parts", [])
                        if parts:
                            text_output = str(parts[0].get("text", "")).strip()

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
                        model=gemini_model,
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
                        provider="gemini",
                        model=gemini_model,
                        latency_ms=round(latency, 2),
                        estimated_baseline_cost_usd=costs.baseline_cost_usd,
                        actual_cost_usd=costs.actual_cost_usd,
                        estimated_savings_usd=costs.savings_usd,
                        savings_percentage=costs.savings_percentage,
                    )

                    return UpstreamLLMResponse(
                        text=text_output,
                        model=gemini_model,
                        provider="gemini",
                        telemetry=telemetry,
                    )
                else:
                    logger.debug(
                        "Gemini call returned status %d: %s",
                        res.status_code,
                        res.text,
                    )
        except Exception as exc:
            logger.debug("Gemini API call failed (%s)", exc)

    return None


async def call_upstream_llm(
    prompt: str,
    tenant_id: str = "default",
    model: str = "gemini-1.5-flash",
    system_instruction: str | None = None,
    temperature: float = 0.7,
    max_tokens: int = 1024,
    compiled_prompt: CompiledPrompt | None = None,
    tools: list[dict[str, Any]] | None = None,
) -> str | None:
    """Convenience wrapper returning plain text response for backward compatibility."""
    res = await call_upstream_llm_detailed(
        prompt=prompt,
        tenant_id=tenant_id,
        model=model,
        system_instruction=system_instruction,
        temperature=temperature,
        max_tokens=max_tokens,
        compiled_prompt=compiled_prompt,
        tools=tools,
    )
    return res.text if res is not None else None
