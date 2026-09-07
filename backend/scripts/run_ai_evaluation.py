"""CLI Entrypoint for Phase 00 AI Evaluation Benchmark Suite.

Executes multi-workload benchmark, generates machine-readable JSON artifacts in benchmark-results/,
prints human-readable summary table, and publishes markdown summary to GITHUB_STEP_SUMMARY.
"""

import argparse
import asyncio
import os
import sys
from pathlib import Path

# Add backend directory to sys.path so app imports resolve
backend_dir = Path(__file__).resolve().parent.parent
if str(backend_dir) not in sys.path:
    sys.path.insert(0, str(backend_dir))

from app.evals.benchmark_runner import BenchmarkRunner  # noqa: E402


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="JakeAI AI Evaluation Benchmark Runner"
    )
    parser.add_argument(
        "--dataset",
        type=str,
        default=None,
        help="Path to evaluation workloads dataset JSON",
    )
    parser.add_argument(
        "--output-dir",
        type=str,
        default="benchmark-results",
        help="Directory to save machine-readable results",
    )
    parser.add_argument(
        "--min-reduction",
        type=float,
        default=40.0,
        help="Minimum portfolio token reduction percentage gate (default: 40.0%%)",
    )
    parser.add_argument(
        "--max-regression",
        type=float,
        default=0.05,
        help="Maximum allowable quality regression vs baseline (default: 0.05)",
    )
    return parser.parse_args()


def main() -> None:
    args = parse_args()
    runner = BenchmarkRunner(dataset_path=args.dataset, output_dir=args.output_dir)

    print("\nStarting Phase 00 AI Evaluation Benchmark...")
    print(f"Dataset Path : {runner.dataset_path}")
    print(f"Output Dir   : {runner.output_dir}")
    print(f"Target Floor : >= {args.min_reduction}% Portfolio Token Reduction")
    print(f"Quality Gate : Max Regression <= {args.max_regression}\n")

    summary, records, quality_results, cost_meas = asyncio.run(
        runner.run_portfolio_benchmark()
    )
    artifact_paths = runner.save_artifacts(summary, records, quality_results, cost_meas)

    report_text = runner.format_human_readable_report(summary, records)
    print(report_text)
    print("\nSaved Machine-Readable Artifacts:")
    for name, path in artifact_paths.items():
        print(f"  - {name:<10}: {path}")

    # Write Markdown summary to GITHUB_STEP_SUMMARY if present
    step_summary = os.environ.get("GITHUB_STEP_SUMMARY")
    if step_summary:
        md_lines = [
            "## 🤖 Phase 00 — AI Evaluation Benchmark Results",
            "",
            f"**Verdict**: **{summary.verdict}**",
            "",
            "| Metric | Measured Value | Requirement / Target |",
            "| :--- | :--- | :--- |",
            f"| **Portfolio Net Token Reduction** | **{summary.portfolio_token_reduction_pct:.2f}%** | ≥ {args.min_reduction}% |",
            f"| **Workload Pass Rate** | {summary.pass_rate_pct}% ({summary.total_passed}/{summary.total_workloads}) | 100% |",
            f"| **Average Quality Score** | {summary.avg_quality_score:.4f} | ≥ 0.8500 |",
            f"| **Max Quality Regression** | {summary.max_quality_regression:.4f} | ≤ {args.max_regression} |",
            f"| **Baseline Input Tokens** | {summary.total_baseline_input_tokens:,} tokens | Reference |",
            f"| **Optimized Input Tokens** | {summary.total_optimized_input_tokens:,} tokens | Optimized |",
            f"| **Physical Tokens Removed** | {summary.total_physical_tokens_removed:,} tokens ({summary.physical_reduction_pct}%) | Context Pruning |",
            f"| **Provider Cached Tokens** | {summary.total_provider_cached_tokens:,} tokens | Upstream KV |",
            f"| **Total Baseline Cost** | ${summary.total_baseline_cost_usd:.6f} USD | Unoptimized |",
            f"| **Total Incurred Cost Saved** | ${summary.total_cost_saved_usd:.6f} USD ({summary.cost_savings_pct}%) | FinOps Savings |",
            "",
            "### Workload Breakdown",
            "",
            "| Workload ID | Type | Raw Tokens | Opt Tokens | Saved % | Quality Score | Status |",
            "| :--- | :--- | :--- | :--- | :--- | :--- | :--- |",
        ]
        for r in records:
            pct = round((r.tokens_saved / max(1, r.raw_input_tokens)) * 100.0, 1)
            status_badge = "✅ PASS" if r.passed else "❌ FAIL"
            md_lines.append(
                f"| `{r.workload_id}` | `{r.workload_type}` | {r.raw_input_tokens} | {r.optimized_input_tokens} | {pct}% | {r.quality_score:.4f} | {status_badge} |"
            )

        with open(step_summary, "a", encoding="utf-8") as f:
            f.write("\n".join(md_lines) + "\n\n")

    # Gate Evaluation
    if not summary.is_40pct_claim_verified:
        print(
            "\n[ERROR] Portfolio benchmark gate FAILED. Conditions not satisfied.",
            file=sys.stderr,
        )
        sys.exit(1)

    if summary.max_quality_regression > args.max_regression:
        print(
            f"\n[ERROR] Quality regression {summary.max_quality_regression:.4f} exceeded threshold {args.max_regression}.",
            file=sys.stderr,
        )
        sys.exit(1)

    print("\n[SUCCESS] Phase 00 AI Evaluation Benchmark Passed all gates.")
    sys.exit(0)


if __name__ == "__main__":
    main()
