"""Comprehensive verification test suite for R-FUNC-03: Cache Behavior.
Verifies exact and semantic response-cache behavior end-to-end:

1. Exact cache (Tier 1): miss -> generation -> set -> hit lifecycle, and
   one-at-a-time identity isolation across every generation-relevant
   dimension (tenant, provider, model, system instructions, full message
   history, message order, tools, tool_call_id/tool_calls message fields,
   response format, generation parameters, cache schema version).
2. Semantic cache (Tier 2): real dense embeddings (FastEmbed), strict
   tenant isolation, similarity threshold boundaries, generation
   compatibility guardrails (strict model/provider + generation params),
   expired/stale/legacy entry rejection, exact-tier precedence, and the
   real Qdrant client roundtrip (query_points) including a process
   restart simulation.
3. HTTP boundary: /api/v1/chat/stream cache miss/hit and identity
   isolation over real SSE responses; /api/v1/gateway/chat/completions
   exact-cache hit accounting and tool-call-structure isolation.
4. Real Redis persistence (skipped automatically when Redis is not
   reachable; executed in CI where the Redis service is present).
5. Concurrency: parallel set/get streams without cross-contamination.
"""

import asyncio
import time
import uuid
from typing import Any

import jwt
import pytest
from httpx import AsyncClient

from app.core.config import get_settings
from app.optimizer.semantic_cache import (
    CACHE_VERSION,
    SemanticCacheEntry,
    SemanticCacheManager,
    _compute_hash,
    compute_cache_identity,
)
from app.rag.embedding import TestOnlyFakeEmbeddingProvider

# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def unique_tenant(prefix: str) -> str:
    """Fresh tenant id per test to isolate cache state across the suite."""
    return f"{prefix}-{uuid.uuid4().hex[:10]}"


def _check_redis_reachable() -> bool:
    """Synchronous probe used for skipif on real-Redis persistence tests."""
    try:
        import redis as sync_redis

        client = sync_redis.Redis.from_url(
            get_settings().REDIS_URL,
            socket_connect_timeout=0.5,
            socket_timeout=0.5,
        )
        try:
            return bool(client.ping())
        finally:
            client.close()
    except Exception:
        return False


REDIS_AVAILABLE = _check_redis_reachable()


def parse_sse_events(body: str) -> list[tuple[str, dict[str, Any]]]:
    """Parse an SSE frame body into (event, data) pairs."""
    events: list[tuple[str, dict[str, Any]]] = []
    for frame in body.split("\n\n"):
        event_name: str | None = None
        data_payload: dict[str, Any] | None = None
        for line in frame.splitlines():
            if line.startswith("event: "):
                event_name = line[len("event: ") :].strip()
            elif line.startswith("data: "):
                import json

                try:
                    data_payload = json.loads(line[len("data: ") :])
                except json.JSONDecodeError:
                    data_payload = None
        if event_name is not None and isinstance(data_payload, dict):
            events.append((event_name, data_payload))
    return events


def auth_headers(
    tenant_id: str,
    roles: list[str] | None = None,
    permissions: list[str] | None = None,
) -> dict[str, str]:
    """Generate valid HS256 JWT Authorization headers for HTTP tests."""
    settings = get_settings()
    now = int(time.time())
    token = jwt.encode(
        {
            "sub": "user-rfunc03",
            "tenant_id": tenant_id,
            "iat": now,
            "exp": now + 3600,
            "roles": roles or ["financial_analyst"],
            "permissions": permissions or ["chat:stream", "chat:write"],
        },
        settings.JWT_SECRET_KEY,
        algorithm="HS256",
    )
    return {"Authorization": f"Bearer {token}"}


# ---------------------------------------------------------------------------
# Section 1 — Exact cache engine: lifecycle, identity, TTL, legacy, concurrency
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_scenario_01_exact_cache_miss_set_hit_lifecycle() -> None:
    """First request misses, second identical request hits the exact tier."""
    cache = SemanticCacheManager(similarity_threshold=2.0)
    tenant = unique_tenant("r03-lifecycle")
    await cache.invalidate(tenant)

    missed = await cache.get("Quarterly revenue summary", tenant_id=tenant)
    assert missed is None
    assert cache.metrics.misses == 1

    await cache.set(
        prompt="Quarterly revenue summary",
        tenant_id=tenant,
        response="Revenue grew 14% quarter over quarter.",
        model="gpt-4o",
        provider="openai",
    )

    hit = await cache.get(
        "Quarterly revenue summary",
        tenant_id=tenant,
        model="gpt-4o",
        provider="openai",
    )
    assert hit is not None
    assert hit.response == "Revenue grew 14% quarter over quarter."
    assert hit.cache_type == "exact"
    assert hit.similarity_score == 1.0
    assert cache.metrics.exact_hits == 1
    assert cache.metrics.semantic_hits == 0


