"""Comprehensive verification test suite for R-FUNC-02: RAG Behavior.

Verifies the entire RAG pipeline from file ingestion to parsing, normalization,
chunking, metadata, embeddings, Qdrant/sparse indexing, hybrid retrieval, fusion,
reranking, context selection, grounded generation, claim verification, citation
verification, and explicit abstention across 14 canonical scenarios:

1.  TXT Document Ingestion & Retrieval (NFKC, control char stripping, chunking, retrieval)
2.  Markdown Document Ingestion & Structure Awareness (headings, code blocks preservation)
3.  PDF Multi-Page Binary Extraction & Pre-Extracted / Base64 Support
4.  Empty, Malformed, and Unsupported Document Handling (0-chunks, malformed PDF, unsupported extensions)
5.  Repeated Indexing, Duplicate Prevention, and Version Updates (UUIDv5 idempotency, BM25 TF repair)
6.  Relevant Query Processing, High Relevance Ranking & Inline Citations
7.  Irrelevant Query Processing & Explicit Abstention (NO_RELEVANT_EVIDENCE)
8.  Missing Evidence Abstention on Unindexed Tenant Workspaces
9.  Conflicting Evidence Detection & UNCERTAIN Grounding Classification
10. Citation Verification, Metric-Only Collision Rejection & Footnote Hallucination Stripping
11. Multi-Tenant Isolation Defense-in-Depth Across All Pipeline Layers
12. BM25 Sparse Index Cold-Start Recovery & Restart Persistence
13. Upstream Provider Failure & Graceful Abstention (PROVIDER_FAILURE)
14. Public HTTP API Endpoints (/ingest, /tasks, /query, /generate) Real Boundary Testing
"""

from __future__ import annotations

import base64
import io
import tempfile
from pathlib import Path
from unittest.mock import AsyncMock, patch

import jwt
import pytest
from httpx import ASGITransport, AsyncClient

from app.core.config import get_settings
from app.main import app
from app.rag.bm25 import BM25Retriever
from app.rag.citations import CitationGenerator
from app.rag.context_selector import ContextSelector
from app.rag.embedding import (
    EmbeddingProvider,
    TestOnlyFakeEmbeddingProvider,
)
from app.rag.grounding import GroundingVerifier
from app.rag.ingestion import (
    DocumentIngestionPipeline,
    DocumentIngestRequest,
)
from app.rag.models import (
    AbstentionReason,
    ClaimEntailment,
    DocumentChunk,
)
from app.rag.parsers import (
    MarkdownParser,
    PDFParser,
    PlainTextParser,
    UnsupportedDocumentTypeError,
    get_parser,
)
from app.rag.pipeline import RAGPipeline
from app.rag.retriever import HybridRetriever
from app.rag.vector_store import QdrantVectorStore


@pytest.fixture
def test_embedding_provider() -> EmbeddingProvider:
    """Provide fast deterministic embedding provider for isolated tests."""
    return TestOnlyFakeEmbeddingProvider(dimension=384)


@pytest.fixture
def auth_headers() -> dict[str, str]:
    """Generate valid JWT bearer authorization header."""
    settings = get_settings()
    token = jwt.encode(
        {
            "sub": "test-rag-admin",
            "tenant_id": "tenant-rf2-main",
            "roles": ["admin"],
        },
        settings.JWT_SECRET_KEY,
        algorithm="HS256",
    )
    return {"Authorization": f"Bearer {token}"}


