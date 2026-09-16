"""High-Precision Performance Profiler & Statistical Aggregator (TEST-09).

Measures:
- Latency distributions (p50, p90, p95, p99, min, max, avg, std_dev)
- Memory heap allocations and peak footprint via tracemalloc
- CPU process user+system time via time.process_time
- SSE streaming behavior (Time to First Chunk - TTFC, inter-chunk latency)
- Throughput (requests/s, ops/s)
"""

from __future__ import annotations

import math
import statistics
import time
import tracemalloc
from typing import Any

from app.performance.contracts import (
    MetricDistribution,
    ResourceMetrics,
    ThroughputMetrics,
)


def compute_distribution(samples: list[float]) -> MetricDistribution:
    """Compute comprehensive statistical distribution from raw samples."""
    if not samples:
        return MetricDistribution()

    clean_samples = sorted(float(s) for s in samples)
    n = len(clean_samples)

    min_val = clean_samples[0]
    max_val = clean_samples[-1]
    avg_val = sum(clean_samples) / n
    std_dev = statistics.stdev(clean_samples) if n > 1 else 0.0

    def get_percentile(p: float) -> float:
        if n == 1:
            return clean_samples[0]
        # Rank calculation with linear interpolation
        k = (n - 1) * (p / 100.0)
        f = math.floor(k)
        c = math.ceil(k)
        if f == c:
            return clean_samples[int(k)]
        d0 = clean_samples[int(f)] * (c - k)
        d1 = clean_samples[int(c)] * (k - f)
        return d0 + d1

    return MetricDistribution(
        count=n,
        min_val=round(min_val, 3),
        max_val=round(max_val, 3),
        avg_val=round(avg_val, 3),
        median_p50=round(get_percentile(50.0), 3),
        p90=round(get_percentile(90.0), 3),
        p95=round(get_percentile(95.0), 3),
        p99=round(get_percentile(99.0), 3),
        std_dev=round(std_dev, 3),
    )


class PerformanceProfiler:
    """Context manager measuring execution duration, CPU time, and peak memory allocations."""

    def __init__(self, track_memory: bool = True) -> None:
        self.track_memory = track_memory
        self.start_wall: float = 0.0
        self.end_wall: float = 0.0
        self.start_cpu: float = 0.0
        self.end_cpu: float = 0.0
        self.start_mem: int = 0
        self.peak_mem: int = 0
        self.end_mem: int = 0
        self._was_tracemalloc_active: bool = False

    def __enter__(self) -> PerformanceProfiler:
        if self.track_memory:
            self._was_tracemalloc_active = tracemalloc.is_tracing()
            if not self._was_tracemalloc_active:
                tracemalloc.start()
            tracemalloc.reset_peak()
            self.start_mem, _ = tracemalloc.get_traced_memory()

        self.start_cpu = time.process_time()
        self.start_wall = time.perf_counter()
        return self

    def __exit__(self, exc_type: Any, exc_val: Any, exc_tb: Any) -> None:
        self.end_wall = time.perf_counter()
        self.end_cpu = time.process_time()

        if self.track_memory:
            self.end_mem, self.peak_mem = tracemalloc.get_traced_memory()
            if not self._was_tracemalloc_active:
                tracemalloc.stop()

    @property
    def duration_seconds(self) -> float:
        return max(0.0, self.end_wall - self.start_wall)

    @property
    def duration_ms(self) -> float:
        return self.duration_seconds * 1000.0

    @property
    def cpu_time_seconds(self) -> float:
        return max(0.0, self.end_cpu - self.start_cpu)

    @property
    def memory_peak_mb(self) -> float:
        return round(self.peak_mem / (1024 * 1024), 3)

    @property
    def memory_delta_mb(self) -> float:
        return round((self.end_mem - self.start_mem) / (1024 * 1024), 3)

    def get_resource_metrics(self) -> ResourceMetrics:
        dur = self.duration_seconds
        cpu_s = self.cpu_time_seconds
        util_pct = round((cpu_s / dur * 100.0), 2) if dur > 0 else 0.0
        return ResourceMetrics(
            peak_memory_mb=self.memory_peak_mb,
            memory_delta_mb=self.memory_delta_mb,
            cpu_time_seconds=round(cpu_s, 4),
            cpu_utilization_pct=util_pct,
        )


class StreamMetricsCollector:
    """Tracks latency and delivery dynamics for Server-Sent Events (SSE) streaming."""

    def __init__(self) -> None:
        self.start_time = time.perf_counter()
        self.first_chunk_time: float | None = None
        self.last_chunk_time: float = self.start_time
        self.inter_chunk_delays_ms: list[float] = []
        self.chunk_count: int = 0
        self.end_time: float = self.start_time

    def record_chunk(self) -> None:
        now = time.perf_counter()
        self.chunk_count += 1
        if self.first_chunk_time is None:
            self.first_chunk_time = now
            ttfc = (now - self.start_time) * 1000.0
            self.inter_chunk_delays_ms.append(ttfc)
        else:
            delay = (now - self.last_chunk_time) * 1000.0
            self.inter_chunk_delays_ms.append(delay)
        self.last_chunk_time = now

    def finish(self) -> None:
        self.end_time = time.perf_counter()

    @property
    def ttfc_ms(self) -> float:
        if self.first_chunk_time is None:
            return 0.0
        return (self.first_chunk_time - self.start_time) * 1000.0

    @property
    def total_duration_ms(self) -> float:
        return (self.end_time - self.start_time) * 1000.0


def calculate_throughput(
    total_requests: int,
    duration_seconds: float,
    concurrency_level: int,
) -> ThroughputMetrics:
    """Compute requests per second and operations per second."""
    dur = max(0.0001, duration_seconds)
    rps = round(total_requests / dur, 2)
    return ThroughputMetrics(
        total_requests=total_requests,
        concurrency_level=concurrency_level,
        duration_seconds=round(dur, 4),
        requests_per_second=rps,
        operations_per_second=rps,
    )