@pytest.mark.parametrize(
    ("dimension", "changed_kwargs"),
    [
        ("tenant", {"tenant_id": "<other>"}),
        ("provider", {"provider": "anthropic"}),
        ("model", {"model": "gpt-3.5-turbo"}),
        (
            "system_instructions",
            {"system_instructions": "You are a security auditor."},
        ),
        (
            "messages_history",
            {
                "messages": [
                    {"role": "user", "content": "Start the analysis"},
                    {"role": "assistant", "content": "Proceeding."},
                    {"role": "user", "content": "Quarterly revenue summary"},
                ]
            },
        ),
        (
            "messages_order",
            {
                "messages": [
                    {"role": "user", "content": "B"},
                    {"role": "user", "content": "Quarterly revenue summary"},
                ]
            },
        ),
        (
            "tool_call_id",
            {
                "messages": [
                    {
                        "role": "tool",
                        "content": "Quarterly revenue summary",
                        "tool_call_id": "call_other",
                    }
                ]
            },
        ),
        (
            "tool_calls_structure",
            {
                "messages": [
                    {
                        "role": "assistant",
                        "content": "",
                        "tool_calls": [{"id": "call_2", "function": {"name": "f"}}],
                    }
                ]
            },
        ),
        (
            "tools",
            {
                "tools": [
                    {
                        "type": "function",
                        "function": {"name": "other_tool", "parameters": {}},
                    }
                ]
            },
        ),
        ("response_format", {"response_format": {"type": "json_object"}}),
        ("generation_params", {"generation_params": {"temperature": 0.0}}),
        ("cache_version", {"version": "v1.0"}),
    ],
)
@pytest.mark.asyncio
async def test_scenario_02_exact_identity_dimension_isolation(
    dimension: str, changed_kwargs: dict[str, Any]
) -> None:
    """Changing any single generation-relevant dimension must miss."""
    cache = SemanticCacheManager(similarity_threshold=2.0)
    tenant = unique_tenant("r03-dim")
    await cache.invalidate(tenant)

    base_kwargs: dict[str, Any] = {
        "prompt": "Quarterly revenue summary",
        "tenant_id": tenant,
        "response": "Baseline response",
        "model": "gpt-4o",
        "provider": "openai",
        "system_instructions": "You are a financial analyst.",
        "messages": [
            {"role": "user", "content": "A"},
            {"role": "user", "content": "Quarterly revenue summary"},
        ],
        "tools": [{"type": "function", "function": {"name": "calc", "parameters": {}}}],
        "response_format": None,
        "generation_params": {"temperature": 0.7, "max_tokens": 512},
        "version": CACHE_VERSION,
    }
    await cache.set(**base_kwargs)

    # Baseline request must hit
    base_hit = await cache.get(
        base_kwargs["prompt"],
        tenant_id=tenant,
        model=base_kwargs["model"],
        provider=base_kwargs["provider"],
        system_instructions=base_kwargs["system_instructions"],
        messages=base_kwargs["messages"],
        tools=base_kwargs["tools"],
        response_format=base_kwargs["response_format"],
        generation_params=base_kwargs["generation_params"],
        version=base_kwargs["version"],
    )
    assert base_hit is not None, f"baseline hit failed for dimension {dimension}"

    # One-at-a-time change must miss
    variant_kwargs = dict(base_kwargs)
    if dimension == "tenant":
        variant_kwargs["tenant_id"] = unique_tenant("r03-dim-other")
    else:
        variant_kwargs.update(changed_kwargs)

    lookup_kwargs = {
        "prompt": variant_kwargs["prompt"],
        "tenant_id": variant_kwargs["tenant_id"],
        "model": variant_kwargs["model"],
        "provider": variant_kwargs["provider"],
        "system_instructions": variant_kwargs["system_instructions"],
        "messages": variant_kwargs["messages"],
        "tools": variant_kwargs["tools"],
        "response_format": variant_kwargs["response_format"],
        "generation_params": variant_kwargs["generation_params"],
        "version": variant_kwargs["version"],
    }
    hit = await cache.get(**lookup_kwargs)
    assert hit is None, f"false exact hit when '{dimension}' differs"

    # Identity function directly: differ on the same dimension
    identity_base = compute_cache_identity(
        tenant_id=base_kwargs["tenant_id"],
        provider=base_kwargs["provider"],
        model=base_kwargs["model"],
        system_instructions=base_kwargs["system_instructions"],
        messages=base_kwargs["messages"],
        tools=base_kwargs["tools"],
        response_format=base_kwargs["response_format"],
        generation_params=base_kwargs["generation_params"],
        version=base_kwargs["version"],
    )
    identity_variant = compute_cache_identity(
        tenant_id=lookup_kwargs["tenant_id"],
        provider=lookup_kwargs["provider"],
        model=lookup_kwargs["model"],
        system_instructions=lookup_kwargs["system_instructions"],
        messages=lookup_kwargs["messages"],
        tools=lookup_kwargs["tools"],
        response_format=lookup_kwargs["response_format"],
        generation_params=lookup_kwargs["generation_params"],
        version=lookup_kwargs["version"],
    )
    assert identity_base != identity_variant, f"identity collision on {dimension}"


@pytest.mark.asyncio
async def test_scenario_03_exact_cache_ttl_expiry() -> None:
    """Expired entries must not be served by the exact tier."""
    cache = SemanticCacheManager(similarity_threshold=2.0)
    tenant = unique_tenant("r03-ttl")
    await cache.invalidate(tenant)

    await cache.set(
        prompt="Ephemeral prompt",
        tenant_id=tenant,
        response="Ephemeral response",
        ttl_seconds=1,
    )
    hit_fresh = await cache.get("Ephemeral prompt", tenant_id=tenant)
    assert hit_fresh is not None

    await asyncio.sleep(1.1)
    hit_expired = await cache.get("Ephemeral prompt", tenant_id=tenant)
    assert hit_expired is None, "expired entry was served by the exact tier"


