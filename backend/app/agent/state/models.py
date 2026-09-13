"""State models for Agent tasks and execution runs."""

from __future__ import annotations

import time
from enum import StrEnum
from typing import TYPE_CHECKING, Any

from pydantic import BaseModel, Field, PrivateAttr, model_validator

if TYPE_CHECKING:
    from collections.abc import Mapping


class TaskStatus(StrEnum):
    """Lifecycle states of an overarching Agent task."""

    PENDING = "pending"
    PLANNING = "planning"
    READY = "ready"
    RUNNING = "running"
    EXECUTING = "executing"
    PAUSED_APPROVAL = "paused_approval"
    WAITING_APPROVAL = "waiting_approval"
    VERIFYING = "verifying"
    REPLANNING = "replanning"
    COMPLETED = "completed"
    FAILED = "failed"
    CANCELLED = "cancelled"
    REJECTED = "rejected"
    TIMEOUT = "timeout"

    @property
    def is_terminal(self) -> bool:
        """Return True if this status is terminal."""
        return self in (
            TaskStatus.COMPLETED,
            TaskStatus.FAILED,
            TaskStatus.CANCELLED,
            TaskStatus.REJECTED,
            TaskStatus.TIMEOUT,
        )


class RunStatus(StrEnum):
    """Lifecycle states of an individual execution run for a task (Phase 3 Canonical State)."""

    CREATED = "created"
    PLANNING = "planning"
    READY = "ready"
    RUNNING = "running"
    EXECUTING = "executing"
    PAUSED_APPROVAL = "paused_approval"
    WAITING_APPROVAL = "waiting_approval"
    VERIFYING = "verifying"
    REPLANNING = "replanning"
    COMPLETED = "completed"
    FAILED = "failed"
    CANCELLED = "cancelled"
    REJECTED = "rejected"
    TIMEOUT = "timeout"

    @property
    def is_terminal(self) -> bool:
        """Return True if this status is terminal."""
        return self in (
            RunStatus.COMPLETED,
            RunStatus.FAILED,
            RunStatus.CANCELLED,
            RunStatus.REJECTED,
            RunStatus.TIMEOUT,
        )

    @property
    def is_success(self) -> bool:
        """Return True if status indicates terminal success."""
        return self == RunStatus.COMPLETED


# Canonical run state machine (R-LOGIC-01). Keys are source states; values are
# the successors the machine may enter. Terminal states have no successors.
RUN_TRANSITIONS: dict[RunStatus, frozenset[RunStatus]] = {
    RunStatus.CREATED: frozenset(
        {
            RunStatus.PLANNING,
            RunStatus.READY,
            RunStatus.RUNNING,
            RunStatus.FAILED,
            RunStatus.CANCELLED,
        }
    ),
    RunStatus.PLANNING: frozenset(
        {RunStatus.READY, RunStatus.RUNNING, RunStatus.FAILED, RunStatus.CANCELLED}
    ),
    RunStatus.READY: frozenset(
        {RunStatus.RUNNING, RunStatus.EXECUTING, RunStatus.FAILED, RunStatus.CANCELLED}
    ),
    RunStatus.RUNNING: frozenset(
        {
            RunStatus.EXECUTING,
            RunStatus.WAITING_APPROVAL,
            RunStatus.PAUSED_APPROVAL,
            RunStatus.VERIFYING,
            RunStatus.COMPLETED,
            RunStatus.FAILED,
            RunStatus.CANCELLED,
            RunStatus.REJECTED,
            RunStatus.TIMEOUT,
        }
    ),
    RunStatus.EXECUTING: frozenset(
        {
            RunStatus.RUNNING,
            RunStatus.WAITING_APPROVAL,
            RunStatus.PAUSED_APPROVAL,
            RunStatus.VERIFYING,
            RunStatus.COMPLETED,
            RunStatus.FAILED,
            RunStatus.CANCELLED,
            RunStatus.REJECTED,
            RunStatus.TIMEOUT,
        }
    ),
    RunStatus.WAITING_APPROVAL: frozenset(
        {
            RunStatus.RUNNING,
            RunStatus.EXECUTING,
            RunStatus.REJECTED,
            RunStatus.CANCELLED,
            RunStatus.FAILED,
        }
    ),
    RunStatus.PAUSED_APPROVAL: frozenset(
        {
            RunStatus.RUNNING,
            RunStatus.EXECUTING,
            RunStatus.REJECTED,
            RunStatus.CANCELLED,
            RunStatus.FAILED,
        }
    ),
    RunStatus.VERIFYING: frozenset(
        {
            RunStatus.COMPLETED,
            RunStatus.REPLANNING,
            RunStatus.PLANNING,
            RunStatus.RUNNING,
            RunStatus.FAILED,
            RunStatus.REJECTED,
            RunStatus.CANCELLED,
        }
    ),
    # After a replan, revised execution resumes.
    RunStatus.REPLANNING: frozenset(
        {
            RunStatus.PLANNING,
            RunStatus.READY,
            RunStatus.RUNNING,
            RunStatus.EXECUTING,
            RunStatus.FAILED,
            RunStatus.CANCELLED,
        }
    ),
}


