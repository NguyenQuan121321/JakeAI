"""Unit tests for TASK RAG-06: Concurrency, Degraded Mode, 3x Candidate Pool, and Deterministic Tie-Breaking."""

import pytest

from app.rag.bm25 import BM25Retriever
from app.rag.embedding import TestOnlyFakeEmbeddingProvider
from app.rag.models import DocumentChunk
from app.rag.retriever import HybridRetriever
from app.rag.vector_store import QdrantVectorStore


class FailingVectorStore(QdrantVectorStore):
    """Vector store subclass that raises an exception on search to test degraded mode."""

    async def search(
        self, query: str, tenant_id: str, top_k: int = 5
    ) -> list[DocumentChunk]:
        raise RuntimeError("Simulated Qdrant cluster network timeout")


@pytest.mark.asyncio
async def test_hybrid_retrieval_concurrent_success() -> None:
    """Verify normal concurrent hybrid retrieval returns mode='hybrid' and degraded=False."""
    provider = TestOnlyFakeEmbeddingProvider(dimension=384)
    vstore = QdrantVectorStore(embedding_provider=provider)
    bm25 = BM25Retriever()
    retriever = HybridRetriever(vector_store=vstore, bm25=bm25)

    tenant = "tenant-hybrid"
    chunks = [
        DocumentChunk(
            chunk_id="h1",
            content="Financial performance in APAC region.",
            tenant_id=tenant,
            source="APAC",
        ),
        DocumentChunk(
            chunk_id="h2",
            content="Financial performance in EMEA region.",
            tenant_id=tenant,
            source="EMEA",
        ),
    ]
    await retriever.index_documents(chunks)

    res = await retriever.retrieve(
        query="Financial performance APAC", tenant_id=tenant, top_k=2
    )

    assert res.retrieval_mode == "hybrid"
    assert res.degraded is False
    assert res.dense_candidate_count > 0
    assert res.sparse_candidate_count > 0
    assert len(res.chunks) > 0


@pytest.mark.asyncio
async def test_hybrid_retrieval_degraded_mode_on_dense_failure() -> None:
    """Verify degraded mode fallback to sparse when vector store fails, without raising exception."""
    provider = TestOnlyFakeEmbeddingProvider(dimension=384)
    vstore = FailingVectorStore(embedding_provider=provider)
    bm25 = BM25Retriever()
    retriever = HybridRetriever(vector_store=vstore, bm25=bm25)

    tenant = "tenant-degraded"
    chunks = [
        DocumentChunk(
            chunk_id="d1",
            content="Quarterly revenue reached 100 million.",
            tenant_id=tenant,
            source="Rev",
        ),
    ]
    # Add to BM25 directly
    bm25.add_documents(chunks)

    res = await retriever.retrieve(query="Quarterly revenue", tenant_id=tenant, top_k=2)

    assert res.retrieval_mode == "sparse_degraded"
    assert res.degraded is True
    assert res.dense_candidate_count == 0
    assert res.sparse_candidate_count >= 1
    assert len(res.chunks) == 1
    assert res.chunks[0].chunk_id == "d1"


@pytest.mark.asyncio
async def test_deterministic_tie_breaking_by_chunk_id() -> None:
    """Verify chunks with equal relevance score sort deterministically by chunk_id."""
    from app.rag.reranker import CrossEncoderReranker

    # Dummy reranker returning equal scores
    def flat_score_fn(query: str, doc_texts: list[str]) -> list[float]:
        return [0.75] * len(doc_texts)

    reranker = CrossEncoderReranker(cross_encoder_fn=flat_score_fn)

    dense = [
        DocumentChunk(
            chunk_id="chunk-z",
            content="Content Z",
            tenant_id="t1",
            source="Z",
            score=0.5,
        ),
        DocumentChunk(
            chunk_id="chunk-a",
            content="Content A",
            tenant_id="t1",
            source="A",
            score=0.5,
        ),
        DocumentChunk(
            chunk_id="chunk-m",
            content="Content M",
            tenant_id="t1",
            source="M",
            score=0.5,
        ),
    ]

    reranked = reranker.rerank(
        query="test", dense_results=dense, sparse_results=[], top_k=3
    )

    # All scores are equal; therefore chunk_ids must be ascending: 'chunk-a', 'chunk-m', 'chunk-z'
    assert [c.chunk_id for c in reranked] == ["chunk-a", "chunk-m", "chunk-z"]
