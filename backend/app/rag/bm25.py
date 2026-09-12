"""BM25 sparse keyword retrieval engine with strict multi-tenant isolation."""

from __future__ import annotations

import json
import logging
import math
import re
from collections import Counter
from pathlib import Path
from typing import Any

from app.core.config import get_settings
from app.rag.models import DocumentChunk

logger = logging.getLogger(__name__)


def _tokenize(text: str) -> list[str]:
    """Tokenize and normalize text into clean alphanumeric terms."""
    return re.findall(r"\b[a-zA-Z0-9_\-\$]{2,}\b", text.lower())


class BM25Retriever:
    """In-memory BM25 sparse keyword retriever with tenant-scoped inverted index and disk persistence."""

    def __init__(
        self,
        k1: float = 1.5,
        b: float = 0.75,
        storage_path: str | Path | None = None,
        auto_save: bool = True,
    ) -> None:
        self.k1 = k1
        self.b = b
        settings = get_settings()
        self.storage_path = Path(storage_path or settings.BM25_STORAGE_PATH)
        self.auto_save = auto_save
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

        if self.storage_path.is_file():
            self.load_from_disk()

    def clear(self, tenant_id: str | None = None) -> None:
        """Clear index state for a specific tenant or the entire index."""
        if tenant_id:
            self._corpus.pop(tenant_id, None)
            self._term_freqs.pop(tenant_id, None)
            self._doc_freqs.pop(tenant_id, None)
            self._doc_lengths.pop(tenant_id, None)
            self._avg_lengths.pop(tenant_id, None)
        else:
            self._corpus.clear()
            self._term_freqs.clear()
            self._doc_freqs.clear()
            self._doc_lengths.clear()
            self._avg_lengths.clear()
        if self.auto_save and self.storage_path.is_file():
            self.save_to_disk()

    def add_documents(self, chunks: list[DocumentChunk]) -> None:
        """Index a batch of document chunks partitioned strictly per tenant."""
        for chunk in chunks:
            tenant = chunk.tenant_id
            if tenant not in self._corpus:
                self._corpus[tenant] = []
                self._term_freqs[tenant] = {}
                self._doc_freqs[tenant] = {}
                self._doc_lengths[tenant] = {}

            cid = chunk.chunk_id
            tokens = _tokenize(chunk.content)
            tf = Counter(tokens)

            # Fix re-indexing defect: decrement old document frequency counts if chunk exists
            old_tf = self._term_freqs[tenant].get(cid)
            if old_tf is not None:
                for old_token in old_tf:
                    if old_token in self._doc_freqs[tenant]:
                        self._doc_freqs[tenant][old_token] -= 1
                        if self._doc_freqs[tenant][old_token] <= 0:
                            del self._doc_freqs[tenant][old_token]

            # Update or append chunk in corpus
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

        if self.auto_save and chunks:
            self.save_to_disk()

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
            # Strict tenant boundary verification
            if chunk.tenant_id != tenant_id:
                continue

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
                    metadata=chunk.metadata.copy(),
                    score=round(score, 4),
                )
                scores.append((chunk_copy, score))

        # Deterministic sorting: score descending, chunk_id ascending
        scores.sort(key=lambda x: (-x[1], x[0].chunk_id))
        return [c for c, _ in scores[:top_k]]

    def save_to_disk(self, filepath: str | Path | None = None) -> None:
        """Persist BM25 state to disk."""
        target = Path(filepath or self.storage_path)
        target.parent.mkdir(parents=True, exist_ok=True)

        data: dict[str, Any] = {
            "version": "1.0",
            "k1": self.k1,
            "b": self.b,
            "corpus": {
                tenant: [c.model_dump() for c in chunks]
                for tenant, chunks in self._corpus.items()
            },
            "term_freqs": {
                tenant: {cid: dict(counter) for cid, counter in cids.items()}
                for tenant, cids in self._term_freqs.items()
            },
            "doc_freqs": self._doc_freqs,
            "doc_lengths": self._doc_lengths,
            "avg_lengths": self._avg_lengths,
        }

        temp_target = target.with_suffix(".tmp")
        with open(temp_target, "w", encoding="utf-8") as f:
            json.dump(data, f, indent=2)
        temp_target.replace(target)
        logger.info("Saved BM25 sparse index to %s", target)

    def load_from_disk(self, filepath: str | Path | None = None) -> bool:
        """Load BM25 state from disk if available."""
        target = Path(filepath or self.storage_path)
        if not target.is_file():
            return False

        try:
            with open(target, encoding="utf-8") as f:
                data = json.load(f)

            self.k1 = data.get("k1", self.k1)
            self.b = data.get("b", self.b)

            self._corpus = {
                tenant: [DocumentChunk(**c) for c in chunks]
                for tenant, chunks in data.get("corpus", {}).items()
            }
            self._term_freqs = {
                tenant: {cid: Counter(counts) for cid, counts in cids.items()}
                for tenant, cids in data.get("term_freqs", {}).items()
            }
            self._doc_freqs = data.get("doc_freqs", {})
            self._doc_lengths = data.get("doc_lengths", {})
            self._avg_lengths = data.get("avg_lengths", {})
            logger.info("Loaded BM25 sparse index from %s", target)
            return True
        except Exception as exc:
            logger.warning("Failed to load BM25 index from %s: %s", target, exc)
            return False
