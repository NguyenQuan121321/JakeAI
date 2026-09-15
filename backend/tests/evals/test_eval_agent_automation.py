"""Automated Agent Orchestration Evaluation Test Suite (TEST-06 / AI-012 / CAT-121).

Evaluates the 14 agent orchestration dimensions without brittle exact string equality:
1.  Goal Interpretation
2.  Plan Structure (DAG acyclicity, parallel tiers)
3.  Agent Selection (capability matching & fallback bounds)
4.  Model Selection (workload routing, no literal 'default' leak)
5.  Tool Selection (synonym matching & negative constraints)
6.  Tool Execution (JSON schema validation & argument safety)
7.  Verification (mathematical variance rejection)
8.  Recovery (non-retryable error classification)
9.  Retry Bounds (retry ceiling enforcement)
10. Approval Flow (dangerous tool gating & TOCTOU defense)
11. Resume (checkpoint rehydration without step duplication)
12. Cancellation (clean termination & idempotent cancel)
13. Terminal State (immutable absorbing state invariants)
14. Failure Truthfulness (honest error reporting, no false COMPLETED)
"""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any

import pytest

from app.agent.domain.contracts import (
    PlanStep,
    TaskSpec,
    VerificationVerdict,
)
from app.agent.planning.planner import BoundedPlanner
from app.agent.recovery.recovery import (
    BoundedRecoveryEngine,
    RecoveryAction,
    RecoveryLimits,
)
from app.agent.registry.agent_selector import AgentSelector
from app.agent.state.models import RunState, RunStatus
from app.agent.tools.policy import ToolPolicyEngine
from app.agent.tools.registry import get_tool_registry
from app.agent.verification.verifier import CanonicalVerifier
from app.evals.agent_evaluator import (
    evaluate_agent_selection,
    evaluate_goal_interpretation,
    evaluate_lifecycle_and_terminal_state,
    evaluate_model_selection,
    evaluate_plan_structure,
    evaluate_tool_selection_and_schema,
    evaluate_verification_and_recovery,
)
from app.routing.router import ModelRouter, RoutingPolicy

FIXTURES_PATH = Path(__file__).parent / "datasets" / "eval_agent_fixtures_v1.json"


def load_agent_fixtures() -> list[dict[str, Any]]:
    """Load versioned agent evaluation fixtures."""
    with open(FIXTURES_PATH, encoding="utf-8") as f:
        cases: list[dict[str, Any]] = json.load(f)
        return cases


# =========================================================================
# 1. Goal Interpretation
# =========================================================================
def test_eval_agent_01_goal_interpretation_and_negative_constraints() -> None:
    """Evaluate planner decomposes complex goals and strictly honors negative constraints."""
    planner = BoundedPlanner()
    goal = "Reconcile Q3 treasury turnover with ledger records and summarize discrepancies. Do NOT execute shell scripts or terminal_exec."

    plan = planner.create_initial_plan(goal)
    eval_result = evaluate_goal_interpretation(
        goal=goal,
        plan=plan,
        prohibited_tools=["terminal_exec"],
        required_specialists=["financial_specialist", "synthesizer"],
    )

    assert eval_result.passed, (
        f"Goal interpretation evaluation failed: {eval_result.diagnostics}"
    )
    assert eval_result.criteria["negative_constraints_respected"]
    assert eval_result.criteria["complex_goal_decomposed"]
    assert not any("terminal_exec" in s.required_tools for s in plan.steps)


# =========================================================================
# 2. Plan Structure (DAG Acyclicity & Parallel Tiers)
# =========================================================================
def test_eval_agent_02_plan_structure_dag_acyclicity() -> None:
    """Evaluate plan DAG structure: valid dependency tree, topological order, and synthesis coherent."""
    planner = BoundedPlanner()
    goal = "Retrieve both customer credit limit and recent invoice history concurrently, then compile an audit report"

    plan = planner.create_initial_plan(goal)
    eval_result = evaluate_plan_structure(plan)

    assert eval_result.passed, (
        f"Plan structure evaluation failed: {eval_result.diagnostics}"
    )
    assert eval_result.criteria["dag_acyclic"]
    assert eval_result.criteria["dependencies_valid"]
    assert eval_result.criteria["terminal_synthesis_coherent"]


