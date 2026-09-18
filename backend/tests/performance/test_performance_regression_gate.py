"""Performance Regression Detector & Gating Test Suite (TEST-09 / PERF-005 / CAT-127).

Verifies the regression detection and tolerance evaluation engine:
1. Explicit tolerance enforcement (allowed regression percentage).
2. Noise filtering: sub-millisecond CI jitter does not trigger false positive gates.
3. Hard zero-tolerance gate on error rates (>0% produces FAIL).
4. Versioned baseline persistence and auto-introspected environment metadata.
5. Markdown and JSON artifact generation with required comparison columns.
"""

from __future__ import annotations

import math
import tempfile
from pathlib import Path

import pytest

from app.performance.baseline_store import (
    PerformanceBaselineStore,
    capture_environment_metadata,
)
from app.performance.contracts import (
    LatencyMetrics,
    MetricDirection,
    MetricDistribution,
    PerformanceBaseline,
    RegressionVerdict,
    ResourceMetrics,
    ScenarioBaseline,
    ScenarioResult,
    ThroughputMetrics,
)
from app.performance.regression_detector import PerformanceRegressionDetector
from app.performance.reporter import PerformanceReporter


def _create_dummy_result(
    scenario_name: str = "test_scenario",
    p50: float = 10.0,
    p95: float = 20.0,
    p99: float = 30.0,
    rps: float = 100.0,
    error_rate: float = 0.0,
) -> ScenarioResult:
    """Helper to construct synthetic scenario results for deterministic auditing."""
    dist = MetricDistribution(
        count=100,
        min=5.0,
        max=p99,
        avg=p50,
        median_p50=p50,
        p90=p95 * 0.9,
        p95=p95,
        p99=p99,
        std_dev=2.0,
    )
    return ScenarioResult(
        scenario_name=scenario_name,
        concurrency=10,
        total_requests=100,
        success_count=int(100 * (1.0 - error_rate / 100.0)),
        error_count=int(100 * (error_rate / 100.0)),
        error_rate_pct=error_rate,
        latency=LatencyMetrics(overall_ms=dist),
        throughput=ThroughputMetrics(
            total_requests=100,
            elapsed_seconds=1.0,
            requests_per_second=rps,
            concurrency=10,
        ),
        resources=ResourceMetrics(
            peak_memory_mb=10.0, memory_delta_mb=1.0, cpu_process_time_seconds=0.1
        ),
    )


def _create_dummy_baseline(
    scenario_name: str = "test_scenario",
    p50: float = 10.0,
    p95: float = 20.0,
    p99: float = 30.0,
    rps: float = 100.0,
    allowed_lat_pct: float = 40.0,
    min_delta_ms: float = 15.0,
) -> ScenarioBaseline:
    """Helper to construct synthetic scenario baseline."""
    return ScenarioBaseline(
        scenario_name=scenario_name,
        concurrency=10,
        input_size="100 requests",
        baseline_metrics={
            "latency_p50_ms": p50,
            "latency_p95_ms": p95,
            "latency_p99_ms": p99,
            "throughput_rps": rps,
            "error_rate_pct": 0.0,
            "memory_peak_mb": 10.0,
        },
        tolerances={
            "allowed_latency_regression_pct": allowed_lat_pct,
            "min_significant_delta_ms": min_delta_ms,
            "allowed_throughput_regression_pct": 35.0,
            "max_error_rate_pct": 0.0,
        },
    )


def test_regression_detector_passes_within_tolerance() -> None:
    """PERF-005: Verify detector reports PASS when metrics remain within configured tolerance."""
    base = _create_dummy_baseline(p95=20.0, allowed_lat_pct=40.0)  # ceiling: 28.0ms
    curr = _create_dummy_result(p95=22.0)  # +10%, well below +40%

    findings = PerformanceRegressionDetector.evaluate_scenario(curr, base)
    verdicts = [f.verdict for f in findings]
    assert RegressionVerdict.FAIL not in verdicts
    assert all(
        f.verdict in (RegressionVerdict.PASS, RegressionVerdict.WARN) for f in findings
    )


