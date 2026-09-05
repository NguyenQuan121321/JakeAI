"""RAG document ingestion and retrieval endpoints."""

from fastapi import APIRouter, Depends, status
from pydantic import BaseModel, Field

from app.core.context import TenantContext
from app.core.security import get_current_tenant
from app.rag.ingestion import (
    DocumentIngestRequest,
    DocumentIngestResponse,
    default_ingestion_pipeline,
)
from app.rag.models import DocumentChunk
from app.rag.retriever import default_hybrid_retriever

router = APIRouter()


class RAGQueryRequest(BaseModel):
    """Payload to search tenant RAG index."""

    query: str = Field(
        ...,
        min_length=1,
        max_length=2000,
        description="Query text to retrieve relevant chunks",
    )
    top_k: int = Field(
        default=5,
        ge=1,
        le=20,
        description="Maximum number of chunks to return",
    )


class RAGQueryResponse(BaseModel):
    """Response returning retrieved document chunks and latency."""

    query: str
    tenant_id: str
    chunks: list[DocumentChunk]
    latency_ms: float
    total_candidates: int


@router.post(
    "/ingest",
    response_model=DocumentIngestResponse,
    status_code=status.HTTP_201_CREATED,
    summary="Ingest document into tenant RAG index",
    description="Chunk, embed, and index document into tenant-isolated vector and keyword stores.",
)
async def ingest_document(
    request: DocumentIngestRequest,
    tenant_ctx: TenantContext = Depends(get_current_tenant),
) -> DocumentIngestResponse:
    """Ingest document text into hybrid dense and sparse stores scoped to tenant."""
    return await default_ingestion_pipeline.ingest(
        request=request,
        tenant_id=tenant_ctx.tenant_id,
    )


@router.post(
    "/query",
    response_model=RAGQueryResponse,
    status_code=status.HTTP_200_OK,
    summary="Query tenant-isolated RAG index",
    description="Retrieve relevant document chunks using hybrid dense vector and sparse lexical search.",
)
async def query_documents(
    request: RAGQueryRequest,
    tenant_ctx: TenantContext = Depends(get_current_tenant),
) -> RAGQueryResponse:
    """Retrieve indexed document chunks for tenant."""
    result = await default_hybrid_retriever.retrieve(
        query=request.query,
        tenant_id=tenant_ctx.tenant_id,
        top_k=request.top_k,
    )
    return RAGQueryResponse(
        query=result.query,
        tenant_id=tenant_ctx.tenant_id,
        chunks=result.chunks,
        latency_ms=result.latency_ms,
        total_candidates=result.total_candidates,
    )
