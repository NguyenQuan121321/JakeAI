"""JakeAI-Agent Platform REST and Server-Sent Events (SSE) streaming API endpoints."""

from __future__ import annotations

from typing import TYPE_CHECKING, Any

from fastapi import APIRouter, BackgroundTasks, Depends, HTTPException, status
from fastapi.responses import StreamingResponse
from pydantic import BaseModel, Field

from app.agent.approvals.authority import (
    ApprovalAuthority,
    BoundConsume,
    BoundDecision,
    SafeApprovalProposal,
)
from app.agent.approvals.models import ApprovalRequest
from app.agent.runtime.manager import get_agent_manager
from app.agent.state.models import RunState, RunStatus, TaskState
from app.agent.telemetry import AgentMetricsSnapshot, agent_telemetry
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
    approval: SafeApprovalProposal | None = None


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
            roles=context.roles,
            permissions=context.permissions,
            correlation_id=context.correlation_id,
        )

        if payload.approval is not None:
            authority = ApprovalAuthority()
            try:
                record = await authority.create(task_id, run.run_id, payload.approval)
            finally:
                await authority.close()
            run.status = RunStatus.RUNNING
            run.status = RunStatus.WAITING_APPROVAL
            run.pending_approval_id = record["approval_id"]
            # This branch never schedules the general execution loop. Its sole
            # controlled effect is durable publication through consume below.
            return run

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
    except ValueError as exc:
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT, detail=str(exc)
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
        return await manager.get_or_restore_run(run_id, context.tenant_id)
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
        run = manager.get_run(run_id, context.tenant_id)
    except KeyError as exc:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND, detail=str(exc)
        ) from exc
    except PermissionError as exc:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN, detail=str(exc)
        ) from exc

    generator = manager.runner.stream_run_events(run_id, run=run)
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
        run = manager.get_run(run_id, context.tenant_id)
        if run.pending_approval_id and run.status == RunStatus.WAITING_APPROVAL:
            authority = ApprovalAuthority()
            try:
                await authority.cancel(
                    context.tenant_id,
                    task_id,
                    run_id,
                    run.pending_approval_id,
                    permission="agent:write",
                )
            finally:
                await authority.close()
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
)
async def decide_approval(
    task_id: str,
    run_id: str,
    approval_id: str,
    decision: BoundDecision,
    context: TenantContext = Depends(get_current_tenant),
) -> dict[str, Any]:
    """Decide only the assigned, immutable safe action in the durable store."""
    authority = ApprovalAuthority()
    try:
        return await authority.decide(
            context.tenant_id, task_id, run_id, approval_id, decision
        )
    finally:
        await authority.close()


@router.get("/tasks/{task_id}/runs/{run_id}/approvals/{approval_id}")
async def get_bound_approval(
    task_id: str,
    run_id: str,
    approval_id: str,
    context: TenantContext = Depends(get_current_tenant),
) -> dict[str, Any]:
    authority = ApprovalAuthority()
    try:
        return await authority.get(context.tenant_id, task_id, run_id, approval_id)
    finally:
        await authority.close()


@router.post("/tasks/{task_id}/runs/{run_id}/approvals/{approval_id}/consume")
async def consume_bound_approval(
    task_id: str,
    run_id: str,
    approval_id: str,
    payload: BoundConsume,
    context: TenantContext = Depends(get_current_tenant),
) -> dict[str, Any]:
    authority = ApprovalAuthority()
    try:
        return await authority.consume(
            context.tenant_id, task_id, run_id, approval_id, payload
        )
    finally:
        await authority.close()


@router.post("/tasks/{task_id}/runs/{run_id}/approvals/{approval_id}/cancel")
async def cancel_bound_approval(
    task_id: str,
    run_id: str,
    approval_id: str,
    context: TenantContext = Depends(get_current_tenant),
) -> dict[str, Any]:
    authority = ApprovalAuthority()
    try:
        return await authority.cancel(context.tenant_id, task_id, run_id, approval_id)
    finally:
        await authority.close()


@router.get("/approvals/pending", response_model=list[ApprovalRequest])
async def list_pending_approvals(
    context: TenantContext = Depends(get_current_tenant),
) -> list[ApprovalRequest]:
    """List all pending dangerous action approval requests for the calling tenant."""
    manager = get_agent_manager()
    return manager.approval_manager.get_pending_approvals(context.tenant_id)


@router.get("/metrics", response_model=AgentMetricsSnapshot)
async def get_agent_metrics(
    context: TenantContext = Depends(get_current_tenant),
) -> AgentMetricsSnapshot:
    """Retrieve runtime telemetry snapshot for the agent platform."""
    _ = context
    return agent_telemetry.get_snapshot()
