"""Comprehensive verification test suite for R-AI-01: RAG Grounding.

Tests whether generated claims are actually supported by retrieved evidence across:
1.  Fully Supported Claims with Provenance Tracing (claim -> passage -> source metadata).
2.  Partially Supported Answers with Unsupported Claims Cleanly Dropped.
3.  Metric Format Normalization ($100M vs $100 million vs $100,000,000).
4.  Conflicting Numerical Evidence Surfaced as UNCERTAIN with Adjusted Confidence.
5.  Conflicting Qualitative Entity Evidence Surfaced as UNCERTAIN.
6.  Direct Antonym & Polarity Contradiction Rejected and Dropped.
7.  Citation Mismatch Prevention on Partial Numeric Coincidence ($999M vs $100M).
8.  Missing Evidence Producing Explicit Abstention (NO_RELEVANT_EVIDENCE).
9.  Irrelevant Chunks Suppressed and Never Cited or Echoed.
10. Model Explicit Epistemic Abstention Preserved and Mapped to NO_RELEVANT_EVIDENCE.
11. Completely Contradictory Generation Producing Explicit Abstention.
12. Public HTTP API Boundary (/api/v1/rag/generate) Real ASGI Integration with Grounding Provenance.
"""

from __future__ import annotations

from unittest.mock import AsyncMock, patch

import jwt
import pytest
from httpx import ASGITransport, AsyncClient

from app.core.config import get_settings
from app.main import app
from app.rag.bm25 import BM25Retriever
from app.rag.citations import CitationGenerator
from app.rag.embedding import EmbeddingProvider, TestOnlyFakeEmbeddingProvider
from app.rag.grounding import (
    GroundingVerifier,
    extract_canonical_metrics,
)
from app.rag.ingestion import (
    DocumentIngestRequest,
)
from app.rag.models import (
    AbstentionReason,
    ClaimEntailment,
    ContextSelectionResult,
    DocumentChunk,
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
            "tenant_id": "tenant-grounding-test",
            "roles": ["admin"],
        },
        settings.JWT_SECRET_KEY,
        algorithm="HS256",
    )
    return {"Authorization": f"Bearer {token}"}


# ==============================================================================
# Scenario 01: Fully Supported Generation with Provenance Tracing
# ==============================================================================
@pytest.mark.asyncio
async def test_scenario_01_fully_supported_with_provenance_tracing(
    test_embedding_provider: EmbeddingProvider,
) -> None:
    """Verify supported claims map to evidence, trace claim -> passage -> source metadata, and generate valid citations."""
    vstore = QdrantVectorStore(embedding_provider=test_embedding_provider)
    bm25 = BM25Retriever(auto_save=False)
    retriever = HybridRetriever(vector_store=vstore, bm25=bm25)
    pipeline = RAGPipeline(retriever=retriever)

    tenant_id = "tenant-prov-01"
    req = DocumentIngestRequest(
        content=(
            "ACME Corporation Annual Report FY2026.\n"
            "Total gross revenue reached $120,000,000 with an operating margin of 32.5%.\n"
            "Headcount expanded to 3,200 full-time employees across global offices."
        ),
        source="ACME_10K_FY2026.pdf",
        metadata={"fiscal_year": 2026, "type": "annual_filing"},
    )
    ingest_res = await pipeline.ingest_document(req, tenant_id=tenant_id)
    assert ingest_res.status == "success"

    # Simulated LLM generating grounded claims
    generated_text = (
        "ACME Corporation achieved $120,000,000 in gross revenue for FY2026. "
        "The company employs 3,200 full-time employees."
    )

    with patch(
        "app.rag.pipeline.call_upstream_llm",
        new=AsyncMock(return_value=generated_text),
    ):
        gen_res = await pipeline.generate_grounded_answer(
            query="What was ACME FY2026 revenue and headcount?",
            tenant_id=tenant_id,
        )

    assert gen_res.status == "SUCCESS"
    assert gen_res.abstention_reason is None
    assert gen_res.grounding is not None
    assert gen_res.grounding.is_grounded is True
    assert gen_res.grounding.groundedness_ratio == 1.0
    assert len(gen_res.grounding.supported_claims) >= 2
    assert len(gen_res.grounding.unsupported_claims) == 0

    # Trace Claim -> Supporting Chunk ID -> Passage Content & Source Metadata
    for claim in gen_res.grounding.supported_claims:
        assert claim.entailment == ClaimEntailment.SUPPORTED
        assert len(claim.supporting_chunk_ids) > 0
        for chunk_id in claim.supporting_chunk_ids:
            matching_chunk = next(
                (
                    c
                    for c in gen_res.context_selection.selected_chunks
                    if c.chunk_id == chunk_id
                ),
                None,
            )
            assert matching_chunk is not None
            assert matching_chunk.source == "ACME_10K_FY2026.pdf"
            assert matching_chunk.metadata.get("fiscal_year") == 2026

    # Verify citation mapping
    assert len(gen_res.citations) >= 1
    assert all(c.source == "ACME_10K_FY2026.pdf" for c in gen_res.citations)
    assert all(c.confidence >= 0.80 for c in gen_res.citations)
    assert "[^1]" in gen_res.answer


