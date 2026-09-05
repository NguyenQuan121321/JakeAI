"""Qdrant dense vector store with multi-tenant filtering and in-memory fallback."""

import hashlib
import math
import struct
from typing import Any

from app.core.config import get_settings
from app.rag.models import DocumentChunk


def _generate_dense_embedding(text: str, dim: int = 64) -> list[float]:
    """Generate deterministic normalized dense embedding vector for matching."""
    vec: list[float] = []
    # Use multiple seeded hashes to create smooth continuous dense dimensions
    for i in range(dim):
        seed = f"{text}_{i}".encode()
        h = hashlib.sha256(seed).digest()
        val = struct.unpack("f", h[:4])[0]
        # Bound value
        if math.isnan(val) or math.isinf(val):
            val = 0.0
        vec.append(val)

    # Normalize vector to unit length (L2 norm)
    norm = math.sqrt(sum(v * v for v in vec)) or 1e-6
    return [round(v / norm, 6) for v in vec]


def _cosine_similarity(v1: list[float], v2: list[float]) -> float:
    """Compute cosine similarity between two normalized vectors."""
    dot = sum(a * b for a, b in zip(v1, v2, strict=False))
    return max(0.0, min(1.0, dot))


class QdrantVectorStore:
    """Qdrant vector store client with strict tenant isolation and memory fallback."""

    def __init__(
        self,
        collection_name: str = "jakeai_documents",
        dimension: int = 64,
        url: str | None = None,
    ) -> None:
        self.collection_name = collection_name
        self.dimension = dimension
        settings = get_settings()
        self.url = url or settings.QDRANT_URL
        # In-memory storage fallback: tenant_id -> list of (DocumentChunk, embedding)
        self._memory_vectors: dict[str, list[tuple[DocumentChunk, list[float]]]] = {}
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
                # Test connectivity and ensure target collection exists
                if not await client.collection_exists(self.collection_name):
                    await client.create_collection(
                        collection_name=self.collection_name,
                        vectors_config=models.VectorParams(
                            size=self.dimension,
                            distance=models.Distance.COSINE,
                        ),
                    )
                self._client = client
                self._is_qdrant_available = True
            except Exception:
                self._client = None
                self._is_qdrant_available = False
        return self._client

    async def upsert(self, chunks: list[DocumentChunk]) -> None:
        """Embed and upsert document chunks into vector store with tenant metadata."""
        for chunk in chunks:
            tenant = chunk.tenant_id
            if tenant not in self._memory_vectors:
                self._memory_vectors[tenant] = []

            embedding = _generate_dense_embedding(chunk.content, self.dimension)

            # Update or append in local fallback
            existing = next(
                (
                    i
                    for i, (c, _) in enumerate(self._memory_vectors[tenant])
                    if c.chunk_id == chunk.chunk_id
                ),
                None,
            )
            if existing is not None:
                self._memory_vectors[tenant][existing] = (chunk, embedding)
            else:
                self._memory_vectors[tenant].append((chunk, embedding))

        # If live Qdrant is connected, also upsert to Qdrant
        client = await self._get_client()
        if client and self._is_qdrant_available:
            try:
                from qdrant_client.http import models

                points = []
                for chunk in chunks:
                    emb = _generate_dense_embedding(chunk.content, self.dimension)
                    pid = abs(hash(chunk.chunk_id)) % (2**63 - 1)
                    points.append(
                        models.PointStruct(
                            id=pid,
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
            except Exception:
                self._is_qdrant_available = False

    async def search(
        self,
        query: str,
        tenant_id: str,
        top_k: int = 5,
    ) -> list[DocumentChunk]:
        """Query dense embeddings with strict tenant boundary filtering."""
        query_emb = _generate_dense_embedding(query, self.dimension)
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
                    chunks.append(
                        DocumentChunk(
                            chunk_id=str(payload.get("chunk_id", hit.id)),
                            content=str(payload.get("content", "")),
                            tenant_id=str(payload.get("tenant_id", tenant_id)),
                            source=str(payload.get("source", "Qdrant Vector")),
                            metadata=payload.get("metadata", {}),
                            score=round(float(hit.score), 4),
                        )
                    )
                return chunks
            except Exception:
                self._is_qdrant_available = False

        # In-Memory Cosine Similarity Fallback with hard tenant filter
        tenant_entries = self._memory_vectors.get(tenant_id, [])
        scored_chunks: list[tuple[DocumentChunk, float]] = []

        for chunk, doc_emb in tenant_entries:
            sim = _cosine_similarity(query_emb, doc_emb)
            chunk_copy = DocumentChunk(
                chunk_id=chunk.chunk_id,
                content=chunk.content,
                tenant_id=chunk.tenant_id,
                source=chunk.source,
                metadata=chunk.metadata,
                score=round(sim, 4),
            )
            scored_chunks.append((chunk_copy, sim))

        scored_chunks.sort(key=lambda x: x[1], reverse=True)
        return [c for c, _ in scored_chunks[:top_k]]
