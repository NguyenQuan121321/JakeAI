"""Agent Runtime Manager service orchestrating tasks, runs, and multi-tenant isolation."""

from __future__ import annotations

import logging
import time
import uuid
from typing import TYPE_CHECKING, Any

from app.agent.approvals.manager import ApprovalManager, get_approval_manager
from app.agent.backends.jakeai import JakeAIBackend
from app.agent.execution.engine import ExecutionEngine, get_execution_engine
from app.agent.memory.manager import AgentMemoryManager, get_memory_manager
from app.agent.planning.planner import BoundedPlanner
from app.agent.runtime.models import AgentConfig, AgentRunEvent
from app.agent.runtime.runner import AgentRunner
from app.agent.state.checkpoint import CheckpointManager, get_checkpoint_manager
from app.agent.state.models import (
    RunState,
    RunStatus,
    TaskState,
    TaskStatus,
)
from app.agent.telemetry import agent_telemetry
from app.agent.tools.registry import ToolRegistry, get_tool_registry

if TYPE_CHECKING:
    from collections.abc import AsyncGenerator

    from app.agent.approvals.models import ApprovalDecision, ApprovalRequest
    from app.agent.backends.base import AgentBackendInterface
    from app.agent.domain.contracts import TaskSpec

logger = logging.getLogger(__name__)


