"""Guarded hosted paired capture; legacy v1 remains independently blocking.

Requires four job-owned service containers so subject state survives while
measuring the other subject. No store/configuration change or load retry.
"""

import argparse
import asyncio
import copy
import hashlib
import importlib.metadata
import json
import os
import platform
import shutil
import subprocess
import sys
import tempfile
import traceback
import urllib.request
from pathlib import Path

from j02_rehearsal import identity

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "backend"))
from app.performance.paired import (
    CAPTURE_SECONDS,
    CONTROL_SHA,
    ROLES,
    WORKLOAD,
    PairedComparisonRunner,
    validate_subjects,
)


def git(source, *args):
    return subprocess.check_output(["git", "-C", str(source), *args]).decode().strip()


def docker(*args):
    return subprocess.check_output(["docker", *args], timeout=15).decode()


def merge(left, right):
    result = copy.deepcopy(left)
    for key, value in right.items():
        result[key] = (
            merge(result.get(key, {}), value) if isinstance(value, dict) else value
        )
    return result


def cpu_quota(
    root=Path("/sys/fs/cgroup"), process=Path("/proc/self/cgroup"), affinity=None
):
    """Capture v2 process/ancestor limits, including the root's absent cpu.max.

    Linux exposes cpu.max only on non-root cgroups. Absence is recorded, never
    silently substituted for an unknown controller or malformed hierarchy.
    """
    root = root.resolve()
    groups = [
        line[3:] for line in process.read_text().splitlines() if line.startswith("0::")
    ]
    if (
        len(groups) != 1
        or not groups[0].startswith("/")
        or ".." in Path(groups[0]).parts
    ):
        raise ValueError("Known unified process cgroup required")
    if "cpu" not in (root / "cgroup.controllers").read_text().split():
        raise RuntimeError("CPU controller provenance unavailable")
    path = (root / groups[0].lstrip("/")).resolve()
    if not path.is_relative_to(root) or not path.is_dir():
        raise ValueError("Process cgroup is outside the observed hierarchy")
    hierarchy = []
    while True:
        file = path / "cpu.max"
        limit = file.read_text().strip() if file.is_file() else None
        if limit is not None:
            quota, period = limit.split()
            if (quota != "max" and int(quota) <= 0) or int(period) <= 0:
                raise ValueError("Malformed CPU bandwidth limit")
        hierarchy.append(
            {
                "path": "/"
                if path == root
                else "/" + path.relative_to(root).as_posix(),
                "cpu.max": limit,
            }
        )
        if path == root:
            break
        path = path.parent
    cpus = sorted(os.sched_getaffinity(0) if affinity is None else affinity)
    if not cpus:
        raise ValueError("Effective CPU affinity missing")
    return json.dumps(
        {"process_cgroup": groups[0], "hierarchy": hierarchy, "affinity": cpus},
        sort_keys=True,
    )


async def profile_failure(report, request):
    """One failure-only diagnostic per subject; never re-audit or clear FAIL."""
    if report["exit_code"] != 1:
        return
    findings = [
        f
        for f in report.get("confirmation_findings", [])
        if f["verdict"] == "FAIL" and f["scenario"] in report["confirmation_required"]
    ]
    names = sorted({f["scenario"] for f in findings})
    if not names:
        return
    report["profile_basis"] = findings
    report["diagnostic_profiles"] = {}
    for role in ROLES:
        try:
            report["diagnostic_profiles"][role] = await request(
                role, "diagnostic_profile", names
            )
        except (RuntimeError, ValueError, OSError, TimeoutError) as error:
            report["diagnostic_profiles"][role] = {"error_class": type(error).__name__}


