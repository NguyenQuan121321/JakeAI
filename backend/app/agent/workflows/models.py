"""Models defining structured workflows and step execution records."""

from __future__ import annotations

import time
from enum import StrEnum
from typing import Any

from pydantic import BaseModel, Field


class StepType(StrEnum):
    """Execution type for a workflow step."""

    MODEL_CALL = "model_call"
    TOOL_CALL = "tool_call"
    CONDITION = "condition"


class WorkflowStepDefinition(BaseModel):
    """Specification of a discrete step in a workflow pipeline."""

    step_id: str
    name: str
    step_type: StepType = StepType.TOOL_CALL
    tool_name: str | None = None
    arguments: dict[str, Any] = Field(default_factory=dict)
    prompt_template: str | None = None


class WorkflowDefinition(BaseModel):
    """Reusable multi-step workflow recipe."""

    workflow_id: str
    name: str
    description: str = ""
    steps: list[WorkflowStepDefinition] = Field(default_factory=list)


class WorkflowExecutionStatus(StrEnum):
    """Execution status of a workflow instance."""

    PENDING = "pending"
    RUNNING = "running"
    PAUSED_APPROVAL = "paused_approval"
    COMPLETED = "completed"
    FAILED = "failed"
    CANCELLED = "cancelled"


class WorkflowExecution(BaseModel):
    """Observable and resumable runtime record of a workflow execution."""

    execution_id: str
    workflow_id: str
    tenant_id: str
    status: WorkflowExecutionStatus = WorkflowExecutionStatus.PENDING
    current_step_index: int = 0
    step_results: dict[str, Any] = Field(default_factory=dict)
    created_at: float = Field(default_factory=time.time)
    updated_at: float = Field(default_factory=time.time)
    error: str | None = None
