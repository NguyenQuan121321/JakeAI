"""Context Selection and Evidence Optimization Engine for JakeAI RAG.

Implements Section 4 of 04_RAG.md:
The final context builder prefers:
- high relevance (adaptive score thresholding)
- high evidence value (novel fact/entity discovery)
- low redundancy (cross-chunk Jaccard deduplication)
- low token cost (budget-bounded packing with physical token reduction)
- strict multi-tenant isolation boundary
"""

from __future__ import annotations

import logging
import re

from app.optimizer.token_pruner import (
    estimate_tokens,
    get_token_pruner,
)
from app.rag.models import ContextSelectionResult, DocumentChunk

logger = logging.getLogger(__name__)

CITATION_TAG_REGEX = re.compile(
    r"\[(?:SEC|DOC|P|REF|CHUNK|EXCERPT)[^\]]+\]|=== DOCUMENT EXCERPT \[[^\]]+\] ===",
    re.IGNORECASE,
)

FACT_REGEX = re.compile(
    r"[\$€£¥₫]\s*\d+(?:[.,]\d+)?(?:\s*(?:billion|million|trillion|tỷ|triệu|k|m|b))?"
    r"|\b\d+(?:[.,]\d+)?\s*(?:USD|EUR|GBP|VND|VNĐ|tỷ|triệu|seats|%)"
    r"|\b(?:q[1-4]|fy\d{2,4})\b"
    r"|\b\d{4}[-/.]\d{1,2}[-/.]\d{1,2}\b"
    r"|\b\d+(?:[.,]\d+)?\b",
    re.IGNORECASE,
)


EXTRA_BOILERPLATE = [
    re.compile(r"(?i)\bfor immediate release\b"),
    re.compile(r"(?i)\ball rights reserved\b"),
    re.compile(r"(?i)\bconfidential and proprietary\b"),
    re.compile(r"(?i)\bforward looking statements?\b"),
    re.compile(r"(?i)\bplease review full disclaimer\b[^.\n]*"),
    re.compile(r"(?i)\bdisclaimer:[^.\n]*"),
]

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
    "give",
    "given",
    "into",
    "upon",
    "announcement",
    "please",
    "review",
    "full",
    "legal",
    "notice",
}


def _clean_content_for_analysis(text: str) -> str:
    """Remove metadata banners and corporate boilerplate before analysis."""
    clean = re.sub(
        r"=== (?:DOCUMENT EXCERPT|SECTION|CHUNK) \[[^\]]+\] ===\n?",
        "",
        text,
        flags=re.IGNORECASE,
    )
    for pat in EXTRA_BOILERPLATE:
        clean = pat.sub("", clean)
    pruner = get_token_pruner()
    return pruner._clean_boilerplate(clean).strip()


def _tokenize_terms(text: str) -> set[str]:
    """Extract lowercased significant substantive terms excluding stopwords."""
    clean = _clean_content_for_analysis(text)
    raw_tokens = set(re.findall(r"\b[a-zA-Z0-9_\-\$]{3,}\b", clean.lower()))
    return {t for t in raw_tokens if t not in STOPWORDS}


def _extract_protected_facts(text: str) -> set[str]:
    """Extract all numerical figures, dates, currencies, and metrics."""
    clean = _clean_content_for_analysis(text)
    return {match.strip() for match in FACT_REGEX.findall(clean)}


