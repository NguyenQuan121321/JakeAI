"""Automated Hallucination & Fact Verification Evaluation Suite (TEST-06 / AI-014 / CAT-123).

Evaluates the 4 mandatory hallucination categories plus edge cases deterministically
without relying on brittle natural-language string equality or LLM-judge-only checks:
1. SUPPORTED: All propositions, canonical metrics, and relational assertions anchored in context.
2. UNSUPPORTED: Extraneous projections, unevidenced claims, and fabricated figures flagged.
3. CONTRADICTORY: Antonym polarities, conflicting metrics, and entity conflicts flagged.
4. INSUFFICIENT EVIDENCE: Missing facts trigger recognized epistemic abstention.
5. Multi-chunk compound metrics synthesis across disparate passages.
6. Entity divergence contradiction detection despite high lexical token overlap.
"""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any

import pytest

from app.evals.hallucination_evaluator import (
    HallucinationCategory,
    evaluate_hallucination_case,
)
from app.rag.grounding import (
    ANTONYM_PAIRS,
    normalize_metric,
)

FIXTURES_PATH = (
    Path(__file__).parent / "datasets" / "eval_hallucination_fixtures_v1.json"
)


def load_hallucination_fixtures() -> list[dict[str, Any]]:
    """Load versioned controlled hallucination regression dataset."""
    assert FIXTURES_PATH.exists(), f"Fixtures file missing at {FIXTURES_PATH}"
    with FIXTURES_PATH.open("r", encoding="utf-8") as f:
        return json.load(f)


# =========================================================================
# 1. Category: SUPPORTED Claims
# =========================================================================
def test_eval_hallucination_01_supported_claims() -> None:
    """Evaluate fully supported propositions with metrics (42.5M, 6.2%, 18.4%) pass with 1.0 groundedness."""
    case = {
        "case_id": "HALLUC-EVAL-001",
        "task": "supported_claims",
        "input": {
            "context": (
                "Global shipping volume reached 42.5 million TEU in 2025, representing an "
                "increase of 6.2% over the previous year. Operating margin was 18.4%."
            ),
            "candidate_answer": (
                "In 2025, global shipping volume was 42.5M TEU, reflecting a 6.2% increase "
                "with an operating margin of 18.4%."
            ),
        },
    }

    result = evaluate_hallucination_case(case)
    assert result.passed, f"Supported evaluation failed: {result.diagnostics}"
    assert result.detected_category == HallucinationCategory.SUPPORTED
    assert result.groundedness_ratio == 1.0
    assert len(result.contradicted_claims) == 0


# =========================================================================
# 2. Category: UNSUPPORTED Claims
# =========================================================================
def test_eval_hallucination_02_unsupported_extrapolations() -> None:
    """Evaluate unevidenced projections ($88.5B by 2030, 45 datacenters) are flagged as ungrounded."""
    case = {
        "case_id": "HALLUC-EVAL-002",
        "task": "unsupported_claims",
        "input": {
            "context": "Cloud infrastructure spend reached $14.2B in Q2 2026 across primary enterprise accounts.",
            "candidate_answer": (
                "Cloud infrastructure spend reached $14.2B in Q2 2026 across primary enterprise accounts, "
                "and the firm projects $88.5B total cloud revenue by 2030 with 45 new datacenter builds."
            ),
        },
    }

    result = evaluate_hallucination_case(case)
    assert result.passed, f"Unsupported evaluation failed: {result.diagnostics}"
    assert result.detected_category in [
        HallucinationCategory.UNSUPPORTED,
        HallucinationCategory.CONTRADICTORY,
    ]
    assert (
        any(
            "88" in d or "divergence" in d or "unsupported" in d.lower()
            for d in result.diagnostics
        )
        or len(result.unsupported_claims) > 0
        or len(result.contradicted_claims) > 0
    )


# =========================================================================
# 3. Category: CONTRADICTORY Claims
# =========================================================================
def test_eval_hallucination_03_contradictory_claims() -> None:
    """Evaluate antonym polarity ('lowered' vs 'raised') and metric conflict (4.25% vs 5.75%) detected."""
    case = {
        "case_id": "HALLUC-EVAL-003",
        "task": "contradictory_claims",
        "input": {
            "context": "The central bank lowered benchmark interest rates by 50 basis points to 4.25% in September.",
            "candidate_answer": "The central bank raised benchmark interest rates by 50 basis points to 5.75% in September.",
        },
    }

    result = evaluate_hallucination_case(case)
    assert result.passed, f"Contradiction evaluation failed: {result.diagnostics}"
    assert result.detected_category == HallucinationCategory.CONTRADICTORY
    assert len(result.contradicted_claims) > 0 or any(
        "antonym" in d.lower() or "divergence" in d.lower() for d in result.diagnostics
    )


