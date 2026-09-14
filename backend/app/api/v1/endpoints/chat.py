"""Chat and Server-Sent Events (SSE) streaming endpoints with LangGraph integration."""

import asyncio
import logging
import time
import uuid
from collections.abc import AsyncGenerator
from typing import Any

from fastapi import APIRouter, Depends, HTTPException, Request, status
from fastapi.responses import StreamingResponse
from pydantic import BaseModel, Field, model_validator

from app.agents import stream_multi_agent_workflow
from app.core.config import get_settings
from app.core.context import TenantContext
from app.core.rate_limiter import enforce_rate_limit
from app.core.security import get_current_tenant
from app.core.sse import format_sse_event, streaming_sse_headers
from app.finops.budget import QuotaReservation, get_budget_manager
from app.finops.pricing import calculate_baseline_cost
from app.finops.service import get_finops_service
from app.guardrails import GuardrailsEngine
from app.optimizer.semantic_cache import get_semantic_cache_manager
from app.optimizer.token_accounting import TokenAccounting
from app.optimizer.token_pruner import estimate_tokens
from app.providers.errors import sanitize_error_message
from app.telemetry.metrics import metrics

logger = logging.getLogger(__name__)

router = APIRouter()


class ChatStreamRequest(BaseModel):
    """Payload model for chat streaming requests supporting both prompt and query aliases."""

    prompt: str = Field(
        default="",
        max_length=8000,
        description="User question or financial prompt",
    )
    query: str | None = Field(
        default=None,
        max_length=8000,
        description="Alias for prompt used by frontend widget",
    )
    conversation_id: str | None = Field(
        default=None,
        max_length=128,
        description="Optional conversation thread ID",
    )
    parameters: dict[str, Any] = Field(
        default_factory=dict,
        description="Optional model execution parameters",
    )

    @model_validator(mode="before")
    @classmethod
    def harmonize_prompt_and_query(cls, data: Any) -> Any:
        """Reconcile prompt and query aliases."""
        if isinstance(data, dict):
            p = data.get("prompt")
            q = data.get("query")
            if not p and q:
                data["prompt"] = q
            elif p and not q:
                data["query"] = p
        return data

    @model_validator(mode="after")
    def validate_content_not_empty(self) -> "ChatStreamRequest":
        """Ensure resolved prompt is not empty."""
        if not self.prompt.strip():
            raise ValueError("Prompt or query must not be empty.")
        return self


def _format_sse_event(event: str, data: dict[str, Any]) -> str:
    """Format structured payload into W3C Server-Sent Event frame."""
    return format_sse_event(event, data)


async def _settle_stream_finops(
    record: Any,
    *,
    cache_hit: bool,
    cache_type: str,
    telemetry: Any | None,
    reservation: QuotaReservation | None,
) -> None:
    """Single FinOps settlement authority for the chat SSE stream (R-LOGIC-03).

    Records the per-request ledger entry (cache hit or upstream inference) and
    settles the tenant budget exactly once — finalizing the pre-flight
    reservation when present, else settling absolutely. Failures are logged,
    never raised: settlement must not break an in-flight stream.
    """
    try:
        svc = get_finops_service()
        if cache_hit:
            if reservation is not None:
                await get_budget_manager().finalize_reservation(reservation, 0, 0.0)
            await svc.record_cache_hit(
                request_id=record.request_id,
                tenant_id=record.tenant_id,
                model=record.model,
                raw_tokens=record.raw_input_tokens,
                output_tokens=record.completion_tokens,
                cache_type=cache_type,
            )
            return

        provider_usage = None
        provider = "langgraph"
        cache_write_tokens = 0
        if telemetry is not None:
            provider_usage = (
                telemetry.model_dump()
                if hasattr(telemetry, "model_dump")
                else telemetry
            )
            provider = getattr(telemetry, "provider", None) or provider
            cache_write_tokens = int(getattr(telemetry, "cache_write_tokens", 0) or 0)
        await svc.record_upstream_inference(
            request_id=record.request_id,
            tenant_id=record.tenant_id,
            provider=provider,
            model=record.model,
            raw_tokens=record.raw_input_tokens,
            optimized_tokens=record.optimized_input_tokens,
            output_tokens=record.completion_tokens,
            provider_usage=provider_usage,
            provider_cached_tokens=record.provider_cached_input_tokens,
            provider_cache_write_tokens=cache_write_tokens,
            reservation=reservation,
            metadata={"route": "chat_stream"},
        )
    except Exception:
        logger.exception(
            "FinOps settlement failed for stream request %s (tenant %s)",
            record.request_id,
            record.tenant_id,
        )


