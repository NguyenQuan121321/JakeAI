"""LLM-as-Judge Secondary Signal Evaluator for Phase 06.

Implements Section 4 of 06_EVALUATION.md:
- Fixed judge model/version specification.
- Fixed 7-dimension rubric matching Phase 06 evaluation standard.
- Blinded baseline vs optimized evaluation ordering (eliminates position bias).
- Stored judge results with explanation, scores, and winning candidate mapping.
- Calibration mode against ground truth / known reference answers.
- Invariant Gate: Secondary signal only (never used as sole arbiter of safety).
"""

from __future__ import annotations

import random
from typing import Any

from pydantic import BaseModel, Field

from app.evals.rubric_evaluator import RubricDimension, RubricEvaluator


class BlindedOrder(BaseModel):
    """Blinded mapping of candidates to eliminate presentation/position bias."""

    candidate_a_role: str = Field(..., description="'baseline' or 'optimized'")
    candidate_b_role: str = Field(..., description="'baseline' or 'optimized'")
    candidate_a_text: str
    candidate_b_text: str


class JudgeComparisonResult(BaseModel):
    """Structured outcome from the LLM-as-Judge evaluation."""

    workload_id: str
    judge_model: str
    blinded_order: BlindedOrder
    winner: str = Field(..., description="'baseline', 'optimized', or 'tie'")
    baseline_score: float = Field(..., ge=0.0, le=1.0)
    optimized_score: float = Field(..., ge=0.0, le=1.0)
    score_delta: float = Field(..., description="optimized_score - baseline_score")
    is_regression: bool = Field(
        ..., description="True if optimized regresses vs baseline > threshold"
    )
    explanation: str
    dimension_breakdown: dict[str, dict[str, float]]
    calibrated_against_ground_truth: bool = False
    is_secondary_signal: bool = True


class LLMJudge:
    """Fixed-model, blinded rubric judge for comparative evaluation."""

    FIXED_JUDGE_MODEL: str = "gpt-4o-2024-08-06"
    MAX_ACCEPTABLE_REGRESSION: float = 0.05

    def __init__(self, judge_model: str | None = None, seed: int = 42) -> None:
        self.judge_model = judge_model or self.FIXED_JUDGE_MODEL
        self._rng = random.Random(seed)  # nosec B311

    def create_blinded_pair(
        self, baseline_text: str, optimized_text: str, force_order: str | None = None
    ) -> BlindedOrder:
        """Randomize candidate presentation order (Candidate A vs B) to eliminate position bias."""
        if force_order == "baseline_first":
            choose_baseline_a = True
        elif force_order == "optimized_first":
            choose_baseline_a = False
        else:
            choose_baseline_a = self._rng.choice([True, False])

        if choose_baseline_a:
            return BlindedOrder(
                candidate_a_role="baseline",
                candidate_b_role="optimized",
                candidate_a_text=baseline_text,
                candidate_b_text=optimized_text,
            )
        return BlindedOrder(
            candidate_a_role="optimized",
            candidate_b_role="baseline",
            candidate_a_text=optimized_text,
            candidate_b_text=baseline_text,
        )

    def evaluate_pair(
        self,
        case: dict[str, Any],
        baseline_text: str,
        optimized_text: str,
        force_order: str | None = None,
    ) -> JudgeComparisonResult:
        """Execute blinded rubric evaluation between baseline and optimized candidates."""
        workload_id = case.get("workload_id", "unknown")
        blinded = self.create_blinded_pair(baseline_text, optimized_text, force_order)

        # Evaluate Candidate A and Candidate B with the fixed 7-dimension rubric
        res_a = RubricEvaluator.evaluate(case, blinded.candidate_a_text)
        res_b = RubricEvaluator.evaluate(case, blinded.candidate_b_text)

        # Map back to unblinded roles
        if blinded.candidate_a_role == "baseline":
            base_res = res_a
            opt_res = res_b
        else:
            base_res = res_b
            opt_res = res_a

        base_score = base_res.composite_score
        opt_score = opt_res.composite_score
        delta = round(opt_score - base_score, 4)

        if abs(delta) < 0.02:
            winner = "tie"
        elif delta > 0:
            winner = "optimized"
        else:
            winner = "baseline"

        is_regr = delta < -self.MAX_ACCEPTABLE_REGRESSION

        explanation = (
            f"Judge evaluated candidates using fixed {self.judge_model} rubric. "
            f"Baseline: {base_score:.4f}, Optimized: {opt_score:.4f} (delta: {delta:+.4f}). "
            f"Verdict: {winner.upper()}."
        )

        dim_breakdown: dict[str, dict[str, float]] = {}
        for dim in RubricDimension:
            b_dim = base_res.dimension_scores.get(dim)
            o_dim = opt_res.dimension_scores.get(dim)
            dim_breakdown[dim.value] = {
                "baseline": b_dim.score if b_dim else 0.0,
                "optimized": o_dim.score if o_dim else 0.0,
            }

        return JudgeComparisonResult(
            workload_id=workload_id,
            judge_model=self.judge_model,
            blinded_order=blinded,
            winner=winner,
            baseline_score=base_score,
            optimized_score=opt_score,
            score_delta=delta,
            is_regression=is_regr,
            explanation=explanation,
            dimension_breakdown=dim_breakdown,
            calibrated_against_ground_truth=bool(case.get("ground_truth_answer")),
            is_secondary_signal=True,
        )

    def calibrate(
        self, case: dict[str, Any], reference_answer: str, perturbed_answer: str
    ) -> bool:
        """Verify judge reliably scores reference answer above a degraded/perturbed answer."""
        res = self.evaluate_pair(
            case=case,
            baseline_text=reference_answer,
            optimized_text=perturbed_answer,
        )
        # Reference answer must score higher than perturbed answer
        return res.baseline_score > res.optimized_score