def assert_run_transition(current: RunStatus, target: RunStatus) -> None:
    """Raise ValueError unless current→target is a legal run state transition.

    Re-assigning the identical status is an idempotent no-op. Terminal states
    are immutable: no writer may move a run out of COMPLETED, FAILED,
    CANCELLED, REJECTED, or TIMEOUT.
    """
    if current == target:
        return
    if current.is_terminal:
        raise ValueError(
            f"Invalid run state transition: cannot transition from terminal "
            f"state '{current}' to '{target}'."
        )
    if target not in RUN_TRANSITIONS.get(current, frozenset()):
        raise ValueError(
            f"Invalid run state transition from '{current}' to '{target}'."
        )


# Canonical task state machine mirrors the run machine. A task aggregates
# attempts: a terminal task may be explicitly re-opened to RUNNING only when a
# new run attempt starts — the immutable unit of retry is the run.
TASK_TRANSITIONS: dict[TaskStatus, frozenset[TaskStatus]] = {
    TaskStatus.PENDING: frozenset(
        {
            TaskStatus.PLANNING,
            TaskStatus.READY,
            TaskStatus.RUNNING,
            TaskStatus.FAILED,
            TaskStatus.REJECTED,
            TaskStatus.CANCELLED,
        }
    ),
    TaskStatus.PLANNING: frozenset(
        {TaskStatus.READY, TaskStatus.RUNNING, TaskStatus.FAILED, TaskStatus.CANCELLED}
    ),
    TaskStatus.READY: frozenset(
        {
            TaskStatus.RUNNING,
            TaskStatus.EXECUTING,
            TaskStatus.FAILED,
            TaskStatus.CANCELLED,
        }
    ),
    TaskStatus.RUNNING: frozenset(
        {
            TaskStatus.EXECUTING,
            TaskStatus.WAITING_APPROVAL,
            TaskStatus.PAUSED_APPROVAL,
            TaskStatus.VERIFYING,
            TaskStatus.COMPLETED,
            TaskStatus.FAILED,
            TaskStatus.CANCELLED,
            TaskStatus.REJECTED,
            TaskStatus.TIMEOUT,
        }
    ),
    TaskStatus.EXECUTING: frozenset(
        {
            TaskStatus.RUNNING,
            TaskStatus.WAITING_APPROVAL,
            TaskStatus.PAUSED_APPROVAL,
            TaskStatus.VERIFYING,
            TaskStatus.COMPLETED,
            TaskStatus.FAILED,
            TaskStatus.CANCELLED,
            TaskStatus.REJECTED,
            TaskStatus.TIMEOUT,
        }
    ),
    TaskStatus.WAITING_APPROVAL: frozenset(
        {
            TaskStatus.RUNNING,
            TaskStatus.EXECUTING,
            TaskStatus.REJECTED,
            TaskStatus.CANCELLED,
            TaskStatus.FAILED,
        }
    ),
    TaskStatus.PAUSED_APPROVAL: frozenset(
        {
            TaskStatus.RUNNING,
            TaskStatus.EXECUTING,
            TaskStatus.REJECTED,
            TaskStatus.CANCELLED,
            TaskStatus.FAILED,
        }
    ),
    TaskStatus.VERIFYING: frozenset(
        {
            TaskStatus.COMPLETED,
            TaskStatus.REPLANNING,
            TaskStatus.PLANNING,
            TaskStatus.RUNNING,
            TaskStatus.FAILED,
            TaskStatus.REJECTED,
            TaskStatus.CANCELLED,
        }
    ),
    TaskStatus.REPLANNING: frozenset(
        {
            TaskStatus.PLANNING,
            TaskStatus.READY,
            TaskStatus.RUNNING,
            TaskStatus.EXECUTING,
            TaskStatus.FAILED,
            TaskStatus.CANCELLED,
        }
    ),
}


