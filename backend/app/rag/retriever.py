"""Unified Hybrid Retriever for Qdrant vector search and BM25 sparse retrieval."""

import time

from app.rag.bm25 import BM25Retriever
from app.rag.models import DocumentChunk, RetrievalResult
from app.rag.reranker import CrossEncoderReranker
from app.rag.vector_store import QdrantVectorStore


class HybridRetriever:
    """Enterprise hybrid retrieval engine with strict multi-tenant isolation."""

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
        self.bm25.add_documents(chunks)
        await self.vector_store.upsert(chunks)

    async def retrieve(
        self,
        query: str,
        tenant_id: str,
        top_k: int = 5,
        candidate_pool: int = 15,
    ) -> RetrievalResult:
        """Execute parallel hybrid retrieval, enforce tenant filter, and rerank."""
        start_time = time.time()

        # 1. Parallel dense and sparse search strictly bounded to tenant_id
        dense_candidates = await self.vector_store.search(
            query=query,
            tenant_id=tenant_id,
            top_k=candidate_pool,
        )
        sparse_candidates = self.bm25.search(
            query=query,
            tenant_id=tenant_id,
            top_k=candidate_pool,
        )

        # 2. Strict Tenant Boundary Filter Guardrail
        valid_dense = [c for c in dense_candidates if c.tenant_id == tenant_id]
        valid_sparse = [c for c in sparse_candidates if c.tenant_id == tenant_id]
        total_candidates = len(valid_dense) + len(valid_sparse)

        # 3. Cross-Encoder / RRF Reranking
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
        )


default_hybrid_retriever = HybridRetriever()
