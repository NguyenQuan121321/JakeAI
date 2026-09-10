"""Regression tests for Verifier invariant guarantees (TASK ORC-01).

Guarantees:
- IF tenant_mismatch: immediately return FAILED / REJECTED.
- ELSE IF math_error OR not_grounded:
    IF revision_count < max_revisions: return NEEDS_REVISION
    ELSE: return FAILED / REJECTED
- NEVER return PASS when any hard verification failure remains.
- PASS is allowed only when:
    tenant_mismatch == False
    AND math_error == False
    AND grounding == valid
    AND all other hard gates passed.
"""

from typing import TYPE_CHECKING
from unittest.mock import patch

import pytest

from app.agents.verifier import verifier_node
from app.evals.rag_evaluator import RAGEvalResult

if TYPE_CHECKING:
    from app.agents.state import AgentState


@pytest.mark.asyncio
async def test_verifier_tenant_mismatch_at_revision_0() -> None:
    """Tenant mismatch at revision 0 must immediately return REJECTED without retry loop."""
    state: AgentState = {
        "prompt": "Show account balance",
        "tenant_id": "tenant-legitimate",
        "user_id": "user-01",
        "tool_calls": [
            {
                "tool_name": "get_account_balance",
                "tenant_id": "tenant-other-owner",  # Breach!
            }
        ],
        "revision_count": 0,
    }

    result = await verifier_node(state)
    assert result["verification_verdict"] == "REJECTED"
    assert result["workflow_phase"] == "verification_failed"
    assert "Multi-tenant" in result["critique_notes"]
    assert result["next_agent"] == "synthesizer"
    assert result["mascot_state"] == "alert"


@pytest.mark.asyncio
async def test_verifier_tenant_mismatch_at_max_revision() -> None:
    """Tenant mismatch at max revision must return REJECTED, NEVER PASS."""
    state: AgentState = {
        "prompt": "Show account balance",
        "tenant_id": "tenant-legitimate",
        "user_id": "user-01",
        "tool_calls": [],
        "retrieved_chunks": [
            {
                "chunk_id": "c1",
                "content": "Secret ledger",
                "tenant_id": "tenant-adversary",  # Breach!
            }
        ],
        "revision_count": 2,  # At max revisions
    }

    result = await verifier_node(state)
    assert result["verification_verdict"] == "REJECTED"
    assert result["workflow_phase"] == "verification_failed"
    assert result["verification_verdict"] != "PASS"


@pytest.mark.asyncio
async def test_verifier_math_error_at_max_revision() -> None:
    """Math error at max revision must return FAILED, NEVER PASS."""
    state: AgentState = {
        "prompt": "Calculate margin",
        "tenant_id": "tenant-test",
        "user_id": "user-01",
        "financial_analysis": {
            "revenue": 1000.0,
            "operating_expenses": 400.0,
            "operating_income": 999.0,  # 1000 - 400 != 999
        },
        "tool_calls": [],
        "revision_count": 2,  # Reached max revisions
    }

    result = await verifier_node(state)
    assert result["verification_verdict"] == "FAILED"
    assert result["workflow_phase"] == "verification_failed"
    assert "Mathematical variance" in result["critique_notes"]
    assert result["verification_verdict"] != "PASS"


@pytest.mark.asyncio
async def test_verifier_ungrounded_answer_at_max_revision() -> None:
    """Ungrounded answer (low faithfulness / anti-hallucination failed) at max revision returns FAILED."""
    fake_eval = RAGEvalResult(
        case_id="eval-ungrounded",
        faithfulness_score=0.40,  # Below 0.80
        context_relevancy_score=0.90,
        anti_hallucination_passed=False,
        data_leakage_detected=False,
        passed=False,
    )

    state: AgentState = {
        "prompt": "Analyze market share",
        "tenant_id": "tenant-test",
        "user_id": "user-01",
        "tool_calls": [],
        "revision_count": 2,  # At max revisions
    }

    with patch("app.agents.verifier.evaluate_rag_case", return_value=fake_eval):
        result = await verifier_node(state)
        assert result["verification_verdict"] == "FAILED"
        assert result["workflow_phase"] == "verification_failed"
        assert "Groundedness below threshold" in result["critique_notes"]
        assert result["verification_verdict"] != "PASS"


@pytest.mark.asyncio
async def test_verifier_clean_pass() -> None:
    """Clean pass occurs strictly when tenant matches, math is consistent, and grounding passes."""
    fake_eval = RAGEvalResult(
        case_id="eval-pass",
        faithfulness_score=0.95,
        context_relevancy_score=0.90,
        anti_hallucination_passed=True,
        data_leakage_detected=False,
        passed=True,
    )

    state: AgentState = {
        "prompt": "Calculate margin",
        "tenant_id": "tenant-test",
        "user_id": "user-01",
        "financial_analysis": {
            "revenue": 1000.0,
            "operating_expenses": 400.0,
            "operating_income": 600.0,  # 1000 - 400 == 600
        },
        "tool_calls": [{"tool_name": "get_balance", "tenant_id": "tenant-test"}],
        "revision_count": 0,
    }

    with patch("app.agents.verifier.evaluate_rag_case", return_value=fake_eval):
        result = await verifier_node(state)
        assert result["verification_verdict"] == "PASS"
        assert result["workflow_phase"] == "verification_passed"
        assert result["next_agent"] == "synthesizer"
        assert result["mascot_state"] == "success"
