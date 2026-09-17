"""Unit tests for JakeAI Flaky Test Tracker (TEST-11)."""

from __future__ import annotations

import json
from typing import TYPE_CHECKING
from unittest.mock import patch

if TYPE_CHECKING:
    from pathlib import Path

from scripts.ci_flaky_tracker import (
    FlakyOccurrence,
    FlakyReport,
    parse_pytest_junit_failures,
    save_flaky_ledger,
    track_and_run,
)


def test_parse_pytest_junit_failures(tmp_path: Path) -> None:
    xml_data = """<?xml version="1.0" encoding="utf-8"?>
<testsuites>
  <testsuite name="sample" tests="2" failures="1" errors="0">
    <testcase classname="tests.unit.test_demo" name="test_flaky_candidate">
      <failure message="TimeoutError: Connection timed out">Stacktrace...</failure>
    </testcase>
    <testcase classname="tests.unit.test_demo" name="test_stable" />
  </testsuite>
</testsuites>
"""
    xml_file = tmp_path / "junit.xml"
    xml_file.write_text(xml_data, encoding="utf-8")

    failures = parse_pytest_junit_failures(xml_file)
    assert len(failures) == 1
    assert "tests.unit.test_demo::test_flaky_candidate" in failures
    assert "TimeoutError" in failures["tests.unit.test_demo::test_flaky_candidate"]


def test_save_and_load_flaky_ledger(tmp_path: Path) -> None:
    ledger_path = tmp_path / "flaky-tests.json"
    occurrence = FlakyOccurrence(
        test_id="tests.integration.test_chat::test_slow_stream",
        file_path="tests/integration/test_chat.py",
        attempt_1_status="FAILED",
        attempt_1_error="ReadTimeout",
        attempt_2_status="PASSED",
        timestamp="2026-09-17T10:00:00Z",
    )
    report = FlakyReport(
        total_executed=1,
        attempt_1_passed=0,
        attempt_1_failed=1,
        retried_count=1,
        flaky_count=1,
        permanent_failures=0,
        is_clean=False,
        flaky_tests=[occurrence],
    )
    save_flaky_ledger(report, ledger_path)

    assert ledger_path.is_file()
    with open(ledger_path, encoding="utf-8") as f:
        data = json.load(f)

    assert data["flaky_count"] == 1
    assert (
        data["flaky_tests"][0]["test_id"]
        == "tests.integration.test_chat::test_slow_stream"
    )
    assert data["flaky_tests"][0]["attempt_2_status"] == "PASSED"


def test_track_and_run_clean_pass(tmp_path: Path) -> None:
    with patch("scripts.ci_flaky_tracker.run_pytest_command") as mock_run:
        mock_run.return_value = (0, "All 10 tests passed")

        code, report = track_and_run(
            pytest_args=["tests/unit"],
            cwd=tmp_path,
            output_dir=tmp_path / "reports",
            max_retries=1,
            fail_on_flaky=True,
        )

        assert code == 0
        assert report.is_clean is True
        assert report.flaky_count == 0
        assert mock_run.call_count == 1


def test_track_and_run_flaky_detection_never_false_pass(tmp_path: Path) -> None:
    """A test failing on attempt 1 and passing on attempt 2 MUST be classified as FLAKY."""

    def side_effect(args: list[str], junit_path: Path, cwd: Path) -> tuple[int, str]:
        junit_path.parent.mkdir(parents=True, exist_ok=True)
        if "attempt1" in str(junit_path):
            junit_path.write_text(
                """<?xml version="1.0" encoding="utf-8"?>
<testsuites>
  <testsuite name="s" tests="1" failures="1">
    <testcase classname="tests.unit.test_state" name="test_state_race">
      <failure message="AssertionError: lock timeout">Traceback</failure>
    </testcase>
  </testsuite>
</testsuites>""",
                encoding="utf-8",
            )
            return (1, "1 failed")
        else:
            junit_path.write_text(
                """<?xml version="1.0" encoding="utf-8"?>
<testsuites>
  <testsuite name="s" tests="1" failures="0">
    <testcase classname="tests.unit.test_state" name="test_state_race" />
  </testsuite>
</testsuites>""",
                encoding="utf-8",
            )
            return (0, "1 passed on retry")

    with patch("scripts.ci_flaky_tracker.run_pytest_command", side_effect=side_effect):
        # 1. Under fail_on_flaky=True -> must return exit code 2 (Strict Gate Failure)
        code, report = track_and_run(
            pytest_args=["tests/unit"],
            cwd=tmp_path,
            output_dir=tmp_path / "reports",
            max_retries=1,
            fail_on_flaky=True,
        )

        assert code == 2  # Strict block!
        assert report.flaky_count == 1
        assert report.is_clean is False
        assert (
            report.flaky_tests[0]["test_id"]
            if isinstance(report.flaky_tests[0], dict)
            else report.flaky_tests[0].test_id
            == "tests.unit.test_state::test_state_race"
        )

        # 2. Under fail_on_flaky=False -> reports flaky count > 0 (Never silent false pass)
        _code_warn, report_warn = track_and_run(
            pytest_args=["tests/unit"],
            cwd=tmp_path,
            output_dir=tmp_path / "reports",
            max_retries=1,
            fail_on_flaky=False,
        )
        assert report_warn.flaky_count == 1
        assert report_warn.is_clean is False
