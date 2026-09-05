"""BM25 sparse keyword retrieval engine with strict multi-tenant isolation."""

import math
import re
from collections import Counter

from app.rag.models import DocumentChunk


def _tokenize(text: str) -> list[str]:
    """Tokenize and normalize text into clean alphanumeric terms."""
    return re.findall(r"\b[a-zA-Z0-9_\-\$]{2,}\b", text.lower())


class BM25Retriever:
    """In-memory BM25 sparse keyword retriever with tenant-scoped inverted index."""

    def __init__(self, k1: float = 1.5, b: float = 0.75) -> None:
        self.k1 = k1
        self.b = b
        # tenant_id -> list of DocumentChunk
        self._corpus: dict[str, list[DocumentChunk]] = {}
        # tenant_id -> chunk_id -> Counter(token -> count)
        self._term_freqs: dict[str, dict[str, Counter[str]]] = {}
        # tenant_id -> token -> doc_count
        self._doc_freqs: dict[str, dict[str, int]] = {}
        # tenant_id -> chunk_id -> length
        self._doc_lengths: dict[str, dict[str, int]] = {}
        # tenant_id -> avg_doc_length
        self._avg_lengths: dict[str, float] = {}

    def add_documents(self, chunks: list[DocumentChunk]) -> None:
        """Index a batch of document chunks partitioned strictly per tenant."""
        for chunk in chunks:
            tenant = chunk.tenant_id
            if tenant not in self._corpus:
                self._corpus[tenant] = []
                self._term_freqs[tenant] = {}
                self._doc_freqs[tenant] = {}
                self._doc_lengths[tenant] = {}

            tokens = _tokenize(chunk.content)
            cid = chunk.chunk_id
            tf = Counter(tokens)

            # Check if chunk already exists to prevent duplicate counting
            existing_idx = next(
                (i for i, c in enumerate(self._corpus[tenant]) if c.chunk_id == cid),
                None,
            )
            if existing_idx is not None:
                self._corpus[tenant][existing_idx] = chunk
            else:
                self._corpus[tenant].append(chunk)

            self._term_freqs[tenant][cid] = tf
            self._doc_lengths[tenant][cid] = len(tokens)

            for token in set(tokens):
                self._doc_freqs[tenant][token] = (
                    self._doc_freqs[tenant].get(token, 0) + 1
                )

        # Update average doc length per tenant
        for tenant, lengths in self._doc_lengths.items():
            if lengths:
                self._avg_lengths[tenant] = sum(lengths.values()) / len(lengths)
            else:
                self._avg_lengths[tenant] = 0.0

    def search(
        self,
        query: str,
        tenant_id: str,
        top_k: int = 5,
    ) -> list[DocumentChunk]:
        """Perform sparse BM25 scoring against tenant-isolated corpus."""
        if tenant_id not in self._corpus or not self._corpus[tenant_id]:
            return []

        query_tokens = _tokenize(query)
        if not query_tokens:
            return []

        tenant_chunks = self._corpus[tenant_id]
        total_docs = len(tenant_chunks)
        avgdl = self._avg_lengths.get(tenant_id, 1.0)
        scores: list[tuple[DocumentChunk, float]] = []

        for chunk in tenant_chunks:
            cid = chunk.chunk_id
            tf = self._term_freqs[tenant_id].get(cid, Counter())
            doc_len = self._doc_lengths[tenant_id].get(cid, 0)

            score = 0.0
            for token in query_tokens:
                if token not in tf:
                    continue

                freq = tf[token]
                doc_freq = self._doc_freqs[tenant_id].get(token, 0)

                # Robertson-Spärck Jones BM25 IDF formulation
                idf = math.log(1.0 + (total_docs - doc_freq + 0.5) / (doc_freq + 0.5))

                # BM25 term saturation & document length normalization
                numerator = freq * (self.k1 + 1.0)
                denominator = freq + self.k1 * (
                    1.0 - self.b + self.b * (doc_len / avgdl)
                )
                score += idf * (numerator / max(1e-6, denominator))

            if score > 0.0:
                chunk_copy = DocumentChunk(
                    chunk_id=chunk.chunk_id,
                    content=chunk.content,
                    tenant_id=chunk.tenant_id,
                    source=chunk.source,
                    metadata=chunk.metadata,
                    score=round(score, 4),
                )
                scores.append((chunk_copy, score))

        scores.sort(key=lambda x: x[1], reverse=True)
        return [c for c, _ in scores[:top_k]]
