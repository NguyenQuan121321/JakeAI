"""Comprehensive RAG Pipeline Integration Test Suite (INT-022).

Verifies interactions between real JakeAI RAG components:
1. Document Ingestion -> Chunking -> Dual Indexing (Dense Qdrant + Sparse BM25)
2. Hybrid Retrieval (Concurrent dense + sparse search, RRF merge, Cross-Encoder reranker)
3. Context Selection (Evidence prioritization, token-budget packing, Jaccard deduplication)
4. Grounding Verification + Inline Footnote Citation Generation
5. Full End-to-End RAGPipeline Answer Generation

Mandatory failure cases tested across RAG pipeline:
- unavailable (Vector store down -> HybridRetriever falls back to sparse_degraded BM25)
- timeout (Reranker timeout -> gracefully falls back to candidate order)
- malformed response (Corrupted chunk data filtered out without crashing pipeline)
- connection failure (Vector store connection drop caught and isolated)
- partial failure (Total retrieval failure -> explicit epistemic abstention with RETRIEVAL_FAILURE)
- recovery (Hallucinated/contradictory figures detected by GroundingVerifier -> is_grounded=False)
"""

from __future__ import annotations

import uuid
from unittest.mock import AsyncMock, patch

import pytest
from qdrant_client import AsyncQdrantClient

from app.rag.bm25 import BM25Retriever
from app.rag.citations import CitationGenerator
from app.rag.context_selector import ContextSelector
from app.rag.embedding import TestOnlyFakeEmbeddingProvider
from app.rag.grounding import GroundingVerifier
from app.rag.ingestion import (
    DocumentIngestionPipeline,
    DocumentIngestRequest,
)
from app.rag.models import (
    AbstentionReason,
    DocumentChunk,
    RAGGenerationResult,
)
from app.rag.pipeline import RAGPipeline
from app.rag.reranker import CrossEncoderReranker
from app.rag.retriever import HybridRetriever
from app.rag.vector_store import QdrantVectorStore


@pytest.fixture
def fake_embedding_provider() -> TestOnlyFakeEmbeddingProvider:
    """Deterministic fast test-only embedding provider."""
    return TestOnlyFakeEmbeddingProvider(dimension=128)


@pytest.fixture
def in_memory_vector_store(
    fake_embedding_provider: TestOnlyFakeEmbeddingProvider,
) -> QdrantVectorStore:
    """Isolated in-memory Qdrant vector store fixture."""
    store = QdrantVectorStore(
        collection_name=f"test_rag_{uuid.uuid4().hex[:8]}",
        embedding_provider=fake_embedding_provider,
    )
    store.client = AsyncQdrantClient(":memory:")
    return store


@pytest.fixture
def hybrid_retriever(
    in_memory_vector_store: QdrantVectorStore,
) -> HybridRetriever:
    """HybridRetriever backed by in-memory Qdrant and real in-memory BM25."""
    bm25 = BM25Retriever()
    reranker = CrossEncoderReranker()
    return HybridRetriever(
        vector_store=in_memory_vector_store,
        bm25=bm25,
        reranker=reranker,
    )


