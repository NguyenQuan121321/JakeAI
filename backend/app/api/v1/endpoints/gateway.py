"""AI Gateway as a Service REST API endpoints."""

from typing import Any

from fastapi import APIRouter, Depends, HTTPException, Request, status
from fastapi.responses import StreamingResponse
from pydantic import BaseModel, Field

from app.core.context import TenantContext
from app.core.security import get_current_tenant
from app.services.ai_gateway import (
    GatewayChatRequest,
    GatewayChatResponse,
    QuotaStatus,
    get_gateway_proxy,
    get_quota_manager,
)

router = APIRouter()


class UpdateQuotaRequest(BaseModel):
    """Payload to update tenant monthly token quota."""

    new_limit: int = Field(..., ge=10_000, description="New token limit (e.g. 5000000)")


class ModelItem(BaseModel):
    """OpenAI model descriptor."""

    id: str
    object: str = "model"
    created: int = 1700000000
    owned_by: str = "jakeai"


class ModelListResponse(BaseModel):
    """OpenAI-compatible model list response."""

    object: str = "list"
    data: list[ModelItem]


@router.post(
    "/chat/completions",
    response_model=GatewayChatResponse,
    responses={
        200: {
            "content": {
                "application/json": {},
                "text/event-stream": {},
            },
            "description": "OpenAI-compatible chat completion JSON object or Server-Sent Events stream",
        }
    },
)
async def proxy_chat_completions(
    request: GatewayChatRequest,
    raw_request: Request,
    context: TenantContext = Depends(get_current_tenant),
) -> Any:
    """OpenAI-compatible inference proxy with Tier 1 Redis exact caching and quota deduction."""
    from app.guardrails import GuardrailsEngine
    from app.telemetry.metrics import metrics

    # 1. Perimeter Input Guardrail & PII Inspection (OPS-02, OPS-12)
    for msg in reversed(request.messages):
        if msg.role == "user" and msg.content:
            guard_res = GuardrailsEngine.inspect_input(msg.content)
            if not guard_res.allowed:
                metrics.record_security_incident("PROMPT_INJECTION_ATTEMPT", context.tenant_id)
                raise HTTPException(
                    status_code=status.HTTP_400_BAD_REQUEST,
                    detail=f"Safety guardrail violation: {guard_res.reason}",
                )
            masked_content, _ = GuardrailsEngine.redact_pii(msg.content)
            msg.content = masked_content

    proxy = get_gateway_proxy()
    if request.stream:
        return StreamingResponse(
            proxy.chat_completions_stream(
                tenant_id=context.tenant_id,
                request=request,
                raw_request=raw_request,
                correlation_id=context.correlation_id,
            ),
            media_type="text/event-stream",
            headers={
                "Cache-Control": "no-cache",
                "Connection": "keep-alive",
                "X-Accel-Buffering": "no",
                "X-Tenant-ID": context.tenant_id,
                "X-Correlation-ID": context.correlation_id,
            },
        )

    try:
        return await proxy.chat_completions(
            tenant_id=context.tenant_id,
            request=request,
            correlation_id=context.correlation_id,
        )
    except ValueError as exc:
        raise HTTPException(
            status_code=status.HTTP_429_TOO_MANY_REQUESTS,
            detail=str(exc),
        ) from exc


@router.get("/models", response_model=ModelListResponse)
async def list_available_models(
    _context: TenantContext = Depends(get_current_tenant),
) -> Any:
    """Return catalog of available models supported by the AI Gateway."""
    from app.providers.base import ModelCapabilityCatalog

    catalog = ModelCapabilityCatalog.list_all()
    return ModelListResponse(
        object="list",
        data=[ModelItem(id=cap.model, owned_by=cap.provider) for cap in catalog],
    )


@router.get("/quotas", response_model=QuotaStatus)
async def get_tenant_quota(
    context: TenantContext = Depends(get_current_tenant),
) -> Any:
    """Retrieve active period token usage, limits, and budget health."""
    quota_mgr = get_quota_manager()
    return await quota_mgr.get_status(context.tenant_id)


@router.post("/quotas", response_model=QuotaStatus)
async def update_tenant_quota(
    request: UpdateQuotaRequest,
    context: TenantContext = Depends(get_current_tenant),
) -> Any:
    """Configure monthly token quota limit for a tenant."""
    quota_mgr = get_quota_manager()
    await quota_mgr.set_quota_limit(context.tenant_id, request.new_limit)
    return await quota_mgr.get_status(context.tenant_id)
