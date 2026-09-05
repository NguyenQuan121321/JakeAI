"""Unit and integration tests for RAG engine, hybrid retrieval, and Self-RAG loop."""

from typing import TYPE_CHECKING

import pytest

from app.agents.verifier import verifier_node
from app.rag.bm25 import BM25Retriever
from app.rag.citations import CitationGenerator
from app.rag.models import DocumentChunk
from app.rag.reranker import CrossEncoderReranker
from app.rag.retriever import HybridRetriever
from app.rag.vector_store import QdrantVectorStore

if TYPE_CHECKING:
    from app.agents.state import AgentState


@pytest.fixture
def sample_chunks() -> list[DocumentChunk]:
    """Provide sample financial document chunks across multiple tenants."""
    return [
        DocumentChunk(
            chunk_id="chunk-acme-01",
            content=(
                "ACME Corp reported Q3 gross revenue of $5,000,000 "
                "and operating expenses of $3,200,000."
            ),
            tenant_id="tenant-acme",
            source="ACME Q3 Financial Statement",
        ),
        DocumentChunk(
            chunk_id="chunk-acme-02",
            content=(
                "ACME Corp operating margin is 36.0% with positive cash "
                "flow of $1,800,000."
            ),
            tenant_id="tenant-acme",
            source="ACME Q3 Executive Summary",
        ),
        DocumentChunk(
            chunk_id="chunk-globex-01",
            content=(
                "Globex Corporation reported revenue of $8,500,000 "
                "with expenses of $6,000,000."
            ),
            tenant_id="tenant-globex",
            source="Globex Annual Filing",
        ),
    ]


def test_bm25_retriever_search_and_tenant_isolation(
    sample_chunks: list[DocumentChunk],
) -> None:
    """Verify BM25 retrieval finds passages and strictly isolates tenant data."""
    bm25 = BM25Retriever()
    bm25.add_documents(sample_chunks)

    # 1. Search within tenant-acme
    results_acme = bm25.search("gross revenue expenses", tenant_id="tenant-acme")
    assert len(results_acme) >= 1
    assert results_acme[0].chunk_id == "chunk-acme-01"
    assert results_acme[0].score > 0.0

    # 2. Strict isolation: searching tenant-acme should NEVER return Globex docs
    for res in results_acme:
        assert res.tenant_id == "tenant-acme"
        assert "Globex" not in res.content

    # 3. Search within tenant-globex
    results_globex = bm25.search("revenue expenses", tenant_id="tenant-globex")
    assert len(results_globex) == 1
    assert results_globex[0].chunk_id == "chunk-globex-01"


@pytest.mark.asyncio
async def test_qdrant_vector_store_dense_search(
    sample_chunks: list[DocumentChunk],
) -> None:
    """Verify dense vector store indexes embeddings with tenant filtering."""
    store = QdrantVectorStore()
    await store.upsert(sample_chunks)

    results = await store.search(
        query="operating margin cash flow",
        tenant_id="tenant-acme",
        top_k=2,
    )
    assert len(results) >= 1
    assert results[0].tenant_id == "tenant-acme"
    assert results[0].score >= 0.0


def test_cross_encoder_reranker(sample_chunks: list[DocumentChunk]) -> None:
    """Verify CrossEncoderReranker combines streams and prioritizes exact matches."""
    reranker = CrossEncoderReranker()
    dense_candidates = [sample_chunks[1], sample_chunks[0]]
    sparse_candidates = [sample_chunks[0], sample_chunks[1]]

    reranked = reranker.rerank(
        query="operating margin 36.0%",
        dense_results=dense_candidates,
        sparse_results=sparse_candidates,
        top_k=2,
    )
    assert len(reranked) == 2
    # chunk-acme-02 contains exact phrase 'operating margin' and '36.0%'
    assert reranked[0].chunk_id == "chunk-acme-02"
    assert reranked[0].score >= reranked[1].score


@pytest.mark.asyncio
async def test_hybrid_retriever_pipeline(
    sample_chunks: list[DocumentChunk],
) -> None:
    """Verify end-to-end HybridRetriever indexing and parallel querying."""
    retriever = HybridRetriever()
    await retriever.index_documents(sample_chunks)

    result = await retriever.retrieve(
        query="gross revenue",
        tenant_id="tenant-acme",
        top_k=2,
    )
    assert result.tenant_id == "tenant-acme"
    assert len(result.chunks) >= 1
    assert result.latency_ms >= 0.0
    for chunk in result.chunks:
        assert chunk.tenant_id == "tenant-acme"


def test_citation_generator(sample_chunks: list[DocumentChunk]) -> None:
    """Verify CitationGenerator inserts footnotes and generates markdown cards."""
    generator = CitationGenerator()
    text = (
        "ACME Corp reported Q3 gross revenue of $5,000,000. "
        "Operating margin is 36.0%."
    )

    annotated_text, citations = generator.generate_citations(text, sample_chunks)
    assert len(citations) >= 1
    assert "[^1]" in annotated_text
    assert "#### 📚 Verifiable Citations & Sources" in annotated_text
    assert citations[0].tenant_id == "tenant-acme"


@pytest.mark.asyncio
async def test_verifier_node_self_rag_groundedness_pass() -> None:
    """Verify verifier_node passes when response is grounded in retrieved context."""
    state: AgentState = {
        "prompt": "What was the revenue and operating expenses for ACME Corp?",
        "tenant_id": "tenant-acme",
        "financial_analysis": {
            "revenue": 5000000.0,
            "operating_expenses": 3200000.0,
            "operating_income": 1800000.0,
        },
        "retrieved_chunks": [
            {
                "chunk_id": "c-1",
                "content": (
                    "Gross revenue is $5000000.0 and operating expenses "
                    "are $3200000.0 with operating income $1800000.0"
                ),
                "tenant_id": "tenant-acme",
            }
        ],
        "revision_count": 0,
    }

    result = await verifier_node(state)
    assert result["verification_verdict"] == "PASS"
    assert result["mascot_state"] == "success"
    assert result["next_agent"] == "synthesizer"
    assert result["groundedness_score"] >= 0.80


@pytest.mark.asyncio
async def test_verifier_node_self_rag_groundedness_reject_loop() -> None:
    """Verify verifier_node triggers critique loop when groundedness is low."""
    state: AgentState = {
        "prompt": "What was the EBITDA?",
        "tenant_id": "tenant-acme",
        "financial_analysis": {
            "revenue": 9999999.0,  # Hallucinated number not in context
            "operating_expenses": 1000.0,
            "operating_income": 9998999.0,
        },
        "retrieved_chunks": [
            {
                "chunk_id": "c-1",
                "content": "Completely unrelated text with zero numbers.",
                "tenant_id": "tenant-acme",
            }
        ],
        "revision_count": 0,
    }

    result = await verifier_node(state)
    assert result["verification_verdict"] == "NEEDS_REVISION"
    assert result["mascot_state"] == "alert"
    assert result["next_agent"] == "supervisor"
    assert result["revision_count"] == 1
