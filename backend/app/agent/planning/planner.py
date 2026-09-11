"""Bounded planning engine preventing runaway agent loops and orchestrating goal completion."""

from __future__ import annotations

import json
import logging
import re
import uuid
from typing import TYPE_CHECKING, Any

from app.agent.backends.base import (
    AgentBackendInterface,
    AgentMessage,
    BackendRequest,
)
from app.agent.domain.contracts import (
    AgentCapability,
    StepStatus,
)
from app.agent.planning.models import (
    NextAction,
    NextActionType,
    Plan,
    PlanStep,
    PlanStepStatus,
)
from app.routing.router import ModelRouter, RoutingPolicy
from app.routing.workload_classifier import WorkloadClassifier

if TYPE_CHECKING:
    from app.agent.memory.manager import AgentMemoryManager
    from app.agent.tools.base import ToolMetadata

logger = logging.getLogger(__name__)

# Heuristic classifiers for goal decomposition
_FINANCIAL_KW = re.compile(
    r"(?i)\b(?:ebitda|margin|revenue|expense|profit|operating income|financial|ratio|variance|statements?)\b|\$\d+"
)
_BANKING_KW = re.compile(
    r"(?i)\b(?:finnapi|account balance|transactions?|transfer|invoice|limit|banking)\b"
)
_RETRIEVAL_KW = re.compile(
    r"(?i)\b(?:retrieve|search|lookup|documents?|qdrant|bm25|rag|sources?)\b"
)
_MULTI_SOURCE_KW = re.compile(
    r"(?i)\b(?:two independent|combine|merge|multiple sources?|cross-reference|both|compare|versus|vs)\b"
)
_APPROVAL_KW = re.compile(
    r"(?i)\b(?:approval|dangerous|terminal|shell|exec|cmd|bash|delete|push)\b"
)


