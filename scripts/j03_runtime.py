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
import secrets
import subprocess
import tempfile
import time
import urllib.error
import urllib.request
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]


def run(command, *, env=None, timeout=120, required=True):
    result = subprocess.run(
        command, cwd=ROOT, env=env, text=True, capture_output=True, timeout=timeout
    )
    if required and result.returncode:
        # Dependency output can contain injected values. Persist only a fixed diagnosis.
        raise RuntimeError(f"Command failed: {command[0]} (exit {result.returncode})")
    return result


def mint(env, *, tenant="runtime", perms=None, user="owner"):
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
            negative = env | {name: value}
            args = ["docker", "run", "--rm"]
            for field in names:
                args += ["--env", field]
            result = run([*args, image], env=negative, timeout=30, required=False)
            if result.returncode == 0:
                raise RuntimeError("Invalid production startup unexpectedly succeeded")
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
            run(
                [
                    *args,
                    "--volume",
                    str(ROOT / "backend/tests") + ":/app/tests:ro",
                    image,
                    "python",
                    "-m",
                    "pytest",
                    "tests/security/test_byok_rotation.py",
                    "-q",
                    "--tb=no",
                ],
                env=testenv,
            )
            report["checks"].append(
                "live Redis rotation/concurrency/CAS/fault/recovery suite"
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
            check_settings = "from app.core.config import get_settings; import os; s=get_settings(); assert all(getattr(s,k)==os.environ[k] for k in ('JWT_SECRET_KEY','INTERNAL_GATEWAY_SECRET','FINNAPIGO_SERVICE_SECRET','AUDIT_HMAC_KEY','BYOK_MASTER_KEY','BYOK_MASTER_KEY_ID')); print('SETTINGS_MATCH')"
            run(
                [
                    *compose,
                    "exec",
                    "-T",
                    "jakeai-backend",
                    "python",
                    "-c",
                    check_settings,
                ],
                env=env,
            )
            report["checks"].append(
                "production image process settings match injected synthetic material"
            )
            token, canary = mint(env), secrets.token_urlsafe(24)
            code, body = http(
                base,
                "/api/v1/byok/keys",
                token,
                {"provider": "openai", "api_key": canary},
            )
            assert code == 201 and canary not in json.dumps(body)
            for denied in [mint(env, perms=[]), mint(env, user="member")]:
                assert http(base, "/api/v1/byok/keys", denied)[0] == 403
            code, body = http(base, "/api/v1/byok/keys", mint(env, tenant="other"))
            assert code == 200 and not any(item["configured"] for item in body["keys"])
            run([*compose, "restart", "jakeai-backend", "byok-redis"], env=env)
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
    except Exception as error:
        args.output.parent.mkdir(parents=True, exist_ok=True)
        args.output.write_text(
            json.dumps(
                {"result": "BLOCKED_OR_FAILED", "error_type": type(error).__name__}
            )
            + "\n"
        )
        print("J03 runtime BLOCKED_OR_FAILED: " + type(error).__name__)
        raise SystemExit(1) from None
