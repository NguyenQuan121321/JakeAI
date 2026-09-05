"""RAG (Retrieval-Augmented Generation) package initialization."""

from app.rag.bm25 import BM25Retriever
from app.rag.citations import CitationGenerator
from app.rag.models import Citation, DocumentChunk, RetrievalResult
from app.rag.reranker import CrossEncoderReranker
from app.rag.retriever import HybridRetriever, default_hybrid_retriever
from app.rag.vector_store import QdrantVectorStore

__all__ = [
    "BM25Retriever",
    "Citation",
    "CitationGenerator",
    "CrossEncoderReranker",
    "DocumentChunk",
    "HybridRetriever",
    "QdrantVectorStore",
    "RetrievalResult",
    "default_hybrid_retriever",
]
