"""Comprehensive Multi-Tenant Isolation Test Suite for JakeAI RAG Platform.

Validates Section 2 of 04_RAG.md:
"Every retrieval path must enforce tenant scope.
Test:
tenant A document
tenant B query
=> document A must never appear"
"""

import asyncio

import pytest

from app.rag.bm25 import BM25Retriever
from app.rag.context_selector import ContextSelector
from app.rag.ingestion import DocumentIngestRequest
from app.rag.models import DocumentChunk
from app.rag.pipeline import RAGPipeline
from app.rag.retriever import HybridRetriever
from app.rag.vector_store import QdrantVectorStore


@pytest.fixture
def tenant_isolation_chunks() -> dict[str, list[DocumentChunk]]:
    """Create distinct confidential corporate documents across separate tenants."""
    chunks_alpha = [
        DocumentChunk(
            chunk_id="chunk-alpha-001",
            content="AlphaCorp confidential Q3 profit reached $42,500,000 with secret acquisition target Project Titan.",
            tenant_id="tenant-alpha",
            source="AlphaCorp Board Minutes",
            score=0.95,
        ),
        DocumentChunk(
            chunk_id="chunk-alpha-002",
            content="AlphaCorp operating margin expanded to 44.2% driven by proprietary AI enterprise software.",
            tenant_id="tenant-alpha",
            source="AlphaCorp Executive Filing",
            score=0.90,
        ),
    ]

    chunks_beta = [
        DocumentChunk(
            chunk_id="chunk-beta-001",
            content="BetaGroup retail revenue was $18,200,000 with operating expenses of $14,100,000 in Q3.",
            tenant_id="tenant-beta",
            source="BetaGroup 10-Q Report",
            score=0.92,
        ),
        DocumentChunk(
            chunk_id="chunk-beta-002",
            content="BetaGroup retail store count reached 150 locations with 12.5% same-store sales growth.",
            tenant_id="tenant-beta",
            source="BetaGroup Investor Presentation",
            score=0.88,
        ),
    ]

    return {"tenant-alpha": chunks_alpha, "tenant-beta": chunks_beta}


def test_bm25_strict_tenant_isolation(
    tenant_isolation_chunks: dict[str, list[DocumentChunk]],
) -> None:
    """Verify BM25 sparse index never returns Tenant Alpha documents for Tenant Beta queries."""
    bm25 = BM25Retriever()
    # Ingest documents from both tenants into same retriever
    bm25.add_documents(tenant_isolation_chunks["tenant-alpha"])
    bm25.add_documents(tenant_isolation_chunks["tenant-beta"])

    # Tenant Beta queries using exact terms present in Alpha's confidential filing
    results_for_beta = bm25.search(
        query="AlphaCorp profit $42,500,000 Project Titan acquisition",
        tenant_id="tenant-beta",
        top_k=10,
    )

    # Must return ZERO AlphaCorp documents
    assert len(results_for_beta) == 0 or all(
        c.tenant_id == "tenant-beta" for c in results_for_beta
    )
    for chunk in results_for_beta:
        assert chunk.tenant_id == "tenant-beta"
        assert "AlphaCorp" not in chunk.content
        assert "Project Titan" not in chunk.content

    # In contrast, Tenant Alpha querying the same text finds the exact document
    results_for_alpha = bm25.search(
        query="Project Titan profit",
        tenant_id="tenant-alpha",
        top_k=5,
    )
    assert len(results_for_alpha) >= 1
    assert results_for_alpha[0].chunk_id == "chunk-alpha-001"
    assert results_for_alpha[0].tenant_id == "tenant-alpha"


@pytest.mark.asyncio
async def test_qdrant_vector_store_strict_tenant_isolation(
    tenant_isolation_chunks: dict[str, list[DocumentChunk]],
) -> None:
    """Verify dense vector store enforces tenant boundary filtering in memory and live store."""
    store = QdrantVectorStore()
    all_chunks = (
        tenant_isolation_chunks["tenant-alpha"] + tenant_isolation_chunks["tenant-beta"]
    )
    await store.upsert(all_chunks)

    # Beta searches for Alpha's exact dense semantic concepts
    beta_hits = await store.search(
        query="proprietary AI enterprise software acquisition profit",
        tenant_id="tenant-beta",
        top_k=10,
    )

    for hit in beta_hits:
        assert hit.tenant_id == "tenant-beta"
        assert "AlphaCorp" not in hit.content
        assert "Project Titan" not in hit.content


