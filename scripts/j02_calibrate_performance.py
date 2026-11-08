"""Authorized fixed five-pair hosted calibration; active v1 gates stay decisive."""

import hashlib
import importlib.metadata
import json
import os
from pathlib import Path
import platform
import shutil
import subprocess
import sys

from j02_benchmark_control import BASE, ROOT, control, reset_owned_services, validate_measurements
from j02_rehearsal import identity

FROZEN = "12edd7519f2e4771460ed9d0063dd80af6428480"
LANES = {"A": (1, 2, 3), "B": (4, 5)}
ORDERS = {pair: ("candidate", "control") if pair % 2 else ("control", "candidate") for pair in range(1, 6)}


def candidate_outcome(code, payload):
    validate_measurements(payload["report"]["initial_scenarios"], payload["scenarios"])
    report = payload["report"]
    blocking = report["has_blocking_regressions"]
    if code not in (0, 1) or code != int(blocking) or (report["verdict"] == "FAIL") != blocking:
        raise ValueError("Candidate exit/verdict integrity failed")
    return {"performance_verdict": report["verdict"], "gate_failed": blocking,
            "exit_code": code, "results": payload}


def measure_pairs(lane, candidate, diagnostic_control, emit):
    """Retain the prescribed cohort even after gate failures; never retry/select."""
    failed = False
    for pair in LANES[lane]:
        results = {}
        for subject in ORDERS[pair]:
            try:
                value = candidate(pair) if subject == "candidate" else diagnostic_control(pair)
                results[subject] = value
                if subject == "candidate":
                    failed |= value["gate_failed"]
            except Exception as exc:
                # No exception text: subprocess/configuration errors can contain
                # credentials. The class and missing subject remain explicit.
                results[subject] = {"integrity": "INVALID", "error_class": type(exc).__name__}
                failed = True
        emit("J02_CALIBRATION_PAIR", {"lane": lane, "pair": pair, "order": ORDERS[pair], "subjects": results})
    return int(failed)


def run(lane):
    project, _ = identity()  # Refuse local/fork/private execution before store/file access.
    if lane not in LANES or platform.python_version() != "3.12.15":
        raise RuntimeError("Frozen authorized lane/runtime required")
    backend_tree = subprocess.check_output(["git", "rev-parse", "HEAD:backend"], text=True).strip()
    frozen_tree = subprocess.check_output(["git", "rev-parse", FROZEN + ":backend"], text=True).strip()
    if backend_tree != frozen_tree:
        raise RuntimeError("Calibration backend must match frozen repaired source")
    constraint = ROOT / "scripts/j02/calibration-20261102.constraints.txt"
    normalize = lambda name: name.lower().replace("_", "-").replace(".", "-")
    actual = {normalize(d.metadata["Name"]): d.version for d in importlib.metadata.distributions()}
    expected = dict(line.split("==") for line in constraint.read_text().splitlines() if line and not line.startswith("#"))
    mismatches = {name: {"expected": version, "actual": actual.get(normalize(name))}
                  for name, version in expected.items() if actual.get(normalize(name)) != version}
    if mismatches:
        raise RuntimeError("Frozen dependency mismatch: " + json.dumps(mismatches))
    if set(actual) - {normalize(name) for name in expected} - {"pip", "setuptools", "wheel"}:
        raise RuntimeError("Unexpected calibration dependency")
    emit = lambda tag, data: print(tag + " " + json.dumps(data), flush=True)
    emit("J02_CALIBRATION_PROVENANCE", {"lane": lane, "pairs": LANES[lane], "orders": ORDERS,
        "frozen_backend_source": FROZEN, "backend_tree": backend_tree, "control_source": BASE,
        "tested_merge": os.environ["GITHUB_SHA"], "os": platform.platform(), "python": platform.python_version(),
        "cpu_count": os.cpu_count(), "runner_image": os.environ.get("ImageVersion"),
        "constraint_sha256": hashlib.sha256(constraint.read_bytes()).hexdigest(),
        "installed_distributions": actual, "additional_budget_usd": 0,
        "baseline_selected": "v1 unchanged; calibration never activates a baseline"})
    parent = Path(os.environ["RUNNER_TEMP"]).resolve()
    runtime = parent / (project + "-calibration")
    if runtime.resolve().parent != parent or runtime.is_symlink():
        raise RuntimeError("Owned calibration path required")
    runtime.mkdir(mode=0o700, exist_ok=False)
    baseline = ROOT / "backend/app/performance/baselines/baseline_v1.json"
    baseline_hash = hashlib.sha256(baseline.read_bytes()).hexdigest()
    def candidate(pair):
        reset_owned_services()
        output = runtime / ("pair-" + str(pair))
        result = subprocess.run([sys.executable, str(ROOT / "backend/scripts/run_performance_benchmark.py"),
            "--mode", "full", "--fail-on-regression", "--output-dir", str(output)],
            cwd=ROOT / "backend", capture_output=True, timeout=180)
        payload = json.loads((output / "performance-results.json").read_text())
        return candidate_outcome(result.returncode, payload)
    def diagnostic_control(pair):
        captured = []
        code = control(receipt_callback=captured.append)
        if code or len(captured) != 1:
            raise RuntimeError("Control capture integrity failed")
        return captured[0]
    try:
        code = measure_pairs(lane, candidate, diagnostic_control, emit)
        if hashlib.sha256(baseline.read_bytes()).hexdigest() != baseline_hash:
            raise RuntimeError("Active baseline changed during calibration")
        emit("J02_CALIBRATION_LANE", {"lane": lane, "planned_pairs": LANES[lane],
            "exit_code": code, "candidate_gates_preserved": True, "baseline_unchanged": True})
        return code
    finally:
        shutil.rmtree(runtime)
        emit("J02_CALIBRATION_CLEANUP", {"lane": lane, "owned_private_root_removed": not runtime.exists()})


if __name__ == "__main__":
    if len(sys.argv) != 2 or sys.argv[1] not in LANES:
        raise RuntimeError("Explicit frozen lane A/B required")
    sys.exit(run(sys.argv[1]))