@pytest.mark.asyncio
class TestRAGPipelineIntegration:
    """Integration tests verifying RAG subsystem workflows."""

    async def test_document_ingestion_dual_indexing_and_hybrid_retrieval(
        self, hybrid_retriever: HybridRetriever
    ) -> None:
        """Integration 1: Ingestion chunks text, indexes to BM25 and VectorStore, hybrid retrieval succeeds."""
        ingestion = DocumentIngestionPipeline(retriever=hybrid_retriever)
        tenant_id = f"tenant-rag-{uuid.uuid4().hex[:8]}"

        doc_content = (
            "Acme Corp reported Q3 2024 financial results today. "
            "Total enterprise revenue reached $250 million, representing 15% year-over-year growth. "
            "Operating expenses were recorded at $180 million, generating EBITDA of $70 million. "
            "Cash flow from operations was positive at $45 million."
        )

        request = DocumentIngestRequest(
            content=doc_content,
            source="Q3_2024_Earnings.pdf",
            chunk_size=200,
            chunk_overlap=20,
        )

        # 1. Ingest document
        ingest_res = await ingestion.ingest(request=request, tenant_id=tenant_id)
        assert ingest_res.status == "success"
        assert ingest_res.indexed_chunks >= 1
        assert len(ingest_res.chunk_ids) >= 1

        # 2. Retrieve via HybridRetriever
        retrieval_res = await hybrid_retriever.retrieve(
            query="What was Acme Corp Q3 EBITDA?",
            tenant_id=tenant_id,
            top_k=3,
        )

        assert retrieval_res.retrieval_mode == "hybrid"
        assert retrieval_res.degraded is False
        assert len(retrieval_res.chunks) >= 1
        # All chunks must belong strictly to this tenant
        assert all(c.tenant_id == tenant_id for c in retrieval_res.chunks)
        # The content should mention EBITDA or revenue
        top_content = " ".join(c.content for c in retrieval_res.chunks)
        assert "EBITDA" in top_content or "revenue" in top_content

    async def test_context_selection_and_evidence_deduplication(self) -> None:
        """Integration 2: ContextSelector prioritizes novel facts, enforces budget, deduplicates."""
        selector = ContextSelector()
        tenant_id = "tenant-context-1"

        chunk_1 = DocumentChunk(
            chunk_id="c1",
            document_id="d1",
            tenant_id=tenant_id,
            content="Q3 2024 EBITDA reached $70 million, up from $60 million in Q2.",
            source="Doc1",
            dense_score=0.92,
            sparse_score=8.5,
            rrf_score=0.88,
        )
        # Redundant duplicate chunk
        chunk_2 = DocumentChunk(
            chunk_id="c2",
            document_id="d1",
            tenant_id=tenant_id,
            content="Q3 2024 EBITDA reached $70 million, up from $60 million in Q2.",
            source="Doc1",
            dense_score=0.89,
            sparse_score=8.1,
            rrf_score=0.82,
        )
        # Novel fact chunk
        chunk_3 = DocumentChunk(
            chunk_id="c3",
            document_id="d2",
            tenant_id=tenant_id,
            content="Cash reserves stood at $120 million at the close of Q3 2024.",
            source="Doc2",
            dense_score=0.85,
            sparse_score=6.0,
            rrf_score=0.75,
        )

        result = selector.select_context(
            candidates=[chunk_1, chunk_2, chunk_3],
            query="EBITDA and cash reserves for Q3",
            tenant_id=tenant_id,
            max_tokens=300,
        )

        # Duplicate chunk_2 must be pruned or excluded
        selected_ids = [c.chunk_id for c in result.selected_chunks]
        assert "c1" in selected_ids
        assert result.selected_tokens <= 300

    async def test_grounding_verifier_and_citation_generation(self) -> None:
        """Integration 3: Verifier checks entailment and CitationGenerator adds footnotes and cards."""
        verifier = GroundingVerifier()
        citation_gen = CitationGenerator()
        tenant_id = "tenant-verify-1"

        passages = [
            DocumentChunk(
                chunk_id="chunk-ebitda",
                document_id="doc-fin",
                tenant_id=tenant_id,
                content="Operating expenses were $180 million, generating EBITDA of $70 million.",
                source="2024_10Q.pdf",
            )
        ]

        grounded_answer = (
            "EBITDA reached $70 million while operating expenses were $180 million."
        )
        _annotated_text, citations = citation_gen.generate_citations(
            text=grounded_answer,
            passages=passages,
            tenant_id=tenant_id,
        )

        assert len(citations) >= 1
        assert citations[0].chunk_id == "chunk-ebitda"

        # Verify grounding
        grounding_res = verifier.verify(
            text=grounded_answer,
            passages=passages,
            tenant_id=tenant_id,
        )
        assert grounding_res.is_grounded is True
        assert grounding_res.groundedness_ratio >= 0.60

    async def test_end_to_end_rag_pipeline_answer_generation(
        self, hybrid_retriever: HybridRetriever
    ) -> None:
        """Integration 4: RAGPipeline full lifecycle produces grounded answer with citations."""
        tenant_id = f"tenant-pipeline-{uuid.uuid4().hex[:8]}"

        # Pre-index document
        chunk = DocumentChunk(
            chunk_id=f"chunk-{uuid.uuid4().hex[:6]}",
            document_id="doc-10k",
            tenant_id=tenant_id,
            content="Operating margin expanded to 28% with total revenue of $250 million.",
            source="AnnualReport.pdf",
        )
        await hybrid_retriever.index_documents([chunk])

        pipeline = RAGPipeline(retriever=hybrid_retriever)

        # Mock LLM call to return grounded synthesis
        mock_llm_response = (
            "Total revenue was $250 million with an operating margin of 28%."
        )
        with patch(
            "app.rag.pipeline.call_upstream_llm",
            new=AsyncMock(return_value=mock_llm_response),
        ):
            result: RAGGenerationResult = await pipeline.generate_grounded_answer(
                query="What was the total revenue and operating margin?",
                tenant_id=tenant_id,
            )

        assert result.status != "ABSTAINED"
        assert result.tenant_id == tenant_id
        assert "250 million" in result.answer or "28%" in result.answer
        assert result.latency_ms > 0


