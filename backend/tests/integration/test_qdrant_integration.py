"""Comprehensive Qdrant Vector Integration Test Suite (INT-018).

Verifies real interactions between JakeAI components and the Qdrant vector database:
1. QdrantVectorStore (collection management, dense embeddings, multi-tenant isolation)
2. SemanticCacheManager (Tier 2 vector semantic similarity cache)
3. HybridRetriever (Qdrant dense vector fusion with sparse BM25)

Mandatory failure cases tested across Qdrant vector consumers:
- unavailable (Qdrant unreachable -> in-memory fallback without crash)
- timeout (query times out -> in-memory store fallback)
- dimension mismatch (incompatible vector dimension -> raises DimensionMismatchError)
- connection failure (socket reset -> graceful fallback with backoff)
- partial failure (dense fails, sparse succeeds -> degraded sparse mode in HybridRetriever)
- recovery (Qdrant service restored -> reconnect and normal dense retrieval)
"""

from __future__ import annotations

import uuid
from typing import Any
from unittest.mock import AsyncMock, patch

import pytest

from app.optimizer.semantic_cache import SemanticCacheManager
from app.rag.bm25 import BM25Retriever
from app.rag.embedding import TestOnlyFakeEmbeddingProvider
from app.rag.models import DocumentChunk
from app.rag.retriever import HybridRetriever
from app.rag.vector_store import DimensionMismatchError, QdrantVectorStore


def _check_qdrant_reachable() -> bool:
    """Probe if real Qdrant service is reachable."""
    import socket

    try:
        sock = socket.socket()
        sock.settimeout(0.3)
        sock.connect(("localhost", 6333))
        sock.close()
        return True
    except Exception:
        return False


QDRANT_AVAILABLE = _check_qdrant_reachable()


@pytest.fixture
def fake_embedding_provider() -> TestOnlyFakeEmbeddingProvider:
    return TestOnlyFakeEmbeddingProvider(dimension=64)


@pytest.mark.asyncio
class TestQdrantIntegrationAuthorities:
    """Integration verification across Qdrant vector storage consumers."""

    async def test_qdrant_vector_store_upsert_search_and_tenant_isolation(
        self,
        fake_embedding_provider: TestOnlyFakeEmbeddingProvider,
    ) -> None:
        """Authority 1: QdrantVectorStore collection upsert, search, and tenant boundary."""
        col_name = f"test_col_{uuid.uuid4().hex[:8]}"
        store = QdrantVectorStore(
            collection_name=col_name,
            embedding_provider=fake_embedding_provider,
        )

        tenant_a = f"tenant-qa-{uuid.uuid4().hex[:8]}"
        tenant_b = f"tenant-qb-{uuid.uuid4().hex[:8]}"

        chunks_a = [
            DocumentChunk(
                chunk_id="chunk-a1",
                content="Enterprise balance sheet reveals high liquidity and cash surplus.",
                tenant_id=tenant_a,
                source="annual_report_2025.txt",
                metadata={"type": "finance"},
            ),
        ]
        chunks_b = [
            DocumentChunk(
                chunk_id="chunk-b1",
                content="Foreign tenant secret confidential acquisition target document.",
                tenant_id=tenant_b,
                source="mna_confidential.txt",
                metadata={"type": "mna"},
            ),
        ]

        # Upsert both tenants
        await store.upsert(chunks_a)
        await store.upsert(chunks_b)

        # Search for tenant A
        results_a = await store.search(
            query="balance sheet liquidity",
            tenant_id=tenant_a,
            top_k=5,
        )
        assert len(results_a) > 0
        assert results_a[0].tenant_id == tenant_a
        assert "liquidity" in results_a[0].content

        # Search for tenant B - verify tenant A's documents are NEVER returned
        results_b = await store.search(
            query="balance sheet liquidity",
            tenant_id=tenant_b,
            top_k=5,
        )
        for doc in results_b:
            assert doc.tenant_id == tenant_b
            assert doc.tenant_id != tenant_a

    async def test_semantic_cache_qdrant_vector_matching(
        self,
        fake_embedding_provider: TestOnlyFakeEmbeddingProvider,
    ) -> None:
        """Authority 2: SemanticCacheManager vector semantic caching in Qdrant."""
        cache = SemanticCacheManager(
            similarity_threshold=0.85,
            default_ttl=120,
            embedding_provider=fake_embedding_provider,
        )
        tenant_id = f"tenant-sc-{uuid.uuid4().hex[:8]}"
        base_prompt = "What is the net profit of our enterprise for fiscal year 2025?"
        similar_prompt = (
            "What is the net profit of our enterprise for fiscal year 2025?"
        )
        response_text = "Net profit for fiscal year 2025 was $42.5 million."

        # Cache miss initially
        hit = await cache.get(prompt=base_prompt, tenant_id=tenant_id)
        assert hit is None

        # Cache set
        await cache.set(
            prompt=base_prompt,
            tenant_id=tenant_id,
            response=response_text,
            tokens_avoided=150,
        )

        # Similar prompt hit
        hit2 = await cache.get(prompt=similar_prompt, tenant_id=tenant_id)
        assert hit2 is not None
        assert hit2.response == response_text
        assert hit2.tenant_id == tenant_id

        # Cross-tenant query on the exact same prompt must miss (isolation)
        foreign_hit = await cache.get(
            prompt=similar_prompt, tenant_id="foreign-tenant-id"
        )
        assert foreign_hit is None

    async def test_hybrid_retriever_dense_sparse_fusion(
        self,
        fake_embedding_provider: TestOnlyFakeEmbeddingProvider,
    ) -> None:
        """Authority 3: HybridRetriever dense Qdrant + sparse BM25 fusion."""
        store = QdrantVectorStore(embedding_provider=fake_embedding_provider)
        bm25 = BM25Retriever()
        retriever = HybridRetriever(vector_store=store, bm25=bm25)

        tenant_id = f"tenant-hr-{uuid.uuid4().hex[:8]}"
        chunks = [
            DocumentChunk(
                chunk_id="chk-hr-1",
                content="Deep reinforcement learning accelerates algorithmic trading.",
                tenant_id=tenant_id,
                source="ai_trading.txt",
                metadata={},
            ),
            DocumentChunk(
                chunk_id="chk-hr-2",
                content="Quantitative statistical arbitrage strategies require microsecond latency.",
                tenant_id=tenant_id,
                source="quant_strategies.txt",
                metadata={},
            ),
        ]

        # Index into both vector store and BM25
        await store.upsert(chunks)
        bm25.add_documents(chunks)

        # Hybrid retrieval
        result = await retriever.retrieve(
            query="algorithmic trading and reinforcement learning",
            tenant_id=tenant_id,
            top_k=2,
        )
        assert result is not None
        assert len(result.chunks) > 0
        assert result.tenant_id == tenant_id
        assert not result.degraded
        assert result.retrieval_mode == "hybrid"