_semantic_cache = get_semantic_cache_manager()


async def generate_chat_stream(
    prompt: str,
    context: TenantContext,
    conversation_id: str,
    request: Request | None = None,
    parameters: dict[str, Any] | None = None,
    reservation: QuotaReservation | None = None,
) -> AsyncGenerator[str, None]:
    """Stream real-time LangGraph multi-agent events via SSE with guardrails & caching.

    When a quota reservation is supplied (created by the HTTP endpoint), every
    terminal path finalizes it — refunded on pre-inference exits, trued up to
    actual usage after inference (R-LOGIC-03 exactly-once settlement).
    """
    start_time = time.time()
    settings = get_settings()
    metrics.stream_started()

    # 1. Perimeter Input Guardrail Check
    guard_decision = GuardrailsEngine.inspect_input(prompt)
    if not guard_decision.allowed:
        # Nothing was sent upstream: release the reservation in full.
        if reservation is not None:
            try:
                await get_budget_manager().finalize_reservation(reservation, 0, 0.0)
            except Exception:
                logger.exception(
                    "Reservation refund failed for stream %s", conversation_id
                )
        metrics.stream_completed(round((time.time() - start_time) * 1000, 2))
        yield _format_sse_event(
            "error",
            {
                "conversation_id": conversation_id,
                "error": "Guardrail violation",
                "detail": guard_decision.reason,
                "mascot_state": "alert",
            },
        )
        return

    # 2. PII Redaction & Model-Visible Request Envelope Accounting
    sanitized_prompt, _ = GuardrailsEngine.redact_pii(prompt)
    params = parameters or {}
    # The absent-model default must name the model that actually serves the
    # request (the dispatcher's default), not a fictional "default" label —
    # the label keys the response cache and prices token accounting.
    model_name = params.get("model") or "gemini-1.5-flash"
    system_instruction = (
        params.get("system_instruction")
        or params.get("system_prompt")
        or "You are JakeAI, a universal AI engineering and financial assistant."
    )
    history_messages: list[Any] = params.get("messages", [])
    tool_schemas: list[dict[str, Any]] | None = params.get("tools")
    if not tool_schemas:
        try:
            from app.agent.tools.registry import get_tool_registry

            discovered = get_tool_registry().discover(
                context.roles, context.permissions
            )
            if discovered:
                tool_schemas = [
                    t.to_dict()
                    if hasattr(t, "to_dict")
                    else {"name": t.name, "description": t.description}
                    for t in discovered
                ]
        except Exception:
            tool_schemas = None

    rag_context = params.get("rag_context")
    dynamic_context = params.get("dynamic_context")

    raw_prompt_tokens = TokenAccounting.calculate_envelope_tokens(
        messages=history_messages,
        tools=tool_schemas,
        system_instruction=system_instruction,
        user_query=sanitized_prompt,
        dynamic_context=dynamic_context,
        rag_context=rag_context,
        model=model_name,
    )

    # 2.1 Dynamic Context & RAG Optimization on Live Path (COST-06)
    from app.optimizer.context_optimizer import WorkloadType, get_context_optimizer

    ctx_optimizer = get_context_optimizer()
    optimized_dynamic_context = dynamic_context
    optimized_rag_context = rag_context

    if dynamic_context:
        opt_dyn = ctx_optimizer.optimize_dynamic_context(
            dynamic_context=str(dynamic_context),
            user_query=sanitized_prompt,
        )
        optimized_dynamic_context = (
            opt_dyn.content if not opt_dyn.fallback_used else dynamic_context
        )
        params["dynamic_context"] = optimized_dynamic_context

    if rag_context:
        opt_rag = ctx_optimizer.optimize_dynamic_context(
            dynamic_context=str(rag_context),
            user_query=sanitized_prompt,
            workload_type=WorkloadType.RAG,
        )
        optimized_rag_context = (
            opt_rag.content if not opt_rag.fallback_used else rag_context
        )
        params["rag_context"] = optimized_rag_context

    optimized_prompt_tokens = TokenAccounting.calculate_envelope_tokens(
        messages=history_messages,
        tools=tool_schemas,
        system_instruction=system_instruction,
        user_query=sanitized_prompt,
        dynamic_context=optimized_dynamic_context,
        rag_context=optimized_rag_context,
        model=model_name,
    )
    final_response: str = ""
    accounting_recorded = False
    provider_telemetry: Any | None = None
    model_used: str | None = None

    try:
        # 3. Initial Handshake & Context Acknowledgment
        yield _format_sse_event(
            "status",
            {
                "phase": "initialized",
                "conversation_id": conversation_id,
                "tenant_id": context.tenant_id,
                "user_id": context.user_id,
                "mascot_state": "thinking",
                "timestamp": time.time(),
            },
        )
        await asyncio.sleep(0.01)

        # 4. Check Semantic Cache (Tier 1 & Tier 2) - bypassed ONLY if edge proxy evaluated with valid secret (Invariant 4)
        from app.core.security import verify_internal_perimeter_secret

        is_edge_forwarded = bool(request and verify_internal_perimeter_secret(request))
        cached_entry = (
            None
            if is_edge_forwarded
            else await _semantic_cache.get(
                prompt=sanitized_prompt,
                tenant_id=context.tenant_id,
                provider=params.get("provider", "openai"),
                model=model_name,
                system_instructions=system_instruction,
                messages=history_messages,
                tools=tool_schemas,
                response_format=params.get("response_format"),
                generation_params=params.get("generation_params"),
                rag_context=optimized_rag_context,
                dynamic_context=optimized_dynamic_context,
            )
        )
        if cached_entry:
            yield _format_sse_event(
                "status",
                {
                    "node": "semantic_cache",
                    "phase": "cache_hit",
                    "mascot_state": "success",
                    "message": f"Retrieved from {cached_entry.cache_type} cache.",
                },
            )
            words = cached_entry.response.split(" ")
            for i, word in enumerate(words):
                if request and await request.is_disconnected():
                    metrics.record_stream_cancellation(
                        "/api/v1/chat/stream", reason="client_disconnect"
                    )
                    return
                delta = word if i == 0 else f" {word}"
                yield _format_sse_event(
                    "token",
                    {
                        "delta": delta,
                        "token": delta,
                        "content": delta,
                        "conversation_id": conversation_id,
                    },
                )
                await asyncio.sleep(0.002)

            est_comp = max(1, estimate_tokens(cached_entry.response))
            record = TokenAccounting.record_transaction(
                request_id=f"stream-{conversation_id}",
                tenant_id=context.tenant_id,
                model=model_name,
                raw_input_tokens=raw_prompt_tokens,
                optimized_input_tokens=0,
                completion_tokens=est_comp,
                cache_hit=True,
                cache_type=cached_entry.cache_type or "exact",
            )
            accounting_recorded = True
            await _settle_stream_finops(
                record,
                cache_hit=True,
                cache_type=cached_entry.cache_type or "exact",
                telemetry=None,
                reservation=reservation,
            )
            yield _format_sse_event(
                "telemetry",
                {
                    "baseline_tokens": raw_prompt_tokens + est_comp,
                    "billed_tokens": record.actual_billed_tokens,
                    "tokens_saved": record.tokens_saved,
                    "reduction_rate": round(record.reduction_percentage / 100.0, 4),
                    "cache_hit": cached_entry.cache_type or "exact",
                },
            )

            elapsed_ms = round((time.time() - start_time) * 1000, 2)
            metrics.stream_completed(elapsed_ms)
            yield _format_sse_event(
                "done",
                {
                    "conversation_id": conversation_id,
                    "tenant_id": context.tenant_id,
                    "elapsed_ms": elapsed_ms,
                    "mascot_state": cached_entry.mascot_state,
                    "citations": cached_entry.citations,
                    "cache_hit": cached_entry.cache_type,
                },
            )
            return

        citations: list[dict[str, Any]] = []
        final_mascot_state: str = "idle"
        has_tool_execution = False

        # 5. Real-time LangGraph Event Stream
        async for event in stream_multi_agent_workflow(
            sanitized_prompt, context, conversation_id, model=model_name
        ):
            if event.get("provider_telemetry"):
                provider_telemetry = event["provider_telemetry"]
            if event.get("model_used"):
                model_used = event["model_used"]

            # Check for Bounded Stream Timeout
            if (time.time() - start_time) > settings.STREAM_TIMEOUT_SECONDS:
                # Workflow execution already consumed upstream tokens: finalize
                # accounting exactly like the disconnect/failure paths (the
                # former silent return skipped settlement entirely).
                if not accounting_recorded:
                    comp_tokens = (
                        max(1, estimate_tokens(final_response)) if final_response else 0
                    )
                    record = TokenAccounting.record_transaction(
                        request_id=f"stream-{conversation_id}",
                        tenant_id=context.tenant_id,
                        model=model_used or model_name,
                        raw_input_tokens=raw_prompt_tokens,
                        optimized_input_tokens=optimized_prompt_tokens,
                        completion_tokens=comp_tokens,
                        cache_hit=False,
                        cache_type="none",
                        provider_telemetry=provider_telemetry,
                    )
                    accounting_recorded = True
                    await _settle_stream_finops(
                        record,
                        cache_hit=False,
                        cache_type="none",
                        telemetry=provider_telemetry,
                        reservation=reservation,
                    )
                yield _format_sse_event(
                    "error",
                    {
                        "conversation_id": conversation_id,
                        "error": "Stream timeout",
                        "detail": f"Stream exceeded maximum duration of {settings.STREAM_TIMEOUT_SECONDS}s",
                        "mascot_state": "alert",
                    },
                )
                metrics.record_stream_cancellation(
                    "/api/v1/chat/stream", reason="stream_timeout"
                )
                return

            # Check if client disconnected to prevent wasted compute & finalize accounting
            if request and await request.is_disconnected():
                metrics.record_stream_cancellation(
                    "/api/v1/chat/stream", reason="client_disconnect"
                )
                if not accounting_recorded:
                    comp_tokens = (
                        max(1, estimate_tokens(final_response)) if final_response else 0
                    )
                    record = TokenAccounting.record_transaction(
                        request_id=f"stream-{conversation_id}",
                        tenant_id=context.tenant_id,
                        model=model_used or model_name,
                        raw_input_tokens=raw_prompt_tokens,
                        optimized_input_tokens=optimized_prompt_tokens,
                        completion_tokens=comp_tokens,
                        cache_hit=False,
                        cache_type="none",
                        provider_telemetry=provider_telemetry,
                    )
                    accounting_recorded = True
                    await _settle_stream_finops(
                        record,
                        cache_hit=False,
                        cache_type="none",
                        telemetry=provider_telemetry,
                        reservation=reservation,
                    )
                return

            node = event.get("node")
            phase = event.get("workflow_phase", "executing")
            mascot = event.get("mascot_state", "thinking")
            msg = event.get("message", "")

            yield _format_sse_event(
                "status",
                {
                    "node": node,
                    "phase": phase,
                    "mascot_state": mascot,
                    "message": msg,
                },
            )
            await asyncio.sleep(0.005)

            # Emit tool telemetry if tools were executed
            if event.get("tool_calls"):
                has_tool_execution = True
                yield _format_sse_event(
                    "tool_call",
                    {
                        "node": node,
                        "tool_calls": event.get("tool_calls"),
                    },
                )

            if event.get("final_response"):
                final_response = event["final_response"]
                citations = event.get("citations", [])
                final_mascot_state = mascot

        # 6. Output Guardrail & Semantic Cache Population (TASK OPS-03)
        if final_response:
            sanitized_resp, leak_detected = (
                GuardrailsEngine.inspect_and_sanitize_output(
                    final_response, context.tenant_id
                )
            )
            if leak_detected:
                metrics.record_security_incident(
                    "OUTPUT_DATA_LEAKAGE", context.tenant_id
                )
                # Upstream tokens were already consumed: finalize accounting
                # before blocking the response from reaching the client.
                if not accounting_recorded:
                    comp_tokens = max(1, estimate_tokens(final_response))
                    record = TokenAccounting.record_transaction(
                        request_id=f"stream-{conversation_id}",
                        tenant_id=context.tenant_id,
                        model=model_used or model_name,
                        raw_input_tokens=raw_prompt_tokens,
                        optimized_input_tokens=optimized_prompt_tokens,
                        completion_tokens=comp_tokens,
                        cache_hit=False,
                        cache_type="none",
                        provider_telemetry=provider_telemetry,
                    )
                    accounting_recorded = True
                    await _settle_stream_finops(
                        record,
                        cache_hit=False,
                        cache_type="none",
                        telemetry=provider_telemetry,
                        reservation=reservation,
                    )
                yield _format_sse_event(
                    "error",
                    {
                        "conversation_id": conversation_id,
                        "error": "Output leakage detected",
                        "detail": "Response blocked due to sensitive data leakage policy violation.",
                        "mascot_state": "alert",
                    },
                )
                metrics.record_stream_cancellation(
                    "/api/v1/chat/stream", reason="security_leak_blocked"
                )
                return
            final_response = sanitized_resp

            # Store in Semantic Cache only for non-tool knowledge/RAG queries to prevent cross-user leak
            if not has_tool_execution:
                await _semantic_cache.set(
                    prompt=sanitized_prompt,
                    tenant_id=context.tenant_id,
                    response=final_response,
                    citations=citations,
                    mascot_state=final_mascot_state,
                    provider=params.get("provider", "openai"),
                    model=model_name,
                    system_instructions=system_instruction,
                    messages=history_messages,
                    tools=tool_schemas,
                    response_format=params.get("response_format"),
                    generation_params=params.get("generation_params"),
                    rag_context=optimized_rag_context,
                    dynamic_context=optimized_dynamic_context,
                )

            # Stream Real Token Deltas (providing delta, token, and content aliases without artificial sleep)
            if request and await request.is_disconnected():
                metrics.record_stream_cancellation(
                    "/api/v1/chat/stream", reason="client_disconnect"
                )
                if not accounting_recorded:
                    comp_tokens = max(1, estimate_tokens(final_response))
                    record = TokenAccounting.record_transaction(
                        request_id=f"stream-{conversation_id}",
                        tenant_id=context.tenant_id,
                        model=model_used or model_name,
                        raw_input_tokens=raw_prompt_tokens,
                        optimized_input_tokens=optimized_prompt_tokens,
                        completion_tokens=comp_tokens,
                        cache_hit=False,
                        cache_type="none",
                        provider_telemetry=provider_telemetry,
                    )
                    accounting_recorded = True
                    await _settle_stream_finops(
                        record,
                        cache_hit=False,
                        cache_type="none",
                        telemetry=provider_telemetry,
                        reservation=reservation,
                    )
                return

            yield _format_sse_event(
                "token",
                {
                    "delta": final_response,
                    "token": final_response,
                    "content": final_response,
                    "conversation_id": conversation_id,
                },
            )

        # 7. Telemetry & Token Optimization Frame
        comp_tokens = max(1, estimate_tokens(final_response)) if final_response else 10
        record = TokenAccounting.record_transaction(
            request_id=f"stream-{conversation_id}",
            tenant_id=context.tenant_id,
            model=model_used or model_name,
            raw_input_tokens=raw_prompt_tokens,
            optimized_input_tokens=optimized_prompt_tokens,
            completion_tokens=comp_tokens,
            cache_hit=False,
            cache_type="none",
            provider_telemetry=provider_telemetry,
        )
        accounting_recorded = True
        await _settle_stream_finops(
            record,
            cache_hit=False,
            cache_type="none",
            telemetry=provider_telemetry,
            reservation=reservation,
        )
        yield _format_sse_event(
            "telemetry",
            {
                "baseline_tokens": raw_prompt_tokens + comp_tokens,
                "billed_tokens": record.actual_billed_tokens,
                "tokens_saved": record.tokens_saved,
                "reduction_rate": round(record.reduction_percentage / 100.0, 4),
            },
        )

        # 8. Stream Completion Frame with Mascot State
        elapsed_ms = round((time.time() - start_time) * 1000, 2)
        metrics.stream_completed(elapsed_ms)
        yield _format_sse_event(
            "done",
            {
                "conversation_id": conversation_id,
                "tenant_id": context.tenant_id,
                "elapsed_ms": elapsed_ms,
                "mascot_state": final_mascot_state,
                "citations": citations,
                "model": model_used or model_name,
            },
        )
    except asyncio.CancelledError:
        # Client aborted connection: finalize partial token accounting and record telemetry
        metrics.record_stream_cancellation(
            "/api/v1/chat/stream", reason="client_disconnect"
        )
        if not accounting_recorded:
            comp_tokens = (
                max(1, estimate_tokens(final_response)) if final_response else 1
            )
            record = TokenAccounting.record_transaction(
                request_id=f"stream-{conversation_id}",
                tenant_id=context.tenant_id,
                model=model_name,
                raw_input_tokens=raw_prompt_tokens,
                optimized_input_tokens=optimized_prompt_tokens,
                completion_tokens=comp_tokens,
                cache_hit=False,
                cache_type="none",
                provider_telemetry=provider_telemetry,
            )
            accounting_recorded = True
            await _settle_stream_finops(
                record,
                cache_hit=False,
                cache_type="none",
                telemetry=provider_telemetry,
                reservation=reservation,
            )
        return
    except Exception as exc:
        elapsed_ms = round((time.time() - start_time) * 1000, 2)
        metrics.stream_completed(elapsed_ms)
        # A workflow failure still consumed upstream tokens: finalize partial
        # accounting exactly like the disconnect/cancel paths do.
        if not accounting_recorded:
            comp_tokens = (
                max(1, estimate_tokens(final_response)) if final_response else 1
            )
            record = TokenAccounting.record_transaction(
                request_id=f"stream-{conversation_id}",
                tenant_id=context.tenant_id,
                model=model_used or model_name,
                raw_input_tokens=raw_prompt_tokens,
                optimized_input_tokens=optimized_prompt_tokens,
                completion_tokens=comp_tokens,
                cache_hit=False,
                cache_type="none",
                provider_telemetry=provider_telemetry,
            )
            accounting_recorded = True
            await _settle_stream_finops(
                record,
                cache_hit=False,
                cache_type="none",
                telemetry=provider_telemetry,
                reservation=reservation,
            )
        yield _format_sse_event(
            "error",
            {
                "conversation_id": conversation_id,
                "error": "Error during multi-agent workflow execution",
                "detail": sanitize_error_message(str(exc)),
                "mascot_state": "alert",
            },
        )


