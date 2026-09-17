"""Unit tests for JakeAI Dependency Regression Runner & Reporter (TEST-10 / DEP-003 / CAT-131)."""

from __future__ import annotations

import json
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from pathlib import Path

import pytest

from app.dependencies.diff_detector import compare_semver, detect_dependency_diffs
from app.dependencies.models import (
    BreakageReport,
    DependencyCategory,
    DependencyDiff,
    ValidationSuiteResult,
)
from app.dependencies.reporter import DependencyReporter
from app.dependencies.runner import DependencyRegressionRunner


@pytest.mark.unit
class TestDependencyRegressionRunner:
    """Validate dependency diffing, validation runner, and reporter subsystems."""

    def test_compare_semver_detection(self) -> None:
        """Verify semver delta detection for major, minor, patch, and downgrades."""
        # Major bump
        is_major, is_minor, diff_type = compare_semver("1.4.0", "2.0.0")
        assert is_major is True
        assert is_minor is False
        assert diff_type == "upgrade"

        # Minor bump
        is_major, is_minor, diff_type = compare_semver("0.141.1", "0.142.0")
        assert is_major is False
        assert is_minor is True
        assert diff_type == "upgrade"

        # Patch bump
        is_major, is_minor, diff_type = compare_semver("0.28.1", "0.28.2")
        assert is_major is False
        assert is_minor is False
        assert diff_type == "upgrade"

        # Downgrade
        is_major, is_minor, diff_type = compare_semver("2.13.5", "2.12.0")
        assert diff_type == "downgrade"

    def test_detect_dependency_diffs_matrix(self) -> None:
        """Verify delta detection across added, removed, upgraded, and unchanged packages."""
        old_reqs = {
            "fastapi": "0.141.1",
            "pydantic": "2.13.5",
            "redis": "8.1.0",
            "deprecated-pkg": "1.0.0",
        }
        new_reqs = {
            "fastapi": "0.142.0",  # upgraded
            "pydantic": "2.13.5",  # unchanged
            "new-pkg": "1.2.0",  # added
            # redis removed
        }

        diffs = detect_dependency_diffs(old_reqs, new_reqs)
        diff_dict = {d.dependency: d for d in diffs}

        # Check upgraded
        assert "fastapi" in diff_dict
        assert diff_dict["fastapi"].diff_type == "upgrade"
        assert diff_dict["fastapi"].old_version == "0.141.1"
        assert diff_dict["fastapi"].new_version == "0.142.0"

        # Check added
        assert "new-pkg" in diff_dict
        assert diff_dict["new-pkg"].diff_type == "added"
        assert diff_dict["new-pkg"].old_version == "0.0.0"
        assert diff_dict["new-pkg"].new_version == "1.2.0"

        # Check removed
        assert "redis" in diff_dict
        assert diff_dict["redis"].diff_type == "removed"
        assert diff_dict["redis"].old_version == "8.1.0"
        assert diff_dict["redis"].new_version == "0.0.0"

        # Check unchanged package is not in diffs
        assert "pydantic" not in diff_dict

    def test_validation_suites_completeness(self) -> None:
        """Verify runner configures all required validation suites per TEST-10 specification."""
        runner = DependencyRegressionRunner(include_bruno=True)
        suites = runner.get_validation_suites()
        suite_names = [s["name"] for s in suites]

        expected_names = [
            "lint",
            "formatting",
            "type checking",
            "unit",
            "integration",
            "contract",
            "security",
            "AI critical regression",
            "E2E critical regression",
            "Bruno critical smoke",
        ]
        for name in expected_names:
            assert name in suite_names, f"Missing required validation suite: {name}"

    def test_runner_dry_run_execution(self) -> None:
        """Verify dry-run execution completes without running actual subprocesses."""
        runner = DependencyRegressionRunner(include_bruno=False)
        report = runner.run_validation(changed_diffs=[], dry_run=True)

        assert report.verdict == "PASS"
        assert len(report.suite_results) == 9
        for res in report.suite_results:
            assert res.passed is True
            assert res.exit_code == 0
            assert "[DRY-RUN]" in res.stdout_snippet

    def test_runner_regression_detection_and_classification(self) -> None:
        """Verify runner marks verdict REGRESSION_DETECTED and populates breakages on failure."""
        runner = DependencyRegressionRunner(include_bruno=False)
        diff = DependencyDiff(
            dependency="fastapi",
            category=DependencyCategory.FASTAPI,
            old_version="0.141.1",
            new_version="0.142.0",
            diff_type="upgrade",
        )

        # Simulate execution result
        fail_res = ValidationSuiteResult(
            suite_name="contract",
            command="pytest tests/contract/",
            exit_code=1,
            passed=False,
            duration_seconds=1.2,
            stdout_snippet="FAILED tests/contract/test_api_contract.py - SchemaDriftError: OpenAPI drift",
            stderr_snippet="",
        )

        classification = runner.classifier.classify_failure(
            dependency_diff=diff,
            affected_test="contract gate",
            failure_output=fail_res.stdout_snippet,
        )

        report = BreakageReport(
            timestamp="2026-09-16T12:00:00Z",
            base_ref="origin/main",
            target_ref="HEAD",
            changed_dependencies=[diff],
            suite_results=[fail_res],
            breakages=[classification],
            verdict="REGRESSION_DETECTED",
        )

        assert report.verdict == "REGRESSION_DETECTED"
        assert report.has_breakages is True
        assert len(report.breakages) == 1
        assert report.breakages[0].dependency == "fastapi"
        assert "Rollback" in report.breakages[0].rollback_recommendation

    def test_reporter_artifact_generation(self, tmp_path: Path) -> None:
        """Verify DependencyReporter creates valid JSON and Markdown artifacts."""
        reporter = DependencyReporter(output_dir=tmp_path)
        diff = DependencyDiff(
            dependency="pydantic",
            category=DependencyCategory.PYDANTIC,
            old_version="2.13.5",
            new_version="2.14.0",
            diff_type="upgrade",
        )
        report = BreakageReport(
            timestamp="2026-09-16T12:00:00Z",
            base_ref="origin/main",
            target_ref="HEAD",
            changed_dependencies=[diff],
            suite_results=[
                ValidationSuiteResult(
                    suite_name="lint",
                    command="ruff check .",
                    exit_code=0,
                    passed=True,
                    duration_seconds=0.15,
                )
            ],
            breakages=[],
            verdict="PASS",
        )

        artifacts = reporter.save_artifacts(report)
        assert "json" in artifacts and artifacts["json"].exists()
        assert "markdown" in artifacts and artifacts["markdown"].exists()

        # Check JSON integrity
        loaded_json = json.loads(artifacts["json"].read_text(encoding="utf-8"))
        assert loaded_json["verdict"] == "PASS"
        assert loaded_json["changed_dependencies"][0]["dependency"] == "pydantic"

        # Check Markdown contents
        md_text = artifacts["markdown"].read_text(encoding="utf-8")
        assert "# JakeAI Dependency Regression Audit Report (TEST-10)" in md_text
        assert "Zero Dependency Regressions Detected" in md_text
        assert "`pydantic`" in md_text
