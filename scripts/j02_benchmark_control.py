"""Same-runner old-main control; never resets a source baseline or a threshold."""

import json
import os
from pathlib import Path
import platform
import shutil
import subprocess
import sys
import urllib.request

from j02_rehearsal import identity

BASE = "bed2473b0b2878fa5351318a29ca047a8801af51"
ROOT = Path(__file__).resolve().parents[1]
FULL = {"concurrent_chat": (30, 10), "concurrent_agent_runs": (15, 5),
        "concurrent_rag_queries": (30, 10), "sse_connections": (16, 8),
        "redis_contention": (50, 15), "qdrant_access": (30, 10)}


def validate_measurements(initial, final):
    """Require the original complete load and real stores in every trial."""
    for trial in (initial, final):
        if set(trial) != set(FULL):
            raise ValueError("Control must measure all six scenarios")
        for name, (count, concurrency) in FULL.items():
            result = trial[name]
            if (result["scenario_name"] != name or result["total_requests"] != count
                or result["success_count"] != count or result["error_count"] != 0
                or result["error_rate_pct"] != 0 or result["concurrency"] != concurrency
                or result["latency"]["overall_ms"]["count"] != count
                or result["throughput"]["total_requests"] != count
                or result["throughput"]["concurrency_level"] != concurrency):
                raise ValueError("Control load/error/measurement integrity failed: " + name)
        for name, flag in (("redis_contention", "is_live_redis"), ("qdrant_access", "is_live_qdrant")):
            if trial[name]["custom_metrics"].get(flag) is not True:
                raise ValueError("Control requires real stores: " + name)


def classify_control(exit_code, initial, payload):
    """Classify diagnostic data, never reinterpret the candidate performance gate.

    Old-main threshold failures are measurements, not setup failures. Invalid
    capture, request errors, fallback stores, or incomplete load still block.
    """
    validate_measurements(initial, payload["scenarios"])
    report = payload["report"]
    failed = [f for f in report["findings"] if f["verdict"] == "FAIL"]
    if {f["scenario"] for f in report["findings"]} != set(FULL):
        raise ValueError("Control detector coverage is incomplete")
    verdict = report["verdict"]
    blocking = report["has_blocking_regressions"]
    if (report["total_scenarios_evaluated"] != 6 or exit_code not in (0, 1)
        or verdict not in ("PASS", "WARN", "FAIL")
        or bool(failed) != blocking or (verdict == "FAIL") != blocking
        or exit_code != int(blocking)):
        raise ValueError("Control exit/verdict integrity failed")
    return {"integrity": "VALID", "performance_verdict": verdict,
            "classification": "DIAGNOSTIC_THRESHOLD_FAILURE" if blocking else "DIAGNOSTIC_WITHIN_THRESHOLDS",
            "failed_metrics": failed, "step_exit_code": 0,
            "candidate_gate_unchanged": True}


def reset_owned_services():
    identity()  # Refuse local/fork/private/wrong-branch use before any mutation.
    if os.environ.get("J02_BENCHMARK_OWNED_SERVICES") != "1":
        raise RuntimeError("Explicit isolated benchmark services required")
    # These fixed loopback endpoints belong solely to this job's service
    # containers; no configurable production URL or credential is accepted.
    import redis
    with redis.Redis(host="127.0.0.1", port=6379, db=0) as client:
        client.flushdb()
    http = urllib.request.build_opener(urllib.request.ProxyHandler({}))
    with http.open("http://127.0.0.1:6333/collections", timeout=5) as response:
        collections = json.load(response)["result"]["collections"]
    for collection in collections:
        from urllib.parse import quote
        request = urllib.request.Request("http://127.0.0.1:6333/collections/" + quote(collection["name"], safe=""), method="DELETE")
        with http.open(request, timeout=5):
            pass
    print("Owned job-only Redis/Qdrant fixtures reset; source baselines unchanged", flush=True)


def control(receipt_callback=None):
    project, _ = identity()
    base = ROOT / "reviewed-main-control"
    sha = subprocess.check_output(["git", "-C", str(base), "rev-parse", "HEAD"], text=True).strip()
    if sha != BASE:
        raise RuntimeError("Exact reviewed-main control required")
    subprocess.run(["git", "-C", str(base), "diff", "--exit-code", "HEAD", "--", "backend"], check=True, capture_output=True)
    reset_owned_services()
    parent = Path(os.environ["RUNNER_TEMP"]).resolve()
    runtime = parent / (project + "-benchmark-control")
    if runtime.resolve().parent != parent or runtime.is_symlink():
        raise RuntimeError("Owned path required")
    runtime.mkdir(mode=0o700, exist_ok=False)
    # Configure only the known missing offline trust/vault adapter, identically
    # to the candidate; execute the unchanged old-main six-scenario runner.
    bootstrap = """
import json, pathlib, runpy, sys
runpy.run_path(sys.argv[1])['provision_offline_trust']()
sys.path.insert(0, sys.argv[2])
from app.performance.runner import PerformanceBenchmarkRunner
original = PerformanceBenchmarkRunner.run_all_scenarios
control_output = pathlib.Path(sys.argv[3])
async def capture(self, *args, **kwargs):
    results = await original(self, *args, **kwargs)
    (control_output / 'initial.json').write_text(json.dumps({k:v.model_dump() for k,v in results.items()}))
    return results
PerformanceBenchmarkRunner.run_all_scenarios = capture
entry = str(pathlib.Path(sys.argv[2], 'scripts/run_performance_benchmark.py'))
sys.argv = [entry, '--mode', 'full', '--fail-on-regression', '--output-dir', sys.argv[3]]
runpy.run_path(entry, run_name='__main__')
"""
    try:
        result = subprocess.run([sys.executable, "-c", bootstrap, str(ROOT / "backend/tests/offline_trust.py"),
                                 str(base / "backend"), str(runtime)], cwd=runtime,
                                env={**os.environ, "GITHUB_SHA": BASE}, capture_output=True, timeout=180)
        report = json.loads((runtime / "performance-results.json").read_text())
        initial = json.loads((runtime / "initial.json").read_text())
        outcome = classify_control(result.returncode, initial, report)
        receipt = {
            "actual_source": sha, "current_os": platform.platform(), "python": platform.python_version(),
            "same_installed_dependencies_as_candidate": True, "offline_configuration_reconciled": True,
            "baseline_file_modified": False, "exit_code": result.returncode,
            "initial_scenarios": initial, "results": report,
            "legacy_report_target_is_baseline_metadata": True,
            "diagnostic_outcome": outcome,
        }
        print("J02_PERFORMANCE_CONTROL " + json.dumps(receipt), flush=True)
        if receipt_callback is not None:
            receipt_callback(receipt)
        return outcome["step_exit_code"]
    finally:
        shutil.rmtree(runtime)
        print("Owned benchmark control private root removed", flush=True)


if __name__ == "__main__":
    if sys.argv[1:] == ["reset"]:
        reset_owned_services()
    elif sys.argv[1:] == ["control"]:
        sys.exit(control())
    elif sys.argv[1:] == ["candidate-integrity"]:
        identity()
        # This repair authorizes one bounded final pair, not another cohort.
        for directory in ("benchmark-results",):
            payload = json.loads((ROOT / "backend" / directory / "performance-results.json").read_text())
            validate_measurements(payload["report"]["initial_scenarios"], payload["scenarios"])
        print("J02_CANDIDATE_INTEGRITY all six scenarios, original load, real stores, zero errors in initial/confirmation trials; performance verdicts remain separate", flush=True)
    else:
        raise RuntimeError("Explicit reset/control operation required")