@pytest.mark.asyncio
async def test_scenario_04_legacy_entries_must_not_hit() -> None:
    """Legacy schema-version entries and legacy hash keys must never be served."""
    cache = SemanticCacheManager(similarity_threshold=2.0)
    tenant = unique_tenant("r03-legacy")
    await cache.invalidate(tenant)

    prompt = "Legacy compatibility probe"
    legacy_vector = cache._embed_text(prompt)

    # (a) Entry carrying a legacy cache-schema version must fail the
    # semantic compatibility guardrail.
    legacy_versioned = SemanticCacheEntry(
        prompt=prompt,
        response="Legacy v1 response",
        tenant_id=tenant,
        version="v1.0",
        cached_at=time.time(),
        ttl_seconds=3600,
        vector=legacy_vector,
    )
    cache._memory_vectors[tenant] = [legacy_versioned]
    assert await cache.get(prompt, tenant_id=tenant) is None

    # (b) Entry stored under the legacy _compute_hash key layout must be
    # unreachable: the exact tier looks up by canonical identity only.
    cache._memory_exact[_compute_hash(prompt, tenant)] = SemanticCacheEntry(
        prompt=prompt,
        response="Legacy hash-key response",
        tenant_id=tenant,
        version="v1.0",
        cached_at=time.time(),
        ttl_seconds=3600,
        vector=legacy_vector,
    )
    assert await cache.get(prompt, tenant_id=tenant) is None

    # (c) The legacy hash layout differs from the canonical identity keys.
    current_identity = compute_cache_identity(
        tenant_id=tenant, messages=[{"role": "user", "content": prompt}]
    )
    assert _compute_hash(prompt, tenant) != current_identity

    # Sanity: a current-version entry still hits normally.
    await cache.set(prompt=prompt, tenant_id=tenant, response="Current response")
    hit = await cache.get(prompt, tenant_id=tenant)
    assert hit is not None
    assert hit.response == "Current response"


@pytest.mark.asyncio
async def test_scenario_05_concurrent_set_get_no_cross_contamination() -> None:
    """Parallel set/get streams must not cross-contaminate or crash."""
    cache = SemanticCacheManager(similarity_threshold=2.0)
    tenant = unique_tenant("r03-conc")
    await cache.invalidate(tenant)

    async def populate(i: int) -> None:
        await cache.set(
            prompt=f"Concurrent prompt {i}",
            tenant_id=tenant,
            response=f"Concurrent response {i}",
            model="gpt-4o",
            provider="openai",
        )

    async def read_after_populate(i: int) -> None:
        await populate(i)
        hit = await cache.get(
            f"Concurrent prompt {i}",
            tenant_id=tenant,
            model="gpt-4o",
            provider="openai",
        )
        assert hit is not None
        assert hit.response == f"Concurrent response {i}", (
            f"cross-contamination for item {i}: got {hit.response!r}"
        )

    await asyncio.gather(*(read_after_populate(i) for i in range(24)))


@pytest.mark.asyncio
async def test_scenario_06_metrics_accounting() -> None:
    """Hit/miss accounting must track exact hits, semantic hits and misses."""
    cache = SemanticCacheManager(similarity_threshold=0.95)
    tenant = unique_tenant("r03-metrics")
    await cache.invalidate(tenant)

    # 1. miss
    assert await cache.get("Unrelated metrics probe alpha", tenant_id=tenant) is None
    # 2. populate
    await cache.set(
        prompt="How do I reset my account password?",
        tenant_id=tenant,
        response="Use the password reset page.",
    )
    # 3. exact hit
    assert (
        await cache.get("How do I reset my account password?", tenant_id=tenant)
        is not None
    )
    # 4. semantic hit (near duplicate, real embeddings)
    semantic_hit = await cache.get(
        "How can I reset my account password?", tenant_id=tenant
    )
    assert semantic_hit is not None
    assert semantic_hit.cache_type == "semantic"
    # 5. miss
    assert await cache.get("Unrelated metrics probe beta", tenant_id=tenant) is None

    metrics = cache.get_metrics()
    assert metrics["total_requests"] == 4
    assert metrics["exact_hits"] == 1
    assert metrics["semantic_hits"] == 1
    assert metrics["misses"] == 2
    assert metrics["total_hits"] == 2
    assert metrics["hit_rate_pct"] == 50.0

    cache.reset_metrics()
    assert cache.get_metrics()["total_requests"] == 0


# ---------------------------------------------------------------------------
# Section 2 — Semantic tier: real embeddings, isolation, guardrails, Qdrant
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_scenario_07_semantic_real_embeddings_near_duplicate_vs_unrelated() -> (
    None
):
    """Real dense embeddings: near duplicate hits, unrelated query misses."""
    cache = SemanticCacheManager(similarity_threshold=0.95)
    tenant = unique_tenant("r03-semreal")
    await cache.invalidate(tenant)

    await cache.set(
        prompt="How do I reset my account password?",
        tenant_id=tenant,
        response="Use the password reset page.",
    )

    near_dup = await cache.get("How can I reset my account password?", tenant_id=tenant)
    assert near_dup is not None
    assert near_dup.cache_type == "semantic"
    assert near_dup.similarity_score >= 0.95

    unrelated = await cache.get("What is the capital city of France?", tenant_id=tenant)
    assert unrelated is None


@pytest.mark.asyncio
async def test_scenario_08_semantic_tenant_isolation() -> None:
    """Semantic tier must never serve entries across tenants."""
    cache = SemanticCacheManager(similarity_threshold=0.95)
    tenant_a = unique_tenant("r03-sem-iso-a")
    tenant_b = unique_tenant("r03-sem-iso-b")

    await cache.set(
        prompt="Explain our data retention policy",
        tenant_id=tenant_a,
        response="Tenant A confidential policy answer",
    )

    # Exact identity differs by tenant; semantic tier must also reject.
    cross_tenant = await cache.get(
        "Explain our data retention policy", tenant_id=tenant_b
    )
    assert cross_tenant is None, "cross-tenant semantic hit"

    same_tenant = await cache.get(
        "Explain our data retention policy", tenant_id=tenant_a
    )
    assert same_tenant is not None
    assert same_tenant.response == "Tenant A confidential policy answer"