def test_regression_detector_blocks_on_error_rate() -> None:
    """PERF-005: Zero tolerance error rate enforcement produces immediate FAIL."""
    base = _create_dummy_baseline()
    curr = _create_dummy_result(error_rate=1.0)  # 1% error rate

    findings = PerformanceRegressionDetector.evaluate_scenario(curr, base)
    err_finding = next(f for f in findings if f.metric_name == "error_rate_pct")
    assert err_finding.verdict == RegressionVerdict.FAIL
    assert "Error rate exceeded threshold" in err_finding.message


def test_regression_detector_noise_filtering() -> None:
    """PERF-005: Latency shift below min_significant_delta_ms does not trigger FAIL even if percentage is high."""
    # Baseline p95 is 0.5ms. Current is 1.2ms (+140% increase), but delta is only 0.7ms (< 15ms noise floor)
    base = _create_dummy_baseline(p95=0.5, min_delta_ms=15.0)
    curr = _create_dummy_result(p95=1.2)

    findings = PerformanceRegressionDetector.evaluate_scenario(curr, base)
    lat_findings = [f for f in findings if "latency" in f.metric_name]
    assert all(f.verdict != RegressionVerdict.FAIL for f in lat_findings)


def test_regression_detector_blocks_meaningful_latency_regression() -> None:
    """PERF-005: Latency shift exceeding both percentage AND min_significant_delta_ms triggers FAIL."""
    # Baseline p95 is 20.0ms. Current is 45.0ms (+125% increase, delta 25.0ms >= 15.0ms noise floor)
    base = _create_dummy_baseline(p95=20.0, allowed_lat_pct=40.0, min_delta_ms=15.0)
    curr = _create_dummy_result(p95=45.0)

    findings = PerformanceRegressionDetector.evaluate_scenario(curr, base)
    p95_finding = next(f for f in findings if f.metric_name == "latency_p95_ms")
    assert p95_finding.verdict == RegressionVerdict.FAIL
    assert "Meaningful latency regression" in p95_finding.message


def test_regression_detector_throughput_noise_filtering() -> None:
    """PERF-005: Throughput drop below min_significant_delta_rps produces WARN, not blocking FAIL."""
    base = _create_dummy_baseline(rps=50.0)
    # Drop of 20 RPS is >35% drop, but within 25.0 RPS noise floor
    curr = _create_dummy_result(rps=30.0)

    findings = PerformanceRegressionDetector.evaluate_scenario(curr, base)
    rps_finding = next(f for f in findings if f.metric_name == "throughput_rps")
    assert rps_finding.verdict == RegressionVerdict.WARN
    assert "noise margin" in rps_finding.message


def test_regression_detector_blocks_meaningful_throughput_regression() -> None:
    """PERF-005: Throughput drop exceeding percentage AND min_significant_delta_rps triggers FAIL."""
    base = _create_dummy_baseline(rps=100.0)
    # Drop of 60 RPS exceeds 35% AND exceeds 25.0 RPS noise floor
    curr = _create_dummy_result(rps=40.0)

    findings = PerformanceRegressionDetector.evaluate_scenario(curr, base)
    rps_finding = next(f for f in findings if f.metric_name == "throughput_rps")
    assert rps_finding.verdict == RegressionVerdict.FAIL
    assert "Throughput regression" in rps_finding.message


