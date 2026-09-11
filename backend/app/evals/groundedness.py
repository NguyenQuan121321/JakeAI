"""Groundedness and Hallucination Evaluation Engine (TASK OPS-11).

Provides fine-grained claim-level extraction, entailment analysis, and
hallucination scoring against retrieved context passages.
"""

from __future__ import annotations

import re
from typing import Any, Literal

from pydantic import BaseModel, Field

ClaimStatus = Literal["supported", "unsupported", "uncertain"]

STOPWORDS = {
    "the", "a", "an", "and", "or", "but", "in", "on", "at", "to", "for", "with",
    "by", "of", "from", "is", "are", "was", "were", "be", "been", "being",
    "have", "has", "had", "do", "does", "did", "this", "that", "these", "those",
    "it", "its", "they", "them", "their", "we", "our", "you", "your", "i", "me",
    "my", "as", "if", "then", "so", "than", "too", "very", "can", "will", "just",
    "should", "now", "here", "there", "based", "according", "reported", "shows"
}

_NUM_PATTERN = re.compile(r"\$?\b\d+(?:[.,]\d+)?%?")


def _extract_numbers(text: str) -> set[str]:
    """Extract all numbers, percentages, and currencies from text."""
    return set(_NUM_PATTERN.findall(text))


def _extract_keywords(text: str) -> set[str]:
    """Extract content words (3+ chars) excluding common stopwords."""
    words = re.findall(r"\b[a-zA-Z0-9_\-]{3,}\b", text.lower())
    return {w for w in words if w not in STOPWORDS}


def segment_claims(text: str) -> list[str]:
    """Segment generated answer text into atomic verifiable claims."""
    # Split on sentence boundaries and line breaks
    raw_sentences = re.split(r"(?<=[.!?])\s+|\n+", text.strip())
    claims: list[str] = []

    conversational_prefixes = (
        "hello", "hi", "sure", "certainly", "here is", "here are", "based on",
        "according to", "in summary", "to summarize", "in conclusion", "overall"
    )
    conversational_phrases = (
        "let me know", "feel free", "hope this helps", "if you need",
        "more details", "further questions", "reach out"
    )

    for s in raw_sentences:
        clean = s.strip()
        if not clean:
            continue
        lower = clean.lower()
        # Skip introductory framing
        if any(lower.startswith(p) for p in conversational_prefixes) and len(clean.split()) <= 10:
            continue
        # Skip conversational closing remarks
        if any(phrase in lower for phrase in conversational_phrases):
            continue
        # Require sentence to have at least 3 words to be considered a factual claim
        if len(clean.split()) >= 3:
            claims.append(clean)

    return claims


class ClaimAnalysis(BaseModel):
    """Detailed entailment evaluation for an individual claim."""

    claim_text: str
    status: ClaimStatus
    matched_passage_index: int | None = None
    confidence: float = Field(default=0.0, ge=0.0, le=1.0)
    missing_evidence: list[str] = Field(default_factory=list)


class GroundednessReport(BaseModel):
    """Comprehensive groundedness and hallucination evaluation report."""

    total_claims: int = 0
    supported_claims: int = 0
    unsupported_claims: int = 0
    uncertain_claims: int = 0
    supported_claim_rate: float = Field(default=0.0, ge=0.0, le=1.0)
    unsupported_claim_rate: float = Field(default=0.0, ge=0.0, le=1.0)
    uncertain_claim_rate: float = Field(default=0.0, ge=0.0, le=1.0)
    citation_correctness: float = Field(default=1.0, ge=0.0, le=1.0)
    groundedness_score: float = Field(default=0.0, ge=0.0, le=1.0)
    passed: bool = False
    claims: list[ClaimAnalysis] = Field(default_factory=list)


