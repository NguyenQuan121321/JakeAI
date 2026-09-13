"""AI Gateway as a Service.

Cost-optimizing reverse proxy providing:
1. Tier 1 SHA-256 Redis exact match caching (sub-millisecond, 0-token cost).
2. Per-tenant token budget quotas with soft alerting (80%) and hard suspension (100%).
3. Multi-provider circuit-breaker fallback.
"""

from __future__ import annotations

import asyncio
import contextlib
import json
import logging
import time
import uuid
from typing import TYPE_CHECKING, Any

if TYPE_CHECKING:
    from collections.abc import AsyncGenerator

from pydantic import BaseModel, Field

from app.core.byok import get_byok_manager
from app.core.circuit_breaker import CircuitBreaker
from app.core.llm_provider import (
    UpstreamLLMResponse,
    call_upstream_llm,
    call_upstream_llm_detailed,
)
from app.finops.budget import FinOpsBudgetManager, get_budget_manager
from app.finops.service import get_finops_service
from app.optimizer.context_optimizer import get_context_optimizer
from app.optimizer.semantic_cache import get_semantic_cache_manager
from app.optimizer.token_accounting import TokenAccounting
from app.optimizer.token_pruner import estimate_tokens
from app.optimizer.two_zone_compiler import get_two_zone_compiler
from app.providers.base import ChatMessage
from app.providers.registry import get_provider_registry

logger = logging.getLogger(__name__)

DEFAULT_MONTHLY_QUOTA = 1_000_000  # 1M tokens default quota


class QuotaStatus(BaseModel):
    """Current tenant quota consumption and status."""

    tenant_id: str
    quota_limit: int
    tokens_used: int
    tokens_remaining: int
    percentage_used: float
    is_suspended: bool
    warning: str | None


class GatewayChatRequest(BaseModel):
    """OpenAI-compatible chat completions proxy request."""

    model: str = Field(default="gemini-1.5-flash", description="Target model name")
    messages: list[ChatMessage] = Field(
        ..., min_length=1, description="List of messages"
    )
    temperature: float = Field(default=0.7, ge=0.0, le=2.0)
    max_tokens: int = Field(default=1024, ge=1)
    stream: bool = Field(
        default=False,
        description="Whether to stream back partial progress via Server-Sent Events",
    )
    tools: list[dict[str, Any]] | None = Field(
        default=None, description="Optional tools/functions schema"
    )
    response_format: dict[str, Any] | str | None = Field(
        default=None, description="Optional response format (e.g. JSON mode / schema)"
    )


class GatewayChatResponse(BaseModel):
    """OpenAI-compatible chat completion response with JakeAI caching metadata."""

    id: str
    object: str = "chat.completion"
    created: int
    model: str
    choices: list[dict[str, Any]]
    usage: dict[str, int]
    cached: bool
    tokens_saved: int
    reduction_percentage: float = 0.0
    provider_cache: dict[str, Any] | None = None


