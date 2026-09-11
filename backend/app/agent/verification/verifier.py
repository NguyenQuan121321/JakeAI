"""Canonical Verifier inspecting actual execution results for security, consistency, and grounding."""

from __future__ import annotations

import logging
from typing import Any

from app.agent.domain.contracts import (
    RecoveryAction,
    VerificationResult,
    VerificationVerdict,
)
from app.evals.rag_evaluator import evaluate_rag_case

logger = logging.getLogger(__name__)


class CanonicalVerifier:
    """Rigorous verification engine enforcing multi-tenant boundaries, math invariants, and Self-RAG."""

    def __init__(self, max_revisions: int = 2) -> None:
        self.max_revisions = max_revisions

    def verify_execution(
        self,
        tenant_id: str,
        goal: str,
        step_outputs: list[Any],
        tool_calls: list[dict[str, Any]],
        retrieved_chunks: list[dict[str, Any]],
        financial_data: dict[str, Any] | None = None,
        final_output: str | None = None,
        revision_count: int = 0,
        eval_fn: Any = None,
    ) -> VerificationResult:
        """Inspect actual execution records and return structured VerificationResult."""
        evidence: dict[str, Any] = {
            "tenant_id": tenant_id,
            "revision_count": revision_count,
            "total_tool_calls": len(tool_calls),
            "total_chunks": len(retrieved_chunks),
        }

        # 1. Multi-Tenant Boundary Isolation Gate (Hard Security Invariant)
        tenant_breaches: list[str] = []
        for tc in tool_calls:
            tc_tenant = tc.get("tenant_id")
            if tc_tenant and tc_tenant != tenant_id:
                tenant_breaches.append(
                    f"Tool call '{tc.get('tool_name')}' accessed tenant '{tc_tenant}'"
                )
        for rc in retrieved_chunks:
            rc_tenant = rc.get("tenant_id")
            if rc_tenant and rc_tenant != tenant_id:
                tenant_breaches.append(
                    f"Retrieved chunk belongs to tenant '{rc_tenant}'"
                )

        if tenant_breaches:
            reason = (
                f"Multi-tenant boundary breach detected: {'; '.join(tenant_breaches)}"
            )
            evidence["breaches"] = tenant_breaches
            logger.warning("CanonicalVerifier REJECTED execution: %s", reason)
            return VerificationResult(
                verdict=VerificationVerdict.REJECTED,
                reason=reason,
                violated_invariant="Multi-tenant boundary isolation",
                evidence=evidence,
                recoverability=False,
                recommended_recovery_action=RecoveryAction.TERMINATE_REJECTED,
                groundedness_score=0.0,
            )

        # 2. Mathematical Consistency Gate
        math_errors: list[str] = []
        fin = financial_data or {}
        # Also check if any step output has financial analysis
        if not fin:
            for s in step_outputs:
                if isinstance(s, dict) and "financial_analysis" in s:
                    fin = s["financial_analysis"]
                    break
                if isinstance(s, dict) and "revenue" in s and "operating_expenses" in s:
                    fin = s
                    break

        if fin:
            rev = float(fin.get("revenue", 0.0))
            exp = float(fin.get("operating_expenses", 0.0))
            inc = float(fin.get("operating_income", 0.0))
            expected_inc = round(rev - exp, 2)
            actual_inc = round(inc, 2)
            if expected_inc != actual_inc:
                math_errors.append(
                    f"Mathematical variance detected: expected operating income ${expected_inc:,.2f} "
                    f"(rev ${rev:,.2f} - exp ${exp:,.2f}), got ${actual_inc:,.2f}"
                )
            evidence["financial_check"] = {
                "revenue": rev,
                "operating_expenses": exp,
                "operating_income": inc,
                "expected_operating_income": expected_inc,
            }

        # 3. Groundedness & Anti-Hallucination Gate (Self-RAG)
        groundedness_score = 1.0
        grounding_reasons: list[str] = []

        context_parts: list[str] = []
        if retrieved_chunks:
            # When retrieved chunks exist, they are the authoritative grounding source.
            # Step outputs and financial data must NOT pollute grounding context,
            # otherwise hallucinated numbers would self-validate.
            context_parts.extend(
                c.get("content", "") for c in retrieved_chunks if c.get("content")
            )
        else:
            # Fallback: no retrieval pipeline — use execution evidence as context
            for s in step_outputs:
                if isinstance(s, dict):
                    for k, v in s.items():
                        context_parts.append(f"{k} {v}")
                elif isinstance(s, str):
                    context_parts.append(s)
                elif isinstance(s, list):
                    for item in s:
                        context_parts.append(str(item))
            for tc in tool_calls:
                tc_out = tc.get("output")
                if tc_out is not None:
                    if isinstance(tc_out, dict):
                        for k, v in tc_out.items():
                            context_parts.append(f"{k} {v}")
                    elif isinstance(tc_out, list):
                        for item in tc_out:
                            if isinstance(item, dict):
                                for k, v in item.items():
                                    context_parts.append(f"{k} {v}")
                            else:
                                context_parts.append(str(item))
                    else:
                        context_parts.append(str(tc_out))
            if fin:
                for k, v in fin.items():
                    context_parts.append(f"{k} {v}")
        context_parts.append(goal)
        context_parts.append(f"tenant {tenant_id}")

        context_text = " ".join(context_parts)

        response_to_evaluate = final_output or ""
        if not response_to_evaluate and fin:
            response_to_evaluate = (
                f"Gross Revenue: ${fin.get('revenue', 0.0)} "
                f"Operating Expenses: ${fin.get('operating_expenses', 0.0)} "
                f"Operating Income: ${fin.get('operating_income', 0.0)}"
            )

        active_evaluator = eval_fn or evaluate_rag_case
        eval_res = active_evaluator(
            {
                "case_id": f"verify-{tenant_id}",
                "query": goal,
                "context": context_text,
                "response": response_to_evaluate,
                "tenant_id": tenant_id,
            }
        )
        groundedness_score = getattr(eval_res, "faithfulness_score", 1.0)
        anti_hallucination_passed = getattr(eval_res, "anti_hallucination_passed", True)
        is_grounded = groundedness_score >= 0.80 and anti_hallucination_passed
        if not is_grounded:
            if not anti_hallucination_passed:
                grounding_reasons.append(
                    "Anti-hallucination check failed: ungrounded numerical claims detected"
                )
            if groundedness_score < 0.80:
                grounding_reasons.append(
                    f"Groundedness below threshold ({groundedness_score:.2f} < 0.80)"
                )
        evidence["groundedness_score"] = groundedness_score

        # 4. Synthesize Gate Failures and Evaluate Revision Budget
        all_failures = math_errors + grounding_reasons
        if all_failures:
            critique_msg = "; ".join(all_failures)
            evidence["failures"] = all_failures

            if revision_count < self.max_revisions:
                return VerificationResult(
                    verdict=VerificationVerdict.NEEDS_REVISION,
                    reason=f"Self-RAG Critique: {critique_msg}. Recompute accurately.",
                    violated_invariant=math_errors[0]
                    if math_errors
                    else grounding_reasons[0],
                    evidence=evidence,
                    recoverability=True,
                    recommended_recovery_action=RecoveryAction.REPLAN,
                    groundedness_score=groundedness_score,
                )
            else:
                return VerificationResult(
                    verdict=VerificationVerdict.FAILED,
                    reason=f"Verification failed after {revision_count} revisions: {critique_msg}.",
                    violated_invariant=math_errors[0]
                    if math_errors
                    else grounding_reasons[0],
                    evidence=evidence,
                    recoverability=False,
                    recommended_recovery_action=RecoveryAction.TERMINATE_FAILED,
                    groundedness_score=groundedness_score,
                )

        # 5. Quality and Security Gates Passed
        return VerificationResult(
            verdict=VerificationVerdict.PASS,
            reason=(
                f"All quality, safety, and consistency invariants verified. "
                f"Groundedness: {groundedness_score:.2f}, tenant isolation intact."
            ),
            violated_invariant=None,
            evidence=evidence,
            recoverability=True,
            recommended_recovery_action=RecoveryAction.NONE,
            groundedness_score=groundedness_score,
        )


_default_verifier: CanonicalVerifier | None = None


def get_canonical_verifier() -> CanonicalVerifier:
    """Singleton accessor for CanonicalVerifier."""
    global _default_verifier
    if _default_verifier is None:
        _default_verifier = CanonicalVerifier()
    return _default_verifier
