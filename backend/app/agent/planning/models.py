"""Models for bounded planning and action selection."""

from __future__ import annotations

from enum import StrEnum
from typing import Any

from pydantic import BaseModel, Field


class PlanStepStatus(StrEnum):
    """Execution status of an individual step in an agent plan."""

    PENDING = "pending"
    RUNNING = "running"
    COMPLETED = "completed"
    FAILED = "failed"
    WAITING_APPROVAL = "waiting_approval"


class PlanStep(BaseModel):
    """Discrete planned milestone or operation."""

    step_id: str
    description: str
    tool_name: str | None = None
    tool_args: dict[str, Any] = Field(default_factory=dict)
    status: PlanStepStatus = Field(default=PlanStepStatus.PENDING)
    observation: str | None = None
    error: str | None = None


class Plan(BaseModel):
    """High-level structured plan decomposing an overarching goal."""

    plan_id: str
    goal: str
    steps: list[PlanStep] = Field(default_factory=list)
    current_step_index: int = 0
    completed: bool = False


class NextActionType(StrEnum):
    """Type of action determined by the planner for the next execution cycle."""

    TOOL_CALL = "tool_call"
    FINISH = "finish"
    REQUEST_APPROVAL = "request_approval"
    REPLAN = "replan"
    FAIL = "fail"


class NextAction(BaseModel):
    """Action selected by the bounded planner."""

    action_type: NextActionType
    tool_name: str | None = None
    tool_args: dict[str, Any] = Field(default_factory=dict)
    thought: str = ""
    final_output: str | None = None
    error: str | None = None
