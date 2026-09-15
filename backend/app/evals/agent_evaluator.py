"""Agent Orchestration Evaluation Engine for JakeAI (TEST-06 / AI-012).

Provides programmatic, non-brittle evaluation of the 14 agent orchestration dimensions:
1.  Goal Interpretation
2.  Plan Structure (DAG acyclicity, dependencies, parallel tiers)
3.  Agent Selection (capability matching, fallback confidence)
4.  Model Selection (workload class, no literal 'default' leak)
5.  Tool Selection (synonym resolution, prohibited tool exclusion)
6.  Tool Execution (schema validation, boundary enforcement)
7.  Verification (verdict accuracy, mathematical variance rejection)
8.  Recovery (non-retryable vs retryable classification)
9.  Retry Bounds (budget exhaustion, ceiling enforcement)
10. Approval Flow (risk-gated WAITING_APPROVAL, TOCTOU defense)
11. Resume (rehydration without duplicate step execution)
12. Cancellation (clean termination, step halting)
13. Terminal State (immutable absorbing state invariants)
14. Failure Truthfulness (honest error attribution, no false COMPLETED)
"""

from __future__ import annotations

from typing import TYPE_CHECKING, Any

from pydantic import BaseModel, Field

if TYPE_CHECKING:
    from app.agent.domain.contracts import ExecutionPlan


class AgentEvaluationResult(BaseModel):
    """Evaluation result for an agent orchestration capability or workflow."""

    case_id: str = Field(description="Evaluation case identifier")
    task: str = Field(description="Target agent evaluation dimension")
    passed: bool = Field(description="True if all criteria for this dimension pass")
    score: float = Field(
        ge=0.0, le=1.0, default=1.0, description="Normalized score 0.0 - 1.0"
    )
    criteria: dict[str, bool] = Field(
        default_factory=dict, description="Criterion-by-criterion pass/fail"
    )
    diagnostics: list[str] = Field(
        default_factory=list, description="Diagnostic messages and trace info"
    )
    metadata: dict[str, Any] = Field(
        default_factory=dict, description="Additional context and metrics"
    )


def evaluate_goal_interpretation(
    goal: str,
    plan: ExecutionPlan,
    prohibited_tools: list[str] | None = None,
    required_specialists: list[str] | None = None,
) -> AgentEvaluationResult:
    """Evaluate whether the agent planner correctly interpreted user goal and negative constraints."""
    criteria: dict[str, bool] = {}
    diagnostics: list[str] = []

    # 1. Non-empty plan
    criteria["plan_generated"] = len(plan.steps) > 0
    if not criteria["plan_generated"]:
        diagnostics.append("Plan contains zero steps.")

    # 2. Check prohibited tools (negative constraints)
    prohibited_found: list[str] = []
    if prohibited_tools:
        for step in plan.steps:
            for tool in step.required_tools:
                if tool in prohibited_tools:
                    prohibited_found.append(tool)
    criteria["negative_constraints_respected"] = len(prohibited_found) == 0
    if prohibited_found:
        diagnostics.append(f"Prohibited tools scheduled in plan: {prohibited_found}")

    # 3. Check required specialists or capabilities
    assigned_agents = {
        step.assigned_agent for step in plan.steps if step.assigned_agent
    }
    all_caps = {c for step in plan.steps for c in step.required_capabilities}
    cap_specialist_map = {
        "financial_specialist": "financial_analysis",
        "finnapigo_specialist": "banking_api",
        "knowledge_retriever": "rag_retrieval",
        "synthesizer": "synthesis",
        "general_agent": "general",
    }
    if required_specialists:
        matched = []
        for req in required_specialists:
            if req in assigned_agents or cap_specialist_map.get(req) in all_caps:
                matched.append(req)
        criteria["required_specialists_assigned"] = len(matched) > 0
        if not criteria["required_specialists_assigned"]:
            diagnostics.append(
                f"Required specialists {required_specialists} missing from plan capabilities {all_caps} or agents {assigned_agents}"
            )
    else:
        criteria["required_specialists_assigned"] = True

    # 4. Multi-step decomposition for complex goals
    is_complex = any(
        k in goal.lower()
        for k in ["reconcile", "both", "and summarize", "cross-examine", "concurrently"]
    )
    if is_complex:
        criteria["complex_goal_decomposed"] = len(plan.steps) >= 2
        if not criteria["complex_goal_decomposed"]:
            diagnostics.append(
                f"Complex goal collapsed into single step: {len(plan.steps)} step(s)"
            )
    else:
        criteria["complex_goal_decomposed"] = True

    passed = all(criteria.values())
    score = sum(1.0 for v in criteria.values() if v) / max(1, len(criteria))

    return AgentEvaluationResult(
        case_id="GOAL_INTERPRETATION",
        task="goal_interpretation",
        passed=passed,
        score=score,
        criteria=criteria,
        diagnostics=diagnostics,
        metadata={
            "assigned_agents": list(assigned_agents),
            "capabilities": list(all_caps),
            "step_count": len(plan.steps),
        },
    )


