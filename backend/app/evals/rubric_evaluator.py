"""Rubric Evaluation Engine for Phase 06 AI Quality Evaluation.

Implements Section 3 of 06_EVALUATION.md:
Evaluates difficult natural-language cases across 7 explicit dimensions:
1. Correctness: Factual and numerical accuracy against reference truth.
2. Completeness: Coverage of all query requirements and facets.
3. Groundedness: Attribution and evidence support within supplied context.
4. Instruction Following: Adherence to role directives, language, and output constraints.
5. Reasoning Sufficiency: Logical steps, mathematical clarity, and deductive justification.
6. Citation Quality: Presence, precision, and verifiability of source anchors.
7. Format Correctness: Markdown syntax, code fences, JSON schemas, and structural hygiene.
"""

from __future__ import annotations

import json
import re
from enum import StrEnum
from typing import Any

from pydantic import BaseModel, Field


class RubricDimension(StrEnum):
    """The seven standard evaluation dimensions defined in Phase 06."""

    CORRECTNESS = "correctness"
    COMPLETENESS = "completeness"
    GROUNDEDNESS = "groundedness"
    INSTRUCTION_FOLLOWING = "instruction_following"
    REASONING_SUFFICIENCY = "reasoning_sufficiency"
    CITATION_QUALITY = "citation_quality"
    FORMAT_CORRECTNESS = "format_correctness"


class DimensionScore(BaseModel):
    """Score and diagnostic justification for an individual rubric dimension."""

    dimension: RubricDimension
    score: float = Field(
        ..., ge=0.0, le=1.0, description="Normalized score (0.0 to 1.0)"
    )
    weight: float = Field(
        default=1.0, ge=0.0, description="Relative weight in composite score"
    )
    passed: bool = Field(default=True, description="True if score meets threshold")
    justification: str = Field(default="", description="Detailed rationale for score")
    details: dict[str, Any] = Field(
        default_factory=dict, description="Diagnostic metrics"
    )


class RubricEvaluationResult(BaseModel):
    """Composite outcome of a multi-dimensional rubric evaluation."""

    workload_id: str
    composite_score: float = Field(..., ge=0.0, le=1.0)
    passed: bool = Field(default=True)
    dimension_scores: dict[RubricDimension, DimensionScore] = Field(
        default_factory=dict
    )
    critical_failures: list[str] = Field(default_factory=list)
    recommendations: list[str] = Field(default_factory=list)


