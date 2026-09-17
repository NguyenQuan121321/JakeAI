"""JakeAI Flaky Test Tracker and Execution Guard (TEST-11).

Enforces strict CI reliability invariants:
1. Zero infinite or unmonitored retries (max 1 retry for designated tests).
2. Explicit FLAKY tracking: any test passing on retry is recorded as FLAKY,
   never masked as a clean PASS.
3. Strict gate enforcement: on Main and Release gates, --fail-on-flaky
   strictly blocks the pipeline.
"""

from __future__ import annotations

import argparse
import json
import os
import subprocess  # nosec: B404
import sys
import time
from dataclasses import asdict, dataclass
from pathlib import Path

# Ensure UTF-8 output across Windows and Linux
if hasattr(sys.stdout, "reconfigure"):
    sys.stdout.reconfigure(encoding="utf-8", errors="replace")
if hasattr(sys.stderr, "reconfigure"):
    sys.stderr.reconfigure(encoding="utf-8", errors="replace")


@dataclass
class FlakyOccurrence:
    """Record of an unstable test that passed only upon retry."""

    test_id: str
    file_path: str
    attempt_1_status: str
    attempt_1_error: str
    attempt_2_status: str
    timestamp: str
    duration_ms: float = 0.0


@dataclass
class FlakyReport:
    """Aggregated flaky test audit ledger."""

    total_executed: int
    attempt_1_passed: int
    attempt_1_failed: int
    retried_count: int
    flaky_count: int
    permanent_failures: int
    is_clean: bool
    flaky_tests: list[FlakyOccurrence]


def parse_pytest_junit_failures(junit_path: Path) -> dict[str, str]:
    """Extract failed test names and failure messages from JUnit XML."""
    failures: dict[str, str] = {}
    if not junit_path.is_file():
        return failures

    try:
        import xml.etree.ElementTree as ET  # nosec: B405

        tree = ET.parse(junit_path)  # nosec: B314
        root = tree.getroot()
        for tc in root.iter("testcase"):
            classname = tc.get("classname", "")
            name = tc.get("name", "")
            test_id = f"{classname}::{name}" if classname else name
            failure = tc.find("failure")
            error = tc.find("error")
            if failure is not None:
                failures[test_id] = (
                    failure.get("message") or failure.text or "AssertionError"
                )
            elif error is not None:
                failures[test_id] = error.get("message") or error.text or "Error"
    except (ET.ParseError, OSError) as exc:
        print(f"[WARN] Failed parsing JUnit XML {junit_path}: {exc}", file=sys.stderr)

    return failures


def run_pytest_command(
    pytest_args: list[str],
    junit_report_path: Path,
    cwd: Path,
) -> tuple[int, str]:
    """Execute pytest with JUnit XML reporting."""
    junit_report_path.parent.mkdir(parents=True, exist_ok=True)
    cmd = [
        sys.executable,
        "-m",
        "pytest",
        f"--junitxml={junit_report_path}",
        *pytest_args,
    ]

    proc = subprocess.run(  # nosec: B603
        cmd,
        cwd=str(cwd),
        capture_output=True,
        text=True,
        encoding="utf-8",
        errors="replace",
        check=False,
    )
    combined_output = (proc.stdout or "") + ("\n" + proc.stderr if proc.stderr else "")
    return proc.returncode, combined_output


def track_and_run(
    pytest_args: list[str],
    cwd: Path,
    output_dir: Path,
    max_retries: int = 1,
    fail_on_flaky: bool = False,
) -> tuple[int, FlakyReport]:
    """Run pytest suite, perform controlled single retry on failures, and track flakiness."""
    output_dir.mkdir(parents=True, exist_ok=True)
    attempt1_xml = output_dir / "attempt1_junit.xml"
    attempt2_xml = output_dir / "attempt2_junit.xml"
    ledger_path = output_dir / "flaky-tests.json"

    print(f"[*] Executing Test Run (Attempt 1): pytest {' '.join(pytest_args)}")
    code_1, out_1 = run_pytest_command(pytest_args, attempt1_xml, cwd)

    failures_1 = parse_pytest_junit_failures(attempt1_xml)
    flaky_occurrences: list[FlakyOccurrence] = []

    if code_1 == 0 or not failures_1:
        print("[✓] Attempt 1 completed with 100% success. Zero flaky tests detected.")
        report = FlakyReport(
            total_executed=1,
            attempt_1_passed=1,
            attempt_1_failed=0,
            retried_count=0,
            flaky_count=0,
            permanent_failures=0,
            is_clean=True,
            flaky_tests=[],
        )
        save_flaky_ledger(report, ledger_path)
        print(out_1)
        return 0, report

    print(f"[!] Attempt 1 observed {len(failures_1)} failure(s).")
    print(out_1)

    if max_retries <= 0:
        print("[i] Retries disabled. Recording permanent failures without retry.")
        report = FlakyReport(
            total_executed=len(failures_1),
            attempt_1_passed=0,
            attempt_1_failed=len(failures_1),
            retried_count=0,
            flaky_count=0,
            permanent_failures=len(failures_1),
            is_clean=False,
            flaky_tests=[],
        )
        save_flaky_ledger(report, ledger_path)
        return code_1, report

    # Controlled single retry of failed items
    failed_test_targets = list(failures_1.keys())
    print(
        f"[*] Attempting controlled single retry for {len(failed_test_targets)} failed test(s)..."
    )

    # Construct targeted rerun arguments
    retry_args = [
        "-v",
        "-k",
        " or ".join(t.split("::")[-1] for t in failed_test_targets),
    ]
    code_2, _out_2 = run_pytest_command(retry_args, attempt2_xml, cwd)
    failures_2 = parse_pytest_junit_failures(attempt2_xml)

    now_iso = time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime())

    for test_id, err_msg in failures_1.items():
        if test_id not in failures_2:
            # Passed on retry -> THIS IS A FLAKY TEST
            print(f"[FLAKY] Test {test_id} failed on run 1, passed on run 2!")
            flaky_occurrences.append(
                FlakyOccurrence(
                    test_id=test_id,
                    file_path=test_id.split("::")[0] if "::" in test_id else "unknown",
                    attempt_1_status="FAILED",
                    attempt_1_error=err_msg[:300],
                    attempt_2_status="PASSED",
                    timestamp=now_iso,
                )
            )

    permanent_fails = len(failures_2)
    flaky_count = len(flaky_occurrences)
    is_clean = (flaky_count == 0) and (permanent_fails == 0)

    report = FlakyReport(
        total_executed=len(failures_1),
        attempt_1_passed=0,
        attempt_1_failed=len(failures_1),
        retried_count=len(failed_test_targets),
        flaky_count=flaky_count,
        permanent_failures=permanent_fails,
        is_clean=is_clean,
        flaky_tests=flaky_occurrences,
    )
    save_flaky_ledger(report, ledger_path)

    # Publish step summary if running in GitHub Actions
    publish_github_summary(report)

    if permanent_fails > 0:
        print(f"\n[X] {permanent_fails} test(s) failed permanently.")
        return code_2 if code_2 != 0 else 1, report

    if flaky_count > 0:
        print(f"\n[!] {flaky_count} FLAKY test(s) detected.")
        if fail_on_flaky:
            print(
                "[X] --fail-on-flaky enforced: Failing CI pipeline due to unstable tests."
            )
            return 2, report
        print("[WARN] Flaky tests recorded in ledger. Proceeding with warning.")
        return 0, report

    return 0, report


