"""Centralized Upstream LLM Dispatcher with Phase 01 Provider Foundation.

Routes upstream provider invocations (Anthropic, OpenAI, Gemini, Groq, OpenRouter, DeepSeek) via:
1. LLMProvider adapters with Tier 5 Provider Prompt Caching.
2. Tenant-scoped BYOK key prioritization and platform fallback keys.
3. Explicit capabilities, observable routing policy, and bounded retry/failover.
4. FinOps token pricing and cost savings calculation.
"""

from __future__ import annotations

import inspect
import logging
from typing import Any

import httpx

from app.core.byok import get_byok_manager
from app.core.config import get_settings
from app.core.provider_credentials import (
    _PROVIDER_SETTINGS_KEYS,  # noqa: F401  (re-exported canonical authority)
    resolve_provider_credentials,
)
from app.optimizer.two_zone_compiler import CompiledPrompt, get_two_zone_compiler
from app.providers.base import (
    ChatMessage,
    ProviderCacheTelemetry,  # noqa: F401
    ProviderRequest,
    UpstreamLLMResponse,
)
from app.routing.failover import get_failover_manager
from app.routing.router import RoutingPolicy, get_model_router
from app.routing.workload_classifier import get_workload_classifier

logger = logging.getLogger(__name__)

# Single credential-resolution authority (R-ARCH-01, moved to
# app.core.provider_credentials by R-ARCH-03 so the failover manager can share
# it without a routing -> core dispatcher import cycle): platform fallback
# setting per provider, shared by the non-streaming and streaming dispatch
# variants and the failover-time default resolver so they can never drift.


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
    response_format: dict[str, Any] | str | None = None,
    correlation_id: str | None = None,
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

    # Route first: classify workload and pass explicit criteria to ModelRouter
    classifier = get_workload_classifier()
    classification = classifier.classify(
        prompt=prompt,
        messages=[m.model_dump() if hasattr(m, "model_dump") else m for m in messages]
        if messages
        else None,
        tools=tools,
        response_format=response_format,
    )

    router = get_model_router()
    routing_policy = RoutingPolicy(
        requested_model=model,
        tenant_id=tenant_id,
        workload_class=classification.workload_class,
        required_capabilities=classification.required_capabilities,
        context_tokens=classification.context_requirement,
        quality_requirement=classification.quality_requirement,
        allow_fallback=True,
        cost_aware_routing=getattr(settings, "COST_AWARE_ROUTING_ENABLED", False),
        correlation_id=correlation_id,
    )
    decision = router.route(routing_policy)

    from app.telemetry.metrics import metrics

    metrics.record_optimization_decision(
        tenant_id=tenant_id,
        workload_class=classification.workload_class,
        selected_provider=decision.selected_provider,
        selected_model=decision.selected_model,
        estimated_input_cost=decision.estimated_input_cost,
        cost_savings_usd_per_million=decision.cost_savings_usd_per_million,
        reason="; ".join(decision.decision_reasons[:2]),
    )

    # Determine explicit key for the authoritatively resolved provider from
    # tenant BYOK first, then platform fallback key (supports mocked settings
    # tests and BYOK-prioritized credential injection).
    async def resolve_credentials(t_id: str, prov: str) -> str | None:
        return await resolve_provider_credentials(settings, byok_mgr, t_id, prov)

    explicit_key = await resolve_credentials(tenant_id, decision.selected_provider)

    provider_req = ProviderRequest(
        model=decision.selected_model,
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
        correlation_id=correlation_id,
        extra_params={
            "prompt_cache_enabled": getattr(
                settings, "PROVIDER_PROMPT_CACHE_ENABLED", True
            )
        },
    )

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
            sig = inspect.signature(failover_mgr.execute_with_failover)
            if "credential_resolver" in sig.parameters:
                resp = await failover_mgr.execute_with_failover(
                    request=provider_req,
                    decision=decision,
                    client=client,
                    credential_resolver=resolve_credentials,
                )
            else:
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
    correlation_id: str | None = None,
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
        correlation_id=correlation_id,
    )
    return res.text if res is not None else None


async def call_upstream_llm_stream(
    prompt: str = "",
    tenant_id: str = "default",
    model: str = "gemini-1.5-flash",
    system_instruction: str | None = None,
    temperature: float = 0.7,
    max_tokens: int = 1024,
    messages: list[ChatMessage] | None = None,
) -> Any:
    """Stream token deltas from upstream provider adapters."""
    settings = get_settings()
    byok_mgr = get_byok_manager()

    default_system = (
        system_instruction
        or "You are JakeAI, an enterprise financial and operational AI companion."
    )

    classifier = get_workload_classifier()
    classification = classifier.classify(
        prompt=prompt,
        messages=[m.model_dump() if hasattr(m, "model_dump") else m for m in messages]
        if messages
        else None,
        tools=None,
        response_format=None,
    )

    router = get_model_router()
    routing_policy = RoutingPolicy(
        requested_model=model,
        tenant_id=tenant_id,
        workload_class=classification.workload_class,
        required_capabilities=classification.required_capabilities,
        context_tokens=classification.context_requirement,
        quality_requirement=classification.quality_requirement,
        allow_fallback=True,
        cost_aware_routing=getattr(settings, "COST_AWARE_ROUTING_ENABLED", False),
    )
    decision = router.route(routing_policy)

    from app.telemetry.metrics import metrics

    metrics.record_optimization_decision(
        tenant_id=tenant_id,
        workload_class=classification.workload_class,
        selected_provider=decision.selected_provider,
        selected_model=decision.selected_model,
        estimated_input_cost=decision.estimated_input_cost,
        cost_savings_usd_per_million=decision.cost_savings_usd_per_million,
        reason="; ".join(decision.decision_reasons[:2]),
    )

    async def resolve_credentials(t_id: str, prov: str) -> str | None:
        return await resolve_provider_credentials(settings, byok_mgr, t_id, prov)

    explicit_key = await resolve_credentials(tenant_id, decision.selected_provider)

    provider_req = ProviderRequest(
        model=decision.selected_model,
        prompt=prompt,
        messages=messages,
        system_instruction=default_system,
        temperature=temperature,
        max_tokens=max_tokens,
        tenant_id=tenant_id,
        api_key=explicit_key,
    )

    failover_mgr = get_failover_manager()
    timeout = httpx.Timeout(
        connect=5.0,
        read=settings.PROVIDER_TIMEOUT_SECONDS,
        write=10.0,
        pool=5.0,
    )

    try:
        async with httpx.AsyncClient(timeout=timeout) as client:
            sig = inspect.signature(failover_mgr.stream_with_failover)
            if "credential_resolver" in sig.parameters:
                stream_iter = failover_mgr.stream_with_failover(
                    request=provider_req,
                    decision=decision,
                    client=client,
                    credential_resolver=resolve_credentials,
                )
            else:
                stream_iter = failover_mgr.stream_with_failover(
                    request=provider_req,
                    decision=decision,
                    client=client,
                )
            async for chunk in stream_iter:
                if chunk and chunk.delta_text:
                    yield chunk.delta_text
    except Exception as exc:
        # Failure classification (R-LOGIC-04): a provider or stream failure
        # must propagate to the caller so a mid-stream consumer can signal an
        # error terminal state instead of silently truncating the stream.
        logger.debug("call_upstream_llm_stream error: %s", exc)
        raise
