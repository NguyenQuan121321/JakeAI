"""Regression tests for R-AI-00 — Agent Correctness (AI evaluation and self-healing).

Validates agent intelligence and correctness at architectural boundaries:
- Novel/paraphrased task decomposition and DAG structuring.
- Dependency planning and execution ordering.
- Negative constraints (exclusion of terminal/shell and banking tools).
- Contradictory and impossible request handling.
- Dynamic agent selection without false confidence (no supervisor fallback for general tasks).
- Autonomous model routing resolving 'default' without literal leaks.
- Grounded execution of user-specified figures in financial capabilities.
- Real LLM synthesis and multi-source report consolidation.
- Bounded recovery non-retryable classification for unregistered tools.
"""

from __future__ import annotations

import pytest

from app.agent.backends.base import (
    AgentBackendInterface,
    BackendRequest,
    BackendResponse,
    BackendStreamChunk,
)
from app.agent.domain.contracts import (
    ExecutionContext,
    PlanStep,
    RecoveryAction,
    StepStatus,
    TaskSpec,
)
from app.agent.execution.engine import ExecutionEngine
from app.agent.planning.planner import BoundedPlanner
from app.agent.recovery.recovery import BoundedRecoveryEngine, RecoveryLimits
from app.agent.registry.agent_selector import get_agent_selector
from app.agent.registry.capability_patterns import (
    has_negative_constraint,
)
from app.agent.state.models import RunState, RunStatus
from app.agents.supervisor import (
    classify_intent,
    decide_supervisor_route,
)
from app.routing.router import RoutingPolicy, get_model_router


class MockPlannerBackend(AgentBackendInterface):
    """Mock backend providing model-driven responses for planning and routing."""

    def __init__(self, response_content: str = "") -> None:
        self.response_content = response_content
        self.requests: list[BackendRequest] = []

    async def generate(self, request: BackendRequest) -> BackendResponse:
        self.requests.append(request)
        if self.response_content:
            return BackendResponse(content=self.response_content)
        # Default mock response
        return BackendResponse(
            content='{"target_agent": "synthesizer", "reasoning": "General query analyzed by model."}'
        )

    async def generate_stream(self, request: BackendRequest):
        resp = await self.generate(request)
        yield BackendStreamChunk(delta_content=resp.content, is_complete=True)


# ===========================================================================
# 1. Novel & Paraphrased Task Planning & Decomposition
# ===========================================================================


def test_planner_paraphrased_financial_and_retrieval_decomposition() -> None:
    """Paraphrased financial terms (treasury turnover, spending, outlays) trigger multi-step decomposition."""
    planner = BoundedPlanner()
    # Goal uses synonyms: 'treasury turnover', 'departmental outlays', 'operating surplus', 'policy handbook'
    goal = (
        "Analyze treasury turnover and departmental outlays to compute operating surplus, "
        "and cross-examine findings with the corporate policy handbook."
    )
    plan = planner.create_initial_plan(goal=goal, tenant_id="tenant-acme")

    assert len(plan.steps) >= 2, (
        "Novel paraphrased multi-domain task should produce multiple steps"
    )

    # Verify steps have proper dependencies
    final_step = plan.steps[-1]
    assert len(final_step.dependencies) > 0, (
        "Final synthesis step must depend on upstream data steps"
    )

    # Check that required tools and capabilities match expectations
    step_descriptions = " ".join(s.description.lower() for s in plan.steps)
    assert any(
        term in step_descriptions
        for term in ("financial", "treasury", "outlays", "surplus", "turnover")
    )


def test_planner_independent_parallel_steps_with_synthesis_dag() -> None:
    """Multi-source request produces independent parallel steps followed by dependent synthesis."""
    planner = BoundedPlanner()
    goal = "Correlate FinnApiGo banking transaction records with audited handbook documents from dual sources."
    plan = planner.create_initial_plan(goal=goal, tenant_id="tenant-test")

    assert len(plan.steps) >= 3, (
        "Multi-source correlation requires at least 2 source steps + 1 synthesis step"
    )

    # First steps should have no dependencies (parallel)
    source_steps = [s for s in plan.steps if len(s.dependencies) == 0]
    assert len(source_steps) >= 2, (
        "Source steps should be independent to allow parallel execution"
    )

    # Intermediate merge step depends on both parallel source steps
    merge_step = next(s for s in plan.steps if s.step_id == "step_merge_analyze")
    for src in source_steps:
        assert src.step_id in merge_step.dependencies, (
            f"Merge step must depend on {src.step_id}"
        )

    # Final synthesis step must depend on the merge step
    synthesis_step = plan.steps[-1]
    assert merge_step.step_id in synthesis_step.dependencies


# ===========================================================================
# 2. Negative & Contradictory Constraints
# ===========================================================================


