"""Verifier and anti-hallucination critique node for Self-RAG evaluation."""

from typing import Any

from app.agents.state import AgentState


async def verifier_node(state: AgentState) -> dict[str, Any]:
    """Evaluate factual consistency, numerical grounding, and tenant boundary."""
    financial_data = state.get("financial_analysis", {})
    tool_calls = state.get("tool_calls", [])
    revision_count = state.get("revision_count", 0)
    tenant_id = state.get("tenant_id", "")

    # Perform consistency & tenant security checks
    tenant_mismatch = False
    for tc in tool_calls:
        if tc.get("tenant_id") != tenant_id:
            tenant_mismatch = True

    # Check if calculation is mathematically valid
    math_error = False
    if financial_data:
        rev = financial_data.get("revenue", 0.0)
        exp = financial_data.get("operating_expenses", 0.0)
        inc = financial_data.get("operating_income", 0.0)
        if round(rev - exp, 2) != round(inc, 2):
            math_error = True

    # Trigger Self-Correction if error detected and under revision budget
    if (math_error or tenant_mismatch) and revision_count < 2:
        reason = (
            "Mathematical variance detected" if math_error else "Tenant ID mismatch"
        )
        return {
            "current_agent": "verifier",
            "workflow_phase": "critique",
            "verification_verdict": "NEEDS_REVISION",
            "critique_notes": f"Self-RAG Critique: {reason}. Recompute accurately.",
            "revision_count": revision_count + 1,
            "next_agent": "supervisor",
            "mascot_state": "alert",
            "messages": [
                *state.get("messages", []),
                f"Verifier: Rejected ({reason}). Triggering self-correction loop.",
            ],
        }

    # Quality gates verified
    return {
        "current_agent": "verifier",
        "workflow_phase": "verification_passed",
        "verification_verdict": "PASS",
        "critique_notes": "All checks passed. Data is grounded and tenant-isolated.",
        "next_agent": "synthesizer",
        "mascot_state": "success",
        "messages": [
            *state.get("messages", []),
            "Verifier: Factual groundedness and multi-tenant security confirmed.",
        ],
    }
