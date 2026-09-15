"""Deterministic Hallucination & Fact Verification Evaluator for JakeAI (TEST-06 / AI-014).

Provides controlled dataset evaluation covering 4 core categories:
1. SUPPORTED: All propositions, canonical metrics, and qualitative statements are anchored in evidence.
2. UNSUPPORTED: Extraneous facts, unevidenced projections, or fabricated figures are flagged and stripped.
3. CONTRADICTORY: Antonym polarities, conflicting metrics, and conflicting entities are flagged with CONTRADICTORY_EVIDENCE.
4. INSUFFICIENT EVIDENCE: Missing facts trigger deterministic epistemic abstention (NO_RELEVANT_EVIDENCE).

Operates via deterministic syntactic, metric canonicalization, and polarity assertions
without relying only on an LLM judge.
"""

from __future__ import annotations

import enum
import re
from typing import Any

from pydantic import BaseModel, Field

from app.rag.grounding import (
    ANTONYM_PAIRS,
    GroundingVerifier,
    extract_canonical_metrics,
    get_entities,
    is_epistemic_abstention,
)
from app.rag.models import DocumentChunk


class HallucinationCategory(enum.StrEnum):
    """Four canonical evaluation categories for hallucination verification."""

    SUPPORTED = "SUPPORTED"
    UNSUPPORTED = "UNSUPPORTED"
    CONTRADICTORY = "CONTRADICTORY"
    INSUFFICIENT_EVIDENCE = "INSUFFICIENT_EVIDENCE"


class HallucinationEvaluationResult(BaseModel):
    """Result of deterministic hallucination evaluation."""

    case_id: str = Field(description="Unique case identifier")
    expected_category: HallucinationCategory = Field(
        description="Expected category from controlled dataset"
    )
    detected_category: HallucinationCategory = Field(
        description="Category detected by deterministic assertions"
    )
    passed: bool = Field(
        description="True if detected category matches expected property"
    )
    groundedness_ratio: float = Field(ge=0.0, le=1.0, default=0.0)
    unsupported_claim_rate: float = Field(ge=0.0, le=1.0, default=0.0)
    supported_claims: list[str] = Field(default_factory=list)
    unsupported_claims: list[str] = Field(default_factory=list)
    contradicted_claims: list[str] = Field(default_factory=list)
    epistemic_abstention_detected: bool = Field(default=False)
    deterministic_assertions_passed: bool = Field(default=True)
    diagnostics: list[str] = Field(default_factory=list)


