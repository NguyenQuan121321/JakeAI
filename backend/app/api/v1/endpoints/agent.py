"""JakeAI-Agent Platform REST and Server-Sent Events (SSE) streaming API endpoints."""

from __future__ import annotations

from typing import TYPE_CHECKING, Any

from fastapi import APIRouter, BackgroundTasks, Depends, HTTPException, status
from fastapi.responses import StreamingResponse
from pydantic import BaseModel, Field

from app.agent.approvals.models import ApprovalDecision, ApprovalRequest
from app.agent.runtime.manager import get_agent_manager
from app.agent.state.models import RunState, TaskState
from app.core.security import get_current_tenant

if TYPE_CHECKING:
    from app.core.context import TenantContext

router = APIRouter()


class CreateTaskRequest(BaseModel):
    """Payload to create a new autonomous agent task."""

    goal: str = Field(
        ...,
        min_length=1,
        max_length=10000,
        description="Target objective or problem statement",
    )
    metadata: dict[str, Any] = Field(
        default_factory=dict, description="Arbitrary task context metadata"
    )


class CreateRunRequest(BaseModel):
    """Payload to instantiate an execution run for an existing task."""

    max_iterations: int | None = Field(
        default=None, ge=1, le=50, description="Optional iteration ceiling"
    )
    async_execution: bool = Field(
        default=True, description="Whether to execute in background"
    )


@router.post("/tasks", response_model=TaskState, status_code=status.HTTP_201_CREATED)
async def create_task(
    payload: CreateTaskRequest,
    context: TenantContext = Depends(get_current_tenant),
) -> TaskState:
    """Create a new Agent Task within the authenticated tenant boundary."""
    manager = get_agent_manager()
    return manager.create_task(
        goal=payload.goal,
        tenant_id=context.tenant_id,
        user_id=context.user_id,
        metadata=payload.metadata,
    )


@router.get("/tasks/{task_id}", response_model=TaskState)
async def get_task(
    task_id: str,
    context: TenantContext = Depends(get_current_tenant),
) -> TaskState:
    """Retrieve an existing Agent Task by identifier."""
    manager = get_agent_manager()
    try:
        return manager.get_task(task_id, context.tenant_id)
    except KeyError as exc:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND, detail=str(exc)
        ) from exc
    except PermissionError as exc:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN, detail=str(exc)
        ) from exc


@router.post(
    "/tasks/{task_id}/runs",
    response_model=RunState,
    status_code=status.HTTP_201_CREATED,
)
async def start_run(
    task_id: str,
    payload: CreateRunRequest,
    background_tasks: BackgroundTasks,
    context: TenantContext = Depends(get_current_tenant),
) -> RunState:
    """Create and start an execution run for a task."""
    manager = get_agent_manager()
    try:
        run = manager.create_run(
            task_id=task_id,
            tenant_id=context.tenant_id,
            user_id=context.user_id,
            max_iterations=payload.max_iterations,
        )

        if payload.async_execution:
            background_tasks.add_task(
                manager.execute_run,
                task_id=task_id,
                run_id=run.run_id,
                tenant_id=context.tenant_id,
                user_roles=context.roles,
                user_permissions=context.permissions,
            )
        else:
            await manager.execute_run(
                task_id=task_id,
                run_id=run.run_id,
                tenant_id=context.tenant_id,
                user_roles=context.roles,
                user_permissions=context.permissions,
            )

        return run
    except KeyError as exc:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND, detail=str(exc)
        ) from exc
    except PermissionError as exc:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN, detail=str(exc)
        ) from exc


@router.get("/tasks/{task_id}/runs/{run_id}", response_model=RunState)
async def get_run(
    task_id: str,
    run_id: str,
    context: TenantContext = Depends(get_current_tenant),
) -> RunState:
    """Retrieve run execution status, current iteration, and step history."""
    manager = get_agent_manager()
    try:
        # Validate task ownership first
        manager.get_task(task_id, context.tenant_id)
        return manager.get_run(run_id, context.tenant_id)
    except KeyError as exc:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND, detail=str(exc)
        ) from exc
    except PermissionError as exc:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN, detail=str(exc)
        ) from exc


@router.get(
    "/tasks/{task_id}/runs/{run_id}/events",
    response_class=StreamingResponse,
    responses={
        200: {
            "content": {"text/event-stream": {}},
            "description": "Real-time Server-Sent Events stream of agent execution progress",
        }
    },
)
async def stream_run_events(
    task_id: str,
    run_id: str,
    context: TenantContext = Depends(get_current_tenant),
) -> StreamingResponse:
    """Stream real-time Server-Sent Events (SSE) for an active agent run."""
    manager = get_agent_manager()
    try:
        manager.get_task(task_id, context.tenant_id)
        manager.get_run(run_id, context.tenant_id)
    except KeyError as exc:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND, detail=str(exc)
        ) from exc
    except PermissionError as exc:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN, detail=str(exc)
        ) from exc

    generator = manager.runner.stream_run_events(run_id)
    return StreamingResponse(generator, media_type="text/event-stream")


@router.post("/tasks/{task_id}/runs/{run_id}/cancel", response_model=RunState)
async def cancel_run(
    task_id: str,
    run_id: str,
    context: TenantContext = Depends(get_current_tenant),
) -> RunState:
    """Cooperatively cancel an in-flight execution run."""
    manager = get_agent_manager()
    try:
        return manager.cancel_run(task_id, run_id, context.tenant_id)
    except KeyError as exc:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND, detail=str(exc)
        ) from exc
    except PermissionError as exc:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN, detail=str(exc)
        ) from exc


@router.post(
    "/tasks/{task_id}/runs/{run_id}/approvals/{approval_id}",
    response_model=ApprovalRequest,
)
async def decide_approval(
    task_id: str,
    run_id: str,
    approval_id: str,
    decision: ApprovalDecision,
    context: TenantContext = Depends(get_current_tenant),
) -> ApprovalRequest:
    """Approve or reject a pending dangerous action approval gate."""
    manager = get_agent_manager()
    try:
        appr = await manager.decide_approval(
            task_id=task_id,
            run_id=run_id,
            approval_id=approval_id,
            decision=decision,
            tenant_id=context.tenant_id,
            user_id=context.user_id,
            user_roles=context.roles,
            user_permissions=context.permissions,
        )
        return appr
    except KeyError as exc:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND, detail=str(exc)
        ) from exc
    except PermissionError as exc:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN, detail=str(exc)
        ) from exc
    except ValueError as exc:
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT, detail=str(exc)
        ) from exc


@router.get("/approvals/pending", response_model=list[ApprovalRequest])
async def list_pending_approvals(
    context: TenantContext = Depends(get_current_tenant),
) -> list[ApprovalRequest]:
    """List all pending dangerous action approval requests for the calling tenant."""
    manager = get_agent_manager()
    return manager.approval_manager.get_pending_approvals(context.tenant_id)


@router.get("/metrics")
async def get_agent_metrics(
    context: TenantContext = Depends(get_current_tenant),
) -> dict[str, Any]:
    """Retrieve runtime telemetry snapshot for the agent platform."""
    _ = context
    from app.agent.telemetry import agent_telemetry

    return agent_telemetry.get_snapshot().model_dump()