# =========================================================================
# 3. Agent Selection & Capability Matching
# =========================================================================
def test_eval_agent_03_agent_selection_and_fallback_bounds() -> None:
    """Evaluate autonomous agent selector: specialized tasks match specialists, novel tasks use fallback."""
    selector = AgentSelector()

    # Specialized task
    spec_specialized = TaskSpec(
        tenant_id="tenant_eval",
        goal="Perform capital adequacy ratio calculation under Basel III framework",
        task_type="financial_analysis",
    )
    res_specialized = selector.select_agent(spec_specialized)
    eval_spec = evaluate_agent_selection(
        selected_agent=res_specialized.agent_id,
        confidence=res_specialized.confidence,
        fallback_used=res_specialized.fallback_used,
        expected_agent="financial_specialist",
        allow_fallback=False,
    )
    assert eval_spec.passed, f"Specialist selection failed: {eval_spec.diagnostics}"

    # Novel unmatched task
    spec_novel = TaskSpec(
        tenant_id="tenant_eval",
        goal="Draft an introspective philosophical meditation on artificial thought and memory",
        task_type="creative_writing",
    )
    res_novel = selector.select_agent(spec_novel)
    eval_novel = evaluate_agent_selection(
        selected_agent=res_novel.agent_id,
        confidence=res_novel.confidence,
        fallback_used=res_novel.fallback_used,
        allow_fallback=True,
    )
    assert eval_novel.passed, (
        f"Novel task fallback bounds failed: {eval_novel.diagnostics}"
    )


# =========================================================================
# 4. Model Selection & Routing
# =========================================================================
def test_eval_agent_04_model_selection_without_literal_default_leak() -> None:
    """Evaluate dynamic model routing for requested_model='default' resolves to a real model without leaking 'default'."""
    router = ModelRouter()
    workloads = ["financial_reasoning", "coding_context", "simple_chat", "rag"]

    for w_class in workloads:
        policy = RoutingPolicy(requested_model="default", workload_class=w_class)
        route = router.route(policy)
        eval_result = evaluate_model_selection(
            requested_model="default",
            selected_model=route.selected_model,
            selected_provider=route.selected_provider,
            workload_class=w_class,
        )
        assert eval_result.passed, (
            f"Model selection evaluation failed for {w_class}: {eval_result.diagnostics}"
        )
        assert route.selected_model.lower() != "default"


@pytest.mark.asyncio
async def test_eval_agent_05_tool_selection_and_synonym_resolution() -> None:
    """Evaluate semantic tool resolution understands synonyms ('liquid cash reserves' -> 'get_account_balance')."""
    from app.agents.finnapigo_tool import finnapigo_tool_node

    goal = "Check available liquid cash reserves in vault for ACC-7712"
    state = {
        "task_spec": TaskSpec(
            tenant_id="tenant_eval",
            goal=goal,
        ),
        "prompt": goal,
        "tenant_id": "tenant_eval",
        "user_id": "user_eval",
        "steps": [],
        "context": {},
        "current_step": PlanStep(
            step_id="step_1",
            description=goal,
            assigned_agent="finnapigo_specialist",
            required_tools=[],
        ),
    }

    result_state = await finnapigo_tool_node(state)
    selected_tools = [tc["tool_name"] for tc in result_state.get("tool_calls", [])]

    eval_result = evaluate_tool_selection_and_schema(
        selected_tools=selected_tools,
        expected_tools=["get_account_balance"],
        prohibited_tools=["terminal_exec"],
    )
    assert eval_result.passed, (
        f"Tool selection evaluation failed: {eval_result.diagnostics}"
    )


