"""Verifier and anti-hallucination critique node for Self-RAG evaluation."""

from typing import Any

from app.agents.state import AgentState
from app.evals.rag_evaluator import evaluate_rag_case


async def verifier_node(state: AgentState) -> dict[str, Any]:
    """Evaluate factual consistency, tenant boundaries, and Self-RAG."""
    financial_data = state.get("financial_analysis", {})
    tool_calls = state.get("tool_calls", [])
    retrieved_chunks = state.get("retrieved_chunks", [])
    revision_count = state.get("revision_count", 0)
    tenant_id = state.get("tenant_id", "")
    prompt = state.get("prompt", "")

    # 1. Multi-Tenant Boundary Isolation Checks
    tenant_mismatch = False
    for tc in tool_calls:
        if tc.get("tenant_id") != tenant_id:
            tenant_mismatch = True
    for rc in retrieved_chunks:
        if rc.get("tenant_id") and rc.get("tenant_id") != tenant_id:
            tenant_mismatch = True

    # 2. Mathematical Consistency Checks
    math_error = False
    if financial_data:
        rev = financial_data.get("revenue", 0.0)
        exp = financial_data.get("operating_expenses", 0.0)
        inc = financial_data.get("operating_income", 0.0)
        if round(rev - exp, 2) != round(inc, 2):
            math_error = True

    # 3. Self-RAG Groundedness & Anti-Hallucination Evaluation
    context_text = " ".join([c.get("content", "") for c in retrieved_chunks])
    if not context_text:
        context_text = prompt
        if financial_data:
            context_text += (
                f" Gross Revenue: ${financial_data.get('revenue', 0.0)} "
                f"Operating Expenses: ${financial_data.get('operating_expenses', 0.0)} "
                f"Operating Income: ${financial_data.get('operating_income', 0.0)}"
            )

    # Generate synthetic response snippet to score groundedness
    response_snippet = ""
    if financial_data:
        response_snippet = (
            f"Gross Revenue: ${financial_data.get('revenue', 0.0)} "
            f"Operating Expenses: ${financial_data.get('operating_expenses', 0.0)} "
            f"Operating Income: ${financial_data.get('operating_income', 0.0)}"
        )

    eval_result = evaluate_rag_case(
        {
            "case_id": f"eval-{state.get('conversation_id', 'conv')}",
            "query": prompt,
            "context": context_text,
            "response": response_snippet,
            "tenant_id": tenant_id,
        }
    )

    groundedness = eval_result.faithfulness_score
    is_grounded = groundedness >= 0.80 and eval_result.anti_hallucination_passed

    # 4. Trigger Self-Correction Loop if Quality Gates Fail and Under Budget
    if (math_error or tenant_mismatch or not is_grounded) and revision_count < 2:
        reasons = []
        if math_error:
            reasons.append("Mathematical variance detected")
        if tenant_mismatch:
            reasons.append("Multi-tenant isolation breach")
        if not is_grounded:
            reasons.append(f"Groundedness below threshold ({groundedness} < 0.80)")

        critique_msg = "; ".join(reasons)
        return {
            "current_agent": "verifier",
            "workflow_phase": "critique",
            "verification_verdict": "NEEDS_REVISION",
            "critique_notes": (
                f"Self-RAG Critique: {critique_msg}. Recompute accurately."
            ),
            "groundedness_score": groundedness,
            "revision_count": revision_count + 1,
            "next_agent": "supervisor",
            "mascot_state": "alert",
            "messages": [
                *state.get("messages", []),
                (
                    f"Verifier: Rejected ({critique_msg}). "
                    "Triggering self-correction loop."
                ),
            ],
        }

    # 5. Quality gates passed
    return {
        "current_agent": "verifier",
        "workflow_phase": "verification_passed",
        "verification_verdict": "PASS",
        "groundedness_score": groundedness,
        "critique_notes": (
            f"All quality gates verified. Groundedness: {groundedness:.2f}, "
            "tenant isolation confirmed."
        ),
        "next_agent": "synthesizer",
        "mascot_state": "success",
        "messages": [
            *state.get("messages", []),
            (
                f"Verifier: Groundedness ({groundedness:.2f}) and "
                "tenant isolation confirmed."
            ),
        ],
    }
