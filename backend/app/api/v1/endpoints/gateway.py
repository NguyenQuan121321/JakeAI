"""AI Gateway as a Service REST API endpoints."""

from typing import Any

from fastapi import APIRouter, Depends, HTTPException, status
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


@router.post("/chat/completions", response_model=GatewayChatResponse)
async def proxy_chat_completions(
    request: GatewayChatRequest,
    context: TenantContext = Depends(get_current_tenant),
) -> Any:
    """OpenAI-compatible inference proxy with Tier 1 Redis exact caching and quota deduction."""
    proxy = get_gateway_proxy()
    try:
        return await proxy.chat_completions(
            tenant_id=context.tenant_id,
            request=request,
        )
    except ValueError as exc:
        raise HTTPException(
            status_code=status.HTTP_429_TOO_MANY_REQUESTS,
            detail=str(exc),
        ) from exc


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