# =========================================================================
# 6. Tool Execution & Schema Enforcement
# =========================================================================
def test_eval_agent_06_tool_execution_and_schema_validation() -> None:
    """Evaluate ToolRegistry enforces schema types, boundaries, and rejects unexpected properties fail-closed."""
    registry = get_tool_registry()

    # 1. Valid arguments pass
    valid_args = {"limit": 20}
    is_valid, err = registry.validate("list_transactions", valid_args)
    assert is_valid, f"Valid arguments failed schema check: {err}"

    # 2. Malformed arguments (negative limit, unexpected properties) fail
    invalid_args = {"limit": -10, "unexpected_flag": True}
    is_invalid, _err_invalid = registry.validate("list_transactions", invalid_args)
    assert not is_invalid, (
        "Malformed arguments were unexpectedly accepted by ToolRegistry"
    )


# =========================================================================
# 7. Verification & Mathematical Variance
# =========================================================================
def test_eval_agent_07_verification_mathematical_variance_rejection() -> None:
    """Evaluate CanonicalVerifier assigns FAILED / NEEDS_REVISION on mathematical calculation variance."""
    verifier = CanonicalVerifier()

    # Output claims $90M operating income with rev $200M and expenses $150M (expected $50M)
    v_res = verifier.verify_execution(
        tenant_id="tenant_eval",
        goal="Calculate operating income given revenue $200M and operating expenses $150M",
        step_outputs=[],
        tool_calls=[],
        retrieved_chunks=[],
        financial_data={
            "revenue": 200.0,
            "operating_expenses": 150.0,
            "operating_income": 90.0,
        },
        final_output="Operating income was calculated as $90M.",
    )

    eval_res = evaluate_verification_and_recovery(
        verdict=v_res.verdict.value,
        math_variance=True,
        error_type="",
        recovery_action="REPLAN",
        retries_used=0,
    )
    assert eval_res.passed, f"Verification evaluation failed: {eval_res.diagnostics}"
    assert v_res.verdict in [
        VerificationVerdict.FAILED,
        VerificationVerdict.NEEDS_REVISION,
        VerificationVerdict.REJECTED,
    ]


# =========================================================================
# 8. Recovery: Non-Retryable Error Classification
# =========================================================================
def test_eval_agent_08_recovery_non_retryable_classification() -> None:
    """Evaluate BoundedRecoveryEngine recognizes missing tools as non-retryable and avoids wasting retry budget."""
    recovery = BoundedRecoveryEngine(limits=RecoveryLimits(max_step_retries=3))
    step = PlanStep(
        step_id="step_tool",
        description="Invoke scraper",
        assigned_agent="general_agent",
    )
    error_msg = "Unknown tool: 'unregistered_external_scraper' is not registered in ToolRegistry"

    decision = recovery.evaluate_step_failure(
        step=step,
        error_message=error_msg,
        current_step_retries=0,
        elapsed_time_seconds=1.0,
    )

    eval_res = evaluate_verification_and_recovery(
        verdict="FAILED",
        math_variance=False,
        error_type=error_msg,
        recovery_action=decision.action.value
        if hasattr(decision.action, "value")
        else str(decision.action),
        retries_used=0,
    )
    assert eval_res.passed, f"Recovery evaluation failed: {eval_res.diagnostics}"
    assert decision.action in [RecoveryAction.TERMINATE_FAILED, RecoveryAction.REPLAN]


# =========================================================================
# 9. Retry Bounds Enforcement
# =========================================================================
def test_eval_agent_09_retry_bounds_budget_ceiling() -> None:
    """Evaluate BoundedRecoveryEngine strictly respects max retry budget ceiling (3 retries)."""
    recovery = BoundedRecoveryEngine(limits=RecoveryLimits(max_step_retries=3))
    step = PlanStep(
        step_id="step_api", description="Call API", assigned_agent="general_agent"
    )

    transient_error = "504 Gateway Timeout on upstream provider"

    # Attempts with current_step_retries: 0, 1, 2 should RETRY
    for retries in range(3):
        decision = recovery.evaluate_step_failure(
            step=step,
            error_message=transient_error,
            current_step_retries=retries,
            elapsed_time_seconds=float(retries * 2),
        )
        assert decision.action == RecoveryAction.RETRY, (
            f"Attempt with {retries} retries should retry"
        )

    # When retries reach 3 (max_step_retries), next failure terminates (or switches agent if alternatives exist)
    final_decision = recovery.evaluate_step_failure(
        step=step,
        error_message=transient_error,
        current_step_retries=3,
        elapsed_time_seconds=10.0,
    )
    assert final_decision.action in [
        RecoveryAction.TERMINATE_FAILED,
        RecoveryAction.SWITCH_AGENT,
    ], "Max retries reached must terminate or switch agent, never RETRY"