@pytest.mark.parametrize(
    ("dimension", "changed"),
    [
        ("model", {"model": "claude-3-5-sonnet"}),
        ("provider", {"provider": "anthropic"}),
        (
            "system_instructions",
            {"system_instructions": "You are an XML generator."},
        ),
        ("tools", {"tools": [{"name": "delete_user"}]}),
        ("response_format", {"response_format": None}),
    ],
)
@pytest.mark.asyncio
async def test_scenario_09_semantic_generation_compatibility_guardrails(
    dimension: str, changed: dict[str, Any]
) -> None:
    """Semantic hits must be rejected when generation-relevant dims differ."""
    cache = SemanticCacheManager(similarity_threshold=0.80)
    tenant = unique_tenant("r03-semcompat")
    await cache.invalidate(tenant)

    await cache.set(
        prompt="Generate JSON user profile",
        tenant_id=tenant,
        response='{"name": "Alice"}',
        model="gpt-4o",
        provider="openai",
        system_instructions="You are a JSON generator.",
        tools=[{"name": "lookup_user"}],
        response_format={"type": "json_object"},
    )

    lookup: dict[str, Any] = {
        "prompt": "Generate JSON user profile summary",
        "tenant_id": tenant,
        "model": "gpt-4o",
        "provider": "openai",
        "system_instructions": "You are a JSON generator.",
        "tools": [{"name": "lookup_user"}],
        "response_format": {"type": "json_object"},
    }
    lookup.update(changed)
    hit = await cache.get(**lookup)
    assert hit is None, f"semantic hit served despite '{dimension}' mismatch"


@pytest.mark.asyncio
async def test_scenario_10_semantic_generation_params_guardrail() -> None:
    """Different generation parameters must block semantic reuse (R-FUNC-03 fix)."""
    cache = SemanticCacheManager(similarity_threshold=0.95)
    tenant = unique_tenant("r03-semparams")
    await cache.invalidate(tenant)

    await cache.set(
        prompt="Draft an executive summary of the incident",
        tenant_id=tenant,
        response="Creative temperature 0.9 draft",
        model="gpt-4o",
        provider="openai",
        generation_params={"temperature": 0.9, "max_tokens": 512},
    )

    # Same parameters, near-duplicate prompt -> semantic hit.
    hit_same_params = await cache.get(
        "Draft an executive summary of the security incident",
        tenant_id=tenant,
        model="gpt-4o",
        provider="openai",
        generation_params={"temperature": 0.9, "max_tokens": 512},
    )
    assert hit_same_params is not None
    assert hit_same_params.cache_type == "semantic"

    # Different temperature on the IDENTICAL prompt -> identity differs and
    # the semantic tier must also refuse to cross the parameter boundary.
    hit_diff_params = await cache.get(
        "Draft an executive summary of the incident",
        tenant_id=tenant,
        model="gpt-4o",
        provider="openai",
        generation_params={"temperature": 0.0, "max_tokens": 512},
    )
    assert hit_diff_params is None, (
        "semantic hit served although generation parameters differ"
    )


@pytest.mark.asyncio
async def test_scenario_11_semantic_strict_model_provider_matching() -> None:
    """No wildcard model/provider matching in the semantic tier (R-FUNC-03 fix)."""
    cache = SemanticCacheManager(similarity_threshold=0.80)
    tenant = unique_tenant("r03-semstrict")
    await cache.invalidate(tenant)

    # Entry pinned to gpt-4o; request without model ("default") must not hit.
    await cache.set(
        prompt="Summarize the compliance report",
        tenant_id=tenant,
        response="gpt-4o compliance summary",
        model="gpt-4o",
        provider="openai",
    )
    hit_default_request = await cache.get(
        "Summarize the compliance report", tenant_id=tenant, model="default"
    )
    assert hit_default_request is None, (
        "unpinned request served a response cached for a pinned model"
    )

    # Entry without a pinned model; request pinning gpt-4o must not hit.
    tenant2 = unique_tenant("r03-semstrict2")
    await cache.set(
        prompt="Summarize the compliance report",
        tenant_id=tenant2,
        response="default-model compliance summary",
        model="default",
    )
    hit_pinned_request = await cache.get(
        "Summarize the compliance report", tenant_id=tenant2, model="gpt-4o"
    )
    assert hit_pinned_request is None, (
        "pinned request served a response cached for the unpinned default model"
    )

    # Case normalization aligned with the identity function: GPT-4O/OpenAI
    # normalize to the same generation dimensions. Using a near-duplicate
    # prompt keeps the lookup on the semantic tier.
    hit_case = await cache.get(
        "Summarize the compliance report briefly",
        tenant_id=tenant,
        model="GPT-4O",
        provider="OpenAI",
    )
    assert hit_case is not None
    assert hit_case.cache_type == "semantic"


@pytest.mark.asyncio
async def test_scenario_12_semantic_similarity_threshold_boundary() -> None:
    """Threshold is enforced: above hits, above-threshold-but-configured-higher misses."""
    tenant = unique_tenant("r03-threshold")

    strict_cache = SemanticCacheManager(similarity_threshold=0.999)
    await strict_cache.set(
        prompt="How do I rotate my API credentials?",
        tenant_id=tenant,
        response="Credential rotation guide",
    )
    strict_hit = await strict_cache.get(
        "How can I rotate my API credentials?", tenant_id=tenant
    )
    assert strict_hit is None, "hit served below configured similarity threshold"

    lenient_cache = SemanticCacheManager(similarity_threshold=0.90)
    await lenient_cache.set(
        prompt="How do I rotate my API credentials?",
        tenant_id=tenant,
        response="Credential rotation guide",
    )
    lenient_hit = await lenient_cache.get(
        "How can I rotate my API credentials?", tenant_id=tenant
    )
    assert lenient_hit is not None
    assert lenient_hit.cache_type == "semantic"
    assert lenient_hit.similarity_score >= 0.90