class AgentRuntimeManager:
    """Central entrypoint for the JakeAI-Agent platform."""

    def __init__(
        self,
        backend: AgentBackendInterface | None = None,
        tool_registry: ToolRegistry | None = None,
        memory_manager: AgentMemoryManager | None = None,
        checkpoint_manager: CheckpointManager | None = None,
        approval_manager: ApprovalManager | None = None,
        engine: ExecutionEngine | None = None,
        config: AgentConfig | None = None,
    ) -> None:
        self.config = config or AgentConfig()
        self.backend = backend or JakeAIBackend(default_model=self.config.default_model)
        self.tool_registry = tool_registry or get_tool_registry()
        self.memory_manager = memory_manager or get_memory_manager()
        self.checkpoint_manager = checkpoint_manager or get_checkpoint_manager()
        self.approval_manager = approval_manager or get_approval_manager()
        self.engine = engine or get_execution_engine()

        self.planner = BoundedPlanner(
            backend=self.backend,
            max_iterations=self.config.max_iterations,
            timeout_seconds=self.config.timeout_seconds,
            memory_manager=self.memory_manager,
        )

        self.runner = AgentRunner(
            planner=self.planner,
            tool_registry=self.tool_registry,
            memory_manager=self.memory_manager,
            checkpoint_manager=self.checkpoint_manager,
            approval_manager=self.approval_manager,
            config=self.config,
        )

        # In-memory primary task and run stores (keyed by ID)
        self._tasks: dict[str, TaskState] = {}
        self._runs: dict[str, RunState] = {}

    def create_task(
        self,
        goal: str,
        tenant_id: str,
        user_id: str,
        metadata: dict[str, Any] | None = None,
    ) -> TaskState:
        """Instantiate and store a new Agent Task within a tenant boundary."""
        task_id = f"task_{uuid.uuid4().hex[:12]}"
        task = TaskState(
            task_id=task_id,
            tenant_id=tenant_id,
            user_id=user_id,
            goal=goal,
            status=TaskStatus.PENDING,
            metadata=metadata or {},
        )
        self._tasks[task_id] = task
        agent_telemetry.record_task_created(tenant_id)
        logger.info("Created agent task %s for tenant %s", task_id, tenant_id)
        return task

    def get_task(self, task_id: str, tenant_id: str) -> TaskState:
        """Retrieve an Agent Task, verifying tenant ownership."""
        task = self._tasks.get(task_id)
        if task is None:
            raise KeyError(f"Task '{task_id}' not found.")

        if task.tenant_id != tenant_id:
            raise PermissionError(
                f"Tenant mismatch: Task '{task_id}' belongs to '{task.tenant_id}', "
                f"caller is '{tenant_id}'."
            )
        return task

    def create_run(
        self,
        task_id: str,
        tenant_id: str,
        user_id: str,
        max_iterations: int | None = None,
    ) -> RunState:
        """Create a new execution run associated with a task."""
        task = self.get_task(task_id, tenant_id)
        run_id = f"run_{uuid.uuid4().hex[:12]}"
        iterations_limit = max_iterations or self.config.max_iterations

        initial_plan = self.planner.create_initial_plan(task.goal)
        run = RunState(
            run_id=run_id,
            task_id=task_id,
            tenant_id=tenant_id,
            user_id=user_id,
            status=RunStatus.CREATED,
            max_iterations=iterations_limit,
            plan=initial_plan.model_dump(),
        )
        self._runs[run_id] = run
        task.active_run_id = run_id
        task.updated_at = time.time()
        logger.info(
            "Created agent run %s for task %s (tenant %s)", run_id, task_id, tenant_id
        )
        return run

    def get_run(self, run_id: str, tenant_id: str) -> RunState:
        """Retrieve an execution run, verifying tenant ownership."""
        run = self._runs.get(run_id)
        if run is None:
            raise KeyError(f"Run '{run_id}' not found.")

        if run.tenant_id != tenant_id:
            raise PermissionError(
                f"Tenant mismatch: Run '{run_id}' belongs to '{run.tenant_id}', "
                f"caller is '{tenant_id}'."
            )
        return run

    async def get_or_restore_run(self, run_id: str, tenant_id: str) -> RunState:
        """Retrieve an execution run from memory or restore from durable checkpoint."""
        run = self._runs.get(run_id)
        if run is not None:
            if run.tenant_id != tenant_id:
                raise PermissionError(
                    f"Tenant mismatch: Run '{run_id}' belongs to '{run.tenant_id}', "
                    f"caller is '{tenant_id}'."
                )
            return run

        # Attempt restoration from checkpoint manager
        cp = await self.checkpoint_manager.load_checkpoint(run_id, tenant_id=tenant_id)
        if cp is not None:
            dump = cp.model_dump(
                exclude={
                    "checkpoint_id",
                    "checkpoint_created_at",
                    "short_term_memory_snapshot",
                }
            )
            restored_run = RunState(**dump)
            self._runs[run_id] = restored_run
            return restored_run

        raise KeyError(f"Run '{run_id}' not found.")

    async def execute_run(
        self,
        task_id: str,
        run_id: str,
        tenant_id: str,
        user_roles: list[str] | None = None,
        user_permissions: list[str] | None = None,
    ) -> RunState:
        """Execute a run to completion or pause point."""
        task = self.get_task(task_id, tenant_id)
        run = self.get_run(run_id, tenant_id)

        if run.status.is_terminal:
            raise ValueError(
                f"Run '{run_id}' is already in terminal state '{run.status.value}' "
                "and cannot be executed again."
            )

        await self.runner.start_run(
            task=task,
            run=run,
            user_roles=user_roles,
            user_permissions=user_permissions,
        )
        return run

    async def execute_task_spec(
        self,
        spec: TaskSpec,
        run_id: str | None = None,
    ) -> AsyncGenerator[AgentRunEvent, None]:
        """Execute a canonical TaskSpec through the ExecutionEngine, yielding canonical events."""
        if spec.task_id not in self._tasks:
            self._tasks[spec.task_id] = TaskState(
                task_id=spec.task_id,
                tenant_id=spec.tenant_id,
                user_id=spec.user_id,
                goal=spec.goal,
                status=TaskStatus.RUNNING,
                metadata=spec.metadata,
            )

        async for event in self.engine.execute_task(spec, run_id=run_id):
            yield event

    def cancel_run(self, task_id: str, run_id: str, tenant_id: str) -> RunState:
        """Signal cooperative cancellation to a running task run.

        Terminal states are immutable: cancelling a run that already reached a
        terminal state is a no-op that preserves its terminal status.
        """
        task = self.get_task(task_id, tenant_id)
        run = self.get_run(run_id, tenant_id)

        if run.status.is_terminal:
            logger.info(
                "Cancel ignored: run %s already in terminal state %s",
                run_id,
                run.status.value,
            )
            return run

        self.runner.request_cancellation(run_id)
        run.status = RunStatus.CANCELLED
        task.status = TaskStatus.CANCELLED
        return run

    async def decide_approval(
        self,
        task_id: str,
        run_id: str,
        approval_id: str,
        decision: ApprovalDecision,
        tenant_id: str,
        user_id: str,
        user_roles: list[str] | None = None,
        user_permissions: list[str] | None = None,
    ) -> ApprovalRequest:
        """Submit approval or rejection for a dangerous action, resuming run if approved."""
        task = self.get_task(task_id, tenant_id)
        run = self.get_run(run_id, tenant_id)

        appr = self.approval_manager.decide(
            approval_id=approval_id,
            decision=decision,
            tenant_id=tenant_id,
            user_id=user_id,
        )
        agent_telemetry.record_approval_decision(decision.approved, tenant_id)

        if decision.approved and (
            run.status in (RunStatus.PAUSED_APPROVAL, RunStatus.WAITING_APPROVAL)
        ):
            # Resume run execution
            await self.runner.resume_after_approval(
                task=task,
                run=run,
                approval_id=approval_id,
                user_roles=user_roles,
                user_permissions=user_permissions,
            )
        elif not decision.approved:
            # Inform short-term memory that action was rejected by operator
            short_term = self.memory_manager.get_run_memory(run_id)
            from app.agent.backends.base import AgentMessage

            short_term.add_message(
                AgentMessage(
                    role="system",
                    content=f"Operator REJECTED action '{appr.tool_name}'. Reason: {decision.reason or 'Denied'}. Adjust plan accordingly.",
                )
            )
            run.pending_approval_id = None
            # Terminal states are immutable: a late decision on an already
            # terminal run must not resurrect it.
            if not run.status.is_terminal:
                run.status = RunStatus.RUNNING
                task.status = TaskStatus.RUNNING

        return appr


_agent_manager: AgentRuntimeManager | None = None


def get_agent_manager() -> AgentRuntimeManager:
    """Singleton accessor for AgentRuntimeManager."""
    global _agent_manager
    if _agent_manager is None:
        _agent_manager = AgentRuntimeManager()
    return _agent_manager
