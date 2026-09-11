"""Verifier and anti-hallucination critique node delegating to CanonicalVerifier."""

from typing import Any

from app.agent.domain.contracts import VerificationVerdict
from app.agent.verification.verifier import get_canonical_verifier
from app.agents.state import AgentState
from app.evals.rag_evaluator import evaluate_rag_case


async def verifier_node(state: AgentState) -> dict[str, Any]:
    """Evaluate factual consistency, tenant boundaries, and Self-RAG via CanonicalVerifier."""
    financial_data = state.get("financial_analysis", {})
    tool_calls = state.get("tool_calls", [])
    retrieved_chunks = state.get("retrieved_chunks", [])
    revision_count = state.get("revision_count", 0)
    tenant_id = state.get("tenant_id", "")
    prompt = state.get("prompt", "")

    verifier = get_canonical_verifier()
    res = verifier.verify_execution(
        tenant_id=tenant_id,
        goal=prompt,
        step_outputs=[financial_data] if financial_data else [],
        tool_calls=tool_calls,
        retrieved_chunks=retrieved_chunks,
        financial_data=financial_data,
        revision_count=revision_count,
        eval_fn=evaluate_rag_case,
    )

    # 1. Multi-Tenant Boundary Isolation Breach -> Immediate REJECTED
    if res.verdict == VerificationVerdict.REJECTED:
        return {
            "current_agent": "verifier",
            "workflow_phase": "verification_failed",
            "verification_verdict": "REJECTED",
            "critique_notes": f"Immediate rejection: {res.reason}.",
            "groundedness_score": res.groundedness_score,
            "revision_count": revision_count,
            "next_agent": "synthesizer",
            "mascot_state": "alert",
            "messages": [
                *state.get("messages", []),
                (
                    f"Verifier: Immediately REJECTED ({res.reason}). "
                    "Hard security boundary breached."
                ),
            ],
        }

    # 2. Arithmetic or Groundedness failure requiring revision
    if res.verdict == VerificationVerdict.NEEDS_REVISION:
        return {
            "current_agent": "verifier",
            "workflow_phase": "critique",
            "verification_verdict": "NEEDS_REVISION",
            "critique_notes": f"Self-RAG Critique: {res.reason}. Recompute accurately.",
            "groundedness_score": res.groundedness_score,
            "revision_count": revision_count + 1,
            "next_agent": "supervisor",
            "mascot_state": "alert",
            "messages": [
                *state.get("messages", []),
                f"Verifier: Rejected ({res.reason}). Triggering self-correction loop.",
            ],
        }

    # 3. Terminal Verification Failure after max revisions
    if res.verdict == VerificationVerdict.FAILED:
        return {
            "current_agent": "verifier",
            "workflow_phase": "verification_failed",
            "verification_verdict": "FAILED",
            "critique_notes": f"Verification failed after {revision_count} revisions: {res.reason}.",
            "groundedness_score": res.groundedness_score,
            "revision_count": revision_count,
            "next_agent": "synthesizer",
            "mascot_state": "alert",
            "messages": [
                *state.get("messages", []),
                (
                    f"Verifier: Terminal FAILED ({res.reason}). "
                    f"Maximum revisions ({verifier.max_revisions}) exhausted."
                ),
            ],
        }

    # 4. Quality and Security Gates Passed
    return {
        "current_agent": "verifier",
        "workflow_phase": "verification_passed",
        "verification_verdict": "PASS",
        "groundedness_score": res.groundedness_score,
        "critique_notes": res.reason,
        "next_agent": "synthesizer",
        "mascot_state": "success",
        "messages": [
            *state.get("messages", []),
            f"Verifier: Groundedness ({res.groundedness_score:.2f}) and tenant isolation confirmed.",
        ],
    }
