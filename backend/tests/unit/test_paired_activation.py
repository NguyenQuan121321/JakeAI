"""Activation preflight and failure-only diagnostics, without live stores/load."""

import importlib.util
import json
from pathlib import Path
from unittest.mock import AsyncMock

import pytest

SCRIPTS = Path(__file__).resolve().parents[3] / "scripts"


def test_worker_rejects_third_trial_and_repeated_or_unmatched_profile(monkeypatch):
    monkeypatch.syspath_prepend(str(SCRIPTS))
    from j02_paired_worker import allow_command

    names = ["sse_connections"]
    allow_command("confirmation", names, True, set(), False)
    allow_command("diagnostic_profile", names, True, set(names), False)
    for phase, chosen, profiled in [
        ("confirmation", names, False),
        ("diagnostic_profile", names, True),
        ("diagnostic_profile", ["concurrent_chat"], False),
    ]:
        with pytest.raises(RuntimeError):
            allow_command(phase, chosen, True, set(names), profiled)


@pytest.mark.asyncio
async def test_worker_profiles_real_scenario_call_without_arguments_or_locals(
    monkeypatch,
):
    import types

    monkeypatch.syspath_prepend(str(SCRIPTS))
    from j02_paired_worker import diagnostic_profile

    sample = types.SimpleNamespace(
        model_dump=lambda **kwargs: {"synthetic_sample": True}
    )
    runner = types.SimpleNamespace(run_scenario=AsyncMock(return_value=sample))
    result = await diagnostic_profile(runner, ["sse_connections"])
    assert result["scope"] == "DIAGNOSTIC_ONLY_NOT_CONFIRMATION_OR_GATE"
    row = result["scenarios"]["sse_connections"]
    assert row["instrumented_sample"] == {"synthetic_sample": True}
    assert row["functions"] and all(
        set(f)
        == {
            "file",
            "line",
            "function",
            "primitive_calls",
            "calls",
            "self_seconds",
            "cumulative_seconds",
        }
        for f in row["functions"]
    )
    runner.run_scenario.assert_awaited_once_with("sse_connections")


@pytest.fixture
def capture(monkeypatch):
    scripts = Path(__file__).resolve().parents[3] / "scripts"
    monkeypatch.syspath_prepend(str(scripts))
    spec = importlib.util.spec_from_file_location(
        "activation_capture", scripts / "j02_paired_benchmark.py"
    )
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


@pytest.mark.parametrize("nested", [False, True])
def test_cpu_identity_reads_real_hierarchy_without_root_cpu_max(
    capture, tmp_path, nested
):
    root = tmp_path / "cgroup"
    root.mkdir()
    (root / "cgroup.controllers").write_text("cpuset cpu memory")
    process = tmp_path / "self-cgroup"
    path = "/job/worker" if nested else "/"
    process.write_text("0::" + path + "\n")
    if nested:
        (root / "job/worker").mkdir(parents=True)
        (root / "job/cpu.max").write_text("200000 100000")
        (root / "job/worker/cpu.max").write_text("max 100000")
    data = json.loads(capture.cpu_quota(root, process, affinity={0, 1, 2, 3}))
    assert data["process_cgroup"] == path
    assert data["affinity"] == [0, 1, 2, 3]
    assert data["hierarchy"][-1] == {"path": "/", "cpu.max": None}
    if nested:
        assert data["hierarchy"][1]["cpu.max"] == "200000 100000"


@pytest.mark.parametrize("bad", ["v1", "missing_controller", "traversal", "bad_limit"])
def test_missing_or_malformed_cpu_provenance_blocks(capture, tmp_path, bad):
    root = tmp_path / "cgroup"
    root.mkdir()
    (root / "cgroup.controllers").write_text(
        "memory" if bad == "missing_controller" else "cpu"
    )
    path = "/../escape" if bad == "traversal" else "/job"
    (root / "job").mkdir()
    (root / "job/cpu.max").write_text("bad" if bad == "bad_limit" else "max 100000")
    process = tmp_path / "self-cgroup"
    process.write_text("2:cpu:/job" if bad == "v1" else "0::" + path)
    with pytest.raises((ValueError, RuntimeError)):
        capture.cpu_quota(root, process, affinity={0})


@pytest.mark.asyncio
async def test_failed_metric_profiles_once_without_reauditing_or_clearing_result(
    capture,
):
    report = {
        "exit_code": 1,
        "verdict": "FAIL",
        "confirmation_required": ["sse_connections"],
        "confirmation_findings": [
            {
                "scenario": "sse_connections",
                "metric_name": "throughput_rps",
                "verdict": "FAIL",
            }
        ],
    }
    request = AsyncMock(return_value={"scope": "DIAGNOSTIC_ONLY", "scenarios": {}})
    await capture.profile_failure(report, request)
    assert report["exit_code"] == 1 and report["verdict"] == "FAIL"
    assert request.await_count == 2
    assert request.await_args_list[0].args == (
        "control",
        "diagnostic_profile",
        ["sse_connections"],
    )
    assert request.await_args_list[1].args == (
        "candidate",
        "diagnostic_profile",
        ["sse_connections"],
    )
    assert set(report["diagnostic_profiles"]) == {"control", "candidate"}


@pytest.mark.asyncio
@pytest.mark.parametrize("code", [0, 2])
async def test_pass_or_invalid_control_never_gets_an_extra_load(capture, code):
    request = AsyncMock()
    report = {
        "exit_code": code,
        "verdict": "PASS" if code == 0 else "INCONCLUSIVE_BLOCKED",
    }
    await capture.profile_failure(report, request)
    request.assert_not_called()
    assert report["exit_code"] == code


@pytest.mark.asyncio
async def test_profile_error_cannot_recover_the_primary_failure(capture):
    request = AsyncMock(side_effect=RuntimeError("private diagnostic"))
    report = {
        "exit_code": 1,
        "verdict": "FAIL",
        "confirmation_required": ["sse_connections"],
        "confirmation_findings": [{"scenario": "sse_connections", "verdict": "FAIL"}],
    }
    await capture.profile_failure(report, request)
    assert report["exit_code"] == 1 and report["verdict"] == "FAIL"
    assert all(
        value == {"error_class": "RuntimeError"}
        for value in report["diagnostic_profiles"].values()
    )
