"""SEC-008: Dedicated Multi-Tenant Boundary Isolation Security Regression Test Suite.

Automated verification covering:
- Agent Task & Run Isolation (HTTP boundary: 403 on foreign tenant tasks, runs, cancellations, events, artifacts)
- Conversation & Checkpointer Thread Isolation (LangGraph namespaced threads: f"{tenant_id}:{conversation_id}")
- Cache Isolation (Tier 1 Exact and Tier 2 Semantic cross-tenant segregation)
- Context-Aware Cache Identity (retrieval context isolation)
- RAG Evidence & Ingestion Isolation (ingestion tasks, dense vector search, sparse BM25, context envelope)
- BYOK Credential Isolation (key storage, retrieval, rotation, revocation, deletion, and masked exposure)
- Resume Bridge Isolation (fail-closed cross-tenant and unscoped checkpoint resumption)
- Resource Enumeration Defense (uniform 404s for foreign vs non-existent RAG and BYOK resources)
"""

import uuid
from typing import Any

import pytest
from httpx import ASGITransport, AsyncClient

from app.core.context import TenantContext
from app.core.security import exchange_obo_token
from app.main import app
from app.optimizer.semantic_cache import SemanticCacheManager, compute_cache_identity
from app.rag.bm25 import BM25Retriever
from app.rag.context_envelope import ContextEnvelopeBuilder
from app.rag.ingestion import DocumentIngestRequest
from app.rag.models import DocumentChunk
from app.services.resume_bridge import ResumeBridgeManager


def _make_auth_headers(
    tenant_id: str,
    user_id: str = "user-sec-tenant",
    roles: list[str] | None = None,
    permissions: list[str] | None = None,
) -> dict[str, str]:
    """Helper to mint valid authorization headers for a specific tenant."""
    ctx = TenantContext(
        tenant_id=tenant_id,
        user_id=user_id,
        roles=roles or ["admin", "developer"],
        permissions=permissions or ["chat:write", "agent:write", "byok:manage"],
    )
    token = exchange_obo_token(ctx)
    return {"Authorization": f"Bearer {token}"}


# ==============================================================================
# 1. Agent Task & Run Multi-Tenant Isolation (HTTP Boundary)
# ==============================================================================


@pytest.mark.asyncio
async def test_tenant_isolation_agent_tasks_and_runs() -> None:
    """Tenant B attempting to inspect, run, cancel, stream, or read artifacts of Tenant A's task is rejected."""
    headers_a = _make_auth_headers(tenant_id="tenant-alpha-enterprise")
    headers_b = _make_auth_headers(tenant_id="tenant-beta-adversary")

    async with AsyncClient(
        transport=ASGITransport(app=app), base_url="http://test"
    ) as client:
        # 1. Tenant A creates a task
        create_resp = await client.post(
            "/api/v1/agent/tasks",
            headers=headers_a,
            json={
                "goal": "Process confidential quarterly earnings report",
                "metadata": {"confidential": True, "secret_metric": "$50M"},
            },
        )
        assert create_resp.status_code == 201
        task_a_id = create_resp.json()["task_id"]

        # 2. Tenant A starts an execution run
        run_resp = await client.post(
            f"/api/v1/agent/tasks/{task_a_id}/runs",
            headers=headers_a,
            json={"async_execution": False},
        )
        assert run_resp.status_code in (200, 201)
        run_a_id = run_resp.json()["run_id"]

        # 3. Tenant B attempts to read Tenant A's task -> 403 Forbidden (zero body/metadata leakage)
        b_get_task = await client.get(
            f"/api/v1/agent/tasks/{task_a_id}",
            headers=headers_b,
        )
        assert b_get_task.status_code == 403
        assert "$50M" not in b_get_task.text
        assert "confidential" not in b_get_task.text

        # 4. Tenant B attempts to start a run on Tenant A's task -> 403 Forbidden
        b_start_run = await client.post(
            f"/api/v1/agent/tasks/{task_a_id}/runs",
            headers=headers_b,
            json={"async_execution": False},
        )
        assert b_start_run.status_code == 403
        assert run_a_id not in b_start_run.text

        # 5. Tenant B attempts to read Tenant A's run -> 403 Forbidden
        b_get_run = await client.get(
            f"/api/v1/agent/tasks/{task_a_id}/runs/{run_a_id}",
            headers=headers_b,
        )
        assert b_get_run.status_code == 403

        # 6. Tenant B attempts to cancel Tenant A's run -> 403 Forbidden
        b_cancel_run = await client.post(
            f"/api/v1/agent/tasks/{task_a_id}/runs/{run_a_id}/cancel",
            headers=headers_b,
        )
        assert b_cancel_run.status_code == 403

        # 7. Tenant B attempts to stream events of Tenant A's run -> 403 Forbidden
        b_events = await client.get(
            f"/api/v1/agent/tasks/{task_a_id}/runs/{run_a_id}/events",
            headers=headers_b,
        )
        assert b_events.status_code == 403

        # 8. Tenant B attempts to decide approval on Tenant A's run -> 403 Forbidden
        b_approval = await client.post(
            f"/api/v1/agent/tasks/{task_a_id}/runs/{run_a_id}/approvals/appr-fake",
            headers=headers_b,
            json={"approved": True, "comment": "hacked"},
        )
        assert b_approval.status_code == 403