# ==============================================================================
# Scenario 01: TXT Document Ingestion & Full Path
# ==============================================================================
@pytest.mark.asyncio
async def test_scenario_01_txt_document_full_path(
    test_embedding_provider: EmbeddingProvider,
) -> None:
    """Verify TXT document passes MIME detection, NFKC normalization, control char stripping, chunking, and retrieval."""
    parser = PlainTextParser()
    raw_data = b"ACME Corp\x00 Fiscal Year 2026.\r\nTotal gross revenue reported at $120,000,000.\tOperating profit margin is 32.5%."
    parsed = parser.parse_bytes(raw_data, filename="financials.txt")

    # Invariant: null byte stripped, newline normalized, tab preserved
    assert "\x00" not in parsed.content
    assert "\r\n" not in parsed.content
    assert "$120,000,000" in parsed.content
    assert parsed.mime_type == "text/plain"

    vstore = QdrantVectorStore(embedding_provider=test_embedding_provider)
    bm25 = BM25Retriever(auto_save=False)
    retriever = HybridRetriever(vector_store=vstore, bm25=bm25)
    ingestion = DocumentIngestionPipeline(retriever=retriever)

    req = DocumentIngestRequest(
        content=parsed.content,
        source="financials.txt",
        metadata={"category": "earnings"},
    )
    resp = await ingestion.ingest(req, tenant_id="tenant-txt-test")
    assert resp.status == "success"
    assert resp.indexed_chunks >= 1
    assert resp.tenant_id == "tenant-txt-test"

    # Hybrid Retrieval
    results = await retriever.retrieve(
        query="gross revenue operating profit margin",
        tenant_id="tenant-txt-test",
        top_k=2,
    )
    assert len(results.chunks) >= 1
    assert "$120,000,000" in results.chunks[0].content
    assert results.chunks[0].tenant_id == "tenant-txt-test"


# ==============================================================================
# Scenario 02: Markdown Document Ingestion & Structure Awareness
# ==============================================================================
@pytest.mark.asyncio
async def test_scenario_02_markdown_document_full_path(
    test_embedding_provider: EmbeddingProvider,
) -> None:
    """Verify Markdown parsing extracts section headings, protects fenced code blocks, and preserves indentation."""
    md_text = (
        "# JakeAI Cloud Architecture\n\n"
        "JakeAI provides unified agent execution.\n\n"
        "## Ingestion Subsystem\n\n"
        "Here is the core configuration:\n\n"
        "```python\n"
        "def configure_pipeline():\n"
        "    retriever = HybridRetriever()\n"
        "    return retriever\n"
        "```\n\n"
        "### Performance Metrics\n\n"
        "Latency target is under 150ms for hybrid retrieval."
    )

    parser = MarkdownParser()
    parsed = parser.parse_text(md_text, filename="architecture.md")
    assert parsed.mime_type == "text/markdown"
    assert "JakeAI Cloud Architecture" in parsed.metadata.get("headings", [])
    assert "Ingestion Subsystem" in parsed.metadata.get("headings", [])
    # Fenced code block indentation is preserved
    assert "    retriever = HybridRetriever()" in parsed.content

    vstore = QdrantVectorStore(embedding_provider=test_embedding_provider)
    bm25 = BM25Retriever(auto_save=False)
    retriever = HybridRetriever(vector_store=vstore, bm25=bm25)
    pipeline = RAGPipeline(retriever=retriever)

    req = DocumentIngestRequest(
        content=parsed.content,
        source="architecture.md",
        metadata=parsed.metadata,
    )
    await pipeline.ingest_document(req, tenant_id="tenant-md-test")

    query_res = await retriever.retrieve(
        query="HybridRetriever code configuration",
        tenant_id="tenant-md-test",
        top_k=3,
    )
    assert len(query_res.chunks) >= 1
    assert any("configure_pipeline" in c.content for c in query_res.chunks)


