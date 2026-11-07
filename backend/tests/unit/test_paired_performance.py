"""Actual paired runner/CLI contracts; no sockets or benchmark load."""

import copy
import json
from unittest.mock import AsyncMock

import pytest

from app.performance.paired import (
    CONTROL_SHA,
    FULL,
    PairedComparisonRunner,
    compare,
    main,
)


@pytest.fixture
def evidence():
    context = {
        "job": {"run": "1", "attempt": "1", "job": "paired"},
        "runtime": {
            "python": "3.12.15",
            "runner": "ubuntu-24.04",
            "image": "20261026.354.1",
            "os": "Linux",
            "cpu": "test-cpu",
            "quota": "max 100000",
            "cores": 4,
        },
        "dependencies": {"a": "1.0"},
        "harness_sha256": "a" * 64,
        "stores": {
            "redis": {
                "image": "sha256:8da19c7399dca900c6822a1cf30f9d2285585e2c4b457ff4095b0f4500054d3f",
                "version": "7.4.12",
                "configuration": {
                    "appendonly": "no",
                    "appendfsync": "everysec",
                    "maxmemory-policy": "noeviction",
                    "maxmemory": "0",
                },
            },
            "qdrant": {
                "image": "sha256:d774e7bb65744454984c6021637a0da89271f30df15e48601a9fafc926d26b1f",
                "version": "1.12.1",
                "configuration": {
                    "service": {"http_port": 6333, "enable_tls": False},
                    "storage": {"storage_path": "./storage"},
                },
                "configuration_sources": {"default": "b" * 64},
            },
        },
        "workload": "full-1.0-three-tenants-all-miss-search-plus-upsert-v1",
    }
    subjects = {}
    for role, sha in (("candidate", "c" * 40), ("control", CONTROL_SHA)):
        subjects[role] = {
            "source_sha": sha,
            "source_tree": "e" * 40,
            "context": copy.deepcopy(context),
            "instances": {"redis": role + "-redis", "qdrant": role + "-qdrant"},
        }
    initial = {}
    for role in subjects:
        initial[role] = {}
        for name, (count, concurrency) in FULL.items():
            distribution = {"count": count, "median_p50": 100, "p95": 110, "p99": 120}
            initial[role][name] = {
                "scenario_name": name,
                "total_requests": count,
                "success_count": count,
                "error_count": 0,
                "error_rate_pct": 0,
                "concurrency": concurrency,
                "latency": {
                    "overall_ms": distribution,
                    "ttfc_ms": distribution if name == "sse_connections" else {},
                },
                "throughput": {
                    "duration_seconds": count / 100,
                    "total_requests": count,
                    "concurrency_level": concurrency,
                    "requests_per_second": 100,
                },
                "cache": {"tier1_exact_hits": 0},
                "custom_metrics": {"is_live_redis": True, "is_live_qdrant": True},
            }
    return {
        "subjects": subjects,
        "initial": initial,
        "confirmation": {"candidate": {}, "control": {}},
    }


def rps(result, value):
    result["throughput"].update(
        requests_per_second=value, duration_seconds=result["total_requests"] / value
    )


def confirm(evidence, names):
    evidence["confirmation"] = {
        role: {name: copy.deepcopy(evidence["initial"][role][name]) for name in names}
        for role in ("control", "candidate")
    }