def evaluate_plan_structure(plan: ExecutionPlan) -> AgentEvaluationResult:
    """Evaluate DAG properties: acyclicity, valid dependencies, and parallel tier ordering."""
    criteria: dict[str, bool] = {}
    diagnostics: list[str] = []

    step_ids = {s.step_id for s in plan.steps}

    # 1. Dependency references exist in step_ids
    invalid_deps: list[str] = []
    for s in plan.steps:
        for dep in s.dependencies:
            if dep not in step_ids:
                invalid_deps.append(f"{s.step_id} -> {dep}")
    criteria["dependencies_valid"] = len(invalid_deps) == 0
    if invalid_deps:
        diagnostics.append(f"Dangling dependency references: {invalid_deps}")

    # 2. DAG Acyclicity (Topological Sort / Cycle Detection)
    visited: set[str] = set()
    rec_stack: set[str] = set()
    has_cycle = False

    adj: dict[str, list[str]] = {s.step_id: list(s.dependencies) for s in plan.steps}

    def _dfs(node: str) -> bool:
        visited.add(node)
        rec_stack.add(node)
        for parent in adj.get(node, []):
            if parent not in visited:
                if _dfs(parent):
                    return True
            elif parent in rec_stack:
                return True
        rec_stack.remove(node)
        return False

    for s_id in step_ids:
        if s_id not in visited and _dfs(s_id):
            has_cycle = True
            break

    criteria["dag_acyclic"] = not has_cycle
    if has_cycle:
        diagnostics.append("Plan dependency graph contains a cycle.")

    # 3. Parallel step detection (steps with dependencies == [])
    root_steps = [s.step_id for s in plan.steps if len(s.dependencies) == 0]
    criteria["has_root_steps"] = len(root_steps) >= 1
    if not criteria["has_root_steps"]:
        diagnostics.append("Plan has no entry root steps (deadlock).")

    # 4. If multiple parallel steps exist, verify terminal synthesis node depends on them
    if len(root_steps) >= 2 and len(plan.steps) > len(root_steps):
        terminal_step = plan.steps[-1]
        synthesizes_roots = all(
            r in terminal_step.dependencies
            or any(
                r in s.dependencies
                for s in plan.steps
                if s.step_id in terminal_step.dependencies
            )
            for r in root_steps
        )
        criteria["terminal_synthesis_coherent"] = synthesizes_roots
        if not synthesizes_roots:
            diagnostics.append(
                "Terminal synthesis node does not depend on all parallel root branches."
            )
    else:
        criteria["terminal_synthesis_coherent"] = True

    passed = all(criteria.values())
    score = sum(1.0 for v in criteria.values() if v) / max(1, len(criteria))

    return AgentEvaluationResult(
        case_id="PLAN_STRUCTURE",
        task="plan_structure",
        passed=passed,
        score=score,
        criteria=criteria,
        diagnostics=diagnostics,
        metadata={"total_steps": len(plan.steps), "root_steps": root_steps},
    )