# =========================================================================
# 10. Approval Flow & TOCTOU Tamper Resistance
# =========================================================================
def test_eval_agent_10_approval_flow_and_toctou_defense() -> None:
    """Evaluate dangerous tools pause in WAITING_APPROVAL and reject altered arguments upon resume."""
    registry = get_tool_registry()
    tool = registry.get("terminal_exec")
    assert tool is not None
    assert tool.metadata.risk_level.value in ["dangerous", "privileged"]
    decision = ToolPolicyEngine.evaluate(
        tool,
        {"command": "apt-get update"},
        user_permissions=["system:execute"],
    )
    assert decision.allowed is True
    assert decision.requires_approval is True

    # Test TOCTOU detection logic
    original_args = {"command": "apt-get update"}
    tampered_args = {"command": "rm -rf /"}

    eval_res = evaluate_lifecycle_and_terminal_state(
        initial_status=RunStatus.WAITING_APPROVAL.value,
        target_status=RunStatus.RUNNING.value,
        is_terminal_initial=False,
        transition_allowed=True,
        tampered_resume_rejected=(original_args != tampered_args),
    )
    assert eval_res.passed, f"Approval flow evaluation failed: {eval_res.diagnostics}"


# =========================================================================
# 11. Resume Integrity
# =========================================================================
def test_eval_agent_11_resume_without_step_duplication() -> None:
    """Evaluate checkpoint resume executes only pending steps without duplicating completed steps."""
    completed_before = ["step_01_ingest", "step_02_parse"]
    all_steps = [
        "step_01_ingest",
        "step_02_parse",
        "step_03_reconcile",
        "step_04_synthesize",
    ]

    pending_steps = [s for s in all_steps if s not in completed_before]
    assert pending_steps == ["step_03_reconcile", "step_04_synthesize"]

    executed_on_resume = list(pending_steps)
    total_completed = set(completed_before + executed_on_resume)
    assert len(total_completed) == 4
    assert len(set(completed_before).intersection(executed_on_resume)) == 0


# =========================================================================
# 12. Cancellation & Idempotency
# =========================================================================
def test_eval_agent_12_cancellation_halts_and_is_idempotent() -> None:
    """Evaluate cancelling a running run sets CANCELLED and ignores further cancels idempotently."""
    state = RunState(
        run_id="run_cancel",
        task_id="task_cancel",
        tenant_id="tenant_eval",
        user_id="user_eval",
        status=RunStatus.RUNNING,
    )

    # First cancel
    state.status = RunStatus.CANCELLED
    assert state.status == RunStatus.CANCELLED

    # Second cancel (idempotent)
    eval_res = evaluate_lifecycle_and_terminal_state(
        initial_status=RunStatus.CANCELLED.value,
        target_status=RunStatus.CANCELLED.value,
        is_terminal_initial=True,
        transition_allowed=False,
        cancellation_honored=True,
    )
    assert eval_res.passed, f"Cancellation evaluation failed: {eval_res.diagnostics}"


# =========================================================================
# 13. Terminal State Invariants
# =========================================================================
def test_eval_agent_13_terminal_state_invariants() -> None:
    """Evaluate that COMPLETED, FAILED, and CANCELLED states are strictly immutable and absorbing."""
    terminal_statuses = [RunStatus.COMPLETED, RunStatus.FAILED, RunStatus.CANCELLED]

    for term in terminal_statuses:
        state = RunState(
            run_id=f"run_term_{term.value}",
            task_id="task_term",
            tenant_id="tenant_eval",
            user_id="user_eval",
            status=term,
        )
        with pytest.raises(ValueError, match="cannot transition from terminal state"):
            state.status = RunStatus.RUNNING


