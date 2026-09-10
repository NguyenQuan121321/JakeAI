"""Cross-Encoder and Reciprocal Rank Fusion (RRF) reranker for candidate passages."""

from __future__ import annotations

import logging
import math
import re
from typing import TYPE_CHECKING, Any

if TYPE_CHECKING:
    from collections.abc import Callable

from app.core.config import get_settings
from app.rag.models import DocumentChunk

logger = logging.getLogger(__name__)


def _sigmoid(x: float) -> float:
    """Map real-valued cross-encoder logit into [0.0, 1.0] probability range."""
    try:
        return 1.0 / (1.0 + math.exp(-x))
    except OverflowError:
        return 0.0 if x < 0 else 1.0


class CrossEncoderReranker:
    """Reranks candidate passages using ONNX/FastEmbed Cross-Encoder or calibrated RRF heuristics."""

    def __init__(
        self,
        model_name: str | None = None,
        rrf_k: int = 60,
        cross_encoder_fn: Callable[[str, list[str]], list[float]] | None = None,
        enabled: bool = True,
    ) -> None:
        settings = get_settings()
        self.model_name = (
            model_name if model_name is not None else settings.RERANKER_MODEL
        )
        self.rrf_k = rrf_k
        self.cross_encoder_fn = cross_encoder_fn
        self.enabled = enabled
        self._fastembed_model: Any = None
        self._fastembed_failed: bool = False
        self.last_reranker_type: str = "none"

    def _get_fastembed_model(self) -> Any | None:
        """Lazily load FastEmbed TextCrossEncoder if requested and available."""
        if (
            not self.enabled
            or self._fastembed_failed
            or self.cross_encoder_fn is not None
        ):
            return None
        if self._fastembed_model is not None:
            return self._fastembed_model
        if not self.model_name:
            return None

        try:
            from fastembed.rerank.cross_encoder import TextCrossEncoder

            self._fastembed_model = TextCrossEncoder(model_name=self.model_name)
            logger.info("Initialized FastEmbed Cross-Encoder: %s", self.model_name)
            return self._fastembed_model
        except Exception as exc:
            logger.info(
                "FastEmbed cross-encoder unavailable (%s). Using calibrated fallback heuristic.",
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
            self.last_reranker_type = "empty"
            return []

        chunks_list = list(chunk_map.values())
        doc_texts = [c.content for c in chunks_list]

        # 3. Evaluate Cross-Encoder (Custom FN or FastEmbed)
        ce_scores: list[float] | None = None
        reranker_type = "fallback"

        if self.cross_encoder_fn is not None:
            try:
                ce_scores = self.cross_encoder_fn(query, doc_texts)
                reranker_type = "custom_fn"
            except Exception as exc:
                logger.warning("Custom cross-encoder function failed: %s", exc)

        if ce_scores is None:
            fe_model = self._get_fastembed_model()
            if fe_model is not None:
                try:
                    raw_scores = list(fe_model.rerank(query, doc_texts))
                    ce_scores = [_sigmoid(float(s)) for s in raw_scores]
                    reranker_type = "cross_encoder"
                except Exception as exc:
                    logger.warning("FastEmbed reranking execution failed: %s", exc)

        self.last_reranker_type = reranker_type

        # 4. Calibrated Scoring
        reranked: list[tuple[DocumentChunk, float]] = []
        max_possible_rrf = 2.0 / (self.rrf_k + 1)

        for idx, chunk in enumerate(chunks_list):
            cid = chunk.chunk_id
            base_rrf = rrf_scores.get(cid, 0.0)

            if ce_scores is not None and idx < len(ce_scores):
                # Pure cross-encoder semantic score in [0.0, 1.0]
                final_score = max(0.0, min(1.0, ce_scores[idx]))
            else:
                # Calibrated Heuristic Fallback
                rrf_norm = (
                    min(1.0, base_rrf / max_possible_rrf)
                    if max_possible_rrf > 0
                    else 0.0
                )
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
                    (rrf_norm * 0.4) + (overlap_ratio * 0.4) + phrase_bonus + num_match,
                )

            reranked_chunk = DocumentChunk(
                chunk_id=chunk.chunk_id,
                content=chunk.content,
                tenant_id=chunk.tenant_id,
                source=chunk.source,
                metadata=chunk.metadata.copy(),
                score=round(final_score, 4),
            )
            reranked.append((reranked_chunk, final_score))

        # Deterministic sorting: score descending, chunk_id ascending
        reranked.sort(key=lambda x: (-x[1], x[0].chunk_id))
        return [c for c, _ in reranked[:top_k]]
