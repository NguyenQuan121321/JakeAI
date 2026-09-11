"""RAG Document Ingestion Pipeline with RecursiveCharacterTextSplitter and Multiformat Parsers."""

from __future__ import annotations

import hashlib
import logging
import re
from typing import Any

from langchain_text_splitters import RecursiveCharacterTextSplitter
from pydantic import BaseModel, Field, model_validator

from app.rag.models import DocumentChunk
from app.rag.normalizer import normalize_text
from app.rag.parsers import (
    get_parser,
)
from app.rag.retriever import HybridRetriever, default_hybrid_retriever

logger = logging.getLogger(__name__)


class DocumentIngestRequest(BaseModel):
    """Payload for ingesting raw documents into tenant-isolated RAG indexes."""

    content: str = Field(
        default="",
        description="Raw document text to be chunked and indexed",
    )
    text: str | None = Field(
        default=None,
        description="Alias for content",
    )

    @model_validator(mode="before")
    @classmethod
    def harmonize_content_and_text(cls, data: Any) -> Any:
        if isinstance(data, dict):
            if not data.get("content") and data.get("text"):
                data["content"] = data["text"]
            elif not data.get("text") and data.get("content"):
                data["text"] = data["content"]
        return data

    source: str = Field(
        default="Internal Document",
        description="Source document name, URL, or identifier",
    )
    metadata: dict[str, Any] = Field(
        default_factory=dict,
        description="Arbitrary metadata attached to each document chunk",
    )
    chunk_size: int = Field(
        default=500,
        ge=50,
        le=4000,
        description="Maximum characters per document chunk",
    )
    chunk_overlap: int = Field(
        default=50,
        ge=0,
        le=1000,
        description="Character overlap between consecutive chunks",
    )


class DocumentIngestResponse(BaseModel):
    """Outcome metadata of document ingestion pipeline execution."""

    status: str = Field(default="success", description="Ingestion status")
    indexed_chunks: int = Field(description="Total chunks generated and indexed")
    chunk_ids: list[str] = Field(
        description="Unique deterministic IDs of created chunks"
    )
    source: str = Field(description="Document source identifier")
    tenant_id: str = Field(description="Tenant ID boundary where chunks reside")


class DocumentIngestionPipeline:
    """Pipelines documents (Text, Markdown, PDF) into chunked, embedded, and indexed DocumentChunk representations."""

    def __init__(self, retriever: HybridRetriever | None = None) -> None:
        self.retriever = retriever or default_hybrid_retriever

    def chunk_text(
        self,
        content: str,
        source: str,
        tenant_id: str,
        metadata: dict[str, Any] | None = None,
        chunk_size: int = 500,
        chunk_overlap: int = 50,
    ) -> list[DocumentChunk]:
        """Split text into overlapping chunks with deterministic identifiers."""
        normalized_content = normalize_text(content)

        splitter = RecursiveCharacterTextSplitter(
            chunk_size=chunk_size,
            chunk_overlap=chunk_overlap,
            separators=["\n\n", "\n", ". ", "; ", ", ", " ", ""],
        )

        raw_chunks = splitter.split_text(normalized_content)
        source_slug = (
            re.sub(r"[^a-zA-Z0-9_\-]+", "-", source.lower()).strip("-") or "doc"
        )

        chunks: list[DocumentChunk] = []
        base_meta = metadata.copy() if metadata else {}

        for idx, text in enumerate(raw_chunks):
            content_hash = hashlib.sha256(f"{tenant_id}:{text}".encode()).hexdigest()[
                :8
            ]
            chunk_id = f"{source_slug}-{idx}-{content_hash}"
            chunk_meta = {
                **base_meta,
                "chunk_index": idx,
                "total_chunks": len(raw_chunks),
                "source": source,
                "tenant_id": tenant_id,
            }

            chunk = DocumentChunk(
                chunk_id=chunk_id,
                content=text,
                tenant_id=tenant_id,
                source=source,
                metadata=chunk_meta,
            )
            chunks.append(chunk)

        return chunks

    async def ingest(
        self,
        request: DocumentIngestRequest,
        tenant_id: str,
    ) -> DocumentIngestResponse:
        """Process, parse, chunk, and index a document for the target tenant."""
        parser = get_parser(filename=request.source, is_raw_text=True)
        parsed = parser.parse_text(
            text=request.content,
            filename=request.source,
            metadata=request.metadata,
        )

        merged_metadata = {**request.metadata, **parsed.metadata}
        chunks = self.chunk_text(
            content=parsed.content,
            source=request.source,
            tenant_id=tenant_id,
            metadata=merged_metadata,
            chunk_size=request.chunk_size,
            chunk_overlap=request.chunk_overlap,
        )

        if chunks:
            await self.retriever.index_documents(chunks)

        chunk_ids = [c.chunk_id for c in chunks]

        return DocumentIngestResponse(
            status="success",
            indexed_chunks=len(chunks),
            chunk_ids=chunk_ids,
            source=request.source,
            tenant_id=tenant_id,
        )

    async def ingest_file_bytes(
        self,
        data: bytes,
        filename: str,
        tenant_id: str,
        mime_type: str | None = None,
        metadata: dict[str, Any] | None = None,
        chunk_size: int = 500,
        chunk_overlap: int = 50,
    ) -> DocumentIngestResponse:
        """Ingest raw file bytes (e.g. PDF, Markdown, TXT) with MIME validation and extraction."""
        parser = get_parser(filename=filename, mime_type=mime_type)
        parsed = parser.parse_bytes(data=data, filename=filename, metadata=metadata)

        chunks = self.chunk_text(
            content=parsed.content,
            source=filename,
            tenant_id=tenant_id,
            metadata=parsed.metadata,
            chunk_size=chunk_size,
            chunk_overlap=chunk_overlap,
        )

        if chunks:
            await self.retriever.index_documents(chunks)

        chunk_ids = [c.chunk_id for c in chunks]

        return DocumentIngestResponse(
            status="success",
            indexed_chunks=len(chunks),
            chunk_ids=chunk_ids,
            source=filename,
            tenant_id=tenant_id,
        )


default_ingestion_pipeline = DocumentIngestionPipeline()
