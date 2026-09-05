"""Advanced Multi-Tier Semantic Caching Engine for JakeAI Platform.

Implements:
  Tier 1: Sub-millisecond exact match cache backed by Redis (SHA-256 prompt hash).
  Tier 2: Semantic vector cache using cosine similarity (threshold >= 0.95)
          with strict tenant isolation and TTL management.
"""

import hashlib
import json
import math
import re
import time
from typing import Any

from pydantic import BaseModel, Field

try:
    import redis.asyncio as redis
except ImportError:
    redis = None  # type: ignore[assignment]


class SemanticCacheEntry(BaseModel):
    """Cached response item with retrieval metadata."""

    prompt: str
    response: str
    tenant_id: str
    citations: list[dict[str, Any]] = Field(default_factory=list)
    mascot_state: str = "idle"
    similarity_score: float = 1.0
    cache_type: str = "exact"  # "exact" or "semantic"
    cached_at: float = Field(default_factory=time.time)
    ttl_seconds: int = 3600
    vector: list[float] = Field(default_factory=list)


def _compute_hash(text: str, tenant_id: str) -> str:
    """Compute deterministic SHA-256 hash for normalized prompt and tenant."""
    normalized = re.sub(r"\s+", " ", text.strip().lower())
    payload = f"{tenant_id}:{normalized}".encode()
    return hashlib.sha256(payload).hexdigest()


def _generate_synthetic_embedding(text: str, dim: int = 128) -> list[float]:
    """Generate normalized deterministic vector embedding for text.

    Used when external embedding services are unavailable, ensuring
    semantically similar strings yield high cosine similarity.
    """
    words = re.findall(r"\b\w+\b", text.lower())
    vec = [0.0] * dim
    if not words:
        return vec

    for word in words:
        # Hash each token across vector buckets
        token_hash = int(hashlib.md5(word.encode()).hexdigest(), 16)  # nosec B324
        idx = token_hash % dim
        vec[idx] += 1.0

    # L2 normalize
    norm = math.sqrt(sum(x * x for x in vec))
    if norm > 0.0:
        vec = [x / norm for x in vec]
    return vec


def _cosine_similarity(vec_a: list[float], vec_b: list[float]) -> float:
    """Calculate cosine similarity between two unit-normalized vectors."""
    if not vec_a or not vec_b or len(vec_a) != len(vec_b):
        return 0.0
    dot_product = sum(a * b for a, b in zip(vec_a, vec_b, strict=False))
    return max(0.0, min(1.0, dot_product))


class SemanticCacheManager:
    """Multi-tier cache manager supporting exact match and semantic vector search."""

    def __init__(
        self,
        redis_client: Any | None = None,
        similarity_threshold: float = 0.95,
        default_ttl: int = 3600,
    ) -> None:
        self.redis_client = redis_client
        self.similarity_threshold = similarity_threshold
        self.default_ttl = default_ttl
        # Local in-memory store for fallback / fast testing
        self._memory_exact: dict[str, SemanticCacheEntry] = {}
        self._memory_vectors: dict[str, list[SemanticCacheEntry]] = {}
        self._redis_available: bool = True

    async def get(self, prompt: str, tenant_id: str) -> SemanticCacheEntry | None:
        """Query cache for exact or semantic matches for the given tenant."""
        exact_key = _compute_hash(prompt, tenant_id)
        now = time.time()

        # 1. Tier 1: Check Exact Match in Redis
        if self.redis_client is not None:
            try:
                raw_data = await self.redis_client.get(
                    f"cache:exact:{tenant_id}:{exact_key}"
                )
                if raw_data:
                    data = json.loads(raw_data)
                    entry = SemanticCacheEntry(**data)
                    entry.cache_type = "exact"
                    entry.similarity_score = 1.0
                    return entry
            except Exception:
                self._redis_available = False

        # Check in-memory exact match
        if exact_key in self._memory_exact:
            entry = self._memory_exact[exact_key]
            if (now - entry.cached_at) <= entry.ttl_seconds:
                entry.cache_type = "exact"
                entry.similarity_score = 1.0
                return entry
            del self._memory_exact[exact_key]

        # 2. Tier 2: Semantic Vector Cosine Similarity Search
        query_vec = _generate_synthetic_embedding(prompt)
        best_match: SemanticCacheEntry | None = None
        best_similarity = 0.0

        tenant_entries = self._memory_vectors.get(tenant_id, [])
        valid_entries: list[SemanticCacheEntry] = []

        for entry in tenant_entries:
            if (now - entry.cached_at) > entry.ttl_seconds:
                continue
            valid_entries.append(entry)
            sim = _cosine_similarity(query_vec, entry.vector)
            if sim > best_similarity:
                best_similarity = sim
                best_match = entry

        self._memory_vectors[tenant_id] = valid_entries

        if best_match is not None and best_similarity >= self.similarity_threshold:
            # Construct matched entry copy with semantic cache metadata
            return SemanticCacheEntry(
                prompt=best_match.prompt,
                response=best_match.response,
                tenant_id=tenant_id,
                citations=best_match.citations,
                mascot_state=best_match.mascot_state,
                similarity_score=round(best_similarity, 4),
                cache_type="semantic",
                cached_at=best_match.cached_at,
                ttl_seconds=best_match.ttl_seconds,
                vector=best_match.vector,
            )

        return None

    async def set(
        self,
        prompt: str,
        tenant_id: str,
        response: str,
        citations: list[dict[str, Any]] | None = None,
        mascot_state: str = "idle",
        ttl_seconds: int | None = None,
    ) -> SemanticCacheEntry:
        """Store prompt and response in both exact and semantic cache tiers."""
        ttl = ttl_seconds or self.default_ttl
        exact_key = _compute_hash(prompt, tenant_id)
        vector = _generate_synthetic_embedding(prompt)

        entry = SemanticCacheEntry(
            prompt=prompt,
            response=response,
            tenant_id=tenant_id,
            citations=citations or [],
            mascot_state=mascot_state,
            similarity_score=1.0,
            cache_type="exact",
            cached_at=time.time(),
            ttl_seconds=ttl,
            vector=vector,
        )

        # 1. Write Exact Match to Redis
        if self.redis_client is not None:
            try:
                data_str = json.dumps(entry.model_dump())
                await self.redis_client.set(
                    f"cache:exact:{tenant_id}:{exact_key}",
                    data_str,
                    ex=ttl,
                )
            except Exception:
                self._redis_available = False

        # Write to in-memory exact and semantic stores
        self._memory_exact[exact_key] = entry
        if tenant_id not in self._memory_vectors:
            self._memory_vectors[tenant_id] = []
        self._memory_vectors[tenant_id].append(entry)

        return entry

    async def invalidate(self, tenant_id: str | None = None) -> int:
        """Invalidate cache entries for a tenant or globally."""
        cleared_count = 0
        if tenant_id:
            keys_to_delete = [
                k for k, v in self._memory_exact.items() if v.tenant_id == tenant_id
            ]
            cleared_count += len(keys_to_delete)
            for k in keys_to_delete:
                del self._memory_exact[k]

            if tenant_id in self._memory_vectors:
                cleared_count += len(self._memory_vectors[tenant_id])
                del self._memory_vectors[tenant_id]

            if self.redis_client is not None:
                try:
                    pattern = f"cache:exact:{tenant_id}:*"
                    keys = await self.redis_client.keys(pattern)
                    if keys:
                        await self.redis_client.delete(*keys)
                except Exception:
                    self._redis_available = False
        else:
            cleared_count = len(self._memory_exact)
            self._memory_exact.clear()
            self._memory_vectors.clear()

        return cleared_count