@pytest.mark.asyncio
@pytest.mark.parametrize(
    "kind",
    [
        "equivalent",
        "latency",
        "throughput",
        "low",
        "near_zero",
        "recovered",
        "fatal_recovered",
    ],
)
async def test_runner_exit_and_fixed_confirmation(evidence, tmp_path, kind):
    sample = evidence["initial"]["candidate"]["sse_connections"]
    if kind == "latency":
        sample["latency"]["overall_ms"].update(median_p50=400, p95=410, p99=420)
    elif kind in {"throughput", "recovered"}:
        rps(sample, 40)
    elif kind in {"low", "near_zero"}:
        rps(
            evidence["initial"]["control"]["sse_connections"],
            0.1 if kind == "near_zero" else 23.95,
        )
        rps(sample, 0.095 if kind == "near_zero" else 0.1)
    elif kind == "fatal_recovered":
        sample.update(success_count=15, error_count=1, error_rate_pct=6.25)
    # This is the real asynchronous comparison runner, not a prewritten report.
    calls = []

    async def measure(role, phase, names):
        calls.append((role, phase, tuple(names)))
        values = copy.deepcopy(
            {name: evidence["initial"][role][name] for name in names}
        )
        if (
            phase == "confirmation"
            and role == "candidate"
            and kind in {"recovered", "fatal_recovered"}
        ):
            values["sse_connections"] = copy.deepcopy(
                evidence["initial"]["control"]["sse_connections"]
            )
        return values

    result = await PairedComparisonRunner(evidence["subjects"], measure).run()
    expected = 1 if kind in {"latency", "throughput", "low", "fatal_recovered"} else 0
    assert result["exit_code"] == expected
    assert len(calls) == (2 if kind in {"equivalent", "near_zero"} else 4)
    assert all(call[2] == ("sse_connections",) for call in calls[2:])
    file = tmp_path / "samples.json"
    file.write_text(json.dumps(result["evidence"]), encoding="utf-8")
    output = tmp_path / "report.json"
    assert main(["--evidence", str(file), "--output", str(output)]) == expected
    report = json.loads(output.read_text())
    assert report["exit_code"] == expected
    assert report["evidence"]["initial"] == result["evidence"]["initial"]


@pytest.mark.parametrize("role", ["candidate", "control"])
@pytest.mark.parametrize(
    "defect",
    [
        "request",
        "security",
        "fallback",
        "missing",
        "nan",
        "workload",
        "ttfc",
        "rate",
        "cache",
    ],
)
def test_fatal_errors_never_recover(evidence, role, defect):
    name = "sse_connections" if defect == "ttfc" else "redis_contention"
    sample = evidence["initial"][role][name]
    confirm(evidence, [name])
    if defect == "request":
        sample.update(success_count=49, error_count=1, error_rate_pct=2)
    elif defect == "security":
        sample["custom_metrics"]["integrity_errors"] = ["wrong tenant"]
    elif defect == "fallback":
        sample["custom_metrics"]["is_live_redis"] = False
    elif defect == "missing":
        del evidence["initial"][role][name]
    elif defect == "nan":
        sample["latency"]["overall_ms"]["p95"] = float("nan")
    elif defect == "workload":
        sample["concurrency"] = 1
    elif defect == "ttfc":
        sample["latency"]["ttfc_ms"] = {}
    elif defect == "rate":
        sample["throughput"]["duration_seconds"] = 99
    elif defect == "cache":
        sample["cache"]["tier1_exact_hits"] = 1
    result = compare(evidence)
    assert result["exit_code"] == (2 if role == "control" else 1)


@pytest.mark.asyncio
@pytest.mark.parametrize(
    "defect",
    [
        "missing",
        "same",
        "wrong_pin",
        "job",
        "dependencies",
        "harness",
        "image",
        "redis_config",
        "qdrant_config",
        "instance",
        "runtime",
        "workload",
    ],
)
async def test_incompatible_evidence_never_measures_or_succeeds(evidence, defect):
    subjects = evidence["subjects"]
    control = subjects["control"]
    context = control["context"]
    if defect == "missing":
        del subjects["control"]
    elif defect == "same":
        subjects["candidate"]["source_sha"] = CONTROL_SHA
    elif defect == "wrong_pin":
        control["source_sha"] = "d" * 40
    elif defect == "job":
        context["job"]["run"] = "2"
    elif defect == "dependencies":
        context["dependencies"]["a"] = "2"
    elif defect == "harness":
        context["harness_sha256"] = "d" * 64
    elif defect == "image":
        context["stores"]["redis"]["image"] = "sha256:" + "0" * 64
    elif defect == "redis_config":
        context["stores"]["redis"]["configuration"]["appendonly"] = "yes"
    elif defect == "qdrant_config":
        context["stores"]["qdrant"]["configuration"] = {}
    elif defect == "instance":
        control["instances"] = copy.deepcopy(subjects["candidate"]["instances"])
    elif defect == "runtime":
        del context["runtime"]["cpu"]
    elif defect == "workload":
        context["workload"] = "smoke"
    measure = AsyncMock()
    result = await PairedComparisonRunner(subjects, measure).run()
    assert result["exit_code"] == 2
    measure.assert_not_called()


def test_slow_control_is_inconclusive(evidence):
    rps(evidence["initial"]["control"]["sse_connections"], 0.001)
    result = compare(evidence)
    assert result["exit_code"] == 2


