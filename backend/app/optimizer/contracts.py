"""Cross-Tier Typed Data Contracts for Tiers 5, 6, and 7.

Establishes explicit, immutable typed Pydantic models connecting:
- Tier 5: Two-Zone Prompt Compiler & Provider Prompt Caching
- Tier 6: Context Optimizer & AST Code Skeletonizer
- Tier 7: BPE Tokenizer Engine & FinOps Accounting
"""

from __future__ import annotations

from enum import StrEnum
from typing import Any

from pydantic import BaseModel, Field

from app.optimizer.prompt_compiler import PromptEnvelope  # noqa: TC001


class OptimizationLevel(StrEnum):
    """Context optimization aggressiveness level."""

    CONSERVATIVE = "conservative"  # Code editing, bug fixes, auth, security
    BALANCED = "balanced"  # Repository exploration, search
    AGGRESSIVE = "aggressive"  # System overview, architecture queries


class ContextArtifact(BaseModel):
    """Raw context artifact before Tier 5-7 processing."""

    raw_content: str = Field(..., description="Unmodified context string or code")
    source_files: list[str] = Field(
        default_factory=list, description="List of source file paths included"
    )
    metadata: dict[str, Any] = Field(
        default_factory=dict, description="Metadata such as language, task type"
    )


class OptimizedContext(BaseModel):
    """Result of Tier 6 context optimization and AST skeletonization."""

    content: str = Field(
        ..., description="Optimized context string safe for downstream tokenization"
    )
    source_content_hash: str = Field(
        ..., description="SHA-256 hash of original raw content"
    )
    transformations: list[str] = Field(
        default_factory=list, description="List of transformations applied"
    )
    removed_content_metadata: dict[str, Any] = Field(
        default_factory=dict, description="Metadata on discarded nodes or lines"
    )
    optimization_level: OptimizationLevel = Field(
        default=OptimizationLevel.BALANCED,
        description="Applied optimization level",
    )
    raw_tokens: int = Field(default=0, description="Tokens before Tier 6 optimization")
    optimized_tokens: int = Field(
        default=0, description="Tokens after Tier 6 optimization"
    )
    tokens_removed: int = Field(
        default=0, description="Physically removed tokens: raw - optimized"
    )
    reduction_ratio: float = Field(
        default=0.0,
        description="Physical reduction ratio: (raw - optimized) / raw",
    )
    fallback_used: bool = Field(
        default=False,
        description="True if transformation failed and fell back to raw context",
    )
    fallback_reason: str | None = Field(
        default=None, description="Diagnostic reason for fallback"
    )


class TokenMetrics(BaseModel):
    """Accurate BPE Tokenization metrics produced by Tier 7."""

    tokenizer: str = Field(..., description="Name of tokenizer (e.g. tiktoken/cl100k)")
    tokenizer_version: str = Field(default="1.0.0", description="Tokenizer version")
    input_tokens: int = Field(
        ..., description="Total input tokens sent to LLM provider"
    )
    output_tokens: int | None = Field(
        default=None, description="Actual or estimated output tokens"
    )
    removed_tokens: int = Field(
        default=0, description="Tokens removed by Tier 6 optimization"
    )
    estimated: bool = Field(
        default=False,
        description="True if count is estimated rather than exact BPE encode",
    )
    raw_tokens: int = Field(default=0, description="Pre-optimization token count")
    optimized_tokens: int = Field(
        default=0, description="Post-optimization token count"
    )
    reduction_ratio: float = Field(
        default=0.0,
        description="Reduction ratio: (raw - optimized) / raw",
    )