def test_throughput_improvement_is_not_a_regression() -> None:
    """TEST-09 / PART 9: Verify throughput improvement (56.8 -> 117.2 rps) evaluates to PASS."""
    baseline_rps = 56.8
    current_rps = 117.2

    base = _create_dummy_baseline(
        scenario_name="concurrent_rag_queries",
        rps=baseline_rps,
    )
    curr = _create_dummy_result(
        scenario_name="concurrent_rag_queries",
        rps=current_rps,
    )

    findings = PerformanceRegressionDetector.evaluate_scenario(curr, base)
    rps_finding = next(f for f in findings if f.metric_name == "throughput_rps")

    assert rps_finding.verdict != RegressionVerdict.FAIL
    assert rps_finding.verdict == RegressionVerdict.PASS
    assert rps_finding.current_value == pytest.approx(117.2, abs=0.01)
    assert rps_finding.baseline_value == pytest.approx(56.8, abs=0.01)
    assert rps_finding.delta == pytest.approx(60.4, abs=0.05)
    assert rps_finding.delta_pct == pytest.approx(106.34, abs=0.1)
    assert rps_finding.direction == MetricDirection.HIGHER_IS_BETTER
    assert "meets requirement" in rps_finding.message

    # Also verify evaluate_all has_blocking_regressions is False
    perf_baseline = PerformanceBaseline(
        version="v1",
        environment=capture_environment_metadata(),
        scenarios={"concurrent_rag_queries": base},
    )
    report = PerformanceRegressionDetector.evaluate_all(
        {"concurrent_rag_queries": curr}, perf_baseline
    )
    assert report.has_blocking_regressions is False
    assert report.verdict == RegressionVerdict.PASS


def test_regression_matrix_higher_is_better() -> None:
    """TEST-09 / PART 8: HIGHER_IS_BETTER test matrix (throughput_rps)."""
    # Baseline = 100 RPS, allowed drop = 35% (threshold = 65 RPS), min significant delta = 25 RPS
    base = _create_dummy_baseline(rps=100.0)

    # 1. current > baseline -> PASS
    curr_higher = _create_dummy_result(rps=130.0)
    f1 = next(
        f
        for f in PerformanceRegressionDetector.evaluate_scenario(curr_higher, base)
        if f.metric_name == "throughput_rps"
    )
    assert f1.verdict == RegressionVerdict.PASS
    assert f1.delta > 0

    # 2. current == baseline -> PASS
    curr_equal = _create_dummy_result(rps=100.0)
    f2 = next(
        f
        for f in PerformanceRegressionDetector.evaluate_scenario(curr_equal, base)
        if f.metric_name == "throughput_rps"
    )
    assert f2.verdict == RegressionVerdict.PASS
    assert f2.delta == 0.0

    # 3. current slightly below baseline:
    # 3a. Below baseline but above threshold (e.g. 80 RPS >= 65 RPS) -> PASS
    curr_slight_drop = _create_dummy_result(rps=80.0)
    f3a = next(
        f
        for f in PerformanceRegressionDetector.evaluate_scenario(curr_slight_drop, base)
        if f.metric_name == "throughput_rps"
    )
    assert f3a.verdict == RegressionVerdict.PASS

    # 3b. Below threshold but within noise floor (base=50 -> threshold=32.5, drop 20 < 25 noise floor) -> WARN
    base_50 = _create_dummy_baseline(rps=50.0)
    curr_noise = _create_dummy_result(rps=30.0)
    f3b = next(
        f
        for f in PerformanceRegressionDetector.evaluate_scenario(curr_noise, base_50)
        if f.metric_name == "throughput_rps"
    )
    assert f3b.verdict == RegressionVerdict.WARN

    # 4. current materially below baseline (crosses threshold AND drop >= 25 RPS noise floor) -> FAIL
    curr_material_drop = _create_dummy_result(rps=40.0)
    f4 = next(
        f
        for f in PerformanceRegressionDetector.evaluate_scenario(
            curr_material_drop, base
        )
        if f.metric_name == "throughput_rps"
    )
    assert f4.verdict == RegressionVerdict.FAIL