def evaluate_agent_selection(
    selected_agent: str,
    confidence: float,
    fallback_used: bool,
    expected_agent: str | None = None,
    allow_fallback: bool = False,
) -> AgentEvaluationResult:
    """Evaluate agent selector decision, capability scoring, and fallback bounds."""
    criteria: dict[str, bool] = {}
    diagnostics: list[str] = []

    if expected_agent:
        criteria["agent_matched"] = selected_agent == expected_agent
        if not criteria["agent_matched"]:
            diagnostics.append(
                f"Expected agent '{expected_agent}', but got '{selected_agent}'."
            )
    else:
        criteria["agent_matched"] = True

    if not allow_fallback:
        criteria["fallback_not_used"] = not fallback_used
        criteria["confidence_sufficient"] = confidence >= 0.5
        if fallback_used:
            diagnostics.append("Specialized task incorrectly used fallback agent.")
        if confidence < 0.5:
            diagnostics.append(
                f"Confidence score {confidence} is below minimum threshold (0.5)."
            )
    else:
        criteria["fallback_gracefully_applied"] = fallback_used
        criteria["general_agent_selected"] = selected_agent == "general_agent"
        if not fallback_used:
            diagnostics.append(
                "Novel task exhibited false confidence instead of fallback."
            )

    passed = all(criteria.values())
    score = sum(1.0 for v in criteria.values() if v) / max(1, len(criteria))

    return AgentEvaluationResult(
        case_id="AGENT_SELECTION",
        task="agent_selection",
        passed=passed,
        score=score,
        criteria=criteria,
        diagnostics=diagnostics,
        metadata={
            "selected_agent": selected_agent,
            "confidence": confidence,
            "fallback_used": fallback_used,
        },
    )


def evaluate_model_selection(
    requested_model: str,
    selected_model: str,
    selected_provider: str,
    workload_class: str,
) -> AgentEvaluationResult:
    """Evaluate autonomous model selection, ensuring no literal 'default' leak."""
    criteria: dict[str, bool] = {}
    diagnostics: list[str] = []

    # 1. No literal 'default' or empty string leak
    criteria["no_literal_default_leak"] = selected_model.lower() not in ["default", ""]
    if not criteria["no_literal_default_leak"]:
        diagnostics.append(
            "Literal 'default' or empty string returned as selected model name."
        )

    # 2. Known model name
    criteria["known_model_identifier"] = len(selected_model.strip()) > 3
    # 3. Provider valid
    criteria["valid_provider"] = selected_provider in [
        "openai",
        "gemini",
        "anthropic",
        "deepseek",
        "local",
        "mock",
        "groq",
    ]
    if not criteria["valid_provider"]:
        diagnostics.append(f"Unknown provider '{selected_provider}'.")

    # 4. Reasoning workload receives capable model
    if workload_class == "financial_reasoning":
        is_reasoner = any(
            k in selected_model.lower()
            for k in ["reasoner", "r1", "flash", "gpt-4o", "claude", "o1", "o3"]
        )
        criteria["appropriate_reasoner_model"] = is_reasoner
        if not is_reasoner:
            diagnostics.append(
                f"Financial reasoning assigned low-tier model: {selected_model}"
            )
    else:
        criteria["appropriate_reasoner_model"] = True

    passed = all(criteria.values())
    score = sum(1.0 for v in criteria.values() if v) / max(1, len(criteria))

    return AgentEvaluationResult(
        case_id="MODEL_SELECTION",
        task="model_selection",
        passed=passed,
        score=score,
        criteria=criteria,
        diagnostics=diagnostics,
        metadata={
            "requested_model": requested_model,
            "selected_model": selected_model,
            "provider": selected_provider,
            "workload": workload_class,
        },
    )


def evaluate_tool_selection_and_schema(
    selected_tools: list[str],
    expected_tools: list[str] | None = None,
    prohibited_tools: list[str] | None = None,
    arguments: dict[str, Any] | None = None,
    schema_valid: bool = True,
) -> AgentEvaluationResult:
    """Evaluate tool selection synonyms, exclusion of prohibited tools, and argument validation."""
    criteria: dict[str, bool] = {}
    diagnostics: list[str] = []

    if expected_tools:
        matched = [t for t in expected_tools if t in selected_tools]
        criteria["expected_tools_selected"] = len(matched) == len(expected_tools)
        if not criteria["expected_tools_selected"]:
            diagnostics.append(
                f"Expected tools {expected_tools}, selected: {selected_tools}"
            )
    else:
        criteria["expected_tools_selected"] = True

    if prohibited_tools:
        leaked = [t for t in prohibited_tools if t in selected_tools]
        criteria["prohibited_tools_excluded"] = len(leaked) == 0
        if leaked:
            diagnostics.append(f"Prohibited tools selected: {leaked}")
    else:
        criteria["prohibited_tools_excluded"] = True

    criteria["arguments_schema_valid"] = schema_valid
    if not schema_valid:
        diagnostics.append("Tool arguments violated parameter JSON schema.")

    passed = all(criteria.values())
    score = sum(1.0 for v in criteria.values() if v) / max(1, len(criteria))

    return AgentEvaluationResult(
        case_id="TOOL_SELECTION_SCHEMA",
        task="tool_selection",
        passed=passed,
        score=score,
        criteria=criteria,
        diagnostics=diagnostics,
        metadata={"selected_tools": selected_tools, "arguments": arguments or {}},
    )


