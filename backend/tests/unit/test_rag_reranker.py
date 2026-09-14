"""Unit tests for TASK RAG-07: Cross-Encoder Reranking, Telemetry, and Heuristic Fallback."""

from app.rag.models import DocumentChunk
from app.rag.reranker import CrossEncoderReranker


def test_reranker_telemetry_and_custom_fn() -> None:
    """Verify custom cross-encoder function records telemetry 'custom_fn' and scores accurately."""

    def mock_ce_fn(query: str, doc_texts: list[str]) -> list[float]:
        # Give higher score to docs containing 'profit'
        return [0.95 if "profit" in d.lower() else 0.20 for d in doc_texts]

    reranker = CrossEncoderReranker(cross_encoder_fn=mock_ce_fn)

    chunks = [
        DocumentChunk(
            chunk_id="c1",
            content="Weather was sunny today.",
            tenant_id="t1",
            source="W",
        ),
        DocumentChunk(
            chunk_id="c2",
            content="Net profit surged by 25%.",
            tenant_id="t1",
            source="F",
        ),
    ]

    results = reranker.rerank(
        query="profit growth", dense_results=chunks, sparse_results=[], top_k=2
    )

    assert reranker.last_reranker_type == "custom_fn"
    assert len(results) == 2
    assert results[0].chunk_id == "c2"
    assert results[0].score == 0.95


def test_reranker_calibrated_heuristic_fallback() -> None:
    """Verify calibrated heuristic fallback operates properly without 10x multiplier."""
    # Instantiating with enabled=False triggers calibrated heuristic fallback
    reranker = CrossEncoderReranker(enabled=False)

    chunks = [
        DocumentChunk(
            chunk_id="c1",
            content="Cloud gross margin reached 65% with $50M revenue.",
            tenant_id="t1",
            source="C",
        ),
        DocumentChunk(
            chunk_id="c2",
            content="Cafeteria serves coffee at 8 AM.",
            tenant_id="t1",
            source="Caf",
        ),
    ]

    results = reranker.rerank(
        query="What was Cloud gross margin and revenue?",
        dense_results=chunks,
        sparse_results=[],
        top_k=2,
    )

    assert reranker.last_reranker_type == "fallback"
    assert len(results) == 2
    assert results[0].chunk_id == "c1"
    # Scores must be within [0.0, 1.0]
    assert 0.0 <= results[0].score <= 1.0
    assert results[0].score > results[1].score


def test_reranker_empty_results_telemetry() -> None:
    """Verify empty input candidates sets last_reranker_type to 'empty'."""
    reranker = CrossEncoderReranker()
    res = reranker.rerank(
        query="anything", dense_results=[], sparse_results=[], top_k=5
    )
    assert res == []
    assert reranker.last_reranker_type == "empty"