@pytest.mark.asyncio
async def test_scenario_13_exact_only_bypasses_semantic_tier() -> None:
    """exact_only lookups must never return semantic candidates."""
    cache = SemanticCacheManager(similarity_threshold=0.90)
    tenant = unique_tenant("r03-exactonly")
    await cache.invalidate(tenant)

    await cache.set(
        prompt="Describe the reconciliation workflow",
        tenant_id=tenant,
        response="Reconciliation workflow description",
    )
    semantic_hit = await cache.get(
        "Describe the account reconciliation workflow", tenant_id=tenant
    )
    assert semantic_hit is not None
    assert semantic_hit.cache_type == "semantic"

    exact_only = await cache.get(
        "Describe the account reconciliation workflow",
        tenant_id=tenant,
        exact_only=True,
    )
    assert exact_only is None, "exact_only lookup returned a semantic candidate"


@pytest.mark.asyncio
async def test_scenario_14_semantic_never_replaces_exact_tier() -> None:
    """An identical request must be served by the exact tier, not the semantic tier."""
    cache = SemanticCacheManager(similarity_threshold=0.90)
    tenant = unique_tenant("r03-precedence")
    await cache.invalidate(tenant)

    # Two semantically similar but distinct entries.
    await cache.set(
        prompt="Explain invoice factoring",
        tenant_id=tenant,
        response="Invoice factoring explanation",
    )
    await cache.set(
        prompt="Explain invoice factoring and discounting",
        tenant_id=tenant,
        response="Factoring and discounting explanation",
    )
    hits_before = cache.metrics.exact_hits + cache.metrics.semantic_hits

    # Identical replay of the second entry: exact tier must win.
    hit = await cache.get("Explain invoice factoring and discounting", tenant_id=tenant)
    assert hit is not None
    assert hit.cache_type == "exact", "exact replay was served by the semantic tier"
    assert hit.response == "Factoring and discounting explanation"
    assert cache.metrics.exact_hits >= 1
    assert cache.metrics.exact_hits + cache.metrics.semantic_hits == hits_before + 1


@pytest.mark.asyncio
async def test_scenario_15_qdrant_roundtrip_serves_after_restart_simulation() -> None:
    """Real Qdrant client roundtrip: semantic hit must survive memory loss.

    Regression for the dead ``AsyncQdrantClient.search`` call: the manager
    must use the supported ``query_points`` API so cached semantic vectors
    are actually retrievable from Qdrant after an in-process restart.
    """
    from qdrant_client import AsyncQdrantClient
    from qdrant_client.http import models as qdrant_models

    qdrant = AsyncQdrantClient(":memory:")
    cache = SemanticCacheManager(
        similarity_threshold=0.90,
        qdrant_client=qdrant,
        collection_name=f"r03_qdrant_roundtrip_{uuid.uuid4().hex[:8]}",
    )
    tenant = unique_tenant("r03-qdrant")

    # An injected client bypasses the manager's auto-provisioning, so create
    # the collection with the manager's actual embedding dimension.
    dim = len(cache._embed_text("dimension probe"))
    await qdrant.create_collection(
        collection_name=cache.collection_name,
        vectors_config=qdrant_models.VectorParams(
            size=dim, distance=qdrant_models.Distance.COSINE
        ),
    )

    await cache.set(
        prompt="Outline the vendor onboarding checklist",
        tenant_id=tenant,
        response="Vendor onboarding checklist steps",
        model="gpt-4o",
        provider="openai",
    )

    count = await qdrant.count(cache.collection_name, exact=True)
    assert count.count == 1, "semantic vector was not persisted to Qdrant"

    # Simulate process restart: drop every in-process store.
    cache._memory_exact.clear()
    cache._memory_vectors.clear()

    hit = await cache.get(
        "Outline the vendor onboarding checklist",
        tenant_id=tenant,
        model="gpt-4o",
        provider="openai",
    )
    assert hit is not None, (
        "semantic entry not served from Qdrant after memory loss - "
        "Qdrant search path is dead (query_points regression)"
    )
    assert hit.cache_type == "semantic"
    assert hit.response == "Vendor onboarding checklist steps"

    # Deterministic point identity: re-setting the same request must
    # overwrite the same UUIDv5 point instead of duplicating it.
    await cache.set(
        prompt="Outline the vendor onboarding checklist",
        tenant_id=tenant,
        response="Vendor onboarding checklist steps v2",
        model="gpt-4o",
        provider="openai",
    )
    count_after_reset = await qdrant.count(cache.collection_name, exact=True)
    assert count_after_reset.count == 1, "point identity is not deterministic"


@pytest.mark.asyncio
async def test_scenario_16_qdrant_expired_entry_not_served() -> None:
    """Qdrant-backed semantic hits must respect TTL expiry."""
    from qdrant_client import AsyncQdrantClient
    from qdrant_client.http import models as qdrant_models

    qdrant = AsyncQdrantClient(":memory:")
    cache = SemanticCacheManager(
        similarity_threshold=0.90,
        qdrant_client=qdrant,
        embedding_provider=TestOnlyFakeEmbeddingProvider(dimension=64),
        collection_name=f"r03_qdrant_ttl_{uuid.uuid4().hex[:8]}",
    )
    tenant = unique_tenant("r03-qdrant-ttl")

    dim = len(cache._embed_text("dimension probe"))
    await qdrant.create_collection(
        collection_name=cache.collection_name,
        vectors_config=qdrant_models.VectorParams(
            size=dim, distance=qdrant_models.Distance.COSINE
        ),
    )

    await cache.set(
        prompt="Temporary vector entry",
        tenant_id=tenant,
        response="Temporary response",
        ttl_seconds=1,
    )
    cache._memory_exact.clear()
    cache._memory_vectors.clear()

    await asyncio.sleep(1.1)
    hit = await cache.get("Temporary vector entry", tenant_id=tenant)
    assert hit is None, "expired semantic entry was served from Qdrant"