def test_missing_confirmation_is_blocking(evidence):
    rps(evidence["initial"]["candidate"]["sse_connections"], 20)
    assert compare(evidence)["exit_code"] == 2


def test_legacy_still_warns_for_low_reference_and_defaults_to_v1():
    from app.performance.baseline_store import PerformanceBaselineStore
    from app.performance.regression_detector import PerformanceRegressionDetector

    finding = PerformanceRegressionDetector.evaluate_metric(
        "sse_connections", "throughput_rps", 23.95, 0.001, 50, 25
    )
    assert finding.verdict.value == "WARN"
    assert PerformanceBaselineStore().load_baseline().version == "v1"


@pytest.mark.parametrize(
    "raw",
    ["null", "[]", "{", '{"subjects":null}', '{"subjects":{}}', '{"measurement":NaN}'],
)
def test_cli_malformed_evidence_blocks(tmp_path, raw):
    path = tmp_path / "input.json"
    path.write_text(raw, encoding="utf-8")
    output = tmp_path / "output.json"
    assert main(["--evidence", str(path), "--output", str(output)]) == 2
    assert json.loads(output.read_text())["verdict"] == "INCONCLUSIVE_BLOCKED"


@pytest.mark.parametrize("role", ["control", "candidate"])
def test_confirmation_fatal_after_initial_pass_also_blocks(evidence, role):
    confirm(evidence, ["sse_connections"])
    evidence["confirmation"][role]["sse_connections"]["custom_metrics"][
        "integrity_errors"
    ] = ["forbidden effect"]
    assert compare(evidence)["exit_code"] == (2 if role == "control" else 1)


def test_unmatched_confirmation_blocks(evidence):
    confirm(evidence, ["sse_connections"])
    evidence["confirmation"]["candidate"] = {}
    assert compare(evidence)["exit_code"] == 2


@pytest.mark.parametrize("defect", ["redis", "qdrant", "empty_dependencies", "runtime"])
def test_identically_invalid_contexts_still_block(evidence, defect):
    for subject in evidence["subjects"].values():
        context = subject["context"]
        if defect == "redis":
            context["stores"]["redis"]["configuration"]["maxmemory-policy"] = (
                "allkeys-lru"
            )
        elif defect == "qdrant":
            context["stores"]["qdrant"]["configuration"]["service"]["api_key"] = (
                "synthetic-forbidden"
            )
        elif defect == "empty_dependencies":
            context["dependencies"] = {}
        else:
            context["runtime"]["cpu"] = "unknown"
    assert compare(evidence)["exit_code"] == 2


@pytest.mark.asyncio
async def test_failed_capture_preserves_partial_evidence(evidence):
    calls = []

    async def measure(role, phase, names):
        calls.append((role, phase))
        if role == "candidate":
            raise TimeoutError("synthetic private exception text")
        return copy.deepcopy(evidence["initial"][role])

    result = await PairedComparisonRunner(evidence["subjects"], measure).run()
    assert result["exit_code"] == 2
    assert result["evidence"]["initial"]["control"]
    assert "synthetic private" not in result["reason"]


@pytest.fixture
def collector(monkeypatch):
    import importlib.util
    from pathlib import Path

    scripts = Path(__file__).resolve().parents[3] / "scripts"
    monkeypatch.syspath_prepend(str(scripts))
    spec = importlib.util.spec_from_file_location(
        "paired_capture_test", scripts / "j02_paired_benchmark.py"
    )
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def test_hosted_guard_precedes_any_store_or_docker_access(
    collector, monkeypatch, tmp_path
):
    monkeypatch.setenv("GITHUB_ACTIONS", "false")
    stores = AsyncMock(side_effect=AssertionError("No stores allowed"))
    monkeypatch.setattr(collector, "capture_stores", stores)
    assert (
        collector.main(
            ["--control", str(tmp_path), "--output", str(tmp_path / "report.json")]
        )
        == 2
    )
    stores.assert_not_called()