# ==============================================================================
# Scenario 02: Partially Supported Answer - Unsupported Claim Stripped
# ==============================================================================
@pytest.mark.asyncio
async def test_scenario_02_partially_supported_unsupported_claim_dropped() -> None:
    """Verify that when an answer contains both supported and unsupported claims, the unsupported claim is dropped."""
    pipeline = RAGPipeline()
    tenant_id = "tenant-partial-02"

    chunk = DocumentChunk(
        chunk_id="chunk-fin",
        content="ACME Corp reported $150,000,000 in revenue for Q3 2026.",
        tenant_id=tenant_id,
        source="Q3_Report.txt",
    )
    ctx_res = ContextSelectionResult(
        selected_chunks=[chunk],
        formatted_context=f"[{chunk.chunk_id}]: {chunk.content}",
        selected_tokens=15,
    )
    pipeline.retrieve_and_select_context = AsyncMock(return_value=(None, ctx_res))  # type: ignore

    # Model generates one factual claim and one hallucinated/unsupported claim
    raw_answer = (
        "ACME Corp reported $150,000,000 in revenue for Q3 2026. "
        "The CFO was recently arrested for securities fraud."
    )

    with patch(
        "app.rag.pipeline.call_upstream_llm",
        new=AsyncMock(return_value=raw_answer),
    ):
        gen_res = await pipeline.generate_grounded_answer(
            query="What was ACME revenue and executive status?",
            tenant_id=tenant_id,
        )

    # Invariant: The unsupported claim MUST NOT silently reach the final answer!
    assert "securities fraud" not in gen_res.answer
    assert "arrested" not in gen_res.answer
    assert "$150,000,000" in gen_res.answer

    # Grounding breakdown must capture both
    assert gen_res.grounding is not None
    assert len(gen_res.grounding.supported_claims) == 1
    assert len(gen_res.grounding.unsupported_claims) == 1
    assert "arrested" in gen_res.grounding.unsupported_claims[0].claim_text


# ==============================================================================
# Scenario 03: Metric Format Normalization Across Variants
# ==============================================================================
def test_scenario_03_metric_format_normalization() -> None:
    """Verify metric normalization resolves $100M, $100 million, and $100,000,000 to identical canonical metrics."""
    m1 = extract_canonical_metrics("Revenue was $100M in 2026.")
    m2 = extract_canonical_metrics("Revenue was $100 million in 2026.")
    m3 = extract_canonical_metrics("Revenue was $100,000,000 in 2026.")

    assert ("USD", 100000000.0) in m1
    assert ("USD", 100000000.0) in m2
    assert ("USD", 100000000.0) in m3
    assert m1 == m2 == m3

    verifier = GroundingVerifier()
    doc_chunk = DocumentChunk(
        chunk_id="chunk-norm",
        content="Enterprise revenue was $100 million for FY2026 with 25% margin.",
        tenant_id="tenant-norm",
        source="Earnings.txt",
    )

    # Claim using $100M abbreviation
    claim_abbr = "Enterprise revenue was $100M for FY2026 with 25% margin."
    res_abbr = verifier.verify_claim(claim_abbr, [doc_chunk])
    assert res_abbr.entailment == ClaimEntailment.SUPPORTED
    assert "chunk-norm" in res_abbr.supporting_chunk_ids

    # Claim using expanded digits $100,000,000
    claim_digits = "Enterprise revenue was $100,000,000 for FY2026 with 25% margin."
    res_digits = verifier.verify_claim(claim_digits, [doc_chunk])
    assert res_digits.entailment == ClaimEntailment.SUPPORTED
    assert "chunk-norm" in res_digits.supporting_chunk_ids


