"""Unified 10-Step Enterprise RAG Pipeline for JakeAI Platform.

Implements the complete lifecycle mandated by 04_RAG.md:
1. Ingestion
2. Chunking
3. Metadata Extraction
4. Indexing (Dense Vector + Sparse BM25)
5. Candidate Retrieval
6. Hybrid Retrieval
7. Reranking (Cross-Encoder / RRF)
8. Context Selection (Evidence-preserving, token-bounded deduplication)
9. Citation Mapping (Inline footnote attribution)
10. Generation (Grounded LLM synthesis with anti-hallucination guardrails and explicit abstention)
"""

from __future__ import annotations

import logging
import re
import time

from app.core.config import get_settings
from app.core.llm_provider import call_upstream_llm
from app.rag.citations import CitationGenerator
from app.rag.context_selector import ContextSelector, get_context_selector
from app.rag.grounding import (
    METRIC_REGEX,
    STOPWORDS,
    GroundingVerifier,
    get_grounding_verifier,
)
from app.rag.ingestion import (
    DocumentIngestionPipeline,
    DocumentIngestRequest,
    DocumentIngestResponse,
    default_ingestion_pipeline,
)
from app.rag.models import (
    AbstentionReason,
    Citation,
    ContextSelectionResult,
    RAGGenerationResult,
    RetrievalResult,
)
from app.rag.retriever import (
    HybridRetriever,
    default_hybrid_retriever,
)

logger = logging.getLogger(__name__)

DEFAULT_RAG_SYSTEM_PROMPT = (
    "You are JakeAI's verified enterprise financial and technical knowledge specialist.\n"
    "Answer the user query faithfully and accurately based strictly on the provided verified sources.\n"
    "Rules:\n"
    "1. Only state facts, numbers, dates, and metrics directly supported by the context.\n"
    "2. Never fabricate, estimate, or hallucinate financial figures.\n"
    "3. Reference source documents using inline citations like [^1], [^2] where applicable.\n"
    "4. If the context does not contain enough information, explicitly state that."
)


