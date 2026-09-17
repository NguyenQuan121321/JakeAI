"""Artifact generation and Markdown reporting for JakeAI Dependency Regression (TEST-10)."""

from __future__ import annotations

import json
import os
from pathlib import Path
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from app.dependencies.models import BreakageReport


class DependencyReporter:
    """Generates JSON artifacts and Markdown summaries for dependency regression audits."""

    def __init__(self, output_dir: str | Path = "reports/dependencies") -> None:
        self.output_dir = Path(output_dir)
        self.output_dir.mkdir(parents=True, exist_ok=True)

    def generate_markdown_summary(self, report: BreakageReport) -> str:
        """Construct GFM-compliant markdown report conforming to TEST-10 specification."""
        lines: list[str] = [
            "# JakeAI Dependency Regression Audit Report (TEST-10)",
            f"**Audit Timestamp**: `{report.timestamp}` | **Base Reference**: `{report.base_ref}` | **Target Reference**: `{report.target_ref}`",
            f"**Overall Verdict**: **`{report.verdict}`**",
            "",
            "---",
            "",
        ]

        if report.verdict == "PASS":
            lines.extend(
                [
                    "> [!NOTE]",
                    "> **Zero Dependency Regressions Detected**: All automated validation suites (lint, typecheck, unit, integration, contract, security, AI evals, E2E workflows, Bruno smoke) completed cleanly.",
                    "",
                ]
            )
        elif report.verdict == "REGRESSION_DETECTED":
            lines.extend(
                [
                    "> [!CAUTION]",
                    "> **Dependency Regression Detected**: One or more validation gates failed following dependency updates. Review the empirical breakage classifications below before merging.",
                    "",
                ]
            )
        else:
            lines.extend(
                [
                    "> [!NOTE]",
                    "> **No Dependency Changes Detected**: Workspace dependencies exactly match baseline.",
                    "",
                ]
            )

        # 1. Detected Dependency Changes Table
        lines.extend(
            [
                "## 1. Tracked Dependency Updates",
                "",
            ]
        )
        if report.changed_dependencies:
            lines.extend(
                [
                    "| Dependency | Category | Old Version | New Version | Delta Type | Major Bump |",
                    "|---|---|:---:|:---:|:---:|:---:|",
                ]
            )
            for diff in report.changed_dependencies:
                bump = (
                    "Yes"
                    if diff.is_major_bump
                    else ("Minor" if diff.is_minor_bump else "Patch")
                )
                lines.append(
                    f"| `{diff.dependency}` | `{diff.category.value}` | `{diff.old_version}` | `{diff.new_version}` | `{diff.diff_type}` | {bump} |"
                )
            lines.append("")
        else:
            lines.extend(
                ["_No package version deltas detected between references._", ""]
            )

        # 2. Automated Validation Suites Matrix
        lines.extend(
            [
                "## 2. Automated Validation Suite Matrix",
                "",
                "| Validation Layer | Command Executed | Duration | Status |",
                "|---|---|:---:|:---:|",
            ]
        )
        for suite in report.suite_results:
            status_badge = "PASS" if suite.passed else f"FAIL (exit {suite.exit_code})"
            lines.append(
                f"| **{suite.suite_name}** | `{suite.command}` | {suite.duration_seconds:.2f}s | `{status_badge}` |"
            )
        lines.append("")

        # 3. Breakage Classifications
        if report.breakages:
            lines.extend(
                [
                    "## 3. Empirical Breakage Classifications",
                    "",
                    "The following breakages were classified using deterministic root cause analysis. Arbitrary pinning without evidence is strictly prohibited.",
                    "",
                ]
            )
            for idx, breakage in enumerate(report.breakages, 1):
                b_dict = breakage.to_formatted_dict()
                lines.extend(
                    [
                        f"### Breakage #{idx}: `{breakage.dependency}` ({breakage.old_version} -> {breakage.new_version})",
                        "",
                        "| Specification Field | Diagnostic Finding |",
                        "|---|---|",
                        f"| **dependency** | `{b_dict['dependency']}` |",
                        f"| **old version** | `{b_dict['old version']}` |",
                        f"| **new version** | `{b_dict['new version']}` |",
                        f"| **failure** | `{b_dict['failure']}` |",
                        f"| **affected test** | `{b_dict['affected test']}` |",
                        f"| **root cause** | {b_dict['root cause']} |",
                        f"| **breaking API if confirmed** | `{b_dict['breaking API if confirmed']}` |",
                        f"| **rollback/revert recommendation** | {b_dict['rollback/revert recommendation']} |",
                        "",
                    ]
                )
                if breakage.evidence:
                    lines.extend(
                        [
                            "<details>",
                            "<summary>Click to expand empirical diagnostic trace</summary>",
                            "",
                            "```text",
                            breakage.evidence.strip(),
                            "```",
                            "</details>",
                            "",
                        ]
                    )

        return "\n".join(lines)

    def save_artifacts(self, report: BreakageReport) -> dict[str, Path]:
        """Save JSON and Markdown report artifacts to the output directory."""
        json_path = self.output_dir / "breakage-report.json"
        md_path = self.output_dir / "dependency-regression-report.md"

        # Save JSON
        json_path.write_text(
            json.dumps(report.model_dump(), indent=2), encoding="utf-8"
        )

        # Save Markdown
        md_content = self.generate_markdown_summary(report)
        md_path.write_text(md_content, encoding="utf-8")

        # Append to GitHub Actions step summary if running in CI
        step_summary = os.environ.get("GITHUB_STEP_SUMMARY")
        if step_summary:
            try:
                with open(step_summary, "a", encoding="utf-8") as f:
                    f.write("\n" + md_content + "\n")
            except Exception:
                pass

        return {
            "json": json_path,
            "markdown": md_path,
        }
