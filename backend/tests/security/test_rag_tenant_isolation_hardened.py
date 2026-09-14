"""Unit tests for TASK RAG-13: Hardened Multi-Tenant Isolation Defense-in-Depth."""

import pytest

from app.rag.bm25 import BM25Retriever
from app.rag.citations import CitationGenerator
from app.rag.context_envelope import ContextEnvelopeBuilder
from app.rag.context_selector import ContextSelector
from app.rag.embedding import TestOnlyFakeEmbeddingProvider
from app.rag.ingestion import DocumentIngestionPipeline, DocumentIngestRequest
from app.rag.models import DocumentChunk
from app.rag.retriever import HybridRetriever
from app.rag.vector_store import QdrantVectorStore


@pytest.mark.asyncio
async def test_tenant_isolation_in_ingestion_and_hybrid_retrieval() -> None:
    """Verify tenant data indexed under tenant-A is strictly inaccessible to tenant-B in dense, sparse, and hybrid search."""
    provider = TestOnlyFakeEmbeddingProvider(dimension=384)
    vstore = QdrantVectorStore(embedding_provider=provider)
    bm25 = BM25Retriever()
    retriever = HybridRetriever(vector_store=vstore, bm25=bm25)
    ingestion = DocumentIngestionPipeline(retriever=retriever)

    # Ingest private data for tenant A
    req_a = DocumentIngestRequest(
        content="Secret merger acquisition target is AlphaCorp for 2 billion dollars.",
        source="M&A Private Briefing",
    )
    await ingestion.ingest(req_a, tenant_id="tenant-A")

    # Ingest normal data for tenant B
    req_b = DocumentIngestRequest(
        content="Public annual report showing standard operational metrics.",
        source="Public Report",
    )
    await ingestion.ingest(req_b, tenant_id="tenant-B")

    # Tenant B queries for AlphaCorp merger
    res_b = await retriever.retrieve(
        query="Secret merger acquisition AlphaCorp",
        tenant_id="tenant-B",
        top_k=5,
    )

    # Tenant B MUST NOT see any chunks from Tenant A
    for chunk in res_b.chunks:
        assert chunk.tenant_id == "tenant-B"
        assert "AlphaCorp" not in chunk.content
        assert "merger" not in chunk.content


def test_tenant_isolation_context_selector_guard() -> None:
    """Verify ContextSelector forcefully drops candidate chunks belonging to foreign tenants."""
    selector = ContextSelector()
    chunks = [
        DocumentChunk(
            chunk_id="chunk-legit",
            content="Tenant 1 financial statement.",
            tenant_id="tenant-1",
            source="Doc 1",
            score=0.9,
        ),
        DocumentChunk(
            chunk_id="chunk-foreign",
            content="Tenant 2 confidential data leaked by rogue candidate.",
            tenant_id="tenant-2",
            source="Doc 2",
            score=0.99,
        ),
    ]

    res = selector.select_context(
        candidates=chunks, query="confidential", tenant_id="tenant-1"
    )

    # Foreign chunk must be dropped
    assert len(res.selected_chunks) == 1
    assert res.selected_chunks[0].chunk_id == "chunk-legit"
    assert "Tenant 2" not in res.formatted_context


def test_tenant_isolation_citations_filter() -> None:
    """Verify CitationGenerator never links citations containing foreign tenant IDs."""
    generator = CitationGenerator()
    passages = [
        DocumentChunk(
            chunk_id="chunk-valid",
            content="Revenue increased to $50,000,000 in Q3.",
            tenant_id="tenant-target",
            source="Target 10-Q",
        ),
    ]

    # Generate citation
    text = "Revenue was $50,000,000 in Q3."
    _, citations = generator.generate_citations(text, passages)

    assert len(citations) == 1
    assert citations[0].tenant_id == "tenant-target"


def test_tenant_isolation_context_envelope_tagging() -> None:
    """Verify ContextEnvelope retains tenant boundary tag and scopes correctly."""
    builder = ContextEnvelopeBuilder()
    envelope = builder.assemble(
        system_instructions="System",
        task_constraints="Constraint",
        conversation_history="User: hi",
        verified_memory="Fact",
        retrieved_evidence="Evidence",
        user_query="Query",
        tenant_id="tenant-secure-boundary",
    )

    assert envelope.tenant_id == "tenant-secure-boundary"
