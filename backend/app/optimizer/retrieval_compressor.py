"""Layer 4: RAG Retrieval Compression Engine for JakeAI Platform.

DEPRECATION NOTICE:
RetrievalCompressor is deprecated in favor of ContextSelector in app.rag.context_selector,
which serves as the single canonical authority for RAG context selection and compression.
This module is retained for backwards compatibility.
"""

from __future__ import annotations

import logging
import warnings
from typing import TYPE_CHECKING, Any

if TYPE_CHECKING:
    from app.optimizer.token_pruner import HeuristicTokenPruner
    from app.rag.context_selector import ContextSelector

from app.rag.context_selector import (
    CITATION_TAG_REGEX as CITATION_REGEX,
)
from app.rag.context_selector import (
    get_context_selector,
)
from app.rag.models import RetrievalCompressionResult

logger = logging.getLogger(__name__)

__all__ = [
    "CITATION_REGEX",
    "RetrievalCompressionResult",
    "RetrievalCompressor",
    "get_retrieval_compressor",
]


class RetrievalCompressor:
    """Deprecated: Use ContextSelector in app.rag.context_selector instead.

    Delegates all calls directly to the canonical ContextSelector.
    """

    def __init__(
        self,
        min_relative_score: float = 0.35,
        max_chunks: int = 5,
        selector: ContextSelector | None = None,
    ) -> None:
        self.min_relative_score = min_relative_score
        self.max_chunks = max_chunks
        self._selector = selector or get_context_selector()

    @property
    def pruner(self) -> HeuristicTokenPruner:
        """Backwards-compatible accessor for token pruner."""
        return self._selector.pruner

    def compress_document_chunks(
        self,
        chunks: list[Any],
        query: str = "",
        min_relative_score: float | None = None,
        max_chunks: int | None = None,
    ) -> RetrievalCompressionResult:
        """Filter and compress candidate document chunks (delegates to ContextSelector)."""
        warnings.warn(
            "RetrievalCompressor is deprecated. Use ContextSelector from app.rag.context_selector.",
            DeprecationWarning,
            stacklevel=2,
        )
        return self._selector.compress_document_chunks(
            chunks=chunks,
            query=query,
            min_relative_score=(
                min_relative_score
                if min_relative_score is not None
                else self.min_relative_score
            ),
            max_chunks=(max_chunks if max_chunks is not None else self.max_chunks),
        )

    def compress_rag_context_string(
        self,
        rag_context: str,
        query: str = "",
    ) -> RetrievalCompressionResult:
        """Compress raw multi-excerpt RAG string (delegates to ContextSelector)."""
        warnings.warn(
            "RetrievalCompressor is deprecated. Use ContextSelector from app.rag.context_selector.",
            DeprecationWarning,
            stacklevel=2,
        )
        return self._selector.compress_rag_context_string(
            rag_context=rag_context,
            query=query,
        )


_retrieval_compressor: RetrievalCompressor | None = None


def get_retrieval_compressor() -> RetrievalCompressor:
    """Singleton getter for RetrievalCompressor (deprecated)."""
    global _retrieval_compressor
    if _retrieval_compressor is None:
        _retrieval_compressor = RetrievalCompressor()
    return _retrieval_compressor