def evaluate_groundedness(
    answer: str,
    context_passages: list[str],
    citations: list[dict[str, Any]] | None = None,
) -> GroundednessReport:
    """Evaluate factual groundedness and hallucination rate of generated answer."""
    claims = segment_claims(answer)
    if not claims:
        return GroundednessReport(
            total_claims=0,
            supported_claims=0,
            unsupported_claims=0,
            uncertain_claims=0,
            supported_claim_rate=1.0,
            unsupported_claim_rate=0.0,
            uncertain_claim_rate=0.0,
            citation_correctness=1.0,
            groundedness_score=1.0,
            passed=True,
            claims=[],
        )

    # Pre-extract keywords and numbers from all context passages
    passage_data: list[tuple[set[str], set[str]]] = []
    combined_numbers: set[str] = set()
    for p in context_passages:
        kws = _extract_keywords(p)
        nums = _extract_numbers(p)
        passage_data.append((kws, nums))
        combined_numbers.update(nums)

    claim_analyses: list[ClaimAnalysis] = []
    supported_count = 0
    unsupported_count = 0
    uncertain_count = 0

    for claim in claims:
        claim_kws = _extract_keywords(claim)
        claim_nums = _extract_numbers(claim)

        # 1. Hard hallucination: claim introduces numbers not in ANY passage
        unsupported_nums = claim_nums - combined_numbers
        if unsupported_nums:
            claim_analyses.append(
                ClaimAnalysis(
                    claim_text=claim,
                    status="unsupported",
                    matched_passage_index=None,
                    confidence=1.0,
                    missing_evidence=list(unsupported_nums),
                )
            )
            unsupported_count += 1
            continue

        # 2. Check overlap against each individual passage
        best_passage_idx: int | None = None
        best_overlap_ratio = 0.0

        for p_idx, (p_kws, p_nums) in enumerate(passage_data):
            if not claim_kws:
                overlap_ratio = 1.0
            else:
                overlap_count = len(claim_kws.intersection(p_kws))
                overlap_ratio = overlap_count / len(claim_kws)

            # Check number consistency within this passage
            if claim_nums and not claim_nums.issubset(p_nums):
                # Contains numbers from different passages or not fully present here
                overlap_ratio *= 0.5

            if overlap_ratio > best_overlap_ratio:
                best_overlap_ratio = overlap_ratio
                best_passage_idx = p_idx

        # Classify status based on best overlap ratio
        if best_overlap_ratio >= 0.70:
            status: ClaimStatus = "supported"
            supported_count += 1
            confidence = round(best_overlap_ratio, 2)
            missing = []
        elif best_overlap_ratio >= 0.40:
            status = "uncertain"
            uncertain_count += 1
            confidence = round(best_overlap_ratio, 2)
            missing = list(claim_kws - passage_data[best_passage_idx][0]) if best_passage_idx is not None else []
        else:
            status = "unsupported"
            unsupported_count += 1
            confidence = round(1.0 - best_overlap_ratio, 2)
            missing = list(claim_kws)

        claim_analyses.append(
            ClaimAnalysis(
                claim_text=claim,
                status=status,
                matched_passage_index=best_passage_idx,
                confidence=confidence,
                missing_evidence=missing[:5],
            )
        )

    total = len(claims)
    supp_rate = round(supported_count / total, 4)
    unsupp_rate = round(unsupported_count / total, 4)
    uncert_rate = round(uncertain_count / total, 4)
    # Groundedness score weights supported claims fully and uncertain claims halfway
    grounded_score = round(min(1.0, max(0.0, (supported_count + 0.5 * uncertain_count) / total)), 4)

    # Citation correctness check
    citation_correctness = 1.0
    if citations:
        correct_cites = 0
        for cite in citations:
            passage_idx = cite.get("passage_index")
            if isinstance(passage_idx, int) and 0 <= passage_idx < len(context_passages):
                correct_cites += 1
        citation_correctness = round(correct_cites / len(citations), 4)

    # Strict Quality Gate: supported >= 85%, unsupported <= 10%, groundedness >= 0.85
    passed = supp_rate >= 0.85 and unsupp_rate <= 0.10 and grounded_score >= 0.85

    return GroundednessReport(
        total_claims=total,
        supported_claims=supported_count,
        unsupported_claims=unsupported_count,
        uncertain_claims=uncertain_count,
        supported_claim_rate=supp_rate,
        unsupported_claim_rate=unsupp_rate,
        uncertain_claim_rate=uncert_rate,
        citation_correctness=citation_correctness,
        groundedness_score=grounded_score,
        passed=passed,
        claims=claim_analyses,
    )
