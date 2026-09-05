"""RAG document ingestion and retrieval endpoints."""

from fastapi import APIRouter, Depends, status

from app.core.context import TenantContext
from app.core.security import get_current_tenant
from app.rag.ingestion import (
    DocumentIngestRequest,
    DocumentIngestResponse,
    default_ingestion_pipeline,
)

router = APIRouter()


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
