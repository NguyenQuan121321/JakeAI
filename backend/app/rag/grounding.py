"""Claim-level Grounding and Fact Verification Engine for JakeAI RAG."""

from __future__ import annotations

import logging
import re

from pydantic import BaseModel, Field

from app.rag.models import ClaimEntailment, DocumentChunk, GroundingClaim

logger = logging.getLogger(__name__)

# Numerical, currency, percentage, and metric tokens
METRIC_REGEX = re.compile(
    r"[\$€£¥₫]\s*\d+(?:,\d{3})*(?:\.\d+)?(?:\s*(?:billion|million|trillion|tỷ|triệu|k|m|b))?"
    r"|\b\d+(?:,\d{3})*(?:\.\d+)?\s*(?:USD|EUR|GBP|VND|VNĐ|tỷ|triệu|seats|%)"
    r"|\b\d+(?:,\d{3})*(?:\.\d+)?\b",
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

CURRENCY_SYMBOLS: dict[str, str] = {
    "$": "USD",
    "usd": "USD",
    "€": "EUR",
    "eur": "EUR",
    "£": "GBP",
    "gbp": "GBP",
    "¥": "JPY",
    "jpy": "JPY",
    "₫": "VND",
    "vnd": "VND",
    "vnđ": "VND",
    "%": "%",
    "percent": "%",
    "seats": "seats",
}

MULTIPLIER_SUFFIXES: list[tuple[str, float]] = [
    ("trillion", 1e12),
    ("billion", 1e9),
    ("million", 1e6),
    ("triệu", 1e6),
    ("thousand", 1e3),
    ("tỷ", 1e9),
    ("b", 1e9),
    ("m", 1e6),
    ("k", 1e3),
]

ANTONYM_PAIRS: dict[str, set[str]] = {
    "approved": {"rejected", "denied", "disapproved", "vetoed"},
    "rejected": {"approved", "accepted", "passed", "ratified"},
    "denied": {"approved", "accepted", "granted", "confirmed"},
    "launched": {"cancelled", "terminated", "aborted", "scrapped", "postponed"},
    "cancelled": {"launched", "initiated", "continued", "completed"},
    "active": {"inactive", "terminated", "suspended", "closed", "defunct"},
    "inactive": {"active", "operating"},
    "completed": {"cancelled", "abandoned", "aborted", "failed", "incomplete"},
    "success": {"failure", "fiasco", "collapse", "bankrupt", "bankruptcy"},
    "successful": {"failed", "unsuccessful", "bankrupt"},
    "successfully": {"unsuccessfully"},
    "profit": {"loss", "deficit"},
    "profitable": {"unprofitable", "loss-making"},
    "growth": {"decline", "contraction", "decrease"},
    "increase": {"decrease", "decline", "reduction", "drop"},
    "increased": {"decreased", "declined", "reduced", "dropped"},
    "passed": {"failed"},
    "failed": {"passed", "succeeded"},
    "hired": {"fired", "dismissed", "terminated"},
    "true": {"false"},
    "false": {"true"},
    "yes": {"no"},
    "no": {"yes"},
}
for _k, _vs in list(ANTONYM_PAIRS.items()):
    for _v in _vs:
        ANTONYM_PAIRS.setdefault(_v, set()).add(_k)

ABSTENTION_PATTERNS = [
    re.compile(
        r"\b(?:no|insufficient|not enough)\s+(?:information|evidence|data|documents|records|details)\b",
        re.IGNORECASE,
    ),
    re.compile(
        r"\b(?:cannot|unable to|could not)\s+(?:answer|determine|verify|find|state)\b",
        re.IGNORECASE,
    ),
    re.compile(
        r"\b(?:not|never)\s+(?:mentioned|found|stated|disclosed|provided)\b",
        re.IGNORECASE,
    ),
    re.compile(
        r"\bdocuments?\s+(?:do not|does not)\s+(?:mention|contain|state|provide)\b",
        re.IGNORECASE,
    ),
    re.compile(r"\bno\s+verified\s+documents\b", re.IGNORECASE),
]


def is_epistemic_abstention(text: str) -> bool:
    """Check if statement expresses epistemic boundary or explicit evidence absence."""
    return any(p.search(text) for p in ABSTENTION_PATTERNS)


def normalize_metric(raw_token: str) -> tuple[str, float] | None:
    """Normalize a raw metric/numeric string into a canonical (unit, value) tuple."""
    token = raw_token.strip().lower()
    if not token:
        return None

    unit = ""
    for symbol, canonical_unit in CURRENCY_SYMBOLS.items():
        if symbol in token:
            unit = canonical_unit
            break

    cleaned = token.replace(",", "")
    match = re.search(r"\d+(?:\.\d+)?", cleaned)
    if not match:
        return None

    multiplier = 1.0
    for suffix, mult in MULTIPLIER_SUFFIXES:
        pattern = r"(?<=\d|\s)" + re.escape(suffix) + r"(?=\b|\s|$)"
        if re.search(pattern, cleaned):
            multiplier = mult
            break

    try:
        val = float(match.group(0)) * multiplier
        return (unit, round(val, 4))
    except (ValueError, OverflowError):
        return None


def extract_canonical_metrics(text: str) -> set[tuple[str, float]]:
    """Extract set of canonicalized (unit, value) metrics from text."""
    raw_matches = METRIC_REGEX.findall(text)
    metrics: set[tuple[str, float]] = set()
    for m in raw_matches:
        norm = normalize_metric(m)
        if norm is not None:
            metrics.add(norm)
    return metrics


class GroundingVerificationResult(BaseModel):
    """Consolidated result of claim-level grounding verification."""

    is_grounded: bool = Field(
        description="True if generation satisfies groundedness threshold"
    )
    groundedness_ratio: float = Field(
        description="Ratio of supported claims: supported / total substantive claims"
    )
    unsupported_claim_rate: float = Field(
        default=0.0,
        description="Ratio of ungrounded/contradicted claims: (unsupported + contradicted) / total claims",
    )
    claims: list[GroundingClaim] = Field(default_factory=list)
    supported_claims: list[GroundingClaim] = Field(default_factory=list)
    unsupported_claims: list[GroundingClaim] = Field(default_factory=list)
    contradicted_claims: list[GroundingClaim] = Field(default_factory=list)
    uncertain_claims: list[GroundingClaim] = Field(default_factory=list)
    verified_answer: str = Field(
        description="Answer with ungrounded claims filtered or qualified"
    )


def get_entities(text: str) -> set[str]:
    """Extract named entities or capitalized terms from text."""
    words = re.findall(r"\b[a-zA-Z0-9_\-\$]{3,}\b", text)
    entities = set()
    for i, w in enumerate(words):
        if w[0].isupper() and (i > 0 or len(words) == 1) and w.lower() not in STOPWORDS:
            entities.add(w.lower())
    return entities


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
            # Retain epistemic abstentions
            if is_epistemic_abstention(s_clean):
                claims.append(s_clean)
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
        tenant_id: str | None = None,
    ) -> GroundingClaim:
        """Verify a single claim against candidate evidence passages."""
        if tenant_id is not None:
            passages = [p for p in passages if p.tenant_id == tenant_id]

        # 0. Prompt Injection & Jailbreak Defense: Prohibit adversarial commands from grounding
        from app.guardrails.input_guard import check_input_guardrail

        guard_decision = check_input_guardrail(claim)
        if not guard_decision.allowed:
            return GroundingClaim(
                claim_text=claim,
                entailment=ClaimEntailment.UNSUPPORTED,
                confidence=0.0,
                supporting_chunk_ids=[],
                reasoning=(
                    f"Claim contains adversarial prompt injection or security override directives: "
                    f"{guard_decision.violation_type or 'SECURITY_VIOLATION'}."
                ),
            )

        if is_epistemic_abstention(claim):
            return GroundingClaim(
                claim_text=claim,
                entailment=ClaimEntailment.SUPPORTED,
                confidence=1.0,
                supporting_chunk_ids=[],
                reasoning="Epistemic boundary statement or explicit evidence absence.",
            )

        if not passages:
            return GroundingClaim(
                claim_text=claim,
                entailment=ClaimEntailment.UNSUPPORTED,
                confidence=0.0,
                supporting_chunk_ids=[],
                reasoning="No context passages available for verification.",
            )

        claim_metrics = extract_canonical_metrics(claim)
        claim_raw_numbers = set(METRIC_REGEX.findall(claim))
        claim_terms = {
            w.lower()
            for w in re.findall(r"\b[a-zA-Z0-9_\-\$]{3,}\b", claim)
            if w.lower() not in STOPWORDS and not w.isdigit()
        }
        claim_entities = get_entities(claim)

        best_support_chunks: list[str] = []
        contradicting_chunks: list[str] = []
        max_overlap_ratio = 0.0
        number_mismatch_detected = False
        antonym_contradiction_detected = False
        qualitative_conflict_detected = False

        for chunk in passages:
            chunk_content = chunk.content
            chunk_metrics = extract_canonical_metrics(chunk_content)
            chunk_raw_numbers = set(METRIC_REGEX.findall(chunk_content))
            chunk_terms = {
                w.lower()
                for w in re.findall(r"\b[a-zA-Z0-9_\-\$]{3,}\b", chunk_content)
                if w.lower() not in STOPWORDS and not w.isdigit()
            }
            chunk_entities = get_entities(chunk_content)

            overlap = len(claim_terms.intersection(chunk_terms))
            ratio = overlap / max(1, len(claim_terms))

            # Check antonym contradiction
            has_antonym = any(
                chunk_terms.intersection(ANTONYM_PAIRS.get(w, set()))
                for w in claim_terms
            )
            if has_antonym and ratio >= 0.25:
                antonym_contradiction_detected = True
                contradicting_chunks.append(chunk.chunk_id)
                continue

            # If claim asserts numbers or metrics
            if claim_metrics or claim_raw_numbers:
                metrics_match = (
                    claim_metrics.issubset(chunk_metrics)
                    if claim_metrics
                    else claim_raw_numbers.issubset(chunk_raw_numbers)
                )

                if metrics_match:
                    if ratio >= 0.25:
                        best_support_chunks.append(chunk.chunk_id)
                        max_overlap_ratio = max(max_overlap_ratio, ratio)
                else:
                    if ratio >= 0.25 and (chunk_metrics or chunk_raw_numbers):
                        number_mismatch_detected = True
                        contradicting_chunks.append(chunk.chunk_id)
            else:
                # Qualitative claim verification
                max_overlap_ratio = max(max_overlap_ratio, ratio)
                if claim_entities:
                    if claim_entities.issubset(chunk_entities):
                        if ratio >= 0.40:
                            best_support_chunks.append(chunk.chunk_id)
                    else:
                        if ratio >= 0.35 and chunk_entities:
                            qualitative_conflict_detected = True
                            contradicting_chunks.append(chunk.chunk_id)
                else:
                    if ratio >= 0.65:
                        best_support_chunks.append(chunk.chunk_id)
                    elif ratio >= 0.35 and best_support_chunks:
                        qualitative_conflict_detected = True
                        contradicting_chunks.append(chunk.chunk_id)

        # Multi-chunk ensemble metric evaluation for compound claims
        if (claim_metrics or claim_raw_numbers) and not best_support_chunks:
            all_passage_metrics: set[tuple[str, float]] = set()
            all_passage_raw: set[str] = set()
            for p in passages:
                all_passage_metrics.update(extract_canonical_metrics(p.content))
                all_passage_raw.update(METRIC_REGEX.findall(p.content))

            multi_metric_match = (
                claim_metrics.issubset(all_passage_metrics)
                if claim_metrics
                else claim_raw_numbers.issubset(all_passage_raw)
            )
            if multi_metric_match:
                for chunk in passages:
                    c_metrics = extract_canonical_metrics(chunk.content)
                    c_raw = set(METRIC_REGEX.findall(chunk.content))
                    c_terms = {
                        w.lower()
                        for w in re.findall(r"\b[a-zA-Z0-9_\-\$]{3,}\b", chunk.content)
                        if w.lower() not in STOPWORDS and not w.isdigit()
                    }
                    overlap = len(claim_terms.intersection(c_terms))
                    ratio = overlap / max(1, len(claim_terms))
                    has_metric_overlap = (
                        bool(claim_metrics.intersection(c_metrics))
                        if claim_metrics
                        else bool(claim_raw_numbers.intersection(c_raw))
                    )
                    if has_metric_overlap and ratio >= 0.15:
                        best_support_chunks.append(chunk.chunk_id)
                        max_overlap_ratio = max(max_overlap_ratio, ratio)
                if best_support_chunks:
                    number_mismatch_detected = False

        # Classify entailment
        if best_support_chunks:
            if (
                number_mismatch_detected
                or qualitative_conflict_detected
                or antonym_contradiction_detected
            ):
                return GroundingClaim(
                    claim_text=claim,
                    entailment=ClaimEntailment.UNCERTAIN,
                    confidence=0.50,
                    supporting_chunk_ids=best_support_chunks,
                    reasoning=(
                        f"Conflicting evidence detected in context passages: supported by "
                        f"{', '.join(best_support_chunks)} but contradicted by other records."
                    ),
                )
            confidence = round(min(1.0, 0.70 + (max_overlap_ratio * 0.30)), 2)
            return GroundingClaim(
                claim_text=claim,
                entailment=ClaimEntailment.SUPPORTED,
                confidence=confidence,
                supporting_chunk_ids=best_support_chunks,
                reasoning=f"Attested in chunks: {', '.join(best_support_chunks)}",
            )

        if antonym_contradiction_detected or (
            (claim_metrics or claim_raw_numbers) and number_mismatch_detected
        ):
            return GroundingClaim(
                claim_text=claim,
                entailment=ClaimEntailment.UNSUPPORTED,
                confidence=0.0,
                supporting_chunk_ids=[],
                reasoning=(
                    "Claim directly contradicts context passages: "
                    f"contradicted by {', '.join(contradicting_chunks or ['evidence records'])}."
                ),
            )

        if (claim_metrics or claim_raw_numbers) and self.strict_metric_entailment:
            return GroundingClaim(
                claim_text=claim,
                entailment=ClaimEntailment.UNSUPPORTED,
                confidence=0.0,
                supporting_chunk_ids=[],
                reasoning="Claim contains numbers or metrics absent from or contradicting evidence passages.",
            )

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
        tenant_id: str | None = None,
    ) -> GroundingVerificationResult:
        """Run complete claim extraction and grounding verification."""
        if tenant_id is not None:
            passages = [p for p in passages if p.tenant_id == tenant_id]

        claims = self.extract_claims(text)
        if not claims:
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
            self.verify_claim(c, passages, tenant_id=tenant_id) for c in claims
        ]

        supported = [
            c for c in verified_claims if c.entailment == ClaimEntailment.SUPPORTED
        ]
        contradicted = [
            c
            for c in verified_claims
            if c.entailment == ClaimEntailment.CONTRADICTED
            or "contradicts" in c.reasoning.lower()
        ]
        unsupported = [
            c
            for c in verified_claims
            if c.entailment == ClaimEntailment.UNSUPPORTED and c not in contradicted
        ]
        uncertain = [
            c for c in verified_claims if c.entailment == ClaimEntailment.UNCERTAIN
        ]

        total_claims_count = len(claims)
        ratio = len(supported) / total_claims_count if total_claims_count else 0.0
        unsupported_rate = (
            (len(unsupported) + len(contradicted)) / total_claims_count
            if total_claims_count
            else 0.0
        )
        is_grounded = (
            ratio >= self.min_groundedness_ratio
            and len(unsupported) == 0
            and len(contradicted) == 0
        )

        # Construct verified answer filtering out unsupported and contradicted statements
        verified_sentences: list[str] = []
        for claim_obj in verified_claims:
            if claim_obj.entailment == ClaimEntailment.SUPPORTED:
                verified_sentences.append(claim_obj.claim_text)
            elif claim_obj.entailment == ClaimEntailment.UNCERTAIN:
                c_text = claim_obj.claim_text.strip()
                if c_text.endswith((".", "!", "?")):
                    verified_sentences.append(f"{c_text[:-1]} [unverified]{c_text[-1]}")
                else:
                    verified_sentences.append(f"{c_text} [unverified]")
            else:
                logger.warning(
                    "Dropping unsupported/contradicted claim from user answer: '%s' (Reason: %s)",
                    claim_obj.claim_text,
                    claim_obj.reasoning,
                )

        verified_answer = " ".join(verified_sentences) if verified_sentences else ""

        return GroundingVerificationResult(
            is_grounded=is_grounded,
            groundedness_ratio=round(ratio, 4),
            unsupported_claim_rate=round(unsupported_rate, 4),
            claims=verified_claims,
            supported_claims=supported,
            unsupported_claims=unsupported + contradicted,
            contradicted_claims=contradicted,
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
