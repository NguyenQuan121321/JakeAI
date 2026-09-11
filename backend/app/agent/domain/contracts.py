"""Canonical Domain Models and Contracts for JakeAI AI Orchestration.

This module defines the single authoritative contract suite for:
- Task specifications (TaskSpec)
- Structured execution plans and dependency-aware steps (ExecutionPlan, PlanStep)
- Machine-readable agent capabilities and dynamic selection (AgentCapability, AgentSelection)
- Model routing decisions (ModelSelection)
- Tool selection and policy validation (ToolSelection)
- Multi-tenant execution contexts (ExecutionContext)
- Step execution outputs and verification results (StepResult, VerificationResult)
- Bounded recovery decisions and terminal states (RecoveryDecision, TerminalState)
"""

from __future__ import annotations

import time
import uuid
from enum import StrEnum
from typing import Any

from pydantic import BaseModel, Field, field_validator


class ExecutionStateStatus(StrEnum):
    """Canonical lifecycle states of an orchestration run."""

    CREATED = "created"
    PLANNING = "planning"
    READY = "ready"
    EXECUTING = "executing"
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
        """Return True if this state is terminal."""
        return self in (
            ExecutionStateStatus.COMPLETED,
            ExecutionStateStatus.FAILED,
            ExecutionStateStatus.CANCELLED,
            ExecutionStateStatus.REJECTED,
            ExecutionStateStatus.TIMEOUT,
        )

    @property
    def is_success(self) -> bool:
        """Return True if and only if execution completed successfully."""
        return self == ExecutionStateStatus.COMPLETED


class StepStatus(StrEnum):
    """Lifecycle states of an individual PlanStep."""

    PENDING = "pending"
    READY = "ready"
    RUNNING = "running"
    EXECUTING = "executing"
    PAUSED_APPROVAL = "paused_approval"
    WAITING_APPROVAL = "waiting_approval"
    COMPLETED = "completed"
    FAILED = "failed"
    SKIPPED = "skipped"
    CANCELLED = "cancelled"


class VerificationVerdict(StrEnum):
    """Possible outcomes of execution verification."""

    PASS = "PASS"
    NEEDS_REVISION = "NEEDS_REVISION"
    FAILED = "FAILED"
    REJECTED = "REJECTED"


class RecoveryAction(StrEnum):
    """Actions recommended by verification or recovery engines."""

    NONE = "none"
    RETRY = "retry"
    REPLAN = "replan"
    SWITCH_MODEL = "switch_model"
    SWITCH_AGENT = "switch_agent"
    TERMINATE_FAILED = "terminate_failed"
    TERMINATE_REJECTED = "terminate_rejected"


class AgentCapability(StrEnum):
    """Machine-readable agent capability categories."""

    SUPERVISION = "supervision"
    PLANNING = "planning"
    FINANCIAL_ANALYSIS = "financial_analysis"
    BANKING_API = "banking_api"
    RAG_RETRIEVAL = "rag_retrieval"
    SYNTHESIS = "synthesis"
    VERIFICATION = "verification"
    GENERAL_REASONING = "general_reasoning"
    CODE_EXECUTION = "code_execution"


class StepRetryPolicy(BaseModel):
    """Retry policy governing step-level execution failure."""

    max_retries: int = Field(default=3, ge=0, le=10)
    backoff_seconds: float = Field(default=1.0, ge=0.0)
    retryable_errors: list[str] = Field(default_factory=list)


class StepTimeoutPolicy(BaseModel):
    """Timeout policy governing step execution."""

    timeout_seconds: float = Field(default=30.0, ge=0.1, le=600.0)


class TaskSpec(BaseModel):
    """Canonical specification defining a user or enterprise task."""

    task_id: str = Field(default_factory=lambda: f"task_{uuid.uuid4().hex[:12]}")
    tenant_id: str = Field(..., description="Tenant boundary identifier")
    user_id: str = Field(default="anonymous", description="Requesting user identifier")
    goal: str = Field(..., description="Target objective or problem statement")
    roles: list[str] = Field(default_factory=list)
    permissions: list[str] = Field(default_factory=list)
    correlation_id: str = Field(
        default_factory=lambda: str(uuid.uuid4()),
        description="Distributed correlation tracing ID",
    )
    context: dict[str, Any] = Field(default_factory=dict)
    metadata: dict[str, Any] = Field(default_factory=dict)
    created_at: float = Field(default_factory=time.time)

    @field_validator("tenant_id")
    @classmethod
    def validate_tenant_not_empty(cls, v: str) -> str:
        if not v or not v.strip():
            raise ValueError("TaskSpec tenant_id must not be empty.")
        return v.strip()

    @field_validator("goal")
    @classmethod
    def validate_goal_not_empty(cls, v: str) -> str:
        if not v or not v.strip():
            raise ValueError("TaskSpec goal must not be empty.")
        return v.strip()


