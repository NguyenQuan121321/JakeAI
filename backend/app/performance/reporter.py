"""Performance Report Generator & Artifact Publisher (TEST-09).

Generates:
1. Machine-readable JSON:
   - performance-summary.json
   - performance-results.json
2. Human-readable Markdown:
   - performance-report.md
   Contains columns: Baseline | Current | Delta | Threshold | PASS/FAIL
3. Optional publishing to GITHUB_STEP_SUMMARY in CI environments.
"""

from __future__ import annotations

import json
import logging
import os
from pathlib import Path

from app.performance.contracts import (
    PerformanceRegressionReport,
    RegressionVerdict,
    ScenarioResult,
)

logger = logging.getLogger(__name__)


class PerformanceReporter:
    """Generates structured JSON artifacts and markdown report tables."""

    def __init__(self, output_dir: Path | str = "benchmark-results") -> None:
        self.output_dir = Path(output_dir)
        self.output_dir.mkdir(parents=True, exist_ok=True)

    def generate_markdown_report(
        self,
        report: PerformanceRegressionReport,
        results: dict[str, ScenarioResult],
    ) -> str:
        """Generate comprehensive GitHub-flavored markdown report table."""
        env = report.environment

        badge = {
            RegressionVerdict.PASS: "🟢 PASS",
            RegressionVerdict.WARN: "🟡 WARN",
            RegressionVerdict.FAIL: "🔴 FAIL",
        }.get(report.verdict, str(report.verdict))

        lines = [
            "# 🚀 JakeAI Performance Regression Report",
            "",
            f"**Overall Verdict**: **{badge}**",
            "",
            "## 1. Execution Metadata & Environment",
            "",
            "| Property | Value |",
            "| :--- | :--- |",
            f"| **Baseline Version** | `{report.baseline_version}` |",
            f"| **Target Commit** | `{report.commit}` |",
            f"| **Environment** | `{env.environment}` ({env.platform_name}) |",
            f"| **Python Runtime** | `Python {env.python_version}` |",
            f"| **CPU Core Count** | `{env.cpu_count} vCPUs` |",
            f"| **Dependency Hash** | `{env.dependencies_hash}` |",
            f"| **Scenarios Evaluated** | `{report.total_scenarios_evaluated}` (`{report.passed_scenarios}` Passed, `{report.failed_scenarios}` Failed) |",
            "",
            "---",
            "",
            "## 2. Benchmark Comparison Matrix",
            "",
            "| Scenario | Metric | Baseline | Current | Delta | Threshold | Verdict |",
            "| :--- | :--- | :--- | :--- | :--- | :--- | :--- |",
        ]

        for finding in report.findings:
            v_str = {
                RegressionVerdict.PASS: "✅ PASS",
                RegressionVerdict.WARN: "⚠️ WARN",
                RegressionVerdict.FAIL: "❌ FAIL",
            }.get(finding.verdict, str(finding.verdict))

            # Format numbers based on metric
            if "ms" in finding.metric_name:
                b_val = f"{finding.baseline_value:.2f} ms"
                c_val = f"{finding.current_value:.2f} ms"
                d_val = f"{finding.delta:+.2f} ms ({finding.delta_pct:+.1f}%)"
                t_val = f"≤ {finding.threshold:.2f} ms"
            elif "rps" in finding.metric_name:
                b_val = f"{finding.baseline_value:.1f} rps"
                c_val = f"{finding.current_value:.1f} rps"
                d_val = f"{finding.delta:+.1f} rps ({finding.delta_pct:+.1f}%)"
                t_val = f"≥ {finding.threshold:.1f} rps"
            elif "pct" in finding.metric_name:
                b_val = f"{finding.baseline_value:.2f}%"
                c_val = f"{finding.current_value:.2f}%"
                d_val = f"{finding.delta:+.2f}%"
                t_val = f"≤ {finding.threshold:.2f}%"
            else:
                b_val = str(finding.baseline_value)
                c_val = str(finding.current_value)
                d_val = str(finding.delta)
                t_val = str(finding.threshold)

            scen_display = f"`{finding.scenario}`"
            metric_display = f"`{finding.metric_name}`"
            lines.append(
                f"| {scen_display} | {metric_display} | {b_val} | {c_val} | {d_val} | {t_val} | {v_str} |"
            )

        lines.extend(
            [
                "",
                "---",
                "",
                "## 3. Detailed Scenario Telemetry",
                "",
                "| Scenario | Requests | Concurrency | p50 (ms) | p95 (ms) | p99 (ms) | Throughput (rps) | Peak Mem (MB) | CPU Time (s) |",
                "| :--- | :--- | :--- | :--- | :--- | :--- | :--- | :--- | :--- |",
            ]
        )

        for name, res in results.items():
            lines.append(
                f"| `{name}` | {res.total_requests} | {res.concurrency} | "
                f"{res.latency.overall_ms.median_p50:.2f} | {res.latency.overall_ms.p95:.2f} | {res.latency.overall_ms.p99:.2f} | "
                f"{res.throughput.requests_per_second:.1f} | {res.resources.peak_memory_mb:.1f} | {res.resources.cpu_time_seconds:.3f} |"
            )

        lines.extend(
            [
                "",
                "---",
                "",
                f"> **Audit Summary**: {report.summary_text}",
                "",
            ]
        )

        return "\n".join(lines)

    def save_artifacts(
        self,
        report: PerformanceRegressionReport,
        results: dict[str, ScenarioResult],
    ) -> dict[str, Path]:
        """Persist JSON artifacts and Markdown report."""
        summary_path = self.output_dir / "performance-summary.json"
        results_path = self.output_dir / "performance-results.json"
        report_path = self.output_dir / "performance-report.md"

        # 1. Save summary JSON
        summary_data = {
            "verdict": report.verdict,
            "has_blocking_regressions": report.has_blocking_regressions,
            "baseline_version": report.baseline_version,
            "commit": report.commit,
            "total_scenarios": report.total_scenarios_evaluated,
            "passed_scenarios": report.passed_scenarios,
            "failed_scenarios": report.failed_scenarios,
            "summary_text": report.summary_text,
            "findings_count": len(report.findings),
            "environment": report.environment.model_dump(),
        }
        with open(summary_path, "w", encoding="utf-8") as f:
            json.dump(summary_data, f, indent=2)

        # 2. Save full results JSON
        results_data = {
            "report": report.model_dump(),
            "scenarios": {k: v.model_dump() for k, v in results.items()},
        }
        with open(results_path, "w", encoding="utf-8") as f:
            json.dump(results_data, f, indent=2)

        # 3. Save markdown report
        md_content = self.generate_markdown_report(report, results)
        with open(report_path, "w", encoding="utf-8") as f:
            f.write(md_content)

        # 4. Export to GITHUB_STEP_SUMMARY if available
        step_summary_path = os.environ.get("GITHUB_STEP_SUMMARY")
        if step_summary_path:
            try:
                with open(step_summary_path, "a", encoding="utf-8") as f:
                    f.write("\n" + md_content + "\n")
            except OSError as exc:
                logger.debug(
                    "Failed to append performance report to GITHUB_STEP_SUMMARY (%s): %s",
                    step_summary_path,
                    exc,
                )

        return {
            "summary": summary_path,
            "results": results_path,
            "markdown": report_path,
        }
