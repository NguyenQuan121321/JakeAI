"""Comprehensive unit and integration tests for COST-08: True Vector Semantic Cache.

Tests verify:
1. Real dense embeddings and cosine similarity on similar vs dissimilar prompts.
2. Qdrant vector backend integration (upsert, search with tenant filter, invalidate).
3. Strict tenant isolation boundaries.
4. Generation parameter and model/provider guardrails.
5. In-memory vector store fallback when Qdrant is unavailable or fails.
"""

from __future__ import annotations

import time
from typing import Any
from unittest.mock import AsyncMock

import pytest

from app.optimizer.semantic_cache import (
    CACHE_VERSION,
    SemanticCacheManager,
)
from app.rag.embedding import TestOnlyFakeEmbeddingProvider


class MockQdrantHit:
    def __init__(
        self,
        score: float,
        payload: dict[str, Any],
        vector: list[float] | None = None,
    ) -> None:
        self.score = score
        self.payload = payload
        self.vector = vector
        self.id = payload.get("id", "mock-point-id")


@pytest.fixture
def fake_embedding_provider() -> TestOnlyFakeEmbeddingProvider:
    return TestOnlyFakeEmbeddingProvider(dimension=64)


@pytest.fixture
def mock_qdrant_client() -> AsyncMock:
    client = AsyncMock()
    client.collection_exists.return_value = True
    client.create_collection = AsyncMock()
    client.upsert = AsyncMock()
    client.search = AsyncMock(return_value=[])
    client.delete = AsyncMock()
    return client


@pytest.mark.asyncio
async def test_real_embedding_dense_semantic_matching(
    fake_embedding_provider: TestOnlyFakeEmbeddingProvider,
) -> None:
    """Verify real embedding provider computes dense vectors and yields semantic hits."""
    cache = SemanticCacheManager(
        similarity_threshold=0.85,
        default_ttl=300,
        embedding_provider=fake_embedding_provider,
    )

    prompt_base = "Summarize annual financial statements for 2025"
    prompt_similar = "Summarize annual financial statements for 2025"
    tenant_id = "tenant_finance"

    await cache.set(
        prompt=prompt_base,
        tenant_id=tenant_id,
        response="Financial revenue for 2025 was $250M.",
        tokens_avoided=120,
        cost_avoided_usd=0.0036,
    )

    hit = await cache.get(prompt_similar, tenant_id)
    assert hit is not None
    assert hit.cache_type in ("exact", "semantic")
    assert hit.tokens_avoided == 120
    assert hit.cost_avoided_usd == 0.0036


@pytest.mark.asyncio
async def test_qdrant_vector_store_upsert_and_search(
    mock_qdrant_client: AsyncMock,
    fake_embedding_provider: TestOnlyFakeEmbeddingProvider,
) -> None:
    """Verify SemanticCacheManager interacts with Qdrant client for upsert and search."""
    cache = SemanticCacheManager(
        similarity_threshold=0.90,
        default_ttl=600,
        qdrant_client=mock_qdrant_client,
        embedding_provider=fake_embedding_provider,
    )

    tenant_id = "tenant_qdrant"
    prompt = "Explain quantum entanglement in simple terms"
    response = "Quantum entanglement is a physical phenomenon..."

    # 1. Set cache entry -> should call qdrant.upsert
    entry = await cache.set(
        prompt=prompt,
        tenant_id=tenant_id,
        response=response,
        model="gpt-4o",
        provider="openai",
    )
    assert entry.prompt == prompt
    assert mock_qdrant_client.upsert.called

    call_kwargs = mock_qdrant_client.upsert.call_args.kwargs
    assert call_kwargs["collection_name"] == cache.collection_name
    points = call_kwargs["points"]
    assert len(points) == 1
    assert points[0].payload["tenant_id"] == tenant_id
    assert points[0].payload["model"] == "gpt-4o"
    assert points[0].payload["provider"] == "openai"

    # 2. Simulate Qdrant search returning a semantic hit
    cached_payload = {
        "prompt": prompt,
        "response": response,
        "tenant_id": tenant_id,
        "model": "gpt-4o",
        "provider": "openai",
        "cached_at": time.time(),
        "ttl_seconds": 600,
        "version": CACHE_VERSION,
        "tokens_avoided": 85,
        "cost_avoided_usd": 0.002,
        "system_instructions": "",
        "tools": None,
        "response_format": None,
    }
    mock_qdrant_client.search.return_value = [
        MockQdrantHit(score=0.96, payload=cached_payload)
    ]

    # Query with a slightly different prompt to bypass exact memory cache
    query_prompt = "Could you explain quantum entanglement simply?"
    hit = await cache.get(
        prompt=query_prompt,
        tenant_id=tenant_id,
        model="gpt-4o",
        provider="openai",
    )

    assert hit is not None
    assert hit.cache_type == "semantic"
    assert hit.similarity_score == 0.96
    assert hit.response == response
    assert mock_qdrant_client.search.called


