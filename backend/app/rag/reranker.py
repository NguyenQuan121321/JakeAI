"""Cross-Encoder and Reciprocal Rank Fusion (RRF) reranker for candidate passages."""

import logging
import re
from collections.abc import Callable
from typing import Any

from app.rag.models import DocumentChunk

logger = logging.getLogger(__name__)


class CrossEncoderReranker:
    """Reranks candidate passages using ONNX/FastEmbed Cross-Encoder or RRF heuristics."""

    def __init__(
        self,
        model_name: str | None = None,
        rrf_k: int = 60,
        cross_encoder_fn: Callable[[str, list[str]], list[float]] | None = None,
    ) -> None:
        self.model_name = model_name
        self.rrf_k = rrf_k
        self.cross_encoder_fn = cross_encoder_fn
        self._fastembed_model: Any = None
        self._fastembed_failed: bool = False

    def _get_fastembed_model(self) -> Any | None:
        """Lazily load FastEmbed TextCrossEncoder if requested and available."""
        if self._fastembed_failed or self.cross_encoder_fn is not None:
            return None
        if self._fastembed_model is not None:
            return self._fastembed_model
        if not self.model_name:
            return None

        try:
            from fastembed import (
                TextCrossEncoder,
            )

            self._fastembed_model = TextCrossEncoder(model_name=self.model_name)
            return self._fastembed_model
        except Exception as exc:
            logger.info(
                "FastEmbed cross-encoder unavailable (%s). Using calibrated heuristic RRF.",
                exc,
            )
            self._fastembed_failed = True
            return None

    def rerank(
        self,
        query: str,
        dense_results: list[DocumentChunk],
        sparse_results: list[DocumentChunk],
        top_k: int = 5,
    ) -> list[DocumentChunk]:
        """Merge, rerank, and calibrate scores across dense and sparse streams."""
        query_terms = set(re.findall(r"\b[a-zA-Z0-9_\-\$]{2,}\b", query.lower()))

        # Map chunk_id to DocumentChunk
        chunk_map: dict[str, DocumentChunk] = {}
        # Reciprocal Rank Fusion scores
        rrf_scores: dict[str, float] = {}

        # 1. Dense Stream Ranks
        for rank, chunk in enumerate(dense_results):
            cid = chunk.chunk_id
            chunk_map[cid] = chunk
            rrf_scores[cid] = rrf_scores.get(cid, 0.0) + (1.0 / (self.rrf_k + rank + 1))

        # 2. Sparse Stream Ranks
        for rank, chunk in enumerate(sparse_results):
            cid = chunk.chunk_id
            if cid not in chunk_map:
                chunk_map[cid] = chunk
            rrf_scores[cid] = rrf_scores.get(cid, 0.0) + (1.0 / (self.rrf_k + rank + 1))

        if not chunk_map:
            return []

        chunks_list = list(chunk_map.values())
        doc_texts = [c.content for c in chunks_list]

        # 3. Check for external / ONNX cross-encoder
        ce_scores: list[float] | None = None
        if self.cross_encoder_fn is not None:
            try:
                ce_scores = self.cross_encoder_fn(query, doc_texts)
            except Exception as exc:
                logger.warning("Custom cross-encoder function failed: %s", exc)

        if ce_scores is None:
            fe_model = self._get_fastembed_model()
            if fe_model is not None:
                try:
                    raw_scores = list(fe_model.rerank(query, doc_texts))
                    ce_scores = [float(s) for s in raw_scores]
                except Exception as exc:
                    logger.warning("FastEmbed reranking execution failed: %s", exc)

        # 4. Cross-Encoder Calibration (Model or Heuristic)
        reranked: list[tuple[DocumentChunk, float]] = []
        for idx, chunk in enumerate(chunks_list):
            cid = chunk.chunk_id
            base_rrf = rrf_scores.get(cid, 0.0)

            if ce_scores is not None and idx < len(ce_scores):
                # Normalized composite: 70% cross-encoder + 30% RRF rank
                ce_norm = max(0.0, min(1.0, ce_scores[idx]))
                final_score = min(1.0, (ce_norm * 0.7) + ((base_rrf * 10.0) * 0.3))
            else:
                # Calibrated Heuristic RRF fallback
                content_lower = chunk.content.lower()
                doc_terms = set(re.findall(r"\b[a-zA-Z0-9_\-\$]{2,}\b", content_lower))

                overlap_count = len(query_terms.intersection(doc_terms))
                overlap_ratio = overlap_count / max(1, len(query_terms))
                phrase_bonus = 0.2 if query.lower() in content_lower else 0.0

                numbers_in_query = set(re.findall(r"\$?\d+(?:\.\d+)?", query))
                numbers_in_doc = set(re.findall(r"\$?\d+(?:\.\d+)?", chunk.content))
                num_match = (
                    0.15
                    if numbers_in_query and numbers_in_query.issubset(numbers_in_doc)
                    else 0.0
                )

                final_score = min(
                    1.0,
                    (base_rrf * 10.0) * 0.4
                    + (overlap_ratio * 0.4)
                    + phrase_bonus
                    + num_match,
                )

            reranked_chunk = DocumentChunk(
                chunk_id=chunk.chunk_id,
                content=chunk.content,
                tenant_id=chunk.tenant_id,
                source=chunk.source,
                metadata=chunk.metadata,
                score=round(final_score, 4),
            )
            reranked.append((reranked_chunk, final_score))

        reranked.sort(key=lambda x: x[1], reverse=True)
        return [c for c, _ in reranked[:top_k]]