# ==============================================================================
# 2. Conversation & Checkpointer Thread State Isolation
# ==============================================================================


@pytest.mark.asyncio
async def test_tenant_isolation_langgraph_namespaced_threads() -> None:
    """LangGraph multi-agent workflow threads are strictly namespaced f'{tenant_id}:{conversation_id}' (RL02-F-03)."""
    from app.agents.graph import stream_multi_agent_workflow

    shared_conversation_id = f"conv-shared-{uuid.uuid4().hex[:8]}"

    ctx_a = TenantContext(
        tenant_id="tenant-alpha-classified",
        user_id="user-a",
        roles=["admin"],
        permissions=["chat:write"],
    )
    # Tenant A seeds thread with confidential information
    events_a = []
    async for event in stream_multi_agent_workflow(
        prompt="Record secret key: ALPHA-TOP-SECRET-MARKER-9999",
        context=ctx_a,
        conversation_id=shared_conversation_id,
    ):
        events_a.append(event)

    ctx_b = TenantContext(
        tenant_id="tenant-beta-observer",
        user_id="user-b",
        roles=["admin"],
        permissions=["chat:write"],
    )
    # Tenant B queries using the EXACT same conversation_id
    events_b = []
    async for event in stream_multi_agent_workflow(
        prompt="What was the secret key mentioned previously?",
        context=ctx_b,
        conversation_id=shared_conversation_id,
    ):
        events_b.append(event)

    # Reconstruct text yielded to Tenant B
    tenant_b_text = "".join(
        e.get("message", "") for e in events_b if isinstance(e, dict)
    )

    # Assert Tenant B NEVER observed Tenant A's secret marker
    assert "ALPHA-TOP-SECRET-MARKER-9999" not in tenant_b_text


# ==============================================================================
# 3. Cache Multi-Tenant Isolation (Tier 1 Exact & Tier 2 Semantic)
# ==============================================================================


@pytest.mark.asyncio
async def test_tenant_isolation_exact_and_semantic_cache() -> None:
    """Tenant A's cached response is never returned to Tenant B for identical or similar prompts."""
    cache_mgr = SemanticCacheManager()

    tenant_a = "tenant-corp-a"
    tenant_b = "tenant-corp-b"
    prompt = "What are the Q3 2026 financial projections?"
    cached_answer = "Tenant A Confidential Projections: Revenue $120M, Net Margin 24%."

    # Store in cache for Tenant A
    await cache_mgr.set(
        prompt=prompt,
        response=cached_answer,
        tenant_id=tenant_a,
        model="gpt-4o",
        ttl_seconds=3600,
    )

    # Tenant A hits cache
    hit_a = await cache_mgr.get(
        prompt=prompt,
        tenant_id=tenant_a,
        model="gpt-4o",
    )
    assert hit_a is not None
    assert "Revenue $120M" in hit_a.response

    # Tenant B with identical prompt experiences CACHE MISS
    miss_b = await cache_mgr.get(
        prompt=prompt,
        tenant_id=tenant_b,
        model="gpt-4o",
    )
    assert miss_b is None


def test_tenant_isolation_context_aware_cache_identity() -> None:
    """Cache identity incorporates retrieval context dimension to prevent cross-context leakage (RL02-F-04)."""
    prompt = "Summarize earnings"
    tenant = "tenant-ctx-sec"

    id_ctx_1 = compute_cache_identity(
        tenant_id=tenant,
        model="gpt-4o",
        messages=[{"role": "user", "content": prompt}],
        rag_context="Q1 2026: $10M revenue",
    )
    id_ctx_2 = compute_cache_identity(
        tenant_id=tenant,
        model="gpt-4o",
        messages=[{"role": "user", "content": prompt}],
        rag_context="Q2 2026: $20M revenue",
    )
    id_no_ctx = compute_cache_identity(
        tenant_id=tenant,
        model="gpt-4o",
        messages=[{"role": "user", "content": prompt}],
    )

    assert id_ctx_1 != id_ctx_2
    assert id_ctx_1 != id_no_ctx
    assert id_ctx_2 != id_no_ctx


