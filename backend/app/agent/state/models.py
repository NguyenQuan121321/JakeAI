"""State models for Agent tasks and execution runs."""

from __future__ import annotations

import time
from enum import StrEnum
from typing import Any

from pydantic import BaseModel, Field


class TaskStatus(StrEnum):
    """Lifecycle states of an overarching Agent task."""

    PENDING = "pending"
    RUNNING = "running"
    PAUSED_APPROVAL = "paused_approval"
    COMPLETED = "completed"
    FAILED = "failed"
    CANCELLED = "cancelled"


class RunStatus(StrEnum):
    """Lifecycle states of an individual execution run for a task."""

    CREATED = "created"
    RUNNING = "running"
    PAUSED_APPROVAL = "paused_approval"
    COMPLETED = "completed"
    FAILED = "failed"
    CANCELLED = "cancelled"


class StepExecutionRecord(BaseModel):
    """Observable record of an individual step executed in an agent run."""

    step_number: int = Field(..., ge=0)
    description: str = Field(default="")
    action_type: str = Field(
        ..., description="Action: tool_call, direct_response, approval_request, finish"
    )
    tool_name: str | None = None
    tool_args: dict[str, Any] = Field(default_factory=dict)
    observation: str | None = None
    status: str = Field(default="completed")
    execution_time_ms: float = Field(default=0.0)
    timestamp: float = Field(default_factory=time.time)


class TaskState(BaseModel):
    """Persistent representation of an Agent Task."""

    task_id: str = Field(..., description="Unique task identifier")
    tenant_id: str = Field(..., description="Tenant boundary identifier")
    user_id: str = Field(..., description="User ownership identifier")
    goal: str = Field(..., description="Target objective or problem statement")
    status: TaskStatus = Field(default=TaskStatus.PENDING)
    active_run_id: str | None = None
    created_at: float = Field(default_factory=time.time)
    updated_at: float = Field(default_factory=time.time)
    metadata: dict[str, Any] = Field(default_factory=dict)


class RunState(BaseModel):
    """Persistent and checkpointable state of an active Agent Run."""

    run_id: str = Field(..., description="Unique execution run identifier")
    task_id: str = Field(..., description="Associated parent task identifier")
    tenant_id: str = Field(..., description="Tenant boundary identifier")
    user_id: str = Field(..., description="User ownership identifier")
    status: RunStatus = Field(default=RunStatus.CREATED)
    current_iteration: int = Field(default=0, ge=0)
    max_iterations: int = Field(default=10, ge=1)
    steps: list[StepExecutionRecord] = Field(default_factory=list)
    pending_approval_id: str | None = None
    final_output: str | None = None
    error: str | None = None
    tokens_consumed: int = Field(default=0, ge=0)
    cost_usd: float = Field(default=0.0, ge=0.0)
    created_at: float = Field(default_factory=time.time)
    completed_at: float | None = None
    metadata: dict[str, Any] = Field(default_factory=dict)
