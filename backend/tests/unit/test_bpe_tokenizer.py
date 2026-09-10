"""Unit tests for Tier 7 BPE Tokenizer Engine and Token Budgeting."""

from unittest.mock import MagicMock

import pytest

from app.optimizer.bpe_tokenizer import (
    BPETokenizer,
    ContextBudgetExceededError,
    get_bpe_tokenizer,
)
from app.optimizer.contracts import OptimizedContext


def test_bpe_tokenizer_initialization() -> None:
    """Verify standard and invalid BPE tokenizer initialization."""
    tok = BPETokenizer()
    assert tok.is_native_bpe is True
    assert tok.default_encoding_name == "cl100k_base"

    # Initialization with an unknown encoding name falls back safely
    tok_invalid = BPETokenizer(default_encoding="invalid_encoding_9999")
    assert tok_invalid.is_native_bpe is False
    assert tok_invalid._tiktoken_encoding is None


def test_bpe_tokenizer_encode() -> None:
    """Verify token encoding for empty string, default model, and specific models."""
    tok = BPETokenizer()

    # Empty string yields empty list
    assert tok.encode("") == []

    # Standard text encoding
    tokens = tok.encode("def calculate_total(items: list[float]) -> float:")
    assert len(tokens) > 0
    assert all(isinstance(t, int) for t in tokens)

    # Specific model encoding (e.g. gpt-4o uses o200k_base)
    tokens_model = tok.encode(
        "def calculate_total(items: list[float]) -> float:", model="gpt-4o"
    )
    assert len(tokens_model) > 0

    # Non-existent model falls back to default encoding
    tokens_fallback_model = tok.encode(
        "def calculate_total(items: list[float]) -> float:",
        model="non_existent_model_xyz",
    )
    assert len(tokens_fallback_model) > 0


def test_bpe_tokenizer_encode_fallback_on_exception() -> None:
    """Verify encode gracefully falls back to regex token estimate when an exception occurs."""
    tok = BPETokenizer()
    mock_enc = MagicMock()
    mock_enc.encode.side_effect = RuntimeError("Simulated tiktoken encode failure")
    tok._tiktoken_encoding = mock_enc

    tokens = tok.encode("Sample query text for fallback")
    assert len(tokens) > 0
    assert tokens == list(range(len(tokens)))

    # Non-native tokenizer directly uses fallback
    tok_non_native = BPETokenizer(default_encoding="invalid_encoding")
    tokens_nn = tok_non_native.encode("Another sample query")
    assert len(tokens_nn) > 0
    assert tokens_nn == list(range(len(tokens_nn)))


def test_bpe_tokenizer_count_tokens() -> None:
    """Verify exact and fallback token counting."""
    tok = BPETokenizer()

    assert tok.count_tokens("") == 0

    count = tok.count_tokens("JakeAI Universal AI Engineering Worker")
    assert count > 0

    count_model = tok.count_tokens(
        "JakeAI Universal AI Engineering Worker", model="gpt-4o"
    )
    assert count_model > 0

    count_fallback_model = tok.count_tokens(
        "JakeAI Universal AI Engineering Worker", model="non_existent_model_xyz"
    )
    assert count_fallback_model > 0

    # Exception fallback during count
    mock_enc = MagicMock()
    mock_enc.encode.side_effect = RuntimeError("Simulated count error")
    tok._tiktoken_encoding = mock_enc
    count_err = tok.count_tokens("Fallback counting test")
    assert count_err > 0


def test_bpe_tokenizer_measure_optimization() -> None:
    """Verify Tier 6 context optimization measurement and token metrics generation."""
    tok = BPETokenizer()
    raw_text = (
        "This is a long financial analysis document with multiple paragraphs " * 10
    )
    ctx = OptimizedContext(
        content="This is a pruned financial analysis document.",
        source_content_hash="abc123hash",
        original_length=len(raw_text),
        optimized_length=45,
        strategy_applied="ast_skeletonize",
        processing_time_ms=1.5,
    )

    metrics = tok.measure_optimization(raw_text, ctx, output_tokens=15)
    assert metrics.raw_tokens > metrics.optimized_tokens
    assert metrics.removed_tokens > 0
    assert metrics.reduction_ratio > 0.0
    assert metrics.output_tokens == 15
    assert "tiktoken/cl100k_base" in metrics.tokenizer
    assert metrics.estimated is False

    # Empty raw text handles 0 division safely
    metrics_empty = tok.measure_optimization("", ctx)
    assert metrics_empty.raw_tokens == 0
    assert metrics_empty.reduction_ratio == 0.0

    # Non-native tokenizer metrics
    tok_non_native = BPETokenizer(default_encoding="invalid_encoding")
    metrics_nn = tok_non_native.measure_optimization(raw_text, ctx)
    assert metrics_nn.estimated is True
    assert metrics_nn.tokenizer == "calibrated-bpe-heuristic"
    assert metrics_nn.tokenizer_version == "1.0.0"


def test_bpe_tokenizer_enforce_context_budget() -> None:
    """Verify Section 9 context budget enforcement with and without exception raising."""
    tok = BPETokenizer()

    # Case 1: Optimized tokens fit within budget
    assert (
        tok.enforce_context_budget(raw_tokens=2000, optimized_tokens=800, budget=1000)
        is True
    )

    # Case 2: Optimized tokens exceed budget and raise_on_exceed is True
    with pytest.raises(ContextBudgetExceededError) as exc_info:
        tok.enforce_context_budget(
            raw_tokens=2000, optimized_tokens=1200, budget=1000, raise_on_exceed=True
        )
    assert "Context budget exceeded" in str(exc_info.value)
    assert "1200 tokens" in str(exc_info.value)

    # Case 3: Optimized tokens exceed budget and raise_on_exceed is False
    assert (
        tok.enforce_context_budget(
            raw_tokens=2000, optimized_tokens=1200, budget=1000, raise_on_exceed=False
        )
        is False
    )


def test_bpe_tokenizer_singleton() -> None:
    """Verify get_bpe_tokenizer returns a singleton instance."""
    inst1 = get_bpe_tokenizer()
    inst2 = get_bpe_tokenizer()
    assert inst1 is inst2
    assert isinstance(inst1, BPETokenizer)
