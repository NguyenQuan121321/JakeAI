"""RAG document ingestion and retrieval endpoints with asynchronous bounded task queue."""

from fastapi import APIRouter, Depends, HTTPException, Query, Response, status
from pydantic import BaseModel, Field

from app.core.context import TenantContext
from app.core.security import get_current_tenant
from app.rag.context_selector import get_context_selector
from app.rag.ingestion import (
    DocumentIngestRequest,
    DocumentIngestResponse,
    default_ingestion_pipeline,
)
from app.rag.models import Citation, DocumentChunk
from app.rag.pipeline import default_rag_pipeline
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
    select_context: bool = Field(
        default=False,
        description="Whether to apply context selection, deduplication, and budget packing",
    )
    max_context_tokens: int = Field(
        default=800,
        ge=100,
        le=4000,
        description="Maximum context tokens ceiling for selection",
    )


class RAGQueryResponse(BaseModel):
    """Response returning retrieved document chunks and latency."""

    query: str
    tenant_id: str
    chunks: list[DocumentChunk]
    latency_ms: float
    total_candidates: int
    selected_context: str | None = Field(
        default=None,
        description="Structured context string with citation markers if select_context=True",
    )
    context_tokens: int | None = Field(
        default=None,
        description="Tokens in selected context",
    )
    tokens_saved: int | None = Field(
        default=None,
        description="Tokens eliminated through relevance filtering and redundancy pruning",
    )
    reduction_ratio: float | None = Field(
        default=None,
        description="Token reduction ratio: tokens_saved / raw_candidate_tokens",
    )


class RAGGenerateRequest(BaseModel):
    """Payload for full 10-step RAG grounded generation."""

    query: str = Field(
        ...,
        min_length=1,
        max_length=2000,
        description="Query or question to answer using grounded tenant context",
    )
    top_k: int = Field(
        default=5,
        ge=1,
        le=20,
        description="Number of candidate chunks to retrieve",
    )
    max_context_tokens: int = Field(
        default=800,
        ge=100,
        le=4000,
        description="Maximum tokens allocated for selected context",
    )
    model: str | None = Field(
        default=None,
        description="Optional provider model override",
    )


class RAGGenerateResponse(BaseModel):
    """Outcome of full 10-step RAG grounded generation."""

    query: str
    tenant_id: str
    answer: str
    citations: list[Citation] = Field(default_factory=list)
    context_tokens: int
    tokens_saved: int
    reduction_ratio: float
    latency_ms: float


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
    """Retrieve indexed document chunks for tenant with optional context selection."""
    retrieval_res = await default_hybrid_retriever.retrieve(
        query=request.query,
        tenant_id=tenant_ctx.tenant_id,
        top_k=request.top_k,
    )

    if not request.select_context:
        return RAGQueryResponse(
            query=retrieval_res.query,
            tenant_id=tenant_ctx.tenant_id,
            chunks=retrieval_res.chunks,
            latency_ms=retrieval_res.latency_ms,
            total_candidates=retrieval_res.total_candidates,
        )

    context_selector = get_context_selector()
    context_res = context_selector.select_context(
        candidates=retrieval_res.chunks,
        query=request.query,
        tenant_id=tenant_ctx.tenant_id,
        max_tokens=request.max_context_tokens,
    )

    return RAGQueryResponse(
        query=retrieval_res.query,
        tenant_id=tenant_ctx.tenant_id,
        chunks=context_res.selected_chunks,
        latency_ms=retrieval_res.latency_ms,
        total_candidates=retrieval_res.total_candidates,
        selected_context=context_res.formatted_context,
        context_tokens=context_res.selected_tokens,
        tokens_saved=context_res.tokens_saved,
        reduction_ratio=context_res.reduction_ratio,
    )


@router.post(
    "/generate",
    response_model=RAGGenerateResponse,
    status_code=status.HTTP_200_OK,
    summary="Generate grounded answer via 10-step RAG pipeline",
    description="Execute full 10-step RAG: hybrid search, rerank, context select, grounded synthesis, and citation mapping.",
)
async def generate_rag_answer(
    request: RAGGenerateRequest,
    tenant_ctx: TenantContext = Depends(get_current_tenant),
) -> RAGGenerateResponse:
    """Execute end-to-end grounded RAG generation with verifiable inline citations."""
    gen_result = await default_rag_pipeline.generate_grounded_answer(
        query=request.query,
        tenant_id=tenant_ctx.tenant_id,
        max_context_tokens=request.max_context_tokens,
        top_k=request.top_k,
        model=request.model,
    )
    return RAGGenerateResponse(
        query=gen_result.query,
        tenant_id=gen_result.tenant_id,
        answer=gen_result.answer,
        citations=gen_result.citations,
        context_tokens=gen_result.context_selection.selected_tokens,
        tokens_saved=gen_result.context_selection.tokens_saved,
        reduction_ratio=gen_result.context_selection.reduction_ratio,
        latency_ms=gen_result.latency_ms,
    )
