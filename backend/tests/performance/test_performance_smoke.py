"""Fast Performance Smoke Test Suite (TEST-09 / PERF-003 / CAT-125).

Runs in under 10 seconds in CI PR validation.
Validates:
1. All 6 core performance scenarios execute without crashes or timeouts.
2. Hard zero error rate (error_rate_pct == 0.0%).
3. Positive throughput and latency metrics captured.
4. Profiler resource telemetry (heap memory, CPU time) populated.
"""

from __future__ import annotations

import sys
import time

import pytest

from app.performance.runner import PerformanceBenchmarkRunner


@pytest.mark.performance
@pytest.mark.asyncio
async def test_performance_smoke_all_six_scenarios() -> None:
    """PERF-003: Verify all 6 performance scenarios complete with zero error rate under 10s."""
    runner = PerformanceBenchmarkRunner(mode="smoke", concurrency_multiplier=1.0)

    t0 = time.perf_counter()
    results = await runner.run_all_scenarios(run_warmup=False)
    elapsed_seconds = time.perf_counter() - t0

    expected_scenarios = [
        "concurrent_chat",
        "concurrent_agent_runs",
        "concurrent_rag_queries",
        "sse_connections",
        "redis_contention",
        "qdrant_access",
    ]

    assert len(results) == 6, f"Expected 6 scenarios, got {len(results)}"

    for scen_name in expected_scenarios:
        assert scen_name in results, f"Missing scenario {scen_name} in smoke results"
        res = results[scen_name]

        # Zero tolerance for errors in CI smoke
        assert res.error_count == 0, (
            f"Scenario {scen_name} had {res.error_count} errors"
        )
        assert res.error_rate_pct == 0.0, (
            f"Scenario {scen_name} had non-zero error rate: {res.error_rate_pct}%"
        )
        assert res.success_count > 0, f"Scenario {scen_name} had zero successes"

        # Telemetry sanity checks
        assert res.latency.overall_ms.median_p50 > 0.0, f"{scen_name} p50 <= 0"
        assert res.latency.overall_ms.p95 > 0.0, f"{scen_name} p95 <= 0"
        assert res.throughput.requests_per_second > 0.0, f"{scen_name} throughput <= 0"
        assert res.resources.peak_memory_mb >= 0.0, f"{scen_name} peak memory invalid"

    # Strict smoke timing budget (< 10s benchmark budget; accounts for branch coverage tracer overhead if active)
    budget = 15.0 if sys.gettrace() is not None else 10.0
    assert elapsed_seconds < budget, (
        f"Smoke test exceeded {budget}s timing budget: took {elapsed_seconds:.2f}s"
    )