class StepResult(BaseModel):
    """Execution output captured for an individual PlanStep."""

    step_id: str
    status: StepStatus = StepStatus.COMPLETED
    output: Any = None
    error: str | None = None
    agent_id: str | None = None
    model_used: str | None = None
    provider_used: str | None = None
    tool_calls: list[dict[str, Any]] = Field(default_factory=list)
    execution_time_ms: float = Field(default=0.0, ge=0.0)
    tokens_consumed: int = Field(default=0, ge=0)
    cost_usd: float = Field(default=0.0, ge=0.0)
    timestamp: float = Field(default_factory=time.time)


class PlanStep(BaseModel):
    """Discrete, dependency-aware milestone within an ExecutionPlan."""

    step_id: str
    description: str
    objective: str = ""
    dependencies: list[str] = Field(
        default_factory=list,
        description="IDs of prerequisite PlanSteps that must succeed before this step runs",
    )
    required_capabilities: list[str] = Field(default_factory=list)
    candidate_agents: list[str] = Field(default_factory=list)
    required_tools: list[str] = Field(default_factory=list)
    model_requirements: dict[str, Any] = Field(default_factory=dict)
    success_conditions: list[str] = Field(default_factory=list)
    retry_policy: StepRetryPolicy = Field(default_factory=StepRetryPolicy)
    timeout_policy: StepTimeoutPolicy = Field(default_factory=StepTimeoutPolicy)
    status: StepStatus = Field(default=StepStatus.PENDING)
    assigned_agent: str | None = None
    selected_model: str | None = None
    selected_provider: str | None = None
    observation: str | None = None
    error: str | None = None
    result: StepResult | None = None
    retries_exhausted: int = Field(default=0, ge=0)


class ExecutionPlan(BaseModel):
    """Directed dependency graph of planned operations fulfilling a TaskSpec."""

    plan_id: str = Field(default_factory=lambda: f"plan_{uuid.uuid4().hex[:12]}")
    task_id: str
    goal: str
    analysis: str = ""
    steps: list[PlanStep] = Field(default_factory=list)
    created_at: float = Field(default_factory=time.time)
    updated_at: float = Field(default_factory=time.time)

    def get_step(self, step_id: str) -> PlanStep | None:
        """Find a step by ID."""
        for s in self.steps:
            if s.step_id == step_id:
                return s
        return None

    def get_runnable_steps(
        self, completed_step_ids: set[str] | None = None
    ) -> list[PlanStep]:
        """Return steps whose prerequisite dependencies are fully completed and are in PENDING or READY status."""
        completed = completed_step_ids or {
            s.step_id for s in self.steps if s.status == StepStatus.COMPLETED
        }
        runnable: list[PlanStep] = []
        for s in self.steps:
            if s.status in (StepStatus.PENDING, StepStatus.READY) and all(
                dep in completed for dep in s.dependencies
            ):
                runnable.append(s)
        return runnable

    def get_independent_step_groups(self) -> list[list[PlanStep]]:
        """Group steps into parallelizable execution tiers based on dependencies."""
        remaining = {s.step_id: s for s in self.steps}
        completed: set[str] = set()
        tiers: list[list[PlanStep]] = []

        while remaining:
            current_tier: list[PlanStep] = []
            for _s_id, step in list(remaining.items()):
                if all(dep in completed for dep in step.dependencies):
                    current_tier.append(step)
            if not current_tier:
                # Dependency cycle or unsatisfied dependencies: fall back to remaining sequentially
                current_tier = list(remaining.values())
                tiers.append(current_tier)
                break
            tiers.append(current_tier)
            for s in current_tier:
                completed.add(s.step_id)
                remaining.pop(s.step_id, None)

        return tiers

    def is_complete(self) -> bool:
        """Return True if all steps in plan are completed or skipped."""
        return bool(self.steps) and all(
            s.status in (StepStatus.COMPLETED, StepStatus.SKIPPED) for s in self.steps
        )

    def has_failures(self) -> bool:
        """Return True if any step in plan failed without recovery."""
        return any(s.status == StepStatus.FAILED for s in self.steps)

    def mark_step_status(
        self,
        step_id: str,
        status: StepStatus,
        observation: str | None = None,
        error: str | None = None,
        result: StepResult | None = None,
    ) -> None:
        """Update status and outputs for an individual step."""
        step = self.get_step(step_id)
        if step:
            step.status = status
            if observation is not None:
                step.observation = observation
            if error is not None:
                step.error = error
            if result is not None:
                step.result = result
            self.updated_at = time.time()