class RAGPipeline:
    """Enterprise RAG engine unifying ingestion, hybrid search, context selection, and generation."""

    def __init__(
        self,
        retriever: HybridRetriever | None = None,
        ingestion_pipeline: DocumentIngestionPipeline | None = None,
        context_selector: ContextSelector | None = None,
        citation_generator: CitationGenerator | None = None,
        grounding_verifier: GroundingVerifier | None = None,
    ) -> None:
        self.retriever = retriever or default_hybrid_retriever
        self.ingestion_pipeline = ingestion_pipeline or default_ingestion_pipeline
        self.context_selector = context_selector or get_context_selector()
        self.citation_generator = citation_generator or CitationGenerator()
        self.grounding_verifier = grounding_verifier or get_grounding_verifier()

    async def ingest_document(
        self,
        request: DocumentIngestRequest,
        tenant_id: str,
    ) -> DocumentIngestResponse:
        """Step 1-4: Ingest, chunk, tag metadata, and index document into tenant namespace."""
        return await self.ingestion_pipeline.ingest(
            request=request, tenant_id=tenant_id
        )

    async def retrieve_candidates(
        self,
        query: str,
        tenant_id: str,
        candidate_pool: int = 15,
        top_k: int = 5,
    ) -> RetrievalResult:
        """Step 5-7: Parallel dense/sparse candidate retrieval, tenant filtering, and cross-encoder reranking."""
        return await self.retriever.retrieve(
            query=query,
            tenant_id=tenant_id,
            top_k=top_k,
            candidate_pool=candidate_pool,
        )

    async def retrieve_and_select_context(
        self,
        query: str,
        tenant_id: str,
        top_k: int = 5,
        candidate_pool: int = 15,
        max_context_tokens: int = 800,
        min_relative_score: float = 0.30,
        redundancy_threshold: float = 0.65,
    ) -> tuple[RetrievalResult, ContextSelectionResult]:
        """Step 5-8: Retrieve candidate passages, rerank, and select minimal sufficient evidence context."""
        retrieval_res = await self.retrieve_candidates(
            query=query,
            tenant_id=tenant_id,
            candidate_pool=candidate_pool,
            top_k=top_k,
        )

        context_res = self.context_selector.select_context(
            candidates=retrieval_res.chunks,
            query=query,
            tenant_id=tenant_id,
            max_tokens=max_context_tokens,
            min_relative_score=min_relative_score,
            redundancy_threshold=redundancy_threshold,
        )

        return retrieval_res, context_res

    async def generate_grounded_answer(
        self,
        query: str,
        tenant_id: str,
        max_context_tokens: int = 800,
        top_k: int = 5,
        candidate_pool: int = 15,
        model: str | None = None,
        system_instruction: str | None = None,
    ) -> RAGGenerationResult:
        """Step 1-10: Execute end-to-end RAG pipeline from retrieval through synthesis, claim verification, and citation mapping."""
        start_time = time.time()

        # Step 5-8: Retrieve and select minimal sufficient context
        _retrieval_res, context_res = await self.retrieve_and_select_context(
            query=query,
            tenant_id=tenant_id,
            top_k=top_k,
            candidate_pool=candidate_pool,
            max_context_tokens=max_context_tokens,
        )

        # Explicit Abstention: No relevant evidence available
        if not context_res.selected_chunks:
            answer = (
                f"I cannot answer this question because no verified documents were found for tenant `{tenant_id}`. "
                "Please ensure relevant documents are indexed in your tenant workspace."
            )
            elapsed = round((time.time() - start_time) * 1000, 2)
            return RAGGenerationResult(
                query=query,
                tenant_id=tenant_id,
                answer=answer,
                citations=[],
                context_selection=context_res,
                latency_ms=elapsed,
                status="ABSTAINED",
                abstention_reason=AbstentionReason.NO_RELEVANT_EVIDENCE,
            )

        # Assemble grounded prompt
        sys_prompt = system_instruction or DEFAULT_RAG_SYSTEM_PROMPT
        prompt = (
            f"{sys_prompt}\n\n"
            f"### Verified Sources & Context:\n"
            f"{context_res.formatted_context}\n\n"
            f"### User Question:\n{query}\n\n"
            f"### Answer:"
        )

        # Step 10: Call upstream LLM provider
        raw_answer: str | None = None
        try:
            raw_answer = await call_upstream_llm(
                prompt=prompt,
                tenant_id=tenant_id,
                model=model or "default",
            )
        except Exception as exc:
            logger.warning("Upstream LLM invocation failed: %s", exc)
            elapsed = round((time.time() - start_time) * 1000, 2)
            return RAGGenerationResult(
                query=query,
                tenant_id=tenant_id,
                answer="I am unable to generate an answer at this time due to an upstream model provider failure.",
                citations=[],
                context_selection=context_res,
                latency_ms=elapsed,
                status="ABSTAINED",
                abstention_reason=AbstentionReason.PROVIDER_FAILURE,
            )

        if not raw_answer:
            settings = get_settings()
            env = settings.ENVIRONMENT.lower()
            if env == "production":
                # In production, missing LLM output is an explicit provider failure
                elapsed = round((time.time() - start_time) * 1000, 2)
                return RAGGenerationResult(
                    query=query,
                    tenant_id=tenant_id,
                    answer="I am unable to generate an answer at this time due to an upstream model provider failure.",
                    citations=[],
                    context_selection=context_res,
                    latency_ms=elapsed,
                    status="ABSTAINED",
                    abstention_reason=AbstentionReason.PROVIDER_FAILURE,
                )

            # In dev/test: perform deterministic grounded synthesis only if evidence is relevant
            top_chunk = context_res.selected_chunks[0]
            query_terms = {
                w.lower()
                for w in re.findall(r"\b[a-zA-Z0-9_\-\$]{3,}\b", query)
                if w.lower() not in STOPWORDS
            }
            chunk_terms = {
                w.lower()
                for w in re.findall(r"\b[a-zA-Z0-9_\-\$]{3,}\b", top_chunk.content)
                if w.lower() not in STOPWORDS
            }
            query_nums = set(METRIC_REGEX.findall(query))
            chunk_nums = set(METRIC_REGEX.findall(top_chunk.content))

            # Never echo irrelevant chunks on LLM absence
            if not query_terms.intersection(
                chunk_terms
            ) and not query_nums.intersection(chunk_nums):
                elapsed = round((time.time() - start_time) * 1000, 2)
                return RAGGenerationResult(
                    query=query,
                    tenant_id=tenant_id,
                    answer="I cannot answer this question because no relevant evidence was found.",
                    citations=[],
                    context_selection=context_res,
                    latency_ms=elapsed,
                    status="ABSTAINED",
                    abstention_reason=AbstentionReason.NO_RELEVANT_EVIDENCE,
                )

            raw_answer = f"Based on verified records ({top_chunk.source}): {top_chunk.content.strip()}"

        # Step 9b: Grounding and Entailment Verification
        verification = self.grounding_verifier.verify(
            text=raw_answer,
            passages=context_res.selected_chunks,
        )

        if not verification.is_grounded and not verification.verified_answer:
            # All statements failed grounding verification: explicit generation abstention
            elapsed = round((time.time() - start_time) * 1000, 2)
            return RAGGenerationResult(
                query=query,
                tenant_id=tenant_id,
                answer="I cannot verify the generated statements against the retrieved enterprise records. To avoid inaccurate information, generation was halted.",
                citations=[],
                context_selection=context_res,
                latency_ms=elapsed,
                status="ABSTAINED",
                abstention_reason=AbstentionReason.GENERATION_FAILURE,
            )

        verified_text = (
            verification.verified_answer if verification.verified_answer else raw_answer
        )

        # Step 9: Citation Mapping
        annotated_answer, citations = self.citation_generator.generate_citations(
            text=verified_text,
            passages=context_res.selected_chunks,
        )

        # Enforce strict tenant boundary on all citations
        valid_citations: list[Citation] = [
            c for c in citations if c.tenant_id == tenant_id
        ]

        elapsed_ms = round((time.time() - start_time) * 1000, 2)

        return RAGGenerationResult(
            query=query,
            tenant_id=tenant_id,
            answer=annotated_answer,
            citations=valid_citations,
            context_selection=context_res,
            latency_ms=elapsed_ms,
            status="SUCCESS",
            abstention_reason=None,
        )


default_rag_pipeline = RAGPipeline()


def get_rag_pipeline() -> RAGPipeline:
    """Singleton getter for unified RAGPipeline."""
    global default_rag_pipeline
    return default_rag_pipeline