@router.post(
    "/stream",
    response_class=StreamingResponse,
    status_code=status.HTTP_200_OK,
    summary="Real-time Chat SSE Stream",
    description="Stream real-time multi-agent responses via Server-Sent Events (SSE).",
    tags=["Chat"],
    responses={
        200: {
            "content": {"text/event-stream": {}},
            "description": "Real-time Server-Sent Events (SSE) stream",
        }
    },
)
async def chat_stream_endpoint(
    payload: ChatStreamRequest,
    request: Request,
    context: TenantContext = Depends(get_current_tenant),
) -> StreamingResponse:
    """Enforce security, rate limits, and budget reservation, then start the SSE stream."""
    await enforce_rate_limit(request, context.tenant_id)

    conv_id = payload.conversation_id or f"conv-{uuid.uuid4().hex[:12]}"

    # Atomic budget reservation (R-LOGIC-03): the hard-stop check and the usage
    # increment are one operation, so concurrent streams cannot oversubscribe
    # the tenant's quota/dollar budget via check-then-act interleaving. The
    # generator finalizes (or refunds) the reservation on every terminal path.
    params = payload.parameters or {}
    stream_model = params.get("model") or "gemini-1.5-flash"
    est_input = TokenAccounting.calculate_envelope_tokens(
        messages=params.get("messages", []),
        system_instruction=params.get("system_instruction")
        or params.get("system_prompt"),
        user_query=payload.prompt,
        model=stream_model,
    )
    try:
        est_completion = int(params.get("max_tokens") or 1024)
    except (TypeError, ValueError):
        est_completion = 1024
    est_cost = calculate_baseline_cost(
        model=stream_model,
        raw_input_tokens=est_input,
        output_tokens=est_completion,
    )
    reservation, deny_msg = await get_budget_manager().reserve_budget(
        context.tenant_id,
        estimated_tokens=est_input + est_completion,
        estimated_cost_usd=est_cost,
    )
    if reservation is None:
        raise HTTPException(
            status_code=status.HTTP_429_TOO_MANY_REQUESTS,
            detail=deny_msg or "Token budget quota exceeded",
        )

    return StreamingResponse(
        generate_chat_stream(
            prompt=payload.prompt,
            context=context,
            conversation_id=conv_id,
            request=request,
            parameters=payload.parameters,
            reservation=reservation,
        ),
        media_type="text/event-stream",
        headers=streaming_sse_headers(context),
    )