# ==============================================================================
# Scenario 04: Conflicting Numerical Evidence Surfaced as UNCERTAIN
# ==============================================================================
def test_scenario_04_conflicting_numerical_evidence_surfaced() -> None:
    """Verify conflicting numerical records are flagged UNCERTAIN, reasoning surfaces conflict, and citation confidence is adjusted."""
    verifier = GroundingVerifier()
    citation_gen = CitationGenerator()

    passages = [
        DocumentChunk(
            chunk_id="chunk-v1",
            content="ACME Corp preliminary revenue was $50,000,000 for Q3 2026.",
            tenant_id="tenant-audit",
            source="Preliminary Report",
        ),
        DocumentChunk(
            chunk_id="chunk-v2",
            content="ACME Corp audited restated revenue was $42,000,000 for Q3 2026.",
            tenant_id="tenant-audit",
            source="Audited 10-Q",
        ),
    ]

    claim = "ACME Corp preliminary revenue was $50,000,000 for Q3 2026."
    v_res = verifier.verify_claim(claim, passages)

    assert v_res.entailment == ClaimEntailment.UNCERTAIN
    assert "Conflicting evidence detected" in v_res.reasoning
    assert "chunk-v1" in v_res.supporting_chunk_ids
    assert v_res.confidence == 0.50

    v_full = verifier.verify(claim, passages)
    assert "[unverified]" in v_full.verified_answer

    text, cites = citation_gen.generate_citations(
        v_full.verified_answer, passages, tenant_id="tenant-audit"
    )
    assert len(cites) == 1
    assert cites[0].confidence == 0.50
    assert "[unverified]" in text


# ==============================================================================
# Scenario 05: Conflicting Qualitative Entity Evidence Surfaced as UNCERTAIN
# ==============================================================================
def test_scenario_05_conflicting_qualitative_entities_surfaced() -> None:
    """Verify that qualitative claims with conflicting entities across candidate chunks are flagged UNCERTAIN."""
    verifier = GroundingVerifier()

    passages = [
        DocumentChunk(
            chunk_id="chunk-tokyo",
            content="The global engineering headquarters is located in Tokyo.",
            tenant_id="tenant-hq",
            source="Facilities_Tokyo.txt",
        ),
        DocumentChunk(
            chunk_id="chunk-london",
            content="The global engineering headquarters is located in London.",
            tenant_id="tenant-hq",
            source="Facilities_London.txt",
        ),
    ]

    claim_tokyo = "The global engineering headquarters is located in Tokyo."
    res_tokyo = verifier.verify_claim(claim_tokyo, passages)

    assert "chunk-london" not in res_tokyo.supporting_chunk_ids
    assert "chunk-tokyo" in res_tokyo.supporting_chunk_ids
    assert res_tokyo.entailment == ClaimEntailment.UNCERTAIN
    assert "Conflicting evidence detected" in res_tokyo.reasoning


# ==============================================================================
# Scenario 06: Direct Antonym & Polarity Contradiction Rejected
# ==============================================================================
def test_scenario_06_direct_antonym_contradiction_rejected() -> None:
    """Verify statements asserting antonyms (e.g. cancelled vs launched) are rejected with 0.0 confidence."""
    verifier = GroundingVerifier()
    passages = [
        DocumentChunk(
            chunk_id="chunk-launch",
            content="The company project was launched successfully on schedule.",
            tenant_id="tenant-proj",
            source="Project_Update.txt",
        )
    ]

    claim_cancelled = "The company project was cancelled due to bankruptcy."
    res = verifier.verify_claim(claim_cancelled, passages)

    assert res.entailment == ClaimEntailment.UNSUPPORTED
    assert res.confidence == 0.0
    assert len(res.supporting_chunk_ids) == 0
    assert "contradicts" in res.reasoning.lower()


