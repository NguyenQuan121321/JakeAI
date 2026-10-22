"""Rehearse synthetic production Compose startup on the exact CI-scanned image.

Uses isolated project/container/volume names. No live providers, production
settings, credentials, external service changes, or live rotation are involved.
Requires an existing Docker engine; never installs infrastructure.
"""

import argparse
import base64
import hashlib
import hmac
import json
import os
import re
import secrets
import subprocess
import tempfile
import time
import urllib.error
import urllib.request
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
CURRENT_STAGE = "initialization"


def stage(label):
    global CURRENT_STAGE
    CURRENT_STAGE = label
    print("J03 stage: " + label, flush=True)


def run(command, *, env=None, timeout=120, required=True):
    result = subprocess.run(
        command,
        cwd=ROOT,
        env=env,
        text=True,
        capture_output=True,
        timeout=timeout,
        check=False,
    )
    if required and result.returncode:
        # Dependency output can contain injected values. Persist only a fixed diagnosis.
        raise RuntimeError(f"Command failed: {command[0]} (exit {result.returncode})")
    return result


def suite_diagnostics(result):
    """Classify image test failures without echoing injected values or tracebacks."""
    captured = result.stdout + result.stderr
    return {
        "exit_code": result.returncode,
        "counts": {
            status: int(count)
            for count, status in re.findall(
                r"\b(\d+) (passed|failed|errors?|skipped)\b", captured
            )
        },
        "missing_native_libraries": [
            library
            for library in ("libstdc++.so.6", "libgomp.so.1")
            if library + ": cannot open shared object file" in captured
        ],
        "failed_groups": [
            name
            for name in (
                "tests/security/test_byok_rotation.py",
                "tests/security/test_byok_owner_listing.py",
                "tests/security/test_provider_credential_sources.py",
                "tests/unit/test_fastembed_pillow_compat.py",
                "tests/unit/test_rag_parsers.py",
            )
            if "FAILED " + name in captured or "ERROR " + name in captured
        ],
    }


def mint(env, *, tenant="runtime", perms=None, user="owner", roles=None):
    def encoded(value):
        return base64.urlsafe_b64encode(
            json.dumps(value, separators=(",", ":")).encode()
        ).rstrip(b"=")

    now = int(time.time())
    header = encoded({"alg": "HS256", "typ": "JWT"})
    body = encoded(
        {
            "sub": user,
            "uid": user,
            "tid": tenant,
            "type": "access",
            "iat": now,
            "exp": now + 600,
            "perms": perms if perms is not None else ["byok:read", "byok:write"],
            "roles": roles or [],
        }
    )
    signed = header + b"." + body
    return (
        signed
        + b"."
        + base64.urlsafe_b64encode(
            hmac.digest(env["JWT_SECRET_KEY"].encode(), signed, "sha256")
        ).rstrip(b"=")
    ).decode()


def http(base, path, token=None, data=None, method=None):
    headers = {"Content-Type": "application/json"}
    if token:
        headers["Authorization"] = f"Bearer {token}"
    request = urllib.request.Request(
        base + path,
        headers=headers,
        data=json.dumps(data).encode() if data is not None else None,
        method=method,
    )
    try:
        with urllib.request.urlopen(request, timeout=8) as response:
            return response.status, json.load(response)
    except urllib.error.HTTPError as error:
        return error.code, json.load(error)


def wait_http(base):
    for _ in range(45):
        try:
            if http(base, "/health/live")[0] == 200:
                return
        except (OSError, ValueError):
            pass
        time.sleep(1)
    raise RuntimeError("Synthetic production HTTP startup unavailable")