class BoundedPlanner:
    """Bounded planning engine with DAG multi-step plans, dependency resolution, and replanning."""

    def __init__(
        self,
        backend: AgentBackendInterface | None = None,
        max_iterations: int = 10,
        timeout_seconds: float = 60.0,
        memory_manager: AgentMemoryManager | None = None,
        model_router: ModelRouter | None = None,
        workload_classifier: WorkloadClassifier | None = None,
    ) -> None:
        if backend is None:
            from app.agent.backends.jakeai import JakeAIBackend

            backend = JakeAIBackend()
        self.backend = backend
        self.max_iterations = max_iterations
        self.timeout_seconds = timeout_seconds
        if memory_manager is None:
            from app.agent.memory.manager import get_memory_manager

            self.memory_manager = get_memory_manager()
        else:
            self.memory_manager = memory_manager

        self.model_router = model_router or ModelRouter()
        self.workload_classifier = workload_classifier or WorkloadClassifier()

    def create_initial_plan(
        self,
        goal: str,
        available_tools: list[ToolMetadata] | None = None,
        tenant_id: str = "default",
        task_id: str | None = None,
    ) -> Plan:
        """Formulate a real structured, dependency-aware DAG plan decomposing the goal."""
        _ = available_tools
        plan_id = f"plan_{uuid.uuid4().hex[:12]}"
        t_id = task_id or f"task_{uuid.uuid4().hex[:12]}"
        steps: list[PlanStep] = []

        # 1. Multi-source parallel task
        if _MULTI_SOURCE_KW.search(goal):
            analysis = "Multi-source parallel retrieval and consolidation workflow."
            step_1a = PlanStep(
                step_id="step_source_a",
                description="Retrieve external document and symbol context",
                objective="Fetch grounding documents from retrieval system",
                dependencies=[],
                required_capabilities=[AgentCapability.RAG_RETRIEVAL.value],
                candidate_agents=["retrieval_specialist"],
                required_tools=["search_symbols", "read_file"],
                model_requirements={"workload_class": "rag", "min_quality": 0.75},
                status=PlanStepStatus.PENDING,
            )
            step_1b = PlanStep(
                step_id="step_source_b",
                description="Retrieve banking and financial transactions",
                objective="Fetch live account and ledger data from FinnApiGo",
                dependencies=[],
                required_capabilities=[AgentCapability.BANKING_API.value],
                candidate_agents=["finnapigo_specialist"],
                required_tools=["get_account_balance", "list_transactions"],
                model_requirements={"workload_class": "structured_json", "min_quality": 0.70},
                status=PlanStepStatus.PENDING,
            )
            step_2 = PlanStep(
                step_id="step_merge_analyze",
                description="Merge independent sources and perform variance analysis",
                objective="Cross-reference financial metrics with document evidence",
                dependencies=["step_source_a", "step_source_b"],
                required_capabilities=[AgentCapability.FINANCIAL_ANALYSIS.value],
                candidate_agents=["financial_specialist"],
                model_requirements={"workload_class": "financial_reasoning", "min_quality": 0.85},
                status=PlanStepStatus.PENDING,
            )
            step_3 = PlanStep(
                step_id="step_synthesize",
                description="Synthesize final intelligence report with citations",
                objective="Generate executive summary and audited citation tables",
                dependencies=["step_merge_analyze"],
                required_capabilities=[AgentCapability.SYNTHESIS.value],
                candidate_agents=["synthesizer"],
                model_requirements={"workload_class": "general", "min_quality": 0.75},
                status=PlanStepStatus.PENDING,
            )
            steps = [step_1a, step_1b, step_2, step_3]

        # 2. Tool-required banking & financial analysis task
        elif _BANKING_KW.search(goal) and _FINANCIAL_KW.search(goal):
            analysis = "Integrated banking retrieval and quantitative financial analysis workflow."
            step_1 = PlanStep(
                step_id="step_fetch_banking",
                description="Fetch banking account balance and transaction records",
                objective="Obtain verified tenant ledger figures via FinnApiGo tool",
                dependencies=[],
                required_capabilities=[AgentCapability.BANKING_API.value],
                candidate_agents=["finnapigo_specialist"],
                required_tools=["get_account_balance"],
                model_requirements={"workload_class": "structured_json", "min_quality": 0.70},
                status=PlanStepStatus.PENDING,
            )
            step_2 = PlanStep(
                step_id="step_compute_financials",
                description="Calculate operating margins and adjusted EBITDA",
                objective="Compute deterministic income and profitability ratios",
                dependencies=["step_fetch_banking"],
                required_capabilities=[AgentCapability.FINANCIAL_ANALYSIS.value],
                candidate_agents=["financial_specialist"],
                model_requirements={"workload_class": "financial_reasoning", "min_quality": 0.85},
                status=PlanStepStatus.PENDING,
            )
            step_3 = PlanStep(
                step_id="step_synthesize",
                description="Compile final audited financial report",
                objective="Produce markdown report with formatted performance metrics",
                dependencies=["step_compute_financials"],
                required_capabilities=[AgentCapability.SYNTHESIS.value],
                candidate_agents=["synthesizer"],
                model_requirements={"workload_class": "general", "min_quality": 0.75},
                status=PlanStepStatus.PENDING,
            )
            steps = [step_1, step_2, step_3]

        # 3. Tool requiring human approval
        elif _APPROVAL_KW.search(goal):
            analysis = "Sensitive administrative operation requiring human-in-the-loop approval."
            step_1 = PlanStep(
                step_id="step_dangerous_action",
                description="Execute privileged terminal operation",
                objective="Execute authorized system-level operation with approval boundary",
                dependencies=[],
                required_capabilities=[AgentCapability.CODE_EXECUTION.value],
                candidate_agents=["general_agent"],
                required_tools=["terminal_exec"],
                model_requirements={"workload_class": "coding", "min_quality": 0.80},
                status=PlanStepStatus.PENDING,
            )
            step_2 = PlanStep(
                step_id="step_report_outcome",
                description="Synthesize execution outcome",
                objective="Report stdout and status of the approved execution",
                dependencies=["step_dangerous_action"],
                required_capabilities=[AgentCapability.SYNTHESIS.value],
                candidate_agents=["synthesizer"],
                model_requirements={"workload_class": "simple_chat", "min_quality": 0.60},
                status=PlanStepStatus.PENDING,
            )
            steps = [step_1, step_2]

        # 4. Pure financial calculation task
        elif _FINANCIAL_KW.search(goal):
            analysis = "Quantitative financial modeling and reasoning workflow."
            step_1 = PlanStep(
                step_id="step_financial_analysis",
                description="Analyze financial figures and compute operating income",
                objective="Calculate revenues, expenses, operating margin, and EBITDA",
                dependencies=[],
                required_capabilities=[AgentCapability.FINANCIAL_ANALYSIS.value],
                candidate_agents=["financial_specialist"],
                model_requirements={"workload_class": "financial_reasoning", "min_quality": 0.85},
                status=PlanStepStatus.PENDING,
            )
            step_2 = PlanStep(
                step_id="step_synthesize",
                description="Synthesize financial findings",
                objective="Format quantitative intelligence into structured markdown",
                dependencies=["step_financial_analysis"],
                required_capabilities=[AgentCapability.SYNTHESIS.value],
                candidate_agents=["synthesizer"],
                model_requirements={"workload_class": "general", "min_quality": 0.70},
                status=PlanStepStatus.PENDING,
            )
            steps = [step_1, step_2]

        # 5. Simple direct question
        else:
            analysis = "Direct question resolution via intelligent synthesis."
            step_1 = PlanStep(
                step_id="step_direct_answer",
                description=f"Formulate comprehensive response for: {goal}",
                objective="Answer user query directly using optimal cost-effective model",
                dependencies=[],
                required_capabilities=[AgentCapability.SYNTHESIS.value],
                candidate_agents=["synthesizer", "general_agent"],
                model_requirements={"workload_class": "simple_chat", "min_quality": 0.60},
                status=PlanStepStatus.PENDING,
            )
            steps = [step_1]

        # Route optimal models for each step using ModelRouter
        for s in steps:
            req_workload = s.model_requirements.get("workload_class", "general")
            try:
                routing_policy = RoutingPolicy(
                    requested_model="default",
                    tenant_id=tenant_id,
                    workload_class=req_workload,
                    cost_aware_routing=True,
                )
                decision = self.model_router.route(routing_policy)
                s.selected_model = decision.selected_model
                s.selected_provider = decision.selected_provider
            except Exception as exc:
                logger.debug("Planner ModelRouter assignment fallback: %s", exc)
                s.selected_model = "gemini-1.5-flash"
                s.selected_provider = "gemini"

        return Plan(
            plan_id=plan_id,
            task_id=t_id,
            goal=goal,
            analysis=analysis,
            steps=steps,
            current_step_index=0,
            completed=False,
        )

    def replan(
        self,
        existing_plan: Plan | str,
        *args: Any,
        goal: str | None = None,
        failed_step_id: str | None = None,
        verifier_critique: str | None = None,
        tenant_id: str = "default",
        **kwargs: Any,
    ) -> Plan:
        """Reconstruct plan following verification critique or execution failure."""
        if isinstance(existing_plan, str):
            actual_goal = existing_plan
            actual_plan: Plan = args[0] if args else kwargs["existing_plan"]
            actual_failed_id = str(args[1] if len(args) > 1 else (failed_step_id or kwargs.get("failed_step_id", "")))
            actual_critique = str(args[2] if len(args) > 2 else (verifier_critique or kwargs.get("verifier_critique", "")))
        else:
            actual_plan = existing_plan
            actual_goal = goal or actual_plan.goal
            actual_failed_id = str(failed_step_id or kwargs.get("failed_step_id") or (args[1] if len(args) > 1 else (args[0] if args else "")))
            actual_critique = str(verifier_critique or kwargs.get("verifier_critique") or (args[0] if args and not failed_step_id else (args[1] if len(args) > 1 else "")))

        logger.info(
            "Replanning task '%s' at step '%s' due to critique: %s",
            actual_plan.task_id,
            actual_failed_id,
            actual_critique,
        )

        new_steps: list[PlanStep] = []
        for s in actual_plan.steps:
            if s.status == StepStatus.COMPLETED:
                # Keep already completed prerequisite steps
                new_steps.append(s)
            elif s.step_id == actual_failed_id:
                # Create revision step with remedial objective and increased revision count
                revised_step = PlanStep(
                    step_id=f"{s.step_id}_revised",
                    description=f"{s.description} (Revision: {actual_critique})",
                    objective=f"Corrected execution addressing critique: {actual_critique}",
                    dependencies=s.dependencies,
                    required_capabilities=s.required_capabilities,
                    candidate_agents=s.candidate_agents,
                    required_tools=s.required_tools,
                    model_requirements={
                        **s.model_requirements,
                        "min_quality": min(1.0, s.model_requirements.get("min_quality", 0.7) + 0.1),
                    },
                    status=PlanStepStatus.PENDING,
                    retries_exhausted=s.retries_exhausted + 1,
                )
                new_steps.append(revised_step)
            else:
                # Update dependencies if subsequent step depended on the failed step
                updated_deps = [
                    f"{actual_failed_id}_revised" if d == actual_failed_id else d
                    for d in s.dependencies
                ]
                s_copy = s.model_copy()
                s_copy.dependencies = updated_deps
                s_copy.status = PlanStepStatus.PENDING
                new_steps.append(s_copy)

        # Route models for any new or modified steps
        for s in new_steps:
            if not s.selected_model:
                try:
                    routing_policy = RoutingPolicy(
                        requested_model="default",
                        tenant_id=tenant_id,
                        workload_class=s.model_requirements.get("workload_class", "general"),
                        cost_aware_routing=True,
                    )
                    decision = self.model_router.route(routing_policy)
                    s.selected_model = decision.selected_model
                    s.selected_provider = decision.selected_provider
                except Exception:
                    s.selected_model = "gemini-1.5-flash"
                    s.selected_provider = "gemini"

        return Plan(
            plan_id=f"plan_replan_{uuid.uuid4().hex[:8]}",
            task_id=actual_plan.task_id,
            goal=actual_goal,
            analysis=f"Replanned after critique: {actual_critique}",
            steps=new_steps,
            current_step_index=0,
            completed=False,
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
        """Determine next action while strictly enforcing bounded ceilings and ModelRouter."""
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

        # 3. Check if all plan steps are completed
        if plan.is_complete():
            last_obs = ""
            for s in reversed(plan.steps):
                if s.observation:
                    last_obs = s.observation
                    break
            return NextAction(
                action_type=NextActionType.FINISH,
                final_output=last_obs or f"Plan successfully completed all {len(plan.steps)} steps.",
                thought="All plan steps successfully completed.",
            )

        # 4. Route model dynamically via canonical ModelRouter (Phase 7)
        backend_default = getattr(self.backend, "default_model", None)
        workload_res = self.workload_classifier.classify(goal)
        routing_policy = RoutingPolicy(
            requested_model=backend_default or "default",
            tenant_id=tenant_id,
            required_capabilities=workload_res.required_capabilities,
            workload_class=workload_res.workload_class,
            cost_aware_routing=not bool(backend_default),
        )
        try:
            route_decision = self.model_router.route(routing_policy)
            selected_model = backend_default or route_decision.selected_model
        except Exception as exc:
            logger.debug("ModelRouter route fallback in planner: %s", exc)
            selected_model = backend_default or "gemini-1.5-flash"

        # 5. Build Prompt for Model Backend
        tool_schemas = [
            {
                "name": t.name,
                "description": t.description,
                "parameters": t.input_schema,
                "risk_level": t.risk_level.value,
            }
            for t in available_tools
        ]

        plan_summary = "\n".join(
            f"- [{s.status.value.upper()}] {s.step_id}: {s.description}"
            for s in plan.steps
        )

        system_instruction = (
            "You are JakeAI-Agent, an autonomous enterprise task execution engine. "
            f"The user's overarching goal is: '{goal}'.\n"
            f"Current iteration: {current_iteration + 1} of {self.max_iterations}.\n"
            f"Active Plan:\n{plan_summary}\n\n"
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
            model=selected_model,
        )

        resp = await self.backend.generate(req)

        # 6. Check if backend returned structured tool calls directly
        if resp.tool_calls:
            first_tc = resp.tool_calls[0]
            return NextAction(
                action_type=NextActionType.TOOL_CALL,
                tool_name=first_tc.tool_name,
                tool_args=first_tc.arguments,
                thought=resp.content,
                selected_model=selected_model,
            )

        # 7. Parse JSON block from response text
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
                    selected_model=selected_model,
                )
            if action == "finish":
                return NextAction(
                    action_type=NextActionType.FINISH,
                    final_output=parsed.get("output") or content,
                    thought=parsed.get("thought", ""),
                    selected_model=selected_model,
                )

        # 8. Default Fallback: If text generated without explicit tool call, treat as completion
        if content:
            return NextAction(
                action_type=NextActionType.FINISH,
                final_output=content,
                thought="Direct completion synthesized.",
                selected_model=selected_model,
            )

        return NextAction(
            action_type=NextActionType.FAIL,
            error="Planner received empty response from backend.",
            selected_model=selected_model,
        )

    @staticmethod
    def _extract_json_action(text: str) -> dict | None:
        """Attempt to parse action JSON block from model text."""
        if not text:
            return None
        if text.startswith("{") and text.endswith("}"):
            try:
                data = json.loads(text)
                if isinstance(data, dict) and "action" in data:
                    return data
            except (json.JSONDecodeError, ValueError) as exc:
                logger.debug("Failed direct JSON parsing for action: %s", exc)

        if "```json" in text:
            try:
                sub = text.split("```json")[1].split("```")[0].strip()
                data = json.loads(sub)
                if isinstance(data, dict) and "action" in data:
                    return data
            except (json.JSONDecodeError, ValueError, IndexError) as exc:
                logger.debug("Failed codeblock JSON parsing for action: %s", exc)
        return None
