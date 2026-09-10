"""Agent Runner orchestrating background run tasks, SSE streaming queues, and cancellation."""

from __future__ import annotations

import asyncio
import contextlib
import logging
import time
from typing import TYPE_CHECKING, Any

from app.agent.approvals.models import ApprovalStatus
from app.agent.backends.base import AgentMessage
from app.agent.runtime.loop import AgentExecutionLoop
from app.agent.runtime.models import AgentRunEvent
from app.agent.state.models import RunState, RunStatus, TaskState, TaskStatus
from app.agent.telemetry import agent_telemetry

if TYPE_CHECKING:
    from collections.abc import AsyncIterator

    from app.agent.approvals.manager import ApprovalManager
    from app.agent.memory.manager import AgentMemoryManager
    from app.agent.planning.planner import BoundedPlanner
    from app.agent.runtime.models import AgentConfig
    from app.agent.state.checkpoint import CheckpointManager
    from app.agent.tools.registry import ToolRegistry

logger = logging.getLogger(__name__)


class AgentRunner:
    """Manages active run execution jobs, real-time event broadcasting, and cancellation."""

    def __init__(
        self,
        planner: BoundedPlanner,
        tool_registry: ToolRegistry,
        memory_manager: AgentMemoryManager,
        checkpoint_manager: CheckpointManager,
        approval_manager: ApprovalManager,
        config: AgentConfig | None = None,
    ) -> None:
        self.loop = AgentExecutionLoop(
            planner=planner,
            tool_registry=tool_registry,
            memory_manager=memory_manager,
            checkpoint_manager=checkpoint_manager,
            approval_manager=approval_manager,
            config=config,
        )
        # Event queues per run: run_id -> list[asyncio.Queue[AgentRunEvent | None]]
        self._event_subscribers: dict[
            str, list[asyncio.Queue[AgentRunEvent | None]]
        ] = {}
        # Cancellation flags: run_id -> bool
        self._cancellation_flags: dict[str, bool] = {}
        # In-flight asyncio tasks: run_id -> asyncio.Task
        self._active_tasks: dict[str, asyncio.Task[Any]] = {}

    def subscribe_events(self, run_id: str) -> asyncio.Queue[AgentRunEvent | None]:
        """Create and register an event queue for SSE streaming."""
        q: asyncio.Queue[AgentRunEvent | None] = asyncio.Queue()
        self._event_subscribers.setdefault(run_id, []).append(q)
        return q

    def unsubscribe_events(
        self, run_id: str, q: asyncio.Queue[AgentRunEvent | None]
    ) -> None:
        """Remove subscriber queue."""
        if run_id in self._event_subscribers:
            with contextlib.suppress(ValueError):
                self._event_subscribers[run_id].remove(q)
            if not self._event_subscribers[run_id]:
                del self._event_subscribers[run_id]

    async def _broadcast_event(self, run_id: str, event: AgentRunEvent | None) -> None:
        """Broadcast event to all connected listeners."""
        subscribers = self._event_subscribers.get(run_id, [])
        for q in list(subscribers):
            await q.put(event)

    def request_cancellation(self, run_id: str) -> None:
        """Signal cooperative and task cancellation to an active run."""
        self._cancellation_flags[run_id] = True
        logger.info("Cancellation requested for run %s", run_id)
        task = self._active_tasks.get(run_id)
        if task is not None and not task.done():
            task.cancel()

    async def start_run(
        self,
        task: TaskState,
        run: RunState,
        user_roles: list[str] | None = None,
        user_permissions: list[str] | None = None,
    ) -> None:
        """Execute run loop synchronously or via background task."""
        self._cancellation_flags[run.run_id] = False
        current_async_task = asyncio.current_task()
        if current_async_task is not None:
            self._active_tasks[run.run_id] = current_async_task

        agent_telemetry.record_run_started(
            task.tenant_id, self.loop.config.backend_type
        )

        try:
            async for event in self.loop.execute(
                task=task,
                run=run,
                cancellation_requested=lambda: self._cancellation_flags.get(
                    run.run_id, False
                ),
                user_roles=user_roles,
                user_permissions=user_permissions,
            ):
                await self._broadcast_event(run.run_id, event)
        except asyncio.CancelledError:
            run.status = RunStatus.CANCELLED
            task.status = TaskStatus.CANCELLED
            run.completed_at = time.time()
            logger.info("Run %s was cancelled via asyncio task cancellation", run.run_id)
            await self._broadcast_event(
                run.run_id,
                AgentRunEvent(
                    event_type="cancelled",
                    task_id=task.task_id,
                    run_id=run.run_id,
                    data={"message": "Run execution cancelled"},
                ),
            )
            raise
        finally:
            # Send completion Sentinel to SSE listeners
            await self._broadcast_event(run.run_id, None)
            self._cancellation_flags.pop(run.run_id, None)
            self._active_tasks.pop(run.run_id, None)

    async def resume_after_approval(
        self,
        task: TaskState,
        run: RunState,
        approval_id: str,
        user_roles: list[str] | None = None,
        user_permissions: list[str] | None = None,
    ) -> None:
        """Resume an execution run that was paused awaiting approval."""
        appr = self.loop.approval_manager.get_request(approval_id, task.tenant_id)
        if appr.status != ApprovalStatus.APPROVED:
            raise ValueError(
                f"Approval '{approval_id}' is not in approved state (status: {appr.status})."
            )

        # Execute the approved dangerous tool directly, record observation, and continue loop
        short_term_mem = self.loop.memory_manager.get_run_memory(run.run_id)
        tool_res = await self.loop.tool_registry.execute(
            tool_name=appr.tool_name,
            arguments=appr.tool_args,
            context={
                "tenant_id": task.tenant_id,
                "user_id": task.user_id,
                "roles": user_roles or [],
                "permissions": user_permissions or [],
            },
        )
        obs_text = (
            str(tool_res.output)
            if tool_res.success
            else f"Tool execution error: {tool_res.error}"
        )
        short_term_mem.add_message(
            AgentMessage(role="tool", name=appr.tool_name, content=obs_text)
        )

        run.pending_approval_id = None
        run.status = RunStatus.RUNNING
        task.status = TaskStatus.RUNNING
        run.current_iteration += 1

        # Continue execution loop
        await self.start_run(
            task, run, user_roles=user_roles, user_permissions=user_permissions
        )

    async def stream_run_events(
        self,
        run_id: str,
    ) -> AsyncIterator[str]:
        """Yield Server-Sent Event formatted strings until the run completes."""
        queue = self.subscribe_events(run_id)
        try:
            while True:
                event = await queue.get()
                if event is None:
                    break
                yield event.to_sse()
        finally:
            self.unsubscribe_events(run_id, queue)
