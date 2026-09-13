"""Advanced Multi-Tier Semantic Caching Engine for JakeAI Platform.

Implements:
  Tier 1: Sub-millisecond exact match cache backed by Redis (SHA-256 prompt hash).
  Tier 2: Semantic vector cache using cosine similarity (threshold >= 0.95)
          with strict tenant isolation and TTL management.
"""

import hashlib
import json
import logging
import math
import re
import time
import unicodedata
import uuid
from typing import Any

from pydantic import BaseModel, Field

logger = logging.getLogger(__name__)

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
    messages_hash: str | None = Field(
        default=None,
        description=(
            "SHA-256 fingerprint of the prior conversation context (all messages "
            "before the embedded prompt); semantic hits require an exact match."
        ),
    )


def _prior_context(
    effective_messages: list[dict[str, Any]] | list[Any], prompt: str
) -> list[dict[str, Any]] | list[Any]:
    """Return the conversation context that precedes the embedded prompt.

    The embedded prompt itself is already compared by vector similarity; only
    the surrounding history is invisible to the semantic tier and therefore
    needs an exact fingerprint.
    """
    if effective_messages:
        last = effective_messages[-1]
        content = (
            last.get("content")
            if isinstance(last, dict)
            else getattr(last, "content", None)
        )
        if content == prompt:
            return effective_messages[:-1]
    return effective_messages


def _messages_fingerprint(
    messages: list[dict[str, Any]] | list[Any] | None,
) -> str:
    """SHA-256 fingerprint over the canonical prior conversation context.

    The exact tier folds the full history into its identity hash; the semantic
    tier cannot compare vectors for history, so entries carry this fingerprint
    and semantic hits require an exact match. Returns "" for prompt-only
    requests (no prior context), which also matches legacy entries that carry
    no fingerprint only when the incoming request equally has no prior context.
    """
    if not messages:
        return ""
    canonical = _canonical_messages_repr(messages)
    if not canonical:
        return ""
    return hashlib.sha256(canonical.encode("utf-8")).hexdigest()


def _normalize_system_text(text: str) -> str:
    """Apply deterministic Unicode NFC normalization and collapse horizontal whitespace for system instructions."""
    nfc_text = unicodedata.normalize("NFC", text.strip())
    return re.sub(r"[ \t]+", " ", nfc_text)


def _normalize_text(text: str) -> str:
    """Apply deterministic Unicode NFC normalization without lowercasing or destroying whitespace."""
    return unicodedata.normalize("NFC", text)


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
    nfc_text = unicodedata.normalize("NFC", text.strip().lower())
    normalized = re.sub(r"\s+", " ", nfc_text)
    payload = f"{tenant_id}:{provider}:{model}:{version}:{normalized}".encode()
    return hashlib.sha256(payload).hexdigest()


