"""Unit tests for TASK RAG-03 and RAG-04: Real Embeddings, Dimension Verification, and Deterministic Points."""

import os

import pytest

from app.rag.embedding import (
    DimensionMismatchError,
    TestOnlyFakeEmbeddingProvider,
    get_embedding_provider,
)
from app.rag.models import DocumentChunk
from app.rag.vector_store import QdrantVectorStore, derive_point_id


def test_fastembed_provider_dimension_and_norm() -> None:
    """Verify FastEmbed generates 384-dimensional unit vectors."""
    provider = get_embedding_provider("fastembed")
    assert provider.dimension == 384
    assert "bge-small" in provider.model_name

    text = "Enterprise AI agent architecture."
    vec = provider.embed_text(text)
    assert len(vec) == 384

    # Check L2 unit normalization: sum(x^2) ~= 1.0
    norm_sq = sum(x * x for x in vec)
    assert abs(norm_sq - 1.0) < 1e-3


def test_fastembed_batch_order_preservation() -> None:
    """Verify batch embeddings preserve exact input ordering."""
    provider = get_embedding_provider("fastembed")
    texts = [
        "First sentence about financial dividends.",
        "Second sentence about infrastructure containers.",
        "Third sentence about neural network latency.",
    ]
    batch_vecs = provider.embed_batch(texts)
    assert len(batch_vecs) == len(texts)

    indiv_vec_0 = provider.embed_text(texts[0])
    # Compare first vector from batch to individual embedding
    dot_sim = sum(a * b for a, b in zip(batch_vecs[0], indiv_vec_0, strict=True))
    assert dot_sim > 0.999


def test_test_fake_embedding_provider_guard() -> None:
    """Verify TestOnlyFakeEmbeddingProvider cannot be instantiated in production."""
    old_env = os.environ.get("ENVIRONMENT")
    try:
        os.environ["ENVIRONMENT"] = "production"
        with pytest.raises(RuntimeError, match="strictly prohibited in production"):
            TestOnlyFakeEmbeddingProvider()
    finally:
        if old_env is not None:
            os.environ["ENVIRONMENT"] = old_env
        else:
            os.environ.pop("ENVIRONMENT", None)


def test_deterministic_qdrant_point_id() -> None:
    """Verify derive_point_id produces stable UUIDv5 across calls and changes on different chunk_ids."""
    chunk1 = DocumentChunk(
        chunk_id="doc-chunk-001",
        content="Passage 1 content.",
        tenant_id="tenant-alpha",
        source="Annual Report",
        metadata={"document_id": "doc-001", "version": "1.0"},
    )
    chunk2 = DocumentChunk(
        chunk_id="doc-chunk-001",
        content="Passage 1 content updated slightly.",
        tenant_id="tenant-alpha",
        source="Annual Report",
        metadata={"document_id": "doc-001", "version": "1.0"},
    )
    chunk_other = DocumentChunk(
        chunk_id="doc-chunk-002",
        content="Passage 2 content.",
        tenant_id="tenant-alpha",
        source="Annual Report",
        metadata={"document_id": "doc-001", "version": "1.0"},
    )

    pid1 = derive_point_id(chunk1)
    pid2 = derive_point_id(chunk2)
    pid_other = derive_point_id(chunk_other)

    # Identical tenant, document_id, version, chunk_id MUST yield identical UUID
    assert pid1 == pid2
    assert len(pid1) == 36  # Standard UUID string length
    # Different chunk_id must yield different UUID
    assert pid1 != pid_other


@pytest.mark.asyncio
async def test_vector_store_dimension_mismatch_error() -> None:
    """Verify vector store raises DimensionMismatchError when collection dimension != provider dimension."""
    provider = TestOnlyFakeEmbeddingProvider(dimension=384)
    with pytest.raises(DimensionMismatchError):
        QdrantVectorStore(dimension=128, embedding_provider=provider)


@pytest.mark.asyncio
async def test_repeat_indexing_idempotent_no_duplicates() -> None:
    """Verify updating a chunk in vector store updates existing point rather than creating duplicates."""
    provider = TestOnlyFakeEmbeddingProvider(dimension=384)
    store = QdrantVectorStore(embedding_provider=provider)

    chunk = DocumentChunk(
        chunk_id="test-chunk-repeat",
        content="Initial content version 1.",
        tenant_id="tenant-repeat",
        source="Doc",
    )
    await store.upsert([chunk])

    res1 = await store.search(
        query="Initial content", tenant_id="tenant-repeat", top_k=10
    )
    assert len(res1) == 1
    assert "version 1" in res1[0].content

    # Re-index updated version of the same chunk
    updated_chunk = DocumentChunk(
        chunk_id="test-chunk-repeat",
        content="Updated content version 2.",
        tenant_id="tenant-repeat",
        source="Doc",
    )
    await store.upsert([updated_chunk])

    res2 = await store.search(
        query="Updated content", tenant_id="tenant-repeat", top_k=10
    )
    # Must still have only 1 chunk in index, updated to version 2
    assert len(res2) == 1
    assert "version 2" in res2[0].content


@pytest.mark.asyncio
async def test_vector_store_edge_cases() -> None:
    """Verify empty upserts and cosine similarity boundary conditions."""
    from app.rag.embedding import set_embedding_provider
    from app.rag.vector_store import _cosine_similarity

    provider = TestOnlyFakeEmbeddingProvider(dimension=384)
    store = QdrantVectorStore(embedding_provider=provider)

    # Empty upsert does not error
    await store.upsert([])

    # Cosine similarity boundaries
    assert _cosine_similarity([], []) == 0.0
    assert _cosine_similarity([1.0], [1.0, 2.0]) == 0.0

    # Provider reset
    set_embedding_provider(None)
    new_provider = get_embedding_provider()
    assert new_provider is not None
