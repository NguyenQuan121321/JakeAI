"""Cross-Encoder and Reciprocal Rank Fusion (RRF) reranker for candidate passages."""

import re

from app.rag.models import DocumentChunk


class CrossEncoderReranker:
    """Reranks candidate passages using RRF and cross-attention heuristics."""

    def __init__(self, rrf_k: int = 60) -> None:
        self.rrf_k = rrf_k

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

        # 3. Cross-Encoder Relevance Calibration
        reranked: list[tuple[DocumentChunk, float]] = []
        for cid, chunk in chunk_map.items():
            base_rrf = rrf_scores.get(cid, 0.0)
            content_lower = chunk.content.lower()
            doc_terms = set(re.findall(r"\b[a-zA-Z0-9_\-\$]{2,}\b", content_lower))

            # Term overlap ratio
            overlap_count = len(query_terms.intersection(doc_terms))
            overlap_ratio = overlap_count / max(1, len(query_terms))

            # Phrase match bonus
            phrase_bonus = 0.2 if query.lower() in content_lower else 0.0

            # Numerical claim match bonus
            numbers_in_query = set(re.findall(r"\$?\d+(?:\.\d+)?", query))
            numbers_in_doc = set(re.findall(r"\$?\d+(?:\.\d+)?", chunk.content))
            num_match = (
                0.15
                if numbers_in_query and numbers_in_query.issubset(numbers_in_doc)
                else 0.0
            )

            # Composite cross-encoder score (normalized to 0.0 - 1.0)
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
