"""Unit tests for Multi-Tier Semantic Cache (Exact & Vector Cosine Similarity)."""

import pytest

from app.optimizer.semantic_cache import (
    SemanticCacheManager,
    _compute_hash,
    _cosine_similarity,
    _generate_synthetic_embedding,
)


@pytest.mark.asyncio
async def test_exact_match_cache_hit_and_miss() -> None:
    """Verify exact match caching returns identical payload on hit and None on miss."""
    cache = SemanticCacheManager(default_ttl=300)
    prompt = "What is our Q3 operating income?"
    tenant_id = "tenant_alpha"
    response = "Operating income for Q3 was $45M."

    # Cache miss
    cached = await cache.get(prompt, tenant_id)
    assert cached is None

    # Populate cache
    entry = await cache.set(
        prompt=prompt,
        tenant_id=tenant_id,
        response=response,
        citations=[{"source": "q3_report.pdf", "page": 12}],
        mascot_state="success",
    )
    assert entry.prompt == prompt
    assert entry.cache_type == "exact"

    # Cache hit
    hit = await cache.get(prompt, tenant_id)
    assert hit is not None
    assert hit.cache_type == "exact"
    assert hit.response == response
    assert hit.similarity_score == 1.0
    assert len(hit.citations) == 1
    assert hit.mascot_state == "success"


@pytest.mark.asyncio
async def test_semantic_vector_cache_hit_and_tenant_isolation() -> None:
    """Verify semantic similarity matches close queries and enforces tenant boundaries."""
    cache = SemanticCacheManager(similarity_threshold=0.85, default_ttl=300)
    prompt_base = "calculate quarterly revenue and expenses"
    prompt_similar = "calculate quarterly revenue and expenses report"
    tenant_a = "tenant_a"
    tenant_b = "tenant_b"

    await cache.set(
        prompt=prompt_base,
        tenant_id=tenant_a,
        response="Revenue: $100M, Expenses: $60M",
    )

    # Similar query under Tenant A should hit semantic cache
    match_a = await cache.get(prompt_similar, tenant_a)
    assert match_a is not None
    assert match_a.cache_type in ("exact", "semantic")
    assert match_a.similarity_score >= 0.85
    assert "Revenue: $100M" in match_a.response

    # Same query under Tenant B must NOT hit Tenant A's cache (Tenant Isolation)
    match_b = await cache.get(prompt_base, tenant_b)
    assert match_b is None


@pytest.mark.asyncio
async def test_cache_invalidation() -> None:
    """Verify cache invalidation by tenant and globally."""
    cache = SemanticCacheManager()
    await cache.set("query 1", "tenant_1", "resp 1")
    await cache.set("query 2", "tenant_2", "resp 2")

    # Invalidate tenant_1
    cleared = await cache.invalidate("tenant_1")
    assert cleared >= 1

    assert await cache.get("query 1", "tenant_1") is None
    assert await cache.get("query 2", "tenant_2") is not None

    # Global invalidation
    await cache.invalidate()
    assert await cache.get("query 2", "tenant_2") is None


def test_embedding_and_cosine_similarity() -> None:
    """Test vector normalization and cosine similarity computation."""
    vec1 = _generate_synthetic_embedding("financial earnings report")
    vec2 = _generate_synthetic_embedding("financial earnings report")
    vec3 = _generate_synthetic_embedding("unrelated weather in sunny florida")

    assert len(vec1) == 128
    sim_identical = _cosine_similarity(vec1, vec2)
    assert pytest.approx(sim_identical, 0.001) == 1.0

    sim_unrelated = _cosine_similarity(vec1, vec3)
    assert sim_unrelated < sim_identical

    # Test empty vector edge cases
    assert _cosine_similarity([], []) == 0.0
    assert _cosine_similarity([1.0], [1.0, 2.0]) == 0.0
    assert _compute_hash("  test prompt  ", "t1") == _compute_hash("test prompt", "t1")