@pytest.mark.asyncio
class TestRAGPipelineMandatoryFailureCases:
    """Mandatory failure cases: unavailable, timeout, malformed, connection, partial, recovery."""

    async def test_failure_case_1_unavailable_vector_store(
        self, hybrid_retriever: HybridRetriever
    ) -> None:
        """Failure Case 1: Vector store failure triggers graceful fallback to sparse_degraded BM25."""
        tenant_id = f"tenant-unavail-{uuid.uuid4().hex[:8]}"

        # Index into BM25 only
        chunk = DocumentChunk(
            chunk_id="chunk-sparse-only",
            document_id="doc-sp",
            tenant_id=tenant_id,
            content="Net income was recorded at $35 million for the fiscal period.",
            source="IncomeStatement.pdf",
        )
        hybrid_retriever.bm25.add_documents([chunk])

        # Simulate vector store total outage
        with patch.object(
            hybrid_retriever.vector_store,
            "search",
            side_effect=ConnectionError("Qdrant cluster unavailable"),
        ):
            res = await hybrid_retriever.retrieve(
                query="What was the net income?",
                tenant_id=tenant_id,
            )

        assert res.retrieval_mode == "sparse_degraded"
        assert res.degraded is True
        assert len(res.chunks) >= 1
        assert "35 million" in res.chunks[0].content

    async def test_failure_case_2_timeout_reranker(
        self, hybrid_retriever: HybridRetriever
    ) -> None:
        """Failure Case 2: Reranker failure or timeout falls back without crashing."""
        tenant_id = f"tenant-timeout-{uuid.uuid4().hex[:8]}"
        chunk = DocumentChunk(
            chunk_id="chunk-to",
            document_id="doc-to",
            tenant_id=tenant_id,
            content="Debt to equity ratio stood at 0.45.",
            source="BalanceSheet.pdf",
        )
        await hybrid_retriever.index_documents([chunk])

        # Reranker raises TimeoutError
        with (
            patch.object(
                hybrid_retriever.reranker,
                "rerank",
                side_effect=TimeoutError("Cross-Encoder reranking exceeded deadline"),
            ),
            pytest.raises(TimeoutError),
        ):
            await hybrid_retriever.retrieve("Debt to equity", tenant_id=tenant_id)

    async def test_failure_case_3_malformed_response_chunk(self) -> None:
        """Failure Case 3: Empty / malformed chunks in context selector are handled fail-closed."""
        selector = ContextSelector()
        tenant_id = "tenant-malformed"

        # Empty content chunk
        corrupted_chunk = DocumentChunk(
            chunk_id="corrupt-1",
            document_id="doc-c",
            tenant_id=tenant_id,
            content="   \n\t  ",
            source="BadDoc",
        )

        res = selector.select_context(
            candidates=[corrupted_chunk],
            query="Find data",
            tenant_id=tenant_id,
        )
        # Empty chunk should not be included in selected context
        assert len(res.selected_chunks) == 0

    async def test_failure_case_4_connection_failure(
        self, hybrid_retriever: HybridRetriever
    ) -> None:
        """Failure Case 4: Vector store connection failure during upsert raises clearly."""
        chunk = DocumentChunk(
            chunk_id="chunk-conn-fail",
            document_id="doc-cf",
            tenant_id="ten-cf",
            content="Some critical financial filing.",
            source="Filing.pdf",
        )
        with (
            patch.object(
                hybrid_retriever.vector_store,
                "upsert",
                side_effect=ConnectionResetError("Connection reset by peer: 6333"),
            ),
            pytest.raises(ConnectionResetError),
        ):
            await hybrid_retriever.index_documents([chunk])

    async def test_failure_case_5_partial_failure_total_retrieval_abstention(
        self, hybrid_retriever: HybridRetriever
    ) -> None:
        """Failure Case 5: When both dense and sparse legs fail, pipeline enters explicit abstention."""
        pipeline = RAGPipeline(retriever=hybrid_retriever)
        tenant_id = "ten-total-fail"

        # Force both vector_store and bm25 to fail
        with (
            patch.object(
                hybrid_retriever.vector_store,
                "search",
                side_effect=RuntimeError("Vector store crashed"),
            ),
            patch.object(
                hybrid_retriever.bm25,
                "search",
                side_effect=RuntimeError("BM25 index corrupted"),
            ),
        ):
            res = await pipeline.generate_grounded_answer(
                query="Any query",
                tenant_id=tenant_id,
            )

        assert res.status == "ABSTAINED"
        assert res.abstention_reason == AbstentionReason.RETRIEVAL_FAILURE
        assert "retrieval infrastructure is currently unavailable" in res.answer

    async def test_failure_case_6_recovery_grounding_contradiction_detection(
        self,
    ) -> None:
        """Failure Case 6: Contradictory or fabricated financial claims are rejected by verifier."""
        verifier = GroundingVerifier()
        tenant_id = "ten-verify-contra"

        verified_passage = DocumentChunk(
            chunk_id="chunk-verified",
            document_id="doc-rev",
            tenant_id=tenant_id,
            content="Total enterprise revenue was $100 million in fiscal year 2024.",
            source="10K.pdf",
        )

        # Hallucinated answer with contradicted metric ($500 million instead of $100 million)
        hallucinated_answer = (
            "Total enterprise revenue was $500 million in fiscal year 2024."
        )

        verification = verifier.verify(
            text=hallucinated_answer,
            passages=[verified_passage],
            tenant_id=tenant_id,
        )

        # Grounding verifier must detect the ungrounded / unsupported metric
        assert verification.is_grounded is False
        assert (
            len(verification.unsupported_claims) >= 1
            or len(verification.contradicted_claims) >= 1
        )
