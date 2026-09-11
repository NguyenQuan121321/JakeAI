"""Canonical Models for bounded planning and action selection."""

from __future__ import annotations

import uuid
from enum import StrEnum
from typing import Any

from pydantic import BaseModel, Field

from app.agent.domain.contracts import (
    ExecutionPlan,
    StepStatus,
)
from app.agent.domain.contracts import (
    PlanStep as DomainPlanStep,
)

PlanStepStatus = StepStatus


class PlanStep(DomainPlanStep):
    """Discrete planned milestone or operation within a DAG plan."""

    tool_name: str | None = None
    tool_args: dict[str, Any] = Field(default_factory=dict)


class Plan(ExecutionPlan):
    """Structured plan decomposing an overarching goal with DAG dependencies."""

    task_id: str = Field(default_factory=lambda: f"task_{uuid.uuid4().hex[:12]}")
    steps: list[PlanStep] = Field(default_factory=list)  # type: ignore[assignment]
    current_step_index: int = 0
    completed: bool = False

    def is_complete(self) -> bool:
        """Return True if all steps in plan are completed or skipped."""
        complete = bool(self.steps) and all(
            s.status in (StepStatus.COMPLETED, StepStatus.SKIPPED, PlanStepStatus.COMPLETED)
            for s in self.steps
        )
        self.completed = complete
        return complete


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
    target_step_id: str | None = None
    assigned_agent: str | None = None
    selected_model: str | None = None
