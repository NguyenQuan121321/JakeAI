"""JakeAI CI Test Failure & Forensic Reporter (TEST-11).

Consolidates all CI test outcomes across all layers (Unit, Integration, Contract,
Security, AI Evals, E2E, Bruno CLI, Performance, Dependencies, and Flaky Tests).

Emits structured reporting with mandatory forensic fields:
- layer
- test
- file
- scenario
- dependency
- log
- artifact
"""

from __future__ import annotations

import argparse
import json
import os
import sys
import xml.etree.ElementTree as ET  # nosec: B405
from dataclasses import asdict, dataclass
from pathlib import Path

# Ensure UTF-8 console output
if hasattr(sys.stdout, "reconfigure"):
    sys.stdout.reconfigure(encoding="utf-8", errors="replace")
if hasattr(sys.stderr, "reconfigure"):
    sys.stderr.reconfigure(encoding="utf-8", errors="replace")


@dataclass
class FailureItem:
    """Individual test failure with full forensic classification."""

    layer: str
    test: str
    file: str
    scenario: str
    dependency: str
    log: str
    artifact: str
    status: str = "FAILED"  # FAILED, FLAKY, BLOCKED


@dataclass
class FailureSummaryReport:
    """Aggregated CI execution failure report."""

    total_evaluated: int
    total_passed: int
    total_failed: int
    total_flaky: int
    total_blocked: int
    is_green: bool
    failures: list[FailureItem]


def classify_layer_from_path(file_path: str) -> str:
    """Classify testing layer based on path or dotted test module."""
    norm = file_path.replace("\\", "/").lower()
    if "tests/unit/" in norm or "tests.unit." in norm:
        return "Unit"
    if "tests/integration/" in norm or "tests.integration." in norm:
        return "Integration"
    if "tests/contract/" in norm or "tests.contract." in norm:
        return "Contract"
    if "tests/security/" in norm or "tests.security." in norm:
        return "Security"
    if "tests/evals/" in norm or "tests.evals." in norm or "benchmark" in norm:
        return "AI / Evaluation"
    if "tests/e2e/" in norm or "tests.e2e." in norm:
        return "E2E Workflow"
    if "tests/performance/" in norm or "tests.performance." in norm:
        return "Performance"
    if "bruno" in norm:
        return "Bruno CLI"
    if "dependencies" in norm or "dependency" in norm:
        return "Dependency"
    return "Core / Platform"


def infer_dependency_from_context(test_name: str, file_path: str, log_msg: str) -> str:
    """Infer the underlying technical dependency involved in the failure."""
    combined = f"{test_name} {file_path} {log_msg}".lower()
    deps: list[str] = []
    if "redis" in combined:
        deps.append("Redis")
    if "qdrant" in combined or "vector" in combined:
        deps.append("Qdrant")
    if "finnapigo" in combined or "jwt" in combined or "token" in combined:
        deps.append("FinnApiGo / Auth")
    if "fastembed" in combined or "onnx" in combined or "embedding" in combined:
        deps.append("FastEmbed (ONNX)")
    if "openai" in combined or "gemini" in combined or "provider" in combined:
        deps.append("LLM Provider")

    return ", ".join(deps) if deps else "None (In-Memory)"


def extract_scenario_name(test_name: str) -> str:
    """Extract human-readable scenario from test identifier."""
    clean = test_name.split("::")[-1]
    if clean.startswith("test_"):
        clean = clean[5:]
    return clean.replace("_", " ").capitalize()


def parse_junit_xml_failures(xml_path: Path) -> list[FailureItem]:
    """Parse JUnit XML file for testcase failures."""
    items: list[FailureItem] = []
    if not xml_path.is_file():
        return items

    try:
        tree = ET.parse(xml_path)  # nosec: B314
        root = tree.getroot()
        for tc in root.iter("testcase"):
            failure = tc.find("failure")
            error = tc.find("error")
            skipped = tc.find("skipped")
            node = failure if failure is not None else error

            classname = tc.get("classname", "")
            name = tc.get("name", "")
            file_attr = tc.get("file", classname)

            if node is not None:
                err_text = node.text or node.get("message") or "Unknown error"
                first_line = (
                    err_text.strip().splitlines()[0] if err_text else "Test failure"
                )
                layer = classify_layer_from_path(file_attr)
                dep = infer_dependency_from_context(name, file_attr, err_text)
                scenario = extract_scenario_name(name)

                items.append(
                    FailureItem(
                        layer=layer,
                        test=name,
                        file=file_attr,
                        scenario=scenario,
                        dependency=dep,
                        log=first_line[:250],
                        artifact=str(xml_path.name),
                        status="FAILED",
                    )
                )
            elif (
                skipped is not None
                and "blocked" in (skipped.get("message") or "").lower()
            ):
                items.append(
                    FailureItem(
                        layer=classify_layer_from_path(file_attr),
                        test=name,
                        file=file_attr,
                        scenario=extract_scenario_name(name),
                        dependency=infer_dependency_from_context(
                            name, file_attr, skipped.get("message", "")
                        ),
                        log=skipped.get("message", "Dependency blocked")[:250],
                        artifact=str(xml_path.name),
                        status="BLOCKED",
                    )
                )
    except (ET.ParseError, OSError) as exc:
        print(f"[WARN] Failed parsing {xml_path}: {exc}", file=sys.stderr)

    return items


