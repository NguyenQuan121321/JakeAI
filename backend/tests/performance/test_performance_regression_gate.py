"""Performance Regression Detector & Gating Test Suite (TEST-09 / PERF-005 / CAT-127).

Verifies the regression detection and tolerance evaluation engine:
1. Explicit tolerance enforcement (allowed regression percentage).
2. Noise filtering: sub-millisecond CI jitter does not trigger false positive gates.
3. Hard zero-tolerance gate on error rates (>0% produces FAIL).
4. Versioned baseline persistence and auto-introspected environment metadata.
5. Markdown and JSON artifact generation with required comparison columns.
"""

from __future__ import annotations

import tempfile
from pathlib import Path
import pytest

from app.performance.baseline_store import PerformanceBaselineStore, capture_environment_metadata
from app.performance.contracts import (
    EnvironmentMetadata,
    LatencyMetrics,
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
        resources=ResourceMetrics(peak_memory_mb=10.0, memory_delta_mb=1.0, cpu_process_time_seconds=0.1),
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
    assert all(f.verdict in (RegressionVerdict.PASS, RegressionVerdict.WARN) for f in findings)


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
        report = PerformanceRegressionDetector.evaluate_all({"chat": res}, perf_baseline)

        artifacts = reporter.save_artifacts(report, {"chat": res})
        assert Path(artifacts["summary"]).exists()
        assert Path(artifacts["results"]).exists()
        assert Path(artifacts["markdown"]).exists()

        md_content = Path(artifacts["markdown"]).read_text(encoding="utf-8")
        assert "JakeAI Performance Regression Report" in md_content
        assert "| Scenario | Metric | Baseline | Current | Delta | Threshold | Verdict |" in md_content
        assert "`chat`" in md_content