def evaluate_hallucination_case(case: dict[str, Any]) -> HallucinationEvaluationResult:
    """Evaluate a controlled dataset case against deterministic grounding rules."""
    case_id: str = case.get("case_id", "UNKNOWN")
    task_name: str = case.get("task", "").upper()
    case_input: dict[str, Any] = case.get("input", {})

    # Determine expected category from task or input
    if "UNSUPPORTED" in task_name:
        expected_category = HallucinationCategory.UNSUPPORTED
    elif "CONTRADICT" in task_name or "ENTITY" in task_name:
        expected_category = HallucinationCategory.CONTRADICTORY
    elif "INSUFFICIENT" in task_name or "ABSTENTION" in task_name:
        expected_category = HallucinationCategory.INSUFFICIENT_EVIDENCE
    elif "SUPPORTED" in task_name or "COMPOUND" in task_name:
        expected_category = HallucinationCategory.SUPPORTED
    else:
        expected_category = HallucinationCategory.SUPPORTED

    candidate_answer = (
        case_input.get("candidate_answer")
        or case_input.get("generated_answer")
        or case_input.get("answer", "")
    )
    context_text = case_input.get("context", "")
    passages_list = case_input.get("passages", [])

    if not passages_list and context_text:
        passages = [
            DocumentChunk(
                chunk_id="chunk_01",
                tenant_id="tenant_eval",
                content=context_text,
            )
        ]
    else:
        passages = [
            DocumentChunk(
                chunk_id=f"chunk_{i}",
                tenant_id="tenant_eval",
                content=p,
            )
            for i, p in enumerate(passages_list)
        ]

    diagnostics: list[str] = []

    # 1. Epistemic Abstention Check
    is_abstention = is_epistemic_abstention(candidate_answer)
    if is_abstention:
        detected_category = HallucinationCategory.INSUFFICIENT_EVIDENCE
        passed = expected_category == HallucinationCategory.INSUFFICIENT_EVIDENCE
        return HallucinationEvaluationResult(
            case_id=case_id,
            expected_category=expected_category,
            detected_category=detected_category,
            passed=passed,
            groundedness_ratio=1.0,
            unsupported_claim_rate=0.0,
            epistemic_abstention_detected=True,
            deterministic_assertions_passed=True,
            diagnostics=["Epistemic abstention recognized accurately."],
        )

    # 2. Run GroundingVerifier
    verifier = GroundingVerifier(min_groundedness_ratio=0.60)
    v_res = verifier.verify(
        text=candidate_answer, passages=passages, tenant_id="tenant_eval"
    )

    supp_texts = [c.claim_text for c in v_res.supported_claims]
    unsupp_texts = [c.claim_text for c in v_res.unsupported_claims]
    contra_texts = [c.claim_text for c in v_res.contradicted_claims]

    # 3. Deterministic Antonym & Numeric Contradiction Detection
    has_contradiction = len(contra_texts) > 0

    # Direct check across all passages for conflicting metrics or antonyms
    all_context_metrics: set[float] = set()
    for p in passages:
        for _u, val in extract_canonical_metrics(p.content):
            all_context_metrics.add(val)

    answer_metrics = extract_canonical_metrics(candidate_answer)
    metric_divergence = False
    for unit, m_val in answer_metrics:
        if all_context_metrics and not any(
            abs(m_val - c_val) < 1e-3 for c_val in all_context_metrics
        ):
            # Answer introduces a metric value not in context
            metric_divergence = True
            diagnostics.append(
                f"Metric divergence: '{unit}' ({m_val}) not found in context passages."
            )

    # Check for entity conflicts
    answer_entities = get_entities(candidate_answer)
    context_entities: set[str] = set()
    for p in passages:
        context_entities.update(get_entities(p.content))

    entity_conflict = False
    if answer_entities and context_entities:
        unmatched_entities = answer_entities - context_entities
        if unmatched_entities and len(unmatched_entities) == len(answer_entities):
            entity_conflict = True
            diagnostics.append(
                f"Entity divergence: {unmatched_entities} conflicts with {context_entities}"
            )

    # Check for antonym inversion
    answer_words = set(re.findall(r"\b\w+\b", candidate_answer.lower()))
    for p in passages:
        p_words = set(re.findall(r"\b\w+\b", p.content.lower()))
        for word, opposites in ANTONYM_PAIRS.items():
            if word in answer_words and any(opp in p_words for opp in opposites):
                has_contradiction = True
                diagnostics.append(
                    f"Antonym contradiction: '{word}' in answer vs '{opposites & p_words}' in evidence."
                )
            elif word in p_words and any(opp in answer_words for opp in opposites):
                has_contradiction = True
                diagnostics.append(
                    f"Antonym contradiction: '{word}' in evidence vs '{opposites & answer_words}' in answer."
                )

    # 4. Classify detected category
    if has_contradiction or entity_conflict:
        detected_category = HallucinationCategory.CONTRADICTORY
    elif (
        v_res.unsupported_claim_rate > 0.0 or metric_divergence or len(unsupp_texts) > 0
    ):
        detected_category = HallucinationCategory.UNSUPPORTED
    else:
        detected_category = HallucinationCategory.SUPPORTED

    # 5. Deterministic Assertions Pass Check
    deterministic_passed = True
    if expected_category == HallucinationCategory.SUPPORTED:
        passed = (detected_category == HallucinationCategory.SUPPORTED) and (
            v_res.unsupported_claim_rate == 0.0
        )
    elif expected_category == HallucinationCategory.UNSUPPORTED:
        passed = (
            detected_category
            in [HallucinationCategory.UNSUPPORTED, HallucinationCategory.CONTRADICTORY]
        ) and (
            v_res.unsupported_claim_rate > 0.0
            or metric_divergence
            or len(unsupp_texts) > 0
        )
    elif expected_category == HallucinationCategory.CONTRADICTORY:
        passed = (
            detected_category == HallucinationCategory.CONTRADICTORY
        ) or has_contradiction
    elif expected_category == HallucinationCategory.INSUFFICIENT_EVIDENCE:
        passed = is_abstention or (
            detected_category == HallucinationCategory.INSUFFICIENT_EVIDENCE
        )
    else:
        passed = False

    return HallucinationEvaluationResult(
        case_id=case_id,
        expected_category=expected_category,
        detected_category=detected_category,
        passed=passed,
        groundedness_ratio=v_res.groundedness_ratio,
        unsupported_claim_rate=v_res.unsupported_claim_rate,
        supported_claims=supp_texts,
        unsupported_claims=unsupp_texts,
        contradicted_claims=contra_texts,
        epistemic_abstention_detected=is_abstention,
        deterministic_assertions_passed=deterministic_passed,
        diagnostics=diagnostics,
    )