@pytest.mark.asyncio
async def test_hybrid_retriever_cross_tenant_rejection(
    tenant_isolation_chunks: dict[str, list[DocumentChunk]],
) -> None:
    """Verify end-to-end HybridRetriever filters candidate pools to tenant scope."""
    retriever = HybridRetriever()
    all_chunks = (
        tenant_isolation_chunks["tenant-alpha"] + tenant_isolation_chunks["tenant-beta"]
    )
    await retriever.index_documents(all_chunks)

    # Beta queries for Alpha information
    res_beta = await retriever.retrieve(
        query="AlphaCorp $42,500,000 profit",
        tenant_id="tenant-beta",
        top_k=5,
    )

    assert res_beta.tenant_id == "tenant-beta"
    for chunk in res_beta.chunks:
        assert chunk.tenant_id == "tenant-beta"
        assert "AlphaCorp" not in chunk.content

    # Alpha queries for Beta information
    res_alpha = await retriever.retrieve(
        query="BetaGroup retail store count 150 locations",
        tenant_id="tenant-alpha",
        top_k=5,
    )

    assert res_alpha.tenant_id == "tenant-alpha"
    for chunk in res_alpha.chunks:
        assert chunk.tenant_id == "tenant-alpha"
        assert "BetaGroup" not in chunk.content


def test_context_selector_foreign_tenant_rejection(
    tenant_isolation_chunks: dict[str, list[DocumentChunk]],
) -> None:
    """Verify ContextSelector detects and purges any foreign tenant chunks in candidates."""
    selector = ContextSelector()
    # Maliciously or accidentally mixed candidates
    mixed_candidates = (
        tenant_isolation_chunks["tenant-alpha"] + tenant_isolation_chunks["tenant-beta"]
    )

    res = selector.select_context(
        candidates=mixed_candidates,
        query="enterprise financial performance",
        tenant_id="tenant-beta",
        max_tokens=1000,
    )

    # Result must contain ONLY tenant-beta chunks
    assert len(res.selected_chunks) >= 1
    for chunk in res.selected_chunks:
        assert chunk.tenant_id == "tenant-beta"
        assert "AlphaCorp" not in chunk.content

    assert "AlphaCorp" not in res.formatted_context
    assert "BetaGroup" in res.formatted_context


@pytest.mark.asyncio
async def test_rag_pipeline_end_to_end_tenant_isolation() -> None:
    """Verify the 10-step RAGPipeline guarantees zero cross-tenant evidence leakage."""
    retriever = HybridRetriever()
    pipeline = RAGPipeline(retriever=retriever)

    # 1. Ingest Alpha document
    alpha_req = DocumentIngestRequest(
        content="Confidential Patent Alpha-992 discloses quantum resistant encryption keys.",
        source="Alpha Patent Filing",
        metadata={"classification": "top-secret"},
    )
    await pipeline.ingest_document(request=alpha_req, tenant_id="tenant-alpha")

    # 2. Ingest Beta document
    beta_req = DocumentIngestRequest(
        content="Beta public logistics fleet operates 450 electric freight vehicles.",
        source="Beta ESG Report",
        metadata={"classification": "public"},
    )
    await pipeline.ingest_document(request=beta_req, tenant_id="tenant-beta")

    # 3. Tenant Beta asks for Alpha's secret patent
    beta_gen = await pipeline.generate_grounded_answer(
        query="What are the quantum resistant encryption keys in Patent Alpha-992?",
        tenant_id="tenant-beta",
    )

    # Tenant Beta must NEVER see Patent Alpha-992
    assert "Patent Alpha-992" not in beta_gen.answer
    assert "quantum resistant encryption" not in beta_gen.answer
    for cite in beta_gen.citations:
        assert cite.tenant_id == "tenant-beta"
        assert "Alpha" not in cite.source

    # 4. Context selection for Beta must have 0 Alpha chunks
    for chk in beta_gen.context_selection.selected_chunks:
        assert chk.tenant_id == "tenant-beta"


@pytest.mark.asyncio
async def test_concurrent_multi_tenant_isolation_stress() -> None:
    """Stress test 5 concurrent tenants querying their own and peer data simultaneously."""
    retriever = HybridRetriever()
    pipeline = RAGPipeline(retriever=retriever)

    # Ingest unique data for 5 tenants
    tenants = [f"tenant-{i}" for i in range(1, 6)]
    for idx, t in enumerate(tenants):
        req = DocumentIngestRequest(
            content=f"Unique Secret Token for {t} is TOKEN_{idx}_{t.upper()}_KEY.",
            source=f"Vault {t}",
        )
        await pipeline.ingest_document(request=req, tenant_id=t)

    # Query all 5 in parallel
    async def query_tenant(requester: str, target_secret: str) -> None:
        _retrieval, selection = await pipeline.retrieve_and_select_context(
            query=f"What is {target_secret}?",
            tenant_id=requester,
        )
        for chunk in selection.selected_chunks:
            assert chunk.tenant_id == requester, (
                f"Leakage: {chunk.tenant_id} leaked to {requester}"
            )

    tasks = []
    # Each tenant queries for someone else's secret token
    for i, t in enumerate(tenants):
        peer = tenants[(i + 1) % len(tenants)]
        target_peer_token = f"TOKEN_{(i + 1) % len(tenants)}_{peer.upper()}_KEY"
        tasks.append(query_tenant(t, target_peer_token))

    await asyncio.gather(*tasks)