# ==============================================================================
# Scenario 07: Citation Mismatch Prevention on Partial Numeric Overlap
# ==============================================================================
def test_scenario_07_citation_mismatch_prevention_on_partial_numbers() -> None:
    """Verify a passage reporting $100,000,000 in 2026 is NEVER cited for a sentence asserting $999,000,000 in 2026."""
    citation_gen = CitationGenerator()
    passages = [
        DocumentChunk(
            chunk_id="chunk-rev-real",
            content="In 2026, ACME Corp recorded total revenue of $100,000,000.",
            tenant_id="tenant-mismatch",
            source="Financial_Statement.pdf",
        )
    ]

    false_sentence = "Revenue was $999,000,000 in 2026."
    annotated_text, citations = citation_gen.generate_citations(
        false_sentence, passages, tenant_id="tenant-mismatch"
    )

    assert len(citations) == 0
    assert "[^1]" not in annotated_text


# ==============================================================================
# Scenario 08: Missing Evidence Produces Explicit Abstention
# ==============================================================================
@pytest.mark.asyncio
async def test_scenario_08_missing_evidence_explicit_abstention() -> None:
    """Verify RAGPipeline returns status='ABSTAINED' and reason='NO_RELEVANT_EVIDENCE' when evidence is absent."""
    pipeline = RAGPipeline()
    res = await pipeline.generate_grounded_answer(
        query="What is the quantum encryption key rotation policy?",
        tenant_id="tenant-unindexed-empty",
    )

    assert res.status == "ABSTAINED"
    assert res.abstention_reason == AbstentionReason.NO_RELEVANT_EVIDENCE
    assert len(res.citations) == 0
    assert "no verified documents were found" in res.answer.lower()


# ==============================================================================
# Scenario 09: Irrelevant Chunks Suppressed and Never Cited
# ==============================================================================
@pytest.mark.asyncio
async def test_scenario_09_irrelevant_chunks_suppressed(
    test_embedding_provider: EmbeddingProvider,
) -> None:
    """Verify irrelevant documents in index are neither echoed nor cited on unrelated queries."""
    vstore = QdrantVectorStore(embedding_provider=test_embedding_provider)
    bm25 = BM25Retriever(auto_save=False)
    retriever = HybridRetriever(vector_store=vstore, bm25=bm25)
    pipeline = RAGPipeline(retriever=retriever)

    tenant_id = "tenant-cafeteria"
    req = DocumentIngestRequest(
        content="The employee cafeteria serves vegetable lasagna on Thursdays and clam chowder on Fridays.",
        source="Cafeteria_Menu.txt",
    )
    await pipeline.ingest_document(req, tenant_id=tenant_id)

    res = await pipeline.generate_grounded_answer(
        query="What was our EBITDA and net operating debt?",
        tenant_id=tenant_id,
    )

    assert "lasagna" not in res.answer.lower()
    assert "chowder" not in res.answer.lower()
    assert res.status == "ABSTAINED"
    assert len(res.citations) == 0


# ==============================================================================
# Scenario 10: Model Explicit Epistemic Abstention Preserved
# ==============================================================================
@pytest.mark.asyncio
async def test_scenario_10_model_epistemic_abstention_preserved() -> None:
    """Verify model's honest statement of evidence absence is recognized as abstention and not dropped."""
    pipeline = RAGPipeline()
    tenant_id = "tenant-epistemic-10"

    chunk = DocumentChunk(
        chunk_id="chunk-rev-only",
        content="ACME Corp revenue was $100,000,000 for FY2026.",
        tenant_id=tenant_id,
        source="Revenue_Report.txt",
    )
    ctx_res = ContextSelectionResult(
        selected_chunks=[chunk],
        formatted_context=f"[{chunk.chunk_id}]: {chunk.content}",
        selected_tokens=10,
    )
    pipeline.retrieve_and_select_context = AsyncMock(return_value=(None, ctx_res))  # type: ignore

    abstention_text = "Based on the provided documents, there is no information about net profit or operating margin for FY2026."

    with patch(
        "app.rag.pipeline.call_upstream_llm",
        new=AsyncMock(return_value=abstention_text),
    ):
        gen_res = await pipeline.generate_grounded_answer(
            query="What was ACME FY2026 net profit?",
            tenant_id=tenant_id,
        )

    assert gen_res.status == "ABSTAINED"
    assert gen_res.abstention_reason == AbstentionReason.NO_RELEVANT_EVIDENCE
    assert "no information about net profit" in gen_res.answer.lower()


