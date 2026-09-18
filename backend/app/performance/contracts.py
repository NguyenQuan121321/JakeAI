"""Pydantic Contracts for JakeAI Performance Regression Automation (TEST-09).

Defines strongly-typed data structures for:
1. Metric distributions (p50, p90, p95, p99, min, max, avg, std_dev)
2. Latency, throughput, resource (memory/CPU), token, and cache metrics
3. Scenario execution results
4. Versioned performance baseline specifications and explicit tolerances
5. Environment metadata (commit, Python version, platform, dependencies hash)
6. Regression audit findings and evaluation reports
"""

from __future__ import annotations

import time
from enum import StrEnum
from typing import Any

from pydantic import BaseModel, Field


class RegressionVerdict(StrEnum):
    """Verdict classifications for performance regression evaluation."""

    PASS = "PASS"  # nosec B105
    WARN = "WARN"
    FAIL = "FAIL"


class MetricDirection(StrEnum):
    """Directionality of metric optimization quality (higher vs lower is better)."""

    HIGHER_IS_BETTER = "HIGHER_IS_BETTER"
    LOWER_IS_BETTER = "LOWER_IS_BETTER"


class MetricDistribution(BaseModel):
    """Statistical distribution of a measured numeric metric."""

    count: int = Field(default=0, ge=0)
    min_val: float = Field(default=0.0)
    max_val: float = Field(default=0.0)
    avg_val: float = Field(default=0.0)
    median_p50: float = Field(default=0.0)
    p90: float = Field(default=0.0)
    p95: float = Field(default=0.0)
    p99: float = Field(default=0.0)
    std_dev: float = Field(default=0.0)


class LatencyMetrics(BaseModel):
    """Granular latency measurements in milliseconds."""

    overall_ms: MetricDistribution = Field(default_factory=MetricDistribution)
    ttfc_ms: MetricDistribution = Field(
        default_factory=MetricDistribution,
        description="Time to first chunk for streaming responses (ms)",
    )
    inter_chunk_ms: MetricDistribution = Field(
        default_factory=MetricDistribution,
        description="Interval between consecutive chunks in streaming responses (ms)",
    )
    provider_ms: MetricDistribution = Field(
        default_factory=MetricDistribution,
        description="Upstream model provider round-trip time (ms)",
    )
    rag_ms: MetricDistribution = Field(
        default_factory=MetricDistribution,
        description="Retrieval + rerank + context selection time (ms)",
    )
    agent_ms: MetricDistribution = Field(
        default_factory=MetricDistribution,
        description="Agent run iteration execution time (ms)",
    )


class ThroughputMetrics(BaseModel):
    """System throughput metrics across concurrent operations."""

    total_requests: int = Field(default=0, ge=0)
    concurrency_level: int = Field(default=1, ge=1)
    duration_seconds: float = Field(default=0.0, ge=0.0)
    requests_per_second: float = Field(default=0.0, ge=0.0)
    operations_per_second: float = Field(default=0.0, ge=0.0)


class ResourceMetrics(BaseModel):
    """Process memory footprint and CPU utilization."""

    peak_memory_mb: float = Field(
        default=0.0, ge=0.0, description="Peak memory heap allocated during test (MB)"
    )
    memory_delta_mb: float = Field(
        default=0.0, description="Memory heap delta between start and finish (MB)"
    )
    cpu_time_seconds: float = Field(
        default=0.0, ge=0.0, description="Total CPU user+system time consumed (s)"
    )
    cpu_utilization_pct: float = Field(
        default=0.0, ge=0.0, description="Effective process CPU utilization percentage"
    )


class TokenMetrics(BaseModel):
    """Token consumption, caching efficiency, and cost telemetry."""

    total_raw_tokens: int = Field(default=0, ge=0)
    total_optimized_tokens: int = Field(default=0, ge=0)
    total_cached_tokens: int = Field(default=0, ge=0)
    total_output_tokens: int = Field(default=0, ge=0)
    token_reduction_pct: float = Field(default=0.0)


class CacheMetrics(BaseModel):
    """Multi-tier cache hit/miss behavior."""

    tier1_exact_hits: int = Field(default=0, ge=0)
    tier1_exact_misses: int = Field(default=0, ge=0)
    tier2_semantic_hits: int = Field(default=0, ge=0)
    tier2_semantic_misses: int = Field(default=0, ge=0)
    provider_prompt_cache_hits: int = Field(default=0, ge=0)
    provider_prompt_cache_misses: int = Field(default=0, ge=0)
    cache_hit_rate_pct: float = Field(default=0.0, ge=0.0, le=100.0)


class ScenarioResult(BaseModel):
    """Complete execution outcome for a specific performance scenario."""

    scenario_name: str
    concurrency: int = Field(default=1, ge=1)
    total_requests: int = Field(default=0, ge=0)
    success_count: int = Field(default=0, ge=0)
    error_count: int = Field(default=0, ge=0)
    error_rate_pct: float = Field(default=0.0, ge=0.0, le=100.0)
    latency: LatencyMetrics = Field(default_factory=LatencyMetrics)
    throughput: ThroughputMetrics = Field(default_factory=ThroughputMetrics)
    resources: ResourceMetrics = Field(default_factory=ResourceMetrics)
    tokens: TokenMetrics | None = None
    cache: CacheMetrics | None = None
    custom_metrics: dict[str, Any] = Field(default_factory=dict)


class EnvironmentMetadata(BaseModel):
    """Hardware, software, and dependency context for reproducibility."""

    commit: str = "unknown"
    environment: str = "local"
    python_version: str = ""
    os_name: str = ""
    platform_name: str = ""
    cpu_count: int = 1
    dependencies_hash: str = ""
    recorded_at: float = Field(default_factory=time.time)


class ScenarioBaseline(BaseModel):
    """Baseline expectations and explicit tolerances for one scenario."""

    scenario_name: str
    concurrency: int = 1
    input_size: str = "standard"
    baseline_metrics: dict[str, float] = Field(
        default_factory=dict,
        description="Map of metric names to baseline numeric values (e.g. p50_ms, p95_ms, throughput_rps)",
    )
    tolerances: dict[str, float] = Field(
        default_factory=dict,
        description="Explicit allowed degradation percentage or maximum absolute value",
    )


class PerformanceBaseline(BaseModel):
    """Source-controlled performance baseline contract."""

    version: str = "v1"
    environment: EnvironmentMetadata = Field(default_factory=EnvironmentMetadata)
    scenarios: dict[str, ScenarioBaseline] = Field(default_factory=dict)
    description: str = "Canonical Performance Regression Baseline"


class RegressionFinding(BaseModel):
    """Single metric regression or pass comparison finding."""

    scenario: str
    metric_name: str
    baseline_value: float
    current_value: float
    delta: float
    delta_pct: float
    threshold: float
    verdict: RegressionVerdict
    direction: MetricDirection = MetricDirection.LOWER_IS_BETTER
    is_reproducible: bool = True
    message: str


class PerformanceRegressionReport(BaseModel):
    """Consolidated regression report comparing run against versioned baseline."""

    baseline_version: str
    commit: str
    environment: EnvironmentMetadata
    verdict: RegressionVerdict
    has_blocking_regressions: bool
    total_scenarios_evaluated: int = 0
    passed_scenarios: int = 0
    failed_scenarios: int = 0
    findings: list[RegressionFinding] = Field(default_factory=list)
    scenarios: dict[str, ScenarioResult] = Field(default_factory=dict)
    summary_text: str = ""
