"""RAG (Retrieval-Augmented Generation) package initialization."""

from app.rag.bm25 import BM25Retriever
from app.rag.citations import CitationGenerator
from app.rag.context_envelope import (
    ContextEnvelope,
    ContextEnvelopeBuilder,
    get_context_envelope_builder,
)
from app.rag.context_selector import ContextSelector, get_context_selector
from app.rag.embedding import (
    DimensionMismatchError,
    EmbeddingProvider,
    FastEmbedEmbeddingProvider,
    TestOnlyFakeEmbeddingProvider,
    get_embedding_provider,
    set_embedding_provider,
)
from app.rag.grounding import (
    GroundingVerificationResult,
    GroundingVerifier,
    get_grounding_verifier,
)
from app.rag.ingestion import (
    DocumentIngestionPipeline,
    DocumentIngestRequest,
    DocumentIngestResponse,
    default_ingestion_pipeline,
)
from app.rag.models import (
    AbstentionReason,
    Citation,
    ClaimEntailment,
    ContextSelectionResult,
    DocumentChunk,
    GroundingClaim,
    RAGGenerationResult,
    RetrievalResult,
)
from app.rag.normalizer import normalize_text
from app.rag.parsers import (
    BaseDocumentParser,
    MarkdownParser,
    ParsedDocument,
    PDFParser,
    PlainTextParser,
    UnsupportedDocumentTypeError,
    get_parser,
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
from app.rag.vector_store import QdrantVectorStore, derive_point_id

__all__ = [
    "AbstentionReason",
    "BM25Retriever",
    "BaseDocumentParser",
    "Citation",
    "CitationGenerator",
    "ClaimEntailment",
    "ContextEnvelope",
    "ContextEnvelopeBuilder",
    "ContextSelectionResult",
    "ContextSelector",
    "CrossEncoderReranker",
    "DimensionMismatchError",
    "DocumentChunk",
    "DocumentIngestRequest",
    "DocumentIngestResponse",
    "DocumentIngestionPipeline",
    "EmbeddingProvider",
    "FastEmbedEmbeddingProvider",
    "GroundingClaim",
    "GroundingVerificationResult",
    "GroundingVerifier",
    "HybridRetriever",
    "MarkdownParser",
    "PDFParser",
    "ParsedDocument",
    "PlainTextParser",
    "QdrantVectorStore",
    "RAGGenerationResult",
    "RAGPipeline",
    "RetrievalResult",
    "TestOnlyFakeEmbeddingProvider",
    "UnsupportedDocumentTypeError",
    "default_hybrid_retriever",
    "default_ingestion_pipeline",
    "default_rag_pipeline",
    "derive_point_id",
    "get_context_envelope_builder",
    "get_context_selector",
    "get_embedding_provider",
    "get_grounding_verifier",
    "get_hybrid_retriever",
    "get_parser",
    "get_rag_pipeline",
    "normalize_text",
    "set_embedding_provider",
]