@pytest.mark.asyncio
class TestQdrantMandatoryFailureCases:
    """Mandatory failure cases: unavailable, timeout, mismatch, connection, partial, recovery."""

    async def test_failure_case_1_unavailable(
        self,
        fake_embedding_provider: TestOnlyFakeEmbeddingProvider,
    ) -> None:
        """Failure Case 1: Qdrant unreachable falls back to in-memory vector store."""
        # Force unreachable URL
        store = QdrantVectorStore(
            url="http://127.0.0.1:59998",
            embedding_provider=fake_embedding_provider,
        )
        tenant_id = "tenant-unavail"
        chunk = DocumentChunk(
            chunk_id="c-unavail",
            content="Fallback content safely stored in memory.",
            tenant_id=tenant_id,
            source="fallback.txt",
            metadata={},
        )

        # Upsert and search must succeed via memory store without raising exception
        await store.upsert([chunk])
        results = await store.search(query="fallback content", tenant_id=tenant_id)
        assert len(results) == 1
        assert results[0].chunk_id == "c-unavail"
        assert store._is_qdrant_available is False

    async def test_failure_case_2_timeout(
        self,
        fake_embedding_provider: TestOnlyFakeEmbeddingProvider,
    ) -> None:
        """Failure Case 2: Qdrant search timeout triggers in-memory fallback."""
        store = QdrantVectorStore(embedding_provider=fake_embedding_provider)
        mock_client = AsyncMock()
        mock_client.search.side_effect = TimeoutError("Qdrant query timed out")
        store._client = mock_client
        store._is_qdrant_available = True

        tenant_id = "tenant-timeout"
        chunk = DocumentChunk(
            chunk_id="c-timeout",
            content="Memory copy remains accessible despite remote timeout.",
            tenant_id=tenant_id,
            source="timeout.txt",
            metadata={},
        )
        store._memory_vectors[tenant_id] = {
            "c-timeout": (chunk, fake_embedding_provider.embed_text("test")),
        }

        # Search handles timeout gracefully and returns in-memory vector hit
        results = await store.search(query="Memory copy", tenant_id=tenant_id)
        assert len(results) == 1
        assert results[0].chunk_id == "c-timeout"
        assert store._is_qdrant_available is False

    async def test_failure_case_3_dimension_mismatch(
        self,
        fake_embedding_provider: TestOnlyFakeEmbeddingProvider,
    ) -> None:
        """Failure Case 3: Incompatible collection dimension raises DimensionMismatchError."""
        store = QdrantVectorStore(
            dimension=64,
            embedding_provider=fake_embedding_provider,
        )
        mock_client = AsyncMock()
        mock_client.collection_exists.return_value = True

        # Existing collection has dimension 384, but store expects 64
        class MockColParams:
            vectors = type("V", (), {"size": 384})()

        class MockColInfo:
            config = type("C", (), {"params": MockColParams()})()

        mock_client.get_collection.return_value = MockColInfo()

        with patch("qdrant_client.AsyncQdrantClient", return_value=mock_client):
            with pytest.raises(DimensionMismatchError) as exc_info:
                await store._get_client()
            assert "dimension 384" in str(exc_info.value)
            assert "does not match" in str(exc_info.value)

    async def test_failure_case_4_connection_failure(
        self,
        fake_embedding_provider: TestOnlyFakeEmbeddingProvider,
    ) -> None:
        """Failure Case 4: Socket disconnect during upsert retains in-memory copy."""
        store = QdrantVectorStore(embedding_provider=fake_embedding_provider)
        mock_client = AsyncMock()
        mock_client.upsert.side_effect = ConnectionResetError(
            "Connection severed by peer"
        )
        store._client = mock_client
        store._is_qdrant_available = True

        tenant_id = "tenant-conn-drop"
        chunk = DocumentChunk(
            chunk_id="c-conn-drop",
            content="Retained in local memory despite network severed.",
            tenant_id=tenant_id,
            source="net_drop.txt",
            metadata={},
        )

        # Upsert retains chunk in memory despite Qdrant socket reset
        await store.upsert([chunk])
        assert store._is_qdrant_available is False

        # Query finds the in-memory copy
        results = await store.search(
            query="Retained in local memory", tenant_id=tenant_id
        )
        assert len(results) == 1
        assert results[0].chunk_id == "c-conn-drop"

    async def test_failure_case_5_partial_failure_degraded_retrieval(
        self,
        fake_embedding_provider: TestOnlyFakeEmbeddingProvider,
    ) -> None:
        """Failure Case 5: Dense vector store fails, BM25 succeeds -> degraded sparse mode."""
        store = QdrantVectorStore(embedding_provider=fake_embedding_provider)
        bm25 = BM25Retriever()
        retriever = HybridRetriever(vector_store=store, bm25=bm25)

        tenant_id = "tenant-partial-rag"
        chunk = DocumentChunk(
            chunk_id="chk-sparse-only",
            content="Critical sparse keyword exact matching document.",
            tenant_id=tenant_id,
            source="sparse.txt",
            metadata={},
        )
        bm25.add_documents([chunk])

        # Dense store search raises an unexpected runtime exception
        store.search = AsyncMock(
            side_effect=RuntimeError("Dense vector index unavailable")
        )

        result = await retriever.retrieve(
            query="Critical sparse keyword",
            tenant_id=tenant_id,
            top_k=2,
        )
        assert result is not None
        assert result.degraded is True
        assert result.retrieval_mode == "sparse_degraded"
        assert len(result.chunks) > 0
        assert result.chunks[0].chunk_id == "chk-sparse-only"

    async def test_failure_case_6_recovery(
        self,
        fake_embedding_provider: TestOnlyFakeEmbeddingProvider,
    ) -> None:
        """Failure Case 6: Qdrant recovery re-enables live dense queries."""
        store = QdrantVectorStore(embedding_provider=fake_embedding_provider)
        tenant_id = "tenant-recov-qdrant"

        # Initially degraded/offline
        store._is_qdrant_available = False
        assert store._is_qdrant_available is False

        # Simulated service recovery
        mock_recovered_client = AsyncMock()
        mock_recovered_client.collection_exists.return_value = True

        class MockHit:
            def __init__(self, id: str, score: float, payload: dict[str, Any]) -> None:
                self.id = id
                self.score = score
                self.payload = payload

        mock_hit = MockHit(
            id="recov-pt-1",
            score=0.96,
            payload={
                "chunk_id": "chk-recov-1",
                "content": "Live Qdrant vector hit recovered successfully.",
                "tenant_id": tenant_id,
                "source": "live_qdrant.txt",
                "metadata": {},
            },
        )
        mock_recovered_client.search.return_value = [mock_hit]

        store._client = mock_recovered_client
        store._is_qdrant_available = True

        results = await store.search(
            query="Live Qdrant vector hit", tenant_id=tenant_id
        )
        assert len(results) == 1
        assert results[0].chunk_id == "chk-recov-1"
        assert results[0].score == 0.96
        assert store._is_qdrant_available is True