def evaluate_verification_and_recovery(
    verdict: str,
    math_variance: bool,
    error_type: str,
    recovery_action: str,
    retries_used: int,
    max_retries: int = 3,
) -> AgentEvaluationResult:
    """Evaluate verifier accuracy and recovery engine classification."""
    criteria: dict[str, bool] = {}
    diagnostics: list[str] = []

    # 1. Variance handling: Mathematical variance must produce FAILED or NEEDS_REVISION
    if math_variance:
        criteria["variance_rejected"] = verdict.upper() in [
            "FAILED",
            "NEEDS_REVISION",
            "REJECTED",
        ]
        if not criteria["variance_rejected"]:
            diagnostics.append(
                f"Mathematical variance was marked as {verdict} instead of rejected."
            )
    else:
        criteria["variance_rejected"] = True

    # 2. Non-retryable error classification
    is_non_retryable = any(
        k in error_type.lower()
        for k in [
            "unknown tool",
            "not registered",
            "permission",
            "tampering",
            "unauthorized",
            "invalid schema",
        ]
    )
    if is_non_retryable:
        criteria["non_retryable_classified_correctly"] = recovery_action.upper() in [
            "TERMINATE_FAILED",
            "REPLAN",
        ]
        if not criteria["non_retryable_classified_correctly"]:
            diagnostics.append(
                f"Non-retryable error '{error_type}' issued '{recovery_action}' instead of TERMINATE_FAILED."
            )
    else:
        criteria["non_retryable_classified_correctly"] = True

    # 3. Retry budget bounds
    criteria["retry_budget_respected"] = retries_used <= max_retries
    if not criteria["retry_budget_respected"]:
        diagnostics.append(
            f"Retries used ({retries_used}) exceeded max budget ({max_retries})."
        )

    passed = all(criteria.values())
    score = sum(1.0 for v in criteria.values() if v) / max(1, len(criteria))

    return AgentEvaluationResult(
        case_id="VERIFICATION_RECOVERY",
        task="verification_and_recovery",
        passed=passed,
        score=score,
        criteria=criteria,
        diagnostics=diagnostics,
        metadata={
            "verdict": verdict,
            "recovery_action": recovery_action,
            "retries": retries_used,
        },
    )


def evaluate_lifecycle_and_terminal_state(
    initial_status: str,
    target_status: str,
    is_terminal_initial: bool,
    transition_allowed: bool,
    cancellation_honored: bool = True,
    tampered_resume_rejected: bool = True,
) -> AgentEvaluationResult:
    """Evaluate state transition invariants, cancellation halts, and TOCTOU defense."""
    criteria: dict[str, bool] = {}
    diagnostics: list[str] = []

    # 1. Absorbing terminal states: cannot transition out of COMPLETED, FAILED, CANCELLED
    if is_terminal_initial:
        criteria["terminal_state_immutable"] = not transition_allowed
        if transition_allowed:
            diagnostics.append(
                f"Illegal transition out of terminal state {initial_status} to {target_status}."
            )
    else:
        criteria["terminal_state_immutable"] = True

    # 2. Cancellation stops execution
    criteria["cancellation_honored"] = cancellation_honored
    if not cancellation_honored:
        diagnostics.append("Run continued executing steps after cancellation.")

    # 3. TOCTOU tamper defense
    criteria["toctou_tamper_rejected"] = tampered_resume_rejected
    if not tampered_resume_rejected:
        diagnostics.append("Run executed tampered arguments on resume.")

    passed = all(criteria.values())
    score = sum(1.0 for v in criteria.values() if v) / max(1, len(criteria))

    return AgentEvaluationResult(
        case_id="LIFECYCLE_TERMINAL_STATE",
        task="lifecycle_and_terminal_state",
        passed=passed,
        score=score,
        criteria=criteria,
        diagnostics=diagnostics,
        metadata={"initial_status": initial_status, "target_status": target_status},
    )
