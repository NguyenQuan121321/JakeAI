"""Unit tests for TASK RAG-09, 10, 11: Grounding, Verifiable Citations, and Explicit Abstention."""

import pytest

from app.rag.citations import CitationGenerator
from app.rag.grounding import GroundingVerifier
from app.rag.ingestion import DocumentIngestRequest
from app.rag.models import (
    AbstentionReason,
    ClaimEntailment,
    DocumentChunk,
)
from app.rag.pipeline import RAGPipeline


def test_grounding_verifier_claim_classification() -> None:
    """Verify GroundingVerifier classifies SUPPORTED, UNSUPPORTED, and UNCERTAIN claims."""
    verifier = GroundingVerifier()
    passages = [
        DocumentChunk(
            chunk_id="p1",
            content="ACME Corp reported $150,000,000 in revenue and 30% margin for Q3 2026.",
            tenant_id="tenant-corp",
            source="Q3 Earnings",
        )
    ]

    # 1. Supported Claim
    claim_supported = "ACME Corp achieved $150,000,000 in revenue for Q3 2026."
    res_sup = verifier.verify_claim(claim_supported, passages)
    assert res_sup.entailment == ClaimEntailment.SUPPORTED
    assert "p1" in res_sup.supporting_chunk_ids
    assert res_sup.confidence >= 0.70

    # 2. Unsupported Claim with conflicting numbers
    claim_unsupported = "ACME Corp reported $999,000,000 in revenue for Q3 2026."
    res_unsup = verifier.verify_claim(claim_unsupported, passages)
    assert res_unsup.entailment == ClaimEntailment.UNSUPPORTED
    assert res_unsup.confidence == 0.0

    # 3. Unsupported Claim with completely fabricated statement
    claim_absent = "The CEO announced a complete shutdown of operations."
    res_absent = verifier.verify_claim(claim_absent, passages)
    assert res_absent.entailment == ClaimEntailment.UNSUPPORTED


def test_citation_generator_strips_hallucinated_footnotes() -> None:
    """Verify CitationGenerator removes arbitrary LLM hallucinated footnotes like [^99]."""
    generator = CitationGenerator()
    passages = [
        DocumentChunk(
            chunk_id="chunk-div",
            content="Quarterly dividend declared at $0.85 per share.",
            tenant_id="tenant-div",
            source="Dividend Notice",
        )
    ]

    text_with_hallucination = (
        "Dividend is $0.85 per share [^99]. Unrelated rumor is circulating [^42]."
    )
    annotated_text, citations = generator.generate_citations(
        text_with_hallucination, passages
    )

    # Hallucinated [^99] and [^42] must not persist in the final output
    assert "[^99]" not in annotated_text
    assert "[^42]" not in annotated_text

    # Valid passage must be cited with footnote [^1]
    assert "[^1]" in annotated_text
    assert len(citations) == 1
    assert citations[0].source == "Dividend Notice"
    assert citations[0].confidence >= 0.80


@pytest.mark.asyncio
async def test_pipeline_abstention_on_no_evidence() -> None:
    """Verify RAGPipeline explicitly returns status='ABSTAINED' and reason='NO_RELEVANT_EVIDENCE' when no chunks match."""
    pipeline = RAGPipeline()
    # Query for a tenant with empty index
    res = await pipeline.generate_grounded_answer(
        query="What was our EBITDA in 2026?",
        tenant_id="tenant-empty-workspace",
    )

    assert res.status == "ABSTAINED"
    assert res.abstention_reason == AbstentionReason.NO_RELEVANT_EVIDENCE
    assert len(res.citations) == 0
    assert "no verified documents were found" in res.answer


@pytest.mark.asyncio
async def test_pipeline_abstention_never_echoes_irrelevant_chunks() -> None:
    """Verify RAGPipeline never echoes irrelevant chunks when LLM synthesis is offline."""
    pipeline = RAGPipeline()
    # Ingest document about cafeteria menu
    req = DocumentIngestRequest(
        content="The cafeteria serves lasagna on Thursdays and fish tacos on Fridays.",
        source="Cafeteria Weekly Menu",
    )
    await pipeline.ingest_document(request=req, tenant_id="tenant-irrelevant")

    # Ask an unrelated financial question
    res = await pipeline.generate_grounded_answer(
        query="What was the total operating cash flow and net debt?",
        tenant_id="tenant-irrelevant",
    )

    # It must NOT echo the cafeteria menu!
    assert "lasagna" not in res.answer
    assert "tacos" not in res.answer
    assert res.status == "ABSTAINED"


@pytest.mark.asyncio
async def test_pipeline_abstention_on_provider_failure(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Verify RAGPipeline explicitly returns status='ABSTAINED' and reason='PROVIDER_FAILURE' on upstream error."""
    import app.rag.pipeline as pipeline_mod

    pipeline = RAGPipeline()
    req = DocumentIngestRequest(
        content="Enterprise revenue is $100M.",
        source="RevDoc",
    )
    await pipeline.ingest_document(request=req, tenant_id="tenant-prov-fail")

    async def failing_llm(*args: object, **kwargs: object) -> None:
        raise RuntimeError("Upstream API connection refused")

    monkeypatch.setattr(pipeline_mod, "call_upstream_llm", failing_llm)

    res = await pipeline.generate_grounded_answer(
        query="What was enterprise revenue?",
        tenant_id="tenant-prov-fail",
    )

    assert res.status == "ABSTAINED"
    assert res.abstention_reason == AbstentionReason.PROVIDER_FAILURE
    assert len(res.citations) == 0


@pytest.mark.asyncio
async def test_pipeline_abstention_on_generation_failure(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Verify RAGPipeline explicitly returns status='ABSTAINED' and reason='GENERATION_FAILURE' on completely ungrounded generation."""
    import app.rag.pipeline as pipeline_mod

    pipeline = RAGPipeline()
    req = DocumentIngestRequest(
        content="Enterprise revenue was $100,000,000 in FY2026.",
        source="RevDoc",
    )
    await pipeline.ingest_document(request=req, tenant_id="tenant-gen-fail")

    # Upstream LLM returns completely fabricated numbers and claims
    async def hallucinating_llm(*args: object, **kwargs: object) -> str:
        return "The company lost $950,000,000 and declared bankruptcy with $888,000,000 in penalties."

    monkeypatch.setattr(pipeline_mod, "call_upstream_llm", hallucinating_llm)

    res = await pipeline.generate_grounded_answer(
        query="What was enterprise revenue?",
        tenant_id="tenant-gen-fail",
    )

    assert res.status == "ABSTAINED"
    assert res.abstention_reason == AbstentionReason.GENERATION_FAILURE
    assert len(res.citations) == 0
    assert "cannot verify the generated statements" in res.answer