class AgentSelection(BaseModel):
    """Result of selecting an agent for a plan step."""

    agent_id: str
    reasoning: str
    confidence: float = Field(default=1.0, ge=0.0, le=1.0)
    matched_capabilities: list[str] = Field(default_factory=list)
    risk_level: str = Field(default="safe")
    fallback_used: bool = False


class ModelSelection(BaseModel):
    """Result of canonical model routing for an orchestration step."""

    model: str
    provider: str
    workload_class: str = "general"
    quality_score: float = Field(default=0.8, ge=0.0, le=1.0)
    estimated_cost_savings: float = Field(default=0.0, ge=0.0)
    fallback_chain: list[Any] = Field(default_factory=list)
    reasoning: list[str] = Field(default_factory=list)


class ToolSelection(BaseModel):
    """Result of selecting and validating a tool for execution."""

    tool_name: str
    arguments: dict[str, Any] = Field(default_factory=dict)
    risk_level: str = "safe"
    requires_approval: bool = False
    policy_decision: str = "allowed"


class ExecutionContext(BaseModel):
    """Validated multi-tenant execution context that cannot be degraded or dropped."""

    tenant_id: str = Field(..., description="Tenant boundary identifier")
    user_id: str = Field(default="anonymous")
    roles: list[str] = Field(default_factory=list)
    permissions: list[str] = Field(default_factory=list)
    correlation_id: str = Field(default_factory=lambda: str(uuid.uuid4()))
    obo_token: str | None = None
    raw_token: str | None = None
    metadata: dict[str, Any] = Field(default_factory=dict)

    @field_validator("tenant_id")
    @classmethod
    def validate_tenant(cls, v: str) -> str:
        if not v or not v.strip():
            raise ValueError("ExecutionContext tenant_id must not be empty.")
        return v.strip()

    def assert_tenant_match(self, expected_tenant_id: str) -> None:
        """Enforce strict tenant boundary check. Hard failure on mismatch."""
        if self.tenant_id != expected_tenant_id:
            raise PermissionError(
                f"Multi-tenant boundary violation: execution context tenant '{self.tenant_id}' "
                f"does not match expected tenant '{expected_tenant_id}'."
            )


class VerificationResult(BaseModel):
    """Structured evaluation of actual execution outputs."""

    verdict: VerificationVerdict
    reason: str
    violated_invariant: str | None = None
    evidence: dict[str, Any] = Field(default_factory=dict)
    recoverability: bool = True
    recommended_recovery_action: RecoveryAction = RecoveryAction.NONE
    groundedness_score: float = Field(default=1.0, ge=0.0, le=1.0)
    timestamp: float = Field(default_factory=time.time)


class RecoveryDecision(BaseModel):
    """Deterministic recovery action decided upon step or verification failure."""

    action: RecoveryAction
    step_id: str | None = None
    reason: str
    attempt: int = Field(default=1, ge=1)
    max_attempts: int = Field(default=3, ge=1)
    alternative_agent: str | None = None
    alternative_model: str | None = None


class TerminalState(BaseModel):
    """Authoritative outcome of an orchestration run upon completion or failure."""

    status: ExecutionStateStatus
    final_output: str | None = None
    error: str | None = None
    reason: str | None = None
    tokens_consumed: int = Field(default=0, ge=0)
    cost_usd: float = Field(default=0.0, ge=0.0)
    duration_ms: float = Field(default=0.0, ge=0.0)
    completed_at: float = Field(default_factory=time.time)

    @field_validator("status")
    @classmethod
    def validate_terminal(cls, v: ExecutionStateStatus) -> ExecutionStateStatus:
        if not v.is_terminal:
            raise ValueError(f"Status '{v}' is not a valid terminal state.")
        return v
