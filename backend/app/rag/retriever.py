"""Unified Hybrid Retriever for Qdrant vector search and BM25 sparse retrieval."""

from __future__ import annotations

import asyncio
import logging
import time

from app.rag.bm25 import BM25Retriever
from app.rag.models import DocumentChunk, RetrievalResult
from app.rag.reranker import CrossEncoderReranker
from app.rag.vector_store import QdrantVectorStore

logger = logging.getLogger(__name__)


class HybridRetriever:
    """Enterprise hybrid retrieval engine with strict multi-tenant isolation and graceful degradation."""

    def __init__(
        self,
        vector_store: QdrantVectorStore | None = None,
        bm25: BM25Retriever | None = None,
        reranker: CrossEncoderReranker | None = None,
    ) -> None:
        self.vector_store = vector_store or QdrantVectorStore()
        self.bm25 = bm25 or BM25Retriever()
        self.reranker = reranker or CrossEncoderReranker()

    async def index_documents(self, chunks: list[DocumentChunk]) -> None:
        """Index document chunks into both dense vector store and sparse BM25 index."""
        if not chunks:
            return
        self.bm25.add_documents(chunks)
        await self.vector_store.upsert(chunks)

    async def retrieve(
        self,
        query: str,
        tenant_id: str,
        top_k: int = 5,
        candidate_pool: int | None = None,
    ) -> RetrievalResult:
        """Execute concurrent hybrid retrieval, enforce tenant filter, and rerank."""
        start_time = time.time()
        pool_size = candidate_pool if candidate_pool is not None else max(15, 3 * top_k)

        # 1. Concurrent dense and sparse search strictly bounded to tenant_id
        async def _run_sparse() -> list[DocumentChunk]:
            return await asyncio.to_thread(
                self.bm25.search, query, tenant_id, pool_size
            )

        dense_task = self.vector_store.search(
            query=query, tenant_id=tenant_id, top_k=pool_size
        )
        sparse_task = _run_sparse()

        results = await asyncio.gather(dense_task, sparse_task, return_exceptions=True)
        dense_res, sparse_res = results[0], results[1]

        dense_failed = isinstance(dense_res, Exception)
        sparse_failed = isinstance(sparse_res, Exception)

        if dense_failed:
            logger.warning("Dense vector search failed: %s", dense_res)
            dense_candidates: list[DocumentChunk] = []
        else:
            dense_candidates = dense_res  # type: ignore[assignment]

        if sparse_failed:
            logger.warning("Sparse BM25 search failed: %s", sparse_res)
            sparse_candidates: list[DocumentChunk] = []
        else:
            sparse_candidates = sparse_res  # type: ignore[assignment]

        # Determine retrieval mode and degradation telemetry
        if dense_failed and not sparse_failed:
            retrieval_mode = "sparse_degraded"
            degraded = True
        elif sparse_failed and not dense_failed:
            retrieval_mode = "dense_degraded"
            degraded = True
        elif dense_failed and sparse_failed:
            retrieval_mode = "failed"
            degraded = True
        else:
            retrieval_mode = "hybrid"
            degraded = False

        # 2. Defense-in-depth Tenant Boundary Filter Guardrail
        valid_dense = [c for c in dense_candidates if c.tenant_id == tenant_id]
        valid_sparse = [c for c in sparse_candidates if c.tenant_id == tenant_id]

        dense_count = len(valid_dense)
        sparse_count = len(valid_sparse)
        total_candidates = dense_count + sparse_count

        # 3. Cross-Encoder / RRF Reranking with deterministic tie-breaking
        reranked_chunks = self.reranker.rerank(
            query=query,
            dense_results=valid_dense,
            sparse_results=valid_sparse,
            top_k=top_k,
        )

        latency_ms = round((time.time() - start_time) * 1000, 2)

        return RetrievalResult(
            query=query,
            tenant_id=tenant_id,
            chunks=reranked_chunks,
            total_candidates=total_candidates,
            latency_ms=latency_ms,
            retrieval_mode=retrieval_mode,
            degraded=degraded,
            dense_candidate_count=dense_count,
            sparse_candidate_count=sparse_count,
        )


default_hybrid_retriever = HybridRetriever()


def get_hybrid_retriever() -> HybridRetriever:
    """Singleton getter for HybridRetriever."""
    global default_hybrid_retriever
    return default_hybrid_retriever