@pytest.mark.parametrize("defect", [None, "port", "mount", "override", "command"])
def test_actual_store_configuration_collector(collector, monkeypatch, defect):
    import io
    from unittest.mock import MagicMock

    import redis

    context = evidence.__wrapped__()["subjects"]["candidate"]["context"]["stores"]

    def docker(*args):
        if args[0] == "inspect":
            name = args[1]
            config = {
                "Env": ["RUN_MODE=production"],
                "Cmd": ["./entrypoint.sh"],
                "Entrypoint": None,
            }
            if defect == "override" and name == "qdrant":
                config["Env"].append("QDRANT__SERVICE__API_KEY=forbidden")
            if defect == "command":
                config["Cmd"] = ["./entrypoint.sh", "--config-path", "unknown"]
            return json.dumps(
                [
                    {
                        "Id": name,
                        "Image": name,
                        "Config": config,
                        "Mounts": [{"Destination": "/qdrant/config"}]
                        if defect == "mount"
                        else [],
                        "NetworkSettings": {
                            "Ports": {
                                ("6379" if name == "redis" else "6333") + "/tcp": [
                                    {
                                        "HostPort": "9999"
                                        if defect == "port"
                                        else "6379"
                                        if name == "redis"
                                        else "6333"
                                    }
                                ]
                            }
                        },
                    }
                ]
            )
        if args[0] == "image":
            return json.dumps(
                [
                    {
                        "RepoDigests": ["image@" + context[args[2]]["image"]],
                        "Config": {"Cmd": ["./entrypoint.sh"], "Entrypoint": None},
                    }
                ]
            )
        if "config.yaml" in args[-1]:
            return "service:\n  http_port: 6333\n  enable_tls: false\nstorage:\n  storage_path: ./storage\n"
        return ""

    monkeypatch.setattr(collector, "docker", docker)
    monkeypatch.setenv("J02_CANDIDATE_REDIS_CONTAINER", "redis")
    monkeypatch.setenv("J02_CANDIDATE_QDRANT_CONTAINER", "qdrant")
    client = MagicMock()
    client.__enter__.return_value = client
    client.info.return_value = {"redis_version": "7.4.12"}
    client.config_get.return_value = context["redis"]["configuration"]
    client.dbsize.return_value = 0
    monkeypatch.setattr(redis, "Redis", MagicMock(return_value=client))
    http = MagicMock()
    http.open.side_effect = lambda url, **kwargs: io.BytesIO(
        json.dumps(
            {"result": {"collections": []}}
            if url.endswith("/collections")
            else {"version": "1.12.1"}
        ).encode()
    )
    monkeypatch.setattr(collector.urllib.request, "build_opener", lambda *args: http)
    if defect:
        with pytest.raises(RuntimeError):
            collector.capture_stores("candidate")
    else:
        result, instances = collector.capture_stores("candidate")
        assert result["redis"] == context["redis"]
        assert result["qdrant"]["configuration"] == context["qdrant"]["configuration"]
        assert instances == {"redis": "redis", "qdrant": "qdrant"}


