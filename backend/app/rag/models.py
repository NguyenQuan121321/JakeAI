"""RAG and context retrieval data models."""

from typing import Any

from pydantic import BaseModel, Field


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
