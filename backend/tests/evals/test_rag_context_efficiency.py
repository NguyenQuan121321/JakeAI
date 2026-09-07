"""RAG Context Efficiency & Quality Evaluation Benchmark Suite.

Validates Section 4, 5, and 6 of 04_RAG.md:
1. Context reduction measured (>= 35-45% token savings from candidate pool)
2. High relevance and evidence value preference
3. Low redundancy elimination
4. 100% preservation of numerical facts, dates, currencies, and citations
5. Citation correctness & tenant boundary verification
"""

import pytest

from app.evals.rag_evaluator import evaluate_rag_case
from app.rag.citations import CitationGenerator
from app.rag.context_selector import ContextSelector
from app.rag.models import DocumentChunk
from app.rag.pipeline import RAGPipeline


@pytest.fixture
def enterprise_rag_candidates() -> list[DocumentChunk]:
    """Provide realistic financial disclosure passages with high relevance, duplicates, and distractors."""
    return [
        # Highly relevant core passage with crucial numbers
        DocumentChunk(
            chunk_id="chunk-fin-001",
            content=(
                "=== DOCUMENT EXCERPT [SEC-Q3-P14] ===\n"
                "ACME Corporation Q3 Consolidated Results: Gross revenue reached $150,000,000 "
                "with operating expenses of $105,000,000. Net profit stood at $45,000,000 "
                "yielding a 30.0% operating margin."
            ),
            tenant_id="tenant-corp",
            source="ACME SEC Form 10-Q",
            score=0.96,
        ),
        # Redundant passage repeating identical facts with heavy corporate filler boilerplate
        DocumentChunk(
            chunk_id="chunk-fin-002",
            content=(
                "=== DOCUMENT EXCERPT [PR-WIRE-01] ===\n"
                "FOR IMMEDIATE RELEASE. All rights reserved. Confidential and proprietary. "
                "ACME Corporation Q3 Results announcement: Gross revenue was reported at $150,000,000 "
                "with operating expenses of $105,000,000 and net profit at $45,000,000. "
                "Please review full disclaimer at acme.com/legal for forward looking statements."
            ),
            tenant_id="tenant-corp",
            source="ACME Press Wire",
            score=0.91,
        ),
        # Supporting distinct passage with novel numerical metrics
        DocumentChunk(
            chunk_id="chunk-fin-003",
            content=(
                "=== DOCUMENT EXCERPT [SEC-Q3-P22] ===\n"
                "Cash and cash equivalents totaled $38,500,000 at the close of Q3, "
                "with free cash flow generation of $22,000,000."
            ),
            tenant_id="tenant-corp",
            source="ACME SEC Cash Flow Statement",
            score=0.85,
        ),
        # Low-relevance distractor passage
        DocumentChunk(
            chunk_id="chunk-fin-004",
            content=(
                "Corporate campus cafeteria menu for September 2026: Grilled salmon, "
                "organic salads, and beverage bar available for all headquarters employees."
            ),
            tenant_id="tenant-corp",
            source="HQ Employee Handbook",
            score=0.15,
        ),
        # Another weak distractor
        DocumentChunk(
            chunk_id="chunk-fin-005",
            content=(
                "Visitor parking registration policy: Please register vehicles at the security desk "
                "upon arrival at building C."
            ),
            tenant_id="tenant-corp",
            source="HQ Visitor Policy",
            score=0.10,
        ),
    ]


def test_context_selector_efficiency_and_redundancy_elimination(
    enterprise_rag_candidates: list[DocumentChunk],
) -> None:
    """Verify ContextSelector achieves >= 35% token reduction while preserving all numbers and citations."""
    selector = ContextSelector(
        min_relative_score=0.30,
        redundancy_threshold=0.60,
        max_context_tokens=800,
    )

    query = (
        "What was ACME Corporation Q3 gross revenue, net profit, and free cash flow?"
    )
    result = selector.select_context(
        candidates=enterprise_rag_candidates,
        query=query,
        tenant_id="tenant-corp",
    )

    # 1. Reduction Measurement Gate
    assert result.raw_tokens > result.selected_tokens
    assert result.tokens_saved > 0
    # Expected token reduction percentage >= 35% due to distractor pruning & duplicate reduction
    assert result.reduction_ratio >= 0.35, (
        f"Context reduction ratio {result.reduction_ratio:.2%} was below 35% target"
    )
    assert result.pruned_chunks_count >= 2

    # 2. Fact Preservation Invariants
    # Every critical numerical figure must be preserved in selected context
    assert "$150,000,000" in result.formatted_context
    assert "$105,000,000" in result.formatted_context
    assert "$45,000,000" in result.formatted_context
    assert "$38,500,000" in result.formatted_context
    assert "$22,000,000" in result.formatted_context
    assert "30.0%" in result.formatted_context

    # 3. Citation Tag Preservation
    assert any("SEC-Q3-P14" in c for c in result.citations_preserved)
    assert any("SEC-Q3-P22" in c for c in result.citations_preserved)

    # 4. Distractors completely eliminated
    assert "cafeteria menu" not in result.formatted_context
    assert "Visitor parking" not in result.formatted_context


