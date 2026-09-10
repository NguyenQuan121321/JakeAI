"""Claim-level Grounding and Fact Verification Engine for JakeAI RAG."""

from __future__ import annotations

import logging
import re

from pydantic import BaseModel, Field

from app.rag.models import ClaimEntailment, DocumentChunk, GroundingClaim

logger = logging.getLogger(__name__)

# Numerical, currency, percentage, and metric tokens
METRIC_REGEX = re.compile(
    r"[\$€£¥₫]\s*\d+(?:[.,]\d+)?(?:\s*(?:billion|million|trillion|tỷ|triệu|k|m|b))?"
    r"|\b\d+(?:[.,]\d+)?\s*(?:USD|EUR|GBP|VND|VNĐ|tỷ|triệu|seats|%)"
    r"|\b\d+(?:[.,]\d+)?\b",
    re.IGNORECASE,
)

STOPWORDS = {
    "the",
    "and",
    "for",
    "with",
    "that",
    "this",
    "from",
    "are",
    "was",
    "were",
    "has",
    "have",
    "had",
    "what",
    "which",
    "when",
    "where",
    "who",
    "whom",
    "why",
    "how",
    "been",
    "will",
    "would",
    "could",
    "should",
    "than",
    "then",
    "also",
    "such",
    "about",
    "both",
    "each",
    "other",
    "some",
    "according",
    "based",
    "provided",
    "context",
    "document",
    "documents",
    "report",
    "reports",
}


class GroundingVerificationResult(BaseModel):
    """Consolidated result of claim-level grounding verification."""

    is_grounded: bool = Field(
        description="True if generation satisfies groundedness threshold"
    )
    groundedness_ratio: float = Field(
        description="Ratio of supported claims: supported / total substantive claims"
    )
    claims: list[GroundingClaim] = Field(default_factory=list)
    supported_claims: list[GroundingClaim] = Field(default_factory=list)
    unsupported_claims: list[GroundingClaim] = Field(default_factory=list)
    uncertain_claims: list[GroundingClaim] = Field(default_factory=list)
    verified_answer: str = Field(
        description="Answer with ungrounded claims filtered or qualified"
    )


