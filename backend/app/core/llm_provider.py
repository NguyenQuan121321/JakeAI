"""Centralized Upstream LLM Dispatcher with Phase 01 Provider Foundation.

Routes upstream provider invocations (Anthropic, OpenAI, Gemini, Groq, OpenRouter, DeepSeek) via:
1. LLMProvider adapters with Tier 5 Provider Prompt Caching.
2. Tenant-scoped BYOK key prioritization and platform fallback keys.
3. Explicit capabilities, observable routing policy, and bounded retry/failover.
4. FinOps token pricing and cost savings calculation.
"""

from __future__ import annotations

import logging
from typing import Any

import httpx

from app.core.byok import get_byok_manager
from app.core.config import get_settings
from app.optimizer.two_zone_compiler import CompiledPrompt, get_two_zone_compiler
from app.providers.base import (
    ChatMessage,
    ProviderCacheTelemetry,  # noqa: F401
    ProviderRequest,
    UpstreamLLMResponse,
)
from app.routing.failover import get_failover_manager
from app.routing.router import RoutingPolicy, get_model_router

logger = logging.getLogger(__name__)


async def call_upstream_llm_detailed(
    prompt: str = "",
    tenant_id: str = "default",
    model: str = "gemini-1.5-flash",
    system_instruction: str | None = None,
    temperature: float = 0.7,
    max_tokens: int = 1024,
    compiled_prompt: CompiledPrompt | None = None,
    tools: list[dict[str, Any]] | None = None,
    messages: list[ChatMessage] | None = None,
    response_format: dict[str, Any] | None = None,
) -> UpstreamLLMResponse | None:
    """Call upstream LLM provider and capture full Tier 5 cache telemetry.

    Dispatches through ModelRouter and FailoverManager using isolated provider adapters.
    Prioritizes decrypted tenant BYOK keys, falls back to platform keys.
    """
    settings = get_settings()
    byok_mgr = get_byok_manager()

    default_system = (
        system_instruction
        or "You are JakeAI, an enterprise financial and operational AI companion. "
        "Respond helpfully, concisely, and professionally in the same language as the user's prompt."
    )

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
    is_anthropic = "claude" in model_lower or "anthropic" in model_lower
    is_openai = any(k in model_lower for k in ("gpt", "o1", "o3"))
    is_groq = "groq" in model_lower or "llama" in model_lower
    is_deepseek = "deepseek" in model_lower
    is_openrouter = "openrouter" in model_lower or "/" in model_lower
    is_gemini = "gemini" in model_lower or (
        not is_anthropic
        and not is_openai
        and not is_groq
        and not is_deepseek
        and not is_openrouter
    )

    # Determine explicit key from settings or BYOK if available to support mocked settings tests
    explicit_key: str | None = None
    if is_anthropic:
        explicit_key = await byok_mgr.get_decrypted_key(
            tenant_id, "anthropic"
        ) or getattr(settings, "ANTHROPIC_API_KEY", None)
    elif is_openai:
        explicit_key = await byok_mgr.get_decrypted_key(tenant_id, "openai") or getattr(
            settings, "OPENAI_API_KEY", None
        )
    elif is_groq:
        explicit_key = await byok_mgr.get_decrypted_key(tenant_id, "groq") or getattr(
            settings, "GROQ_API_KEY", None
        )
    elif is_deepseek:
        explicit_key = await byok_mgr.get_decrypted_key(
            tenant_id, "deepseek"
        ) or getattr(settings, "DEEPSEEK_API_KEY", None)
    elif is_openrouter:
        explicit_key = await byok_mgr.get_decrypted_key(
            tenant_id, "openrouter"
        ) or getattr(settings, "OPENROUTER_API_KEY", None)
    elif is_gemini:
        explicit_key = await byok_mgr.get_decrypted_key(tenant_id, "gemini") or getattr(
            settings, "GEMINI_API_KEY", None
        )

    provider_req = ProviderRequest(
        model=model,
        prompt=prompt,
        messages=messages,
        system_instruction=default_system,
        temperature=temperature,
        max_tokens=max_tokens,
        compiled_prompt=compiled,
        tools=tools,
        tenant_id=tenant_id,
        api_key=explicit_key,
        response_format=response_format,
        extra_params={
            "prompt_cache_enabled": getattr(
                settings, "PROVIDER_PROMPT_CACHE_ENABLED", True
            )
        },
    )

    router = get_model_router()
    routing_policy = RoutingPolicy(
        requested_model=model,
        tenant_id=tenant_id,
        allow_fallback=True,
    )
    decision = router.route(routing_policy)
    failover_mgr = get_failover_manager()

    from app.telemetry.metrics import metrics

    timeout = httpx.Timeout(
        connect=5.0,
        read=settings.PROVIDER_TIMEOUT_SECONDS,
        write=10.0,
        pool=5.0,
    )

    try:
        async with httpx.AsyncClient(timeout=timeout) as client:
            resp = await failover_mgr.execute_with_failover(
                request=provider_req,
                decision=decision,
                client=client,
            )

            metrics.record_provider_request(
                provider=resp.provider,
                model=resp.model,
                status="success",
                duration_ms=resp.telemetry.latency_ms,
                prompt_tokens=resp.telemetry.uncached_input_tokens
                + resp.telemetry.cached_tokens,
                completion_tokens=resp.telemetry.output_tokens,
                cost_usd=resp.telemetry.actual_cost_usd,
            )

            return UpstreamLLMResponse(
                text=resp.text,
                model=resp.model,
                provider=resp.provider,
                telemetry=resp.telemetry,
            )
    except Exception as exc:
        metrics.record_provider_request(
            provider=decision.selected_provider,
            model=decision.selected_model,
            status="error",
            duration_ms=0.0,
        )
        logger.debug("Provider dispatch failed via failover manager: %s", exc)
        return None


async def call_upstream_llm(
    prompt: str = "",
    tenant_id: str = "default",
    model: str = "gemini-1.5-flash",
    system_instruction: str | None = None,
    temperature: float = 0.7,
    max_tokens: int = 1024,
    compiled_prompt: CompiledPrompt | None = None,
    tools: list[dict[str, Any]] | None = None,
    messages: list[ChatMessage] | None = None,
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
        messages=messages,
    )
    return res.text if res is not None else None