def capture_stores(role, require_empty=True):
    import redis
    import yaml

    stores, instances = {}, {}
    offset = 0 if role == "candidate" else 1
    for name in ("redis", "qdrant"):
        identifier = os.environ[
            "J02_" + role.upper() + "_" + name.upper() + "_CONTAINER"
        ]
        info = json.loads(docker("inspect", identifier))[0]
        port = 6379 if name == "redis" else 6333
        expected_port = port + (offset if name == "redis" else offset * 2)
        bindings = info["NetworkSettings"]["Ports"][str(port) + "/tcp"]
        if not bindings or any(
            binding["HostPort"] != str(expected_port) for binding in bindings
        ):
            raise RuntimeError("Inspected container does not own the measured endpoint")
        # Only published job-owned containers; reject config/credential mounts.
        if any(
            m["Destination"] not in {"/data", "/qdrant/storage"} for m in info["Mounts"]
        ):
            raise RuntimeError("Unexpected service mount")
        image = json.loads(docker("image", "inspect", info["Image"]))[0]
        digests = image["RepoDigests"]
        if len(digests) != 1:
            raise RuntimeError("Ambiguous service image identity")
        digest = digests[0].split("@", 1)[1]
        instances[name] = info["Id"]
        if name == "redis":
            with redis.Redis(
                host="127.0.0.1", port=6379 + offset, decode_responses=True
            ) as client:
                server = client.info("server")
                configuration = client.config_get(
                    "appendonly", "appendfsync", "maxmemory-policy", "maxmemory"
                )
                if require_empty and client.dbsize() != 0:
                    raise RuntimeError("Subject store is not initially empty")
            stores[name] = {
                "image": digest,
                "version": server["redis_version"],
                "configuration": configuration,
            }
        else:
            # Reconstruct effective startup configuration from the actual
            # immutable files, RUN_MODE, environment and command. Refuse flags
            # or unknown sources rather than infer effective configuration.
            environment = dict(item.split("=", 1) for item in info["Config"]["Env"])
            mode = environment.get("RUN_MODE", "production")
            if (
                mode != "production"
                or info["Config"]["Cmd"] != image["Config"]["Cmd"]
                or info["Config"]["Entrypoint"] != image["Config"]["Entrypoint"]
            ):
                raise RuntimeError("Unsupported Qdrant configuration source")
            if any(key.startswith("QDRANT") for key in environment):
                raise RuntimeError(
                    "Qdrant environment overrides require explicit review"
                )
            effective, sources = {}, {}
            for filename in ("config.yaml", "production.yaml", "local.yaml"):
                raw = docker(
                    "exec",
                    identifier,
                    "sh",
                    "-c",
                    "if [ -f /qdrant/config/"
                    + filename
                    + " ]; then cat /qdrant/config/"
                    + filename
                    + "; fi",
                )
                sources[filename] = hashlib.sha256(raw.encode()).hexdigest()
                effective = merge(effective, yaml.safe_load(raw) or {})
            if any(
                effective.get("service", {}).get(key)
                for key in ("api_key", "read_only_api_key")
            ):
                raise RuntimeError("Unexpected service authentication configuration")
            http = urllib.request.build_opener(urllib.request.ProxyHandler({}))
            with http.open(
                "http://127.0.0.1:" + str(6333 + offset * 2) + "/", timeout=5
            ) as response:
                version = json.load(response)["version"]
            with http.open(
                "http://127.0.0.1:" + str(6333 + offset * 2) + "/collections", timeout=5
            ) as response:
                if json.load(response)["result"]["collections"] and require_empty:
                    raise RuntimeError("Subject vector store is not initially empty")
            stores[name] = {
                "image": digest,
                "version": version,
                "configuration": effective,
                "configuration_sources": sources,
            }
    return stores, instances


def source_identity(path):
    if git(path, "status", "--porcelain", "--untracked-files=no"):
        raise RuntimeError("Tracked subject source must be clean")
    return {
        "source_sha": git(path, "rev-parse", "HEAD"),
        "source_tree": git(path, "rev-parse", "HEAD:backend"),
    }


