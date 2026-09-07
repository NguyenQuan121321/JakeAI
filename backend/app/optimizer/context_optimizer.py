"""Tier 6: Task-Aware Context Optimizer & Code Skeletonizer.

Enforces:
1. Critical Rule 4: Tier 6 MUST NOT modify Tier 5's Zone 1 Static Prefix.
   Zone 1 is immutable. Only Zone 2 (dynamic suffix / task context) is optimized.
2. Task-Aware Optimization Policy:
   - CONSERVATIVE: For bug fixes, code changes, security logic. Preserves full implementations.
   - BALANCED: For search and general coding questions. Skeletonizes helper utilities.
   - AGGRESSIVE: For architectural overviews, system maps. Skeletonizes all code bodies.
3. Fail-Closed Fallback (Rule 13):
   If any syntax error or transformation fails, returns the original uncorrupted context.
"""

from __future__ import annotations

import hashlib
import logging
import re
from typing import Any

from app.optimizer.ast_skeletonizer import (
    CodeSkeletonizer,
    get_code_skeletonizer,
)
from app.optimizer.contracts import (
    OptimizationLevel,
    OptimizedContext,
)
from app.optimizer.token_pruner import (
    HeuristicTokenPruner,
    estimate_tokens,
    get_token_pruner,
)

logger = logging.getLogger(__name__)

# Keywords indicating task criticality
CONSERVATIVE_KEYWORDS = [
    r"\bfix\b",
    r"\bbug\b",
    r"\berror\b",
    r"\bexception\b",
    r"\bauth\w*\b",
    r"\bauthoriz\w*\b",
    r"\bsecurity\b",
    r"\btoken\b",
    r"\bpassword\b",
    r"\bcredential\b",
    r"\bpatch\b",
    r"\bimplement\w*\b",
    r"\brefactor\w*\b",
    r"\bupdate\b",
    r"\bmodify\b",
    r"\bchange\b",
    r"\bedit\b",
    r"\btest\w*\b",
]

AGGRESSIVE_KEYWORDS = [
    r"\bexplain\b",
    r"\barchitecture\b",
    r"\boverview\b",
    r"\bstructure\b",
    r"\bhigh[- ]level\b",
    r"\btopology\b",
    r"\bhow does .* work\b",
    r"\bwhere is\b",
]


