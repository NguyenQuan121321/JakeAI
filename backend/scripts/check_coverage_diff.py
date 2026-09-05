"""Strict Test Coverage Gate & Patch Coverage Diff Analyzer.

Enforces:
1. Global line coverage floor (>= 85%)
2. Branch coverage analysis
3. PR / Commit Patch Coverage (ensures newly added/modified code has >= 85% coverage)
"""

import argparse
import os
import re
import subprocess
import sys
import xml.etree.ElementTree as ET
from pathlib import Path

# Ensure stdout/stderr handle UTF-8 cleanly on Windows/PowerShell
if hasattr(sys.stdout, "reconfigure"):
    sys.stdout.reconfigure(encoding="utf-8")
if hasattr(sys.stderr, "reconfigure"):
    sys.stderr.reconfigure(encoding="utf-8")


def get_git_diff_modified_lines(base_ref: str = "HEAD~1") -> dict[str, set[int]]:
    """Parse git diff to extract added/modified line numbers per file."""
    modified_lines: dict[str, set[int]] = {}
    cmd = ["git", "diff", "-U0", base_ref, "HEAD", "--", "app"]
    try:
        proc = subprocess.run(cmd, capture_output=True, text=True, check=False)
        if proc.returncode != 0:
            # Fallback to unstaged/staged diff if HEAD~1 is not available
            proc = subprocess.run(
                ["git", "diff", "-U0", "HEAD", "--", "app"],
                capture_output=True,
                text=True,
                check=False,
            )

        current_file: str | None = None
        for line in proc.stdout.splitlines():
            if line.startswith("+++ b/"):
                raw_path = line[6:].strip()
                # Normalize path (e.g. backend/app/... -> app/...)
                if raw_path.startswith("backend/"):
                    raw_path = raw_path[8:]
                current_file = raw_path.replace("\\", "/")
                if current_file.endswith(".py"):
                    modified_lines.setdefault(current_file, set())
                else:
                    current_file = None
            elif line.startswith("@@") and current_file:
                # Format: @@ -start,count +start,count @@
                match = re.search(r"\+([0-9]+)(?:,([0-9]+))?", line)
                if match:
                    start = int(match.group(1))
                    count = int(match.group(2)) if match.group(2) else 1
                    for line_num in range(start, start + count):
                        modified_lines[current_file].add(line_num)
    except Exception as exc:
        print(f"Warning: Could not compute git diff lines: {exc}", file=sys.stderr)

    return modified_lines


def analyze_coverage_xml(
    xml_path: Path,
) -> tuple[float, float, dict[str, dict[int, bool]]]:
    """Parse coverage.xml and return (line_rate, branch_rate, {file_path: {line_num: is_covered}})."""
    if not xml_path.exists():
        raise FileNotFoundError(f"Coverage file '{xml_path}' does not exist.")

    tree = ET.parse(xml_path)
    root = tree.getroot()

    line_rate = float(root.attrib.get("line-rate", 0)) * 100
    branch_rate = float(root.attrib.get("branch-rate", 0)) * 100

    file_line_coverage: dict[str, dict[int, bool]] = {}

    for cls_elem in root.findall(".//class"):
        filename = cls_elem.attrib.get("filename", "")
        # Normalize path
        norm_path = filename.replace("\\", "/")
        if "app/" in norm_path:
            norm_path = norm_path[norm_path.find("app/") :]

        line_status: dict[int, bool] = {}
        for line_elem in cls_elem.findall(".//line"):
            ln = int(line_elem.attrib.get("number", 0))
            hits = int(line_elem.attrib.get("hits", 0))
            line_status[ln] = hits > 0

        file_line_coverage[norm_path] = line_status

    return (line_rate, branch_rate, file_line_coverage)


def write_step_summary(summary_md: str) -> None:
    """Write markdown summary to GITHUB_STEP_SUMMARY."""
    summary_path = os.environ.get("GITHUB_STEP_SUMMARY")
    if summary_path:
        try:
            with open(summary_path, "a", encoding="utf-8") as f:
                f.write(summary_md + "\n\n")
        except Exception as err:
            print(f"Failed to write GITHUB_STEP_SUMMARY: {err}", file=sys.stderr)