async def capture(control, output):
    identity()  # Before subprocess, filesystem creation or store access.
    if (
        os.environ.get("J02_PAIRED_CONTRACT") != "review-v1"
        or platform.python_version() != "3.12.15"
    ):
        raise RuntimeError("Explicit reviewed hosted paired contract required")
    sources = {"candidate": ROOT, "control": control.resolve()}
    event = json.loads(
        Path(os.environ["GITHUB_EVENT_PATH"]).read_text(encoding="utf-8")
    )
    if git(ROOT, "rev-parse", "HEAD") != event["pull_request"]["head"]["sha"]:
        raise RuntimeError("Candidate checkout is not the exact PR head")
    if git(sources["control"], "rev-parse", "HEAD") != CONTROL_SHA:
        raise RuntimeError("Pinned pre-J02 source required")
    if git(ROOT, "merge-base", "--is-ancestor", CONTROL_SHA, "HEAD"):
        raise RuntimeError("Unexpected ancestry result")
    files = (
        sorted((ROOT / "backend/app/performance").rglob("*.py"))
        + [
            ROOT / "backend/tests/offline_trust.py",
            ROOT / "scripts/j02_paired_worker.py",
        ]
        + [ROOT / "scripts/j02_paired_benchmark.py"]
    )
    harness_hash = hashlib.sha256(
        b"".join(
            str(p.relative_to(ROOT)).encode() + b"\0" + p.read_bytes() for p in files
        )
    ).hexdigest()
    runtime = {
        "python": platform.python_version(),
        "runner": "ubuntu-24.04",
        "image": os.environ["ImageVersion"],
        "os": platform.system(),
        "cores": os.cpu_count(),
        "cpu": next(
            line.split(":", 1)[1].strip()
            for line in Path("/proc/cpuinfo").read_text().splitlines()
            if line.startswith("model name")
        ),
        "quota": cpu_quota(),
    }
    dependencies = {
        d.metadata["Name"].lower().replace("_", "-").replace(".", "-"): d.version
        for d in importlib.metadata.distributions()
    }
    constraint = dict(
        line.split("==")
        for line in (ROOT / "scripts/j02/calibration-20261102.constraints.txt")
        .read_text()
        .splitlines()
        if line and not line.startswith("#")
    )
    if any(
        dependencies.get(name.lower().replace("_", "-").replace(".", "-")) != value
        for name, value in constraint.items()
    ):
        raise RuntimeError("Installed constraint mismatch")
    subjects = {}
    baseline = ROOT / "backend/app/performance/baselines/baseline_v1.json"
    baseline_hash = hashlib.sha256(baseline.read_bytes()).hexdigest()
    for role in ROLES:
        stores, instances = capture_stores(role)
        subjects[role] = {
            **source_identity(sources[role]),
            "source_requirements_sha256": hashlib.sha256(
                (sources[role] / "backend/requirements.txt").read_bytes()
            ).hexdigest(),
            "shared_constraint_sha256": hashlib.sha256(
                (ROOT / "scripts/j02/calibration-20261102.constraints.txt").read_bytes()
            ).hexdigest(),
            "harness_adaptation": "Common measurement package; native JWT format with equivalent ephemeral access claims; synthetic state/model adapters",
            "instances": instances,
            "context": {
                "job": {
                    "run": os.environ["GITHUB_RUN_ID"],
                    "attempt": os.environ["GITHUB_RUN_ATTEMPT"],
                    "job": os.environ["GITHUB_JOB"],
                },
                "runtime": runtime,
                "dependencies": dependencies,
                "harness_sha256": harness_hash,
                "stores": stores,
                "workload": WORKLOAD,
            },
        }
    validate_subjects(subjects)
    workers, logs = {}, []
    private = Path(
        tempfile.mkdtemp(prefix="j02-paired-", dir=os.environ["RUNNER_TEMP"])
    ).resolve()
    private_parent = Path(os.environ["RUNNER_TEMP"]).resolve()
    try:
        for role in ROLES:
            offset = 0 if role == "candidate" else 1
            env = {
                **os.environ,
                "ENVIRONMENT": "test",
                "REDIS_URL": f"redis://127.0.0.1:{6379 + offset}/0",
                "QDRANT_URL": f"http://127.0.0.1:{6333 + offset * 2}",
                "QDRANT_OFFLINE": "0",
            }
            for name in (
                "OPENAI_API_KEY",
                "GEMINI_API_KEY",
                "ANTHROPIC_API_KEY",
                "DEEPSEEK_API_KEY",
                "QDRANT_API_KEY",
            ):
                env.pop(name, None)
            log = (private / (role + ".log")).open("wb")
            logs.append(log)
            workers[role] = await asyncio.create_subprocess_exec(
                sys.executable,
                str(ROOT / "scripts/j02_paired_worker.py"),
                str(sources[role]),
                str(ROOT),
                cwd=private,
                env=env,
                stdin=asyncio.subprocess.PIPE,
                stdout=asyncio.subprocess.PIPE,
                stderr=log,
                limit=2 * 1024 * 1024,
            )
            ready = json.loads(
                await asyncio.wait_for(workers[role].stdout.readline(), 30)
            )
            if ready != {"ready": True, "dependencies": dependencies}:
                raise RuntimeError("Worker dependency identity mismatch")
        observations = []

        async def measure(role, phase, names):
            before = capture_stores(role, require_empty=False)
            if before != (
                subjects[role]["context"]["stores"],
                subjects[role]["instances"],
            ):
                raise RuntimeError("Store configuration changed before measurement")
            process = workers[role]
            process.stdin.write(
                (json.dumps({"phase": phase, "names": names}) + "\n").encode()
            )
            await process.stdin.drain()
            result = json.loads(
                await asyncio.wait_for(process.stdout.readline(), CAPTURE_SECONDS)
            )
            observation = {
                "role": role,
                "phase": phase,
                "names": names,
                "samples": result,
                "stores_before": before[0],
                "instances": before[1],
                "store_verification": "INCOMPLETE_BLOCKING",
            }
            # Retain the received measurement before any subsequent probe can
            # fail. A blocked capture must not discard an observed trial.
            observations.append(observation)
            after = capture_stores(role, require_empty=False)
            observation["stores_after"] = after[0]
            if after != before:
                observation["store_verification"] = "MISMATCH_BLOCKING"
                raise RuntimeError("Store configuration changed during measurement")
            observation["store_verification"] = "MATCHED"
            return result

        report = await PairedComparisonRunner(subjects, measure).run()
        try:
            identities_valid = (
                all(
                    source_identity(sources[role])
                    == {
                        key: subjects[role][key]
                        for key in ("source_sha", "source_tree")
                    }
                    for role in ROLES
                )
                and hashlib.sha256(baseline.read_bytes()).hexdigest() == baseline_hash
            )
        except (OSError, RuntimeError, subprocess.SubprocessError):
            identities_valid = False
        if not identities_valid:
            report.update(
                exit_code=2,
                verdict="INCONCLUSIVE_BLOCKED",
                reason="Source/baseline identity changed; all received samples retained",
            )
        report["legacy_v1_sha256"] = baseline_hash
        report["capture_observations"] = observations
        output.write_text(
            json.dumps(report, indent=2, allow_nan=False) + "\n", encoding="utf-8"
        )
        # Baseline bytes were never used as control measurements or rewritten.
        print("J02_PAIRED_RESULT " + json.dumps(report), flush=True)
        # The primary verdict and observations are already durable in the job
        # file/log before a requested failure-only diagnostic can fail or time out.
        await profile_failure(report, measure)
        output.write_text(
            json.dumps(report, indent=2, allow_nan=False) + "\n", encoding="utf-8"
        )
        if report.get("diagnostic_profiles"):
            print(
                "J02_PAIRED_DIAGNOSTICS " + json.dumps(report["diagnostic_profiles"]),
                flush=True,
            )
        return report["exit_code"]
    finally:
        for process in workers.values():
            if process.returncode is None:
                process.kill()
            await process.wait()
        for log in logs:
            log.close()
        if private.parent != private_parent or private.is_symlink():
            raise RuntimeError("Refusing cleanup outside the owned private root")
        shutil.rmtree(private)


def main(arguments=None):
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--control", required=True, type=Path)
    parser.add_argument("--output", required=True, type=Path)
    args = parser.parse_args(arguments)
    try:
        return asyncio.run(capture(args.control, args.output))
    except Exception as error:  # noqa: BLE001 -- process boundary: block and redact private diagnostics
        # An unsupported capture is never a successful paired comparison.
        frame = traceback.extract_tb(error.__traceback__)[-1]
        print(
            "J02_PAIRED_BLOCKED "
            + json.dumps(
                {
                    "error_class": type(error).__name__,
                    "file": Path(frame.filename).name,
                    "function": frame.name,
                    "line": frame.lineno,
                }
            ),
            flush=True,
        )
        return 2


if __name__ == "__main__":
    raise SystemExit(main())
