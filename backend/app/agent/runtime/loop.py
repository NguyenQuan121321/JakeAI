"""Core Agent Execution Loop orchestrating planning, tool execution, and approval gates."""

from __future__ import annotations

import logging
import time
from typing import TYPE_CHECKING, Any

from app.agent.approvals.policy import ApprovalPolicy
from app.agent.backends.base import AgentMessage
from app.agent.planning.models import NextActionType
from app.agent.runtime.models import AgentConfig, AgentRunEvent
from app.agent.state.models import (
    RunState,
    RunStatus,
    StepExecutionRecord,
    TaskState,
    TaskStatus,
)
from app.agent.telemetry import agent_telemetry

if TYPE_CHECKING:
    from collections.abc import AsyncIterator

    from app.agent.approvals.manager import ApprovalManager
    from app.agent.memory.manager import AgentMemoryManager
    from app.agent.planning.planner import BoundedPlanner
    from app.agent.state.checkpoint import CheckpointManager
    from app.agent.tools.registry import ToolRegistry

logger = logging.getLogger(__name__)


class AgentExecutionLoop:
    """Iterative execution loop enforcing safety policies, bounded iterations, and approvals."""

    def __init__(
        self,
        planner: BoundedPlanner,
        tool_registry: ToolRegistry,
        memory_manager: AgentMemoryManager,
        checkpoint_manager: CheckpointManager,
        approval_manager: ApprovalManager,
        config: AgentConfig | None = None,
    ) -> None:
        self.planner = planner
        self.tool_registry = tool_registry
        self.memory_manager = memory_manager
        self.checkpoint_manager = checkpoint_manager
        self.approval_manager = approval_manager
        self.config = config or AgentConfig()

    async def execute(
        self,
        task: TaskState,
        run: RunState,
        cancellation_requested: Any = None,  # Callable or threading.Event
        user_roles: list[str] | None = None,
        user_permissions: list[str] | None = None,
    ) -> AsyncIterator[AgentRunEvent]:
        """Run execution loop until completion, failure, cancellation, or approval gate."""
        start_ts = time.time()
        short_term_mem = self.memory_manager.get_run_memory(run.run_id)

        # Populate initial user goal if memory is empty
        if not short_term_mem.get_messages():
            short_term_mem.add_message(AgentMessage(role="user", content=task.goal))

        # Discover available tools for the user context
        available_tools = self.tool_registry.discover(
            user_roles=user_roles,
            user_permissions=user_permissions,
        )
        if self.config.allowed_tools:
            available_tools = [t for t in available_tools if t.name in self.config.allowed_tools]

        # Initialize or retrieve plan
        plan = self.planner.create_initial_plan(task.goal, available_tools)

        run.status = RunStatus.RUNNING
        task.status = TaskStatus.RUNNING
        yield AgentRunEvent(
            event_type="run_started",
            task_id=task.task_id,
            run_id=run.run_id,
            data={"goal": task.goal, "max_iterations": run.max_iterations},
        )

        while run.current_iteration < run.max_iterations:
            # 1. Cooperative Cancellation Check
            is_cancelled = False
            if callable(cancellation_requested):
                is_cancelled = cancellation_requested()
            elif cancellation_requested is not None and getattr(cancellation_requested, "is_set", None):
                is_cancelled = cancellation_requested.is_set()

            if is_cancelled or run.status == RunStatus.CANCELLED:
                run.status = RunStatus.CANCELLED
                task.status = TaskStatus.CANCELLED
                run.completed_at = time.time()
                await self.checkpoint_manager.save_checkpoint(run, short_term_mem.snapshot())
                agent_telemetry.record_run_cancelled(task.tenant_id)
                yield AgentRunEvent(
                    event_type="cancelled",
                    task_id=task.task_id,
                    run_id=run.run_id,
                    data={"message": "Run cancelled cooperatively by operator"},
                )
                return

            elapsed = time.time() - start_ts

            # 2. Query Planner for Next Action
            action = await self.planner.determine_next_action(
                goal=task.goal,
                plan=plan,
                history=short_term_mem.get_messages(),
                available_tools=available_tools,
                current_iteration=run.current_iteration,
                elapsed_time_seconds=elapsed,
                tenant_id=task.tenant_id,
            )

            # 3. Action Dispatch: Finish
            if action.action_type == NextActionType.FINISH:
                run.status = RunStatus.COMPLETED
                task.status = TaskStatus.COMPLETED
                run.final_output = action.final_output
                run.completed_at = time.time()
                await self.checkpoint_manager.save_checkpoint(run, short_term_mem.snapshot())
                agent_telemetry.record_run_completed(
                    tenant_id=task.tenant_id,
                    duration_ms=(time.time() - start_ts) * 1000.0,
                    tokens=run.tokens_consumed,
                    cost_usd=run.cost_usd,
                )
                yield AgentRunEvent(
                    event_type="completed",
                    task_id=task.task_id,
                    run_id=run.run_id,
                    data={"output": run.final_output, "iterations": run.current_iteration + 1},
                )
                return

            # 4. Action Dispatch: Failure / Timeout
            if action.action_type == NextActionType.FAIL:
                run.status = RunStatus.FAILED
                task.status = TaskStatus.FAILED
                run.error = action.error or "Goal failed by planner decision."
                run.completed_at = time.time()
                await self.checkpoint_manager.save_checkpoint(run, short_term_mem.snapshot())
                agent_telemetry.record_run_failed(task.tenant_id, run.error)
                yield AgentRunEvent(
                    event_type="failed",
                    task_id=task.task_id,
                    run_id=run.run_id,
                    data={"error": run.error, "iterations": run.current_iteration + 1},
                )
                return

            # 5. Action Dispatch: Tool Call
            if action.action_type == NextActionType.TOOL_CALL:
                tool_name = action.tool_name or "unknown"
                tool_args = action.tool_args or {}
                tool_obj = self.tool_registry.get(tool_name)

                # 5a. Server-Side Approval Verification
                needs_approval, appr_reason = ApprovalPolicy.requires_approval(
                    tool=tool_obj,
                    tool_name=tool_name,
                    arguments=tool_args,
                )

                if needs_approval and self.config.require_human_approval_for_dangerous:
                    # Check if this tool invocation was already approved in this run
                    # If not, pause execution and wait for human decision
                    appr_req = self.approval_manager.create_request(
                        task_id=task.task_id,
                        run_id=run.run_id,
                        tenant_id=task.tenant_id,
                        tool_name=tool_name,
                        tool_args=tool_args,
                        reason=appr_reason,
                    )
                    run.status = RunStatus.PAUSED_APPROVAL
                    task.status = TaskStatus.PAUSED_APPROVAL
                    run.pending_approval_id = appr_req.approval_id

                    # Save checkpoint for resumption
                    await self.checkpoint_manager.save_checkpoint(run, short_term_mem.snapshot())
                    agent_telemetry.record_approval_requested(tool_name, task.tenant_id)

                    yield AgentRunEvent(
                        event_type="approval_required",
                        task_id=task.task_id,
                        run_id=run.run_id,
                        data={
                            "approval_id": appr_req.approval_id,
                            "tool_name": tool_name,
                            "arguments": tool_args,
                            "reason": appr_reason,
                        },
                    )
                    # Halt loop until approved
                    return

                # 5b. Tool Execution
                step_start = time.time()
                yield AgentRunEvent(
                    event_type="tool_call",
                    task_id=task.task_id,
                    run_id=run.run_id,
                    data={"tool_name": tool_name, "arguments": tool_args, "thought": action.thought},
                )

                tool_res = await self.tool_registry.execute(
                    tool_name=tool_name,
                    arguments=tool_args,
                    context={
                        "tenant_id": task.tenant_id,
                        "user_id": task.user_id,
                        "roles": user_roles or [],
                        "permissions": user_permissions or [],
                    },
                )
                step_duration = (time.time() - step_start) * 1000.0

                agent_telemetry.record_tool_call(tool_name, task.tenant_id)
                agent_telemetry.record_step_executed(task.tenant_id)

                obs_text = (
                    str(tool_res.output)
                    if tool_res.success
                    else f"Tool execution error: {tool_res.error}"
                )

                # Record in short-term memory
                short_term_mem.add_message(
                    AgentMessage(
                        role="tool",
                        name=tool_name,
                        content=obs_text,
                    )
                )

                # Record in run steps
                step_rec = StepExecutionRecord(
                    step_number=run.current_iteration,
                    description=action.thought or f"Executed {tool_name}",
                    action_type="tool_call",
                    tool_name=tool_name,
                    tool_args=tool_args,
                    observation=obs_text,
                    status="completed" if tool_res.success else "failed",
                    execution_time_ms=step_duration,
                )
                run.steps.append(step_rec)

                yield AgentRunEvent(
                    event_type="observation",
                    task_id=task.task_id,
                    run_id=run.run_id,
                    data={
                        "tool_name": tool_name,
                        "success": tool_res.success,
                        "output": tool_res.output,
                        "error": tool_res.error,
                        "duration_ms": step_duration,
                    },
                )

            run.current_iteration += 1
            await self.checkpoint_manager.save_checkpoint(run, short_term_mem.snapshot())

        # If loop exited naturally due to iteration ceiling
        run.status = RunStatus.FAILED
        task.status = TaskStatus.FAILED
        run.error = f"Exceeded maximum iterations limit ({run.max_iterations})."
        run.completed_at = time.time()
        await self.checkpoint_manager.save_checkpoint(run, short_term_mem.snapshot())
        agent_telemetry.record_run_failed(task.tenant_id, run.error)
        yield AgentRunEvent(
            event_type="failed",
            task_id=task.task_id,
            run_id=run.run_id,
            data={"error": run.error, "iterations": run.current_iteration},
        )