# =========================================================================
# 4. Category: INSUFFICIENT EVIDENCE (Epistemic Abstention)
# =========================================================================
def test_eval_hallucination_04_insufficient_evidence_abstention() -> None:
    """Evaluate explicit epistemic abstention is recognized as grounded behavior and not penalized."""
    case = {
        "case_id": "HALLUC-EVAL-004",
        "task": "insufficient_evidence",
        "input": {
            "context": "The company operates in North America and Western Europe, offering cybersecurity audit software.",
            "candidate_answer": "I do not have sufficient evidence in the provided documents to determine the average customer acquisition cost or churn rate.",
        },
    }

    result = evaluate_hallucination_case(case)
    assert result.passed, (
        f"Epistemic abstention evaluation failed: {result.diagnostics}"
    )
    assert result.detected_category == HallucinationCategory.INSUFFICIENT_EVIDENCE
    assert result.epistemic_abstention_detected is True


# =========================================================================
# 5. Multi-Chunk Compound Metrics Synthesis
# =========================================================================
def test_eval_hallucination_05_multi_chunk_compound_metrics() -> None:
    """Evaluate compound metrics across distinct passages are validated ensemble without false conflict."""
    case = {
        "case_id": "HALLUC-EVAL-005",
        "task": "multi_chunk_compound_metrics",
        "input": {
            "passages": [
                "In FY2024, North America division delivered $100M revenue.",
                "In FY2025, North America division expanded to $130M revenue.",
            ],
            "candidate_answer": "North America revenue expanded from $100M in FY2024 to $130M in FY2025.",
        },
    }

    result = evaluate_hallucination_case(case)
    assert result.passed, f"Multi-chunk evaluation failed: {result.diagnostics}"
    assert result.detected_category == HallucinationCategory.SUPPORTED
    assert result.groundedness_ratio == 1.0


# =========================================================================
# 6. Entity Divergence Contradiction
# =========================================================================
def test_eval_hallucination_06_entity_divergence_contradiction() -> None:
    """Evaluate named entity collision ('Singapore' vs 'Berlin') flagged despite 80% lexical overlap."""
    case = {
        "case_id": "HALLUC-EVAL-006",
        "task": "entity_divergence_contradiction",
        "input": {
            "context": "The cybersecurity summit was hosted in Singapore with over 5,000 delegates.",
            "candidate_answer": "The cybersecurity summit was hosted in Berlin with over 5,000 delegates.",
        },
    }

    result = evaluate_hallucination_case(case)
    assert result.passed, f"Entity divergence evaluation failed: {result.diagnostics}"
    assert result.detected_category == HallucinationCategory.CONTRADICTORY
    assert any("entity" in d.lower() for d in result.diagnostics)


# =========================================================================
# 7. Deterministic Metric Normalization Assertions
# =========================================================================
def test_eval_hallucination_07_deterministic_metric_canonicalization() -> None:
    """Evaluate metric normalizer equates formatted variations deterministically."""
    # Test billion representations
    b1 = normalize_metric("$14.2B")
    b2 = normalize_metric("$14.2 billion")
    b3 = normalize_metric("$14,200,000,000")
    b4 = normalize_metric("14.2B USD")

    assert b1 is not None and b2 is not None and b3 is not None and b4 is not None
    assert b1[1] == 14200000000.0
    assert b2[1] == 14200000000.0
    assert b3[1] == 14200000000.0
    assert b4[1] == 14200000000.0

    # Test million representations
    m1 = normalize_metric("42.5 million")
    m2 = normalize_metric("42.5M")
    assert m1 is not None and m2 is not None
    assert m1[1] == 42500000.0
    assert m2[1] == 42500000.0

    # Test percentages
    p1 = normalize_metric("6.2%")
    p2 = normalize_metric("6.2 percent")
    assert p1 is not None and p2 is not None
    assert p1[1] == 6.2
    assert p2[1] == 6.2


# =========================================================================
# 8. Deterministic Antonym Polarity Matrix Assertions
# =========================================================================
def test_eval_hallucination_08_deterministic_antonym_polarity() -> None:
    """Evaluate known antonym pairs are recognized in the bidirectional polarity dictionary."""
    expected_pairs = [
        ("increase", "decrease"),
        ("approved", "rejected"),
        ("profit", "loss"),
        ("grew", "declined"),
        ("lowered", "raised"),
    ]

    for w1, w2 in expected_pairs:
        assert w2 in ANTONYM_PAIRS.get(w1, set()) or w1 in ANTONYM_PAIRS.get(
            w2, set()
        ), f"Missing antonym mapping between '{w1}' and '{w2}'"


# =========================================================================
# 9. Parameterized Versioned Controlled Dataset
# =========================================================================
@pytest.mark.parametrize(
    "fixture",
    load_hallucination_fixtures(),
    ids=lambda f: f"{f['case_id']}_{f['task']}",
)
def test_eval_hallucination_versioned_fixtures_pass(fixture: dict[str, Any]) -> None:
    """Execute evaluation assertions across all versioned hallucination fixtures."""
    result = evaluate_hallucination_case(fixture)
    assert result.passed, (
        f"Fixture {fixture['case_id']} failed evaluation: "
        f"expected {result.expected_category}, detected {result.detected_category}. "
        f"Diagnostics: {result.diagnostics}"
    )
