"""State models for Agent tasks and execution runs."""

from __future__ import annotations

import time
from enum import StrEnum
from typing import TYPE_CHECKING, Any

from pydantic import BaseModel, Field

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

    def transition_to(
        self, target_status: RunStatus, reason: str | None = None
    ) -> None:
        """Deterministically transition run status with explicit state machine verification."""
        terminal_statuses = {
            RunStatus.COMPLETED,
            RunStatus.FAILED,
            RunStatus.CANCELLED,
            RunStatus.REJECTED,
            RunStatus.TIMEOUT,
        }
        if self.status in terminal_statuses:
            raise ValueError(
                f"Invalid run state transition: cannot transition from terminal state '{self.status}' to '{target_status}'."
            )

        valid_transitions: dict[RunStatus, set[RunStatus]] = {
            RunStatus.CREATED: {
                RunStatus.PLANNING,
                RunStatus.READY,
                RunStatus.RUNNING,
                RunStatus.FAILED,
                RunStatus.CANCELLED,
            },
            RunStatus.PLANNING: {
                RunStatus.READY,
                RunStatus.RUNNING,
                RunStatus.FAILED,
                RunStatus.CANCELLED,
            },
            RunStatus.READY: {
                RunStatus.RUNNING,
                RunStatus.EXECUTING,
                RunStatus.FAILED,
                RunStatus.CANCELLED,
            },
            RunStatus.RUNNING: {
                RunStatus.EXECUTING,
                RunStatus.WAITING_APPROVAL,
                RunStatus.PAUSED_APPROVAL,
                RunStatus.VERIFYING,
                RunStatus.COMPLETED,
                RunStatus.FAILED,
                RunStatus.CANCELLED,
                RunStatus.REJECTED,
                RunStatus.TIMEOUT,
            },
            RunStatus.EXECUTING: {
                RunStatus.RUNNING,
                RunStatus.WAITING_APPROVAL,
                RunStatus.PAUSED_APPROVAL,
                RunStatus.VERIFYING,
                RunStatus.COMPLETED,
                RunStatus.FAILED,
                RunStatus.CANCELLED,
                RunStatus.REJECTED,
                RunStatus.TIMEOUT,
            },
            RunStatus.WAITING_APPROVAL: {
                RunStatus.RUNNING,
                RunStatus.EXECUTING,
                RunStatus.REJECTED,
                RunStatus.CANCELLED,
                RunStatus.FAILED,
            },
            RunStatus.PAUSED_APPROVAL: {
                RunStatus.RUNNING,
                RunStatus.EXECUTING,
                RunStatus.REJECTED,
                RunStatus.CANCELLED,
                RunStatus.FAILED,
            },
            RunStatus.VERIFYING: {
                RunStatus.COMPLETED,
                RunStatus.REPLANNING,
                RunStatus.PLANNING,
                RunStatus.RUNNING,
                RunStatus.FAILED,
                RunStatus.REJECTED,
                RunStatus.CANCELLED,
            },
            RunStatus.REPLANNING: {
                RunStatus.PLANNING,
                RunStatus.READY,
                RunStatus.RUNNING,
                RunStatus.FAILED,
                RunStatus.CANCELLED,
            },
        }

        allowed = valid_transitions.get(self.status, set())
        if target_status not in allowed:
            raise ValueError(
                f"Invalid run state transition from '{self.status}' to '{target_status}'."
            )

        self.status = target_status
        if reason:
            self.termination_reason = reason
        if target_status in terminal_statuses:
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
