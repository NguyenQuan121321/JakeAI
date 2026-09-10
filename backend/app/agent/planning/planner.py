"""Bounded planning engine preventing runaway agent loops and orchestrating goal completion."""

from __future__ import annotations

import json
import logging
import uuid
from typing import TYPE_CHECKING

from app.agent.backends.base import (
    AgentBackendInterface,
    AgentMessage,
    BackendRequest,
)
from app.agent.planning.models import (
    NextAction,
    NextActionType,
    Plan,
    PlanStep,
    PlanStepStatus,
)

if TYPE_CHECKING:
    from app.agent.memory.manager import AgentMemoryManager
    from app.agent.tools.base import ToolMetadata

logger = logging.getLogger(__name__)


class BoundedPlanner:
    """Bounded planning engine with hard iteration ceilings and timeout defenses."""

    def __init__(
        self,
        backend: AgentBackendInterface,
        max_iterations: int = 10,
        timeout_seconds: float = 60.0,
        memory_manager: AgentMemoryManager | None = None,
    ) -> None:
        self.backend = backend
        self.max_iterations = max_iterations
        self.timeout_seconds = timeout_seconds
        if memory_manager is None:
            from app.agent.memory.manager import get_memory_manager

            self.memory_manager = get_memory_manager()
        else:
            self.memory_manager = memory_manager

    def create_initial_plan(
        self,
        goal: str,
        _available_tools: list[ToolMetadata] | None = None,
    ) -> Plan:
        """Formulate an initial bounded plan containing milestones for the goal."""
        plan_id = f"plan_{uuid.uuid4().hex[:12]}"
        # Generate initial default step to inspect goal
        initial_step = PlanStep(
            step_id="step_0",
            description=f"Analyze requirements and execute operations for goal: {goal}",
            status=PlanStepStatus.PENDING,
        )
        return Plan(
            plan_id=plan_id,
            goal=goal,
            steps=[initial_step],
            current_step_index=0,
        )

    async def determine_next_action(
        self,
        goal: str,
        plan: Plan,
        history: list[AgentMessage],
        available_tools: list[ToolMetadata],
        current_iteration: int,
        elapsed_time_seconds: float,
        tenant_id: str = "default",
    ) -> NextAction:
        """Determine next action while strictly enforcing bounded ceilings."""
        _ = plan
        # 1. Hard Bounded Iteration Guard
        if current_iteration >= self.max_iterations:
            logger.warning(
                "BoundedPlanner: max_iterations (%d) reached for goal '%s'",
                self.max_iterations,
                goal,
            )
            return NextAction(
                action_type=NextActionType.FAIL,
                error=f"Maximum allowed iterations ({self.max_iterations}) reached without goal completion.",
            )

        # 2. Hard Bounded Timeout Guard
        if elapsed_time_seconds >= self.timeout_seconds:
            logger.warning(
                "BoundedPlanner: timeout (%.1fs >= %.1fs) reached for goal '%s'",
                elapsed_time_seconds,
                self.timeout_seconds,
                goal,
            )
            return NextAction(
                action_type=NextActionType.FAIL,
                error=f"Execution timeout of {self.timeout_seconds:.1f}s exceeded.",
            )

        # 3. Build Prompt for Model Backend
        tool_schemas = [
            {
                "name": t.name,
                "description": t.description,
                "parameters": t.input_schema,
                "risk_level": t.risk_level.value,
            }
            for t in available_tools
        ]

        system_instruction = (
            "You are JakeAI-Agent, an autonomous enterprise task execution engine. "
            f"The user's overarching goal is: '{goal}'.\n"
            f"Current iteration: {current_iteration + 1} of {self.max_iterations}.\n"
            "You can execute available tools or produce the final answer when finished.\n"
            "If you need to call a tool, output a JSON object with format:\n"
            '{"action": "tool_call", "tool_name": "<name>", "arguments": {...}, "thought": "<reasoning>"}\n'
            "If you have completed the goal and can answer, output format:\n"
            '{"action": "finish", "output": "<final answer>", "thought": "<reasoning>"}'
        )

        # Recall relevant episodic/long-term memory for tenant
        if self.memory_manager is not None:
            try:
                recalled = self.memory_manager.recall_relevant(
                    tenant_id=tenant_id,
                    query_key=goal[:40],
                    limit=3,
                )
                if recalled:
                    facts = "\n".join(f"- {m.key}: {m.value}" for m in recalled)
                    system_instruction += f"\n\nRelevant Context from Memory:\n{facts}"
            except Exception as exc:
                logger.debug("Memory recall skipped due to error: %s", exc)

        prompt_messages: list[AgentMessage] = [
            AgentMessage(role="system", content=system_instruction),
            *history,
        ]

        req = BackendRequest(
            messages=prompt_messages,
            tools=tool_schemas,
            temperature=0.2,
            tenant_id=tenant_id,
            model=getattr(self.backend, "default_model", None),
        )

        resp = await self.backend.generate(req)

        # 4. Check if backend returned structured tool calls directly
        if resp.tool_calls:
            first_tc = resp.tool_calls[0]
            return NextAction(
                action_type=NextActionType.TOOL_CALL,
                tool_name=first_tc.tool_name,
                tool_args=first_tc.arguments,
                thought=resp.content,
            )

        # 5. Parse JSON block from response text
        content = resp.content.strip()
        parsed = self._extract_json_action(content)
        if parsed:
            action = parsed.get("action")
            if action == "tool_call":
                return NextAction(
                    action_type=NextActionType.TOOL_CALL,
                    tool_name=parsed.get("tool_name"),
                    tool_args=parsed.get("arguments") or {},
                    thought=parsed.get("thought", ""),
                )
            if action == "finish":
                return NextAction(
                    action_type=NextActionType.FINISH,
                    final_output=parsed.get("output") or content,
                    thought=parsed.get("thought", ""),
                )

        # 6. Default Fallback: If text generated without explicit tool call, treat as completion
        if content:
            return NextAction(
                action_type=NextActionType.FINISH,
                final_output=content,
                thought="Direct completion synthesized.",
            )

        return NextAction(
            action_type=NextActionType.FAIL,
            error="Planner received empty response from backend.",
        )

    @staticmethod
    def _extract_json_action(text: str) -> dict | None:
        """Attempt to parse action JSON block from model text."""
        if not text:
            return None
        # Try direct parse
        if text.startswith("{") and text.endswith("}"):
            try:
                data = json.loads(text)
                if isinstance(data, dict) and "action" in data:
                    return data
            except (json.JSONDecodeError, ValueError) as exc:
                logger.debug("Failed direct JSON parsing for action: %s", exc)

        # Try markdown codeblock extract
        if "```json" in text:
            try:
                sub = text.split("```json")[1].split("```")[0].strip()
                data = json.loads(sub)
                if isinstance(data, dict) and "action" in data:
                    return data
            except (json.JSONDecodeError, ValueError, IndexError) as exc:
                logger.debug("Failed codeblock JSON parsing for action: %s", exc)
        return None