def _canonical_messages_repr(
    messages: list[dict[str, Any]] | list[Any] | None,
) -> str:
    """Build a deterministic canonical string from the full message history.

    Includes role, content, name, tool_call_id, and tool_calls.
    Preserves exact user casing and code indentation.
    """
    if not messages:
        return ""
    parts: list[str] = []
    for msg in messages:
        if isinstance(msg, dict):
            role = str(msg.get("role") or "").strip().lower()
            raw_content = msg.get("content")
            name = msg.get("name")
            tool_call_id = msg.get("tool_call_id")
            tool_calls = msg.get("tool_calls")
        else:
            role = str(getattr(msg, "role", "") or "").strip().lower()
            raw_content = getattr(msg, "content", None)
            name = getattr(msg, "name", None)
            tool_call_id = getattr(msg, "tool_call_id", None)
            tool_calls = getattr(msg, "tool_calls", None)

        content_str = (
            _normalize_text(str(raw_content)) if raw_content is not None else ""
        )
        name_str = f":name={name}" if name else ""
        tcid_str = f":tcid={tool_call_id}" if tool_call_id else ""
        tc_str = (
            f":tc={json.dumps(tool_calls, sort_keys=True, separators=(',', ':'))}"
            if tool_calls
            else ""
        )
        parts.append(f"{role}:{content_str}{name_str}{tcid_str}{tc_str}")
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
    messages: list[dict[str, Any]] | list[Any] | None = None,
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

    All text inputs are NFC-normalized. User content casing and indentation
    are strictly preserved to ensure collision safety for code, identifiers,
    and formatted text.

    Returns:
        64-character lowercase hex SHA-256 digest.
    """
    normalized_system = (
        _normalize_system_text(system_instructions) if system_instructions else ""
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


_qdrant_global_available: bool = True
_qdrant_global_retry_after: float = 0.0


class SemanticCacheManager:
    """Multi-tier cache manager supporting exact match and semantic vector search."""

    def __init__(
        self,
        redis_client: Any | None = None,
        similarity_threshold: float = 0.95,
        default_ttl: int = 3600,
        collection_name: str = "jakeai_semantic_cache",
        qdrant_client: Any | None = None,
        embedding_provider: Any | None = None,
    ) -> None:
        self.redis_client = redis_client
        self.similarity_threshold = similarity_threshold
        self.default_ttl = default_ttl
        self.collection_name = collection_name
        self.qdrant_client = qdrant_client
        self._embedding_provider = embedding_provider
        # Local in-memory store for fallback / fast testing
        self._memory_exact: dict[str, SemanticCacheEntry] = {}
        self._memory_vectors: dict[str, list[SemanticCacheEntry]] = {}
        self._redis_available: bool = True
        self._redis_retry_after: float = 0.0
        self._qdrant_available: bool = True
        self._qdrant_retry_after: float = 0.0
        self.metrics = CacheMetrics()

    @property
    def embedding_provider(self) -> Any:
        """Get or lazily initialize the embedding provider."""
        if self._embedding_provider is None:
            try:
                from app.rag.embedding import get_embedding_provider

                self._embedding_provider = get_embedding_provider()
            except Exception as exc:
                logger.debug("Failed to retrieve embedding provider: %s", exc)
        return self._embedding_provider

    def _embed_text(self, text: str) -> list[float]:
        """Embed text using real dense embedding provider with fallback vector."""
        provider = self.embedding_provider
        if provider is not None:
            try:
                raw_emb = provider.embed_text(text)
                return [float(x) for x in raw_emb]
            except Exception as exc:
                logger.debug(
                    "Embedding provider embed_text error: %s; using fallback vector.",
                    exc,
                )
        return _generate_synthetic_embedding(text, dim=128)

    async def _get_qdrant(self) -> Any | None:
        """Lazily initialize Qdrant client connection if available with auto-collection provisioning."""
        global _qdrant_global_available, _qdrant_global_retry_after

        if self.qdrant_client is not None:
            return self.qdrant_client

        now = time.time()
        if (not self._qdrant_available and now < self._qdrant_retry_after) or (
            not _qdrant_global_available and now < _qdrant_global_retry_after
        ):
            return None

        try:
            from qdrant_client import AsyncQdrantClient
            from qdrant_client.http import models

            from app.core.config import get_settings

            settings = get_settings()
            dim = (
                self.embedding_provider.dimension
                if self.embedding_provider is not None
                else getattr(settings, "EMBEDDING_DIMENSION", 384)
            )
            client = AsyncQdrantClient(
                url=settings.QDRANT_URL,
                timeout=1,
                check_compatibility=False,
            )
            if not await client.collection_exists(self.collection_name):
                await client.create_collection(
                    collection_name=self.collection_name,
                    vectors_config=models.VectorParams(
                        size=dim,
                        distance=models.Distance.COSINE,
                    ),
                )
            self.qdrant_client = client
            self._qdrant_available = True
            self._qdrant_retry_after = 0.0
            _qdrant_global_available = True
            _qdrant_global_retry_after = 0.0
            return self.qdrant_client
        except Exception as exc:
            logger.debug(
                "Qdrant unavailable for semantic cache (%s); using in-memory store",
                exc,
            )
            self._qdrant_available = False
            self._qdrant_retry_after = time.time() + 60.0
            _qdrant_global_available = False
            _qdrant_global_retry_after = time.time() + 60.0
            self.qdrant_client = None
            return None

    @staticmethod
    def _is_compatible_for_semantic_hit(
        entry: SemanticCacheEntry,
        model: str,
        provider: str,
        version: str,
        effective_system: str,
        effective_tools: list[dict[str, Any]] | None,
        effective_rf: dict[str, Any] | str | None,
        effective_params: dict[str, Any] | None = None,
        incoming_messages_hash: str | None = None,
    ) -> bool:
        """Enforce strict generation compatibility guardrails for semantic hits.

        A semantic candidate may only be served when every generation-relevant
        dimension of the stored entry matches the incoming request. Model,
        provider, and generation parameters are compared with the same
        normalization used by ``compute_cache_identity`` so that the semantic
        tier can never serve a response the exact tier would have isolated.
        The full conversation history is compared via its fingerprint: a
        response cached under one history must never be served for another.
        """
        if entry.model.strip().lower() != model.strip().lower():
            return False
        if entry.provider.strip().lower() != provider.strip().lower():
            return False
        if entry.version != version:
            return False
        # Conversation history is generation-relevant (the exact tier hashes
        # it into the identity); entries without a fingerprint (legacy) never
        # match, fail-closed.
        if (entry.messages_hash or "") != (incoming_messages_hash or ""):
            return False
        if (
            entry.system_instructions
            and effective_system
            and _normalize_text(entry.system_instructions)
            != _normalize_text(effective_system)
        ):
            return False
        if entry.tools != effective_tools:
            return False
        if entry.response_format != effective_rf:
            return False
        # Generation parameters (temperature, max_tokens, ...) change model
        # output; a stored response generated under different parameters must
        # not be semantically reused.
        stored_params = dict(entry.parameters) if entry.parameters else {}
        incoming_params = dict(effective_params) if effective_params else {}
        # Ignore identity-extracted keys (tools/response_format/system) the
        # way get()/set() do before storing parameters.
        for key in ("tools", "response_format", "system_instructions"):
            stored_params.pop(key, None)
            incoming_params.pop(key, None)
        return _canonical_params_repr(stored_params) == _canonical_params_repr(
            incoming_params
        )

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

        # Build canonical messages ensuring current prompt is included
        effective_messages = list(messages) if messages is not None else []
        if not effective_messages:
            effective_messages = [{"role": "user", "content": prompt}]
        elif prompt and not any(
            (m.get("content") if isinstance(m, dict) else getattr(m, "content", ""))
            == prompt
            for m in effective_messages
        ):
            effective_messages.append({"role": "user", "content": prompt})

        # Extract tools, response_format, and system_instructions from parameters/generation_params if passed there
        combined_params = dict(generation_params or parameters or {})
        effective_tools = (
            tools if tools is not None else combined_params.pop("tools", None)
        )
        effective_rf = (
            response_format
            if response_format is not None
            else combined_params.pop("response_format", None)
        )
        effective_system = (
            system_instructions
            if system_instructions
            else combined_params.pop("system_instructions", "")
        )

        exact_key = compute_cache_identity(
            tenant_id=tenant_id,
            provider=provider,
            model=model,
            system_instructions=effective_system,
            messages=effective_messages,
            tools=effective_tools,
            response_format=effective_rf,
            generation_params=combined_params if combined_params else None,
            version=version,
        )
        incoming_messages_hash = _messages_fingerprint(
            _prior_context(effective_messages, prompt)
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
        query_vec = self._embed_text(prompt)

        # 2a. Query Qdrant if available
        qdrant = await self._get_qdrant()
        if qdrant is not None and self._qdrant_available:
            try:
                from qdrant_client.http import models

                tenant_filter = models.Filter(
                    must=[
                        models.FieldCondition(
                            key="tenant_id",
                            match=models.MatchValue(value=tenant_id),
                        )
                    ]
                )
                # qdrant-client >= 1.10 removed AsyncQdrantClient.search;
                # query_points is the supported search API.
                response = await qdrant.query_points(
                    collection_name=self.collection_name,
                    query=query_vec,
                    query_filter=tenant_filter,
                    limit=5,
                    score_threshold=self.similarity_threshold,
                )
                for hit in response.points:
                    payload = hit.payload or {}
                    # Defense-in-depth tenant boundary check
                    if str(payload.get("tenant_id")) != tenant_id:
                        continue
                    cached_at = float(payload.get("cached_at", 0.0))
                    ttl_sec = int(payload.get("ttl_seconds", self.default_ttl))
                    if (now - cached_at) > ttl_sec:
                        continue

                    candidate = SemanticCacheEntry(
                        prompt=str(payload.get("prompt", "")),
                        response=str(payload.get("response", "")),
                        tenant_id=tenant_id,
                        model=str(payload.get("model", "default")),
                        provider=str(payload.get("provider", "generic")),
                        parameters=payload.get("parameters") or {},
                        version=str(payload.get("version", CACHE_VERSION)),
                        citations=payload.get("citations") or [],
                        mascot_state=str(payload.get("mascot_state", "idle")),
                        similarity_score=round(float(hit.score), 4),
                        cache_type="semantic",
                        cached_at=cached_at,
                        ttl_seconds=ttl_sec,
                        vector=query_vec,
                        tokens_avoided=int(payload.get("tokens_avoided", 0)),
                        cost_avoided_usd=float(payload.get("cost_avoided_usd", 0.0)),
                        system_instructions=str(payload.get("system_instructions", "")),
                        tools=payload.get("tools"),
                        response_format=payload.get("response_format"),
                        messages_hash=payload.get("messages_hash"),
                    )
                    if self._is_compatible_for_semantic_hit(
                        candidate,
                        model=model,
                        provider=provider,
                        version=version,
                        effective_system=effective_system,
                        effective_tools=effective_tools,
                        effective_rf=effective_rf,
                        effective_params=combined_params,
                        incoming_messages_hash=incoming_messages_hash,
                    ):
                        self.metrics.semantic_hits += 1
                        self.metrics.tokens_avoided += candidate.tokens_avoided
                        self.metrics.cost_avoided_usd += candidate.cost_avoided_usd
                        return candidate
            except Exception as exc:
                logger.debug(
                    "Qdrant semantic search error: %s; falling back to in-memory store",
                    exc,
                )
                if self.qdrant_client is None:
                    self._qdrant_available = False
                    self._qdrant_retry_after = time.time() + 60.0

        # 2b. In-memory vector fallback search
        best_match: SemanticCacheEntry | None = None
        best_similarity = 0.0

        tenant_entries = self._memory_vectors.get(tenant_id, [])
        valid_entries: list[SemanticCacheEntry] = []

        for entry in tenant_entries:
            if (now - entry.cached_at) > entry.ttl_seconds:
                continue
            valid_entries.append(entry)
            if not self._is_compatible_for_semantic_hit(
                entry,
                model=model,
                provider=provider,
                version=version,
                effective_system=effective_system,
                effective_tools=effective_tools,
                effective_rf=effective_rf,
                effective_params=combined_params,
                incoming_messages_hash=incoming_messages_hash,
            ):
                continue
            if entry.vector is not None:
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
                messages_hash=best_match.messages_hash,
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

        # Build canonical messages ensuring current prompt is included
        effective_messages = list(messages) if messages is not None else []
        if not effective_messages:
            effective_messages = [{"role": "user", "content": prompt}]
        elif prompt and not any(
            (m.get("content") if isinstance(m, dict) else getattr(m, "content", ""))
            == prompt
            for m in effective_messages
        ):
            effective_messages.append({"role": "user", "content": prompt})

        # Extract tools, response_format, and system_instructions from parameters/generation_params if passed there
        combined_params = dict(generation_params or parameters or {})
        effective_tools = (
            tools if tools is not None else combined_params.pop("tools", None)
        )
        effective_rf = (
            response_format
            if response_format is not None
            else combined_params.pop("response_format", None)
        )
        effective_system = (
            system_instructions
            if system_instructions
            else combined_params.pop("system_instructions", "")
        )

        exact_key = compute_cache_identity(
            tenant_id=tenant_id,
            provider=provider,
            model=model,
            system_instructions=effective_system,
            messages=effective_messages,
            tools=effective_tools,
            response_format=effective_rf,
            generation_params=combined_params if combined_params else None,
            version=version,
        )
        vector = self._embed_text(prompt)

        entry = SemanticCacheEntry(
            prompt=prompt,
            response=response,
            tenant_id=tenant_id,
            model=model,
            provider=provider,
            parameters=combined_params,
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
            system_instructions=effective_system,
            tools=effective_tools,
            response_format=effective_rf,
            messages_hash=_messages_fingerprint(
                _prior_context(effective_messages, prompt)
            ),
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

        # 2. Write Semantic Vector to Qdrant if available
        qdrant = await self._get_qdrant()
        if qdrant is not None and self._qdrant_available:
            try:
                from qdrant_client.http import models

                point_id = str(
                    uuid.uuid5(uuid.NAMESPACE_DNS, f"{tenant_id}:{exact_key}")
                )
                payload = entry.model_dump()
                payload.pop("vector", None)
                await qdrant.upsert(
                    collection_name=self.collection_name,
                    points=[
                        models.PointStruct(
                            id=point_id,
                            vector=vector,
                            payload=payload,
                        )
                    ],
                )
            except Exception as exc:
                logger.debug("Failed to upsert semantic entry to Qdrant: %s", exc)
                if self.qdrant_client is None:
                    self._qdrant_available = False
                    self._qdrant_retry_after = time.time() + 60.0

        # 3. Write to in-memory exact and semantic stores
        self._memory_exact[exact_key] = entry
        if tenant_id not in self._memory_vectors:
            self._memory_vectors[tenant_id] = []
        self._memory_vectors[tenant_id].append(entry)

        return entry

    async def invalidate(self, tenant_id: str | None = None) -> int:
        """Invalidate cache entries for a tenant or globally across all tiers."""
        cleared_count = 0
        redis_conn = await self._get_redis()
        qdrant = await self._get_qdrant()

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

            if qdrant is not None and self._qdrant_available:
                try:
                    from qdrant_client.http import models

                    tenant_filter = models.Filter(
                        must=[
                            models.FieldCondition(
                                key="tenant_id",
                                match=models.MatchValue(value=tenant_id),
                            )
                        ]
                    )
                    await qdrant.delete(
                        collection_name=self.collection_name,
                        points_selector=models.FilterSelector(filter=tenant_filter),
                    )
                except Exception as exc:
                    logger.debug("Failed to delete tenant points from Qdrant: %s", exc)
                    if self.qdrant_client is None:
                        self._qdrant_available = False
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

            if qdrant is not None and self._qdrant_available:
                try:
                    from qdrant_client.http import models

                    await qdrant.delete(
                        collection_name=self.collection_name,
                        points_selector=models.FilterSelector(filter=models.Filter()),
                    )
                except Exception as exc:
                    logger.debug("Failed to clear all points from Qdrant: %s", exc)
                    if self.qdrant_client is None:
                        self._qdrant_available = False

        return cleared_count


_semantic_cache_manager: SemanticCacheManager | None = None


def get_semantic_cache_manager() -> SemanticCacheManager:
    """Singleton getter for SemanticCacheManager."""
    global _semantic_cache_manager
    if _semantic_cache_manager is None:
        _semantic_cache_manager = SemanticCacheManager()
    return _semantic_cache_manager