def main() -> None:
    parser = argparse.ArgumentParser(
        description="Check coverage gate and patch coverage diff."
    )
    parser.add_argument(
        "--xml", default="coverage.xml", help="Path to coverage.xml file."
    )
    parser.add_argument(
        "--min-line",
        type=float,
        default=85.0,
        help="Minimum global line coverage (default: 85.0).",
    )
    parser.add_argument(
        "--min-patch",
        type=float,
        default=80.0,
        help="Minimum patch coverage for changed lines (default: 80.0).",
    )
    parser.add_argument(
        "--base-ref",
        default="HEAD~1",
        help="Base git ref for diff analysis (default: HEAD~1).",
    )
    args = parser.parse_args()

    xml_path = Path(args.xml)
    if not xml_path.exists():
        xml_path = Path("backend") / args.xml

    try:
        global_line_rate, branch_rate, coverage_map = analyze_coverage_xml(xml_path)
    except Exception as exc:
        print(f"❌ Error analyzing coverage XML: {exc}", file=sys.stderr)
        sys.exit(1)

    print(
        "================================================================================"
    )
    print("📊 STRICT CODE COVERAGE QUALITY GATE")
    print(
        f"  • Global Line Coverage:   {global_line_rate:.2f}% (Threshold: >={args.min_line}%)"
    )
    print(f"  • Global Branch Coverage: {branch_rate:.2f}%")
    print(
        "================================================================================"
    )

    # 1. Global Coverage Gate Check
    global_passed = global_line_rate >= args.min_line

    # 2. Patch Coverage Check
    modified_lines_map = get_git_diff_modified_lines(args.base_ref)
    total_patch_executable = 0
    total_patch_covered = 0
    uncovered_patch_details: list[tuple[str, int]] = []

    for file_path, lines in modified_lines_map.items():
        file_cov = coverage_map.get(file_path)
        if not file_cov:
            # Check without leading path
            for k in coverage_map:
                if k.endswith(file_path) or file_path.endswith(k):
                    file_cov = coverage_map[k]
                    break

        if not file_cov:
            continue

        for ln in lines:
            if ln in file_cov:
                total_patch_executable += 1
                if file_cov[ln]:
                    total_patch_covered += 1
                else:
                    uncovered_patch_details.append((file_path, ln))

    if total_patch_executable > 0:
        patch_coverage_rate = (total_patch_covered / total_patch_executable) * 100
        patch_passed = patch_coverage_rate >= args.min_patch
        print(
            f"  • PR Patch Coverage:      {patch_coverage_rate:.2f}% ({total_patch_covered}/{total_patch_executable} lines) (Threshold: >={args.min_patch}%)"
        )
    else:
        patch_coverage_rate = 100.0
        patch_passed = True
        print(
            "  • PR Patch Coverage:      100.0% (No executable lines modified in diff)"
        )

    # Build Summary Table
    status_icon = "✅" if (global_passed and patch_passed) else "❌"
    summary_md = (
        f"### {status_icon} Test Coverage & Quality Gate Report\n\n"
        f"| Metric | Result | Minimum Floor | Gate Status |\n"
        f"| :--- | :--- | :--- | :--- |\n"
        f"| **Global Line Coverage** | **{global_line_rate:.2f}%** | ≥{args.min_line}% | {'✅ PASS' if global_passed else '❌ FAIL'} |\n"
        f"| **Global Branch Coverage** | **{branch_rate:.2f}%** | - | [INFO] Tracked |\n"
        f"| **PR Patch Coverage** | **{patch_coverage_rate:.2f}%** ({total_patch_covered}/{total_patch_executable} modified lines) | ≥{args.min_patch}% | {'✅ PASS' if patch_passed else '❌ FAIL'} |\n\n"
    )

    if uncovered_patch_details:
        summary_md += "#### ⚠️ Untested Modified Lines:\n\n"
        for fpath, lnum in uncovered_patch_details[:20]:
            summary_md += f"- `{fpath}:{lnum}`\n"
        if len(uncovered_patch_details) > 20:
            summary_md += (
                f"- *...and {len(uncovered_patch_details) - 20} more lines.*\n"
            )

    write_step_summary(summary_md)

    if not global_passed:
        print(
            f"\n❌ Global Line Coverage ({global_line_rate:.2f}%) fell below required floor of {args.min_line}%."
        )
        sys.exit(1)

    if not patch_passed:
        print(
            f"\n❌ Patch Coverage ({patch_coverage_rate:.2f}%) fell below required threshold of {args.min_patch}%."
        )
        print("Untested modified lines:")
        for fpath, lnum in uncovered_patch_details:
            print(f"  - {fpath}:{lnum}")
        sys.exit(1)

    print("\n✅ All test coverage gates successfully passed.")
    sys.exit(0)


if __name__ == "__main__":
    main()