def test_regression_matrix_lower_is_better() -> None:
    """TEST-09 / PART 8: LOWER_IS_BETTER test matrix (latency_p95_ms)."""
    # Baseline = 100ms, allowed increase = 40% (threshold = 140ms), min_delta = 15ms
    base = _create_dummy_baseline(p95=100.0, allowed_lat_pct=40.0, min_delta_ms=15.0)

    # 5. current < baseline -> PASS
    curr_lower = _create_dummy_result(p95=75.0)
    f5 = next(
        f
        for f in PerformanceRegressionDetector.evaluate_scenario(curr_lower, base)
        if f.metric_name == "latency_p95_ms"
    )
    assert f5.verdict == RegressionVerdict.PASS
    assert f5.delta < 0

    # 6. current == baseline -> PASS
    curr_equal = _create_dummy_result(p95=100.0)
    f6 = next(
        f
        for f in PerformanceRegressionDetector.evaluate_scenario(curr_equal, base)
        if f.metric_name == "latency_p95_ms"
    )
    assert f6.verdict == RegressionVerdict.PASS
    assert f6.delta == 0.0

    # 7. current slightly above baseline (> 20% warning threshold but <= 40% threshold) -> WARN
    curr_slight_increase = _create_dummy_result(p95=125.0)
    f7 = next(
        f
        for f in PerformanceRegressionDetector.evaluate_scenario(
            curr_slight_increase, base
        )
        if f.metric_name == "latency_p95_ms"
    )
    assert f7.verdict == RegressionVerdict.WARN

    # 8. current materially above baseline (> 40% threshold and delta >= 15ms) -> FAIL
    curr_material_increase = _create_dummy_result(p95=150.0)
    f8 = next(
        f
        for f in PerformanceRegressionDetector.evaluate_scenario(
            curr_material_increase, base
        )
        if f.metric_name == "latency_p95_ms"
    )
    assert f8.verdict == RegressionVerdict.FAIL


def test_zero_baseline_and_edge_cases() -> None:
    """TEST-09 / PART 10: Zero baseline division protection and deterministic behavior."""
    # Zero baseline, zero current -> delta = 0.0, delta_pct = 0.0, PASS
    f_zero = PerformanceRegressionDetector.evaluate_metric(
        scenario_name="test",
        metric_name="throughput_rps",
        baseline_val=0.0,
        current_val=0.0,
        allowed_tolerance_pct=35.0,
        min_significant_delta=10.0,
        direction=MetricDirection.HIGHER_IS_BETTER,
    )
    assert f_zero.delta == 0.0
    assert f_zero.delta_pct == 0.0
    assert f_zero.verdict == RegressionVerdict.PASS
    assert not math.isnan(f_zero.delta_pct)
    assert not math.isinf(f_zero.delta_pct)

    # Zero baseline, positive current -> improvement, PASS
    f_pos = PerformanceRegressionDetector.evaluate_metric(
        scenario_name="test",
        metric_name="throughput_rps",
        baseline_val=0.0,
        current_val=50.0,
        allowed_tolerance_pct=35.0,
        min_significant_delta=10.0,
        direction=MetricDirection.HIGHER_IS_BETTER,
    )
    assert f_pos.delta == 50.0
    assert f_pos.delta_pct == 100.0
    assert f_pos.verdict == RegressionVerdict.PASS


def test_reporter_shows_positive_delta_for_throughput_improvement() -> None:
    """TEST-09 / PART 7: Ensure reporter prints +60.4 rps and +106.3% when current > baseline."""
    with tempfile.TemporaryDirectory() as tmpdir:
        reporter = PerformanceReporter(output_dir=Path(tmpdir))
        base = _create_dummy_baseline("rag", rps=56.8)
        curr = _create_dummy_result("rag", rps=117.2)

        perf_baseline = PerformanceBaseline(
            version="v1",
            environment=capture_environment_metadata(),
            scenarios={"rag": base},
        )
        report = PerformanceRegressionDetector.evaluate_all(
            {"rag": curr}, perf_baseline
        )

        md = reporter.generate_markdown_report(report, {"rag": curr})
        assert "+60.4 rps (+106.3%)" in md
        assert "56.8 rps" in md
        assert "117.2 rps" in md
        assert "✅ PASS" in md
        assert "-60.4 rps" not in md


