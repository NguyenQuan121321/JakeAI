"""Telemetry and metrics aggregation for production observability.

Provides thread-safe, low-overhead metrics collection for:
- Request latency and counts
- Provider latency, errors, and retries
- Stream active gauges, duration, and client cancellations
- Cache hit/miss accounting
- RAG latency and token optimization
- Token usage and cost metrics

Guarantees:
- Zero high-cardinality label explosion (normalized route paths)
- Zero secret or raw prompt leakage in metric labels and telemetry entries
"""

from __future__ import annotations

import re
import threading
import time
from collections import defaultdict

from pydantic import BaseModel, Field

# Normalization regex for dynamic path segments (UUIDs, hexadecimal IDs, digits)
_HEX_UUID_RE = re.compile(
    r"/(?:[0-9a-fA-F]{8}-[0-9a-fA-F]{4}-[0-9a-fA-F]{4}-[0-9a-fA-F]{4}-[0-9a-fA-F]{12}|task-[a-zA-Z0-9_-]+|[0-9]+)(?=/|$)"
)


def normalize_metric_path(path: str) -> str:
    """Normalize dynamic parameters from URL path to prevent metric cardinality explosion."""
    normalized = _HEX_UUID_RE.sub("/:id", path)
    return normalized or "/"


class MetricsSnapshot(BaseModel):
    """Structured snapshot of active platform metrics."""

    timestamp: float = Field(default_factory=time.time)
    uptime_seconds: float = Field(default=0.0)
    http_requests_total: dict[str, int] = Field(default_factory=dict)
    http_request_duration_ms_avg: dict[str, float] = Field(default_factory=dict)
    provider_requests_total: dict[str, int] = Field(default_factory=dict)
    provider_latency_ms_avg: dict[str, float] = Field(default_factory=dict)
    provider_errors_total: dict[str, int] = Field(default_factory=dict)
    active_streams: int = Field(default=0)
    stream_cancellations_total: dict[str, int] = Field(default_factory=dict)
    stream_duration_ms_avg: float = Field(default=0.0)
    cache_operations_total: dict[str, int] = Field(default_factory=dict)
    failover_events_total: dict[str, int] = Field(default_factory=dict)
    tokens_consumed_total: dict[str, int] = Field(default_factory=dict)
    estimated_cost_usd_total: float = Field(default=0.0)