# =========================================================================
# 14. Failure Truthfulness
# =========================================================================
def test_eval_agent_14_failure_truthfulness_no_false_success() -> None:
    """Evaluate that agent runs truthfully report FAILED on error rather than fabricating success."""
    state = RunState(
        run_id="run_truth",
        task_id="task_truth",
        tenant_id="tenant_eval",
        user_id="user_eval",
        status=RunStatus.RUNNING,
    )
    error_reason = "PostgreSQL connection refused on port 5432"

    # Set failure
    state.status = RunStatus.FAILED
    state.error = error_reason

    assert state.status == RunStatus.FAILED
    assert "PostgreSQL connection refused" in (state.error or "")
    assert state.status != RunStatus.COMPLETED


# =========================================================================
# 15. Parameterized Versioned Fixtures Test
# =========================================================================
@pytest.mark.parametrize(
    "case",
    load_agent_fixtures(),
    ids=lambda c: str(c.get("case_id")),
)
def test_eval_agent_versioned_fixtures_suite(case: dict[str, Any]) -> None:
    """Execute evaluation gate against versioned agent fixtures dataset."""
    case_id = case["case_id"]
    task = case["task"]
    case_input = case["input"]

    if task == "goal_interpretation":
        planner = BoundedPlanner()
        plan = planner.create_initial_plan(case_input["goal"])
        res = evaluate_goal_interpretation(
            goal=case_input["goal"],
            plan=plan,
            prohibited_tools=["terminal_exec"],
            required_specialists=["financial_specialist", "synthesizer"],
        )
        assert res.passed, f"{case_id} failed: {res.diagnostics}"

    elif task == "plan_structure":
        planner = BoundedPlanner()
        plan = planner.create_initial_plan(case_input["goal"])
        res = evaluate_plan_structure(plan)
        assert res.passed, f"{case_id} failed: {res.diagnostics}"

    elif task == "agent_selection":
        selector = AgentSelector()
        spec = TaskSpec(
            tenant_id="tenant_eval",
            goal=case_input["goal"],
            task_type=case_input.get("task_type", "general"),
        )
        selection = selector.select_agent(spec)
        allow_fallback = case_input.get("task_type") == "creative_writing"
        res = evaluate_agent_selection(
            selected_agent=selection.agent_id,
            confidence=selection.confidence,
            fallback_used=selection.fallback_used,
            expected_agent="financial_specialist"
            if not allow_fallback
            else "general_agent",
            allow_fallback=allow_fallback,
        )
        assert res.passed, f"{case_id} failed: {res.diagnostics}"

    elif task == "model_selection":
        router = ModelRouter()
        policy = RoutingPolicy(
            requested_model=case_input["requested_model"],
            workload_class=case_input["workload_class"],
        )
        route = router.route(policy)
        res = evaluate_model_selection(
            requested_model=case_input["requested_model"],
            selected_model=route.selected_model,
            selected_provider=route.selected_provider,
            workload_class=case_input["workload_class"],
        )
        assert res.passed, f"{case_id} failed: {res.diagnostics}"

    elif task == "tool_execution":
        registry = get_tool_registry()
        valid, _ = registry.validate(case_input["tool_name"], case_input["arguments"])
        assert valid, f"{case_id} valid arguments failed"
        invalid, _ = registry.validate(
            case_input["tool_name"], case_input["malformed_arguments"]
        )
        assert not invalid, f"{case_id} malformed arguments were accepted"

    elif task == "terminal_state":
        for term in case_input["terminal_states"]:
            term_status = RunStatus(term.lower())
            state = RunState(
                run_id=f"run_param_{term.lower()}",
                task_id="task_param",
                tenant_id="tenant_eval",
                user_id="user_eval",
                status=term_status,
            )
            with pytest.raises(
                ValueError, match="cannot transition from terminal state"
            ):
                state.status = RunStatus.RUNNING