@pytest.mark.asyncio
async def test_scenario_17_qdrant_tenant_filter_defense_in_depth() -> None:
    """Qdrant candidate payloads from another tenant must be rejected."""
    from types import SimpleNamespace
    from unittest.mock import AsyncMock

    qdrant = AsyncMock()
    qdrant.collection_exists.return_value = True
    foreign_payload = {
        "prompt": "Confidential roadmap question",
        "response": "Confidential roadmap answer",
        "tenant_id": "tenant-foreign",
        "model": "default",
        "provider": "generic",
        "cached_at": time.time(),
        "ttl_seconds": 3600,
        "version": CACHE_VERSION,
    }
    qdrant.query_points.return_value = SimpleNamespace(
        points=[SimpleNamespace(score=0.99, payload=foreign_payload, id="x")]
    )

    cache = SemanticCacheManager(
        similarity_threshold=0.90,
        qdrant_client=qdrant,
        embedding_provider=TestOnlyFakeEmbeddingProvider(dimension=64),
    )
    hit = await cache.get("Confidential roadmap question", tenant_id="tenant-mine")
    assert hit is None, "defense-in-depth tenant check failed"


# ---------------------------------------------------------------------------
# Section 3 — HTTP boundary: /api/v1/chat/stream and /api/v1/gateway
# ---------------------------------------------------------------------------


STREAM_PROMPT = "Summarize the monthly revenue trend for our online store"


@pytest.mark.asyncio
async def test_scenario_18_stream_endpoint_miss_then_exact_hit(
    async_client: AsyncClient, monkeypatch: pytest.MonkeyPatch
) -> None:
    """HTTP: identical replay must hit the cache; first request must miss."""
    settings = get_settings()
    monkeypatch.setattr(settings, "JWT_ALGORITHM", "HS256")
    tenant = unique_tenant("r03-http-stream")
    headers = auth_headers(tenant)
    payload = {"prompt": STREAM_PROMPT, "conversation_id": f"conv-{tenant}"}

    res1 = await async_client.post("/api/v1/chat/stream", headers=headers, json=payload)
    assert res1.status_code == 200
    events1 = parse_sse_events(res1.text)
    done1 = next((d for e, d in events1 if e == "done"), None)
    assert done1 is not None, "first request did not complete"
    assert "cache_hit" not in done1, "first request reported a cache hit"

    res2 = await async_client.post("/api/v1/chat/stream", headers=headers, json=payload)
    assert res2.status_code == 200
    events2 = parse_sse_events(res2.text)

    cache_status = next(
        (d for e, d in events2 if e == "status" and d.get("phase") == "cache_hit"),
        None,
    )
    assert cache_status is not None, "replay did not report cache_hit status event"
    done2 = next((d for e, d in events2 if e == "done"), None)
    assert done2 is not None
    assert done2.get("cache_hit") in ("exact", "semantic"), (
        f"unexpected cache_hit type: {done2.get('cache_hit')}"
    )

    # Cached replay must stream the exact same response content.
    tokens1 = "".join(d.get("content", "") for e, d in events1 if e == "token")
    tokens2 = "".join(d.get("content", "") for e, d in events2 if e == "token")
    assert tokens1 == tokens2, "cached replay content differs from original response"
    assert tokens1.strip() != "", "empty response content"

    telemetry2 = next((d for e, d in events2 if e == "telemetry"), None)
    assert telemetry2 is not None
    assert telemetry2.get("cache_hit") in ("exact", "semantic")


@pytest.mark.asyncio
async def test_scenario_19_stream_endpoint_cross_tenant_isolation(
    async_client: AsyncClient, monkeypatch: pytest.MonkeyPatch
) -> None:
    """HTTP: the same prompt from another tenant must not hit the cache."""
    settings = get_settings()
    monkeypatch.setattr(settings, "JWT_ALGORITHM", "HS256")
    tenant_a = unique_tenant("r03-http-ten-a")
    tenant_b = unique_tenant("r03-http-ten-b")

    payload = {"prompt": STREAM_PROMPT, "conversation_id": f"conv-{tenant_a}"}
    res1 = await async_client.post(
        "/api/v1/chat/stream", headers=auth_headers(tenant_a), json=payload
    )
    assert res1.status_code == 200

    res2 = await async_client.post(
        "/api/v1/chat/stream",
        headers=auth_headers(tenant_b),
        json={"prompt": STREAM_PROMPT, "conversation_id": f"conv-{tenant_b}"},
    )
    assert res2.status_code == 200
    events2 = parse_sse_events(res2.text)
    done2 = next((d for e, d in events2 if e == "done"), None)
    assert done2 is not None
    assert "cache_hit" not in done2, "cross-tenant cache hit over HTTP"


