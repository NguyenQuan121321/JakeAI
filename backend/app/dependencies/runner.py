"""Validation runner and orchestration engine for JakeAI Dependency Regression (TEST-10)."""

from __future__ import annotations

import datetime
import subprocess
import sys
import time
from pathlib import Path

from app.dependencies.breakage_classifier import BreakageClassifier
from app.dependencies.diff_detector import detect_git_dependency_diffs
from app.dependencies.models import (
    BreakageClassification,
    BreakageReport,
    DependencyDiff,
    ValidationSuiteResult,
)


class DependencyRegressionRunner:
    """Executes dependency regression validation gates and classifies breakages."""

    def __init__(
        self,
        backend_dir: Path | None = None,
        base_ref: str = "origin/main",
        include_bruno: bool = False,
    ) -> None:
        self.backend_dir = backend_dir or Path(__file__).resolve().parent.parent.parent
        self.root_dir = self.backend_dir.parent
        self.base_ref = base_ref
        self.include_bruno = include_bruno
        self.classifier = BreakageClassifier()

    def get_validation_suites(self) -> list[dict[str, str]]:
        """Return the complete, required automated validation suite commands per TEST-10."""
        python_exe = sys.executable
        suites = [
            {
                "name": "lint",
                "cmd": "ruff check .",
                "cwd": str(self.backend_dir),
            },
            {
                "name": "formatting",
                "cmd": "ruff format --check .",
                "cwd": str(self.backend_dir),
            },
            {
                "name": "type checking",
                "cmd": f"{python_exe} -m mypy --config-file mypy.ini app",
                "cwd": str(self.backend_dir),
            },
            {
                "name": "unit",
                "cmd": f"{python_exe} -m pytest tests/unit/ -q",
                "cwd": str(self.backend_dir),
            },
            {
                "name": "integration",
                "cmd": f"{python_exe} -m pytest tests/integration/ -q",
                "cwd": str(self.backend_dir),
            },
            {
                "name": "contract",
                "cmd": f"{python_exe} -m pytest tests/contract/ -q",
                "cwd": str(self.backend_dir),
            },
            {
                "name": "security",
                "cmd": f"{python_exe} -m pytest tests/security/ -q",
                "cwd": str(self.backend_dir),
            },
            {
                "name": "AI critical regression",
                "cmd": (
                    f"{python_exe} -m pytest tests/evals/test_eval_agent_automation.py "
                    f"tests/evals/test_eval_rag_automation.py "
                    f"tests/evals/test_eval_hallucination_automation.py -q"
                ),
                "cwd": str(self.backend_dir),
            },
            {
                "name": "E2E critical regression",
                "cmd": f'{python_exe} -m pytest tests/e2e/test_e2e_business_workflows.py -q -m "not live_external"',
                "cwd": str(self.backend_dir),
            },
        ]

        if self.include_bruno:
            suites.append(
                {
                    "name": "Bruno critical smoke",
                    "cmd": f"{python_exe} scripts/run_bruno_tests.py --suite smoke --auto-start",
                    "cwd": str(self.root_dir),
                }
            )

        return suites

    def execute_suite(
        self, suite_def: dict[str, str], dry_run: bool = False
    ) -> ValidationSuiteResult:
        """Execute a single validation suite step and record telemetry."""
        name = suite_def["name"]
        cmd = suite_def["cmd"]
        cwd = suite_def["cwd"]

        if dry_run:
            return ValidationSuiteResult(
                suite_name=name,
                command=cmd,
                exit_code=0,
                passed=True,
                duration_seconds=0.01,
                stdout_snippet="[DRY-RUN] Simulated successful run",
                stderr_snippet="",
            )

        start_time = time.perf_counter()
        try:
            proc = subprocess.run(
                cmd,
                shell=True,
                cwd=cwd,
                capture_output=True,
                text=True,
                check=False,
            )
            duration = time.perf_counter() - start_time
            passed = proc.returncode == 0
            stdout_snippet = proc.stdout[-1500:] if proc.stdout else ""
            stderr_snippet = proc.stderr[-1500:] if proc.stderr else ""

            return ValidationSuiteResult(
                suite_name=name,
                command=cmd,
                exit_code=proc.returncode,
                passed=passed,
                duration_seconds=duration,
                stdout_snippet=stdout_snippet,
                stderr_snippet=stderr_snippet,
            )
        except Exception as exc:
            duration = time.perf_counter() - start_time
            return ValidationSuiteResult(
                suite_name=name,
                command=cmd,
                exit_code=1,
                passed=False,
                duration_seconds=duration,
                stdout_snippet="",
                stderr_snippet=str(exc),
            )

    def run_validation(
        self,
        changed_diffs: list[DependencyDiff] | None = None,
        dry_run: bool = False,
    ) -> BreakageReport:
        """Execute all validation suites and produce a comprehensive BreakageReport."""
        timestamp = datetime.datetime.now(datetime.UTC).isoformat()

        if changed_diffs is None:
            changed_diffs = detect_git_dependency_diffs(
                base_ref=self.base_ref,
                backend_dir=self.backend_dir,
            )

        suite_defs = self.get_validation_suites()
        suite_results: list[ValidationSuiteResult] = []
        breakages: list[BreakageClassification] = []

        for s_def in suite_defs:
            res = self.execute_suite(s_def, dry_run=dry_run)
            suite_results.append(res)

            if not res.passed:
                # If failure occurred, classify breakage against changed dependencies
                combined_err = f"{res.stdout_snippet}\n{res.stderr_snippet}"
                if changed_diffs:
                    for diff in changed_diffs:
                        classification = self.classifier.classify_failure(
                            dependency_diff=diff,
                            affected_test=f"{res.suite_name} gate",
                            failure_output=combined_err,
                        )
                        breakages.append(classification)
                else:
                    # Generic unmapped breakage
                    from app.dependencies.manifest import resolve_category

                    diff = DependencyDiff(
                        dependency="unknown",
                        category=resolve_category("unknown"),
                        old_version="current",
                        new_version="candidate",
                        diff_type="unspecified",
                    )
                    classification = self.classifier.classify_failure(
                        dependency_diff=diff,
                        affected_test=f"{res.suite_name} gate",
                        failure_output=combined_err,
                    )
                    breakages.append(classification)

        verdict = "PASS"
        if any(not r.passed for r in suite_results):
            verdict = "REGRESSION_DETECTED"
        elif not changed_diffs:
            verdict = "PASS"

        return BreakageReport(
            timestamp=timestamp,
            base_ref=self.base_ref,
            target_ref="HEAD",
            changed_dependencies=changed_diffs,
            suite_results=suite_results,
            breakages=breakages,
            verdict=verdict,
        )
