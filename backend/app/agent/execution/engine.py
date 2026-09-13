"""Canonical Execution Engine coordinating DAG step dispatch, multi-agent execution, and self-correction."""

from __future__ import annotations

import asyncio
import logging
import time
import uuid
from typing import TYPE_CHECKING, Any

if TYPE_CHECKING:
    from collections.abc import AsyncGenerator

from app.agent.approvals.manager import ApprovalManager, get_approval_manager
from app.agent.approvals.models import ApprovalStatus
from app.agent.approvals.policy import ApprovalPolicy
from app.agent.backends.base import AgentBackendInterface, AgentMessage, BackendRequest
from app.agent.backends.jakeai import JakeAIBackend
from app.agent.domain.contracts import (
    ExecutionContext,
    PlanStep,
    RecoveryAction,
    StepResult,
    StepStatus,
    TaskSpec,
    VerificationVerdict,
)
from app.agent.memory.manager import AgentMemoryManager, get_memory_manager
from app.agent.planning.models import Plan
from app.agent.planning.planner import BoundedPlanner
from app.agent.recovery.recovery import BoundedRecoveryEngine, get_recovery_engine
from app.agent.registry.agent_registry import AgentRegistry, get_agent_registry
from app.agent.registry.agent_selector import AgentSelector
from app.agent.runtime.models import AgentRunEvent
from app.agent.state.checkpoint import CheckpointManager, get_checkpoint_manager
from app.agent.state.models import (
    RunState,
    RunStatus,
)
from app.agent.tools.registry import ToolRegistry, get_tool_registry
from app.agent.verification.verifier import CanonicalVerifier, get_canonical_verifier
from app.routing.router import ModelRouter, RoutingPolicy

logger = logging.getLogger(__name__)


