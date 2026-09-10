"""Qdrant dense vector store with multi-tenant filtering and in-memory fallback."""

from __future__ import annotations

import logging
import uuid
from typing import Any

from app.core.config import get_settings
from app.rag.embedding import (
    DimensionMismatchError,
    EmbeddingProvider,
    get_embedding_provider,
)
from app.rag.models import DocumentChunk

logger = logging.getLogger(__name__)


def derive_point_id(chunk: DocumentChunk) -> str:
    """Generate deterministic UUIDv5 point ID for Qdrant storage."""
    doc_id = chunk.metadata.get("document_id", chunk.source)
    version = chunk.metadata.get("version", "1.0")
    key = f"{chunk.tenant_id}:{doc_id}:{version}:{chunk.chunk_id}"
    return str(uuid.uuid5(uuid.NAMESPACE_DNS, key))


def _cosine_similarity(v1: list[float], v2: list[float]) -> float:
    """Compute cosine similarity between two normalized vectors."""
    if not v1 or not v2 or len(v1) != len(v2):
        return 0.0
    dot = sum(a * b for a, b in zip(v1, v2, strict=False))
    return max(0.0, min(1.0, dot))


class QdrantVectorStore:
    """Qdrant vector store client with strict tenant isolation and memory fallback."""

    def __init__(
        self,
        collection_name: str = "jakeai_documents",
        dimension: int | None = None,
        url: str | None = None,
        embedding_provider: EmbeddingProvider | None = None,
    ) -> None:
        self.collection_name = collection_name
        self.embedding_provider = embedding_provider or get_embedding_provider()
        if dimension is not None and dimension != self.embedding_provider.dimension:
            raise DimensionMismatchError(
                f"Specified dimension {dimension} does not match embedding provider dimension {self.embedding_provider.dimension}"
            )
        self.dimension = dimension or self.embedding_provider.dimension

        settings = get_settings()
        self.url = url or settings.QDRANT_URL

        # In-memory storage fallback: tenant_id -> point_id -> (DocumentChunk, embedding)
        self._memory_vectors: dict[
            str, dict[str, tuple[DocumentChunk, list[float]]]
        ] = {}
        self._client: Any = None
        self._is_qdrant_available = False

    async def _get_client(self) -> Any:
        """Lazily initialize Qdrant client connection and ensure collection exists."""
        if self._client is None:
            try:
                from qdrant_client import AsyncQdrantClient
                from qdrant_client.http import models

                client = AsyncQdrantClient(
                    url=self.url, timeout=1, check_compatibility=False
                )
                if await client.collection_exists(self.collection_name):
                    col_info = await client.get_collection(self.collection_name)
                    # Check dimension
                    existing_dim = getattr(
                        getattr(col_info.config.params, "vectors", None), "size", None
                    )
                    if existing_dim is not None and existing_dim != self.dimension:
                        raise DimensionMismatchError(
                            f"Qdrant collection '{self.collection_name}' has dimension {existing_dim}, "
                            f"which does not match embedding provider dimension {self.dimension}"
                        )
                else:
                    await client.create_collection(
                        collection_name=self.collection_name,
                        vectors_config=models.VectorParams(
                            size=self.dimension,
                            distance=models.Distance.COSINE,
                        ),
                    )
                self._client = client
                self._is_qdrant_available = True
            except DimensionMismatchError:
                raise
            except Exception as exc:
                logger.debug("Qdrant unavailable (%s), using in-memory store", exc)
                self._client = None
                self._is_qdrant_available = False
        return self._client

    async def upsert(self, chunks: list[DocumentChunk]) -> None:
        """Embed and upsert document chunks into vector store with tenant metadata."""
        if not chunks:
            return

        # Generate real semantic embeddings for chunks
        texts = [c.content for c in chunks]
        embeddings = self.embedding_provider.embed_batch(texts)

        # Attach embedding metadata
        for chunk in chunks:
            chunk.metadata["embedding_model"] = self.embedding_provider.model_name
            chunk.metadata["embedding_dimension"] = self.embedding_provider.dimension
            chunk.metadata["embedding_version"] = self.embedding_provider.version

        # Update in-memory store
        for chunk, emb in zip(chunks, embeddings, strict=True):
            tenant = chunk.tenant_id
            if tenant not in self._memory_vectors:
                self._memory_vectors[tenant] = {}

            point_id = derive_point_id(chunk)
            self._memory_vectors[tenant][point_id] = (chunk, emb)

        # If live Qdrant is connected, also upsert to Qdrant
        client = await self._get_client()
        if client and self._is_qdrant_available:
            try:
                from qdrant_client.http import models

                points = []
                for chunk, emb in zip(chunks, embeddings, strict=True):
                    point_id = derive_point_id(chunk)
                    points.append(
                        models.PointStruct(
                            id=point_id,
                            vector=emb,
                            payload={
                                "chunk_id": chunk.chunk_id,
                                "content": chunk.content,
                                "tenant_id": chunk.tenant_id,
                                "source": chunk.source,
                                "metadata": chunk.metadata,
                            },
                        )
                    )
                await client.upsert(
                    collection_name=self.collection_name,
                    points=points,
                )
            except Exception as exc:
                logger.warning(
                    "Failed to upsert to Qdrant (%s), in-memory copy retained", exc
                )
                self._is_qdrant_available = False

    async def search(
        self,
        query: str,
        tenant_id: str,
        top_k: int = 5,
    ) -> list[DocumentChunk]:
        """Query dense embeddings with strict tenant boundary filtering."""
        query_emb = self.embedding_provider.embed_text(query)
        client = await self._get_client()

        if client and self._is_qdrant_available:
            try:
                from qdrant_client.http import models

                tenant_filter = models.Filter(
                    must=[
                        models.FieldCondition(
                            key="tenant_id",
                            match=models.MatchValue(value=tenant_id),
                        )
                    ]
                )
                search_res = await client.search(
                    collection_name=self.collection_name,
                    query_vector=query_emb,
                    query_filter=tenant_filter,
                    limit=top_k,
                )
                chunks: list[DocumentChunk] = []
                for hit in search_res:
                    payload = hit.payload or {}
                    # Defense-in-depth tenant boundary check
                    if str(payload.get("tenant_id")) != tenant_id:
                        continue
                    chunks.append(
                        DocumentChunk(
                            chunk_id=str(payload.get("chunk_id", hit.id)),
                            content=str(payload.get("content", "")),
                            tenant_id=tenant_id,
                            source=str(payload.get("source", "Qdrant Vector")),
                            metadata=payload.get("metadata", {}),
                            score=round(float(hit.score), 4),
                        )
                    )
                # Sort by score descending, tie-break by chunk_id
                chunks.sort(key=lambda x: (-x.score, x.chunk_id))
                return chunks
            except Exception as exc:
                logger.warning(
                    "Qdrant search failed (%s), falling back to in-memory store", exc
                )
                self._is_qdrant_available = False

        # In-Memory Cosine Similarity Fallback with hard tenant filter
        tenant_entries = self._memory_vectors.get(tenant_id, {})
        scored_chunks: list[tuple[DocumentChunk, float]] = []

        for chunk, doc_emb in tenant_entries.values():
            if chunk.tenant_id != tenant_id:
                continue
            sim = _cosine_similarity(query_emb, doc_emb)
            chunk_copy = DocumentChunk(
                chunk_id=chunk.chunk_id,
                content=chunk.content,
                tenant_id=chunk.tenant_id,
                source=chunk.source,
                metadata=chunk.metadata.copy(),
                score=round(sim, 4),
            )
            scored_chunks.append((chunk_copy, sim))

        # Deterministic sorting: score descending, chunk_id ascending
        scored_chunks.sort(key=lambda x: (-x[1], x[0].chunk_id))
        return [c for c, _ in scored_chunks[:top_k]]
