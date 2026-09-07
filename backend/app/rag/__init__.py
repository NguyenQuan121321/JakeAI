"""RAG (Retrieval-Augmented Generation) package initialization."""

from app.rag.bm25 import BM25Retriever
from app.rag.citations import CitationGenerator
from app.rag.context_selector import ContextSelector, get_context_selector
from app.rag.ingestion import (
    DocumentIngestionPipeline,
    DocumentIngestRequest,
    DocumentIngestResponse,
    default_ingestion_pipeline,
)
from app.rag.models import (
    Citation,
    ContextSelectionResult,
    DocumentChunk,
    RAGGenerationResult,
    RetrievalResult,
)
from app.rag.pipeline import (
    RAGPipeline,
    default_rag_pipeline,
    get_rag_pipeline,
)
from app.rag.reranker import CrossEncoderReranker
from app.rag.retriever import (
    HybridRetriever,
    default_hybrid_retriever,
    get_hybrid_retriever,
)
from app.rag.vector_store import QdrantVectorStore

__all__ = [
    "BM25Retriever",
    "Citation",
    "CitationGenerator",
    "ContextSelectionResult",
    "ContextSelector",
    "CrossEncoderReranker",
    "DocumentChunk",
    "DocumentIngestRequest",
    "DocumentIngestResponse",
    "DocumentIngestionPipeline",
    "HybridRetriever",
    "QdrantVectorStore",
    "RAGGenerationResult",
    "RAGPipeline",
    "RetrievalResult",
    "default_hybrid_retriever",
    "default_ingestion_pipeline",
    "default_rag_pipeline",
    "get_context_selector",
    "get_hybrid_retriever",
    "get_rag_pipeline",
]