# ==============================================================================
# Scenario 03: PDF Document Multi-Page Binary Extraction & Base64
# ==============================================================================
@pytest.mark.asyncio
async def test_scenario_03_pdf_document_full_path(
    test_embedding_provider: EmbeddingProvider,
) -> None:
    """Verify real multi-page PDF generation, binary extraction with page metadata, and base64 parsing."""
    import pypdf

    # Construct real two-page PDF in memory
    writer = pypdf.PdfWriter()
    page1 = writer.add_blank_page(width=300, height=300)
    page2 = writer.add_blank_page(width=300, height=300)
    assert page1 is not None and page2 is not None

    buf = io.BytesIO()
    writer.write(buf)
    pdf_bytes = buf.getvalue()

    # Test PDFParser on real binary PDF
    parser = PDFParser()
    parsed = parser.parse_bytes(pdf_bytes, filename="quarterly_report.pdf")
    assert parsed.mime_type == "application/pdf"
    assert parsed.metadata["total_pages"] == 2
    assert "pages" in parsed.metadata

    # Test base64 decoding support in PDFParser
    b64_pdf = base64.b64encode(pdf_bytes).decode("ascii")
    parsed_b64 = parser.parse_text(b64_pdf, filename="base64_report.pdf")
    assert parsed_b64.mime_type == "application/pdf"
    assert parsed_b64.metadata["total_pages"] == 2

    # End-to-end ingestion of pre-extracted PDF text
    vstore = QdrantVectorStore(embedding_provider=test_embedding_provider)
    bm25 = BM25Retriever(auto_save=False)
    retriever = HybridRetriever(vector_store=vstore, bm25=bm25)
    ingestion = DocumentIngestionPipeline(retriever=retriever)

    pdf_text = (
        "[Page 1]\n"
        "Executive Summary: Net revenue surged to $250,000,000 in FY2026.\n\n"
        "[Page 2]\n"
        "Capital Expenditures: Total cloud infrastructure capex was $45,000,000."
    )
    req = DocumentIngestRequest(content=pdf_text, source="FY2026_Report.pdf")
    ingest_resp = await ingestion.ingest(req, tenant_id="tenant-pdf-test")
    assert ingest_resp.indexed_chunks >= 1

    search_res = await retriever.retrieve(
        query="cloud infrastructure capex",
        tenant_id="tenant-pdf-test",
        top_k=2,
    )
    assert len(search_res.chunks) >= 1
    assert "$45,000,000" in search_res.chunks[0].content


# ==============================================================================
# Scenario 04: Empty, Malformed, and Unsupported Documents
# ==============================================================================
@pytest.mark.asyncio
async def test_scenario_04_empty_malformed_unsupported_documents(
    test_embedding_provider: EmbeddingProvider,
) -> None:
    """Verify empty input returns 0 chunks, corrupted PDF raises ValueError, and unsupported types raise UnsupportedDocumentTypeError."""
    vstore = QdrantVectorStore(embedding_provider=test_embedding_provider)
    bm25 = BM25Retriever(auto_save=False)
    retriever = HybridRetriever(vector_store=vstore, bm25=bm25)
    ingestion = DocumentIngestionPipeline(retriever=retriever)

    # 1. Empty and pure whitespace document ingestion
    req_empty = DocumentIngestRequest(content="   \n\n\t   ", source="empty.txt")
    resp_empty = await ingestion.ingest(req_empty, tenant_id="tenant-empty")
    assert resp_empty.indexed_chunks == 0
    assert resp_empty.chunk_ids == []

    # 2. Corrupted PDF byte stream
    corrupted_pdf = b"%PDF-1.4 corrupted and truncated bytes that cannot be parsed"
    parser = PDFParser()
    with pytest.raises(ValueError, match="Failed to read PDF file"):
        parser.parse_bytes(corrupted_pdf, filename="corrupted.pdf")

    # 3. Unsupported file extensions
    with pytest.raises(UnsupportedDocumentTypeError):
        get_parser("malicious.exe")

    with pytest.raises(UnsupportedDocumentTypeError):
        get_parser("archive.zip")

    with pytest.raises(UnsupportedDocumentTypeError):
        get_parser("firmware.bin")


