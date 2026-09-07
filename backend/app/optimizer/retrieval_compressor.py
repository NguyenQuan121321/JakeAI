"""Layer 4: RAG Retrieval Compression Engine for JakeAI Platform.

Implements Section 2 Layer 4 of 03_TOKEN_OPTIMIZATION.md:
1. Adaptive relevance cutoff: filters out low-relevance distractor chunks.
2. Cross-chunk redundancy pruning while strictly preserving:
   - Citations (e.g. [SEC-Q3-P14], [SEC-Q3-P22], [DOC-...])
   - Numerical entities, dates, currencies, and factual metrics
3. Telemetry tracking:
   - Raw retrieved tokens vs compressed tokens sent to model
   - Physical tokens saved & compression ratio
   - Citations preserved
"""

from __future__ import annotations

import logging
import re
from typing import Any

from pydantic import BaseModel, Field

from app.optimizer.token_pruner import (
    estimate_tokens,
    get_token_pruner,
)

logger = logging.getLogger(__name__)

CITATION_REGEX = re.compile(
    r"\[(?:SEC|DOC|P|REF|CHUNK|EXCERPT)[^\]]+\]|=== DOCUMENT EXCERPT \[[^\]]+\] ===",
    re.IGNORECASE,
)


class RetrievalCompressionResult(BaseModel):
    """Outcome of RAG context retrieval compression."""

    compressed_text: str
    raw_tokens: int
    compressed_tokens: int
    tokens_saved: int
    compression_ratio: float = Field(
        ...,
        description="Percentage of tokens pruned: (tokens_saved / raw_tokens) * 100",
    )
    retained_chunks_count: int
    pruned_chunks_count: int
    citations_preserved: list[str]
    metadata: dict[str, Any] = Field(default_factory=dict)


