"""Workflow execution engine executing observable, resumable multi-step pipelines."""

from __future__ import annotations

import logging
import time
import uuid
from typing import TYPE_CHECKING, Any

from app.agent.backends.base import AgentBackendInterface, AgentMessage, BackendRequest
from app.agent.workflows.models import (
    StepType,
    WorkflowDefinition,
    WorkflowExecution,
    WorkflowExecutionStatus,
)

if TYPE_CHECKING:
    from app.agent.tools.registry import ToolRegistry

logger = logging.getLogger(__name__)


class WorkflowEngine:
    """Orchestrates structured task pipelines with step-level observability and resumption."""

    def __init__(
        self,
        tool_registry: ToolRegistry,
        backend: AgentBackendInterface | None = None,
    ) -> None:
        self.tool_registry = tool_registry
        self.backend = backend
        self._executions: dict[str, WorkflowExecution] = {}

    def create_execution(
        self,
        workflow: WorkflowDefinition,
        tenant_id: str,
    ) -> WorkflowExecution:
        """Instantiate a new tracked workflow execution."""
        exec_id = f"wf_exec_{uuid.uuid4().hex[:12]}"
        execution = WorkflowExecution(
            execution_id=exec_id,
            workflow_id=workflow.workflow_id,
            tenant_id=tenant_id,
            status=WorkflowExecutionStatus.PENDING,
        )
        self._executions[exec_id] = execution
        return execution

    async def run(
        self,
        workflow: WorkflowDefinition,
        execution: WorkflowExecution,
        initial_inputs: dict[str, Any] | None = None,
    ) -> WorkflowExecution:
        """Execute or resume workflow steps sequentially with observation capture."""
        execution.status = WorkflowExecutionStatus.RUNNING
        execution.updated_at = time.time()
        context_vars = dict(initial_inputs or {})
        context_vars.update(execution.step_results)

        total_steps = len(workflow.steps)

        while execution.current_step_index < total_steps:
            step = workflow.steps[execution.current_step_index]
            logger.debug(
                "Executing workflow '%s' step %d: %s",
                workflow.workflow_id,
                execution.current_step_index,
                step.name,
            )

            try:
                if step.step_type == StepType.TOOL_CALL:
                    if not step.tool_name:
                        raise ValueError(f"Step '{step.name}' missing tool_name.")

                    # Interpolate arguments
                    resolved_args: dict[str, Any] = {}
                    for k, v in step.arguments.items():
                        if isinstance(v, str) and v.startswith("$"):
                            var_key = v[1:]
                            resolved_args[k] = context_vars.get(var_key, v)
                        else:
                            resolved_args[k] = v

                    tool_res = await self.tool_registry.execute(
                        tool_name=step.tool_name,
                        arguments=resolved_args,
                        context={"tenant_id": execution.tenant_id},
                    )

                    if not tool_res.success:
                        execution.status = WorkflowExecutionStatus.FAILED
                        execution.error = f"Step '{step.name}' failed: {tool_res.error}"
                        return execution

                    execution.step_results[step.step_id] = tool_res.output
                    context_vars[step.step_id] = tool_res.output

                elif step.step_type == StepType.MODEL_CALL:
                    if self.backend is None:
                        raise ValueError(
                            "Workflow requires backend for MODEL_CALL step."
                        )

                    prompt_text = step.prompt_template or "Perform step"
                    for k, v in context_vars.items():
                        prompt_text = prompt_text.replace(f"${k}", str(v))

                    req = BackendRequest(
                        messages=[AgentMessage(role="user", content=prompt_text)],
                        tenant_id=execution.tenant_id,
                    )
                    resp = await self.backend.generate(req)
                    execution.step_results[step.step_id] = resp.content
                    context_vars[step.step_id] = resp.content

                execution.current_step_index += 1
                execution.updated_at = time.time()

            except Exception as exc:
                execution.status = WorkflowExecutionStatus.FAILED
                execution.error = str(exc)
                logger.error(
                    "Workflow '%s' crashed at step '%s': %s",
                    workflow.workflow_id,
                    step.name,
                    exc,
                )
                return execution

        execution.status = WorkflowExecutionStatus.COMPLETED
        execution.updated_at = time.time()
        return execution