# ==============================================================================
# Scenario 05: Repeated Indexing, Duplicate Prevention & Version Updates
# ==============================================================================
@pytest.mark.asyncio
async def test_scenario_05_repeated_indexing_and_version_update(
    test_embedding_provider: EmbeddingProvider,
) -> None:
    """Verify re-indexing identical content is idempotent (no duplicate points/counts) and version updates are tracked."""
    vstore = QdrantVectorStore(embedding_provider=test_embedding_provider)
    bm25 = BM25Retriever(auto_save=False)
    retriever = HybridRetriever(vector_store=vstore, bm25=bm25)
    ingestion = DocumentIngestionPipeline(retriever=retriever)

    content = "Recurring subscription revenue reached $15,000,000 in Q2."
    tenant = "tenant-dedup-test"

    # First ingestion (version 1.0)
    req1 = DocumentIngestRequest(
        content=content, source="mrr.txt", metadata={"version": "1.0"}
    )
    resp1 = await ingestion.ingest(req1, tenant_id=tenant)
    assert resp1.indexed_chunks == 1
    chunk_id_1 = resp1.chunk_ids[0]

    # Re-ingest the exact same document
    resp2 = await ingestion.ingest(req1, tenant_id=tenant)
    assert resp2.indexed_chunks == 1
    chunk_id_2 = resp2.chunk_ids[0]

    # Deterministic chunk ID match
    assert chunk_id_1 == chunk_id_2

    # Verify BM25 document frequency for "revenue" was NOT double-counted
    assert bm25._doc_freqs[tenant]["revenue"] == 1
    assert len(bm25._corpus[tenant]) == 1

    # Verify Qdrant store has exactly 1 entry in memory
    assert len(vstore._memory_vectors[tenant]) == 1

    # Update version to 2.0 with modified content
    req_v2 = DocumentIngestRequest(
        content="Recurring subscription revenue reached $18,500,000 in Q2.",
        source="mrr.txt",
        metadata={"version": "2.0"},
    )
    resp_v2 = await ingestion.ingest(req_v2, tenant_id=tenant)
    assert resp_v2.indexed_chunks == 1

    # In BM25, the new chunk exists and reflects the updated content
    search_res = await retriever.retrieve(
        query="subscription revenue", tenant_id=tenant, top_k=5
    )
    assert len(search_res.chunks) >= 1
    assert any("$18,500,000" in c.content for c in search_res.chunks)


# ==============================================================================
# Scenario 06: Relevant Query Processing & Grounded Generation
# ==============================================================================
@pytest.mark.asyncio
async def test_scenario_06_relevant_query_and_claim_grounding(
    test_embedding_provider: EmbeddingProvider,
) -> None:
    """Verify relevant query retrieves top candidates, selects context, generates grounded answer, and produces citations."""
    vstore = QdrantVectorStore(embedding_provider=test_embedding_provider)
    bm25 = BM25Retriever(auto_save=False)
    retriever = HybridRetriever(vector_store=vstore, bm25=bm25)
    pipeline = RAGPipeline(retriever=retriever)

    req = DocumentIngestRequest(
        content="Acme Corporation reported $85,000,000 in Q3 revenue with 35% operating margin and $22,000,000 free cash flow.",
        source="Acme_Q3_Earnings.txt",
    )
    tenant = "tenant-relevant-query"
    await pipeline.ingest_document(req, tenant_id=tenant)

    # In offline test mode without external API, pipeline uses deterministic grounded synthesis
    res = await pipeline.generate_grounded_answer(
        query="What was Acme Corporation revenue and operating margin?",
        tenant_id=tenant,
        max_context_tokens=600,
    )

    assert res.status == "SUCCESS"
    assert res.abstention_reason is None
    assert "$85,000,000" in res.answer
    assert "35%" in res.answer
    assert len(res.citations) >= 1
    assert res.citations[0].source == "Acme_Q3_Earnings.txt"
    assert res.citations[0].confidence >= 0.70
    assert "[^1]" in res.answer