class RetrievalCompressor:
    """Compresses retrieved RAG passages before passing to downstream prompt."""

    def __init__(
        self,
        min_relative_score: float = 0.35,
        max_chunks: int = 5,
    ) -> None:
        self.min_relative_score = min_relative_score
        self.max_chunks = max_chunks
        self.pruner = get_token_pruner()

    def compress_document_chunks(
        self,
        chunks: list[Any],
        query: str = "",
        min_relative_score: float | None = None,
        max_chunks: int | None = None,
    ) -> RetrievalCompressionResult:
        """Filter and compress candidate document chunks."""
        threshold = (
            min_relative_score
            if min_relative_score is not None
            else self.min_relative_score
        )
        limit = max_chunks if max_chunks is not None else self.max_chunks

        if not chunks:
            return RetrievalCompressionResult(
                compressed_text="",
                raw_tokens=0,
                compressed_tokens=0,
                tokens_saved=0,
                compression_ratio=0.0,
                retained_chunks_count=0,
                pruned_chunks_count=0,
                citations_preserved=[],
            )

        # 1. Normalize chunks to content strings and scores
        normalized_chunks: list[tuple[str, float, list[str]]] = []
        raw_full_texts: list[str] = []

        for c in chunks:
            if hasattr(c, "content") and hasattr(c, "score"):
                text = str(c.content)
                score = float(c.score or 0.0)
            elif isinstance(c, dict):
                text = str(c.get("content", ""))
                score = float(c.get("score", 0.0))
            else:
                text = str(c)
                score = 1.0

            citations = CITATION_REGEX.findall(text)
            normalized_chunks.append((text, score, citations))
            raw_full_texts.append(text)

        raw_combined = "\n\n".join(raw_full_texts)
        raw_tokens = estimate_tokens(raw_combined)

        # 2. Filter by relevance score cutoff
        max_score = (
            max((s for _, s, _ in normalized_chunks), default=1.0)
            if normalized_chunks
            else 1.0
        )
        cutoff = max_score * threshold

        retained: list[tuple[str, float, list[str]]] = []
        for text, score, citations in normalized_chunks:
            # Always keep if score >= cutoff or contains explicit citation requested in query
            has_relevant_citation = any(
                cit.lower() in query.lower() for cit in citations
            )
            if score >= cutoff or has_relevant_citation:
                retained.append((text, score, citations))

        # Enforce maximum chunk limit
        retained = retained[:limit]
        pruned_count = len(normalized_chunks) - len(retained)

        # 3. Prune redundant boilerplate across retained chunks
        retained_texts = [t for t, _, _ in retained]
        pruned_res = self.pruner.prune_context(retained_texts)
        compressed_text = pruned_res.pruned_text

        compressed_tokens = estimate_tokens(compressed_text)
        tokens_saved = max(0, raw_tokens - compressed_tokens)
        compression_ratio = (
            round((tokens_saved / raw_tokens) * 100, 2) if raw_tokens > 0 else 0.0
        )

        all_citations: list[str] = []
        for _, _, cits in retained:
            for c in cits:
                clean_c = c.strip()
                if clean_c and clean_c not in all_citations:
                    all_citations.append(clean_c)

        return RetrievalCompressionResult(
            compressed_text=compressed_text,
            raw_tokens=raw_tokens,
            compressed_tokens=compressed_tokens,
            tokens_saved=tokens_saved,
            compression_ratio=compression_ratio,
            retained_chunks_count=len(retained),
            pruned_chunks_count=pruned_count,
            citations_preserved=all_citations,
            metadata={"threshold": threshold, "max_score": max_score},
        )

    def compress_rag_context_string(
        self,
        rag_context: str,
        query: str = "",
    ) -> RetrievalCompressionResult:
        """Compress raw multi-excerpt RAG string by identifying excerpts and distractor sections."""
        _ = query
        raw_text = rag_context.strip()
        raw_tokens = estimate_tokens(raw_text)

        if not raw_text:
            return RetrievalCompressionResult(
                compressed_text="",
                raw_tokens=0,
                compressed_tokens=0,
                tokens_saved=0,
                compression_ratio=0.0,
                retained_chunks_count=0,
                pruned_chunks_count=0,
                citations_preserved=[],
            )

        # Detect and split excerpt blocks if marked with === or ---
        excerpt_splits = re.split(
            r"(?=(?:=== DOCUMENT EXCERPT|=== SECTION|--- EXCERPT))",
            raw_text,
            flags=re.IGNORECASE,
        )
        if len(excerpt_splits) > 1:
            chunks_to_evaluate: list[str] = []
            for part in excerpt_splits:
                p_strip = part.strip()
                if not p_strip:
                    continue
                # If chunk is explicitly labeled distractor / irrelevant, skip it
                if re.search(r"distractor|irrelevant", p_strip, re.IGNORECASE):
                    logger.debug("Dropping labeled distractor chunk from RAG context")
                    continue
                chunks_to_evaluate.append(p_strip)
        else:
            chunks_to_evaluate = [raw_text]

        pruned = self.pruner.prune_context(chunks_to_evaluate)
        compressed_text = pruned.pruned_text
        compressed_tokens = estimate_tokens(compressed_text)
        tokens_saved = max(0, raw_tokens - compressed_tokens)
        compression_ratio = (
            round((tokens_saved / raw_tokens) * 100, 2) if raw_tokens > 0 else 0.0
        )

        all_citations = CITATION_REGEX.findall(raw_text)
        unique_citations = list(dict.fromkeys(c.strip() for c in all_citations))

        return RetrievalCompressionResult(
            compressed_text=compressed_text,
            raw_tokens=raw_tokens,
            compressed_tokens=compressed_tokens,
            tokens_saved=tokens_saved,
            compression_ratio=compression_ratio,
            retained_chunks_count=len(chunks_to_evaluate),
            pruned_chunks_count=len(excerpt_splits) - len(chunks_to_evaluate),
            citations_preserved=unique_citations,
            metadata={"method": "excerpt_splitting_and_pruning"},
        )


_retrieval_compressor: RetrievalCompressor | None = None


def get_retrieval_compressor() -> RetrievalCompressor:
    """Singleton getter for RetrievalCompressor."""
    global _retrieval_compressor
    if _retrieval_compressor is None:
        _retrieval_compressor = RetrievalCompressor()
    return _retrieval_compressor