def test_citation_generator_precision_and_groundedness(
    enterprise_rag_candidates: list[DocumentChunk],
) -> None:
    """Verify CitationGenerator correctly maps generated claims to passages with zero hallucinated sources."""
    generator = CitationGenerator()
    generated_text = (
        "ACME Corporation reported gross revenue of $150,000,000 and net profit of $45,000,000 for Q3. "
        "Free cash flow generation reached $22,000,000."
    )

    annotated, citations = generator.generate_citations(
        text=generated_text,
        passages=enterprise_rag_candidates[:3],
    )

    assert len(citations) >= 2
    assert "[^1]" in annotated
    assert "#### 📚 Verifiable Citations & Sources" in annotated

    for cite in citations:
        assert cite.tenant_id == "tenant-corp"
        assert cite.confidence >= 0.85
        assert len(cite.snippet) > 0


def test_rag_evaluator_context_reduction_and_quality() -> None:
    """Verify RAG evaluator verifies context reduction, anti-hallucination, and citation precision."""
    eval_case = {
        "case_id": "eval_efficiency_001",
        "query": "What is Q3 operating revenue and profit?",
        "context": "Q3 operating revenue is $150M with operating profit of $45M.",
        "response": "Operating revenue is $150M with operating profit of $45M.",
        "ground_truth": "Revenue is $150M and profit is $45M.",
        "tenant_id": "tenant-corp",
        "foreign_tenant_id": "tenant-rogue",
        "raw_tokens": 500,
        "selected_tokens": 280,
        "citations": [
            {
                "index": 1,
                "source": "Q3 SEC Filing",
                "snippet": "Q3 operating revenue is $150M",
                "tenant_id": "tenant-corp",
                "confidence": 0.95,
            }
        ],
    }

    result = evaluate_rag_case(eval_case)
    assert result.passed
    assert result.anti_hallucination_passed
    assert result.tenant_isolation_verified
    assert not result.data_leakage_detected
    assert result.faithfulness_score >= 0.80
    assert result.context_relevancy_score >= 0.70
    assert result.context_reduction_ratio >= 0.40  # (500 - 280) / 500 = 44%
    assert result.citation_precision == 1.0


@pytest.mark.asyncio
async def test_rag_pipeline_10_step_lifecycle_efficiency() -> None:
    """Verify complete RAGPipeline lifecycle achieves context efficiency and grounded synthesis."""
    pipeline = RAGPipeline()

    long_report = (
        "Q3 Strategic Review for FinTech Services Corp.\n\n"
        "Segment 1 Financials: Digital Banking achieved gross revenue of $84,000,000 "
        "with EBITDA of $26,000,000. Customer retention reached 94.2%.\n\n"
        "Legal notice: All forward looking statements involve risks. Copyright 2026.\n\n"
        "Segment 2 Financials: Wealth Management generated fees of $31,000,000 "
        "with assets under custody of $4,200,000,000."
    )

    ingest_res = await pipeline.ingest_document(
        request=(enterprise_rag_candidates.__name__ and None)
        or (DocumentChunk(chunk_id="temp", content="", tenant_id="") and None)
        or __import__(
            "app.rag.ingestion", fromlist=["DocumentIngestRequest"]
        ).DocumentIngestRequest(
            content=long_report,
            source="Q3 Strategic Filing",
            chunk_size=160,
            chunk_overlap=30,
        ),
        tenant_id="tenant-lifecycle-test",
    )

    assert ingest_res.status == "success"
    assert ingest_res.indexed_chunks >= 2

    # Query pipeline with context selection
    _retrieval, selection = await pipeline.retrieve_and_select_context(
        query="Digital Banking gross revenue and EBITDA",
        tenant_id="tenant-lifecycle-test",
        max_context_tokens=500,
    )

    assert len(selection.selected_chunks) >= 1
    assert selection.selected_tokens > 0
    assert "$84,000,000" in selection.formatted_context
    assert "$26,000,000" in selection.formatted_context
    assert all(
        c.tenant_id == "tenant-lifecycle-test" for c in selection.selected_chunks
    )
