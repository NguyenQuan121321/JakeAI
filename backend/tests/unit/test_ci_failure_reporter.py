"""Unit tests for JakeAI CI Failure & Forensic Reporter (TEST-11)."""

from __future__ import annotations

import json
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from pathlib import Path

from scripts.ci_failure_reporter import (
    classify_layer_from_path,
    collect_all_ci_failures,
    extract_scenario_name,
    generate_markdown_report,
    infer_dependency_from_context,
    parse_bruno_json_failures,
    parse_flaky_ledger,
    parse_junit_xml_failures,
)


def test_classify_layer_from_path() -> None:
    assert classify_layer_from_path("tests/unit/test_foo.py") == "Unit"
    assert (
        classify_layer_from_path("backend/tests/integration/test_bar.py")
        == "Integration"
    )
    assert classify_layer_from_path("tests/contract/test_contract.py") == "Contract"
    assert classify_layer_from_path("tests/security/test_sec.py") == "Security"
    assert classify_layer_from_path("tests/evals/test_eval.py") == "AI / Evaluation"
    assert classify_layer_from_path("tests/e2e/test_workflow.py") == "E2E Workflow"
    assert classify_layer_from_path("tests/performance/test_smoke.py") == "Performance"
    assert classify_layer_from_path("reports/bruno/test.bru") == "Bruno CLI"
    assert classify_layer_from_path("app/dependencies/manifest.py") == "Dependency"
    assert classify_layer_from_path("other/file.py") == "Core / Platform"


def test_infer_dependency_from_context() -> None:
    assert "Redis" in infer_dependency_from_context(
        "test_redis_cache", "test.py", "redis connection failed"
    )
    assert "Qdrant" in infer_dependency_from_context(
        "test_vector_search", "test.py", "qdrant unreachable"
    )
    assert "FinnApiGo / Auth" in infer_dependency_from_context(
        "test_jwt_auth", "test.py", "token invalid"
    )
    assert "FastEmbed (ONNX)" in infer_dependency_from_context(
        "test_embedding", "test.py", "onnx model load failed"
    )
    assert "LLM Provider" in infer_dependency_from_context(
        "test_gemini", "test.py", "openai api error"
    )
    assert (
        infer_dependency_from_context("test_pure_logic", "unit.py", "assert 1 == 2")
        == "None (In-Memory)"
    )


def test_extract_scenario_name() -> None:
    assert extract_scenario_name("test_simple_run") == "Simple run"
    assert (
        extract_scenario_name("TestClass::test_complex_data_flow")
        == "Complex data flow"
    )


def test_parse_junit_xml_failures(tmp_path: Path) -> None:
    xml_content = """<?xml version="1.0" encoding="utf-8"?>
<testsuites>
  <testsuite name="unit-tests" tests="2" failures="1" errors="0">
    <testcase classname="tests.unit.test_demo" name="test_failure" file="tests/unit/test_demo.py">
      <failure message="assert 1 == 2">Traceback (most recent call last):\\nAssertionError: assert 1 == 2</failure>
    </testcase>
    <testcase classname="tests.unit.test_demo" name="test_success" file="tests/unit/test_demo.py" />
  </testsuite>
</testsuites>
"""
    xml_file = tmp_path / "junit.xml"
    xml_file.write_text(xml_content, encoding="utf-8")

    failures = parse_junit_xml_failures(xml_file)
    assert len(failures) == 1
    item = failures[0]
    assert item.layer == "Unit"
    assert item.test == "test_failure"
    assert item.status == "FAILED"
    assert "assert 1 == 2" in item.log


def test_parse_bruno_json_failures(tmp_path: Path) -> None:
    json_data = {
        "items": [
            {
                "name": "Health Smoke",
                "target": "00 — Setup/01 — Health.bru",
                "status": "failed",
                "error_message": "Expected HTTP 200, got 500",
                "is_external": False,
            },
            {
                "name": "FinnApi Login",
                "target": "01 — Auth/01 — Login.bru",
                "status": "blocked",
                "error_message": "FinnApiGo offline",
                "is_external": True,
            },
        ]
    }
    json_file = tmp_path / "bruno-results.json"
    json_file.write_text(json.dumps(json_data), encoding="utf-8")

    failures = parse_bruno_json_failures(json_file)
    assert len(failures) == 2
    assert failures[0].status == "FAILED"
    assert failures[0].layer == "Bruno CLI"
    assert failures[1].status == "BLOCKED"
    assert failures[1].dependency == "FinnApiGo"


def test_parse_flaky_ledger(tmp_path: Path) -> None:
    ledger_data = {
        "flaky_tests": [
            {
                "test_id": "test_intermittent_network",
                "file_path": "tests/integration/test_net.py",
                "attempt_1_error": "ConnectionResetError: Connection lost",
            }
        ]
    }
    ledger_file = tmp_path / "flaky-tests.json"
    ledger_file.write_text(json.dumps(ledger_data), encoding="utf-8")

    flaky_items = parse_flaky_ledger(ledger_file)
    assert len(flaky_items) == 1
    assert flaky_items[0].status == "FLAKY"
    assert flaky_items[0].layer == "Integration"
    assert "Connection lost" in flaky_items[0].log


def test_collect_all_ci_failures_and_markdown(tmp_path: Path) -> None:
    # Empty dir -> clean report
    report = collect_all_ci_failures([tmp_path])
    assert report.is_green is True
    assert len(report.failures) == 0

    md = generate_markdown_report(report)
    assert "ALL CI GATES GREEN" in md
    assert "100% Clean Pass" in md

    # Now add a failure
    xml_content = """<?xml version="1.0" encoding="utf-8"?>
<testsuites>
  <testsuite name="unit" tests="1" failures="1">
    <testcase classname="tests.security.test_byok" name="test_byok_decrypt" file="tests/security/test_byok.py">
      <failure message="CryptoError">Decryption failed</failure>
    </testcase>
  </testsuite>
</testsuites>
"""
    (tmp_path / "report.xml").write_text(xml_content, encoding="utf-8")

    report2 = collect_all_ci_failures([tmp_path])
    assert report2.is_green is False
    assert report2.total_failed == 1
    md2 = generate_markdown_report(report2)
    assert "CI FAILURES DETECTED" in md2
    assert "Security" in md2
    assert "test_byok_decrypt" in md2
