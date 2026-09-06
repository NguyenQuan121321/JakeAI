"""RAG document ingestion and retrieval endpoints with asynchronous bounded task queue."""

from fastapi import APIRouter, Depends, HTTPException, Query, Response, status
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
from app.rag.tasks import (
    IngestionTaskResponse,
    IngestionTaskState,
    get_task_manager,
)

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
    response_model=DocumentIngestResponse | IngestionTaskResponse,
    status_code=status.HTTP_201_CREATED,
    summary="Ingest document into tenant RAG index",
    description=(
        "Chunk, embed, and index document into tenant-isolated stores. "
        "Supports asynchronous bounded task queue (202 Accepted) or synchronous ingestion (201 Created)."
    ),
    responses={
        201: {
            "model": DocumentIngestResponse,
            "description": "Document ingested synchronously",
        },
        202: {
            "model": IngestionTaskResponse,
            "description": "Document ingestion job enqueued for bounded background processing",
        },
    },
)
async def ingest_document(
    request: DocumentIngestRequest,
    response: Response,
    async_mode: bool = Query(
        default=False,
        description="Enqueue document for asynchronous bounded worker processing (202 Accepted)",
    ),
    tenant_ctx: TenantContext = Depends(get_current_tenant),
) -> DocumentIngestResponse | IngestionTaskResponse:
    """Ingest document text synchronously or enqueue into the bounded task queue."""
    if not async_mode:
        response.status_code = status.HTTP_201_CREATED
        return await default_ingestion_pipeline.ingest(
            request=request,
            tenant_id=tenant_ctx.tenant_id,
        )

    task_mgr = get_task_manager()
    task_res = await task_mgr.enqueue(request, tenant_ctx.tenant_id)
    response.status_code = status.HTTP_202_ACCEPTED
    return task_res


@router.get(
    "/tasks/{task_id}",
    response_model=IngestionTaskState,
    status_code=status.HTTP_200_OK,
    summary="Poll status of asynchronous ingestion task",
    description="Retrieve the current status, chunk count, and execution outcome of an ingestion task.",
)
async def get_ingestion_task(
    task_id: str,
    tenant_ctx: TenantContext = Depends(get_current_tenant),
) -> IngestionTaskState:
    """Poll status of an asynchronous document ingestion job, enforcing tenant isolation."""
    task_mgr = get_task_manager()
    task = await task_mgr.get_task(task_id, tenant_id=tenant_ctx.tenant_id)
    if task is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Task '{task_id}' not found for tenant '{tenant_ctx.tenant_id}'.",
        )
    return task


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
