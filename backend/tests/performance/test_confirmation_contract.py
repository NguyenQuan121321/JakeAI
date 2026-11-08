"""Drive the actual runner, reporter and CLI with prescribed measured samples."""

import importlib.util
import json
import os
from pathlib import Path
from unittest.mock import AsyncMock

import pytest

from app.performance.contracts import ScenarioResult
from app.performance.runner import PerformanceBenchmarkRunner


@pytest.fixture(autouse=True)
def isolate_standalone_bootstrap(monkeypatch):
    # Exercise the real CLI bootstrap without rotating the enclosing pytest
    # process's keys (some security parameters are minted at collection time).
    from app.core.config import get_settings
    from app.main import app

    monkeypatch.setattr(os, "environ", os.environ.copy())
    monkeypatch.setattr(
        app.state,
        "identity_client",
        getattr(app.state, "identity_client", None),
        raising=False,
    )
    yield
    get_settings.cache_clear()


def samples(runner, chat_rps):
    baseline = runner.store.load_baseline("v1")
    counts = {
        "concurrent_chat": 3,
        "concurrent_agent_runs": 2,
        "concurrent_rag_queries": 3,
        "sse_connections": 2,
        "redis_contention": 4,
        "qdrant_access": 3,
    }
    results = {}
    for name, count in counts.items():
        rps = (
            chat_rps
            if name == "concurrent_chat"
            else baseline.scenarios[name].baseline_metrics["throughput_rps"]
        )
        results[name] = ScenarioResult.model_validate(
            {
                "scenario_name": name,
                "concurrency": 2,
                "total_requests": count,
                "success_count": count,
                "error_count": 0,
                "error_rate_pct": 0,
                "latency": {
                    "overall_ms": {"count": count, "median_p50": 1, "p95": 1, "p99": 1}
                },
                "throughput": {
                    "total_requests": count,
                    "concurrency_level": 2,
                    "duration_seconds": count / rps,
                    "requests_per_second": rps,
                },
                "custom_metrics": {"is_live_redis": True, "is_live_qdrant": True},
            }
        )
    return results


def cli_module():
    path = Path(__file__).resolve().parents[2] / "scripts/run_performance_benchmark.py"
    spec = importlib.util.spec_from_file_location("confirmation_contract_cli", path)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


@pytest.mark.parametrize(
    "case,expected_exit",
    [
        ("timing_only", 0),
        ("latency_only", 0),
        ("repeatable", 1),
        ("request_recovered", 1),
        ("correctness_recovered", 1),
        ("missing_scenario", 1),
        ("missing_samples", 1),
        ("bad_denominator", 1),
        ("fallback_recovered", 1),
        ("invalid_confirmation", 1),
        ("changed_load", 1),
        ("nonfinite", 1),
        ("initial_pass", 0),
    ],
)
def test_actual_runner_report_and_cli_contract(
    monkeypatch, tmp_path, case, expected_exit
):
    runner = PerformanceBenchmarkRunner(mode="smoke")
    initial = samples(runner, 107.1 if case == "initial_pass" else 70.0)
    confirmations = samples(runner, 70.0 if case == "repeatable" else 107.1)
    bad = initial["concurrent_chat"]
    if case == "latency_only":
        bad.throughput = confirmations["concurrent_chat"].throughput.model_copy()
        bad.latency.overall_ms.p95 = 180
        bad.latency.overall_ms.p99 = 190
    elif case == "request_recovered":
        bad.success_count = 2
        bad.error_count = 1
        bad.error_rate_pct = 100 / 3
    elif case == "correctness_recovered":
        bad.custom_metrics["integrity_errors"] = ["Unexpected tenant in response"]
    elif case == "missing_scenario":
        del initial["concurrent_rag_queries"]
    elif case == "missing_samples":
        bad.latency.overall_ms.count = 0
    elif case == "bad_denominator":
        bad.success_count = 2
    elif case == "fallback_recovered":
        monkeypatch.setenv("J02_BENCHMARK_OWNED_SERVICES", "1")
        initial["redis_contention"].custom_metrics["is_live_redis"] = False
    elif case == "invalid_confirmation":
        confirmations["concurrent_chat"].latency.overall_ms.count = 0
    elif case == "changed_load":
        confirm = confirmations["concurrent_chat"]
        confirm.total_requests = confirm.success_count = (
            confirm.latency.overall_ms.count
        ) = 2
        confirm.throughput.total_requests = 2
    elif case == "nonfinite":
        bad.throughput.requests_per_second = float("nan")
    monkeypatch.setattr(runner, "run_all_scenarios", AsyncMock(return_value=initial))
    confirm = AsyncMock(side_effect=lambda name: confirmations[name])
    monkeypatch.setattr(runner, "run_scenario", confirm)
    cli = cli_module()
    monkeypatch.setattr(cli, "PerformanceBenchmarkRunner", lambda **kwargs: runner)
    monkeypatch.setattr(
        "sys.argv",
        [
            "benchmark",
            "--mode",
            "smoke",
            "--fail-on-regression",
            "--output-dir",
            str(tmp_path),
        ],
    )
    with pytest.raises(SystemExit) as exit_info:
        cli.main()
    assert exit_info.value.code == expected_exit
    payload = json.loads((tmp_path / "performance-results.json").read_text())
    report = payload["report"]
    assert report["initial_scenarios"].keys() == initial.keys()
    assert report["has_blocking_regressions"] == bool(expected_exit)
    assert (report["verdict"] == "FAIL") == bool(expected_exit)
    assert report["summary_text"].startswith(
        "FAIL:" if expected_exit else ("PASS:", "WARN:")
    )
    summary = json.loads((tmp_path / "performance-summary.json").read_text())
    assert summary["has_blocking_regressions"] == bool(expected_exit)
    markdown = (tmp_path / "performance-report.md").read_text(encoding="utf-8")
    assert "single prescribed confirmation" in markdown
    names = [call.args[0] for call in confirm.await_args_list]
    assert len(names) == len(set(names))  # At most one confirmation per scenario.
    assert set(report["confirmation_scenarios"]) == set(names)
    if case == "initial_pass":
        confirm.assert_not_awaited()
    else:
        assert "concurrent_chat" in names
        assert report["initial_findings"]
    if case == "timing_only":
        assert (
            report["initial_scenarios"]["concurrent_chat"]["throughput"][
                "requests_per_second"
            ]
            == 70
        )
        assert (
            payload["scenarios"]["concurrent_chat"]["throughput"]["requests_per_second"]
            == 107.1
        )
        assert any(f["verdict"] == "FAIL" for f in report["initial_findings"])
        assert all(f["verdict"] != "FAIL" for f in report["confirmation_findings"])
        assert not any(
            f["is_reproducible"]
            for f in report["initial_findings"]
            if f["verdict"] == "FAIL"
        )
    if case == "repeatable":
        assert any(
            f["is_reproducible"]
            for f in report["initial_findings"]
            if f["verdict"] == "FAIL"
        )
