"""AI RAG Regression and Evaluation Test Suite using Golden Dataset Stub."""

import json
from pathlib import Path
from typing import Any

import pytest

from app.evals.rag_evaluator import evaluate_rag_case

DATASET_PATH = Path(__file__).parent / "golden_dataset.json"


def load_golden_dataset() -> list[dict[str, Any]]:
    """Load the golden dataset test fixtures."""
    with open(DATASET_PATH, encoding="utf-8") as f:
        data: list[dict[str, Any]] = json.load(f)
        return data


@pytest.mark.parametrize(
    "case",
    load_golden_dataset(),
    ids=lambda c: str(c.get("case_id")),
)
def test_rag_golden_dataset_evaluation(case: dict[str, Any]) -> None:
    """Evaluate RAG quality, faithfulness, anti-hallucination, and leakage."""
    case_id = case["case_id"]
    expected_pass = case.get("expected_pass", True)

    result = evaluate_rag_case(case)

    if expected_pass:
        assert (
            result.passed
        ), f"Case {case_id} failed quality gates: {result.model_dump()}"
        assert (
            result.faithfulness_score >= 0.80
        ), f"Case {case_id} faithfulness below 0.80: {result.faithfulness_score}"
        assert (
            result.context_relevancy_score >= 0.70
        ), f"Case {case_id} relevancy below 0.70: {result.context_relevancy_score}"
        assert (
            result.anti_hallucination_passed
        ), f"Case {case_id} failed anti-hallucination test"
        assert (
            not result.data_leakage_detected
        ), f"Case {case_id} detected data or prompt leakage"
    else:
        # Negative test cases must be properly flagged by the evaluator
        assert (
            not result.passed
        ), f"Negative case {case_id} was expected to fail, but passed"
        assert (
            not result.anti_hallucination_passed or result.data_leakage_detected
        ), f"Negative case {case_id} did not trigger hallucination or leakage flags"