class RubricEvaluator:
    """Deterministic and heuristic evaluator implementing the 7 Phase 06 rubric dimensions."""

    DEFAULT_PASS_THRESHOLD = 0.80

    @classmethod
    def evaluate_correctness(
        cls, candidate: str, expected_facts: list[str], ground_truth: str = ""
    ) -> DimensionScore:
        """Dimension 1: Check factual and numerical correctness."""
        if not expected_facts and not ground_truth:
            return DimensionScore(
                dimension=RubricDimension.CORRECTNESS,
                score=1.0,
                passed=True,
                justification="No explicit facts or ground truth specified for case.",
            )

        text_lower = candidate.lower()
        missing = [f for f in expected_facts if f.strip().lower() not in text_lower]

        if expected_facts:
            score = (len(expected_facts) - len(missing)) / len(expected_facts)
        else:
            # Token overlap with ground truth
            gt_tokens = set(re.findall(r"\b\w{3,}\b", ground_truth.lower()))
            cand_tokens = set(re.findall(r"\b\w{3,}\b", text_lower))
            overlap = len(gt_tokens.intersection(cand_tokens)) / max(1, len(gt_tokens))
            score = overlap

        score = round(max(0.0, min(1.0, score)), 4)
        passed = score >= cls.DEFAULT_PASS_THRESHOLD and len(missing) == 0
        justification = (
            "All expected facts verified."
            if not missing
            else f"Missing critical facts: {missing}"
        )

        return DimensionScore(
            dimension=RubricDimension.CORRECTNESS,
            score=score,
            weight=1.5,
            passed=passed,
            justification=justification,
            details={"missing_facts": missing},
        )

    @classmethod
    def evaluate_completeness(
        cls, candidate: str, query: str, ground_truth: str = ""
    ) -> DimensionScore:
        """Dimension 2: Check query coverage and answering all requested facets."""
        _ = ground_truth
        if not candidate.strip():
            return DimensionScore(
                dimension=RubricDimension.COMPLETENESS,
                score=0.0,
                passed=False,
                justification="Candidate response is empty.",
            )

        # Extract question keywords (e.g. 'and', 'what', 'calculate', commas)
        query_clauses = [
            c.strip()
            for c in re.split(r"\band\b|,|\?", query, flags=re.IGNORECASE)
            if len(c.strip()) > 5
        ]
        if not query_clauses:
            return DimensionScore(
                dimension=RubricDimension.COMPLETENESS,
                score=1.0,
                passed=True,
                justification="Single-intent query completely addressed.",
            )

        addressed = 0
        cand_lower = candidate.lower()
        for clause in query_clauses:
            clause_tokens = [
                w
                for w in re.findall(r"\b\w{4,}\b", clause.lower())
                if w
                not in ("what", "which", "state", "given", "calculate", "summarize")
            ]
            if not clause_tokens:
                addressed += 1
                continue
            matches = sum(1 for t in clause_tokens if t in cand_lower)
            if matches / len(clause_tokens) >= 0.5:
                addressed += 1

        score = round(addressed / len(query_clauses), 4)
        passed = score >= 0.70
        return DimensionScore(
            dimension=RubricDimension.COMPLETENESS,
            score=score,
            weight=1.0,
            passed=passed,
            justification=f"Addressed {addressed}/{len(query_clauses)} query facets.",
            details={"total_clauses": len(query_clauses), "addressed": addressed},
        )

    @classmethod
    def evaluate_groundedness(
        cls,
        candidate: str,
        context: str,
        ground_truth: str = "",
        allowed_facts: list[str] | None = None,
    ) -> DimensionScore:
        """Dimension 3: Verify statements and numerical figures are grounded in context."""
        ref_text = (
            context + " " + ground_truth + " " + " ".join(allowed_facts or [])
        ).strip()
        if not ref_text:
            return DimensionScore(
                dimension=RubricDimension.GROUNDEDNESS,
                score=1.0,
                passed=True,
                justification="No external context required for prompt.",
            )

        # Numerical tokens in response must appear in context/ground-truth
        num_pattern = r"\$?\b\d+(?:[\.,]\d+)?(?:%|[MBkK])?"
        cand_numbers = set(re.findall(num_pattern, candidate))
        ctx_numbers = set(re.findall(num_pattern, ref_text))

        unsupported_nums = cand_numbers - ctx_numbers
        # Extract content words
        cand_words = set(re.findall(r"\b[a-zA-Z0-9_\-]{4,}\b", candidate.lower()))
        ctx_words = set(re.findall(r"\b[a-zA-Z0-9_\-]{4,}\b", ref_text.lower()))

        word_overlap = len(cand_words.intersection(ctx_words)) / max(1, len(cand_words))
        num_groundedness = (
            1.0
            if not unsupported_nums
            else max(0.0, 1.0 - (len(unsupported_nums) * 0.3))
        )

        score = round(
            min(1.0, max(0.0, (word_overlap * 0.4) + (num_groundedness * 0.6))), 4
        )
        passed = len(unsupported_nums) == 0 and score >= 0.75
        justification = (
            "All figures and assertions grounded in context."
            if passed
            else f"Ungrounded figures detected: {list(unsupported_nums)}"
        )

        return DimensionScore(
            dimension=RubricDimension.GROUNDEDNESS,
            score=score,
            weight=1.5,
            passed=passed,
            justification=justification,
            details={
                "unsupported_numbers": list(unsupported_nums),
                "word_overlap": round(word_overlap, 4),
            },
        )

    @classmethod
    def evaluate_instruction_following(
        cls, candidate: str, system_instruction: str, query: str
    ) -> DimensionScore:
        """Dimension 4: Adherence to format constraints, language, role, and negative commands."""
        checks_passed = 0
        total_checks = 0

        # Check 1: Non-empty response
        total_checks += 1
        if candidate.strip():
            checks_passed += 1

        # Check 2: Language constraint (e.g. Vietnamese)
        sys_and_query = (system_instruction + " " + query).lower()
        if any(
            vn in sys_and_query
            for vn in ("tiếng việt", "vietnamese", "bạn là chuyên gia")
        ):
            total_checks += 1
            # Check for Vietnamese diacritic characters
            has_vn = bool(
                re.search(
                    r"[àáạảãâầấậẩẫăằắặẳẵèéẹẻẽêềếệểễìíịỉĩòóọỏõôồốộổỗơờớợởỡùúụủũưừứựửữỳýỵỷỹđ]",
                    candidate,
                    re.IGNORECASE,
                )
            )
            if has_vn:
                checks_passed += 1

        # Check 3: Output constraint (e.g. "JSON only")
        if "json only" in sys_and_query or "valid json only" in sys_and_query:
            total_checks += 1
            try:
                clean_cand = candidate.strip()
                if clean_cand.startswith("```json"):
                    clean_cand = clean_cand[7:].strip()
                    if clean_cand.endswith("```"):
                        clean_cand = clean_cand[:-3].strip()
                json.loads(clean_cand)
                checks_passed += 1
            except (json.JSONDecodeError, ValueError, TypeError):
                # Invalid JSON syntax does not satisfy JSON-only constraint
                checks_passed += 0

        # Check 4: Brevity/conciseness constraint
        if "concise" in sys_and_query or "briefly" in sys_and_query:
            total_checks += 1
            if len(candidate.split()) <= 300:
                checks_passed += 1

        score = round(checks_passed / max(1, total_checks), 4)
        passed = score >= 0.80
        return DimensionScore(
            dimension=RubricDimension.INSTRUCTION_FOLLOWING,
            score=score,
            weight=1.0,
            passed=passed,
            justification=f"Satisfied {checks_passed}/{total_checks} instruction directives.",
        )

    @classmethod
    def evaluate_reasoning_sufficiency(
        cls, candidate: str, query: str
    ) -> DimensionScore:
        """Dimension 5: Logical progression and mathematical formula steps."""
        is_reasoning_query = any(
            k in query.lower()
            for k in (
                "calculate",
                "compute",
                "why",
                "how",
                "ebitda",
                "margin",
                "discount",
                "reason",
            )
        )
        if not is_reasoning_query:
            return DimensionScore(
                dimension=RubricDimension.REASONING_SUFFICIENCY,
                score=1.0,
                passed=True,
                justification="Fact retrieval query; detailed reasoning steps not mandatory.",
            )

        cand_lower = candidate.lower()
        has_math_or_logic = bool(
            re.search(r"[\+\-\*\/=]", candidate)
            or any(
                w in cand_lower
                for w in (
                    "because",
                    "therefore",
                    "equals",
                    "yielding",
                    "steps",
                    "formula",
                    "since",
                    "tính",
                )
            )
        )

        score = 1.0 if has_math_or_logic else 0.5
        passed = score >= 0.75
        justification = (
            "Deductive steps and calculation flow explicitly shown."
            if passed
            else "Reasoning query lacks clear intermediate logical/arithmetic steps."
        )

        return DimensionScore(
            dimension=RubricDimension.REASONING_SUFFICIENCY,
            score=score,
            weight=1.0,
            passed=passed,
            justification=justification,
        )

    @classmethod
    def evaluate_citation_quality(
        cls, candidate: str, expected_citations: list[str]
    ) -> DimensionScore:
        """Dimension 6: Verify citations to source records."""
        if not expected_citations:
            return DimensionScore(
                dimension=RubricDimension.CITATION_QUALITY,
                score=1.0,
                passed=True,
                justification="No citations required for query.",
            )

        missing = [cite for cite in expected_citations if cite not in candidate]
        score = (len(expected_citations) - len(missing)) / len(expected_citations)
        score = round(max(0.0, min(1.0, score)), 4)
        passed = len(missing) == 0

        return DimensionScore(
            dimension=RubricDimension.CITATION_QUALITY,
            score=score,
            weight=1.2,
            passed=passed,
            justification="All expected citations verified."
            if passed
            else f"Missing citations: {missing}",
            details={"missing_citations": missing},
        )

    @classmethod
    def evaluate_format_correctness(
        cls, candidate: str, expected_json_keys: list[str] | None = None
    ) -> DimensionScore:
        """Dimension 7: Markdown formatting, code syntax, and schema correctness."""
        errors = []
        if candidate.count("```") % 2 != 0:
            errors.append("Unclosed markdown code fence")

        if expected_json_keys:
            try:
                clean_cand = candidate.strip()
                if "```json" in clean_cand:
                    match = re.search(r"```json\s*([\s\S]*?)\s*```", clean_cand)
                    if match:
                        clean_cand = match.group(1)
                elif "{" in clean_cand:
                    match = re.search(r"\{[\s\S]*\}", clean_cand)
                    if match:
                        clean_cand = match.group(0)
                data = json.loads(clean_cand)
                dict_str = json.dumps(data).lower()
                missing_keys = [
                    k for k in expected_json_keys if k.lower() not in dict_str
                ]
                if missing_keys:
                    errors.append(f"Missing JSON schema keys: {missing_keys}")
            except Exception as exc:
                errors.append(f"JSON syntax invalid: {exc}")

        score = 1.0 if not errors else 0.5 if len(errors) == 1 else 0.0
        passed = len(errors) == 0
        return DimensionScore(
            dimension=RubricDimension.FORMAT_CORRECTNESS,
            score=score,
            weight=1.0,
            passed=passed,
            justification="Formatting and syntax valid."
            if passed
            else f"Format errors: {errors}",
            details={"format_errors": errors},
        )

    @classmethod
    def evaluate(
        cls,
        case: dict[str, Any],
        candidate: str,
        quality_floor: float = 0.80,
    ) -> RubricEvaluationResult:
        """Evaluate candidate text across all 7 Phase 06 rubric dimensions."""
        workload_id = case.get("workload_id", "unknown")
        query = case.get("user_query", "")
        system_instruction = case.get("system_instruction", "")
        dynamic_context = case.get("dynamic_context", "")
        ground_truth = case.get("ground_truth_answer", "")
        expected_facts = case.get("expected_facts", [])
        expected_citations = case.get("expected_citations", [])
        expected_json_keys = case.get("expected_json_keys", [])

        dim_scores: dict[RubricDimension, DimensionScore] = {
            RubricDimension.CORRECTNESS: cls.evaluate_correctness(
                candidate, expected_facts, ground_truth
            ),
            RubricDimension.COMPLETENESS: cls.evaluate_completeness(
                candidate, query, ground_truth
            ),
            RubricDimension.GROUNDEDNESS: cls.evaluate_groundedness(
                candidate,
                dynamic_context,
                ground_truth=ground_truth,
                allowed_facts=expected_facts,
            ),
            RubricDimension.INSTRUCTION_FOLLOWING: cls.evaluate_instruction_following(
                candidate, system_instruction, query
            ),
            RubricDimension.REASONING_SUFFICIENCY: cls.evaluate_reasoning_sufficiency(
                candidate, query
            ),
            RubricDimension.CITATION_QUALITY: cls.evaluate_citation_quality(
                candidate, expected_citations
            ),
            RubricDimension.FORMAT_CORRECTNESS: cls.evaluate_format_correctness(
                candidate, expected_json_keys
            ),
        }

        # Weighted composite score
        total_weight = sum(ds.weight for ds in dim_scores.values())
        composite = (
            sum(ds.score * ds.weight for ds in dim_scores.values()) / total_weight
        )
        composite = round(max(0.0, min(1.0, composite)), 4)

        critical_failures = [
            f"{ds.dimension.value}: {ds.justification}"
            for ds in dim_scores.values()
            if not ds.passed
            and ds.dimension
            in (
                RubricDimension.CORRECTNESS,
                RubricDimension.GROUNDEDNESS,
                RubricDimension.CITATION_QUALITY,
            )
        ]

        overall_passed = composite >= quality_floor and len(critical_failures) == 0

        recommendations = []
        for ds in dim_scores.values():
            if ds.score < 0.80:
                recommendations.append(
                    f"Improve {ds.dimension.value}: {ds.justification}"
                )

        return RubricEvaluationResult(
            workload_id=workload_id,
            composite_score=composite,
            passed=overall_passed,
            dimension_scores=dim_scores,
            critical_failures=critical_failures,
            recommendations=recommendations,
        )
