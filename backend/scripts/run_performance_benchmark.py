"""CLI Entrypoint for JakeAI Performance Regression Automation (TEST-09).

Executes performance benchmarks across 6 core scenarios (smoke or full mode),
audits against versioned baselines with explicit tolerances, generates JSON/Markdown
artifacts, and enforces CI performance gates.
"""

from __future__ import annotations

import argparse
import asyncio
import os
import sys
from pathlib import Path

if sys.stdout and hasattr(sys.stdout, "reconfigure"):
    sys.stdout.reconfigure(encoding="utf-8", errors="replace")
if sys.stderr and hasattr(sys.stderr, "reconfigure"):
    sys.stderr.reconfigure(encoding="utf-8", errors="replace")

# Add backend directory to sys.path so app imports resolve cleanly
backend_dir = Path(__file__).resolve().parent.parent
if str(backend_dir) not in sys.path:
    sys.path.insert(0, str(backend_dir))

from app.performance.contracts import RegressionVerdict  # noqa: E402
from app.performance.reporter import PerformanceReporter  # noqa: E402
from app.performance.runner import PerformanceBenchmarkRunner  # noqa: E402


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="JakeAI Automated Performance Regression System (TEST-09)"
    )
    parser.add_argument(
        "--mode",
        type=str,
        choices=["smoke", "full", "baseline-record"],
        default="smoke",
        help="Benchmark execution profile (smoke for PR/fast check, full for nightly/release, baseline-record to snapshot)",
    )
    parser.add_argument(
        "--baseline-version",
        type=str,
        default="v1",
        help="Versioned baseline identifier to audit against (default: v1)",
    )
    parser.add_argument(
        "--output-dir",
        type=str,
        default="benchmark-results",
        help="Target directory to write performance artifacts",
    )
    parser.add_argument(
        "--fail-on-regression",
        action="store_true",
        default=False,
        help="Exit with non-zero code if any blocking performance regression is detected",
    )
    parser.add_argument(
        "--concurrency-multiplier",
        type=float,
        default=1.0,
        help="Scale factor for scenario concurrency and iteration volume",
    )
    return parser.parse_args()


async def async_main() -> int:
    args = parse_args()

    print("\n" + "=" * 80)
    print("           JAKEAI PERFORMANCE REGRESSION AUTOMATION (TEST-09)")
    print("=" * 80)
    print(f"Mode                 : {args.mode.upper()}")
    print(f"Baseline Version     : {args.baseline_version}")
    print(f"Output Directory     : {args.output_dir}")
    print(f"Concurrency Scale    : {args.concurrency_multiplier}x")
    print(f"Fail on Regression   : {args.fail_on_regression}")
    print("=" * 80 + "\n")

    runner = PerformanceBenchmarkRunner(
        baseline_version=args.baseline_version,
        mode=args.mode,
        concurrency_multiplier=args.concurrency_multiplier,
    )
    reporter = PerformanceReporter(output_dir=args.output_dir)

    if args.mode == "baseline-record":
        print("Executing benchmark to record NEW versioned baseline...")
        results = await runner.run_all_scenarios(run_warmup=True)
        baseline = runner.record_as_new_baseline(
            results=results,
            version=args.baseline_version,
            description=f"Empirically recorded baseline {args.baseline_version}",
        )
        print(f"\nSuccessfully recorded and persisted baseline '{baseline.version}'!")
        return 0

    results, report = await runner.run_benchmark_and_audit()
    artifacts = reporter.save_artifacts(report, results)

    # Print markdown report to stdout
    md_report = reporter.generate_markdown_report(report, results)
    print("\n" + md_report + "\n")

    print("Saved Performance Artifacts:")
    for name, path in artifacts.items():
        print(f"  - {name:<10}: {path}")

    print("\nFinal Performance Verdict: " + report.verdict.value)

    if args.fail_on_regression and report.has_blocking_regressions:
        print("\n[ERROR] Blocking performance regression detected! Exiting with code 1.")
        return 1

    return 0


def main() -> None:
    code = asyncio.run(async_main())
    sys.exit(code)


if __name__ == "__main__":
    main()