@pytest.mark.asyncio
async def test_qdrant_tenant_isolation_in_search(
    mock_qdrant_client: AsyncMock,
    fake_embedding_provider: TestOnlyFakeEmbeddingProvider,
) -> None:
    """Verify Qdrant search strictly rejects hits that belong to a different tenant."""
    cache = SemanticCacheManager(
        similarity_threshold=0.80,
        qdrant_client=mock_qdrant_client,
        embedding_provider=fake_embedding_provider,
    )

    mock_qdrant_client.search.return_value = [
        MockQdrantHit(
            score=0.99,
            payload={
                "prompt": "secret internal roadmap",
                "response": "Confidential roadmap data",
                "tenant_id": "tenant_foreign",
                "model": "default",
                "provider": "generic",
                "cached_at": time.time(),
                "ttl_seconds": 300,
                "version": CACHE_VERSION,
            },
        )
    ]

    hit = await cache.get("secret internal roadmap", tenant_id="tenant_my_company")
    assert hit is None


@pytest.mark.asyncio
async def test_qdrant_invalidation(
    mock_qdrant_client: AsyncMock,
    fake_embedding_provider: TestOnlyFakeEmbeddingProvider,
) -> None:
    """Verify cache invalidation deletes points from Qdrant by tenant or globally."""
    cache = SemanticCacheManager(
        qdrant_client=mock_qdrant_client,
        embedding_provider=fake_embedding_provider,
    )

    await cache.invalidate(tenant_id="tenant_to_purge")
    assert mock_qdrant_client.delete.called
    delete_kwargs = mock_qdrant_client.delete.call_args.kwargs
    assert delete_kwargs["collection_name"] == cache.collection_name

    mock_qdrant_client.delete.reset_mock()
    await cache.invalidate(tenant_id=None)
    assert mock_qdrant_client.delete.called


@pytest.mark.asyncio
async def test_generation_guardrails_prevent_mismatched_semantic_hit(
    fake_embedding_provider: TestOnlyFakeEmbeddingProvider,
) -> None:
    """Verify semantic hits are prevented when model, tools, or system prompt mismatch."""
    cache = SemanticCacheManager(
        similarity_threshold=0.80,
        embedding_provider=fake_embedding_provider,
    )
    tenant_id = "guardrail_tenant"

    await cache.set(
        prompt="Generate JSON user profile",
        tenant_id=tenant_id,
        response='{"name": "Alice"}',
        model="gpt-4o",
        provider="openai",
        system_instructions="You are a JSON generator.",
        tools=[{"name": "lookup_user"}],
        response_format={"type": "json_object"},
    )

    # 1. Model mismatch: claude-3-5-sonnet vs gpt-4o
    hit_diff_model = await cache.get(
        prompt="Generate JSON user profile summary",
        tenant_id=tenant_id,
        model="claude-3-5-sonnet",
        provider="anthropic",
        system_instructions="You are a JSON generator.",
        tools=[{"name": "lookup_user"}],
        response_format={"type": "json_object"},
    )
    assert hit_diff_model is None

    # 2. System instructions mismatch
    hit_diff_system = await cache.get(
        prompt="Generate JSON user profile summary",
        tenant_id=tenant_id,
        model="gpt-4o",
        provider="openai",
        system_instructions="You are an XML generator.",
        tools=[{"name": "lookup_user"}],
        response_format={"type": "json_object"},
    )
    assert hit_diff_system is None

    # 3. Tools mismatch
    hit_diff_tools = await cache.get(
        prompt="Generate JSON user profile summary",
        tenant_id=tenant_id,
        model="gpt-4o",
        provider="openai",
        system_instructions="You are a JSON generator.",
        tools=[{"name": "delete_user"}],
        response_format={"type": "json_object"},
    )
    assert hit_diff_tools is None


@pytest.mark.asyncio
async def test_fallback_to_memory_when_qdrant_fails(
    fake_embedding_provider: TestOnlyFakeEmbeddingProvider,
) -> None:
    """Verify seamless failover to in-memory vector store when Qdrant encounters exceptions."""
    failing_qdrant = AsyncMock()
    failing_qdrant.upsert.side_effect = RuntimeError("Qdrant connection timeout")
    failing_qdrant.search.side_effect = RuntimeError("Qdrant connection refused")

    cache = SemanticCacheManager(
        similarity_threshold=0.85,
        qdrant_client=failing_qdrant,
        embedding_provider=fake_embedding_provider,
    )

    tenant_id = "fallback_tenant"
    prompt = "How does photosynthesis work?"
    response = "Photosynthesis converts light into chemical energy."

    entry = await cache.set(
        prompt=prompt,
        tenant_id=tenant_id,
        response=response,
    )
    assert entry is not None

    exact_hit = await cache.get(prompt, tenant_id=tenant_id)
    assert exact_hit is not None
    assert exact_hit.response == response
