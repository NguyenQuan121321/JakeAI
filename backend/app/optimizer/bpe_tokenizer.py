"""Tier 7: Real BPE Tokenizer Engine, Token Budgeting & Reconciliation.

Provides:
1. Exact BPE token counting using `tiktoken` (cl100k_base / o200k_base) with
   calibrated fallback when tiktoken is unavailable.
2. Direct measurement of Tier 6 output:
   - raw_tokens, optimized_tokens, removed_tokens, reduction_ratio.
3. Strict enforcement of context budgets (Section 9):
   - Accepts prompt if Tier 6 optimization brings raw overflow within budget.
   - Fails safely if optimized prompt still exceeds context limit.
4. Clean separation of physical token removals (Tier 6) from provider-side
   KV cached tokens (Tier 5).
"""

from __future__ import annotations

import logging
from typing import Any

from app.optimizer.contracts import (
    OptimizedContext,
    TokenMetrics,
)
from app.optimizer.token_pruner import estimate_tokens as regex_estimate_tokens

logger = logging.getLogger(__name__)

# Try importing tiktoken
_TIKTOKEN_AVAILABLE = False
try:
    import tiktoken

    _TIKTOKEN_AVAILABLE = True
except ImportError:
    tiktoken = None  # type: ignore[assignment]


class ContextBudgetExceededError(ValueError):
    """Raised when context exceeds budget even after Tier 6 optimization."""

    pass


class BPETokenizer:
    """Production BPE Tokenizer engine for Tier 7."""

    def __init__(self, default_encoding: str = "cl100k_base") -> None:
        self.default_encoding_name = default_encoding
        self._tiktoken_encoding: Any | None = None
        if _TIKTOKEN_AVAILABLE and tiktoken is not None:
            try:
                self._tiktoken_encoding = tiktoken.get_encoding(default_encoding)
            except Exception as exc:
                logger.warning(
                    "Failed to initialize tiktoken encoding %s: %s",
                    default_encoding,
                    exc,
                )

    @property
    def is_native_bpe(self) -> bool:
        return self._tiktoken_encoding is not None

    def encode(self, text: str, model: str = "default") -> list[int]:
        """Encode text to token IDs using BPE."""
        if not text:
            return []
        if self._tiktoken_encoding is not None:
            try:
                # If specific model is requested, attempt model lookup
                if model and model != "default" and tiktoken is not None:
                    try:
                        enc = tiktoken.encoding_for_model(model)
                        return [int(x) for x in enc.encode(text, disallowed_special=())]
                    except Exception as exc:
                        logger.debug("Model-specific encoding not found: %s", exc)
                return [
                    int(x)
                    for x in self._tiktoken_encoding.encode(text, disallowed_special=())
                ]
            except Exception as exc:
                logger.warning(
                    "tiktoken encode error: %s; falling back to regex estimate.", exc
                )

        # Fallback: simulate tokens
        count = regex_estimate_tokens(text)
        return list(range(count))

    def count_tokens(self, text: str, model: str = "default") -> int:
        """Return exact or calibrated token count for given text."""
        if not text:
            return 0
        if self._tiktoken_encoding is not None:
            try:
                if model and model != "default" and tiktoken is not None:
                    try:
                        enc = tiktoken.encoding_for_model(model)
                        return len(enc.encode(text, disallowed_special=()))
                    except Exception as exc:
                        logger.debug("Model-specific encoding not found: %s", exc)
                return len(self._tiktoken_encoding.encode(text, disallowed_special=()))
            except Exception as exc:
                logger.debug("tiktoken count error: %s", exc)
        return regex_estimate_tokens(text)

    def measure_optimization(
        self,
        raw_text: str,
        optimized_context: OptimizedContext,
        model: str = "default",
        output_tokens: int | None = None,
    ) -> TokenMetrics:
        """Measure real output of Tier 6 context optimization according to Section 6 & 7."""
        raw_count = self.count_tokens(raw_text, model=model)
        optimized_count = self.count_tokens(optimized_context.content, model=model)

        tokens_removed = max(0, raw_count - optimized_count)
        reduction_ratio = round(tokens_removed / raw_count, 4) if raw_count > 0 else 0.0

        tokenizer_name = (
            f"tiktoken/{self.default_encoding_name}"
            if self.is_native_bpe
            else "calibrated-bpe-heuristic"
        )

        return TokenMetrics(
            tokenizer=tokenizer_name,
            tokenizer_version="0.14.0" if self.is_native_bpe else "1.0.0",
            input_tokens=optimized_count,
            output_tokens=output_tokens,
            removed_tokens=tokens_removed,
            estimated=not self.is_native_bpe,
            raw_tokens=raw_count,
            optimized_tokens=optimized_count,
            reduction_ratio=reduction_ratio,
        )

    def enforce_context_budget(
        self,
        raw_tokens: int,
        optimized_tokens: int,
        budget: int,
        raise_on_exceed: bool = True,
    ) -> bool:
        """Check context budget enforcement according to Section 9.

        Accepts request if Tier 6 optimization brings raw overflow within budget.
        Fails safely if optimized prompt still exceeds context limit.
        """
        if optimized_tokens <= budget:
            return True

        if raise_on_exceed:
            raise ContextBudgetExceededError(
                f"Context budget exceeded: optimized prompt requires {optimized_tokens} tokens, "
                f"which exceeds the model limit of {budget} tokens (raw context was {raw_tokens} tokens)."
            )
        return False


_bpe_tokenizer: BPETokenizer | None = None


def get_bpe_tokenizer() -> BPETokenizer:
    """Singleton accessor for BPETokenizer."""
    global _bpe_tokenizer
    if _bpe_tokenizer is None:
        _bpe_tokenizer = BPETokenizer()
    return _bpe_tokenizer