def rehearse(image, output):
    stage("existing Docker engine")
    run(["docker", "info"], timeout=15)
    env = os.environ.copy()
    for name in [
        "JWT_SECRET_KEY",
        "INTERNAL_GATEWAY_SECRET",
        "FINNAPIGO_SERVICE_SECRET",
        "AUDIT_HMAC_KEY",
    ]:
        env[name] = secrets.token_hex(32)
    old = base64.b64encode(secrets.token_bytes(32)).decode()
    current = base64.b64encode(secrets.token_bytes(32)).decode()
    env.update(
        ENVIRONMENT="production",
        BYOK_MASTER_KEY=old,
        BYOK_MASTER_KEY_ID="j03-old",
        BYOK_STORAGE_BACKEND="redis",
        BYOK_PREVIOUS_KEYS="{}",
        BYOK_RETIRED_KEY_IDS="[]",
        BYOK_RETIRED_KEY_HASHES="[]",
        BYOK_REDIS_URL="redis://byok-redis:6379/0",
    )
    names = [
        "ENVIRONMENT",
        "JWT_SECRET_KEY",
        "INTERNAL_GATEWAY_SECRET",
        "FINNAPIGO_SERVICE_SECRET",
        "AUDIT_HMAC_KEY",
        "BYOK_MASTER_KEY",
        "BYOK_MASTER_KEY_ID",
        "BYOK_STORAGE_BACKEND",
        "BYOK_REDIS_URL",
        "BYOK_PREVIOUS_KEYS",
        "BYOK_RETIRED_KEY_IDS",
        "BYOK_RETIRED_KEY_HASHES",
    ]
    report = {
        "source_sha": env.get("GITHUB_SHA", "local-uncommitted"),
        "image_id": run(
            ["docker", "image", "inspect", image, "--format", "{{.Id}}"]
        ).stdout.strip(),
        "checks": [],
    }
    # Default image command must exit nonzero before serving, for each absent/default secret.
    for name in names[1:7]:
        for value in ["", "replace-with-production-secret"]:
            stage("reject " + name + (" missing" if not value else " placeholder"))
            negative = env | {name: value}
            args = ["docker", "run", "--rm"]
            for field in names:
                args += ["--env", field]
            result = run([*args, image], env=negative, timeout=30, required=False)
            if result.returncode == 0:
                raise RuntimeError("Invalid production startup unexpectedly succeeded")
            assert "Production secrets require" in result.stderr, (
                "Startup failed outside the secret-validation boundary"
            )
            assert all(
                secret not in result.stdout + result.stderr
                for field, secret in negative.items()
                if field in names and len(secret) >= 32
            )
    report["checks"].append("12 actual image startup missing/default negatives")
    project = "j03-synthetic-" + secrets.token_hex(5)
    with tempfile.TemporaryDirectory(prefix="j03-runtime-") as temporary:
        override = Path(temporary) / "compose.json"
        override.write_text(
            json.dumps(
                {
                    "services": {
                        "jakeai-backend": {
                            "image": image,
                            "container_name": project + "-api",
                            "restart": "no",
                            "ports": ["127.0.0.1::8000"],
                        },
                        "jakeai-worker": {
                            "image": image,
                            "container_name": project + "-worker",
                            "restart": "no",
                        },
                        "redis": {
                            "container_name": project + "-cache",
                            "restart": "no",
                        },
                        "byok-redis": {
                            "container_name": project + "-vault",
                            "restart": "no",
                        },
                    }
                }
            )
        )
        compose = [
            "docker",
            "compose",
            "-p",
            project,
            "-f",
            str(ROOT / "docker-compose.prod.yml"),
            "-f",
            str(override),
        ]
        try:
            stage("production Compose mapping")
            rendered = json.loads(
                run([*compose, "config", "--format", "json"], env=env).stdout
            )
            for service in ["jakeai-backend", "jakeai-worker"]:
                actual = rendered["services"][service]["environment"]
                for name in names:
                    assert actual[name] == env[name]
            report["checks"].append(
                "actual production Compose maps intended settings for API and worker"
            )
            stage("isolated persistent Redis startup")
            run(
                [
                    *compose,
                    "up",
                    "-d",
                    "--no-build",
                    "--no-deps",
                    "byok-redis",
                    "redis",
                ],
                env=env,
            )
            # Use the built image and isolated live Redis for the fault/CAS/rotation suite.
            stage("real Redis concurrency, fault and rotation suite")
            testenv = env | {
                "ENVIRONMENT": "test",
                "J03_REDIS_URL": "redis://byok-redis:6379/15",
                "BYOK_STORAGE_BACKEND": "memory",
            }
            args = [
                "docker",
                "run",
                "--rm",
                "--network",
                project + "_jakeai-prod-network",
            ]
            for field in [*names, "J03_REDIS_URL"]:
                args += ["--env", field]
            storage_tests = run(
                [
                    *args,
                    "--volume",
                    str(ROOT / "backend/tests") + ":/app/tests:ro",
                    image,
                    "python",
                    "-m",
                    "pytest",
                    "tests/security/test_byok_rotation.py",
                    "tests/security/test_byok_owner_listing.py",
                    "tests/security/test_provider_credential_sources.py",
                    "tests/unit/test_fastembed_pillow_compat.py",
                    "tests/unit/test_rag_parsers.py",
                    "-q",
                    "--tb=short",
                    "-o",
                    "addopts=",
                ],
                env=testenv,
                required=False,
            )
            if storage_tests.returncode:
                print(
                    "J03 image suite failure: "
                    + json.dumps(suite_diagnostics(storage_tests)),
                    flush=True,
                )
                raise RuntimeError("Image regression suite failed")
            assert (
                "84 passed" in storage_tests.stdout
                and "skipped" not in storage_tests.stdout
            )
            report["storage_tests"] = (
                "84 passed; provider HTTP, owner listing, Pillow/PDF, memory and actual Redis; zero skips"
            )
            report["checks"].append(
                "live Redis rotation/concurrency/CAS/fault/recovery suite"
            )
            stage("production API and worker startup")
            run(
                [
                    *compose,
                    "up",
                    "-d",
                    "--no-build",
                    "--no-deps",
                    "jakeai-backend",
                    "jakeai-worker",
                ],
                env=env,
            )
            port = run(
                [*compose, "port", "jakeai-backend", "8000"], env=env
            ).stdout.strip()
            base = "http://" + port
            wait_http(base)
            check_settings = "from app.core.config import get_settings; import os; s=get_settings(); assert all(getattr(s,k)==os.environ[k] for k in ('JWT_SECRET_KEY','INTERNAL_GATEWAY_SECRET','FINNAPIGO_SERVICE_SECRET','AUDIT_HMAC_KEY','BYOK_MASTER_KEY','BYOK_MASTER_KEY_ID')); print('SETTINGS_MATCH')"
            for service in ["jakeai-backend", "jakeai-worker"]:
                run(
                    [*compose, "exec", "-T", service, "python", "-c", check_settings],
                    env=env,
                )
            report["checks"].append(
                "production image process settings match injected synthetic material"
            )
            token, canary = mint(env), secrets.token_urlsafe(24)
            stage("real HTTP authorization and encrypted persistence")
            code, body = http(
                base,
                "/api/v1/byok/keys",
                token,
                {"provider": "openai", "api_key": canary},
            )
            assert code == 201 and canary not in json.dumps(body)
            assert body["masked_key"] == "********"
            for path, data, method in [
                (
                    "/api/v1/byok/keys",
                    {"provider": "openai", "api_key": canary},
                    "POST",
                ),
                ("/api/v1/byok/keys/openai/rotate", {"new_api_key": canary}, "POST"),
                ("/api/v1/byok/keys/openai", None, "DELETE"),
            ]:
                assert (
                    http(base, path, mint(env, user="member"), data, method)[0] == 403
                )
            assert (
                http(
                    base,
                    "/api/v1/byok/keys/openai",
                    mint(env, tenant="other"),
                    method="DELETE",
                )[0]
                == 404
            )
            code, body = http(
                base,
                "/api/v1/byok/keys",
                token,
                {"provider": "openai", "api_key": canary},
            )
            assert code == 201 and canary not in json.dumps(body)
            code, body = http(
                base, "/api/v1/byok/keys/openai/rotate", token, {"new_api_key": canary}
            )
            assert code == 200 and body["masked_key"] == "********"
            assert http(base, "/api/v1/byok/keys", mint(env, perms=[]))[0] == 403
            assert (
                http(base, "/api/v1/byok/keys", mint(env, user="member"))[1]["keys"]
                == []
            )
            second_owner = mint(env, user="second-owner")
            assert (
                http(
                    base,
                    "/api/v1/byok/keys",
                    second_owner,
                    {"provider": "gemini", "api_key": canary},
                )[0]
                == 201
            )
            for identity, expected in [(token, "openai"), (second_owner, "gemini")]:
                status_code, listed = http(base, "/api/v1/byok/keys", identity)
                assert status_code == 200
                assert [row["provider"] for row in listed["keys"]] == [expected]
                assert listed["keys"][0]["masked_key"] == "********"
            delegate = mint(env, user="delegate", roles=["tenant_admin"])
            assert {
                row["provider"]
                for row in http(base, "/api/v1/byok/keys", delegate)[1]["keys"]
                if row["configured"]
            } == {"openai", "gemini"}
            assert (
                http(base, "/api/v1/byok/keys/gemini", token, method="DELETE")[0] == 403
            )
            assert (
                http(base, "/api/v1/byok/keys/gemini", second_owner, method="DELETE")[0]
                == 200
            )
            code, body = http(base, "/api/v1/byok/keys", mint(env, tenant="other"))
            assert code == 200 and not any(item["configured"] for item in body["keys"])
            # The production API deliberately exits if its vault is unavailable
            # at startup. `compose restart A B` restarts both concurrently and
            # does not reapply depends_on health ordering. Restore the vault
            # first, then restart the fail-closed application against it.
            stage("persistent vault restart")
            run([*compose, "restart", "byok-redis"], env=env)
            for _ in range(15):
                ready = run(
                    [*compose, "exec", "-T", "byok-redis", "redis-cli", "ping"],
                    env=env,
                    required=False,
                )
                if ready.returncode == 0 and ready.stdout.strip() == "PONG":
                    break
                time.sleep(1)
            else:
                raise RuntimeError("Synthetic vault restart unavailable")
            stage("production API restart after vault recovery")
            run([*compose, "restart", "jakeai-backend"], env=env)
            port = run(
                [*compose, "port", "jakeai-backend", "8000"], env=env
            ).stdout.strip()
            base = "http://" + port
            wait_http(base)
            for _ in range(10):
                if http(base, "/api/v1/byok/keys", token)[0] == 200:
                    break
                time.sleep(1)
            else:
                raise RuntimeError(
                    "Persisted synthetic record unavailable after process/store restart"
                )
            report["checks"].append(
                "real HTTP authorization and persisted encrypted record across process/store restart"
            )
            env.update(
                BYOK_MASTER_KEY=current,
                BYOK_MASTER_KEY_ID="j03-current",
                BYOK_PREVIOUS_KEYS=json.dumps({"j03-old": old}),
            )
            run(
                [
                    *compose,
                    "up",
                    "-d",
                    "--no-build",
                    "--no-deps",
                    "jakeai-backend",
                    "jakeai-worker",
                ],
                env=env,
            )
            port = run(
                [*compose, "port", "jakeai-backend", "8000"], env=env
            ).stdout.strip()
            base = "http://" + port
            wait_http(base)
            assert http(base, "/api/v1/byok/keys", token)[0] == 200
            stage("current/previous key restart and process migration")
            migration = run(
                [
                    *compose,
                    "exec",
                    "-T",
                    "jakeai-backend",
                    "python",
                    "-m",
                    "app.core.byok_migrate",
                ],
                env=env,
            )
            assert (
                sum(
                    json.loads(line)["migrated"]
                    for line in migration.stdout.splitlines()
                )
                == 1
            )
            run([*compose, "stop", "byok-redis"], env=env)
            stage("actual vault outage and recovery")
            assert http(base, "/api/v1/byok/keys", token)[0] == 503
            assert (
                http(
                    base,
                    "/api/v1/byok/keys",
                    token,
                    {"provider": "openai", "api_key": canary},
                )[0]
                == 503
            )
            assert (
                http(base, "/api/v1/byok/keys/openai", token, method="DELETE")[0] == 503
            )
            run([*compose, "start", "byok-redis"], env=env)
            time.sleep(2)
            assert http(base, "/api/v1/byok/keys", token)[0] == 200
            env.update(
                BYOK_PREVIOUS_KEYS="{}",
                BYOK_RETIRED_KEY_IDS='["j03-old"]',
                BYOK_RETIRED_KEY_HASHES=json.dumps(
                    [hashlib.sha256(base64.b64decode(old)).hexdigest()]
                ),
            )
            run(
                [
                    *compose,
                    "up",
                    "-d",
                    "--no-build",
                    "--no-deps",
                    "jakeai-backend",
                    "jakeai-worker",
                ],
                env=env,
            )
            base = (
                "http://"
                + run(
                    [*compose, "port", "jakeai-backend", "8000"], env=env
                ).stdout.strip()
            )
            wait_http(base)
            assert http(base, "/api/v1/byok/keys", token)[0] == 200
            assert (
                http(base, "/api/v1/byok/keys/openai", token, method="DELETE")[0] == 200
            )
            logs = run([*compose, "logs", "--no-color"], env=env).stdout
            for value in [canary, token, old, current, env["JWT_SECRET_KEY"]]:
                assert value not in logs
            report["checks"].append(
                "current/previous rotation, process migration, outage/recovery, retirement and masked logs"
            )
            stage("retirement, masked diagnostics and production worker")
            state = run(
                [
                    "docker",
                    "inspect",
                    project + "-worker",
                    "--format",
                    "{{.State.Running}}",
                ]
            ).stdout.strip()
            assert state == "true"
            report["checks"].append(
                "production worker startup with the same injected configuration"
            )
        finally:
            run(
                [*compose, "down", "--volumes", "--remove-orphans"],
                env=env,
                required=False,
            )
    report["result"] = "PASS"
    output.parent.mkdir(parents=True, exist_ok=True)
    output.write_text(json.dumps(report, indent=2) + "\n")
    print(json.dumps(report, indent=2))


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--image", default="jakeai-backend:test")
    parser.add_argument(
        "--output", type=Path, default=ROOT / "reports/j03-runtime.json"
    )
    args = parser.parse_args()
    try:
        rehearse(args.image, args.output)
    except Exception as error:  # noqa: BLE001 -- diagnostics must never echo injected values
        args.output.parent.mkdir(parents=True, exist_ok=True)
        args.output.write_text(
            json.dumps(
                {
                    "result": "BLOCKED"
                    if CURRENT_STAGE == "existing Docker engine"
                    else "FAIL",
                    "stage": CURRENT_STAGE,
                    "source_sha": os.getenv("GITHUB_SHA", "local"),
                    "error_type": type(error).__name__,
                }
            )
            + "\n"
        )
        print(
            "J03 runtime incomplete at " + CURRENT_STAGE + ": " + type(error).__name__
        )
        raise SystemExit(1) from None