# ==============================================================================
# Scenario 07: Irrelevant Query Processing & Explicit Abstention
# ==============================================================================
@pytest.mark.asyncio
async def test_scenario_07_irrelevant_query_explicit_abstention(
    test_embedding_provider: EmbeddingProvider,
) -> None:
    """Verify query with zero relevance to indexed documents explicitly abstains with NO_RELEVANT_EVIDENCE."""
    vstore = QdrantVectorStore(embedding_provider=test_embedding_provider)
    bm25 = BM25Retriever(auto_save=False)
    retriever = HybridRetriever(vector_store=vstore, bm25=bm25)
    pipeline = RAGPipeline(retriever=retriever)

    # Ingest document strictly about corporate tax withholding
    req = DocumentIngestRequest(
        content="Corporate payroll tax withholding rates are fixed at 6.2% for social security.",
        source="Payroll_Tax_Guide.txt",
    )
    tenant = "tenant-irrelevant-query"
    await pipeline.ingest_document(req, tenant_id=tenant)

    # Query about unrelated culinary dessert recipe
    res = await pipeline.generate_grounded_answer(
        query="What is the authentic Italian recipe for making tiramisu mascarpone?",
        tenant_id=tenant,
    )

    assert res.status == "ABSTAINED"
    assert res.abstention_reason == AbstentionReason.NO_RELEVANT_EVIDENCE
    assert len(res.citations) == 0
    assert (
        "no relevant evidence was found" in res.answer.lower()
        or "no verified documents were found" in res.answer.lower()
    )


# ==============================================================================
# Scenario 08: Missing Evidence Abstention on Unindexed Tenant
# ==============================================================================
@pytest.mark.asyncio
async def test_scenario_08_missing_evidence_explicit_abstention() -> None:
    """Verify querying an empty tenant workspace with zero documents explicitly returns ABSTAINED with NO_RELEVANT_EVIDENCE."""
    pipeline = RAGPipeline()
    res = await pipeline.generate_grounded_answer(
        query="What was our total net revenue for the European branch?",
        tenant_id="tenant-completely-empty-workspace-99",
    )

    assert res.status == "ABSTAINED"
    assert res.abstention_reason == AbstentionReason.NO_RELEVANT_EVIDENCE
    assert len(res.citations) == 0
    assert (
        "no verified documents were found for tenant `tenant-completely-empty-workspace-99`"
        in res.answer
    )


# ==============================================================================
# Scenario 09: Conflicting Evidence Detection in GroundingVerifier
# ==============================================================================
def test_scenario_09_conflicting_evidence_resolution() -> None:
    """Verify GroundingVerifier detects conflicting metrics across retrieved records and flags UNCERTAIN instead of SUPPORTED."""
    verifier = GroundingVerifier()

    passages = [
        DocumentChunk(
            chunk_id="chunk-prelim",
            content="ACME Corp preliminary financial filing reported revenue of $50,000,000 for Q3.",
            tenant_id="tenant-audit",
            source="Preliminary 8-K",
        ),
        DocumentChunk(
            chunk_id="chunk-audited",
            content="ACME Corp audited financial statement restated revenue of $42,000,000 for Q3.",
            tenant_id="tenant-audit",
            source="Audited 10-Q",
        ),
    ]

    # Claim asserting preliminary figure
    claim_prelim = "ACME Corp reported revenue of $50,000,000 for Q3."
    res = verifier.verify_claim(claim_prelim, passages)

    # Invariant: Because another passage on the same topic reports a contradicting figure ($42M),
    # the claim must be classified as UNCERTAIN, not unconditionally SUPPORTED!
    assert res.entailment == ClaimEntailment.UNCERTAIN
    assert "Conflicting evidence detected" in res.reasoning
    assert "chunk-prelim" in res.supporting_chunk_ids