def test_negative_constraint_detection() -> None:
    """Verify negative constraint regex correctly detects prohibitions across domains."""
    assert has_negative_constraint(
        "terminal", "Please do not use terminal_exec or run bash scripts."
    )
    assert has_negative_constraint(
        "terminal", "Refrain from executing shell maintenance script."
    )
    assert has_negative_constraint(
        "banking", "Do NOT call finnapi or query banking accounts."
    )
    assert has_negative_constraint("banking", "Never access bank balance.")
    assert has_negative_constraint(
        "financial", "Without calculating margin or financial ratios, write a summary."
    )
    assert has_negative_constraint("financial", "Don't compute ebitda or turnover.")

    # Positive prompts should not trigger negative constraint
    assert not has_negative_constraint(
        "terminal", "Execute maintenance script in terminal."
    )
    assert not has_negative_constraint(
        "banking", "Fetch current bank balance from finnapi."
    )
    assert not has_negative_constraint(
        "financial", "Calculate operating margin and EBITDA."
    )


def test_planner_respects_negative_constraints_for_tools() -> None:
    """Planner excludes forbidden tools when user explicitly forbids terminal or banking."""
    planner = BoundedPlanner()
    goal = (
        "Review server configuration and generate report, but DO NOT use terminal_exec "
        "or execute any shell maintenance script."
    )
    plan = planner.create_initial_plan(goal=goal, tenant_id="tenant-safe")

    # None of the steps should require terminal_exec or shell tools
    for step in plan.steps:
        tools = step.required_tools or []
        assert "terminal_exec" not in tools, (
            f"Step '{step.step_id}' scheduled forbidden tool terminal_exec"
        )
        assert "mock_dangerous_shell" not in tools, (
            f"Step '{step.step_id}' scheduled forbidden shell tool"
        )


def test_supervisor_intent_classification_with_negative_constraints() -> None:
    """Supervisor classify_intent respects negative constraints, routing away from prohibited specialists."""
    # Financial keyword mentioned with negation -> routes to synthesizer, NOT financial_specialist
    assert (
        classify_intent(
            "Do not do any financial calculations or margin analysis; write a creative poem."
        )
        == "synthesizer"
    )
    # Banking keyword mentioned with negation -> routes to synthesizer, NOT finnapigo_tool
    assert (
        classify_intent(
            "Do not call finnapi or fetch bank balance; provide a general company overview."
        )
        == "synthesizer"
    )
    # Standard positive queries still route correctly
    assert (
        classify_intent("Calculate operating margin and EBITDA")
        == "financial_specialist"
    )
    assert (
        classify_intent("Fetch customer account balance from finnapi")
        == "finnapigo_tool"
    )


@pytest.mark.asyncio
async def test_supervisor_model_driven_routing_priority() -> None:
    """Supervisor prioritizes model-driven reasoning over regex patterns when backend is available."""
    # Mock backend returns model decision to route to synthesizer despite presence of banking word
    backend = MockPlannerBackend(
        response_content='{"target_agent": "synthesizer", "reasoning": "User asks for philosophy of banking ethics."}'
    )
    decision = await decide_supervisor_route(
        prompt="Discuss the moral philosophy of banking and usury in Renaissance Europe.",
        tenant_id="tenant-edu",
        backend=backend,
    )
    # If regex was evaluated first, 'banking' would route to finnapigo_tool.
    # Model reasoning routes to synthesizer.
    assert decision.target_agent in ("synthesizer", "financial_specialist")
    assert decision.confidence >= 0.85


# ===========================================================================
# 3. Dynamic Agent Selection & False Confidence Elimination
# ===========================================================================


def test_agent_selector_novel_general_task_falls_back_without_false_confidence() -> (
    None
):
    """Novel task with no matching capabilities selects general_agent with fallback_used=True, NOT supervisor."""
    selector = get_agent_selector()
    task_spec = TaskSpec(
        goal="Compose a metaphysical critique of epistemology and existential phenomenology.",
        tenant_id="tenant-philosophy",
    )
    selection = selector.select_agent(task_spec)

    # Must NOT route to supervisor or specialist with false confidence
    assert selection.agent_id == "general_agent", (
        f"Expected general_agent, got {selection.agent_id}"
    )
    assert selection.fallback_used is True, (
        "Fallback should be explicitly marked as True for un-matched task"
    )
    assert selection.selection_mode in ("fallback", "deterministic_fallback")


def test_agent_selector_respects_negative_constraints() -> None:
    """Agent selector penalizes specialists when prompt contains negative constraints."""
    selector = get_agent_selector()
    task_spec = TaskSpec(
        goal="Do not perform financial calculations or revenue analysis. Provide a plain language summary.",
        tenant_id="tenant-text",
    )
    selection = selector.select_agent(task_spec)
    assert selection.agent_id != "financial_specialist", (
        "Agent selector should not select financial_specialist when negated"
    )


# ===========================================================================
# 4. Model Routing: 'default' Model Dynamic Resolution
# ===========================================================================


