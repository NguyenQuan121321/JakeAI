"""Semantic embedding providers for JakeAI RAG pipeline."""

from __future__ import annotations

import hashlib
import logging
import math
import os
import time
from abc import ABC, abstractmethod
from typing import Any

from app.core.config import get_settings
from app.rag.normalizer import normalize_text

logger = logging.getLogger(__name__)


class DimensionMismatchError(ValueError):
    """Raised when an embedding vector dimension does not match collection configuration."""

    pass


class EmbeddingProvider(ABC):
    """Abstract base contract for semantic embedding generation."""

    @property
    @abstractmethod
    def dimension(self) -> int:
        """Embedding vector dimension."""
        pass

    @property
    @abstractmethod
    def model_name(self) -> str:
        """Name of the underlying embedding model."""
        pass

    @property
    @abstractmethod
    def version(self) -> str:
        """Version tag for index tracking."""
        pass

    @abstractmethod
    def embed_text(self, text: str) -> list[float]:
        """Generate normalized embedding vector for a single text."""
        pass

    @abstractmethod
    def embed_batch(self, texts: list[str]) -> list[list[float]]:
        """Generate normalized embedding vectors for an ordered list of texts."""
        pass


class FastEmbedEmbeddingProvider(EmbeddingProvider):
    """Production semantic embedding provider using FastEmbed ONNX runtime."""

    def __init__(
        self,
        model_name: str | None = None,
        dimension: int | None = None,
        version: str | None = None,
    ) -> None:
        settings = get_settings()
        self._model_name = model_name or settings.EMBEDDING_MODEL
        self._dimension = dimension or settings.EMBEDDING_DIMENSION
        self._version = version or settings.EMBEDDING_VERSION
        self._model: Any = None

    @property
    def dimension(self) -> int:
        return self._dimension

    @property
    def model_name(self) -> str:
        return self._model_name

    @property
    def version(self) -> str:
        return self._version

    def _get_model(self) -> Any:
        if self._model is not None:
            return self._model

        from fastembed import TextEmbedding

        max_retries = 3
        backoff = 1.0
        last_err: Exception | None = None

        for attempt in range(max_retries):
            try:
                self._model = TextEmbedding(model_name=self._model_name)
                logger.info(
                    "Initialized FastEmbed model: %s (dim=%d)",
                    self._model_name,
                    self._dimension,
                )
                return self._model
            except Exception as exc:
                last_err = exc
                logger.warning(
                    "FastEmbed load attempt %d failed for model %s: %s. Retrying in %.1fs...",
                    attempt + 1,
                    self._model_name,
                    exc,
                    backoff,
                )
                time.sleep(backoff)
                backoff *= 2.0

        raise RuntimeError(
            f"Failed to load FastEmbed model '{self._model_name}' after {max_retries} attempts: {last_err}"
        ) from last_err

    def embed_text(self, text: str) -> list[float]:
        results = self.embed_batch([text])
        if not results:
            raise RuntimeError("FastEmbed returned empty embedding for single text")
        return results[0]

    def embed_batch(self, texts: list[str]) -> list[list[float]]:
        if not texts:
            return []

        model = self._get_model()
        cleaned = [normalize_text(t) if t else "" for t in texts]

        # FastEmbed returns an iterable of numpy arrays
        raw_embeddings = list(model.embed(cleaned, batch_size=64))

        results: list[list[float]] = []
        for i, emb in enumerate(raw_embeddings):
            vec = [float(x) for x in emb]
            if len(vec) != self._dimension:
                raise DimensionMismatchError(
                    f"Generated embedding dimension {len(vec)} does not match "
                    f"configured dimension {self._dimension} for text at index {i}"
                )
            results.append(vec)

        return results


class TestOnlyFakeEmbeddingProvider(EmbeddingProvider):
    """Deterministic pseudo-vector generator strictly guarded for test environments."""

    __test__ = False

    def __init__(
        self,
        dimension: int = 384,
        model_name: str = "test-fake-embedding",
        version: str = "test-v1.0",
    ) -> None:
        settings = get_settings()
        env = os.environ.get("ENVIRONMENT", settings.ENVIRONMENT).lower()
        if env == "production":
            raise RuntimeError(
                "CRITICAL SECURITY / GROUNDING INVARIANT: "
                "TestOnlyFakeEmbeddingProvider is strictly prohibited in production environments."
            )
        self._dimension = dimension
        self._model_name = model_name
        self._version = version

    @property
    def dimension(self) -> int:
        return self._dimension

    @property
    def model_name(self) -> str:
        return self._model_name

    @property
    def version(self) -> str:
        return self._version

    def _generate_vector(self, text: str) -> list[float]:
        norm = normalize_text(text)
        seed_bytes = hashlib.sha256(norm.encode("utf-8")).digest()

        vec: list[float] = []
        for i in range(self._dimension):
            byte_val = seed_bytes[i % len(seed_bytes)]
            val = (byte_val / 127.5) - 1.0 + (i * 0.001)
            vec.append(val)

        # L2 normalize
        magnitude = math.sqrt(sum(x * x for x in vec))
        if magnitude > 0:
            vec = [x / magnitude for x in vec]
        return vec

    def embed_text(self, text: str) -> list[float]:
        return self._generate_vector(text)

    def embed_batch(self, texts: list[str]) -> list[list[float]]:
        return [self._generate_vector(t) for t in texts]


_GLOBAL_EMBEDDING_PROVIDER: EmbeddingProvider | None = None


def get_embedding_provider(provider_type: str | None = None) -> EmbeddingProvider:
    """Factory retrieving the configured singleton EmbeddingProvider."""
    global _GLOBAL_EMBEDDING_PROVIDER
    if _GLOBAL_EMBEDDING_PROVIDER is not None and provider_type is None:
        return _GLOBAL_EMBEDDING_PROVIDER

    settings = get_settings()
    ptype = provider_type or settings.EMBEDDING_PROVIDER
    provider: EmbeddingProvider

    if ptype == "test_fake":
        provider = TestOnlyFakeEmbeddingProvider(
            dimension=settings.EMBEDDING_DIMENSION,
            model_name="test-fake-embedding",
            version=settings.EMBEDDING_VERSION,
        )
    elif ptype == "fastembed":
        provider = FastEmbedEmbeddingProvider(
            model_name=settings.EMBEDDING_MODEL,
            dimension=settings.EMBEDDING_DIMENSION,
            version=settings.EMBEDDING_VERSION,
        )
    else:
        # Default to FastEmbed
        provider = FastEmbedEmbeddingProvider()

    if provider_type is None:
        _GLOBAL_EMBEDDING_PROVIDER = provider

    return provider


def set_embedding_provider(provider: EmbeddingProvider | None) -> None:
    """Set or reset the global embedding provider instance (useful in tests)."""
    global _GLOBAL_EMBEDDING_PROVIDER
    _GLOBAL_EMBEDDING_PROVIDER = provider