class ProviderCacheMetrics(BaseModel):
    """Layer B Upstream Provider Prompt Cache telemetry."""

    eligible: bool = Field(
        default=False,
        description="True if static prefix meets provider minimum token threshold",
    )
    requested: bool = Field(
        default=False,
        description="True if provider prompt caching headers/breakpoints were attached",
    )
    hit: bool | None = Field(
        default=None,
        description="True strictly if upstream provider reported cached tokens > 0",
    )
    cache_read_tokens: int = Field(
        default=0, description="Tokens served from upstream KV cache"
    )
    cache_creation_tokens: int = Field(
        default=0, description="Tokens written to upstream KV cache"
    )
    uncached_input_tokens: int = Field(
        default=0, description="Input tokens processed without cache hit"
    )
    miss_reason: str = Field(
        default="none", description="Fine-grained miss reason attribution"
    )


class CrossTierResult(BaseModel):
    """Complete end-to-end outcome of Tier 5 -> 6 -> 7 -> 5 pipeline execution."""

    raw_context: str = Field(..., description="Original unoptimized context")
    compiled_prompt: PromptEnvelope = Field(
        ..., description="Final two-zone compiled prompt envelope"
    )
    optimized_context: OptimizedContext = Field(
        ..., description="Tier 6 optimization output"
    )
    token_metrics: TokenMetrics = Field(
        ..., description="Tier 7 BPE token measurements"
    )
    provider_cache_metrics: ProviderCacheMetrics = Field(
        default_factory=ProviderCacheMetrics,
        description="Tier 5 provider cache telemetry",
    )
    cost_metrics: dict[str, Any] = Field(
        default_factory=dict, description="FinOps cost accounting metrics"
    )
    fallback_used: bool = Field(
        default=False, description="True if any fail-safe fallback was engaged"
    )
    fallback_reason: str | None = Field(
        default=None, description="Diagnostic error details if fallback triggered"
    )
    transformations: list[str] = Field(
        default_factory=list, description="All transformations executed across tiers"
    )
    response_content: str | None = Field(
        default=None, description="Final LLM text response if executed"
    )
    latency_metrics: dict[str, float] = Field(
        default_factory=dict, description="Execution latencies per stage in seconds"
    )


class EvaluationRecord(BaseModel):
    """Normalized empirical evaluation entry for Phase 00 measurement model (Section 3)."""

    request_id: str = Field(..., description="Unique evaluation interaction ID")
    workload_id: str = Field(..., description="Workload case identifier")
    workload_type: str = Field(
        ...,
        description="Type: simple_chat, long_conversation, rag, financial_reasoning, coding_context, structured_json, multilingual",
    )
    provider: str = Field(..., description="Upstream model provider")
    model: str = Field(..., description="Evaluated model name")
    raw_input_tokens: int = Field(..., description="Unoptimized baseline input tokens")
    optimized_input_tokens: int = Field(..., description="Tokens after optimization")
    physical_tokens_removed: int = Field(
        ..., description="Raw tokens removed physically"
    )
    provider_cached_input_tokens: int = Field(
        default=0, description="Tokens read from provider KV cache"
    )
    provider_uncached_input_tokens: int = Field(
        default=0, description="Tokens processed as uncached input by provider"
    )
    output_tokens: int = Field(default=0, description="Completion/output tokens")
    total_provider_reported_tokens: int = Field(
        default=0, description="Total tokens reported by provider usage API"
    )
    latency_ms: float = Field(default=0.0, description="End-to-end execution latency")
    estimated_cost_usd: float = Field(
        default=0.0, description="Estimated USD cost under pricing matrix"
    )
    actual_cost_usd_when_available: float | None = Field(
        default=None, description="Actual provider invoice cost if reported"
    )
    tokens_saved: int = Field(
        ..., description="Total tokens saved (physical + cache hit)"
    )
    cost_saved: float = Field(..., description="Total USD cost saved")
    quality_score: float = Field(
        ..., ge=0.0, le=1.0, description="Quality score from Layered Oracle"
    )
    quality_regression: float = Field(
        default=0.0, description="Quality regression vs baseline"
    )
    passed: bool = Field(..., description="True if test case passed all gates")
    verdict_details: dict[str, Any] = Field(
        default_factory=dict, description="Detailed diagnostic verdicts"
    )
