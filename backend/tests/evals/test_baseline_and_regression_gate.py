"""Unit tests for Baseline Store and Live Benchmark Regression Gate (TASK OPS-15 & OPS-16)."""

from app.evals.baseline_store import BaselineMetrics, get_baseline_store
from app.evals.benchmark_runner import BenchmarkSummary
from app.evals.regression_detector import RegressionDetector, RegressionSeverity


def test_baseline_store_load_and_save(tmp_path):
    from app.evals.baseline_store import BaselineStore

    store = BaselineStore(baselines_dir=tmp_path)

    metrics = BaselineMetrics(
        version="v2_test",
        avg_quality_score=0.91,
        min_pass_rate_pct=98.0,
        max_quality_regression=0.03,
    )
    saved_path = store.save_baseline(metrics)
    assert saved_path.exists()

    loaded = store.load_baseline("v2_test")
    assert loaded.version == "v2_test"
    assert loaded.avg_quality_score == 0.91
    assert loaded.min_pass_rate_pct == 98.0


def test_canonical_v1_baseline_exists():
    store = get_baseline_store()
    baseline = store.load_baseline("v1")
    assert baseline.version == "v1"
    assert baseline.avg_quality_score >= 0.85
    assert baseline.min_pass_rate_pct >= 95.0
    assert "financial_analysis" in baseline.workload_baselines


def test_live_benchmark_evaluation_pass():
    summary = BenchmarkSummary(
        total_workloads=10,
        total_passed=10,
        pass_rate_pct=100.0,
        total_baseline_input_tokens=1000,
        total_optimized_input_tokens=600,
        total_physical_tokens_removed=400,
        physical_reduction_pct=40.0,
        total_provider_cached_tokens=200,
        total_provider_uncached_tokens=400,
        total_output_tokens=150,
        total_baseline_cost_usd=0.05,
        total_optimized_cost_usd=0.02,
        total_cost_saved_usd=0.03,
        cost_savings_pct=60.0,
        avg_quality_score=0.90,
        max_quality_regression=0.0,
        portfolio_token_reduction_pct=50.0,
        is_40pct_claim_verified=True,
        verdict="ACCEPTED",
    )
    report = RegressionDetector.evaluate_live_benchmark(summary, baseline_version="v1")
    assert report.verdict == RegressionSeverity.PASS
    assert report.has_blocking_regressions is False


def test_live_benchmark_evaluation_blocks_on_quality_regression():
    # Quality score regressed to 0.70 (well below baseline 0.88 - 0.05 threshold)
    summary = BenchmarkSummary(
        total_workloads=10,
        total_passed=7,
        pass_rate_pct=70.0,
        total_baseline_input_tokens=1000,
        total_optimized_input_tokens=600,
        total_physical_tokens_removed=400,
        physical_reduction_pct=40.0,
        total_provider_cached_tokens=200,
        total_provider_uncached_tokens=400,
        total_output_tokens=150,
        total_baseline_cost_usd=0.05,
        total_optimized_cost_usd=0.02,
        total_cost_saved_usd=0.03,
        cost_savings_pct=60.0,
        avg_quality_score=0.70,
        max_quality_regression=0.18,
        portfolio_token_reduction_pct=50.0,
        is_40pct_claim_verified=False,
        verdict="REJECTED",
    )
    report = RegressionDetector.evaluate_live_benchmark(summary, baseline_version="v1")
    assert report.verdict == RegressionSeverity.BLOCK
    assert report.has_blocking_regressions is True
    dim_names = [r.dimension for r in report.regressions]
    assert "avg_quality_score" in dim_names
    assert "pass_rate_pct" in dim_names
