"""Dedicated RAG Regression Testing Gate (Block 5).

Asserts strict enterprise quality thresholds:
  - Faithfulness Score >= 0.80
  - Context Relevancy Score >= 0.70
  - Anti-Hallucination: 100% numerical fact verification
  - Zero Data/Prompt Leakage
"""

import json
from pathlib import Path
from typing import Any

import pytest

from app.evals.rag_evaluator import evaluate_rag_case

DATASET_PATH = Path(__file__).parent / "golden_dataset.json"


def load_golden_cases() -> list[dict[str, Any]]:
    """Load evaluation test fixtures from golden dataset."""
    with open(DATASET_PATH, encoding="utf-8") as f:
        cases: list[dict[str, Any]] = json.load(f)
        return cases


@pytest.mark.parametrize(
    "case",
    load_golden_cases(),
    ids=lambda c: str(c.get("case_id")),
)
def test_rag_quality_gate(case: dict[str, Any]) -> None:
    """Run RAG evaluation gate against golden test cases."""
    case_id = case["case_id"]
    expected_pass = case.get("expected_pass", True)

    result = evaluate_rag_case(case)

    if expected_pass:
        assert result.passed, (
            f"Quality Gate failed for case '{case_id}': {result.model_dump()}"
        )
        assert result.faithfulness_score >= 0.80, (
            f"Faithfulness below threshold (0.80): {result.faithfulness_score}"
        )
        assert result.context_relevancy_score >= 0.70, (
            f"Relevancy below threshold (0.70): {result.context_relevancy_score}"
        )
        assert result.anti_hallucination_passed, (
            f"Numerical hallucination detected in case '{case_id}'"
        )
        assert not result.data_leakage_detected, (
            f"Data leakage detected in case '{case_id}'"
        )
    else:
        assert not result.passed, (
            f"Adversarial case '{case_id}' was expected to fail but passed quality gate"
        )
        assert not result.anti_hallucination_passed or result.data_leakage_detected, (
            f"Case '{case_id}' should have triggered hallucination or data leakage flag"
        )