class QuotaManager:
    """Compatibility facade delegating all quota and budget authority to FinOpsBudgetManager.

    Established under WORK-03 as part of unified quota authority governance.
    """

    def __init__(self, budget_manager: FinOpsBudgetManager | None = None) -> None:
        self._budget_manager = budget_manager
        self._memory_usage: dict[str, int] = {}
        self._redis_available = True
        self._redis_retry_after: float = 0.0

    def _get_manager(self) -> FinOpsBudgetManager:
        if self._budget_manager is not None:
            return self._budget_manager
        return get_budget_manager()

    @property
    def redis_client(self) -> Any | None:
        return self._get_manager().redis_client

    @redis_client.setter
    def redis_client(self, value: Any | None) -> None:
        self._get_manager().redis_client = value

    @staticmethod
    def _get_period_key() -> str:
        return time.strftime("%Y-%m")

    async def _get_redis(self) -> Any | None:
        """Lazily initialize Redis connection with fast ping check and cooldown."""
        if self.redis_client is not None:
            return self.redis_client
        now = time.time()
        if not self._redis_available and now < self._redis_retry_after:
            return None
        try:
            from redis import asyncio as aioredis

            from app.core.config import get_settings

            settings = get_settings()
            client = aioredis.from_url(
                settings.REDIS_URL,
                decode_responses=False,
                socket_timeout=1.0,
                socket_connect_timeout=1.0,
            )
            await client.ping()
            self.redis_client = client
            self._redis_available = True
            return client
        except Exception as exc:
            logger.debug("QuotaManager Redis unavailable (%s)", exc)
            self._redis_available = False
            self._redis_retry_after = now + 30.0
            return None

    async def get_quota_limit(self, tenant_id: str) -> int:
        """Retrieve quota limit for a tenant."""
        return await self._get_manager().get_token_quota(tenant_id)

    async def set_quota_limit(self, tenant_id: str, new_limit: int) -> int:
        """Set or update quota limit for a tenant."""
        await self._get_manager().set_budget(tenant_id, token_quota=new_limit)
        return new_limit

    async def get_tokens_used(self, tenant_id: str) -> int:
        """Get current token usage for the active period."""
        return await self._get_manager().get_tokens_used(tenant_id)

    async def check_quota(
        self, tenant_id: str, estimated_tokens: int = 100
    ) -> tuple[bool, str | None]:
        """Check if tenant has quota remaining before inference.

        Returns:
            (is_allowed, warning_or_error_message)
        """
        return await self._get_manager().check_budget(
            tenant_id, estimated_tokens=estimated_tokens
        )

    async def record_usage(
        self, tenant_id: str, prompt_tokens: int, completion_tokens: int
    ) -> int:
        """Increment token consumption atomically in FinOps ledger."""
        total = prompt_tokens + completion_tokens
        new_tokens, _ = await self._get_manager().settle_request(tenant_id, total, 0.0)
        return new_tokens

    async def record_tokens_saved(self, tenant_id: str, tokens_saved: int) -> int:
        """Increment tokens saved atomically in FinOps ledger and Redis/memory cache."""
        redis = await self._get_redis()
        period = self._get_period_key()
        if redis is not None:
            try:
                key = f"gateway:tokens_saved:{tenant_id}:{period}"
                new_val = await redis.incrby(key, tokens_saved)
                with contextlib.suppress(Exception):
                    await self._get_manager().record_tokens_saved(
                        tenant_id, tokens_saved
                    )
                return int(new_val)
            except Exception as exc:
                logger.debug("Redis incrby tokens_saved failed (%s)", exc)

        mem_key = f"tokens_saved:{tenant_id}:{period}"
        self._memory_usage[mem_key] = self._memory_usage.get(mem_key, 0) + tokens_saved
        with contextlib.suppress(Exception):
            await self._get_manager().record_tokens_saved(tenant_id, tokens_saved)
        return self._memory_usage[mem_key]

    async def get_tokens_saved(self, tenant_id: str) -> int:
        """Get current tokens saved for the active period from Redis, memory, or FinOps ledger."""
        redis = await self._get_redis()
        period = self._get_period_key()
        if redis is not None:
            try:
                val = await redis.get(f"gateway:tokens_saved:{tenant_id}:{period}")
                if val:
                    return int(val)
            except Exception as exc:
                logger.debug("Redis read tokens_saved failed (%s)", exc)
        mem_key = f"tokens_saved:{tenant_id}:{period}"
        if mem_key in self._memory_usage:
            return self._memory_usage[mem_key]
        return await self._get_manager().get_tokens_saved(tenant_id)

    async def get_status(self, tenant_id: str) -> QuotaStatus:
        """Return full quota status object for a tenant."""
        status = await self._get_manager().get_budget_status(tenant_id)
        return QuotaStatus(
            tenant_id=tenant_id,
            quota_limit=status.token_quota,
            tokens_used=status.tokens_used,
            tokens_remaining=status.tokens_remaining,
            percentage_used=status.percentage_tokens_used,
            is_suspended=status.is_suspended,
            warning=status.warning,
        )