@pytest.mark.parametrize(
    ("dimension", "base_params", "variant_params", "allow_semantic_hit"),
    [
        (
            "model",
            {"model": "gpt-4o"},
            {"model": "gemini-1.5-flash"},
            False,
        ),
        (
            "system_instruction",
            {"system_instruction": "You are a terse financial analyst."},
            {"system_instruction": "You are an verbose poetry assistant."},
            False,
        ),
        (
            "messages_history",
            {"messages": [{"role": "system", "content": "History context one"}]},
            {"messages": [{"role": "system", "content": "History context two"}]},
            # W-COST-04 sanctions prompt-based semantic reuse; the history is
            # guarded by the exact tier only. A semantic hit is acceptable, an
            # exact hit is not.
            True,
        ),
        (
            "tools",
            {
                "tools": [
                    {
                        "type": "function",
                        "function": {"name": "calc_tool", "parameters": {}},
                    }
                ]
            },
            {
                "tools": [
                    {
                        "type": "function",
                        "function": {"name": "lookup_tool", "parameters": {}},
                    }
                ]
            },
            False,
        ),
        (
            "response_format",
            {"response_format": {"type": "json_object"}},
            {"response_format": None},
            False,
        ),
        (
            "generation_params",
            {"generation_params": {"temperature": 0.7}},
            {"generation_params": {"temperature": 0.0}},
            False,
        ),
    ],
)
@pytest.mark.asyncio
async def test_scenario_20_stream_endpoint_identity_dimension_isolation(
    dimension: str,
    base_params: dict[str, Any],
    variant_params: dict[str, Any],
    allow_semantic_hit: bool,
    async_client: AsyncClient,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """HTTP: changing one generation-relevant parameter must not hit the exact tier.

    For dimensions protected by the semantic compatibility guardrails
    (model, system instruction, tools, response format, generation params)
    no hit of any kind may occur. History changes are semantic-tier eligible
    by design (W-COST-04), so only a semantic hit is tolerated there.
    """
    settings = get_settings()
    monkeypatch.setattr(settings, "JWT_ALGORITHM", "HS256")
    tenant = unique_tenant(f"r03-http-dim-{dimension}")

    base_payload = {
        "prompt": STREAM_PROMPT,
        "conversation_id": f"conv-{tenant}",
        "parameters": base_params,
    }
    res1 = await async_client.post(
        "/api/v1/chat/stream", headers=auth_headers(tenant), json=base_payload
    )
    assert res1.status_code == 200
    done1 = next((d for e, d in parse_sse_events(res1.text) if e == "done"), None)
    assert done1 is not None and "cache_hit" not in done1

    variant_payload = {
        "prompt": STREAM_PROMPT,
        "conversation_id": f"conv-{tenant}-v",
        "parameters": variant_params,
    }
    res2 = await async_client.post(
        "/api/v1/chat/stream", headers=auth_headers(tenant), json=variant_payload
    )
    assert res2.status_code == 200
    done2 = next((d for e, d in parse_sse_events(res2.text) if e == "done"), None)
    assert done2 is not None
    if allow_semantic_hit:
        assert done2.get("cache_hit") != "exact", (
            f"HTTP exact hit when '{dimension}' differs"
        )
    else:
        assert "cache_hit" not in done2, f"HTTP false hit when '{dimension}' differs"


GATEWAY_BASE_MESSAGES = [
    {"role": "system", "content": "You are a financial analysis gateway."},
    {"role": "user", "content": "Analyze the working capital position"},
]


@pytest.mark.asyncio
async def test_scenario_21_gateway_http_exact_hit_and_identity_isolation(
    async_client: AsyncClient, monkeypatch: pytest.MonkeyPatch
) -> None:
    """HTTP gateway: identical replay hits; changed dims must not hit."""
    settings = get_settings()
    monkeypatch.setattr(settings, "JWT_ALGORITHM", "HS256")
    tenant = unique_tenant("r03-http-gw")
    headers = auth_headers(tenant)

    base_request = {
        "model": "gpt-4o",
        "messages": GATEWAY_BASE_MESSAGES,
        "temperature": 0.7,
        "max_tokens": 512,
    }

    res1 = await async_client.post(
        "/api/v1/gateway/chat/completions", headers=headers, json=base_request
    )
    assert res1.status_code == 200
    assert res1.json()["cached"] is False

    res2 = await async_client.post(
        "/api/v1/gateway/chat/completions", headers=headers, json=base_request
    )
    assert res2.status_code == 200
    body2 = res2.json()
    assert body2["cached"] is True, "identical gateway replay did not hit"
    assert (
        body2["choices"][0]["message"]["content"]
        == res1.json()["choices"][0]["message"]["content"]
    )

    # Temperature and max_tokens are generation-relevant.
    for field, value in (("temperature", 0.0), ("max_tokens", 64)):
        variant = dict(base_request)
        variant[field] = value
        res_variant = await async_client.post(
            "/api/v1/gateway/chat/completions", headers=headers, json=variant
        )
        assert res_variant.status_code == 200
        assert res_variant.json()["cached"] is False, (
            f"gateway false hit when '{field}' differs"
        )

    # Tools and response_format are generation-relevant.
    variant_tools = dict(base_request)
    variant_tools["tools"] = [
        {"type": "function", "function": {"name": "gw_calc", "parameters": {}}}
    ]
    res_tools = await async_client.post(
        "/api/v1/gateway/chat/completions", headers=headers, json=variant_tools
    )
    assert res_tools.json()["cached"] is False

    variant_rf = dict(base_request)
    variant_rf["response_format"] = {"type": "json_object"}
    res_rf = await async_client.post(
        "/api/v1/gateway/chat/completions", headers=headers, json=variant_rf
    )
    assert res_rf.json()["cached"] is False

    # A different tenant must not hit tenant-isolated entries.
    res_other_tenant = await async_client.post(
        "/api/v1/gateway/chat/completions",
        headers=auth_headers(unique_tenant("r03-http-gw-other")),
        json=base_request,
    )
    assert res_other_tenant.json()["cached"] is False


@pytest.mark.asyncio
async def test_scenario_22_gateway_http_no_false_hit_on_tool_call_structure(
    async_client: AsyncClient, monkeypatch: pytest.MonkeyPatch
) -> None:
    """HTTP gateway regression: tool-call message structure must be part of identity.

    The gateway previously flattened messages to (role, content), so a
    conversation with assistant tool_calls and tool_call_id-tagged tool
    results collided with a structurally different conversation.
    """
    settings = get_settings()
    monkeypatch.setattr(settings, "JWT_ALGORITHM", "HS256")
    tenant = unique_tenant("r03-http-gw-tool")
    headers = auth_headers(tenant)

    request_with_tools = {
        "model": "gpt-4o",
        "temperature": 0.7,
        "max_tokens": 512,
        "messages": [
            {"role": "user", "content": "Check account 123"},
            {
                "role": "assistant",
                "content": "",
                "tool_calls": [
                    {
                        "id": "call_AAA",
                        "function": {"name": "get_balance", "arguments": "{}"},
                    }
                ],
            },
            {
                "role": "tool",
                "content": "Balance is $1,000,000",
                "tool_call_id": "call_AAA",
                "name": "get_balance",
            },
            {"role": "user", "content": "Now summarize"},
        ],
    }
    request_without_tool_structure = {
        "model": "gpt-4o",
        "temperature": 0.7,
        "max_tokens": 512,
        "messages": [
            {"role": "user", "content": "Check account 123"},
            {"role": "assistant", "content": ""},
            {"role": "tool", "content": "Balance is $1,000,000"},
            {"role": "user", "content": "Now summarize"},
        ],
    }

    res1 = await async_client.post(
        "/api/v1/gateway/chat/completions",
        headers=headers,
        json=request_with_tools,
    )
    assert res1.status_code == 200
    assert res1.json()["cached"] is False

    res2 = await async_client.post(
        "/api/v1/gateway/chat/completions",
        headers=headers,
        json=request_without_tool_structure,
    )
    assert res2.status_code == 200
    assert res2.json()["cached"] is False, (
        "structurally different conversation hit the exact cache (message "
        "fields name/tool_call_id/tool_calls dropped from identity)"
    )

    res3 = await async_client.post(
        "/api/v1/gateway/chat/completions",
        headers=headers,
        json=request_with_tools,
    )
    assert res3.json()["cached"] is True, "identical replay lost its cache hit"


# ---------------------------------------------------------------------------
# Section 4 — Real Redis persistence (CI: Redis service; local: skipped)
# ---------------------------------------------------------------------------


@pytest.mark.skipif(
    not REDIS_AVAILABLE, reason="Redis not reachable at settings.REDIS_URL"
)
@pytest.mark.asyncio
async def test_scenario_23_exact_entry_persists_across_manager_instances_via_redis() -> (
    None
):
    """Real Redis roundtrip: an entry set by one manager is hit by another."""
    manager_a = SemanticCacheManager()
    manager_b = SemanticCacheManager()
    tenant = unique_tenant("r03-redis")

    await manager_a.set(
        prompt="Redis persistence probe",
        tenant_id=tenant,
        response="Response stored in real Redis",
        model="gpt-4o",
        provider="openai",
    )

    # manager_b shares no in-process state; a hit proves real Redis storage.
    hit = await manager_b.get(
        "Redis persistence probe",
        tenant_id=tenant,
        model="gpt-4o",
        provider="openai",
    )
    assert hit is not None
    assert hit.cache_type == "exact"
    assert hit.response == "Response stored in real Redis"

    # Cross-instance tenant isolation through real Redis.
    other = await manager_b.get(
        "Redis persistence probe", tenant_id=unique_tenant("r03-redis-other")
    )
    assert other is None


@pytest.mark.skipif(
    not REDIS_AVAILABLE, reason="Redis not reachable at settings.REDIS_URL"
)
@pytest.mark.asyncio
async def test_scenario_24_redis_ttl_expiry_is_honored() -> None:
    """Real Redis TTL: expired exact entries must not be served cross-instance."""
    manager_a = SemanticCacheManager()
    manager_b = SemanticCacheManager()
    tenant = unique_tenant("r03-redis-ttl")

    await manager_a.set(
        prompt="Redis TTL probe",
        tenant_id=tenant,
        response="Short-lived response",
        ttl_seconds=1,
    )
    fresh = await manager_b.get("Redis TTL probe", tenant_id=tenant)
    assert fresh is not None

    await asyncio.sleep(1.1)
    expired = await manager_b.get("Redis TTL probe", tenant_id=tenant)
    assert expired is None, "expired entry served through real Redis"


# ---------------------------------------------------------------------------
# Section 5 — GET/SET identity-function symmetry
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_scenario_25_get_and_set_use_one_identity_function() -> None:
    """SET and GET must derive the same key for equivalent request shapes."""
    cache = SemanticCacheManager(similarity_threshold=2.0)
    tenant = unique_tenant("r03-symmetry")
    await cache.invalidate(tenant)

    tools = [{"type": "function", "function": {"name": "tax_calc"}}]
    rf = {"type": "json_object"}

    # SET via parameters dict (tools/response_format/system inside parameters).
    await cache.set(
        prompt="Compute effective tax rate",
        tenant_id=tenant,
        response="Effective tax rate is 24%",
        model="gpt-4o",
        provider="openai",
        parameters={
            "system_instructions": "You are an accountant.",
            "tools": tools,
            "response_format": rf,
            "temperature": 0.2,
        },
    )

    # GET via explicit kwargs must hit the same identity (both sides
    # synthesize [{role: user, content: prompt}] when no messages are given).
    hit_explicit = await cache.get(
        "Compute effective tax rate",
        tenant_id=tenant,
        model="gpt-4o",
        provider="openai",
        system_instructions="You are an accountant.",
        tools=tools,
        response_format=rf,
        generation_params={"temperature": 0.2},
    )
    assert hit_explicit is not None, "explicit-kwargs GET missed a parameters-SET entry"

    # GET via the same parameters shape must hit too.
    hit_params = await cache.get(
        "Compute effective tax rate",
        tenant_id=tenant,
        model="gpt-4o",
        provider="openai",
        parameters={
            "system_instructions": "You are an accountant.",
            "tools": tools,
            "response_format": rf,
            "temperature": 0.2,
        },
    )
    assert hit_params is not None, "parameters-shape GET missed a parameters-SET entry"

    # Object-style messages (attribute access) must serialize like dicts.
    class _Msg:
        def __init__(self, role: str, content: str) -> None:
            self.role = role
            self.content = content

    hit_objects = await cache.get(
        "Compute effective tax rate",
        tenant_id=tenant,
        model="gpt-4o",
        provider="openai",
        system_instructions="You are an accountant.",
        messages=[_Msg("user", "Compute effective tax rate")],
        tools=tools,
        response_format=rf,
        generation_params={"temperature": 0.2},
    )
    assert hit_objects is not None, "object-style messages broke identity symmetry"