def parse_bruno_json_failures(json_path: Path) -> list[FailureItem]:
    """Parse Bruno results JSON report for request failures."""
    items: list[FailureItem] = []
    if not json_path.is_file():
        return items

    try:
        with open(json_path, encoding="utf-8") as f:
            data = json.load(f)

        for item in data.get("items", []):
            status = item.get("status")
            if status in ("failed", "blocked"):
                target = item.get("target", "")
                name = item.get("name", "")
                err_msg = item.get("error_message") or "Bruno assertion failure"
                dep = (
                    "FinnApiGo"
                    if item.get("is_external")
                    else infer_dependency_from_context(name, target, err_msg)
                )

                items.append(
                    FailureItem(
                        layer="Bruno CLI",
                        test=name,
                        file=target,
                        scenario=f"HTTP Request: {name}",
                        dependency=dep,
                        log=err_msg[:250],
                        artifact="bruno-results.json",
                        status="BLOCKED" if status == "blocked" else "FAILED",
                    )
                )
    except (json.JSONDecodeError, OSError) as exc:
        print(f"[WARN] Failed reading Bruno report {json_path}: {exc}", file=sys.stderr)

    return items


def parse_flaky_ledger(json_path: Path) -> list[FailureItem]:
    """Parse flaky tests JSON ledger."""
    items: list[FailureItem] = []
    if not json_path.is_file():
        return items

    try:
        with open(json_path, encoding="utf-8") as f:
            data = json.load(f)

        for item in data.get("flaky_tests", []):
            test_id = item.get("test_id", "")
            file_path = item.get("file_path", "")
            err_msg = item.get("attempt_1_error", "")
            layer = classify_layer_from_path(file_path)
            dep = infer_dependency_from_context(test_id, file_path, err_msg)

            items.append(
                FailureItem(
                    layer=layer,
                    test=test_id,
                    file=file_path,
                    scenario="Flaky Retry (Attempt 1 Failed -> Attempt 2 Passed)",
                    dependency=dep,
                    log=f"Unstable: {err_msg[:200]}",
                    artifact="flaky-tests.json",
                    status="FLAKY",
                )
            )
    except (json.JSONDecodeError, OSError) as exc:
        print(f"[WARN] Failed reading flaky ledger {json_path}: {exc}", file=sys.stderr)

    return items


def collect_all_ci_failures(search_dirs: list[Path]) -> FailureSummaryReport:
    """Scan directory trees for all failure artifacts."""
    all_failures: list[FailureItem] = []

    for d in search_dirs:
        if not d.is_dir():
            continue

        # 1. JUnit XML files
        for xml_file in d.glob("**/*.xml"):
            all_failures.extend(parse_junit_xml_failures(xml_file))

        # 2. Bruno JSON files
        for bruno_json in d.glob("**/bruno-results.json"):
            all_failures.extend(parse_bruno_json_failures(bruno_json))

        # 3. Flaky ledgers
        for flaky_json in d.glob("**/flaky-tests.json"):
            all_failures.extend(parse_flaky_ledger(flaky_json))

    failed_count = sum(1 for f in all_failures if f.status == "FAILED")
    flaky_count = sum(1 for f in all_failures if f.status == "FLAKY")
    blocked_count = sum(1 for f in all_failures if f.status == "BLOCKED")

    return FailureSummaryReport(
        total_evaluated=len(all_failures),
        total_passed=0,
        total_failed=failed_count,
        total_flaky=flaky_count,
        total_blocked=blocked_count,
        is_green=(failed_count == 0 and flaky_count == 0),
        failures=all_failures,
    )