def assert_task_transition(current: TaskStatus, target: TaskStatus) -> None:
    """Raise ValueError unless current→target is a legal task state transition."""
    if current == target:
        return
    if current.is_terminal:
        if target == TaskStatus.RUNNING:
            return  # explicit re-open for a bounded new attempt
        raise ValueError(
            f"Invalid task state transition: cannot transition from terminal "
            f"state '{current}' to '{target}'."
        )
    if target not in TASK_TRANSITIONS.get(current, frozenset()):
        raise ValueError(
            f"Invalid task state transition from '{current}' to '{target}'."
        )


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

    _enforced_status: TaskStatus | None = PrivateAttr(default=None)

    @model_validator(mode="after")
    def _init_status_tracking(self) -> TaskState:
        """Initialize transition tracking after construction."""
        if self._enforced_status is None:
            self._enforced_status = self.status
        return self

    def __setattr__(self, name: str, value: Any) -> None:
        if name == "status" and self.__pydantic_complete__:
            current = self._enforced_status
            if current is None:
                super().__setattr__(name, value)
                self._enforced_status = self.status
                return
            try:
                target = TaskStatus(value)
            except (ValueError, TypeError) as exc:
                raise ValueError(f"Invalid task status value: {value!r}") from exc
            assert_task_transition(current, target)
            super().__setattr__(name, value)
            self._enforced_status = target
            return
        super().__setattr__(name, value)

    def transition_to(
        self, target_status: TaskStatus, reason: str | None = None
    ) -> None:
        """Explicitly transition the task through the state machine."""
        assert_task_transition(self.status, target_status)
        self.status = target_status
        if reason:
            self.metadata["status_reason"] = reason


