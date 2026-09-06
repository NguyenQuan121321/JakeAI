"""ADR-001 LangGraph Interrupt Checkpoint and Tool Execution Resume Endpoints.

Allows developer workstations to submit client-side tool results (AST search, file diffs,
local unit test outcomes) back to JakeAI without keeping ASGI worker threads blocked.
"""

from __future__ import annotations

from typing import TYPE_CHECKING, Any

from fastapi import APIRouter, Depends, HTTPException, Request, status
from pydantic import BaseModel, Field

from app.core.security import get_current_tenant, verify_internal_perimeter_secret
from app.services.resume_bridge import ResumedExecutionResult, get_resume_bridge

if TYPE_CHECKING:
    from app.core.context import TenantContext

router = APIRouter()


class ToolResultSubmission(BaseModel):
    """Payload submitted by client application upon completing a local tool execution."""

    call_id: str = Field(
        ...,
        min_length=8,
        max_length=128,
        description="Unique tool call execution identifier generated during interrupt()",
    )
    result: dict[str, Any] = Field(
        ...,
        description="Structured tool output (e.g. file contents, AST matches, test outcome)",
    )
    thread_id: str | None = Field(
        default=None,
        max_length=128,
        description="Optional LangGraph thread identifier",
    )
    conversation_id: str | None = Field(
        default=None,
        max_length=128,
        description="Optional conversation identifier",
    )


class InternalResumeSubmission(BaseModel):
    """Payload routed internally by FinnApiGo edge gateway."""

    call_id: str = Field(..., min_length=8, max_length=128)
    tenant_id: str = Field(..., min_length=1, max_length=128)
    result: dict[str, Any] = Field(...)
    thread_id: str | None = Field(default=None)


@router.post("/tool-result", response_model=ResumedExecutionResult)
async def submit_tool_result(
    payload: ToolResultSubmission,
    context: TenantContext = Depends(get_current_tenant),
) -> ResumedExecutionResult:
    """Submit local developer workstation tool execution outcome and resume agent workflow."""
    bridge = get_resume_bridge()
    try:
        return await bridge.resume_checkpoint(
            call_id=payload.call_id,
            result_payload=payload.result,
            tenant_id=context.tenant_id,
        )
    except KeyError as exc:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=str(exc),
        ) from exc
    except ValueError as exc:
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail=str(exc),
        ) from exc
    except PermissionError as exc:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail=str(exc),
        ) from exc


@router.post(
    "/resume",
    response_model=ResumedExecutionResult,
    include_in_schema=True,
    tags=["Internal Coding Bridge"],
)
async def internal_resume_endpoint(
    payload: InternalResumeSubmission,
    request: Request,
) -> ResumedExecutionResult:
    """Internal perimeter resume bridge invoked by FinnApiGo with Invariant 4 authentication."""
    if not verify_internal_perimeter_secret(request):
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Forbidden: Perimeter bypass rejected (missing or invalid internal secret)",
        )

    bridge = get_resume_bridge()
    try:
        return await bridge.resume_checkpoint(
            call_id=payload.call_id,
            result_payload=payload.result,
            tenant_id=payload.tenant_id,
        )
    except KeyError as exc:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=str(exc),
        ) from exc
    except ValueError as exc:
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail=str(exc),
        ) from exc
    except PermissionError as exc:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail=str(exc),
        ) from exc
