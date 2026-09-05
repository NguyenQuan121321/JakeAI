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
