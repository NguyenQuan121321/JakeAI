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
import unicodedata
from enum import StrEnum
from typing import Any

from app.optimizer.ast_skeletonizer import (
    CodeSkeletonizer,
    get_code_skeletonizer,
)
from app.optimizer.code_context_compressor import (
    CodeContextCompressor,
    get_code_context_compressor,
)
from app.optimizer.contracts import (
    OptimizationLevel,
    OptimizedContext,
)
from app.optimizer.retrieval_compressor import (
    RetrievalCompressor,
    get_retrieval_compressor,
)
from app.optimizer.token_pruner import (
    HeuristicTokenPruner,
    compact_json,
    estimate_tokens,
    get_token_pruner,
    is_structured_json,
)

logger = logging.getLogger(__name__)


class WorkloadType(StrEnum):
    """Workload classification for tailored token optimization (Phase 03 Section 3)."""

    SIMPLE_CHAT = "simple_chat"
    LONG_CONVERSATION = "long_conversation"
    RAG = "rag"
    FINANCIAL_REASONING = "financial_reasoning"
    CODING_CONTEXT = "coding_context"
    STRUCTURED_JSON = "structured_json"
    MULTILINGUAL = "multilingual"
    GENERAL = "general"


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
        code_compressor: CodeContextCompressor | None = None,
        retrieval_compressor: RetrievalCompressor | None = None,
    ) -> None:
        self.skeletonizer = skeletonizer or get_code_skeletonizer()
        self.pruner = pruner or get_token_pruner()
        self.code_compressor = code_compressor or get_code_context_compressor()
        self.retrieval_compressor = retrieval_compressor or get_retrieval_compressor()

    @staticmethod
    def infer_workload_type(
        dynamic_context: str,
        user_query: str = "",
        metadata: dict[str, Any] | None = None,
    ) -> WorkloadType:
        """Infer workload type from explicit metadata or contextual signatures."""
        if metadata and "workload_type" in metadata:
            val = str(metadata["workload_type"]).lower()
            for wt in WorkloadType:
                if wt.value == val:
                    return wt

        ctx_stripped = dynamic_context.strip()
        query_lower = user_query.lower()

        # 1. Structured JSON
        if (
            (ctx_stripped.startswith("{") and ctx_stripped.endswith("}"))
            or (ctx_stripped.startswith("[") and ctx_stripped.endswith("]"))
            or "json" in query_lower
        ) and is_structured_json(ctx_stripped):
            return WorkloadType.STRUCTURED_JSON

        # 2. Multilingual (Vietnamese Unicode diacritics / markers)
        if any(
            c in dynamic_context
            for c in "áàảãạăắằẳẵặâấầẩẫậéèẻẽẹêếềểễệíìỉĩịóòỏõọôốồổỗộơớờởỡợúùủũụưứừửữựýỳỷỹỵđ"
        ):
            return WorkloadType.MULTILINGUAL

        # 3. Coding Context
        if (
            "diff --git" in dynamic_context
            or "def " in dynamic_context
            or "class " in dynamic_context
            or "import " in dynamic_context
            or "TokenVerifier" in dynamic_context
            or any(
                kw in query_lower
                for kw in [
                    "method",
                    "function",
                    "class",
                    "syntax",
                    "refactor",
                    "bug",
                    "patch",
                    "constant-time",
                ]
            )
        ):
            return WorkloadType.CODING_CONTEXT

        # 4. RAG Excerpts
        if (
            "=== DOCUMENT EXCERPT" in dynamic_context
            or "[SEC-" in dynamic_context
            or "Form 10-Q" in dynamic_context
            or "cite source" in query_lower
        ):
            return WorkloadType.RAG

        # 5. Financial Reasoning
        if (
            any(
                w in dynamic_context
                for w in [
                    "EBITDA",
                    "Gross Profit",
                    "Operating Margin",
                    "Operating Profit",
                    "Net Income",
                    "Diluted EPS",
                ]
            )
            or "ebitda" in query_lower
        ):
            return WorkloadType.FINANCIAL_REASONING

        # 6. Long Conversation
        if (
            "Turn 1" in dynamic_context and "Turn 2" in dynamic_context
        ) or "TRANSCRIPT" in dynamic_context:
            return WorkloadType.LONG_CONVERSATION

        # 7. Simple Chat
        if len(dynamic_context.split()) < 20 and len(user_query.split()) < 30:
            return WorkloadType.SIMPLE_CHAT

        return WorkloadType.GENERAL

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
        workload_type: str | WorkloadType | None = None,
    ) -> OptimizedContext:
        """Optimize dynamic context (Zone 2) with workload-aware strategies.

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

        resolved_workload: WorkloadType
        if isinstance(workload_type, WorkloadType):
            resolved_workload = workload_type
        elif isinstance(workload_type, str):
            matched = False
            for wt in WorkloadType:
                if wt.value == workload_type:
                    resolved_workload = wt
                    matched = True
                    break
            if not matched:
                resolved_workload = self.infer_workload_type(raw_text, user_query)
        else:
            resolved_workload = self.infer_workload_type(raw_text, user_query)

        transformations: list[str] = []
        removed_metadata: dict[str, Any] = {"workload_type": resolved_workload.value}

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

        try:
            # -------------------------------------------------------------
            # Workload-Aware Tailored Strategy Dispatch
            # -------------------------------------------------------------
            if resolved_workload == WorkloadType.SIMPLE_CHAT:
                # Normal Chat: Compaction only. Strictly NO AST skeletonization or destructive code pruning
                compacted = re.sub(r"[ \t]+", " ", current_text).strip()
                compacted = re.sub(r"\n{3,}", "\n\n", compacted)
                if compacted != current_text:
                    transformations.append("simple_chat_whitespace_normalization")
                    current_text = compacted

            elif resolved_workload == WorkloadType.STRUCTURED_JSON:
                # Structured JSON: compact layout without breaking schema or removing keys
                if is_structured_json(current_text):
                    compacted = compact_json(current_text)
                    if compacted != current_text:
                        transformations.append("structured_json_minification")
                        current_text = compacted

            elif resolved_workload == WorkloadType.MULTILINGUAL:
                # Multilingual: Unicode NFC normalization + entity-safe boilerplate pruning
                nfc_text = unicodedata.normalize("NFC", current_text)
                pruned_res = self.pruner.prune_context(nfc_text)
                if pruned_res.tokens_saved > 0:
                    transformations.append(
                        "multilingual_unicode_nfc_boilerplate_pruning"
                    )
                    current_text = pruned_res.pruned_text

            elif resolved_workload == WorkloadType.CODING_CONTEXT:
                # Coding Context: diff pruning, generated-file exclusion, AST skeletonization
                code_res = self.code_compressor.compress_code_context(
                    current_text,
                    is_coding_workload=True,
                    level=level,
                    preserve_symbols=preserve_symbols,
                )
                if code_res.fallback_used:
                    logger.warning(
                        "AST Skeletonizer failed (%s); triggering fail-closed fallback.",
                        code_res.fallback_reason,
                    )
                    return OptimizedContext(
                        content=raw_text,
                        source_content_hash=source_hash,
                        transformations=["fail_closed_fallback_raw"],
                        removed_content_metadata={
                            "fallback_reason": code_res.fallback_reason
                        },
                        optimization_level=level,
                        raw_tokens=raw_tokens,
                        optimized_tokens=raw_tokens,
                        tokens_removed=0,
                        reduction_ratio=0.0,
                        fallback_used=True,
                        fallback_reason=code_res.fallback_reason,
                    )
                if code_res.transformations:
                    transformations.extend(code_res.transformations)
                    current_text = code_res.compressed_code
                else:
                    # Fallback to AST skeletonizer if standard python code block
                    if "```" in current_text:
                        skel = self.skeletonizer.skeletonize_markdown_blocks(
                            current_text, level=level, preserve_symbols=preserve_symbols
                        )
                        if skel != current_text:
                            transformations.append(
                                f"ast_skeletonize_markdown_{level.value}"
                            )
                            current_text = skel

            elif resolved_workload == WorkloadType.RAG:
                # RAG: Distractor section pruning and cross-chunk deduplication
                rag_res = self.retrieval_compressor.compress_rag_context_string(
                    current_text, query=user_query
                )
                if rag_res.tokens_saved > 0:
                    transformations.append("rag_retrieval_compression")
                    removed_metadata["citations_preserved"] = (
                        rag_res.citations_preserved
                    )
                    current_text = rag_res.compressed_text

            elif resolved_workload == WorkloadType.FINANCIAL_REASONING:
                # Financial: 100% numerical retention and boilerplate cleanup
                pruned_res = self.pruner.prune_context(current_text)
                if pruned_res.tokens_saved > 0:
                    transformations.append("financial_boilerplate_pruning")
                    current_text = pruned_res.pruned_text

            else:
                # Long Conversation / General: Transcript compaction and sentence deduplication
                pruned_res = self.pruner.prune_context(current_text)
                if pruned_res.tokens_saved > 0:
                    transformations.append("heuristic_pruning_boilerplate_dedup")
                    removed_metadata["pruned_tokens_saved"] = pruned_res.tokens_saved
                    current_text = pruned_res.pruned_text

        except Exception as exc:
            logger.error(
                "Unexpected error during workload-aware optimization: %s; falling back safely.",
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