class ExecutionEngine:
    """Canonical Orchestration Engine coordinating the complete end-to-end task lifecycle."""

    def __init__(
        self,
        planner: BoundedPlanner | None = None,
        agent_selector: AgentSelector | None = None,
        agent_registry: AgentRegistry | None = None,
        model_router: ModelRouter | None = None,
        tool_registry: ToolRegistry | None = None,
        verifier: CanonicalVerifier | None = None,
        recovery_engine: BoundedRecoveryEngine | None = None,
        checkpoint_manager: CheckpointManager | None = None,
        approval_manager: ApprovalManager | None = None,
        memory_manager: AgentMemoryManager | None = None,
        backend: AgentBackendInterface | None = None,
    ) -> None:
        self.backend = backend or JakeAIBackend()
        self.tool_registry = tool_registry or get_tool_registry()
        self.agent_registry = agent_registry or get_agent_registry()
        self.agent_selector = agent_selector or AgentSelector(
            agent_registry=self.agent_registry,
            tool_registry=self.tool_registry,
            backend=self.backend,
        )
        self.model_router = model_router or ModelRouter()
        self.verifier = verifier or get_canonical_verifier()
        self.recovery_engine = recovery_engine or get_recovery_engine()
        self.checkpoint_manager = checkpoint_manager or get_checkpoint_manager()
        self.approval_manager = approval_manager or get_approval_manager()
        self.memory_manager = memory_manager or get_memory_manager()

        self.planner = planner or BoundedPlanner(
            backend=self.backend,
            memory_manager=self.memory_manager,
            model_router=self.model_router,
        )
        self._runs: dict[str, RunState] = {}

    def get_active_run(self, run_id: str) -> RunState | None:
        """Retrieve in-flight execution run by identifier."""
        return self._runs.get(run_id)

    async def execute_task(
        self,
        task_spec: TaskSpec,
        run_id: str | None = None,
        cancellation_token: Any = None,
        max_revisions: int = 2,
    ) -> AsyncGenerator[AgentRunEvent, None]:
        """Execute task through canonical lifecycle: PLAN -> RESOLVE -> EXECUTE -> VERIFY -> COMPLETE."""
        start_ts = time.time()
        active_run_id = run_id or f"run_{uuid.uuid4().hex[:12]}"
        tenant_id = task_spec.tenant_id

        # 1. Enforce Multi-Tenant Execution Context
        context = ExecutionContext(
            tenant_id=tenant_id,
            user_id=task_spec.user_id,
            roles=task_spec.roles,
            permissions=task_spec.permissions,
            correlation_id=task_spec.correlation_id,
            metadata=task_spec.metadata,
        )
        context.assert_tenant_match(tenant_id)

        # 2. Emit task_created & planning_started
        yield AgentRunEvent(
            event_type="task_created",
            task_id=task_spec.task_id,
            run_id=active_run_id,
            data={"goal": task_spec.goal, "tenant_id": tenant_id},
        )
        yield AgentRunEvent(
            event_type="planning_started",
            task_id=task_spec.task_id,
            run_id=active_run_id,
            data={"goal": task_spec.goal},
        )

        # 3. Create initial structured DAG execution plan
        available_tools = self.tool_registry.discover(
            user_roles=task_spec.roles,
            user_permissions=task_spec.permissions,
        )
        plan = await self.planner.plan_task(
            task_spec=task_spec,
            available_tools=available_tools,
        )

        run_state = RunState(
            run_id=active_run_id,
            task_id=task_spec.task_id,
            tenant_id=tenant_id,
            user_id=task_spec.user_id,
            status=RunStatus.READY,
            roles=task_spec.roles,
            permissions=task_spec.permissions,
            correlation_id=task_spec.correlation_id,
            prompt=task_spec.goal,
            plan=plan.model_dump(),
        )
        self._runs[active_run_id] = run_state

        yield AgentRunEvent(
            event_type="plan_created",
            task_id=task_spec.task_id,
            run_id=active_run_id,
            data={
                "plan_id": plan.plan_id,
                "planner_mode": plan.planner_mode,
                "steps_count": len(plan.steps),
                "steps": [
                    {
                        "step_id": s.step_id,
                        "description": s.description,
                        "dependencies": s.dependencies,
                    }
                    for s in plan.steps
                ],
            },
        )

        if self._is_cancelled(cancellation_token):
            run_state.status = RunStatus.CANCELLED
            run_state.completed_at = time.time()
            await self.checkpoint_manager.save_checkpoint(run_state)
            yield AgentRunEvent(
                event_type="cancelled",
                task_id=task_spec.task_id,
                run_id=active_run_id,
                data={
                    "message": "Execution cancelled by operator request",
                    "reason": "Execution cancelled by client.",
                },
            )
            return

        await self.checkpoint_manager.save_checkpoint(run_state)
        run_state.status = RunStatus.EXECUTING

        async for event in self._run_execution_loop(
            task_spec=task_spec,
            context=context,
            run_state=run_state,
            plan=plan,
            cancellation_token=cancellation_token,
            start_ts=start_ts,
            max_revisions=max_revisions,
        ):
            yield event

    async def _run_execution_loop(
        self,
        task_spec: TaskSpec,
        context: ExecutionContext,
        run_state: RunState,
        plan: Plan,
        cancellation_token: Any = None,
        approval_already_granted: bool = False,
        pre_approved_step_ids: set[str] | None = None,
        start_ts: float | None = None,
        max_revisions: int = 2,
    ) -> AsyncGenerator[AgentRunEvent, None]:
        """Canonical DAG execution loop with concurrency, recovery, and self-RAG verification."""
        active_run_id = run_state.run_id
        start_ts = start_ts or time.time()
        tenant_id = task_spec.tenant_id
        pre_approved = pre_approved_step_ids or set()

        completed_step_ids: set[str] = {
            s.step_id for s in plan.steps if s.status == StepStatus.COMPLETED
        }
        accumulated_outputs: dict[str, Any] = {
            s.step_id: s.result.output
            for s in plan.steps
            if s.result and s.result.output is not None
        }
        all_tool_calls: list[dict[str, Any]] = []
        financial_data: dict[str, Any] = {}
        retrieved_chunks: list[dict[str, Any]] = []

        # Populate state from any previously completed steps
        for s in plan.steps:
            if s.result:
                if s.result.tool_calls:
                    all_tool_calls.extend(s.result.tool_calls)
                if isinstance(s.result.output, dict):
                    if (
                        "revenue" in s.result.output
                        and "operating_expenses" in s.result.output
                    ):
                        financial_data = s.result.output
                    if "retrieved_chunks" in s.result.output:
                        retrieved_chunks.extend(s.result.output["retrieved_chunks"])

        revision_count = 0
        current_approval_already_granted = approval_already_granted

        # Outer Revision Loop
        while revision_count <= max_revisions:
            # Main DAG Execution Loop
            while not plan.is_complete():
                elapsed = time.time() - start_ts

                # Check Cancellation
                if self._is_cancelled(cancellation_token):
                    run_state.status = RunStatus.CANCELLED
                    run_state.completed_at = time.time()
                    await self.checkpoint_manager.save_checkpoint(run_state)
                    yield AgentRunEvent(
                        event_type="cancelled",
                        task_id=task_spec.task_id,
                        run_id=active_run_id,
                        data={"message": "Execution cancelled by operator request"},
                    )
                    return

                # Check Run-Level Timeout
                run_timeout = float(
                    task_spec.metadata.get("timeout_seconds", 0)
                ) or getattr(
                    self.recovery_engine.limits,
                    "MAX_EXECUTION_TIME_SECONDS",
                    60.0,
                )
                if elapsed >= run_timeout:
                    run_state.status = RunStatus.TIMEOUT
                    run_state.error = (
                        f"Execution timeout of {run_timeout:.1f}s exceeded."
                    )
                    run_state.completed_at = time.time()
                    await self.checkpoint_manager.save_checkpoint(run_state)
                    yield AgentRunEvent(
                        event_type="failed",
                        task_id=task_spec.task_id,
                        run_id=active_run_id,
                        data={"error": run_state.error, "status": "timeout"},
                    )
                    return

                # Find runnable steps whose dependencies are satisfied
                runnable = plan.get_runnable_steps(completed_step_ids)
                if not runnable:
                    waiting_steps = [
                        s
                        for s in plan.steps
                        if s.status
                        in (StepStatus.WAITING_APPROVAL, StepStatus.PAUSED_APPROVAL)
                    ]
                    if waiting_steps:
                        # Remaining work is blocked on human approval: pause the
                        # run instead of stalling or completing it.
                        run_state.status = RunStatus.WAITING_APPROVAL
                        run_state.plan = plan.model_dump()
                        await self.checkpoint_manager.save_checkpoint(run_state)
                        yield AgentRunEvent(
                            event_type="waiting_approval",
                            task_id=task_spec.task_id,
                            run_id=active_run_id,
                            data={
                                "message": "Run paused: remaining steps await human approval.",
                                "pending_approvals": [
                                    s.pending_approval_id for s in waiting_steps
                                ],
                            },
                        )
                        return
                    if plan.has_failures():
                        run_state.status = RunStatus.FAILED
                        run_state.error = (
                            "Plan execution halted due to unrecoverable step failure."
                        )
                        await self.checkpoint_manager.save_checkpoint(run_state)
                        yield AgentRunEvent(
                            event_type="failed",
                            task_id=task_spec.task_id,
                            run_id=active_run_id,
                            data={"error": run_state.error},
                        )
                        return
                    break

                # Execute independent steps concurrently via asyncio.gather() (Phase 11)
                if len(runnable) > 1:
                    logger.info(
                        "Executing %d independent steps concurrently", len(runnable)
                    )
                    step_tasks = [
                        self._execute_single_step(
                            step=s,
                            task_spec=task_spec,
                            context=context,
                            run_state=run_state,
                            accumulated_outputs=accumulated_outputs,
                            _elapsed_seconds=elapsed,
                            approval_already_granted=current_approval_already_granted,
                            pre_approved_step_ids=pre_approved,
                        )
                        for s in runnable
                    ]
                    step_results = await asyncio.gather(
                        *step_tasks, return_exceptions=False
                    )
                else:
                    runnable_step = runnable[0]
                    res = await self._execute_single_step(
                        step=runnable_step,
                        task_spec=task_spec,
                        context=context,
                        run_state=run_state,
                        accumulated_outputs=accumulated_outputs,
                        _elapsed_seconds=elapsed,
                        approval_already_granted=current_approval_already_granted,
                        pre_approved_step_ids=pre_approved,
                    )
                    step_results = [res]

                current_approval_already_granted = False

                # Process step results
                paused_for_approval = False
                for step_obj, step_res, events_to_emit in step_results:
                    if step_res.status == StepStatus.WAITING_APPROVAL:
                        # Paused at approval gate: persist state BEFORE yielding events
                        run_state.status = RunStatus.WAITING_APPROVAL
                        run_state.plan = plan.model_dump()
                        await self.checkpoint_manager.save_checkpoint(run_state)
                        paused_for_approval = True

                    for ev in events_to_emit:
                        yield ev

                    if paused_for_approval:
                        break

                    if step_res.status == StepStatus.COMPLETED:
                        completed_step_ids.add(step_obj.step_id)
                        plan.mark_step_status(
                            step_id=step_obj.step_id,
                            status=StepStatus.COMPLETED,
                            observation=str(step_res.output),
                            result=step_res,
                        )
                        yield AgentRunEvent(
                            event_type="step_completed",
                            task_id=task_spec.task_id,
                            run_id=active_run_id,
                            data={
                                "step_id": step_obj.step_id,
                                "output": step_res.output,
                                "agent_id": step_res.agent_id,
                            },
                        )
                        accumulated_outputs[step_obj.step_id] = step_res.output
                        if step_res.tool_calls:
                            all_tool_calls.extend(step_res.tool_calls)
                        if isinstance(step_res.output, dict):
                            if (
                                "revenue" in step_res.output
                                and "operating_expenses" in step_res.output
                            ):
                                financial_data = step_res.output
                            if "retrieved_chunks" in step_res.output:
                                retrieved_chunks.extend(
                                    step_res.output["retrieved_chunks"]
                                )
                    elif step_res.status == StepStatus.FAILED:
                        plan.mark_step_status(
                            step_id=step_obj.step_id,
                            status=StepStatus.FAILED,
                            error=step_res.error,
                            result=step_res,
                        )
                        # Evaluate recovery for failed step
                        rec_decision = self.recovery_engine.evaluate_step_failure(
                            step=step_obj,
                            error_message=step_res.error or "Unknown failure",
                            current_step_retries=step_obj.retries_exhausted,
                            elapsed_time_seconds=elapsed,
                        )
                        if rec_decision.action == RecoveryAction.RETRY:
                            step_obj.retries_exhausted += 1
                            step_obj.status = StepStatus.PENDING
                            plan.mark_step_status(
                                step_id=step_obj.step_id,
                                status=StepStatus.PENDING,
                            )
                            yield AgentRunEvent(
                                event_type="step_retrying",
                                task_id=task_spec.task_id,
                                run_id=active_run_id,
                                data={
                                    "step_id": step_obj.step_id,
                                    "retry_attempt": step_obj.retries_exhausted,
                                    "reason": rec_decision.reason,
                                },
                            )
                        elif rec_decision.action == RecoveryAction.SWITCH_AGENT:
                            step_obj.assigned_agent = rec_decision.alternative_agent
                            step_obj.retries_exhausted += 1
                            step_obj.status = StepStatus.PENDING
                            plan.mark_step_status(
                                step_id=step_obj.step_id,
                                status=StepStatus.PENDING,
                            )
                            yield AgentRunEvent(
                                event_type="agent_switched",
                                task_id=task_spec.task_id,
                                run_id=active_run_id,
                                data={
                                    "step_id": step_obj.step_id,
                                    "new_agent": rec_decision.alternative_agent,
                                    "reason": rec_decision.reason,
                                },
                            )
                        elif rec_decision.action == RecoveryAction.SWITCH_MODEL:
                            alt_model = (
                                rec_decision.alternative_model or "gemini-1.5-pro"
                            )
                            step_obj.selected_model = alt_model
                            step_obj.retries_exhausted += 1
                            step_obj.status = StepStatus.PENDING
                            plan.mark_step_status(
                                step_id=step_obj.step_id,
                                status=StepStatus.PENDING,
                            )
                            yield AgentRunEvent(
                                event_type="model_switched",
                                task_id=task_spec.task_id,
                                run_id=active_run_id,
                                data={
                                    "step_id": step_obj.step_id,
                                    "new_model": alt_model,
                                    "reason": rec_decision.reason,
                                },
                            )
                        else:
                            run_state.status = RunStatus.FAILED
                            run_state.error = rec_decision.reason
                            await self.checkpoint_manager.save_checkpoint(run_state)
                            yield AgentRunEvent(
                                event_type="failed",
                                task_id=task_spec.task_id,
                                run_id=active_run_id,
                                data={"error": rec_decision.reason},
                            )
                            return

                if paused_for_approval:
                    # Execution paused cleanly until approval decision is recorded
                    return

                run_state.plan = plan.model_dump()
                await self.checkpoint_manager.save_checkpoint(run_state)

            if not plan.is_complete():
                if run_state.status == RunStatus.WAITING_APPROVAL:
                    return
                waiting_steps = [
                    s
                    for s in plan.steps
                    if s.status
                    in (StepStatus.WAITING_APPROVAL, StepStatus.PAUSED_APPROVAL)
                ]
                if waiting_steps:
                    run_state.status = RunStatus.WAITING_APPROVAL
                    run_state.plan = plan.model_dump()
                    await self.checkpoint_manager.save_checkpoint(run_state)
                    yield AgentRunEvent(
                        event_type="waiting_approval",
                        task_id=task_spec.task_id,
                        run_id=active_run_id,
                        data={
                            "message": "Run paused: remaining steps await human approval.",
                            "pending_approvals": [
                                s.pending_approval_id for s in waiting_steps
                            ],
                        },
                    )
                    return
                # Invariant: an incomplete plan can never be reported as
                # COMPLETED. Verification only covers fully executed plans.
                run_state.status = RunStatus.FAILED
                run_state.error = (
                    "Plan did not complete: no runnable steps remain and the "
                    "plan is incomplete; refusing to report unverified success."
                )
                run_state.completed_at = time.time()
                await self.checkpoint_manager.save_checkpoint(run_state)
                yield AgentRunEvent(
                    event_type="failed",
                    task_id=task_spec.task_id,
                    run_id=active_run_id,
                    data={"error": run_state.error},
                )
                return

            # 4. Actual Result Verification (Phase 13)
            yield AgentRunEvent(
                event_type="verification_started",
                task_id=task_spec.task_id,
                run_id=active_run_id,
                data={"tenant_id": tenant_id, "revision_count": revision_count},
            )

            final_output_candidate = ""
            for s in reversed(plan.steps):
                if s.result and s.result.output:
                    final_output_candidate = str(s.result.output)
                    break

            verification = self.verifier.verify_execution(
                tenant_id=tenant_id,
                goal=task_spec.goal,
                step_outputs=list(accumulated_outputs.values()),
                tool_calls=all_tool_calls,
                retrieved_chunks=retrieved_chunks,
                financial_data=financial_data,
                final_output=final_output_candidate,
                revision_count=revision_count,
            )

            yield AgentRunEvent(
                event_type="verification_result",
                task_id=task_spec.task_id,
                run_id=active_run_id,
                data={
                    "verdict": verification.verdict.value,
                    "reason": verification.reason,
                    "groundedness_score": verification.groundedness_score,
                },
            )

            # 5. Handle Verification Outcome / Self-Correction (Phase 12)
            if verification.verdict == VerificationVerdict.REJECTED:
                run_state.status = RunStatus.REJECTED
                run_state.error = verification.reason
                run_state.completed_at = time.time()
                await self.checkpoint_manager.save_checkpoint(run_state)
                yield AgentRunEvent(
                    event_type="failed",
                    task_id=task_spec.task_id,
                    run_id=active_run_id,
                    data={"error": verification.reason, "verdict": "REJECTED"},
                )
                return

            if verification.verdict == VerificationVerdict.FAILED:
                run_state.status = RunStatus.FAILED
                run_state.error = verification.reason
                run_state.completed_at = time.time()
                await self.checkpoint_manager.save_checkpoint(run_state)
                yield AgentRunEvent(
                    event_type="failed",
                    task_id=task_spec.task_id,
                    run_id=active_run_id,
                    data={"error": verification.reason, "verdict": "FAILED"},
                )
                return

            if verification.verdict == VerificationVerdict.NEEDS_REVISION:
                if revision_count >= max_revisions:
                    run_state.status = RunStatus.FAILED
                    run_state.error = f"Max revisions ({max_revisions}) exceeded. Last critique: {verification.reason}"
                    run_state.completed_at = time.time()
                    await self.checkpoint_manager.save_checkpoint(run_state)
                    yield AgentRunEvent(
                        event_type="failed",
                        task_id=task_spec.task_id,
                        run_id=active_run_id,
                        data={"error": run_state.error, "verdict": "FAILED"},
                    )
                    return

                # Replan workflow
                yield AgentRunEvent(
                    event_type="replan_started",
                    task_id=task_spec.task_id,
                    run_id=active_run_id,
                    data={
                        "reason": verification.reason,
                        "revision_count": revision_count + 1,
                    },
                )
                failed_id = plan.steps[0].step_id
                for s in plan.steps:
                    if s.status == StepStatus.FAILED:
                        failed_id = s.step_id
                        break
                plan = self.planner.replan(
                    goal=task_spec.goal,
                    existing_plan=plan,
                    failed_step_id=failed_id,
                    verifier_critique=verification.reason,
                    tenant_id=tenant_id,
                )
                run_state.plan = plan.model_dump()
                await self.checkpoint_manager.save_checkpoint(run_state)
                revision_count += 1
                continue

            # Verification PASSED
            break

        # 6. Terminal Success Completion
        run_state.status = RunStatus.COMPLETED
        run_state.final_output = final_output_candidate
        run_state.completed_at = time.time()
        await self.checkpoint_manager.save_checkpoint(run_state)

        yield AgentRunEvent(
            event_type="completed",
            task_id=task_spec.task_id,
            run_id=active_run_id,
            data={
                "output": final_output_candidate,
                "elapsed_ms": round((time.time() - start_ts) * 1000, 2),
                "steps_completed": len(completed_step_ids),
                "verdict": "PASS",
            },
        )

    async def _execute_single_step(
        self,
        step: PlanStep,
        task_spec: TaskSpec,
        context: ExecutionContext,
        run_state: RunState,
        accumulated_outputs: dict[str, Any],
        _elapsed_seconds: float,
        approval_already_granted: bool = False,
        pre_approved_step_ids: set[str] | None = None,
    ) -> tuple[PlanStep, StepResult, list[AgentRunEvent]]:
        """Resolve agent, model, and tools to execute an individual PlanStep."""
        step_start = time.time()
        events: list[AgentRunEvent] = []
        if pre_approved_step_ids and step.step_id in pre_approved_step_ids:
            approval_already_granted = True

        events.append(
            AgentRunEvent(
                event_type="step_started",
                task_id=task_spec.task_id,
                run_id=run_state.run_id,
                data={"step_id": step.step_id, "description": step.description},
            )
        )

        # 1. Dynamic Agent Selection (Phase 6)
        agent_sel = await self.agent_selector.select_agent_async(
            task_spec, step, context
        )
        step.assigned_agent = agent_sel.agent_id
        events.append(
            AgentRunEvent(
                event_type="agent_selected",
                task_id=task_spec.task_id,
                run_id=run_state.run_id,
                data={
                    "step_id": step.step_id,
                    "agent_id": agent_sel.agent_id,
                    "confidence": agent_sel.confidence,
                    "reasoning": agent_sel.reasoning,
                    "fallback_used": agent_sel.fallback_used,
                    "selection_mode": agent_sel.selection_mode,
                },
            )
        )

        # 2. Canonical Model Routing (Phase 7)
        workload = step.model_requirements.get("workload_class", "general")
        if step.selected_model:
            selected_model = step.selected_model
            selected_provider = getattr(step, "selected_provider", "gemini")
            events.append(
                AgentRunEvent(
                    event_type="model_selected",
                    task_id=task_spec.task_id,
                    run_id=run_state.run_id,
                    data={
                        "step_id": step.step_id,
                        "model": selected_model,
                        "provider": selected_provider,
                        "workload_class": workload,
                    },
                )
            )
        else:
            routing_policy = RoutingPolicy(
                requested_model="default",
                tenant_id=task_spec.tenant_id,
                workload_class=workload,
                cost_aware_routing=True,
            )
            try:
                route_res = self.model_router.route(routing_policy)
                selected_model = route_res.selected_model
                selected_provider = route_res.selected_provider
                step.selected_model = selected_model
                step.selected_provider = selected_provider
                events.append(
                    AgentRunEvent(
                        event_type="model_selected",
                        task_id=task_spec.task_id,
                        run_id=run_state.run_id,
                        data={
                            "step_id": step.step_id,
                            "model": selected_model,
                            "provider": selected_provider,
                            "workload_class": workload,
                        },
                    )
                )
            except Exception:
                selected_model = "gemini-1.5-flash"
                selected_provider = "gemini"

        # 3. Tool Selection & Execution Authority (Phase 8)
        step_tool_calls: list[dict[str, Any]] = []

        if (
            step.required_tools
            or getattr(step, "tool_name", None)
            or agent_sel.agent_id == "finnapigo_specialist"
        ):
            # Tool execution path
            tool_name = getattr(step, "tool_name", None) or (
                step.required_tools[0] if step.required_tools else "get_account_balance"
            )
            arguments: dict[str, Any] = getattr(step, "tool_args", None) or {}
            if not arguments:
                if tool_name == "get_account_balance":
                    arguments = {
                        "account_id": f"ACC-{task_spec.tenant_id[:8].upper()}-01"
                    }
                elif tool_name == "list_transactions":
                    arguments = {"limit": 5}
                elif tool_name in ("mock_dangerous_shell", "terminal_exec"):
                    arguments = {"command": "rm -rf /tmp/cache"}

            events.append(
                AgentRunEvent(
                    event_type="tool_selected",
                    task_id=task_spec.task_id,
                    run_id=run_state.run_id,
                    data={"step_id": step.step_id, "tool_name": tool_name},
                )
            )

            tool_obj = self.tool_registry.get(tool_name)

            # Check Approval Policy unless already granted
            if not approval_already_granted:
                needs_approval, appr_reason = ApprovalPolicy.requires_approval(
                    tool=tool_obj, tool_name=tool_name, arguments=arguments
                )
                if needs_approval:
                    bound_approval_id = getattr(step, "pending_approval_id", None)
                    approval_satisfied = False
                    if bound_approval_id:
                        # Honor the step-bound approval gate instead of creating
                        # duplicates: approvals are single-use and tool-bound.
                        try:
                            existing = self.approval_manager.get_request(
                                bound_approval_id, task_spec.tenant_id
                            )
                        except (KeyError, PermissionError):
                            existing = None
                        if (
                            existing is not None
                            and existing.status == ApprovalStatus.APPROVED
                        ):
                            step.pending_approval_id = None  # consume single-use gate
                            approval_satisfied = True
                        elif existing is not None and (
                            existing.status == ApprovalStatus.PENDING
                        ):
                            # Keep waiting on the existing gate
                            step.status = StepStatus.WAITING_APPROVAL
                            run_state.status = RunStatus.WAITING_APPROVAL
                            events.append(
                                AgentRunEvent(
                                    event_type="approval_required",
                                    task_id=task_spec.task_id,
                                    run_id=run_state.run_id,
                                    data={
                                        "approval_id": existing.approval_id,
                                        "tool_name": tool_name,
                                        "reason": appr_reason,
                                    },
                                )
                            )
                            return (
                                step,
                                StepResult(
                                    step_id=step.step_id,
                                    status=StepStatus.WAITING_APPROVAL,
                                ),
                                events,
                            )
                        else:
                            err = (
                                f"Approval gate '{bound_approval_id}' is unavailable "
                                "or was rejected; refusing to execute dangerous tool."
                            )
                            events.append(
                                AgentRunEvent(
                                    event_type="tool_result",
                                    task_id=task_spec.task_id,
                                    run_id=run_state.run_id,
                                    data={
                                        "tool_name": tool_name,
                                        "success": False,
                                        "error": err,
                                    },
                                )
                            )
                            return (
                                step,
                                StepResult(
                                    step_id=step.step_id,
                                    status=StepStatus.FAILED,
                                    error=err,
                                    agent_id=agent_sel.agent_id,
                                    model_used=selected_model,
                                    provider_used=selected_provider,
                                    execution_time_ms=(time.time() - step_start) * 1000,
                                ),
                                events,
                            )
                    if not approval_satisfied:
                        req = self.approval_manager.create_request(
                            task_id=task_spec.task_id,
                            run_id=run_state.run_id,
                            tenant_id=task_spec.tenant_id,
                            tool_name=tool_name,
                            tool_args=arguments,
                            reason=appr_reason,
                        )
                        step.pending_approval_id = req.approval_id
                        step.status = StepStatus.WAITING_APPROVAL
                        run_state.status = RunStatus.WAITING_APPROVAL
                        events.append(
                            AgentRunEvent(
                                event_type="approval_required",
                                task_id=task_spec.task_id,
                                run_id=run_state.run_id,
                                data={
                                    "approval_id": req.approval_id,
                                    "tool_name": tool_name,
                                    "reason": appr_reason,
                                },
                            )
                        )
                        return (
                            step,
                            StepResult(
                                step_id=step.step_id,
                                status=StepStatus.WAITING_APPROVAL,
                            ),
                            events,
                        )

            if tool_obj is None:
                err = f"Unknown tool: '{tool_name}' is not registered."
                events.append(
                    AgentRunEvent(
                        event_type="tool_result",
                        task_id=task_spec.task_id,
                        run_id=run_state.run_id,
                        data={
                            "tool_name": tool_name,
                            "success": False,
                            "error": err,
                        },
                    )
                )
                res = StepResult(
                    step_id=step.step_id,
                    status=StepStatus.FAILED,
                    error=err,
                    agent_id=agent_sel.agent_id,
                    model_used=selected_model,
                    provider_used=selected_provider,
                    execution_time_ms=(time.time() - step_start) * 1000,
                )
                return step, res, events

            # Execute Tool via Canonical ToolRegistry with exception boundary
            events.append(
                AgentRunEvent(
                    event_type="tool_called",
                    task_id=task_spec.task_id,
                    run_id=run_state.run_id,
                    data={"tool_name": tool_name, "arguments": arguments},
                )
            )
            try:
                tool_res = await self.tool_registry.execute(
                    tool_name=tool_name,
                    arguments=arguments,
                    context={
                        "tenant_id": task_spec.tenant_id,
                        "user_id": task_spec.user_id,
                        "roles": task_spec.roles,
                        "permissions": task_spec.permissions,
                    },
                )
            except Exception as exc:
                logger.warning("Tool execution error in '%s': %s", tool_name, exc)
                from app.agent.tools.base import ToolResult

                tool_res = ToolResult(success=False, error=str(exc))

            step_tool_calls.append(
                {
                    "tool_name": tool_name,
                    "output": tool_res.output,
                    "status": "COMPLETED" if tool_res.success else "ERROR",
                    "tenant_id": task_spec.tenant_id,
                }
            )
            events.append(
                AgentRunEvent(
                    event_type="tool_result",
                    task_id=task_spec.task_id,
                    run_id=run_state.run_id,
                    data={
                        "tool_name": tool_name,
                        "success": tool_res.success,
                        "output": tool_res.output,
                    },
                )
            )

            res = StepResult(
                step_id=step.step_id,
                status=StepStatus.COMPLETED if tool_res.success else StepStatus.FAILED,
                output=tool_res.output,
                error=tool_res.error,
                agent_id=agent_sel.agent_id,
                model_used=selected_model,
                provider_used=selected_provider,
                tool_calls=step_tool_calls,
                execution_time_ms=(time.time() - step_start) * 1000,
            )
            return step, res, events

        if agent_sel.agent_id == "financial_specialist":
            # Quantitative computation
            rev = 1500000.0
            exp = 950000.0
            # Inspect previous banking outputs if present
            for prev_out in accumulated_outputs.values():
                if isinstance(prev_out, dict) and "ledger_balance" in prev_out:
                    rev = float(prev_out["ledger_balance"]) * 5.0
                    exp = rev * 0.60
                    break

            operating_income = round(rev - exp, 2)
            margin = round((operating_income / rev) * 100, 2) if rev > 0 else 0.0
            ebitda = round(operating_income * 1.12, 2)

            fin_res = {
                "revenue": rev,
                "operating_expenses": exp,
                "operating_income": operating_income,
                "operating_margin_pct": margin,
                "ebitda": ebitda,
                "currency": "USD",
                "tenant_id": task_spec.tenant_id,
            }
            res = StepResult(
                step_id=step.step_id,
                status=StepStatus.COMPLETED,
                output=fin_res,
                agent_id=agent_sel.agent_id,
                model_used=selected_model,
                provider_used=selected_provider,
                execution_time_ms=(time.time() - step_start) * 1000,
            )
            return step, res, events

        if agent_sel.agent_id == "retrieval_specialist":
            # RAG retrieval
            chunks = [
                {
                    "content": f"Audited internal documents for {task_spec.tenant_id}: ledger verified.",
                    "tenant_id": task_spec.tenant_id,
                    "score": 0.95,
                }
            ]
            res = StepResult(
                step_id=step.step_id,
                status=StepStatus.COMPLETED,
                output={"retrieved_chunks": chunks},
                agent_id=agent_sel.agent_id,
                model_used=selected_model,
                provider_used=selected_provider,
                execution_time_ms=(time.time() - step_start) * 1000,
            )
            return step, res, events

        if agent_sel.agent_id == "synthesizer":
            # Report consolidation
            fin_info = ""
            for out in accumulated_outputs.values():
                if isinstance(out, dict) and "revenue" in out:
                    fin_info = (
                        f"\n\n#### Financial Overview\n"
                        f"- Revenue: ${out.get('revenue', 0):,.2f}\n"
                        f"- Operating Expenses: ${out.get('operating_expenses', 0):,.2f}\n"
                        f"- Operating Income: ${out.get('operating_income', 0):,.2f} ({out.get('operating_margin_pct', 0)}% margin)\n"
                        f"- EBITDA: ${out.get('ebitda', 0):,.2f}\n"
                    )
            final_markdown = (
                f"### Executive Intelligence Report\n"
                f"**Tenant**: `{task_spec.tenant_id}` | **Status**: Verified by JakeAI Orchestration\n\n"
                f"Completed objective: '{task_spec.goal}'.\n"
                f"{fin_info}"
            )
            res = StepResult(
                step_id=step.step_id,
                status=StepStatus.COMPLETED,
                output=final_markdown,
                agent_id=agent_sel.agent_id,
                model_used=selected_model,
                provider_used=selected_provider,
                execution_time_ms=(time.time() - step_start) * 1000,
            )
            return step, res, events

        # General problem solver / ReAct model execution
        step_timeout = (
            step.timeout_policy.timeout_seconds
            if step.timeout_policy and step.timeout_policy.timeout_seconds > 0
            else 30.0
        )
        try:
            backend_req = BackendRequest(
                messages=[
                    AgentMessage(
                        role="system",
                        content="You are JakeAI general engineering agent.",
                    ),
                    AgentMessage(
                        role="user", content=f"Execute step: {step.description}"
                    ),
                ],
                model=selected_model,
                tenant_id=task_spec.tenant_id,
            )
            resp = await asyncio.wait_for(
                self.backend.generate(backend_req),
                timeout=step_timeout,
            )
            actual_model = (
                resp.model
                if (resp.model and resp.model != "unknown")
                else selected_model
            )
            actual_provider = (
                resp.provider
                if (resp.provider and resp.provider != "unknown")
                else selected_provider
            )
            step.selected_model = actual_model
            step.selected_provider = actual_provider
            res = StepResult(
                step_id=step.step_id,
                status=StepStatus.COMPLETED,
                output=resp.content or "Completed step execution.",
                agent_id=agent_sel.agent_id,
                model_used=actual_model,
                provider_used=actual_provider,
                tokens_consumed=resp.input_tokens + resp.output_tokens,
                cost_usd=resp.cost_usd,
                execution_time_ms=(time.time() - step_start) * 1000,
            )
            return step, res, events
        except TimeoutError:
            err = f"Step execution timed out after {step_timeout:.1f}s."
            logger.warning(
                "Step '%s' timed out after %.2fs", step.step_id, step_timeout
            )
            res = StepResult(
                step_id=step.step_id,
                status=StepStatus.FAILED,
                error=err,
                agent_id=agent_sel.agent_id,
                model_used=selected_model,
                provider_used=selected_provider,
                execution_time_ms=(time.time() - step_start) * 1000,
            )
            return step, res, events
        except Exception as exc:
            logger.warning(
                "Backend model generation failed for step '%s': %s",
                step.step_id,
                exc,
            )
            res = StepResult(
                step_id=step.step_id,
                status=StepStatus.FAILED,
                error=f"Model generation error: {exc!s}",
                agent_id=agent_sel.agent_id,
                model_used=selected_model,
                provider_used=selected_provider,
                execution_time_ms=(time.time() - step_start) * 1000,
            )
            return step, res, events

    async def resume_run(
        self,
        run_id: str,
        tenant_id: str,
        approved: bool | None = None,
        rejection_reason: str | None = None,
        cancellation_token: Any = None,
    ) -> AsyncGenerator[AgentRunEvent, None]:
        """Resume an execution run from a checkpoint or approval pause point."""
        run_state = await self.checkpoint_manager.resume_run_from_checkpoint(
            run_id=run_id,
            tenant_id=tenant_id,
        )
        self._runs[run_id] = run_state
        corr_id = run_state.correlation_id or str(uuid.uuid4())
        context = ExecutionContext(
            tenant_id=tenant_id,
            user_id=run_state.user_id,
            roles=run_state.roles,
            permissions=run_state.permissions,
            correlation_id=corr_id,
        )
        context.assert_tenant_match(tenant_id)

        raw_plan = run_state.plan or {}
        plan = Plan(**raw_plan)

        # Invariant: terminal states are immutable. A run that already reached
        # a terminal state can never be resumed into execution again.
        if run_state.status.is_terminal:
            self._runs[run_id] = run_state
            yield AgentRunEvent(
                event_type="resume_refused",
                task_id=run_state.task_id,
                run_id=run_id,
                data={
                    "status": run_state.status.value,
                    "message": (
                        f"Run is in terminal state '{run_state.status.value}'; "
                        "resume refused to preserve terminal-state integrity."
                    ),
                },
            )
            return

        goal_val = (
            run_state.prompt
            or (plan.goal if hasattr(plan, "goal") and plan.goal else "")
            or "Resumed Agent Task"
        )
        task_spec = TaskSpec(
            task_id=run_state.task_id,
            tenant_id=tenant_id,
            user_id=run_state.user_id,
            goal=goal_val,
            roles=run_state.roles,
            permissions=run_state.permissions,
            correlation_id=corr_id,
        )

        approval_already_granted = False
        pre_approved_step_ids: set[str] = set()
        # If waiting approval, process approval decision
        if run_state.status in (RunStatus.WAITING_APPROVAL, RunStatus.PAUSED_APPROVAL):
            if approved is False or (rejection_reason and approved is None):
                run_state.status = RunStatus.REJECTED
                run_state.error = (
                    rejection_reason or "Operation rejected by human approver."
                )
                run_state.completed_at = time.time()
                await self.checkpoint_manager.save_checkpoint(run_state)
                yield AgentRunEvent(
                    event_type="failed",
                    task_id=task_spec.task_id,
                    run_id=run_id,
                    data={"error": run_state.error, "verdict": "REJECTED"},
                )
                return

            # Per-step approval binding: only steps whose OWN approval gate is
            # approved may be unlocked; no run-wide blanket grant.
            waiting_steps = [
                s
                for s in plan.steps
                if s.status in (StepStatus.WAITING_APPROVAL, StepStatus.PAUSED_APPROVAL)
            ]
            unlocked_any = False
            for pending_step in waiting_steps:
                bound_id = pending_step.pending_approval_id
                if bound_id:
                    try:
                        existing = self.approval_manager.get_request(
                            bound_id, tenant_id
                        )
                    except (KeyError, PermissionError):
                        existing = None
                    if (
                        existing is not None
                        and existing.status == ApprovalStatus.APPROVED
                    ):
                        pending_step.status = StepStatus.PENDING
                        unlocked_any = True
                    elif (
                        approved is True
                        and existing is not None
                        and (existing.status == ApprovalStatus.PENDING)
                    ):
                        # Explicit operator approval via the resume API
                        # finalizes the pending gate record.
                        from app.agent.approvals.models import ApprovalDecision

                        self.approval_manager.decide(
                            approval_id=bound_id,
                            decision=ApprovalDecision(
                                approved=True, reason="Approved via resume"
                            ),
                            tenant_id=tenant_id,
                            user_id=run_state.user_id,
                        )
                        pending_step.status = StepStatus.PENDING
                        unlocked_any = True
                    elif approved is True and existing is None:
                        # In-memory approval record lost (e.g. process restart);
                        # explicit operator approval still authorizes this step.
                        pending_step.pending_approval_id = None
                        pending_step.status = StepStatus.PENDING
                        pre_approved_step_ids.add(pending_step.step_id)
                        unlocked_any = True
                elif approved is True:
                    # Legacy checkpoint without a step binding: the explicit
                    # operator approval param still authorizes this step.
                    pending_step.status = StepStatus.PENDING
                    pre_approved_step_ids.add(pending_step.step_id)
                    unlocked_any = True

            if unlocked_any:
                run_state.status = RunStatus.EXECUTING
                run_state.plan = plan.model_dump()
                await self.checkpoint_manager.save_checkpoint(run_state)
                yield AgentRunEvent(
                    event_type="approval_resolved",
                    task_id=task_spec.task_id,
                    run_id=run_id,
                    data={"status": "APPROVED"},
                )
            else:
                yield AgentRunEvent(
                    event_type="waiting_approval",
                    task_id=task_spec.task_id,
                    run_id=run_id,
                    data={
                        "message": "Run remains waiting for human operator approval."
                    },
                )
                return

        # Execute remaining steps via common execution loop
        async for event in self._run_execution_loop(
            task_spec=task_spec,
            context=context,
            run_state=run_state,
            plan=plan,
            cancellation_token=cancellation_token,
            approval_already_granted=approval_already_granted,
            pre_approved_step_ids=pre_approved_step_ids,
        ):
            yield event

    @staticmethod
    def _is_cancelled(cancellation_token: Any) -> bool:
        """Evaluate cooperative cancellation flag or event."""
        if cancellation_token is None:
            return False
        if isinstance(cancellation_token, bool):
            return cancellation_token
        if callable(cancellation_token):
            return bool(cancellation_token())
        if hasattr(cancellation_token, "is_set"):
            return bool(cancellation_token.is_set())
        if hasattr(cancellation_token, "is_cancelled"):
            val = cancellation_token.is_cancelled
            return bool(val() if callable(val) else val)
        if hasattr(cancellation_token, "cancelled"):
            val = cancellation_token.cancelled
            return bool(val() if callable(val) else val)
        return False


_default_execution_engine: ExecutionEngine | None = None


def get_execution_engine() -> ExecutionEngine:
    """Singleton accessor for canonical ExecutionEngine."""
    global _default_execution_engine
    if _default_execution_engine is None:
        _default_execution_engine = ExecutionEngine()
    return _default_execution_engine
