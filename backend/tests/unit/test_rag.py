"""Unit and integration tests for RAG engine, hybrid retrieval, and Self-RAG loop."""

from typing import TYPE_CHECKING

import pytest

from app.agents.verifier import verifier_node
from app.core.config import get_settings
from app.rag.bm25 import BM25Retriever
from app.rag.citations import CitationGenerator
from app.rag.context_selector import ContextSelector
from app.rag.ingestion import (
    DocumentIngestionPipeline,
    DocumentIngestRequest,
)
from app.rag.models import DocumentChunk
from app.rag.pipeline import RAGPipeline
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
        "ACME Corp reported Q3 gross revenue of $5,000,000. Operating margin is 36.0%."
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


def test_cross_encoder_reranker_with_custom_callable(
    sample_chunks: list[DocumentChunk],
) -> None:
    """Verify CrossEncoderReranker applies custom ONNX/CrossEncoder callable scores."""

    def mock_scorer(query: str, docs: list[str]) -> list[float]:
        # Return 0.95 for doc 0, 0.20 for doc 1
        return [0.95, 0.20]

    reranker = CrossEncoderReranker(
        model_name="test-model",
        cross_encoder_fn=mock_scorer,
    )
    dense_candidates = [sample_chunks[0], sample_chunks[1]]
    sparse_candidates = [sample_chunks[1]]

    reranked = reranker.rerank(
        query="operating metrics",
        dense_results=dense_candidates,
        sparse_results=sparse_candidates,
        top_k=2,
    )
    assert len(reranked) == 2
    assert reranked[0].chunk_id == sample_chunks[0].chunk_id
    assert reranked[0].score > reranked[1].score


def test_cross_encoder_empty_inputs() -> None:
    """Verify CrossEncoderReranker gracefully handles empty candidate inputs."""
    reranker = CrossEncoderReranker()
    assert reranker.rerank(query="anything", dense_results=[], sparse_results=[]) == []


def test_cross_encoder_reranker_model_initialization_and_fallback(
    sample_chunks: list[DocumentChunk],
) -> None:
    """Verify CrossEncoderReranker model_name initialization and fallback execution."""
    reranker = CrossEncoderReranker(model_name="BAAI/bge-reranker-base")
    assert reranker.model_name == "BAAI/bge-reranker-base"

    reranked = reranker.rerank(
        query="operating margin 36.0%",
        dense_results=[sample_chunks[1], sample_chunks[0]],
        sparse_results=[sample_chunks[0], sample_chunks[1]],
        top_k=2,
    )
    assert len(reranked) == 2
    assert reranked[0].chunk_id == "chunk-acme-02"
    assert reranked[0].score >= reranked[1].score


def test_cross_encoder_reranker_with_fastembed_model(
    sample_chunks: list[DocumentChunk],
) -> None:
    """Verify CrossEncoderReranker execution with active FastEmbed model."""
    from unittest.mock import MagicMock

    reranker = CrossEncoderReranker(model_name="BAAI/bge-reranker-base")
    mock_model = MagicMock()
    mock_model.rerank.return_value = [0.92, 0.18]
    reranker._fastembed_model = mock_model

    reranked = reranker.rerank(
        query="operating margin",
        dense_results=[sample_chunks[0], sample_chunks[1]],
        sparse_results=[],
        top_k=2,
    )
    assert len(reranked) == 2
    assert reranked[0].chunk_id == sample_chunks[0].chunk_id
    assert reranked[0].score > reranked[1].score


@pytest.mark.asyncio
async def test_document_ingestion_pipeline_end_to_end() -> None:
    """Verify DocumentIngestionPipeline chunks, creates deterministic IDs, and indexes."""
    retriever = HybridRetriever()
    pipeline = DocumentIngestionPipeline(retriever=retriever)

    long_text = (
        "Enterprise Quarter 3 Financial Review.\n\n"
        "Net revenue reached $12,400,000 for the third fiscal quarter. "
        "Operating costs were reported at $7,800,000. "
        "Operating profit stood at $4,600,000 with a 37.1% operating margin.\n\n"
        "Guidance for Quarter 4 projects further revenue expansion to $14,000,000 "
        "driven by cloud software growth."
    )

    request = DocumentIngestRequest(
        content=long_text,
        source="Q3 Report 2026",
        metadata={"category": "financial_filing", "department": "investor_relations"},
        chunk_size=150,
        chunk_overlap=30,
    )

    response = await pipeline.ingest(request=request, tenant_id="tenant-ingest-test")

    assert response.status_code if hasattr(response, "status_code") else True
    assert response.status == "success"
    assert response.indexed_chunks >= 2
    assert len(response.chunk_ids) == response.indexed_chunks
    assert response.tenant_id == "tenant-ingest-test"
    assert response.source == "Q3 Report 2026"

    # Verify indexed chunks are retrievable via hybrid retriever
    retrieved = await retriever.retrieve(
        query="operating margin net revenue",
        tenant_id="tenant-ingest-test",
        top_k=3,
    )
    assert len(retrieved.chunks) >= 1
    assert retrieved.chunks[0].tenant_id == "tenant-ingest-test"
    assert "tenant-ingest-test" in retrieved.chunks[0].tenant_id