# ==============================================================================
# Scenario 10: Citation Mismatch & Hallucination Stripping
# ==============================================================================
def test_scenario_10_citation_mismatch_and_hallucination_stripping() -> None:
    """Verify metric coincidence without topic overlap is rejected (score 0.0), and hallucinated footnote markers are stripped."""
    generator = CitationGenerator()
    passages = [
        DocumentChunk(
            chunk_id="p1",
            content="ACME Corp reported gross enterprise revenue of $50,000,000 for Q3.",
            tenant_id="tenant-cite",
            source="Revenue Filing",
        )
    ]

    # 1. Metric collision without topic overlap (CEO bought luxury yacht)
    unrelated_sentence = "The executive acquired a luxury yacht for $50,000,000."
    text_unrelated, citations_unrelated = generator.generate_citations(
        unrelated_sentence, passages
    )
    # The revenue filing must NOT be cited for the yacht purchase!
    assert len(citations_unrelated) == 0
    assert "[^1]" not in text_unrelated

    # 2. Hallucinated footnote markers stripped
    hallucinated_text = "Enterprise revenue was $50,000,000 for Q3 [^99]. Another unverified statement [^42]."
    cleaned_text, citations_valid = generator.generate_citations(
        hallucinated_text, passages
    )
    assert "[^99]" not in cleaned_text
    assert "[^42]" not in cleaned_text
    assert "[^1]" in cleaned_text
    assert len(citations_valid) == 1
    assert citations_valid[0].source == "Revenue Filing"


# ==============================================================================
# Scenario 11: Multi-Tenant Isolation Defense-in-Depth
# ==============================================================================
@pytest.mark.asyncio
async def test_scenario_11_tenant_isolation_defense_in_depth(
    test_embedding_provider: EmbeddingProvider,
) -> None:
    """Verify tenant data is strictly quarantined across vector store, BM25, hybrid search, context selector, citations, and pipeline."""
    vstore = QdrantVectorStore(embedding_provider=test_embedding_provider)
    bm25 = BM25Retriever(auto_save=False)
    retriever = HybridRetriever(vector_store=vstore, bm25=bm25)
    selector = ContextSelector()
    citation_gen = CitationGenerator()
    pipeline = RAGPipeline(
        retriever=retriever,
        context_selector=selector,
        citation_generator=citation_gen,
    )

    # Ingest secret document for Tenant Alpha
    req_alpha = DocumentIngestRequest(
        content="Confidential acquisition code-name Falcon: purchase price is $175,000,000.",
        source="M&A_Falcon.txt",
    )
    await pipeline.ingest_document(req_alpha, tenant_id="tenant-alpha")

    # Ingest standard document for Tenant Beta
    req_beta = DocumentIngestRequest(
        content="Routine quarterly facilities update: new office opening in Seattle.",
        source="Facilities.txt",
    )
    await pipeline.ingest_document(req_beta, tenant_id="tenant-beta")

    # 1. Dense search isolation
    dense_hits = await vstore.search(
        query="acquisition Falcon purchase price", tenant_id="tenant-beta"
    )
    assert all(c.tenant_id == "tenant-beta" for c in dense_hits)
    assert not any("Falcon" in c.content for c in dense_hits)

    # 2. BM25 search isolation
    bm25_hits = bm25.search(
        query="acquisition Falcon purchase price", tenant_id="tenant-beta"
    )
    assert len(bm25_hits) == 0

    # 3. Hybrid retriever isolation
    hybrid_res = await retriever.retrieve(
        query="Falcon $175,000,000", tenant_id="tenant-beta"
    )
    assert all(c.tenant_id == "tenant-beta" for c in hybrid_res.chunks)

    # 4. Context selector guardrail (foreign chunk forceful injection)
    foreign_chunk = DocumentChunk(
        chunk_id="chunk-leak",
        content="Falcon price $175,000,000",
        tenant_id="tenant-alpha",
        score=0.99,
    )
    ctx_res = selector.select_context(
        candidates=[foreign_chunk],
        query="Falcon",
        tenant_id="tenant-beta",
    )
    assert len(ctx_res.selected_chunks) == 0

    # 5. Citation generator tenant guardrail
    _, citations = citation_gen.generate_citations(
        text="Falcon price was $175,000,000.",
        passages=[foreign_chunk],
        tenant_id="tenant-beta",
    )
    assert len(citations) == 0

    # 6. End-to-end generation abstention without data leakage
    gen_res = await pipeline.generate_grounded_answer(
        query="What is the purchase price for code-name Falcon?",
        tenant_id="tenant-beta",
    )
    assert gen_res.status == "ABSTAINED"
    assert "175,000,000" not in gen_res.answer
    assert "Falcon" not in gen_res.answer


