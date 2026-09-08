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
import unicodedata
from typing import Any

from pydantic import BaseModel, Field

try:
    import redis.asyncio as redis
except ImportError:
    redis = None  # type: ignore[assignment]

# Cache identity schema version. Bump when the cache key derivation
# algorithm changes to prevent legacy entries from colliding with new ones.
CACHE_VERSION = "v2.0"


class CacheMetrics(BaseModel):
    """Telemetry tracking for exact and semantic cache layers."""

    total_requests: int = 0
    exact_hits: int = 0
    semantic_hits: int = 0
    misses: int = 0
    tokens_avoided: int = 0
    cost_avoided_usd: float = 0.0

    @property
    def total_hits(self) -> int:
        return self.exact_hits + self.semantic_hits

    @property
    def hit_rate_pct(self) -> float:
        if self.total_requests == 0:
            return 0.0
        return round((self.total_hits / self.total_requests) * 100.0, 2)


class SemanticCacheEntry(BaseModel):
    """Cached response item with retrieval metadata."""

    prompt: str
    response: str
    tenant_id: str
    model: str = "default"
    provider: str = "generic"
    parameters: dict[str, Any] = Field(default_factory=dict)
    version: str = CACHE_VERSION
    citations: list[dict[str, Any]] = Field(default_factory=list)
    mascot_state: str = "idle"
    similarity_score: float = 1.0
    cache_type: str = "exact"  # "exact" or "semantic"
    cached_at: float = Field(default_factory=time.time)
    ttl_seconds: int = 3600
    vector: list[float] = Field(default_factory=list)
    tokens_avoided: int = 0
    cost_avoided_usd: float = 0.0
    system_instructions: str = ""
    tools: list[dict[str, Any]] | None = None
    response_format: dict[str, Any] | str | None = None


def _normalize_text(text: str) -> str:
    """Apply deterministic Unicode NFC normalization and whitespace collapsing."""
    nfc_text = unicodedata.normalize("NFC", text.strip().lower())
    return re.sub(r"\s+", " ", nfc_text)


def _compute_hash(
    text: str,
    tenant_id: str,
    model: str = "default",
    provider: str = "generic",
    version: str = CACHE_VERSION,
) -> str:
    """Legacy hash function. Kept for backward-compatible callers.

    New code should use ``compute_cache_identity`` which includes all
    generation-relevant dimensions.
    """
    normalized = _normalize_text(text)
    payload = f"{tenant_id}:{provider}:{model}:{version}:{normalized}".encode()
    return hashlib.sha256(payload).hexdigest()


def _canonical_messages_repr(
    messages: list[dict[str, str]] | None,
) -> str:
    """Build a deterministic canonical string from the full message history.

    Each message is represented as ``role:content`` with normalized content,
    joined by a record separator to preserve ordering.
    """
    if not messages:
        return ""
    parts: list[str] = []
    for msg in messages:
        role = msg.get("role", "").strip().lower()
        content = _normalize_text(msg.get("content", ""))
        parts.append(f"{role}:{content}")
    return "\x1e".join(parts)  # ASCII record separator


def _canonical_tools_repr(tools: list[dict[str, Any]] | None) -> str:
    """Build a deterministic canonical string from tool definitions.

    Tools are serialized as sorted JSON to ensure key ordering does not
    affect the cache identity.
    """
    if not tools:
        return ""
    return json.dumps(tools, sort_keys=True, separators=(",", ":"))


def _canonical_response_format_repr(
    response_format: dict[str, Any] | str | None,
) -> str:
    """Build a deterministic canonical string from response format constraints.

    Dicts (e.g. JSON schemas) are sorted by keys for determinism.
    Strings (e.g. 'json_object') are lowercased and stripped.
    """
    if not response_format:
        return ""
    if isinstance(response_format, str):
        return response_format.strip().lower()
    return json.dumps(response_format, sort_keys=True, separators=(",", ":"))


def _canonical_params_repr(params: dict[str, Any] | None) -> str:
    """Build a deterministic canonical string from generation parameters.

    Only meaningful parameters (non-None values) are included.
    """
    if not params:
        return ""
    # Filter out None values, sort keys for determinism
    filtered = {k: v for k, v in sorted(params.items()) if v is not None}
    if not filtered:
        return ""
    return json.dumps(filtered, sort_keys=True, separators=(",", ":"))