class ContextOptimizer:
    """Tier 6 Context Optimizer coordinating AST skeletonization and token pruning."""

    def __init__(
        self,
        skeletonizer: CodeSkeletonizer | None = None,
        pruner: HeuristicTokenPruner | None = None,
    ) -> None:
        self.skeletonizer = skeletonizer or get_code_skeletonizer()
        self.pruner = pruner or get_token_pruner()

    @staticmethod
    def infer_optimization_level(
        user_query: str,
        metadata: dict[str, Any] | None = None,
    ) -> OptimizationLevel:
        """Deterministically infer optimization level from query intent and metadata."""
        if metadata and "optimization_level" in metadata:
            level_val = str(metadata["optimization_level"]).lower()
            for lvl in OptimizationLevel:
                if lvl.value == level_val:
                    return lvl

        query_lower = user_query.lower()

        # 1. Explicit code modification, bug fixing, or refactoring commands
        explicit_edit = any(
            re.search(pat, query_lower)
            for pat in [
                r"\bfix\b",
                r"\bbug\b",
                r"\berror\b",
                r"\bpatch\b",
                r"\bupdate\b",
                r"\bmodify\b",
                r"\bchange\b",
                r"\bedit\b",
                r"\brefactor\b",
            ]
        )
        if explicit_edit:
            return OptimizationLevel.CONSERVATIVE

        # 2. Architecture and overview queries can be aggressively skeletonized (Section 11 Task D)
        for pat in AGGRESSIVE_KEYWORDS:
            if re.search(pat, query_lower):
                return OptimizationLevel.AGGRESSIVE

        # 3. Remaining conservative keywords (security, auth, tokens, credentials)
        for pat in CONSERVATIVE_KEYWORDS:
            if re.search(pat, query_lower):
                return OptimizationLevel.CONSERVATIVE

        return OptimizationLevel.BALANCED

    def optimize_dynamic_context(
        self,
        dynamic_context: str,
        user_query: str = "",
        optimization_level: OptimizationLevel | None = None,
        preserve_symbols: set[str] | None = None,
        source_files: list[str] | None = None,
    ) -> OptimizedContext:
        """Optimize dynamic context (Zone 2) while preserving semantic correctness.

        CRITICAL: Never call this on Zone 1 static prefix!
        """
        _ = source_files
        raw_text = dynamic_context or ""
        source_hash = hashlib.sha256(raw_text.encode("utf-8")).hexdigest()
        raw_tokens = estimate_tokens(raw_text)

        level = (
            optimization_level
            if optimization_level is not None
            else self.infer_optimization_level(user_query)
        )

        transformations: list[str] = []
        removed_metadata: dict[str, Any] = {}

        if not raw_text.strip():
            return OptimizedContext(
                content=raw_text,
                source_content_hash=source_hash,
                transformations=transformations,
                removed_content_metadata=removed_metadata,
                optimization_level=level,
                raw_tokens=0,
                optimized_tokens=0,
                tokens_removed=0,
                reduction_ratio=0.0,
                fallback_used=False,
            )

        current_text = raw_text

        # 1. Step A: AST Code Skeletonization (for code blocks or raw python)
        try:
            if "```" in current_text:
                # Markdown format containing code blocks
                skeletonized = self.skeletonizer.skeletonize_markdown_blocks(
                    current_text,
                    level=level,
                    preserve_symbols=preserve_symbols,
                )
                if skeletonized != current_text:
                    transformations.append(f"ast_skeletonize_markdown_{level.value}")
                    current_text = skeletonized
            elif (
                "def " in current_text or "class " in current_text
            ) and level != OptimizationLevel.CONSERVATIVE:
                # Raw Python source
                ast_res = self.skeletonizer.skeletonize_python(
                    current_text,
                    level=level,
                    preserve_symbols=preserve_symbols,
                )
                if ast_res.success and ast_res.skeleton_code != current_text:
                    transformations.append(f"ast_skeletonize_raw_{level.value}")
                    removed_metadata["functions_skeletonized"] = (
                        ast_res.functions_skeletonized
                    )
                    removed_metadata["classes_skeletonized"] = (
                        ast_res.classes_skeletonized
                    )
                    current_text = ast_res.skeleton_code
                elif not ast_res.success:
                    logger.warning(
                        "AST Skeletonizer failed (%s); triggering fail-closed fallback.",
                        ast_res.error,
                    )
                    return OptimizedContext(
                        content=raw_text,
                        source_content_hash=source_hash,
                        transformations=["fail_closed_fallback_raw"],
                        removed_content_metadata={"fallback_reason": ast_res.error},
                        optimization_level=level,
                        raw_tokens=raw_tokens,
                        optimized_tokens=raw_tokens,
                        tokens_removed=0,
                        reduction_ratio=0.0,
                        fallback_used=True,
                        fallback_reason=ast_res.error,
                    )
        except Exception as exc:
            logger.error(
                "Unexpected error during AST skeletonization: %s; falling back safely.",
                exc,
            )
            return OptimizedContext(
                content=raw_text,
                source_content_hash=source_hash,
                transformations=["fail_closed_fallback_exception"],
                removed_content_metadata={"fallback_reason": str(exc)},
                optimization_level=level,
                raw_tokens=raw_tokens,
                optimized_tokens=raw_tokens,
                tokens_removed=0,
                reduction_ratio=0.0,
                fallback_used=True,
                fallback_reason=str(exc),
            )

        # 2. Step B: Heuristic Token Pruning (Boilerplate & Sentence Deduplication)
        try:
            pruned_res = self.pruner.prune_context(current_text)
            if pruned_res.tokens_saved > 0:
                transformations.append("heuristic_pruning_boilerplate_dedup")
                removed_metadata["pruned_tokens_saved"] = pruned_res.tokens_saved
                current_text = pruned_res.pruned_text
        except Exception as exc:
            logger.warning(
                "Heuristic pruning error: %s; proceeding with current text.", exc
            )

        optimized_tokens = estimate_tokens(current_text)
        tokens_removed = max(0, raw_tokens - optimized_tokens)
        reduction_ratio = (
            round((tokens_removed / raw_tokens), 4) if raw_tokens > 0 else 0.0
        )

        return OptimizedContext(
            content=current_text,
            source_content_hash=source_hash,
            transformations=transformations,
            removed_content_metadata=removed_metadata,
            optimization_level=level,
            raw_tokens=raw_tokens,
            optimized_tokens=optimized_tokens,
            tokens_removed=tokens_removed,
            reduction_ratio=reduction_ratio,
            fallback_used=False,
        )


_context_optimizer: ContextOptimizer | None = None


def get_context_optimizer() -> ContextOptimizer:
    """Singleton accessor for ContextOptimizer."""
    global _context_optimizer
    if _context_optimizer is None:
        _context_optimizer = ContextOptimizer()
    return _context_optimizer