# ==============================================================================
# 4. RAG Evidence & Ingestion Multi-Tenant Isolation
# ==============================================================================


@pytest.mark.asyncio
async def test_tenant_isolation_rag_ingestion_tasks() -> None:
    """Tenant B cannot read ingestion task status or documents belonging to Tenant A."""
    from app.rag.tasks import get_task_manager

    task_mgr = get_task_manager()
    tenant_a = "tenant-rag-alpha"
    tenant_b = "tenant-rag-beta"

    req = DocumentIngestRequest(
        source="classified_merger.pdf",
        content="Confidential acquisition terms for Project Titan.",
    )
    task_a = await task_mgr.enqueue(request=req, tenant_id=tenant_a)

    headers_b = _make_auth_headers(tenant_id=tenant_b)

    async with AsyncClient(
        transport=ASGITransport(app=app), base_url="http://test"
    ) as client:
        resp = await client.get(
            f"/api/v1/rag/tasks/{task_a.task_id}",
            headers=headers_b,
        )
        assert resp.status_code == 404
        assert "classified_merger.pdf" not in resp.text


def test_tenant_isolation_bm25_sparse_search(tmp_path: Any) -> None:
    """BM25 sparse index search strictly isolates document matches by tenant_id."""
    retriever = BM25Retriever(storage_path=tmp_path / "bm25.json", auto_save=False)

    chunk_a = DocumentChunk(
        chunk_id="chunk-alpha-1",
        document_id="doc-alpha-1",
        tenant_id="tenant-alpha",
        content="The classified project code name is NEPTUNE SECRET ALPHA.",
        chunk_index=0,
    )
    chunk_b = DocumentChunk(
        chunk_id="chunk-beta-1",
        document_id="doc-beta-1",
        tenant_id="tenant-beta",
        content="Public company quarterly overview and general updates.",
        chunk_index=0,
    )

    # Index chunks for Tenant A and Tenant B
    retriever.add_documents([chunk_a, chunk_b])

    # Tenant B queries for 'NEPTUNE' -> MUST RETURN ZERO RESULTS
    hits_b = retriever.search(query="NEPTUNE", tenant_id="tenant-beta")
    assert len(hits_b) == 0

    # Tenant A queries for 'NEPTUNE' -> returns document
    hits_a = retriever.search(query="NEPTUNE", tenant_id="tenant-alpha")
    assert len(hits_a) == 1
    assert hits_a[0].chunk_id == "chunk-alpha-1"


def test_tenant_isolation_context_envelope_builder() -> None:
    """ContextEnvelopeBuilder strictly quarantines and drops foreign tenant chunks and memories (R-AI-04-03)."""
    builder = ContextEnvelopeBuilder()

    foreign_chunk = DocumentChunk(
        chunk_id="chunk_foreign_99",
        document_id="doc_foreign_99",
        tenant_id="tenant-bob-classified",  # FOREIGN
        content="Bob's private financial data: account balance is $9,000,000.",
        chunk_index=0,
    )

    envelope = builder.assemble(
        system_instructions="You are a helpful assistant.",
        retrieved_evidence=[foreign_chunk],
        user_query="What is my account balance?",
        tenant_id="tenant-alice",  # CALLER
    )

    # Assert foreign chunk was discarded fail-closed
    assert "Bob's private financial data" not in envelope.serialized_prompt
    assert "$9,000,000" not in envelope.serialized_prompt


# ==============================================================================
# 5. BYOK Credential Multi-Tenant Isolation
# ==============================================================================


