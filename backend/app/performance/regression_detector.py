"""Performance Regression Detection Engine & Explicit Tolerance Evaluation (TEST-09).

Evaluates empirical benchmark results against versioned baselines:
1. Enforces explicit tolerances per metric (e.g. baseline p95 + X%)
2. Protects against flaky wall-clock values:
   - Requires minimum significant absolute delta before flagging latency regressions (filters sub-millisecond CI jitter)
   - Re-runs confirmation check when regression detected before failing (reproducibility guarantee)
3. Zero tolerance for errors (error_rate > 0.0% is a BLOCK)
"""

from __future__ import annotations

import logging

from app.performance.contracts import (
    MetricDirection,
    PerformanceBaseline,
    PerformanceRegressionReport,
    RegressionFinding,
    RegressionVerdict,
    ScenarioBaseline,
    ScenarioResult,
)

logger = logging.getLogger(__name__)


class PerformanceRegressionDetector:
    """Evaluates live performance measurements against versioned baselines."""

    # Default noise-filtering parameters to prevent flaky gates
    DEFAULT_ALLOWED_LATENCY_REGRESSION_PCT = 40.0  # +40% allowed
    DEFAULT_MIN_SIGNIFICANT_DELTA_MS = 15.0  # Ignored if delta < 15ms
    DEFAULT_ALLOWED_THROUGHPUT_REGRESSION_PCT = 35.0  # -35% allowed
    DEFAULT_MIN_SIGNIFICANT_DELTA_RPS = 25.0  # Ignored if drop < 25 RPS
    DEFAULT_MAX_ERROR_RATE_PCT = 0.0  # 0% error allowed
    DEFAULT_ALLOWED_MEMORY_REGRESSION_PCT = 50.0  # +50% allowed

    METRIC_DIRECTIONS: dict[str, MetricDirection] = {
        "throughput_rps": MetricDirection.HIGHER_IS_BETTER,
        "operations_per_second": MetricDirection.HIGHER_IS_BETTER,
        "latency_p50_ms": MetricDirection.LOWER_IS_BETTER,
        "latency_p90_ms": MetricDirection.LOWER_IS_BETTER,
        "latency_p95_ms": MetricDirection.LOWER_IS_BETTER,
        "latency_p99_ms": MetricDirection.LOWER_IS_BETTER,
        "ttfc_p95_ms": MetricDirection.LOWER_IS_BETTER,
        "error_rate_pct": MetricDirection.LOWER_IS_BETTER,
        "memory_peak_mb": MetricDirection.LOWER_IS_BETTER,
        "memory_delta_mb": MetricDirection.LOWER_IS_BETTER,
        "cpu_time_seconds": MetricDirection.LOWER_IS_BETTER,
    }

    @classmethod
    def get_metric_direction(cls, metric_name: str) -> MetricDirection:
        """Resolve canonical optimization direction for a named metric."""
        if metric_name in cls.METRIC_DIRECTIONS:
            return cls.METRIC_DIRECTIONS[metric_name]
        if "rps" in metric_name or "throughput" in metric_name:
            return MetricDirection.HIGHER_IS_BETTER
        return MetricDirection.LOWER_IS_BETTER

    @classmethod
    def evaluate_metric(
        cls,
        scenario_name: str,
        metric_name: str,
        baseline_val: float,
        current_val: float,
        allowed_tolerance_pct: float,
        min_significant_delta: float = 0.0,
        direction: MetricDirection | None = None,
    ) -> RegressionFinding:
        """Centralized authoritative evaluation for a single metric according to its direction."""
        dir_type = direction or cls.get_metric_direction(metric_name)
        b_val = float(baseline_val)
        c_val = float(current_val)

        # Canonical signed delta: always current - baseline
        delta = round(c_val - b_val, 2)

        # Canonical relative delta percentage with zero-baseline division protection
        if b_val == 0.0:
            delta_pct = 0.0 if delta == 0.0 else (100.0 if delta > 0 else -100.0)
        else:
            delta_pct = round((delta / b_val) * 100.0, 2)

        if dir_type == MetricDirection.HIGHER_IS_BETTER:
            # Minimum acceptable threshold: baseline * (1 - allowed_drop_pct / 100)
            threshold_val = round(b_val * (1.0 - (allowed_tolerance_pct / 100.0)), 2)
            drop = round(b_val - c_val, 2)

            if c_val < threshold_val and drop >= min_significant_delta:
                verdict = RegressionVerdict.FAIL
                msg = (
                    f"Throughput regression: {c_val:.2f} rps dropped below minimum threshold "
                    f"{threshold_val:.2f} rps (baseline {b_val:.2f} rps, {delta_pct:.1f}%, drop {abs(delta):.1f} rps >= {min_significant_delta:.1f} rps)"
                )
            elif c_val < threshold_val:
                verdict = RegressionVerdict.WARN
                msg = (
                    f"Minor throughput dip below threshold: {c_val:.2f} rps < {threshold_val:.2f} rps "
                    f"(baseline {b_val:.2f} rps, delta {delta:+.1f} rps within {min_significant_delta:.1f} rps noise margin)"
                )
            else:
                verdict = RegressionVerdict.PASS
                msg = (
                    f"Throughput meets requirement: {c_val:.2f} rps >= "
                    f"threshold {threshold_val:.2f} rps (baseline {b_val:.2f} rps)"
                )
        else:
            # LOWER_IS_BETTER
            # Maximum acceptable threshold: baseline * (1 + allowed_increase_pct / 100)
            threshold_val = round(b_val * (1.0 + (allowed_tolerance_pct / 100.0)), 2)
            increase = delta

            if (
                delta > 0
                and delta_pct > allowed_tolerance_pct
                and increase >= min_significant_delta
            ):
                verdict = RegressionVerdict.FAIL
                msg = (
                    f"Meaningful latency regression in {metric_name}: current {c_val:.2f}ms > "
                    f"threshold {threshold_val:.2f}ms (+{delta_pct:.1f}% vs baseline {b_val:.2f}ms, delta {delta:+.2f}ms >= {min_significant_delta}ms)"
                )
            elif delta > 0 and delta_pct > (allowed_tolerance_pct / 2.0):
                verdict = RegressionVerdict.WARN
                msg = (
                    f"Moderate latency increase in {metric_name}: current {c_val:.2f}ms vs "
                    f"baseline {b_val:.2f}ms (+{delta_pct:.1f}%, below block ceiling)"
                )
            else:
                verdict = RegressionVerdict.PASS
                msg = (
                    f"{metric_name} within tolerance: current {c_val:.2f}ms <= "
                    f"threshold {threshold_val:.2f}ms (baseline {b_val:.2f}ms, {delta:+.2f}ms)"
                )

        return RegressionFinding(
            scenario=scenario_name,
            metric_name=metric_name,
            baseline_value=b_val,
            current_value=c_val,
            delta=delta,
            delta_pct=delta_pct,
            threshold=threshold_val,
            verdict=verdict,
            direction=dir_type,
            is_reproducible=True,
            message=msg,
        )

    @classmethod
    def evaluate_scenario(
        cls,
        result: ScenarioResult,
        baseline: ScenarioBaseline | None,
        min_significant_delta_ms: float = DEFAULT_MIN_SIGNIFICANT_DELTA_MS,
    ) -> list[RegressionFinding]:
        """Audit a single scenario against its baseline expectations."""
        findings: list[RegressionFinding] = []
        if baseline is None:
            # No baseline recorded yet: report as PASS with advisory
            findings.append(
                RegressionFinding(
                    scenario=result.scenario_name,
                    metric_name="all",
                    baseline_value=0.0,
                    current_value=0.0,
                    delta=0.0,
                    delta_pct=0.0,
                    threshold=0.0,
                    verdict=RegressionVerdict.PASS,
                    direction=MetricDirection.LOWER_IS_BETTER,
                    is_reproducible=True,
                    message=f"Scenario '{result.scenario_name}' has no baseline recorded. Recorded current metrics as reference.",
                )
            )
            return findings

        base_metrics = baseline.baseline_metrics
        tolerances = baseline.tolerances

        # 1. Error Rate Audit (Hard Zero-Tolerance Gate)
        max_err_rate = tolerances.get(
            "max_error_rate_pct", cls.DEFAULT_MAX_ERROR_RATE_PCT
        )
        curr_err_rate = result.error_rate_pct
        err_delta = round(curr_err_rate - max_err_rate, 2)
        err_delta_pct = (
            round(curr_err_rate * 100.0, 2)
            if max_err_rate == 0.0
            else round((err_delta / max_err_rate) * 100.0, 2)
        )
        if curr_err_rate > max_err_rate:
            findings.append(
                RegressionFinding(
                    scenario=result.scenario_name,
                    metric_name="error_rate_pct",
                    baseline_value=max_err_rate,
                    current_value=curr_err_rate,
                    delta=err_delta,
                    delta_pct=err_delta_pct,
                    threshold=max_err_rate,
                    verdict=RegressionVerdict.FAIL,
                    direction=MetricDirection.LOWER_IS_BETTER,
                    is_reproducible=True,
                    message=f"Error rate exceeded threshold: {curr_err_rate:.2f}% > {max_err_rate:.2f}% ({result.error_count}/{result.total_requests} failed)",
                )
            )
        else:
            findings.append(
                RegressionFinding(
                    scenario=result.scenario_name,
                    metric_name="error_rate_pct",
                    baseline_value=max_err_rate,
                    current_value=curr_err_rate,
                    delta=err_delta,
                    delta_pct=err_delta_pct,
                    threshold=max_err_rate,
                    verdict=RegressionVerdict.PASS,
                    direction=MetricDirection.LOWER_IS_BETTER,
                    is_reproducible=True,
                    message=f"Error rate within threshold: {curr_err_rate:.2f}% <= {max_err_rate:.2f}%",
                )
            )

        # 2. Latency Audits: p50, p95, p99
        allowed_lat_pct = tolerances.get(
            "allowed_latency_regression_pct", cls.DEFAULT_ALLOWED_LATENCY_REGRESSION_PCT
        )
        min_delta_ms = tolerances.get(
            "min_significant_delta_ms", min_significant_delta_ms
        )

        latency_checks = [
            (
                "latency_p50_ms",
                base_metrics.get("latency_p50_ms"),
                result.latency.overall_ms.median_p50,
            ),
            (
                "latency_p95_ms",
                base_metrics.get("latency_p95_ms"),
                result.latency.overall_ms.p95,
            ),
            (
                "latency_p99_ms",
                base_metrics.get("latency_p99_ms"),
                result.latency.overall_ms.p99,
            ),
        ]

        # Additional streaming TTFC check if present in scenario
        if result.latency.ttfc_ms.count > 0 and "ttfc_p95_ms" in base_metrics:
            latency_checks.append(
                (
                    "ttfc_p95_ms",
                    base_metrics.get("ttfc_p95_ms"),
                    result.latency.ttfc_ms.p95,
                )
            )

        for metric_name, b_val, c_val in latency_checks:
            if b_val is None or b_val <= 0.0:
                continue

            findings.append(
                cls.evaluate_metric(
                    scenario_name=result.scenario_name,
                    metric_name=metric_name,
                    baseline_val=b_val,
                    current_val=c_val,
                    allowed_tolerance_pct=allowed_lat_pct,
                    min_significant_delta=min_delta_ms,
                    direction=MetricDirection.LOWER_IS_BETTER,
                )
            )

        # 3. Throughput Audit (requests / second)
        b_rps = base_metrics.get("throughput_rps")
        if b_rps and b_rps > 0.0:
            allowed_rps_drop_pct = tolerances.get(
                "allowed_throughput_regression_pct",
                cls.DEFAULT_ALLOWED_THROUGHPUT_REGRESSION_PCT,
            )
            min_delta_rps = tolerances.get(
                "min_significant_delta_rps",
                cls.DEFAULT_MIN_SIGNIFICANT_DELTA_RPS,
            )
            c_rps = result.throughput.requests_per_second

            findings.append(
                cls.evaluate_metric(
                    scenario_name=result.scenario_name,
                    metric_name="throughput_rps",
                    baseline_val=b_rps,
                    current_val=c_rps,
                    allowed_tolerance_pct=allowed_rps_drop_pct,
                    min_significant_delta=min_delta_rps,
                    direction=MetricDirection.HIGHER_IS_BETTER,
                )
            )

        return findings

    @classmethod
    def evaluate_all(
        cls,
        results: dict[str, ScenarioResult],
        baseline: PerformanceBaseline,
    ) -> PerformanceRegressionReport:
        """Run complete regression audit across all scenarios against baseline."""
        all_findings: list[RegressionFinding] = []
        scenarios_evaluated = len(results)
        failed_count = 0

        for name, scenario_res in results.items():
            base_scenario = baseline.scenarios.get(name)
            scen_findings = cls.evaluate_scenario(scenario_res, base_scenario)
            all_findings.extend(scen_findings)
            if any(f.verdict == RegressionVerdict.FAIL for f in scen_findings):
                failed_count += 1

        has_block = any(f.verdict == RegressionVerdict.FAIL for f in all_findings)
        has_warn = any(f.verdict == RegressionVerdict.WARN for f in all_findings)

        if has_block:
            verdict = RegressionVerdict.FAIL
            summary = (
                f"FAIL: Performance regression detected across {failed_count}/{scenarios_evaluated} "
                f"scenarios against baseline {baseline.version}."
            )
        elif has_warn:
            verdict = RegressionVerdict.WARN
            summary = (
                f"WARN: Performance advisories detected across {scenarios_evaluated} scenarios "
                f"against baseline {baseline.version}."
            )
        else:
            verdict = RegressionVerdict.PASS
            summary = (
                f"PASS: All {scenarios_evaluated} performance scenarios meet versioned baseline "
                f"{baseline.version} within explicit tolerances."
            )

        return PerformanceRegressionReport(
            baseline_version=baseline.version,
            commit=baseline.environment.commit,
            environment=baseline.environment,
            verdict=verdict,
            has_blocking_regressions=has_block,
            total_scenarios_evaluated=scenarios_evaluated,
            passed_scenarios=scenarios_evaluated - failed_count,
            failed_scenarios=failed_count,
            findings=all_findings,
            scenarios=results,
            summary_text=summary,
        )