def test_context_selector_deduplication_and_budget() -> None:
    """Verify ContextSelector drops low-score chunks and formats structured context."""
    chunks = [
        DocumentChunk(
            chunk_id="chk-1",
            content="Alpha Corporation Q3 revenue was $100M with profit $30M.",
            tenant_id="tenant-cs-test",
            source="Alpha 10-Q",
            score=0.95,
        ),
        DocumentChunk(
            chunk_id="chk-2",
            content="Alpha Corporation Q3 revenue was $100M with profit $30M.",
            tenant_id="tenant-cs-test",
            source="Alpha Press Release",
            score=0.90,
        ),
        DocumentChunk(
            chunk_id="chk-3",
            content="Random irrelevant cafeteria menu notice for lunch.",
            tenant_id="tenant-cs-test",
            source="Cafeteria Notice",
            score=0.10,
        ),
    ]

    selector = ContextSelector(min_relative_score=0.30, redundancy_threshold=0.60)
    res = selector.select_context(
        candidates=chunks, query="revenue profit", tenant_id="tenant-cs-test"
    )

    assert (
        len(res.selected_chunks) == 1
    )  # chk-2 is redundant, chk-3 is low-scoring distractor
    assert res.selected_chunks[0].chunk_id == "chk-1"
    assert res.tokens_saved > 0
    assert res.reduction_ratio > 0.30
    assert "$100M" in res.formatted_context
    assert "[1] Source: Alpha 10-Q" in res.formatted_context


@pytest.mark.asyncio
async def test_rag_pipeline_retrieve_and_select() -> None:
    """Verify RAGPipeline retrieve_and_select_context returns candidate and context result."""
    pipeline = RAGPipeline()
    req = DocumentIngestRequest(
        content="Enterprise software ARR reached $250,000,000 with 115% net dollar retention.",
        source="ARR Report 2026",
    )
    await pipeline.ingest_document(request=req, tenant_id="tenant-pipe-test")

    retrieval, selection = await pipeline.retrieve_and_select_context(
        query="ARR net dollar retention",
        tenant_id="tenant-pipe-test",
        max_context_tokens=500,
    )

    assert retrieval.tenant_id == "tenant-pipe-test"
    assert len(selection.selected_chunks) >= 1
    assert "$250,000,000" in selection.formatted_context
    assert selection.selected_chunks[0].tenant_id == "tenant-pipe-test"


@pytest.mark.asyncio
async def test_rag_pipeline_generate_grounded_answer() -> None:
    """Verify RAGPipeline generate_grounded_answer synthesizes answer with citations."""
    pipeline = RAGPipeline()
    req = DocumentIngestRequest(
        content="Quarterly dividend declared at $0.85 per share payable on October 15, 2026.",
        source="Dividend Notice",
    )
    await pipeline.ingest_document(request=req, tenant_id="tenant-gen-test")

    gen_res = await pipeline.generate_grounded_answer(
        query="What is the dividend declared per share and payment date?",
        tenant_id="tenant-gen-test",
    )

    assert gen_res.tenant_id == "tenant-gen-test"
    assert len(gen_res.answer) > 0
    assert "$0.85" in gen_res.answer or "0.85" in gen_res.answer
    assert gen_res.context_selection.selected_tokens > 0
    assert gen_res.latency_ms >= 0.0


@pytest.mark.asyncio
async def test_rag_api_endpoints_integration() -> None:
    """Verify /api/v1/rag/query and /api/v1/rag/generate endpoints with HTTP client."""
    import jwt
    from httpx import ASGITransport, AsyncClient

    from app.main import app

    settings = get_settings()
    token = jwt.encode(
        {"sub": "test-user", "tenant_id": "tenant-api-rag", "roles": ["admin"]},
        settings.JWT_SECRET_KEY,
        algorithm="HS256",
    )
    headers = {"Authorization": f"Bearer {token}"}

    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test") as client:
        # 1. Ingest document
        ingest_payload = {
            "content": "Cloud division achieved $75,000,000 in Q3 revenue with 48% gross margin.",
            "source": "Cloud Division Report",
        }
        ingest_resp = await client.post(
            "/api/v1/rag/ingest", json=ingest_payload, headers=headers
        )
        assert ingest_resp.status_code == 201
        assert ingest_resp.json()["indexed_chunks"] >= 1

        # 2. Query with select_context=True
        query_payload = {
            "query": "Cloud revenue gross margin",
            "select_context": True,
            "max_context_tokens": 600,
        }
        query_resp = await client.post(
            "/api/v1/rag/query", json=query_payload, headers=headers
        )
        assert query_resp.status_code == 200
        query_data = query_resp.json()
        assert query_data["tenant_id"] == "tenant-api-rag"
        assert len(query_data["chunks"]) >= 1
        assert query_data["selected_context"] is not None
        assert "$75,000,000" in query_data["selected_context"]

        # 3. Generate grounded answer
        gen_payload = {
            "query": "What was Cloud revenue and gross margin?",
            "max_context_tokens": 600,
        }
        gen_resp = await client.post(
            "/api/v1/rag/generate", json=gen_payload, headers=headers
        )
        assert gen_resp.status_code == 200
        gen_data = gen_resp.json()
        assert gen_data["tenant_id"] == "tenant-api-rag"
        assert len(gen_data["answer"]) > 0
        assert gen_data["context_tokens"] > 0