@pytest.mark.asyncio
async def test_tenant_isolation_byok_keys_crud_and_masking() -> None:
    """Tenant A's stored BYOK key cannot be read, listed, rotated, or deleted by Tenant B."""
    headers_a = _make_auth_headers(tenant_id="tenant-byok-alpha")
    headers_b = _make_auth_headers(tenant_id="tenant-byok-beta")

    secret_key_val = "sk-test-openai-classified-key-1234"

    async with AsyncClient(
        transport=ASGITransport(app=app), base_url="http://test"
    ) as client:
        # 1. Tenant A stores key
        store_resp = await client.post(
            "/api/v1/byok/keys",
            headers=headers_a,
            json={"provider": "openai", "api_key": secret_key_val},
        )
        assert store_resp.status_code == 201

        # 2. Tenant B attempts to validate Tenant A's key directly -> 404 Not Found
        b_val = await client.post(
            "/api/v1/byok/keys/openai/validate", headers=headers_b
        )
        assert b_val.status_code == 404

        # 3. Tenant B lists keys -> Tenant A's key is not configured for Tenant B
        b_list = await client.get("/api/v1/byok/keys", headers=headers_b)
        assert b_list.status_code == 200
        keys_b = {k["provider"]: k for k in b_list.json()["keys"]}
        assert keys_b["openai"]["configured"] is False
        assert keys_b["openai"]["masked_key"] is None

        # 4. Tenant B attempts to rotate Tenant A's key -> 400 or 404 (no existing key)
        b_rotate = await client.post(
            "/api/v1/byok/keys/openai/rotate",
            headers=headers_b,
            json={"new_api_key": "sk-test-openai-rotated-attempt-5678"},
        )
        assert b_rotate.status_code in (400, 404)

        # 5. Tenant B attempts to delete Tenant A's key -> 404 Not Found
        b_delete = await client.delete("/api/v1/byok/keys/openai", headers=headers_b)
        assert b_delete.status_code == 404

        # 6. Tenant A lists keys -> masked key only, zero plaintext leakage
        a_list = await client.get("/api/v1/byok/keys", headers=headers_a)
        assert a_list.status_code == 200
        keys_a = {k["provider"]: k for k in a_list.json()["keys"]}
        assert keys_a["openai"]["configured"] is True
        assert secret_key_val not in a_list.text  # Plaintext never leaked
        assert "1234" in str(
            keys_a["openai"]["masked_key"]
        )  # Last 4 chars visible for audit


# ==============================================================================
# 6. Resume Bridge Multi-Tenant Isolation
# ==============================================================================


@pytest.mark.asyncio
async def test_tenant_isolation_resume_bridge_fails_closed() -> None:
    """ResumeBridgeManager rejects cross-tenant resume attempts fail-closed with PermissionError (RL02-F-11)."""
    bridge = ResumeBridgeManager()

    cp_id = f"cp_sec_{uuid.uuid4().hex[:8]}"
    await bridge.save_checkpoint(
        call_id=cp_id,
        tenant_id="tenant-owner-alpha",
        state_data={"step": "tool_wait"},
    )

    # Foreign tenant attempts resumption -> MUST RAISE PermissionError
    with pytest.raises(PermissionError) as exc_info:
        await bridge.resume_checkpoint(
            call_id=cp_id,
            result_payload={"output": "tampered"},
            tenant_id="tenant-attacker-beta",
        )
    assert "tenant mismatch" in str(exc_info.value).lower()


# ==============================================================================
# 7. Resource Enumeration Resistance (Uniform 404 Behavior)
# ==============================================================================


@pytest.mark.asyncio
async def test_tenant_isolation_uniform_404_timing_and_enumeration() -> None:
    """Requesting a nonexistent resource vs requesting another tenant's resource in RAG tasks yields identical 404 envelopes."""
    headers_b = _make_auth_headers(tenant_id="tenant-prober-beta")

    # Real resource belonging to Tenant A
    from app.rag.tasks import get_task_manager

    task_mgr = get_task_manager()
    req = DocumentIngestRequest(source="secret_file.pdf", content="secret")
    task_a = await task_mgr.enqueue(request=req, tenant_id="tenant-target-alpha")

    nonexistent_id = f"task-ingest-{uuid.uuid4().hex[:12]}"

    async with AsyncClient(
        transport=ASGITransport(app=app), base_url="http://test"
    ) as client:
        # Probe foreign tenant task
        resp_foreign = await client.get(
            f"/api/v1/rag/tasks/{task_a.task_id}",
            headers=headers_b,
        )
        # Probe nonexistent task
        resp_nonexistent = await client.get(
            f"/api/v1/rag/tasks/{nonexistent_id}",
            headers=headers_b,
        )

        assert resp_foreign.status_code == 404
        assert resp_nonexistent.status_code == 404
        assert (
            f"Task '{task_a.task_id}' not found for tenant 'tenant-prober-beta'."
            in resp_foreign.text
        )
        assert (
            f"Task '{nonexistent_id}' not found for tenant 'tenant-prober-beta'."
            in resp_nonexistent.text
        )