def generate_markdown_report(report: FailureSummaryReport) -> str:
    """Render comprehensive Markdown summary table."""
    status_badge = (
        "🟢 **ALL CI GATES GREEN**"
        if report.is_green
        else "🔴 **CI FAILURES DETECTED**"
    )
    lines = [
        "## 🛡️ JakeAI CI Test Failure & Forensic Analysis Summary (TEST-12)",
        "",
        f"- **Overall CI Status**: {status_badge}",
        f"- **Total Issues Classified**: `{len(report.failures)}`",
        f"- **Hard Failures**: `✗ {report.total_failed}` | **Flaky Tests**: `⚠️ {report.total_flaky}` | **Blocked (External)**: `⏸ {report.total_blocked}`",
        "",
    ]

    if not report.failures:
        lines.extend(
            [
                "> [!TIP]",
                "> **100% Clean Pass**: Zero test failures, zero schema drifts, and zero flaky test retries detected across all CI execution layers.",
                "",
            ]
        )
        return "\n".join(lines)

    lines.extend(
        [
            "### Forensic Failure Matrix",
            "",
            "| Status | Layer | Test | File | Scenario | Dependency | Failure Snippet | Artifact |",
            "| :---: | :--- | :--- | :--- | :--- | :--- | :--- | :--- |",
        ]
    )

    for f in report.failures:
        icon = (
            "✗ FAIL"
            if f.status == "FAILED"
            else ("⚠️ FLAKY" if f.status == "FLAKY" else "⏸ BLOCKED")
        )
        sanitized_log = f.log.replace("|", "/").replace("\n", " ")
        lines.append(
            f"| {icon} | `{f.layer}` | `{f.test}` | `{f.file}` | {f.scenario} | `{f.dependency}` | {sanitized_log} | `{f.artifact}` |"
        )

    lines.append("")
    return "\n".join(lines)


def print_console_matrix(report: FailureSummaryReport) -> None:
    """Print high-contrast console matrix."""
    print("\n" + "=" * 90)
    print("         JAKEAI CI TEST FORENSIC FAILURE SUMMARY (TEST-12)")
    print("=" * 90)
    print(
        f" Status         : {'✓ GREEN (All Passed)' if report.is_green else '✗ RED (Issues Detected)'}"
    )
    print(f" Hard Failures  : {report.total_failed}")
    print(f" Flaky Tests    : {report.total_flaky}")
    print(f" Blocked Tests  : {report.total_blocked}")
    print("-" * 90)

    if not report.failures:
        print(" [✓] Zero failures across all CI layers.")
    else:
        for f in report.failures:
            print(f" [{f.status}] Layer: {f.layer:<12} | Test: {f.test}")
            print(f"   File       : {f.file}")
            print(f"   Scenario   : {f.scenario}")
            print(f"   Dependency : {f.dependency}")
            print(f"   Log        : {f.log[:120]}")
            print(f"   Artifact   : {f.artifact}")
            print("-" * 90)
    print("=" * 90 + "\n")


def main() -> int:
    parser = argparse.ArgumentParser(
        description="JakeAI CI Test Failure & Forensic Reporter (TEST-11)"
    )
    parser.add_argument(
        "--report-dirs",
        nargs="+",
        default=[
            "reports",
            "benchmark-results",
            "backend/reports",
            "backend/benchmark-results",
        ],
        help="Directories to search for test reports and artifacts",
    )
    parser.add_argument(
        "--output-dir",
        type=str,
        default="reports/summary",
        help="Directory to save aggregated failure summaries",
    )
    parser.add_argument(
        "--fail-on-flaky",
        action="store_true",
        default=False,
        help="Fail with exit code 2 if any flaky test is observed",
    )
    parser.add_argument(
        "--fail-on-blocked",
        action="store_true",
        default=False,
        help="Fail with exit code 3 if any test is blocked (for strict release pipelines)",
    )

    args = parser.parse_args()

    repo_root = Path.cwd()
    search_dirs = [(repo_root / d).resolve() for d in args.report_dirs]
    out_dir = (repo_root / args.output_dir).resolve()
    out_dir.mkdir(parents=True, exist_ok=True)

    report = collect_all_ci_failures(search_dirs)

    # Output files
    json_path = out_dir / "ci-failure-summary.json"
    md_path = out_dir / "ci-failure-summary.md"

    with open(json_path, "w", encoding="utf-8") as f:
        json.dump(asdict(report), f, indent=2)

    md_content = generate_markdown_report(report)
    with open(md_path, "w", encoding="utf-8") as f:
        f.write(md_content)

    step_summary = os.environ.get("GITHUB_STEP_SUMMARY")
    if step_summary:
        try:
            with open(step_summary, "a", encoding="utf-8") as f:
                f.write(md_content + "\n\n")
        except OSError as err:
            print(
                f"[WARN] Could not write to GITHUB_STEP_SUMMARY: {err}", file=sys.stderr
            )

    print_console_matrix(report)
    print(f"[✓] Forensic reports saved to:\n  - {json_path}\n  - {md_path}\n")

    if report.total_failed > 0:
        return 1
    if args.fail_on_flaky and report.total_flaky > 0:
        return 2
    if args.fail_on_blocked and report.total_blocked > 0:
        return 3
    return 0


if __name__ == "__main__":
    sys.exit(main())