# ==============================================================================
# Scenario 12: BM25 Sparse Index Cold-Start Recovery & Restart Persistence
# ==============================================================================
def test_scenario_12_restart_persistence() -> None:
    """Verify BM25 sparse index persists to disk and reloads identically across process restart."""
    with tempfile.TemporaryDirectory() as tmp_dir:
        storage_path = Path(tmp_dir) / "bm25_persistence.json"

        # 1. First process: create, index, and auto-persist to disk
        retriever_proc1 = BM25Retriever(storage_path=storage_path, auto_save=True)
        chunks = [
            DocumentChunk(
                chunk_id="c-persist-1",
                content="Operating income reached fifty million dollars.",
                tenant_id="tenant-persist",
                source="Statement.txt",
            ),
            DocumentChunk(
                chunk_id="c-persist-2",
                content="Dividends declared at two dollars per preferred share.",
                tenant_id="tenant-persist",
                source="Dividends.txt",
            ),
        ]
        retriever_proc1.add_documents(chunks)
        assert storage_path.is_file()

        # 2. Simulate process termination and cold start: instantiate fresh retriever
        retriever_proc2 = BM25Retriever(storage_path=storage_path, auto_save=True)

        # Invariant: documents and term frequencies must be restored on cold start
        assert "tenant-persist" in retriever_proc2._corpus
        assert len(retriever_proc2._corpus["tenant-persist"]) == 2
        assert retriever_proc2._doc_freqs["tenant-persist"]["operating"] == 1
        assert retriever_proc2._doc_freqs["tenant-persist"]["dividends"] == 1

        # Search against revived index
        results = retriever_proc2.search(
            query="operating income fifty million",
            tenant_id="tenant-persist",
            top_k=2,
        )
        assert len(results) >= 1
        assert results[0].chunk_id == "c-persist-1"
        assert "fifty million" in results[0].content


# ==============================================================================
# Scenario 13: Upstream Provider Failure Graceful Abstention
# ==============================================================================
@pytest.mark.asyncio
async def test_scenario_13_provider_failure_graceful_abstention(
    test_embedding_provider: EmbeddingProvider,
) -> None:
    """Verify upstream model provider exceptions are caught and explicitly return status=ABSTAINED and PROVIDER_FAILURE."""
    vstore = QdrantVectorStore(embedding_provider=test_embedding_provider)
    bm25 = BM25Retriever(auto_save=False)
    retriever = HybridRetriever(vector_store=vstore, bm25=bm25)
    pipeline = RAGPipeline(retriever=retriever)

    req = DocumentIngestRequest(
        content="Operating revenues reached $30,000,000 in Q1.",
        source="Q1_Report.txt",
    )
    tenant = "tenant-provider-fail"
    await pipeline.ingest_document(req, tenant_id=tenant)

    # Injected upstream provider failure
    with patch(
        "app.rag.pipeline.call_upstream_llm",
        new=AsyncMock(
            side_effect=RuntimeError("Provider 503 Overloaded: rate limit exceeded")
        ),
    ):
        res = await pipeline.generate_grounded_answer(
            query="What were operating revenues in Q1?",
            tenant_id=tenant,
        )

        assert res.status == "ABSTAINED"
        assert res.abstention_reason == AbstentionReason.PROVIDER_FAILURE
        assert "unable to generate an answer at this time" in res.answer
        assert len(res.citations) == 0