class ContextSelector:
    """Selects the minimal sufficient evidence set from candidate document chunks."""

    def __init__(
        self,
        min_relative_score: float = 0.30,
        redundancy_threshold: float = 0.65,
        max_context_tokens: int = 800,
    ) -> None:
        self.min_relative_score = min_relative_score
        self.redundancy_threshold = redundancy_threshold
        self.max_context_tokens = max_context_tokens
        self.pruner = get_token_pruner()

    def select_context(
        self,
        candidates: list[DocumentChunk],
        query: str = "",
        tenant_id: str | None = None,
        max_tokens: int | None = None,
        min_relative_score: float | None = None,
        redundancy_threshold: float | None = None,
    ) -> ContextSelectionResult:
        """Filter, deduplicate, and pack candidate chunks into minimal sufficient context."""
        budget = max_tokens if max_tokens is not None else self.max_context_tokens
        score_thresh = (
            min_relative_score
            if min_relative_score is not None
            else self.min_relative_score
        )
        redundancy_limit = (
            redundancy_threshold
            if redundancy_threshold is not None
            else self.redundancy_threshold
        )

        if not candidates:
            return ContextSelectionResult(
                selected_chunks=[],
                formatted_context="",
                raw_tokens=0,
                selected_tokens=0,
                tokens_saved=0,
                reduction_ratio=0.0,
                pruned_chunks_count=0,
                citations_preserved=[],
            )

        # 1. Enforce Strict Multi-Tenant Boundary Guardrail
        valid_candidates: list[DocumentChunk] = []
        for chunk in candidates:
            if tenant_id and chunk.tenant_id != tenant_id:
                logger.error(
                    "SECURITY ALERT: Dropping chunk '%s' belonging to foreign tenant '%s' for request tenant '%s'.",
                    chunk.chunk_id,
                    chunk.tenant_id,
                    tenant_id,
                )
                continue
            valid_candidates.append(chunk)

        if not valid_candidates:
            return ContextSelectionResult(
                selected_chunks=[],
                formatted_context="",
                raw_tokens=0,
                selected_tokens=0,
                tokens_saved=0,
                reduction_ratio=0.0,
                pruned_chunks_count=len(candidates),
                citations_preserved=[],
            )

        # Measure raw candidate tokens across valid pool
        raw_combined_text = "\n\n".join(c.content for c in valid_candidates)
        raw_tokens = estimate_tokens(raw_combined_text)

        # 2. Adaptive Relevance Thresholding
        max_score = max((c.score for c in valid_candidates), default=1.0)
        cutoff_score = max_score * score_thresh

        query_terms = _tokenize_terms(query)
        relevant_candidates: list[DocumentChunk] = []
        for chunk in valid_candidates:
            chunk_terms = _tokenize_terms(chunk.content)
            has_query_term = bool(query_terms.intersection(chunk_terms))
            # Keep chunk if score >= cutoff or contains direct query keywords
            if chunk.score >= cutoff_score or has_query_term:
                relevant_candidates.append(chunk)

        # Sort candidate chunks by score descending
        relevant_candidates.sort(key=lambda x: x.score, reverse=True)

        # 3. Cross-Chunk Redundancy Pruning with Protected Entity Preservation
        selected_chunks: list[DocumentChunk] = []
        accumulated_terms: set[str] = set()
        accumulated_facts: set[str] = set()

        for chunk in relevant_candidates:
            chunk_terms = _tokenize_terms(chunk.content)
            chunk_facts = _extract_protected_facts(chunk.content)

            if not selected_chunks:
                selected_chunks.append(chunk)
                accumulated_terms.update(chunk_terms)
                accumulated_facts.update(chunk_facts)
                continue

            # Calculate Jaccard similarity / overlap ratio against already selected pool
            if accumulated_terms and chunk_terms:
                intersection_count = len(chunk_terms.intersection(accumulated_terms))
                overlap_ratio = intersection_count / len(chunk_terms)
            else:
                overlap_ratio = 0.0

            # Check if this chunk introduces novel numerical figures, dates, or citations
            novel_facts = chunk_facts - accumulated_facts

            # Discard if heavily redundant AND introduces no novel factual evidence
            if overlap_ratio >= redundancy_limit and not novel_facts:
                logger.debug(
                    "Pruning redundant chunk '%s' (overlap=%.2f, novel_facts=0)",
                    chunk.chunk_id,
                    overlap_ratio,
                )
                continue

            selected_chunks.append(chunk)
            accumulated_terms.update(chunk_terms)
            accumulated_facts.update(chunk_facts)

        # 4. Token-Budget Bounded Packing
        budget_chunks: list[DocumentChunk] = []
        current_token_count = 0

        for chunk in selected_chunks:
            chunk_token_est = estimate_tokens(chunk.content)
            if budget_chunks and (current_token_count + chunk_token_est > budget):
                logger.debug(
                    "Context budget reached (%d tokens). Stopping chunk inclusion.",
                    current_token_count,
                )
                break
            budget_chunks.append(chunk)
            current_token_count += chunk_token_est

        # Fallback: Ensure at least the top chunk is retained if candidates existed
        if not budget_chunks and relevant_candidates:
            budget_chunks = [relevant_candidates[0]]

        # 5. Format Structured Context with Citation Anchors
        formatted_parts: list[str] = []
        citations_preserved: list[str] = []

        for idx, chunk in enumerate(budget_chunks, 1):
            # Extract internal citation markers e.g. [SEC-Q3-P14]
            internal_citations = CITATION_TAG_REGEX.findall(chunk.content)
            for ic in internal_citations:
                cleaned = ic.strip()
                if cleaned and cleaned not in citations_preserved:
                    citations_preserved.append(cleaned)

            source_label = chunk.source or f"Document {idx}"
            formatted_parts.append(
                f"[{idx}] Source: {source_label} (Score: {chunk.score:.2f})\n"
                f'"{chunk.content.strip()}"'
            )

        formatted_context = "\n\n".join(formatted_parts)
        selected_content_text = "\n\n".join(c.content for c in budget_chunks)
        selected_tokens = estimate_tokens(selected_content_text)
        tokens_saved = max(0, raw_tokens - selected_tokens)
        reduction_ratio = round(tokens_saved / raw_tokens, 4) if raw_tokens > 0 else 0.0
        pruned_count = len(candidates) - len(budget_chunks)

        return ContextSelectionResult(
            selected_chunks=budget_chunks,
            formatted_context=formatted_context,
            raw_tokens=raw_tokens,
            selected_tokens=selected_tokens,
            tokens_saved=tokens_saved,
            reduction_ratio=reduction_ratio,
            pruned_chunks_count=pruned_count,
            citations_preserved=citations_preserved,
        )


_default_context_selector: ContextSelector | None = None


def get_context_selector() -> ContextSelector:
    """Singleton getter for ContextSelector."""
    global _default_context_selector
    if _default_context_selector is None:
        _default_context_selector = ContextSelector()
    return _default_context_selector
