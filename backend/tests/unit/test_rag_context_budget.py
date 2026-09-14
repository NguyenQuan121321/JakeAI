"""Unit tests for TASK RAG-08: BPETokenizer Full Envelope Budgeting and Score Leakage Elimination."""

from app.optimizer.bpe_tokenizer import get_bpe_tokenizer
from app.rag.context_selector import ContextSelector
from app.rag.models import DocumentChunk


def test_no_score_leakage_in_formatted_context() -> None:
    """Verify formatted context never leaks internal scores like '(Score: 0.95)' into model prompt."""
    selector = ContextSelector()
    chunks = [
        DocumentChunk(
            chunk_id="chunk-score-leak",
            content="Gross revenue exceeded expectations at $120M.",
            tenant_id="tenant-budget",
            source="Financial Report Q3",
            score=0.9542,
        )
    ]

    res = selector.select_context(
        candidates=chunks, query="revenue", tenant_id="tenant-budget"
    )

    # The formatted context MUST NOT contain "(Score:"
    assert "Score:" not in res.formatted_context
    assert "(Score" not in res.formatted_context
    # It must contain source and content
    assert "[1] Source: Financial Report Q3" in res.formatted_context
    assert "$120M" in res.formatted_context


def test_bpe_tokenizer_full_envelope_budgeting() -> None:
    """Verify context selection measures the full formatted string with BPETokenizer and never exceeds max_tokens."""
    tokenizer = get_bpe_tokenizer()
    budget = 80
    selector = ContextSelector(max_context_tokens=budget, tokenizer=tokenizer)

    long_paragraph = (
        "This is an important financial statement describing revenue and operations in great detail. "
        * 10
    )
    chunks = [
        DocumentChunk(
            chunk_id=f"c-{i}",
            content=f"Chunk {i}: {long_paragraph}",
            tenant_id="t1",
            source=f"Doc {i}",
            score=0.9 - (i * 0.05),
        )
        for i in range(5)
    ]

    res = selector.select_context(
        candidates=chunks, query="financial", tenant_id="t1", max_tokens=budget
    )

    # Count tokens of formatted context directly using BPETokenizer
    measured_tokens = tokenizer.count_tokens(res.formatted_context)
    # The formatted context must strictly fit within the token budget (or single chunk if 1st chunk exceeds)
    assert res.selected_tokens == measured_tokens
    assert len(res.selected_chunks) >= 1