class RunState(BaseModel):
    """Persistent, unified, and checkpointable canonical runtime state of an Agent Run (TASK ORC-03)."""

    run_id: str = Field(..., description="Unique execution run identifier")
    task_id: str = Field(..., description="Associated parent task identifier")
    tenant_id: str = Field(..., description="Tenant boundary identifier")
    user_id: str = Field(..., description="User ownership identifier")
    status: RunStatus = Field(default=RunStatus.CREATED)

    # Permissions and tenancy context
    roles: list[str] = Field(default_factory=list)
    permissions: list[str] = Field(default_factory=list)
    correlation_id: str | None = None

    # Iteration and step progress
    current_iteration: int = Field(default=0, ge=0)
    current_step: int | str = Field(default=0)
    max_iterations: int = Field(default=10, ge=1)
    steps: list[StepExecutionRecord] = Field(default_factory=list)

    # Agent identity and routing
    current_agent: str | None = None
    next_agent: str | None = None

    # Context, messages, and prompt
    prompt: str | None = None
    messages: list[str] = Field(default_factory=list)
    context: dict[str, Any] = Field(default_factory=dict)

    # Tool execution records
    tool_calls: list[dict[str, Any]] = Field(default_factory=list)
    tool_results: list[dict[str, Any]] = Field(default_factory=list)

    # Quality and verification loops
    revision_count: int = Field(default=0, ge=0)
    verification_verdict: str | None = None

    # Approvals and human-in-the-loop
    approval_state: str | None = None
    pending_approval_id: str | None = None

    # Checkpoint and persistence metadata
    checkpoint_metadata: dict[str, Any] = Field(default_factory=dict)

    # Output, errors, and termination
    plan: dict[str, Any] | None = None
    final_output: str | None = None
    error: str | None = None
    termination_reason: str | None = None

    # Accounting & telemetry
    tokens_consumed: int = Field(default=0, ge=0)
    cost_usd: float = Field(default=0.0, ge=0.0)
    created_at: float = Field(default_factory=time.time)
    completed_at: float | None = None
    metadata: dict[str, Any] = Field(default_factory=dict)

    _enforced_status: RunStatus | None = PrivateAttr(default=None)

    @model_validator(mode="after")
    def _init_status_tracking(self) -> RunState:
        """Initialize transition tracking after construction (restored
        checkpoints and adapter mappings may start in any legal state)."""
        if self._enforced_status is None:
            self._enforced_status = self.status
        return self

    def __setattr__(self, name: str, value: Any) -> None:
        if name == "status" and self.__pydantic_complete__:
            current = self._enforced_status
            if current is None:
                super().__setattr__(name, value)
                self._enforced_status = self.status
                return
            try:
                target = RunStatus(value)
            except (ValueError, TypeError) as exc:
                raise ValueError(f"Invalid run status value: {value!r}") from exc
            # Validate BEFORE mutation: an illegal write must raise without
            # changing the persisted status.
            assert_run_transition(current, target)
            super().__setattr__(name, value)
            self._enforced_status = target
            return
        super().__setattr__(name, value)

    def transition_to(
        self, target_status: RunStatus, reason: str | None = None
    ) -> None:
        """Deterministically transition run status with explicit state machine verification."""
        assert_run_transition(self.status, target_status)
        self.status = target_status
        if reason:
            self.termination_reason = reason
        if target_status.is_terminal:
            self.completed_at = time.time()

    def to_agent_state(self) -> dict[str, Any]:
        """Convert canonical RunState to LangGraph AgentState dictionary."""
        return {
            "prompt": self.prompt or "",
            "tenant_id": self.tenant_id,
            "user_id": self.user_id,
            "roles": self.roles,
            "permissions": self.permissions,
            "conversation_id": self.task_id,
            "correlation_id": self.correlation_id or "",
            "obo_token": self.metadata.get("obo_token", ""),
            "raw_token": self.metadata.get("raw_token", ""),
            "next_agent": self.next_agent or "supervisor",
            "current_agent": self.current_agent or "supervisor",
            "workflow_phase": self.status.value,
            "messages": self.messages,
            "tool_calls": self.tool_calls,
            "financial_analysis": self.context.get("financial_analysis", {}),
            "retrieved_chunks": self.context.get("retrieved_chunks", []),
            "groundedness_score": self.context.get("groundedness_score", 1.0),
            "verification_verdict": self.verification_verdict or "PASS",
            "critique_notes": self.metadata.get("critique_notes", ""),
            "revision_count": self.revision_count,
            "final_response": self.final_output or "",
            "mascot_state": self.metadata.get("mascot_state", "idle"),
            "citations": self.metadata.get("citations", []),
            "execution_plan": self.plan,
        }

    @classmethod
    def from_agent_state(
        cls, state: Mapping[str, Any], task_id: str, run_id: str
    ) -> RunState:
        """Construct canonical RunState from a LangGraph AgentState dictionary."""
        status_map: dict[str, RunStatus] = {
            "completed": RunStatus.COMPLETED,
            "verification_passed": RunStatus.COMPLETED,
            "verification_failed": RunStatus.FAILED,
            "failed": RunStatus.FAILED,
            "paused_approval": RunStatus.PAUSED_APPROVAL,
            "waiting_approval": RunStatus.WAITING_APPROVAL,
            "planning": RunStatus.PLANNING,
            "ready": RunStatus.READY,
            "verifying": RunStatus.VERIFYING,
            "replanning": RunStatus.REPLANNING,
            "critique": RunStatus.RUNNING,
            "executing": RunStatus.RUNNING,
            "running": RunStatus.RUNNING,
            "cancelled": RunStatus.CANCELLED,
            "rejected": RunStatus.REJECTED,
            "timeout": RunStatus.TIMEOUT,
        }
        raw_phase = state.get("workflow_phase", "running")
        status = status_map.get(raw_phase, RunStatus.RUNNING)

        verdict = state.get("verification_verdict")
        if verdict == "REJECTED":
            status = RunStatus.REJECTED
        elif verdict == "FAILED":
            status = RunStatus.FAILED

        return cls(
            run_id=run_id,
            task_id=task_id,
            tenant_id=state.get("tenant_id", "default"),
            user_id=state.get("user_id", "default"),
            status=status,
            roles=state.get("roles", []),
            permissions=state.get("permissions", []),
            correlation_id=state.get("correlation_id"),
            current_iteration=state.get("revision_count", 0),
            current_step=state.get("current_agent", "supervisor"),
            current_agent=state.get("current_agent"),
            next_agent=state.get("next_agent"),
            prompt=state.get("prompt"),
            messages=state.get("messages", []),
            context={
                "financial_analysis": state.get("financial_analysis", {}),
                "retrieved_chunks": state.get("retrieved_chunks", []),
                "groundedness_score": state.get("groundedness_score", 1.0),
            },
            tool_calls=state.get("tool_calls", []),
            revision_count=state.get("revision_count", 0),
            verification_verdict=state.get("verification_verdict"),
            final_output=state.get("final_response"),
            error=state.get("critique_notes")
            if state.get("verification_verdict") in ("FAILED", "REJECTED")
            else None,
            termination_reason=state.get("verification_verdict"),
            metadata={
                "obo_token": state.get("obo_token", ""),
                "mascot_state": state.get("mascot_state", "idle"),
                "citations": state.get("citations", []),
                "critique_notes": state.get("critique_notes", ""),
            },
        )