def save_flaky_ledger(report: FlakyReport, target_path: Path) -> None:
    """Serialize the flaky audit report to JSON."""
    target_path.parent.mkdir(parents=True, exist_ok=True)
    with open(target_path, "w", encoding="utf-8") as f:
        json.dump(asdict(report), f, indent=2)


def publish_github_summary(report: FlakyReport) -> None:
    """Write markdown summary to GITHUB_STEP_SUMMARY if available."""
    summary_file = os.environ.get("GITHUB_STEP_SUMMARY")
    if not summary_file or not report.flaky_tests:
        return

    md_lines = [
        "### ⚠️ Flaky Test Detection Report (TEST-11)",
        "",
        f"- **Flaky Tests Detected**: `{report.flaky_count}`",
        f"- **Permanent Failures**: `{report.permanent_failures}`",
        "",
        "| Flaky Test | File | Attempt 1 Error | Attempt 2 Status |",
        "| :--- | :--- | :--- | :---: |",
    ]
    for ft in report.flaky_tests:
        md_lines.append(
            f"| `{ft.test_id}` | `{ft.file_path}` | `{ft.attempt_1_error.replace('|', '/')}` | `{ft.attempt_2_status}` |"
        )
    md_lines.append("")

    try:
        with open(summary_file, "a", encoding="utf-8") as f:
            f.write("\n".join(md_lines) + "\n")
    except OSError as err:
        print(f"[WARN] Could not write to GITHUB_STEP_SUMMARY: {err}", file=sys.stderr)


def main() -> int:
    parser = argparse.ArgumentParser(
        description="JakeAI Flaky Test Tracker & CI Execution Guard (TEST-11)"
    )
    parser.add_argument(
        "--output-dir",
        type=str,
        default="reports/flaky",
        help="Directory to store flaky test reports and XML artifacts",
    )
    parser.add_argument(
        "--max-retries",
        type=int,
        default=1,
        help="Maximum allowed retry attempts (default: 1, strict ceiling)",
    )
    parser.add_argument(
        "--fail-on-flaky",
        action="store_true",
        default=False,
        help="Block CI with exit code 2 if any flaky test is observed",
    )
    parser.add_argument(
        "--check-ledger",
        type=str,
        default=None,
        help="Audit existing flaky ledger JSON file and exit non-zero if flakiness exists",
    )
    parser.add_argument(
        "pytest_args",
        nargs=argparse.REMAINDER,
        help="Pytest arguments to execute",
    )

    args = parser.parse_args()

    if args.check_ledger:
        ledger_file = Path(args.check_ledger)
        if not ledger_file.is_file():
            print(f"[✓] Ledger {ledger_file} not found; zero recorded flaky tests.")
            return 0
        with open(ledger_file, encoding="utf-8") as f:
            data = json.load(f)
        flaky_count = data.get("flaky_count", 0)
        if flaky_count > 0:
            print(f"[X] Ledger {ledger_file} contains {flaky_count} flaky test(s).")
            return 2 if args.fail_on_flaky else 0
        print(f"[✓] Ledger {ledger_file} clean (0 flaky tests).")
        return 0

    cwd = Path.cwd()
    output_path = cwd / args.output_dir
    pytest_args = args.pytest_args
    if pytest_args and pytest_args[0] == "--":
        pytest_args = pytest_args[1:]

    if not pytest_args:
        pytest_args = ["tests/unit"]

    code, _ = track_and_run(
        pytest_args=pytest_args,
        cwd=cwd,
        output_dir=output_path,
        max_retries=min(
            args.max_retries, 1
        ),  # Invariant: Never allow infinite or > 1 retries
        fail_on_flaky=args.fail_on_flaky,
    )
    return code


if __name__ == "__main__":
    sys.exit(main())