class GroundingVerifier:
    """Extracts propositional statements and verifies factual entailment against context."""

    def __init__(
        self,
        min_groundedness_ratio: float = 0.60,
        strict_metric_entailment: bool = True,
    ) -> None:
        self.min_groundedness_ratio = min_groundedness_ratio
        self.strict_metric_entailment = strict_metric_entailment

    def extract_claims(self, text: str) -> list[str]:
        """Decompose generated response into discrete substantive factual statements."""
        # Strip citation cards section if present
        clean_text = text.split("#### 📚 Verifiable Citations & Sources")[0]
        # Strip markdown headers, footers, horizontal rules
        clean_text = re.sub(r"^#{1,6}\s+.*$", "", clean_text, flags=re.MULTILINE)
        clean_text = re.sub(r"^---+$", "", clean_text, flags=re.MULTILINE)

        # Split by sentences or bullet points
        raw_sentences = re.split(r"(?<=[.!?])\s+|\n+(?:[-*•]|\d+\.)\s*", clean_text)
        claims: list[str] = []

        for raw_s in raw_sentences:
            s = raw_s.strip()
            # Remove inline footnote markers like [^1], [^2] for claim analysis
            s_clean = re.sub(r"\[\^\d+\]", "", s).strip()
            if not s_clean:
                continue
            # Filter out non-substantive conversational hedges
            words = [
                w for w in re.findall(r"\b\w+\b", s_clean.lower()) if w not in STOPWORDS
            ]
            if len(words) < 3 and not METRIC_REGEX.search(s_clean):
                continue
            claims.append(s_clean)

        return claims

    def verify_claim(
        self,
        claim: str,
        passages: list[DocumentChunk],
    ) -> GroundingClaim:
        """Verify a single claim against candidate evidence passages."""
        if not passages:
            return GroundingClaim(
                claim_text=claim,
                entailment=ClaimEntailment.UNSUPPORTED,
                confidence=0.0,
                supporting_chunk_ids=[],
                reasoning="No context passages available for verification.",
            )

        claim_numbers = set(METRIC_REGEX.findall(claim))
        claim_terms = {
            w.lower()
            for w in re.findall(r"\b[a-zA-Z0-9_\-\$]{3,}\b", claim)
            if w.lower() not in STOPWORDS
        }

        best_support_chunks: list[str] = []
        max_overlap_ratio = 0.0
        number_mismatch_detected = False

        for chunk in passages:
            chunk_content = chunk.content
            chunk_numbers = set(METRIC_REGEX.findall(chunk_content))
            chunk_terms = {
                w.lower()
                for w in re.findall(r"\b[a-zA-Z0-9_\-\$]{3,}\b", chunk_content)
                if w.lower() not in STOPWORDS
            }

            # If claim asserts numbers, check if they exist in the chunk
            if claim_numbers:
                if claim_numbers.issubset(chunk_numbers):
                    # Numbers are attested
                    overlap = len(claim_terms.intersection(chunk_terms))
                    ratio = overlap / max(1, len(claim_terms))
                    if ratio >= 0.25:
                        best_support_chunks.append(chunk.chunk_id)
                        max_overlap_ratio = max(max_overlap_ratio, ratio)
                else:
                    # Check if partial number match with contradicting numbers
                    intersect_num = claim_numbers.intersection(chunk_numbers)
                    if not intersect_num and claim_terms.intersection(chunk_terms):
                        number_mismatch_detected = True
            else:
                # Qualitative claim verification
                overlap = len(claim_terms.intersection(chunk_terms))
                ratio = overlap / max(1, len(claim_terms))
                if ratio >= 0.40:
                    best_support_chunks.append(chunk.chunk_id)
                    max_overlap_ratio = max(max_overlap_ratio, ratio)

        # Classify entailment
        if best_support_chunks:
            confidence = round(min(1.0, 0.70 + (max_overlap_ratio * 0.30)), 2)
            return GroundingClaim(
                claim_text=claim,
                entailment=ClaimEntailment.SUPPORTED,
                confidence=confidence,
                supporting_chunk_ids=best_support_chunks,
                reasoning=f"Attested in chunks: {', '.join(best_support_chunks)}",
            )

        if number_mismatch_detected or (
            claim_numbers and self.strict_metric_entailment
        ):
            return GroundingClaim(
                claim_text=claim,
                entailment=ClaimEntailment.UNSUPPORTED,
                confidence=0.0,
                supporting_chunk_ids=[],
                reasoning="Claim contains numbers or metrics absent from or contradicting evidence passages.",
            )

        # Qualitative claim with modest overlap
        if max_overlap_ratio >= 0.20:
            return GroundingClaim(
                claim_text=claim,
                entailment=ClaimEntailment.UNCERTAIN,
                confidence=0.40,
                supporting_chunk_ids=[],
                reasoning="Weak semantic overlap without definitive factual grounding.",
            )

        return GroundingClaim(
            claim_text=claim,
            entailment=ClaimEntailment.UNSUPPORTED,
            confidence=0.0,
            supporting_chunk_ids=[],
            reasoning="No supporting evidence found in context passages.",
        )

    def verify(
        self,
        text: str,
        passages: list[DocumentChunk],
    ) -> GroundingVerificationResult:
        """Run complete claim extraction and grounding verification."""
        claims = self.extract_claims(text)
        if not claims:
            # If no substantive claims (e.g. empty or boilerplate), check if passages exist
            is_grounded = bool(passages)
            return GroundingVerificationResult(
                is_grounded=is_grounded,
                groundedness_ratio=1.0 if is_grounded else 0.0,
                claims=[],
                supported_claims=[],
                unsupported_claims=[],
                uncertain_claims=[],
                verified_answer=text,
            )

        verified_claims: list[GroundingClaim] = [
            self.verify_claim(c, passages) for c in claims
        ]

        supported = [
            c for c in verified_claims if c.entailment == ClaimEntailment.SUPPORTED
        ]
        unsupported = [
            c for c in verified_claims if c.entailment == ClaimEntailment.UNSUPPORTED
        ]
        uncertain = [
            c for c in verified_claims if c.entailment == ClaimEntailment.UNCERTAIN
        ]

        ratio = len(supported) / len(claims) if claims else 0.0
        is_grounded = ratio >= self.min_groundedness_ratio and len(unsupported) == 0

        # Construct verified answer filtering out unsupported statements
        verified_sentences: list[str] = []
        for claim_obj in verified_claims:
            if claim_obj.entailment == ClaimEntailment.SUPPORTED:
                verified_sentences.append(claim_obj.claim_text)
            elif claim_obj.entailment == ClaimEntailment.UNCERTAIN:
                # Include uncertain claims with caveat
                verified_sentences.append(claim_obj.claim_text)
            else:
                logger.warning(
                    "Dropping unsupported claim from user answer: '%s' (Reason: %s)",
                    claim_obj.claim_text,
                    claim_obj.reasoning,
                )

        verified_answer = " ".join(verified_sentences) if verified_sentences else ""

        return GroundingVerificationResult(
            is_grounded=is_grounded,
            groundedness_ratio=round(ratio, 4),
            claims=verified_claims,
            supported_claims=supported,
            unsupported_claims=unsupported,
            uncertain_claims=uncertain,
            verified_answer=verified_answer,
        )


_default_grounding_verifier: GroundingVerifier | None = None


def get_grounding_verifier() -> GroundingVerifier:
    """Singleton getter for GroundingVerifier."""
    global _default_grounding_verifier
    if _default_grounding_verifier is None:
        _default_grounding_verifier = GroundingVerifier()
    return _default_grounding_verifier