def compute_cache_identity(
    *,
    tenant_id: str,
    provider: str = "generic",
    model: str = "default",
    system_instructions: str = "",
    messages: list[dict[str, str]] | None = None,
    tools: list[dict[str, Any]] | None = None,
    response_format: dict[str, Any] | str | None = None,
    generation_params: dict[str, Any] | None = None,
    version: str = CACHE_VERSION,
) -> str:
    """Compute canonical SHA-256 cache identity from ALL generation-relevant dimensions.

    This function guarantees that two requests sharing a cache identity are
    semantically equivalent with respect to every dimension that affects the
    model's generation output. Any difference in tenant, provider, model,
    system instructions, conversation history, tools, response format,
    generation parameters, or cache schema version produces a different identity.

    All text inputs are NFC-normalized, lowercased, and whitespace-collapsed
    to ensure deterministic hashing.

    Returns:
        64-character lowercase hex SHA-256 digest.
    """
    normalized_system = (
        _normalize_text(system_instructions) if system_instructions else ""
    )
    messages_repr = _canonical_messages_repr(messages)
    tools_repr = _canonical_tools_repr(tools)
    response_format_repr = _canonical_response_format_repr(response_format)
    params_repr = _canonical_params_repr(generation_params)

    # Build the composite payload with explicit field separators.
    # Using \x1f (unit separator) between top-level fields to avoid
    # accidental collisions from field content containing delimiters.
    payload = "\x1f".join(
        [
            f"v={version}",
            f"t={tenant_id}",
            f"p={provider.strip().lower()}",
            f"m={model.strip().lower()}",
            f"si={normalized_system}",
            f"msgs={messages_repr}",
            f"tools={tools_repr}",
            f"rf={response_format_repr}",
            f"params={params_repr}",
        ]
    ).encode("utf-8")

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
        token_hash = int(
            hashlib.md5(word.encode(), usedforsecurity=False).hexdigest(), 16
        )
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
        self._redis_retry_after: float = 0.0
        self.metrics = CacheMetrics()

    def get_metrics(self) -> dict[str, Any]:
        """Return snapshot of cache performance metrics."""
        return {
            "total_requests": self.metrics.total_requests,
            "exact_hits": self.metrics.exact_hits,
            "semantic_hits": self.metrics.semantic_hits,
            "total_hits": self.metrics.total_hits,
            "misses": self.metrics.misses,
            "hit_rate_pct": self.metrics.hit_rate_pct,
            "tokens_avoided": self.metrics.tokens_avoided,
            "cost_avoided_usd": round(self.metrics.cost_avoided_usd, 6),
        }

    def reset_metrics(self) -> None:
        """Reset cache telemetry counters."""
        self.metrics = CacheMetrics()

    async def _get_redis(self) -> Any | None:
        """Lazily initialize Redis connection if available with connection verification and cooldown."""
        if self.redis_client is not None:
            return self.redis_client
        now = time.time()
        if not self._redis_available and now < self._redis_retry_after:
            return None
        try:
            import redis.asyncio as aioredis

            from app.core.config import get_settings

            settings = get_settings()
            client = aioredis.from_url(
                settings.REDIS_URL,
                decode_responses=True,
                socket_connect_timeout=settings.REDIS_CONNECT_TIMEOUT_SECONDS,
                socket_timeout=settings.REDIS_CONNECT_TIMEOUT_SECONDS,
            )
            await client.ping()
            self.redis_client = client
            self._redis_available = True
            self._redis_retry_after = 0.0
            return self.redis_client
        except Exception:
            from app.core.config import get_settings

            settings = get_settings()
            self._redis_available = False
            self._redis_retry_after = time.time() + settings.REDIS_COOLDOWN_SECONDS
            self.redis_client = None
            return None

    async def get(
        self,
        prompt: str,
        tenant_id: str,
        model: str = "default",
        provider: str = "generic",
        parameters: dict[str, Any] | None = None,
        version: str = CACHE_VERSION,
        *,
        system_instructions: str = "",
        messages: list[dict[str, str]] | None = None,
        tools: list[dict[str, Any]] | None = None,
        response_format: dict[str, Any] | str | None = None,
        generation_params: dict[str, Any] | None = None,
        exact_only: bool = False,
    ) -> SemanticCacheEntry | None:
        """Query cache for exact or semantic matches using canonical cache identity.

        The exact cache key is derived from ALL generation-relevant dimensions
        via ``compute_cache_identity``. Passing ``messages`` is strongly
        recommended; when omitted, a single-message list containing ``prompt``
        with role ``user`` is synthesized for backward compatibility.

        When ``exact_only=True``, only Tier 1 exact matches are queried and
        Tier 2 semantic vector search is bypassed.
        """
        self.metrics.total_requests += 1

        # Build canonical messages from prompt when callers haven't provided them
        effective_messages = messages
        if effective_messages is None:
            effective_messages = [{"role": "user", "content": prompt}]

        exact_key = compute_cache_identity(
            tenant_id=tenant_id,
            provider=provider,
            model=model,
            system_instructions=system_instructions,
            messages=effective_messages,
            tools=tools,
            response_format=response_format,
            generation_params=generation_params or parameters,
            version=version,
        )
        now = time.time()

        # 1. Tier 1: Check Exact Match in Redis
        redis_conn = await self._get_redis()
        if redis_conn is not None:
            try:
                raw_data = await redis_conn.get(f"cache:exact:{tenant_id}:{exact_key}")
                if raw_data:
                    data = json.loads(raw_data)
                    entry = SemanticCacheEntry(**data)
                    entry.cache_type = "exact"
                    entry.similarity_score = 1.0
                    self.metrics.exact_hits += 1
                    self.metrics.tokens_avoided += entry.tokens_avoided
                    self.metrics.cost_avoided_usd += entry.cost_avoided_usd
                    return entry
            except Exception:
                from app.core.config import get_settings

                settings = get_settings()
                self._redis_available = False
                self._redis_retry_after = time.time() + settings.REDIS_COOLDOWN_SECONDS
                self.redis_client = None

        # Check in-memory exact match
        if exact_key in self._memory_exact:
            entry = self._memory_exact[exact_key]
            if (now - entry.cached_at) <= entry.ttl_seconds:
                entry.cache_type = "exact"
                entry.similarity_score = 1.0
                self.metrics.exact_hits += 1
                self.metrics.tokens_avoided += entry.tokens_avoided
                self.metrics.cost_avoided_usd += entry.cost_avoided_usd
                return entry
            else:
                del self._memory_exact[exact_key]

        # If exact_only requested, skip Tier 2 semantic vector search
        if exact_only:
            self.metrics.misses += 1
            return None

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
            # Strict Model/Provider Compatibility Guardrail
            if entry.model != model and model != "default" and entry.model != "default":
                continue
            if (
                entry.provider != provider
                and provider != "generic"
                and entry.provider != "generic"
            ):
                continue
            if entry.version != version:
                continue
            # System instructions, tools, and response format must match for semantic hit
            if (
                entry.system_instructions
                and system_instructions
                and _normalize_text(entry.system_instructions)
                != _normalize_text(system_instructions)
            ):
                continue
            if entry.tools != tools:
                continue
            if entry.response_format != response_format:
                continue

            sim = _cosine_similarity(query_vec, entry.vector)
            if sim > best_similarity:
                best_similarity = sim
                best_match = entry

        self._memory_vectors[tenant_id] = valid_entries

        if best_match is not None and best_similarity >= self.similarity_threshold:
            self.metrics.semantic_hits += 1
            self.metrics.tokens_avoided += best_match.tokens_avoided
            self.metrics.cost_avoided_usd += best_match.cost_avoided_usd
            return SemanticCacheEntry(
                prompt=best_match.prompt,
                response=best_match.response,
                tenant_id=tenant_id,
                model=best_match.model,
                provider=best_match.provider,
                parameters=best_match.parameters,
                version=best_match.version,
                citations=best_match.citations,
                mascot_state=best_match.mascot_state,
                similarity_score=round(best_similarity, 4),
                cache_type="semantic",
                cached_at=best_match.cached_at,
                ttl_seconds=best_match.ttl_seconds,
                vector=best_match.vector,
                tokens_avoided=best_match.tokens_avoided,
                cost_avoided_usd=best_match.cost_avoided_usd,
                system_instructions=best_match.system_instructions,
                tools=best_match.tools,
                response_format=best_match.response_format,
            )

        self.metrics.misses += 1
        return None

    async def set(
        self,
        prompt: str,
        tenant_id: str,
        response: str,
        citations: list[dict[str, Any]] | None = None,
        mascot_state: str = "idle",
        ttl_seconds: int | None = None,
        model: str = "default",
        provider: str = "generic",
        parameters: dict[str, Any] | None = None,
        version: str = CACHE_VERSION,
        tokens_avoided: int = 0,
        cost_avoided_usd: float = 0.0,
        *,
        system_instructions: str = "",
        messages: list[dict[str, str]] | None = None,
        tools: list[dict[str, Any]] | None = None,
        response_format: dict[str, Any] | str | None = None,
        generation_params: dict[str, Any] | None = None,
    ) -> SemanticCacheEntry:
        """Store prompt and response in both exact and semantic cache tiers.

        The exact cache key is derived from ALL generation-relevant dimensions
        via ``compute_cache_identity``. When ``messages`` is not provided,
        a single ``user`` message from ``prompt`` is synthesized for backward
        compatibility.
        """
        ttl = ttl_seconds or self.default_ttl

        # Build canonical messages from prompt when callers haven't provided them
        effective_messages = messages
        if effective_messages is None:
            effective_messages = [{"role": "user", "content": prompt}]

        exact_key = compute_cache_identity(
            tenant_id=tenant_id,
            provider=provider,
            model=model,
            system_instructions=system_instructions,
            messages=effective_messages,
            tools=tools,
            response_format=response_format,
            generation_params=generation_params or parameters,
            version=version,
        )
        vector = _generate_synthetic_embedding(prompt)

        entry = SemanticCacheEntry(
            prompt=prompt,
            response=response,
            tenant_id=tenant_id,
            model=model,
            provider=provider,
            parameters=parameters or {},
            version=version,
            citations=citations or [],
            mascot_state=mascot_state,
            similarity_score=1.0,
            cache_type="exact",
            cached_at=time.time(),
            ttl_seconds=ttl,
            vector=vector,
            tokens_avoided=tokens_avoided,
            cost_avoided_usd=cost_avoided_usd,
            system_instructions=system_instructions,
            tools=tools,
            response_format=response_format,
        )

        # 1. Write Exact Match to Redis
        redis_conn = await self._get_redis()
        if redis_conn is not None:
            try:
                data_str = json.dumps(entry.model_dump())
                await redis_conn.set(
                    f"cache:exact:{tenant_id}:{exact_key}",
                    data_str,
                    ex=ttl,
                )
            except Exception:
                from app.core.config import get_settings

                settings = get_settings()
                self._redis_available = False
                self._redis_retry_after = time.time() + settings.REDIS_COOLDOWN_SECONDS
                self.redis_client = None

        # Write to in-memory exact and semantic stores
        self._memory_exact[exact_key] = entry
        if tenant_id not in self._memory_vectors:
            self._memory_vectors[tenant_id] = []
        self._memory_vectors[tenant_id].append(entry)

        return entry

    async def invalidate(self, tenant_id: str | None = None) -> int:
        """Invalidate cache entries for a tenant or globally."""
        cleared_count = 0
        redis_conn = await self._get_redis()

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

            if redis_conn is not None:
                try:
                    pattern = f"cache:exact:{tenant_id}:*"
                    keys = await redis_conn.keys(pattern)
                    if keys:
                        deleted = await redis_conn.delete(*keys)
                        cleared_count = max(cleared_count, int(deleted))
                except Exception:
                    self._redis_available = False
        else:
            cleared_count = len(self._memory_exact)
            self._memory_exact.clear()
            self._memory_vectors.clear()

            if redis_conn is not None:
                try:
                    pattern = "cache:exact:*"
                    keys = await redis_conn.keys(pattern)
                    if keys:
                        deleted = await redis_conn.delete(*keys)
                        cleared_count = max(cleared_count, int(deleted))
                except Exception:
                    self._redis_available = False

        return cleared_count


_semantic_cache_manager: SemanticCacheManager | None = None


def get_semantic_cache_manager() -> SemanticCacheManager:
    """Singleton getter for SemanticCacheManager."""
    global _semantic_cache_manager
    if _semantic_cache_manager is None:
        _semantic_cache_manager = SemanticCacheManager()
    return _semantic_cache_manager
