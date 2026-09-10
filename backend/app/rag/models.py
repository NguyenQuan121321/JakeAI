"""RAG and context retrieval data models."""

from enum import StrEnum
from typing import Any

from pydantic import BaseModel, Field


class AbstentionReason(StrEnum):
    """Canonical reasons for RAG generation abstention."""

    NO_RELEVANT_EVIDENCE = "NO_RELEVANT_EVIDENCE"
    PROVIDER_FAILURE = "PROVIDER_FAILURE"
    GENERATION_FAILURE = "GENERATION_FAILURE"


class ClaimEntailment(StrEnum):
    """Grounding entailment classification for generated statements."""

    SUPPORTED = "SUPPORTED"
    UNSUPPORTED = "UNSUPPORTED"
    UNCERTAIN = "UNCERTAIN"


class GroundingClaim(BaseModel):
    """Individual statement or claim extracted from generated answer for verification."""

    claim_text: str = Field(description="Statement or claim text")
    entailment: ClaimEntailment = Field(
        default=ClaimEntailment.UNCERTAIN,
        description="Entailment status against context evidence",
    )
    confidence: float = Field(
        default=1.0, description="Verification confidence score (0.0 to 1.0)"
    )
    supporting_chunk_ids: list[str] = Field(
        default_factory=list, description="IDs of passages directly supporting claim"
    )
    reasoning: str = Field(
        default="", description="Verification rationale or explanation"
    )


class DocumentChunk(BaseModel):
    """Atomic text chunk stored in dense/sparse indexes with tenant scoping."""

    chunk_id: str = Field(description="Unique chunk identifier")
    content: str = Field(description="Raw text content of the document passage")
    tenant_id: str = Field(description="Tenant identifier owning this document")
    source: str = Field(
        default="Internal Document", description="Document source or title"
    )
    metadata: dict[str, Any] = Field(
        default_factory=dict,
        description="Arbitrary document metadata",
    )
    score: float = Field(default=0.0, description="Retrieval or relevance score")


class Citation(BaseModel):
    """Verifiable citation linking generated response claims to source passages."""

    index: int = Field(description="Citation index footnote reference (e.g. 1)")
    source: str = Field(description="Origin source name or document path")
    snippet: str = Field(description="Verbatim excerpt from context supporting claim")
    tenant_id: str = Field(description="Tenant boundary verification")
    confidence: float = Field(default=1.0, description="Groundedness confidence score")


class RetrievalResult(BaseModel):
    """Consolidated results of a hybrid retrieval operation."""

    query: str = Field(description="Input user query")
    tenant_id: str = Field(description="Scoped tenant ID")
    chunks: list[DocumentChunk] = Field(
        default_factory=list,
        description="Top-ranked relevant document chunks",
    )
    total_candidates: int = Field(
        default=0, description="Total candidates retrieved before reranking"
    )
    latency_ms: float = Field(
        default=0.0, description="Total retrieval and reranking latency in ms"
    )
    retrieval_mode: str = Field(
        default="hybrid",
        description="Mode used: 'hybrid', 'dense_only', 'sparse_only', 'sparse_degraded'",
    )
    degraded: bool = Field(
        default=False,
        description="Whether retrieval operated in degraded fallback mode",
    )
    dense_candidate_count: int = Field(
        default=0, description="Count of candidates retrieved from dense index"
    )
    sparse_candidate_count: int = Field(
        default=0, description="Count of candidates retrieved from sparse index"
    )


class ContextSelectionResult(BaseModel):
    """Result of selecting, deduplicating, and bounding context from retrieved chunks."""

    selected_chunks: list[DocumentChunk] = Field(
        default_factory=list,
        description="High-relevance deduplicated chunks within token budget",
    )
    formatted_context: str = Field(
        default="",
        description="Structured context string with citation anchors for LLM injection",
    )
    raw_tokens: int = Field(
        default=0, description="Total tokens in initial retrieved candidate pool"
    )
    selected_tokens: int = Field(
        default=0, description="Tokens in final selected context"
    )
    tokens_saved: int = Field(
        default=0, description="Tokens eliminated via filtering and redundancy pruning"
    )
    reduction_ratio: float = Field(
        default=0.0,
        description="Context token reduction ratio: tokens_saved / raw_tokens",
    )
    pruned_chunks_count: int = Field(
        default=0,
        description="Number of low-scoring or redundant candidate chunks pruned",
    )
    citations_preserved: list[str] = Field(
        default_factory=list,
        description="Preserved citation markers in selected context",
    )


class RAGGenerationResult(BaseModel):
    """Consolidated response of the complete 10-step RAG pipeline."""

    query: str = Field(description="User query")
    tenant_id: str = Field(description="Scoped tenant boundary")
    answer: str = Field(
        description="Grounded generated answer with citation references"
    )
    citations: list[Citation] = Field(
        default_factory=list,
        description="Verifiable citations supporting generated answer",
    )
    context_selection: ContextSelectionResult = Field(
        description="Detailed context selection and token efficiency metrics"
    )
    latency_ms: float = Field(
        default=0.0, description="Total end-to-end RAG execution latency in ms"
    )
    status: str = Field(
        default="SUCCESS",
        description="Generation status: 'SUCCESS' or 'ABSTAINED'",
    )
    abstention_reason: AbstentionReason | str | None = Field(
        default=None,
        description="Reason code if status is ABSTAINED: 'NO_RELEVANT_EVIDENCE', 'PROVIDER_FAILURE', 'GENERATION_FAILURE'",
    )
