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
    evaluation_method: str = Field(
        default="heuristic_rubric",
        description="'llm_judge' when executed via actual LLM, 'heuristic_rubric' when evaluated via deterministic heuristics",
    )
    judge_version: str = Field(default="1.0.0")


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
            evaluation_method="heuristic_rubric",
            judge_version="1.0.0",
        )

    async def async_evaluate_pair_with_llm(
        self,
        case: dict[str, Any],
        baseline_text: str,
        optimized_text: str,
        force_order: str | None = None,
        tenant_id: str = "default",
    ) -> JudgeComparisonResult:
        """Execute real LLM-as-Judge evaluation via upstream model provider (TASK OPS-09).

        Prompts the judge model with an explicit 7-dimension evaluation schema.
        Falls back cleanly to heuristic rubric evaluation with explicit labeling
        if the upstream model is unreachable or unconfigured.
        """
        import json

        from app.core.llm_provider import call_upstream_llm_detailed

        workload_id = case.get("workload_id", "unknown")
        user_query = case.get("user_query", "")
        ground_truth = case.get("ground_truth_answer", "")
        blinded = self.create_blinded_pair(baseline_text, optimized_text, force_order)

        prompt = f"""You are an expert impartial AI quality judge evaluating two candidate responses to an enterprise user query.
Assess Candidate A and Candidate B across these 7 dimensions (score 1 to 5, where 1 is poor and 5 is excellent):
1. correctness: Factual, mathematical, and numerical precision.
2. completeness: Thoroughness addressing all parts of the user query.
3. groundedness: True to provided reference context without ungrounded hallucinations.
4. instruction_following: Strict adherence to formatting, tone, constraints, and instructions.
5. reasoning_sufficiency: Logical clarity and step-by-step justification.
6. citation_quality: Proper attribution and source reference precision.
7. format_correctness: Clean markdown syntax, valid code blocks, and structured hygiene.

User Query:
{user_query}

Reference Ground Truth (if any):
{ground_truth or "N/A"}

Candidate A:
{blinded.candidate_a_text}

Candidate B:
{blinded.candidate_b_text}

Respond strictly in valid JSON with this exact schema:
{{
  "candidate_a_scores": {{
    "correctness": 5, "completeness": 5, "groundedness": 5, "instruction_following": 5,
    "reasoning_sufficiency": 5, "citation_quality": 5, "format_correctness": 5
  }},
  "candidate_b_scores": {{
    "correctness": 5, "completeness": 5, "groundedness": 5, "instruction_following": 5,
    "reasoning_sufficiency": 5, "citation_quality": 5, "format_correctness": 5
  }},
  "winner": "candidate_a" | "candidate_b" | "tie",
  "explanation": "Brief rationale for the verdict."
}}
"""
        try:
            resp = await call_upstream_llm_detailed(
                prompt=prompt,
                tenant_id=tenant_id,
                model=self.judge_model,
                temperature=0.0,
                max_tokens=1024,
            )
            if not resp or not resp.text:
                raise ValueError("Empty response from judge model")

            cleaned_text = resp.text.strip()
            if "```json" in cleaned_text:
                cleaned_text = (
                    cleaned_text.split("```json", 1)[1].split("```", 1)[0].strip()
                )
            elif "```" in cleaned_text:
                cleaned_text = (
                    cleaned_text.split("```", 1)[1].split("```", 1)[0].strip()
                )

            parsed = json.loads(cleaned_text)
            a_scores: dict[str, float] = {
                k: float(v) / 5.0 for k, v in parsed["candidate_a_scores"].items()
            }
            b_scores: dict[str, float] = {
                k: float(v) / 5.0 for k, v in parsed["candidate_b_scores"].items()
            }

            avg_a = sum(a_scores.values()) / max(1, len(a_scores))
            avg_b = sum(b_scores.values()) / max(1, len(b_scores))

            if blinded.candidate_a_role == "baseline":
                base_score = avg_a
                opt_score = avg_b
                dim_breakdown = {
                    k: {
                        "baseline": a_scores.get(k, 0.0),
                        "optimized": b_scores.get(k, 0.0),
                    }
                    for k in a_scores
                }
            else:
                base_score = avg_b
                opt_score = avg_a
                dim_breakdown = {
                    k: {
                        "baseline": b_scores.get(k, 0.0),
                        "optimized": a_scores.get(k, 0.0),
                    }
                    for k in b_scores
                }

            delta = round(opt_score - base_score, 4)
            if abs(delta) < 0.02:
                winner = "tie"
            elif delta > 0:
                winner = "optimized"
            else:
                winner = "baseline"

            return JudgeComparisonResult(
                workload_id=workload_id,
                judge_model=self.judge_model,
                blinded_order=blinded,
                winner=winner,
                baseline_score=round(base_score, 4),
                optimized_score=round(opt_score, 4),
                score_delta=delta,
                is_regression=delta < -self.MAX_ACCEPTABLE_REGRESSION,
                explanation=str(
                    parsed.get("explanation", "LLM Judge evaluation completed.")
                ),
                dimension_breakdown=dim_breakdown,
                calibrated_against_ground_truth=bool(ground_truth),
                is_secondary_signal=True,
                evaluation_method="llm_judge",
                judge_version="1.0.0",
            )
        except Exception:
            fallback_res = self.evaluate_pair(
                case, baseline_text, optimized_text, force_order
            )
            fallback_res.evaluation_method = "heuristic_rubric"
            return fallback_res

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