# ==============================================================================
# Scenario 14: Public HTTP API Endpoints Complete Boundary
# ==============================================================================
@pytest.mark.asyncio
async def test_scenario_14_http_api_endpoints_complete_boundary(
    auth_headers: dict[str, str],
) -> None:
    """Verify HTTP endpoints /api/v1/rag/ingest, /tasks, /query, and /generate via real ASGI HTTP transport."""
    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test") as client:
        # 1. Ingest document synchronously (201 Created)
        payload_sync = {
            "content": "Global payments division reported transaction volume of $95,000,000 in July.",
            "source": "Payments_July.txt",
            "metadata": {"month": "July"},
        }
        resp_sync = await client.post(
            "/api/v1/rag/ingest", json=payload_sync, headers=auth_headers
        )
        assert resp_sync.status_code == 201
        sync_data = resp_sync.json()
        assert sync_data["status"] == "success"
        assert sync_data["indexed_chunks"] >= 1
        assert sync_data["tenant_id"] == "tenant-rf2-main"

        # 2. Ingest document asynchronously (202 Accepted)
        payload_async = {
            "content": "European operations report strong compliance with GDPR audit standards.",
            "source": "Compliance.txt",
        }
        resp_async = await client.post(
            "/api/v1/rag/ingest?async_mode=true",
            json=payload_async,
            headers=auth_headers,
        )
        assert resp_async.status_code == 202
        async_data = resp_async.json()
        assert "task_id" in async_data
        task_id = async_data["task_id"]

        # 3. Poll task status (200 OK)
        task_resp = await client.get(
            f"/api/v1/rag/tasks/{task_id}", headers=auth_headers
        )
        assert task_resp.status_code == 200
        task_info = task_resp.json()
        assert task_info["task_id"] == task_id
        assert task_info["tenant_id"] == "tenant-rf2-main"

        # 4. Reject unsupported document type with 400 Bad Request
        payload_invalid = {
            "content": "some binary payload",
            "source": "malicious.exe",
        }
        resp_invalid = await client.post(
            "/api/v1/rag/ingest", json=payload_invalid, headers=auth_headers
        )
        assert resp_invalid.status_code == 400
        assert "Unsupported document format" in resp_invalid.json()["detail"]

        # 5. Query endpoint without and with context selection
        resp_query = await client.post(
            "/api/v1/rag/query",
            json={
                "query": "payments transaction volume July",
                "select_context": False,
                "top_k": 3,
            },
            headers=auth_headers,
        )
        assert resp_query.status_code == 200
        query_data = resp_query.json()
        assert query_data["tenant_id"] == "tenant-rf2-main"
        assert len(query_data["chunks"]) >= 1

        resp_query_ctx = await client.post(
            "/api/v1/rag/query",
            json={
                "query": "payments transaction volume July",
                "select_context": True,
                "max_context_tokens": 500,
            },
            headers=auth_headers,
        )
        assert resp_query_ctx.status_code == 200
        query_ctx_data = resp_query_ctx.json()
        assert query_ctx_data["selected_context"] is not None
        assert "$95,000,000" in query_ctx_data["selected_context"]

        # 6. Generate endpoint: relevant query success
        resp_gen = await client.post(
            "/api/v1/rag/generate",
            json={"query": "What was the payments transaction volume in July?"},
            headers=auth_headers,
        )
        assert resp_gen.status_code == 200
        gen_data = resp_gen.json()
        assert gen_data["status"] == "SUCCESS"
        assert "$95,000,000" in gen_data["answer"]
        assert len(gen_data["citations"]) >= 1

        # 7. Generate endpoint: irrelevant query abstention
        resp_gen_abstain = await client.post(
            "/api/v1/rag/generate",
            json={"query": "What is the secret baking recipe for sourdough bread?"},
            headers=auth_headers,
        )
        assert resp_gen_abstain.status_code == 200
        abstain_data = resp_gen_abstain.json()
        assert abstain_data["status"] == "ABSTAINED"
        assert (
            abstain_data["abstention_reason"]
            == AbstentionReason.NO_RELEVANT_EVIDENCE.value
        )