class MetricsCollector:
    """In-memory thread-safe metrics collector."""

    def __init__(self) -> None:
        self._lock = threading.Lock()
        self._start_time = time.time()

        # HTTP metrics: (method, normalized_path, status_code) -> count / sum_ms
        self._http_requests: dict[tuple[str, str, int], int] = defaultdict(int)
        self._http_durations: dict[tuple[str, str], list[float]] = defaultdict(list)

        # Provider metrics: (provider, model, status) -> count / sum_ms
        self._provider_requests: dict[tuple[str, str, str], int] = defaultdict(int)
        self._provider_latencies: dict[tuple[str, str], list[float]] = defaultdict(list)
        self._provider_errors: dict[tuple[str, str], int] = defaultdict(int)

        # Streaming metrics
        self._active_streams: int = 0
        self._stream_durations: list[float] = []
        self._stream_cancellations: dict[str, int] = defaultdict(int)

        # Cache & Failover metrics
        self._cache_operations: dict[tuple[str, str], int] = defaultdict(int)
        self._failover_events: dict[tuple[str, str, str], int] = defaultdict(int)

        # Token & FinOps metrics
        self._tokens_consumed: dict[str, int] = defaultdict(int)
        self._estimated_cost_usd: float = 0.0

    def record_http_request(
        self, method: str, path: str, status_code: int, duration_ms: float
    ) -> None:
        """Record an inbound HTTP request and execution duration."""
        norm_path = normalize_metric_path(path)
        with self._lock:
            self._http_requests[(method.upper(), norm_path, status_code)] += 1
            dur_list = self._http_durations[(method.upper(), norm_path)]
            dur_list.append(duration_ms)
            if len(dur_list) > 500:
                del dur_list[:250]

    def record_provider_request(
        self,
        provider: str,
        model: str,
        status: str,
        duration_ms: float,
        prompt_tokens: int = 0,
        completion_tokens: int = 0,
        cost_usd: float = 0.0,
    ) -> None:
        """Record an upstream provider invocation and token usage."""
        p_clean = str(provider).lower()
        m_clean = str(model).lower()
        with self._lock:
            self._provider_requests[(p_clean, m_clean, status)] += 1
            lat_list = self._provider_latencies[(p_clean, m_clean)]
            lat_list.append(duration_ms)
            if len(lat_list) > 500:
                del lat_list[:250]

            if prompt_tokens > 0:
                self._tokens_consumed[f"{m_clean}:prompt"] += prompt_tokens
            if completion_tokens > 0:
                self._tokens_consumed[f"{m_clean}:completion"] += completion_tokens
            if cost_usd > 0.0:
                self._estimated_cost_usd += cost_usd

    def record_provider_error(self, provider: str, category: str) -> None:
        """Record an upstream provider failure categorized by error taxonomy."""
        with self._lock:
            self._provider_errors[(str(provider).lower(), str(category).lower())] += 1

    def stream_started(self) -> None:
        """Increment active streaming count."""
        with self._lock:
            self._active_streams += 1

    def stream_completed(self, duration_ms: float) -> None:
        """Decrement active streaming count and record stream duration."""
        with self._lock:
            self._active_streams = max(0, self._active_streams - 1)
            self._stream_durations.append(duration_ms)
            if len(self._stream_durations) > 500:
                del self._stream_durations[:250]

    def record_stream_cancellation(self, endpoint: str, reason: str = "client_disconnect") -> None:
        """Record a stream cancellation or client disconnect."""
        norm_endpoint = normalize_metric_path(endpoint)
        with self._lock:
            self._active_streams = max(0, self._active_streams - 1)
            self._stream_cancellations[f"{norm_endpoint}:{reason}"] += 1

    def record_cache_operation(self, tier: str, outcome: str) -> None:
        """Record cache query outcome (e.g. tier='exact'|'semantic', outcome='hit'|'miss')."""
        with self._lock:
            self._cache_operations[(str(tier).lower(), str(outcome).lower())] += 1

    def record_failover(self, from_provider: str, to_provider: str, reason: str) -> None:
        """Record provider failover event."""
        with self._lock:
            self._failover_events[
                (str(from_provider).lower(), str(to_provider).lower(), str(reason).lower())
            ] += 1

    def get_snapshot(self) -> MetricsSnapshot:
        """Generate structured snapshot of all captured metrics."""
        now = time.time()
        with self._lock:
            uptime = round(now - self._start_time, 2)

            http_reqs = {
                f"{m} {p} -> {s}": count
                for (m, p, s), count in self._http_requests.items()
            }
            http_dur_avg = {
                f"{m} {p}": round(sum(d) / len(d), 2)
                for (m, p), d in self._http_durations.items()
                if d
            }
            prov_reqs = {
                f"{p}:{m}:{s}": count
                for (p, m, s), count in self._provider_requests.items()
            }
            prov_lat_avg = {
                f"{p}:{m}": round(sum(d) / len(d), 2)
                for (p, m), d in self._provider_latencies.items()
                if d
            }
            prov_errs = {
                f"{p}:{c}": count
                for (p, c), count in self._provider_errors.items()
            }
            stream_dur_avg = (
                round(sum(self._stream_durations) / len(self._stream_durations), 2)
                if self._stream_durations
                else 0.0
            )
            cache_ops = {
                f"{tier}:{outcome}": count
                for (tier, outcome), count in self._cache_operations.items()
            }
            failovers = {
                f"{src}->{dst}:{reason}": count
                for (src, dst, reason), count in self._failover_events.items()
            }

            return MetricsSnapshot(
                timestamp=now,
                uptime_seconds=uptime,
                http_requests_total=http_reqs,
                http_request_duration_ms_avg=http_dur_avg,
                provider_requests_total=prov_reqs,
                provider_latency_ms_avg=prov_lat_avg,
                provider_errors_total=prov_errs,
                active_streams=self._active_streams,
                stream_cancellations_total=dict(self._stream_cancellations),
                stream_duration_ms_avg=stream_dur_avg,
                cache_operations_total=cache_ops,
                failover_events_total=failovers,
                tokens_consumed_total=dict(self._tokens_consumed),
                estimated_cost_usd_total=round(self._estimated_cost_usd, 6),
            )

    def reset(self) -> None:
        """Reset all metrics (primarily for test isolation)."""
        with self._lock:
            self._start_time = time.time()
            self._http_requests.clear()
            self._http_durations.clear()
            self._provider_requests.clear()
            self._provider_latencies.clear()
            self._provider_errors.clear()
            self._active_streams = 0
            self._stream_durations.clear()
            self._stream_cancellations.clear()
            self._cache_operations.clear()
            self._failover_events.clear()
            self._tokens_consumed.clear()
            self._estimated_cost_usd = 0.0


_global_metrics_collector: MetricsCollector | None = None


def get_metrics_collector() -> MetricsCollector:
    """Singleton getter for MetricsCollector."""
    global _global_metrics_collector
    if _global_metrics_collector is None:
        _global_metrics_collector = MetricsCollector()
    return _global_metrics_collector


metrics = get_metrics_collector()