def test_model_router_resolves_default_without_literal_leak() -> None:
    """Model router resolves requested_model='default' to a real candidate model based on workload."""
    router = get_model_router()

    # Financial workload with 'default' -> resolves to reasoning model
    fin_policy = RoutingPolicy(
        requested_model="default",
        workload_class="financial_reasoning",
        cost_aware_routing=True,
    )
    fin_route = router.route(fin_policy)
    assert fin_route.selected_model != "default", (
        "Literal 'default' leaked from router!"
    )
    assert fin_route.selected_model in (
        "deepseek-reasoner",
        "gemini-2.0-flash",
        "claude-3-5-sonnet",
    )

    # Coding workload with 'default' -> resolves to coding-capable model
    code_policy = RoutingPolicy(
        requested_model="default",
        workload_class="coding",
        cost_aware_routing=True,
    )
    code_route = router.route(code_policy)
    assert code_route.selected_model != "default"
    assert len(code_route.selected_model) > 0


# ===========================================================================
# 5. Execution Grounding & Multi-Source Synthesis
# ===========================================================================


@pytest.mark.asyncio
async def test_execution_engine_grounds_user_figures() -> None:
    """Financial specialist in execution engine calculates metrics from user prompt figures, not hardcoded defaults."""
    engine = ExecutionEngine()
    task_spec = TaskSpec(
        goal="Revenue is $5,000,000 and expenses are $3,000,000. Calculate operating metrics.",
        tenant_id="tenant-metric",
    )
    events = []
    async for ev in engine.execute_task(task_spec):
        events.append(ev)

    completed_events = [e for e in events if e.event_type == "step_completed"]
    assert len(completed_events) >= 1
    fin_step = next(
        e
        for e in completed_events
        if isinstance(e.data.get("output"), dict) and "revenue" in e.data["output"]
    )
    step_out = fin_step.data["output"]
    assert step_out.get("revenue") == 5000000.0, (
        f"Expected 5000000.0, got {step_out.get('revenue')}"
    )
    assert step_out.get("operating_expenses") == 3000000.0
    assert step_out.get("operating_income") == 2000000.0
    assert step_out.get("operating_margin_pct") == 40.0


@pytest.mark.asyncio
async def test_execution_engine_synthesizer_formats_all_accumulated_outputs() -> None:
    """Synthesizer incorporates diverse accumulated outputs (not just revenue) in the final report."""
    engine = ExecutionEngine()
    task_spec = TaskSpec(
        goal="Review network logs and policies",
        tenant_id="tenant-sec",
    )
    context = ExecutionContext(tenant_id="tenant-sec", user_id="user-sec")
    run_state = RunState(
        run_id="run-synth-test",
        task_id=task_spec.task_id,
        tenant_id="tenant-sec",
        user_id="user-sec",
        status=RunStatus.RUNNING,
        prompt=task_spec.goal,
    )
    synth_step = PlanStep(
        step_id="synth_step",
        description="Synthesize findings and generate executive summary",
        assigned_agent="synthesizer",
        candidate_agents=["synthesizer"],
        required_capabilities=["synthesis"],
        dependencies=[],
    )
    accumulated_outputs = {
        "step_rag": {
            "retrieved_chunks": [
                {
                    "content": "Audited internal documents for tenant-sec: ledger verified."
                }
            ]
        },
        "step_calc": {
            "revenue": 5000000.0,
            "operating_expenses": 3000000.0,
            "operating_income": 2000000.0,
            "operating_margin_pct": 40.0,
            "ebitda": 2240000.0,
        },
    }
    _step, res, _events = await engine._execute_single_step(
        step=synth_step,
        task_spec=task_spec,
        context=context,
        run_state=run_state,
        accumulated_outputs=accumulated_outputs,
        _elapsed_seconds=1.0,
    )
    assert res.status == StepStatus.COMPLETED
    output_text = str(res.output)
    assert "Executive Intelligence Report" in output_text
    assert (
        "Knowledge Retrieval" in output_text
        or "Audited internal documents" in output_text
    )
    assert "Financial Overview" in output_text


# ===========================================================================
# 6. Bounded Recovery: Non-Retryable Unregistered Tools
# ===========================================================================


def test_recovery_engine_classifies_unregistered_tool_as_non_retryable() -> None:
    """Recovery engine does not waste retry budget on unregistered/unknown tools."""
    engine = BoundedRecoveryEngine(limits=RecoveryLimits(max_step_retries=3))
    step = PlanStep(
        step_id="bad_tool_step",
        description="Call nonexistent external API tool",
        assigned_agent="finnapigo_specialist",
    )

    decision = engine.evaluate_step_failure(
        step=step,
        error_message="Unknown tool: 'query_nonexistent_service' is not registered.",
        current_step_retries=0,
        elapsed_time_seconds=2.0,
    )

    # Must immediately TERMINATE_FAILED without retrying
    assert decision.action == RecoveryAction.TERMINATE_FAILED
    assert "Non-retryable failure" in decision.reason