# ==============================================================================
# Scenario 11: Completely Contradictory Generation Produces Abstention
# ==============================================================================
@pytest.mark.asyncio
async def test_scenario_11_all_claims_contradicted_abstained() -> None:
    """Verify that when generated text completely contradicts retrieved evidence, generation halts with abstention."""
    pipeline = RAGPipeline()
    tenant_id = "tenant-contra-11"

    chunk = DocumentChunk(
        chunk_id="chunk-profit",
        content="ACME Corp reported record net profit of $85,000,000 for FY2026.",
        tenant_id=tenant_id,
        source="Audit_2026.txt",
    )
    ctx_res = ContextSelectionResult(
        selected_chunks=[chunk],
        formatted_context=f"[{chunk.chunk_id}]: {chunk.content}",
        selected_tokens=10,
    )
    pipeline.retrieve_and_select_context = AsyncMock(return_value=(None, ctx_res))  # type: ignore

    raw_answer = (
        "ACME Corp suffered a net loss of $950,000,000 and collapsed into bankruptcy."
    )

    with patch(
        "app.rag.pipeline.call_upstream_llm",
        new=AsyncMock(return_value=raw_answer),
    ):
        gen_res = await pipeline.generate_grounded_answer(
            query="What was ACME net profit?",
            tenant_id=tenant_id,
        )

    assert gen_res.status == "ABSTAINED"
    assert gen_res.abstention_reason in (
        AbstentionReason.GENERATION_FAILURE,
        AbstentionReason.CONTRADICTORY_EVIDENCE,
    )
    assert len(gen_res.citations) == 0
    assert "cannot verify the generated statements" in gen_res.answer.lower()


# ==============================================================================
# Scenario 12: Public HTTP API Boundary (/api/v1/rag/generate) Integration
# ==============================================================================
@pytest.mark.asyncio
async def test_scenario_12_public_http_api_boundary_grounding(
    auth_headers: dict[str, str],
) -> None:
    """Verify public HTTP endpoint /api/v1/rag/generate executes full 10-step RAG and returns grounding provenance."""
    async with AsyncClient(
        transport=ASGITransport(app=app),
        base_url="http://testserver",
    ) as client:
        # 1. Ingest document via HTTP
        ingest_payload = {
            "content": "Enterprise software maintenance revenue was $65,000,000 for Q3.",
            "source": "Software_Revenue.txt",
            "metadata": {"unit": "enterprise_software"},
        }
        ingest_resp = await client.post(
            "/api/v1/rag/ingest",
            json=ingest_payload,
            headers=auth_headers,
        )
        assert ingest_resp.status_code == 201

        # 2. Call /api/v1/rag/generate
        gen_payload = {
            "query": "What was enterprise software maintenance revenue for Q3?",
            "top_k": 5,
            "max_context_tokens": 800,
        }
        gen_resp = await client.post(
            "/api/v1/rag/generate",
            json=gen_payload,
            headers=auth_headers,
        )
        assert gen_resp.status_code == 200
        body = gen_resp.json()

        assert body["status"] == "SUCCESS"
        assert body["tenant_id"] == "tenant-grounding-test"
        assert "$65,000,000" in body["answer"]
        assert len(body["citations"]) >= 1
        assert body["citations"][0]["source"] == "Software_Revenue.txt"
        assert body["citations"][0]["tenant_id"] == "tenant-grounding-test"

        # Verify grounding provenance is present in HTTP response
        assert "grounding" in body
        assert body["grounding"] is not None
        assert body["grounding"]["is_grounded"] is True
        assert len(body["grounding"]["claims"]) >= 1
        assert body["grounding"]["claims"][0]["entailment"] == "SUPPORTED"
