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


def control():
    project, _ = identity()
    base = ROOT / "reviewed-main-control"
    sha = subprocess.check_output(["git", "-C", str(base), "rev-parse", "HEAD"], text=True).strip()
    if sha != BASE:
        raise RuntimeError("Exact reviewed-main control required")
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
        print("J02_PERFORMANCE_CONTROL " + json.dumps({
            "actual_source": sha, "current_os": platform.platform(), "python": platform.python_version(),
            "same_installed_dependencies_as_candidate": True, "offline_configuration_reconciled": True,
            "baseline_file_modified": False, "exit_code": result.returncode,
            "initial_scenarios": initial, "results": report,
            "legacy_report_target_is_baseline_metadata": True,
        }), flush=True)
        return result.returncode
    finally:
        shutil.rmtree(runtime)
        print("Owned benchmark control private root removed", flush=True)


if __name__ == "__main__":
    if sys.argv[1:] == ["reset"]:
        reset_owned_services()
    elif sys.argv[1:] == ["control"]:
        sys.exit(control())
    else:
        raise RuntimeError("Explicit reset/control operation required")