@pytest.mark.asyncio
@pytest.mark.parametrize(
    "fault", [None, "configuration_drift", "probe_failure", "source_drift"]
)
async def test_capture_command_preserves_received_samples_before_verification(
    collector, evidence, monkeypatch, tmp_path, fault
):
    """Exercise actual capture/result writing with synthetic worker IO."""
    import types
    from pathlib import Path

    control = tmp_path / "control"
    (control / "backend").mkdir(parents=True)
    (control / "backend/requirements.txt").write_bytes(
        (collector.ROOT / "backend/requirements.txt").read_bytes()
    )
    monkeypatch.setattr(collector, "identity", lambda: None)
    monkeypatch.setattr(collector.platform, "python_version", lambda: "3.12.15")
    monkeypatch.setattr(collector.platform, "system", lambda: "Linux")
    monkeypatch.setattr(collector, "cpu_quota", lambda: "unit observed quota")
    event = tmp_path / "event.json"
    event.write_text(json.dumps({"pull_request": {"head": {"sha": "c" * 40}}}))
    for key, value in {
        "GITHUB_EVENT_PATH": str(event),
        "J02_PAIRED_CONTRACT": "review-v1",
        "ImageVersion": "unit-image",
        "GITHUB_RUN_ID": "1",
        "GITHUB_RUN_ATTEMPT": "1",
        "GITHUB_JOB": "unit",
        "RUNNER_TEMP": str(tmp_path),
    }.items():
        monkeypatch.setenv(key, value)
    original_read = Path.read_text

    def read(path, *args, **kwargs):
        if str(path).replace("\\", "/") == "/proc/cpuinfo":
            return "model name: unit-cpu"
        if str(path).replace("\\", "/") == "/sys/fs/cgroup/cpu.max":
            return "max 100000"
        return original_read(path, *args, **kwargs)

    monkeypatch.setattr(Path, "read_text", read)

    def git(source, *args):
        if args == ("rev-parse", "HEAD"):
            return CONTROL_SHA if Path(source) == control else "c" * 40
        return ""

    monkeypatch.setattr(collector, "git", git)
    identity_calls = 0

    def source_identity(source):
        nonlocal identity_calls
        identity_calls += 1
        if fault == "source_drift" and identity_calls > 2:
            raise RuntimeError("synthetic source drift after capture")
        return {
            "source_sha": CONTROL_SHA if Path(source) == control else "c" * 40,
            "source_tree": "e" * 40,
        }

    monkeypatch.setattr(collector, "source_identity", source_identity)
    constraint = collector.ROOT / "scripts/j02/calibration-20261102.constraints.txt"
    dependencies = dict(
        line.split("==")
        for line in constraint.read_text().splitlines()
        if line and not line.startswith("#")
    )
    inventory = {
        name.lower().replace("_", "-").replace(".", "-"): version
        for name, version in dependencies.items()
    }
    monkeypatch.setattr(
        collector.importlib.metadata,
        "distributions",
        lambda: [
            types.SimpleNamespace(metadata={"Name": name}, version=version)
            for name, version in inventory.items()
        ],
    )
    store_calls = dict.fromkeys(("control", "candidate"), 0)

    def stores(role, require_empty=True):
        store_calls[role] += 1
        values = copy.deepcopy(evidence["subjects"][role]["context"]["stores"])
        if role == "control" and store_calls[role] == 3:
            if fault == "probe_failure":
                raise RuntimeError("private synthetic configuration probe error")
            if fault == "configuration_drift":
                values["redis"]["configuration"]["appendonly"] = "yes"
        return values, evidence["subjects"][role]["instances"]

    monkeypatch.setattr(collector, "capture_stores", stores)
    processes = []

    class Process:
        returncode = None

        def __init__(self, role):
            self.role = role
            self.queue = [
                json.dumps({"ready": True, "dependencies": inventory}).encode()
            ]
            self.stdout = self
            self.stdin = self

        async def readline(self):
            return self.queue.pop(0)

        def write(self, raw):
            command = json.loads(raw)
            self.queue.append(
                json.dumps(
                    {
                        name: evidence["initial"][self.role][name]
                        for name in command["names"]
                    }
                ).encode()
            )

        async def drain(self):
            pass

        def kill(self):
            self.returncode = -9

        async def wait(self):
            return self.returncode

    async def start(*args, **kwargs):
        process = Process("control" if not processes else "candidate")
        processes.append(process)
        return process

    monkeypatch.setattr(collector.asyncio, "create_subprocess_exec", start)
    output = tmp_path / "result.json"
    code = await collector.capture(control, output)
    report = json.loads(output.read_text())
    assert code == (2 if fault else 0)
    assert (
        report["capture_observations"][0]["samples"] == evidence["initial"]["control"]
    )
    assert all(process.returncode is not None for process in processes)
    assert not list(tmp_path.glob("j02-paired-*"))


@pytest.mark.parametrize(
    "case,expected", [("equivalent", 0), ("regression", 1), ("missing_control", 2)]
)
def test_module_process_exit_is_blocking(evidence, tmp_path, case, expected):
    import subprocess
    import sys
    from pathlib import Path

    if case == "regression":
        rps(evidence["initial"]["candidate"]["sse_connections"], 40)
        confirm(evidence, ["sse_connections"])
    elif case == "missing_control":
        del evidence["subjects"]["control"]
    samples = tmp_path / "samples.json"
    output = tmp_path / "comparison.json"
    samples.write_text(json.dumps(evidence), encoding="utf-8")
    result = subprocess.run(
        [
            sys.executable,
            "-m",
            "app.performance.paired",
            "--evidence",
            str(samples),
            "--output",
            str(output),
        ],
        cwd=Path(__file__).resolve().parents[2],
        capture_output=True,
        text=True,
    )
    assert result.returncode == expected, result.stderr
    assert json.loads(output.read_text())["exit_code"] == expected