def _message_to_cache_dict(m: ChatMessage) -> dict[str, Any]:
    """Convert a chat message to its cache-identity representation.

    W-COST-03: the cache identity must include every generation-relevant
    message field (role, content, name, tool_call_id, tool_calls); dropping
    tool-call structure makes structurally different conversations collide
    on the same exact cache key.
    """
    msg_dict: dict[str, Any] = {"role": m.role, "content": m.content or ""}
    if m.name:
        msg_dict["name"] = m.name
    if m.tool_call_id:
        msg_dict["tool_call_id"] = m.tool_call_id
    if m.tool_calls:
        msg_dict["tool_calls"] = m.tool_calls
    return msg_dict


class GatewayInferenceProxy:
    """Reverse proxy executing inference with exact caching and quota governance."""

    def __init__(self, quota_manager: QuotaManager | None = None) -> None:
        self.quota_mgr = quota_manager or QuotaManager()
        self.cache_mgr = get_semantic_cache_manager()
        self.breaker = CircuitBreaker(
            name="ai_gateway_proxy",
            failure_threshold=3,
            recovery_timeout_seconds=10.0,
        )

    async def chat_completions(
        self,
        tenant_id: str,
        request: GatewayChatRequest,
        correlation_id: str | None = None,
    ) -> GatewayChatResponse:
        """Execute chat completion with Tier 1 Redis exact cache and quota deduction."""
        # 1. Quota Pre-check
        allowed, error_msg = await self.quota_mgr.check_quota(tenant_id)
        if not allowed:
            raise ValueError(error_msg or "Token budget quota exceeded")

        # Extract last user message for display/optimization
        last_user_msg = (
            next(
                (
                    m.content
                    for m in reversed(request.messages)
                    if m.role == "user" and m.content
                ),
                "",
            )
            or ""
        )

        # Build generation-relevant fields for canonical cache identity
        system_instructions = "\n".join(
            m.content or "" for m in request.messages if m.role == "system"
        )
        messages_as_dicts: list[dict[str, Any]] = [
            _message_to_cache_dict(m) for m in request.messages
        ]
        generation_params = {
            "temperature": request.temperature,
            "max_tokens": request.max_tokens,
        }

        # Resolve provider through the authoritative provider registry so cache
        # identity and BYOK injection match the routing/execution provider
        provider = get_provider_registry().resolve_provider_name_for_model(
            request.model
        )

        # 2. Tier 1 Exact Match Cache
        cache_entry = await self.cache_mgr.get(
            last_user_msg,
            tenant_id=tenant_id,
            model=request.model,
            provider=provider,
            system_instructions=system_instructions,
            messages=messages_as_dicts,
            tools=request.tools,
            response_format=request.response_format,
            generation_params=generation_params,
            exact_only=True,
        )
        now_ts = int(time.time())
        # Compute canonical model-visible input envelope tokens across all dimensions
        # (system instructions, conversation history, user query, tools, and RAG context)
        raw_input_tokens = TokenAccounting.calculate_envelope_tokens(
            messages=request.messages,
            tools=request.tools,
            model=request.model,
        )

        if cache_entry is not None:
            # Output Guardrail leak check on cached response (OPS-03)
            from app.guardrails import GuardrailsEngine
            from app.telemetry.metrics import metrics

            sanitized_cached, cache_leaked = (
                GuardrailsEngine.inspect_and_sanitize_output(
                    cache_entry.response, tenant_id
                )
            )
            if cache_leaked:
                metrics.record_security_incident("OUTPUT_DATA_LEAKAGE", tenant_id)
                raise ValueError(
                    "Output blocked due to security data leakage policy violation."
                )
            # Immediate zero-cost return with exact accounting
            est_completion = max(1, estimate_tokens(cache_entry.response))
            req_id = f"chatcmpl-{uuid.uuid4().hex[:12]}"
            record = TokenAccounting.record_transaction(
                request_id=req_id,
                tenant_id=tenant_id,
                model=request.model,
                raw_input_tokens=raw_input_tokens,
                optimized_input_tokens=0,
                completion_tokens=est_completion,
                cache_hit=True,
                cache_type=cache_entry.cache_type or "exact",
            )
            await self.quota_mgr.record_tokens_saved(tenant_id, record.tokens_saved)
            with contextlib.suppress(Exception):
                await get_finops_service().record_cache_hit(
                    request_id=req_id,
                    tenant_id=tenant_id,
                    model=request.model,
                    raw_tokens=record.raw_input_tokens,
                    output_tokens=est_completion,
                    cache_type=cache_entry.cache_type or "exact",
                )
            return GatewayChatResponse(
                id=req_id,
                created=now_ts,
                model=request.model,
                choices=[
                    {
                        "index": 0,
                        "message": {
                            "role": "assistant",
                            "content": sanitized_cached,
                        },
                        "finish_reason": "stop",
                    }
                ],
                usage={
                    "prompt_tokens": 0,
                    "completion_tokens": 0,
                    "total_tokens": 0,
                },
                cached=True,
                tokens_saved=record.tokens_saved,
                reduction_percentage=record.reduction_percentage,
            )

        # 3. Dynamic BYOK Key Injection (decrypt transiently in memory)
        byok_mgr = get_byok_manager()
        byok_key = await byok_mgr.get_decrypted_key(tenant_id, provider)

        # 4. Context Optimization via Tier 6 ContextOptimizer on dynamic input
        optimizer = get_context_optimizer()
        optimized_result = optimizer.optimize_dynamic_context(
            dynamic_context=last_user_msg,
            user_query=last_user_msg,
        )
        effective_query = optimized_result.content or last_user_msg

        # Tier 5: Two-Zone Prompt Compilation
        compiler = get_two_zone_compiler()
        compiled = compiler.partition_messages(request.messages)
        if effective_query and effective_query != last_user_msg:
            compiled = compiler.compile(
                system_instruction=compiled.static_prefix,
                user_query=effective_query,
                prompt_version=compiled.version,
                tenant_id=tenant_id,
            )

        # 5. Model Generation (Wrapped in CircuitBreaker)
        upstream_response: UpstreamLLMResponse | None = None

        # Prepare messages list preserving full conversation semantics
        messages_to_send: list[ChatMessage] = []
        found_last_user = False
        for m in reversed(request.messages):
            if not found_last_user and m.role == "user" and effective_query:
                messages_to_send.append(
                    ChatMessage(
                        role=m.role,
                        content=effective_query,
                        name=m.name,
                        tool_call_id=m.tool_call_id,
                        tool_calls=m.tool_calls,
                    )
                )
                found_last_user = True
            else:
                messages_to_send.append(m)
        messages_to_send.reverse()

        response_format_dict = (
            request.response_format
            if isinstance(request.response_format, dict)
            else None
        )

        async def call_model() -> str:
            nonlocal upstream_response
            upstream_res = await call_upstream_llm_detailed(
                prompt=effective_query,
                tenant_id=tenant_id,
                model=request.model,
                temperature=request.temperature,
                max_tokens=request.max_tokens,
                compiled_prompt=compiled,
                tools=request.tools,
                messages=messages_to_send,
                response_format=response_format_dict,
                correlation_id=correlation_id,
            )
            if upstream_res:
                upstream_response = upstream_res
                return upstream_res.text

            # Check legacy call_upstream_llm for backward-compatible mock overrides
            legacy_text = await call_upstream_llm(
                prompt=effective_query,
                tenant_id=tenant_id,
                model=request.model,
                temperature=request.temperature,
                max_tokens=request.max_tokens,
                compiled_prompt=compiled,
                tools=request.tools,
                messages=messages_to_send,
                correlation_id=correlation_id,
            )
            if legacy_text:
                return legacy_text

            # Deterministic generator for gateway requests with BYOK provenance
            key_tag = " [BYOK active]" if byok_key else ""
            return (
                f"[JakeAI Gateway Response via {request.model}{key_tag}]\n"
                f"Processed query: {effective_query[:120]}"
            )

        output_text = await self.breaker.call_with_fallback(call_model)

        # Output Inspection & Leakage Blocking (TASK OPS-03)
        from app.guardrails import GuardrailsEngine
        from app.telemetry.metrics import metrics

        sanitized_output, leak_detected = GuardrailsEngine.inspect_and_sanitize_output(
            output_text, tenant_id
        )
        if leak_detected:
            metrics.record_security_incident("OUTPUT_DATA_LEAKAGE", tenant_id)
            raise ValueError(
                "Output blocked due to security data leakage policy violation."
            )
        output_text = sanitized_output

        completion_tokens = max(1, estimate_tokens(output_text))
        req_id = f"chatcmpl-{uuid.uuid4().hex[:12]}"

        telemetry = upstream_response.telemetry if upstream_response else None
        provider_cache_meta = (
            telemetry.model_dump()
            if telemetry
            else {
                "is_cache_eligible": compiled.is_cache_eligible,
                "cache_hit": False,
                "cached_tokens": 0,
                "miss_reason": "offline_fallback",
                "prefix_hash": compiled.static_prefix_hash,
            }
        )

        # Compute optimized input envelope tokens after dynamic optimization
        optimized_input_tokens = TokenAccounting.calculate_envelope_tokens(
            messages=messages_to_send,
            tools=request.tools,
            model=request.model,
        )
        physical_tokens_pruned = max(0, raw_input_tokens - optimized_input_tokens)

        # The model that actually served the request (failover/rerouting may
        # select a different candidate than the requested one).
        served_model = (
            upstream_response.model
            if (
                upstream_response
                and upstream_response.model
                and upstream_response.model != "unknown"
            )
            else request.model
        )

        record = TokenAccounting.record_transaction(
            request_id=req_id,
            tenant_id=tenant_id,
            model=served_model,
            raw_input_tokens=raw_input_tokens,
            optimized_input_tokens=optimized_input_tokens,
            physical_tokens_pruned=physical_tokens_pruned,
            completion_tokens=completion_tokens,
            cache_hit=False,
            cache_type="none",
            provider_telemetry=telemetry,
        )

        # 6. Populate Tier 1 Cache for future hits
        await self.cache_mgr.set(
            prompt=last_user_msg,
            tenant_id=tenant_id,
            response=output_text,
            model=request.model,
            provider=provider,
            system_instructions=system_instructions,
            messages=messages_as_dicts,
            tools=request.tools,
            response_format=request.response_format,
            generation_params=generation_params,
        )

        # 7. Settlement happens exactly once, inside
        # FinOpsService.record_upstream_inference (tokens + dollars, using the
        # authoritative provider-reported totals when available). The gateway
        # must NOT settle quota separately, or every request is double-counted.
        if record.tokens_saved > 0:
            await self.quota_mgr.record_tokens_saved(tenant_id, record.tokens_saved)

        with contextlib.suppress(Exception):
            await get_finops_service().record_upstream_inference(
                request_id=req_id,
                tenant_id=tenant_id,
                provider=telemetry.provider if telemetry else provider,
                model=served_model,
                requested_model=request.model,
                raw_tokens=record.raw_input_tokens,
                optimized_tokens=record.optimized_input_tokens,
                output_tokens=record.completion_tokens,
                provider_usage=telemetry.model_dump() if telemetry else None,
                provider_cached_tokens=record.provider_cached_input_tokens,
                provider_cache_write_tokens=telemetry.cache_write_tokens
                if telemetry
                else 0,
                metadata={"prefix_hash": compiled.static_prefix_hash},
            )

        return GatewayChatResponse(
            id=req_id,
            created=now_ts,
            # Report the model that actually served the request (failover or
            # rerouting may select a different candidate than requested);
            # accounting above already uses served_model.
            model=served_model,
            choices=[
                {
                    "index": 0,
                    "message": {"role": "assistant", "content": output_text},
                    "finish_reason": "stop",
                }
            ],
            usage={
                "prompt_tokens": record.optimized_input_tokens,
                "completion_tokens": record.completion_tokens,
                "total_tokens": record.actual_billed_tokens,
            },
            cached=False,
            tokens_saved=record.tokens_saved,
            reduction_percentage=record.reduction_percentage,
            provider_cache=provider_cache_meta,
        )

    async def chat_completions_stream(
        self,
        tenant_id: str,
        request: GatewayChatRequest,
        raw_request: Any = None,
        correlation_id: str | None = None,
    ) -> AsyncGenerator[str, None]:
        """Stream OpenAI-compatible chat completion chunks via SSE."""
        # 1. Quota Pre-check
        allowed, error_msg = await self.quota_mgr.check_quota(tenant_id)
        if not allowed:
            err_payload = {
                "error": {
                    "message": error_msg or "Token budget quota exceeded",
                    "type": "insufficient_quota",
                    "param": None,
                    "code": "quota_exceeded",
                }
            }
            yield f"data: {json.dumps(err_payload)}\n\n"
            return

        req_id = f"chatcmpl-{uuid.uuid4().hex[:12]}"
        now_ts = int(time.time())

        # Extract last user message for display/optimization
        last_user_msg = (
            next(
                (
                    m.content
                    for m in reversed(request.messages)
                    if m.role == "user" and m.content
                ),
                "",
            )
            or ""
        )
        # Compute canonical model-visible input envelope tokens across all dimensions
        raw_input_tokens = TokenAccounting.calculate_envelope_tokens(
            messages=request.messages,
            tools=request.tools,
            model=request.model,
        )

        # Build generation-relevant fields for canonical cache identity
        system_instructions = "\n".join(
            m.content or "" for m in request.messages if m.role == "system"
        )
        messages_as_dicts: list[dict[str, Any]] = [
            _message_to_cache_dict(m) for m in request.messages
        ]
        generation_params = {
            "temperature": request.temperature,
            "max_tokens": request.max_tokens,
        }
        provider = get_provider_registry().resolve_provider_name_for_model(
            request.model
        )

        # 2. Tier 1 Exact Match Cache (stream instant chunks)
        cache_entry = await self.cache_mgr.get(
            last_user_msg,
            tenant_id=tenant_id,
            model=request.model,
            provider=provider,
            system_instructions=system_instructions,
            messages=messages_as_dicts,
            tools=request.tools,
            response_format=request.response_format,
            generation_params=generation_params,
            exact_only=True,
        )
        if cache_entry is not None:
            # Output Guardrail leak check on cached response (OPS-03)
            from app.guardrails import GuardrailsEngine
            from app.telemetry.metrics import metrics

            sanitized_cached, cache_leaked = (
                GuardrailsEngine.inspect_and_sanitize_output(
                    cache_entry.response, tenant_id
                )
            )
            if cache_leaked:
                metrics.record_security_incident("OUTPUT_DATA_LEAKAGE", tenant_id)
                err_payload = {
                    "error": {
                        "message": "Output blocked due to security data leakage policy violation.",
                        "type": "security_violation",
                    }
                }
                yield f"data: {json.dumps(err_payload)}\n\n"
                yield "data: [DONE]\n\n"
                return
            words = sanitized_cached.split(" ")
            for i, word in enumerate(words):
                if raw_request and await raw_request.is_disconnected():
                    return
                delta_content = word if i == 0 else f" {word}"
                chunk = {
                    "id": req_id,
                    "object": "chat.completion.chunk",
                    "created": now_ts,
                    "model": request.model,
                    "choices": [
                        {
                            "index": 0,
                            "delta": {"content": delta_content},
                            "finish_reason": None,
                        }
                    ],
                }
                yield f"data: {json.dumps(chunk)}\n\n"
                await asyncio.sleep(0.002)

            final_chunk = {
                "id": req_id,
                "object": "chat.completion.chunk",
                "created": now_ts,
                "model": request.model,
                "choices": [
                    {
                        "index": 0,
                        "delta": {},
                        "finish_reason": "stop",
                    }
                ],
            }
            yield f"data: {json.dumps(final_chunk)}\n\n"
            yield "data: [DONE]\n\n"

            est_completion = max(1, estimate_tokens(cache_entry.response))
            record = TokenAccounting.record_transaction(
                request_id=req_id,
                tenant_id=tenant_id,
                model=request.model,
                raw_input_tokens=raw_input_tokens,
                optimized_input_tokens=0,
                completion_tokens=est_completion,
                cache_hit=True,
                cache_type=cache_entry.cache_type or "exact",
            )
            await self.quota_mgr.record_tokens_saved(tenant_id, record.tokens_saved)
            return

        # 3. Model Generation via Provider Stream or Fallback
        compiler = get_two_zone_compiler()
        compiled = compiler.partition_messages(request.messages)

        from app.core.llm_provider import call_upstream_llm

        output_text = await call_upstream_llm(
            prompt=last_user_msg,
            tenant_id=tenant_id,
            model=request.model,
            temperature=request.temperature,
            max_tokens=request.max_tokens,
            compiled_prompt=compiled,
            tools=request.tools,
            messages=request.messages,
            correlation_id=correlation_id,
        )
        if not output_text:
            output_text = (
                f"[JakeAI Gateway Stream via {request.model}]\n"
                f"Processed query: {last_user_msg[:120]}"
            )

        # Output Inspection & Leakage Blocking (TASK OPS-03)
        from app.guardrails import GuardrailsEngine
        from app.telemetry.metrics import metrics

        sanitized_output, leak_detected = GuardrailsEngine.inspect_and_sanitize_output(
            output_text, tenant_id
        )
        if leak_detected:
            metrics.record_security_incident("OUTPUT_DATA_LEAKAGE", tenant_id)
            err_payload = {
                "error": {
                    "message": "Output blocked due to security data leakage policy violation.",
                    "type": "security_violation",
                }
            }
            yield f"data: {json.dumps(err_payload)}\n\n"
            yield "data: [DONE]\n\n"
            return
        output_text = sanitized_output

        # Stream words as SSE chunks
        words = output_text.split(" ")
        streamed_words: list[str] = []
        try:
            for i, word in enumerate(words):
                if raw_request and await raw_request.is_disconnected():
                    break
                delta_content = word if i == 0 else f" {word}"
                streamed_words.append(delta_content)
                chunk = {
                    "id": req_id,
                    "object": "chat.completion.chunk",
                    "created": now_ts,
                    "model": request.model,
                    "choices": [
                        {
                            "index": 0,
                            "delta": {"content": delta_content},
                            "finish_reason": None,
                        }
                    ],
                }
                yield f"data: {json.dumps(chunk)}\n\n"
                await asyncio.sleep(0.002)

            final_chunk = {
                "id": req_id,
                "object": "chat.completion.chunk",
                "created": now_ts,
                "model": request.model,
                "choices": [
                    {
                        "index": 0,
                        "delta": {},
                        "finish_reason": "stop",
                    }
                ],
            }
            yield f"data: {json.dumps(final_chunk)}\n\n"
            yield "data: [DONE]\n\n"
        finally:
            # Deduct usage & populate cache even on disconnect
            completion_tokens = max(1, estimate_tokens("".join(streamed_words)))
            record = TokenAccounting.record_transaction(
                request_id=req_id,
                tenant_id=tenant_id,
                model=request.model,
                raw_input_tokens=raw_input_tokens,
                optimized_input_tokens=raw_input_tokens,
                completion_tokens=completion_tokens,
                cache_hit=False,
                cache_type="none",
            )
            await self.quota_mgr.record_usage(
                tenant_id=tenant_id,
                prompt_tokens=record.optimized_input_tokens,
                completion_tokens=record.completion_tokens,
            )
            if len(streamed_words) == len(words):
                await self.cache_mgr.set(
                    prompt=last_user_msg,
                    tenant_id=tenant_id,
                    response=output_text,
                    model=request.model,
                    provider=provider,
                    system_instructions=system_instructions,
                    messages=messages_as_dicts,
                    tools=request.tools,
                    response_format=request.response_format,
                    generation_params=generation_params,
                )


_quota_manager: QuotaManager | None = None
_gateway_proxy: GatewayInferenceProxy | None = None


def get_quota_manager() -> QuotaManager:
    """Singleton getter for QuotaManager."""
    global _quota_manager
    if _quota_manager is None:
        _quota_manager = QuotaManager()
    return _quota_manager


def get_gateway_proxy() -> GatewayInferenceProxy:
    """Singleton getter for GatewayInferenceProxy."""
    global _gateway_proxy
    if _gateway_proxy is None:
        _gateway_proxy = GatewayInferenceProxy(get_quota_manager())
    return _gateway_proxy