def test_baseline_store_persistence_and_introspection() -> None:
    """PERF-005: Verify filesystem persistence of versioned baseline with metadata."""
    with tempfile.TemporaryDirectory() as tmpdir:
        store = PerformanceBaselineStore(baselines_dir=Path(tmpdir))
        env = capture_environment_metadata()
        assert env.commit is not None
        assert env.python_version is not None

        scen_base = _create_dummy_baseline("chat")
        baseline = PerformanceBaseline(
            version="v_test",
            environment=env,
            scenarios={"chat": scen_base},
            description="Test baseline",
        )
        saved_path = store.save_baseline(baseline, "v_test")
        assert saved_path.exists()

        loaded = store.load_baseline("v_test")
        assert loaded is not None
        assert loaded.version == "v_test"
        assert "chat" in loaded.scenarios
        assert loaded.scenarios["chat"].baseline_metrics["latency_p95_ms"] == 20.0


def test_reporter_artifacts_generation() -> None:
    """PERF-005: Verify PerformanceReporter generates valid JSON and Markdown files."""
    with tempfile.TemporaryDirectory() as tmpdir:
        reporter = PerformanceReporter(output_dir=Path(tmpdir))
        res = _create_dummy_result("chat")
        base = _create_dummy_baseline("chat")

        perf_baseline = PerformanceBaseline(
            version="v1",
            environment=capture_environment_metadata(),
            scenarios={"chat": base},
        )
        report = PerformanceRegressionDetector.evaluate_all(
            {"chat": res}, perf_baseline
        )

        artifacts = reporter.save_artifacts(report, {"chat": res})
        assert Path(artifacts["summary"]).exists()
        assert Path(artifacts["results"]).exists()
        assert Path(artifacts["markdown"]).exists()

        md_content = Path(artifacts["markdown"]).read_text(encoding="utf-8")
        assert "JakeAI Performance Regression Report" in md_content
        assert (
            "| Scenario | Metric | Baseline | Current | Delta | Threshold | Verdict |"
            in md_content
        )
        assert "`chat`" in md_content


def test_baseline_store_fallback_and_exists() -> None:
    """Verify baseline store handles missing baseline and existence queries."""
    with tempfile.TemporaryDirectory() as tmpdir:
        store = PerformanceBaselineStore(baselines_dir=Path(tmpdir))
        assert not store.baseline_exists("nonexistent_v99")
        fallback = store.load_baseline("nonexistent_v99")
        assert fallback.version == "nonexistent_v99"
        assert fallback.environment is not None


@pytest.mark.asyncio
async def test_in_memory_contention_redis_methods() -> None:
    """Verify all auxiliary methods on InMemoryContentionRedis."""
    from app.performance.scenarios.redis_contention_scenario import (
        InMemoryContentionRedis,
    )

    redis = InMemoryContentionRedis()
    assert await redis.ping() is True
    await redis.set("k1", "v1")
    assert await redis.get("k1") == "v1"
    assert await redis.exists("k1", "k2") == 1
    assert await redis.incrby("counter", 5) == 5
    assert await redis.incrbyfloat("f_counter", 2.5) == 2.5
    assert await redis.delete("k1", "counter") == 2
    assert await redis.get("k1") is None


@pytest.mark.asyncio
async def test_runner_benchmark_and_audit() -> None:
    """Verify PerformanceBenchmarkRunner run_benchmark_and_audit pipeline."""
    from unittest.mock import AsyncMock, patch

    from app.performance.runner import PerformanceBenchmarkRunner

    with tempfile.TemporaryDirectory() as tmpdir:
        runner = PerformanceBenchmarkRunner(mode="smoke")
        runner.store = PerformanceBaselineStore(baselines_dir=Path(tmpdir))
        # Seed baseline in temporary store
        base_res = _create_dummy_result("concurrent_chat")
        scen_base = _create_dummy_baseline("concurrent_chat")
        base = PerformanceBaseline(
            version="v1",
            environment=capture_environment_metadata(),
            scenarios={"concurrent_chat": scen_base},
        )
        runner.store.save_baseline(base, "v1")

        with (
            patch.object(
                runner,
                "run_all_scenarios",
                new_callable=AsyncMock,
                return_value={"concurrent_chat": base_res},
            ),
            patch.object(runner, "_warmup", new_callable=AsyncMock),
        ):
            results, report = await runner.run_benchmark_and_audit()
            assert "concurrent_chat" in results
            assert report.baseline_version == "v1"
            assert report.total_scenarios_evaluated == 1
