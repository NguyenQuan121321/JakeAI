"""J02-owned actual Finn/Jake rehearsal. Never starts Docker on a workstation.

Uses the F02 fixture concepts, without importing or changing Finn's guarded scripts.
Only allowlisted hashes/status receipts leave RUNNER_TEMP. No credential artifacts.
"""

import base64
import hashlib
import hmac
import ipaddress
import json
import os
import re
import secrets
import shutil
import ssl
import subprocess
import sys
import time
import urllib.error
import urllib.request
from datetime import datetime, timezone
from pathlib import Path

REPO = Path(__file__).resolve().parents[1]
FINN_SHA = "b79b0dbea09cbf1464baa4de9ab76573c8b6fd32"
MYSQL = "mysql@sha256:a0225d1ea6631c8bc2385dc4c2faba17bbf1834ecf369e1659a9a382bd8d5dd7"
REDIS = "redis@sha256:21090af93f8324db2f0f0f4f38a7c60369d47d917e000c3423d89d2ae2883537"
MAIL = "axllent/mailpit@sha256:0790692be935ea4420d085694f7985b1f692ca6a8771ab0e0bd8ba75ac180498"


def identity():
    if (
        os.environ.get("GITHUB_ACTIONS") != "true"
        or os.environ.get("RUNNER_ENVIRONMENT") != "github-hosted"
        or os.environ.get("RUNNER_OS") != "Linux"
        or os.environ.get("GITHUB_EVENT_NAME") != "pull_request"
        or os.environ.get("GITHUB_REPOSITORY") != "NguyenQuan121321/JakeAI"
    ):
        raise RuntimeError("Standard hosted PR job required")
    event = json.loads(Path(os.environ["GITHUB_EVENT_PATH"]).read_text())
    pr = event["pull_request"]
    if (
        event["repository"]["private"]
        or pr["head"]["repo"]["full_name"] != "NguyenQuan121321/JakeAI"
        or pr["head"]["ref"] != "codex/j02-identity-authorization"
        or pr["base"]["ref"] != "main"
    ):
        raise RuntimeError("Public same-repository exact-branch guard")
    run, attempt = os.environ["GITHUB_RUN_ID"], os.environ["GITHUB_RUN_ATTEMPT"]
    if not re.fullmatch(r"[0-9]+", run) or not re.fullmatch(r"[0-9]+", attempt):
        raise RuntimeError("Run identity guard")
    project = "j02-" + run + "-" + attempt
    parent = Path(os.environ["RUNNER_TEMP"]).resolve()
    root = parent / project
    if root.is_symlink() or root.resolve().parent != parent:
        raise RuntimeError("Owned runtime path guard")
    return project, root


def emit(kind, **fields):
    line = "J02_RECEIPT " + json.dumps(
        {"kind": kind, "observed_unix": int(time.time()), **fields},
        separators=(",", ":"),
    )
    print(line, flush=True)
    if os.environ.get("GITHUB_STEP_SUMMARY"):
        with open(os.environ["GITHUB_STEP_SUMMARY"], "a", encoding="utf-8") as stream:
            stream.write("```text\n" + line + "\n```\n")


def command(args, *, data=None, timeout=180, check=True):
    result = subprocess.run(
        args, input=data, capture_output=True, timeout=timeout, cwd=REPO, check=False
    )
    if check and result.returncode:
        emit(
            "command_failure",
            executable=Path(args[0]).name,
            exit_code=result.returncode,
        )
        raise RuntimeError("Owned rehearsal command failed; diagnostics withheld")
    return result


def private(path, value, mode=0o600):
    path.write_text(value, encoding="utf-8")
    path.chmod(mode)


def mask(value):
    print("::add-mask::" + value, flush=True)
    return value


def compose(*args, data=None, check=True, timeout=180):
    project, root = identity()
    return command(
        ["docker", "compose", "-p", project, "-f", str(root / "compose.json"), *args],
        data=data,
        check=check,
        timeout=timeout,
    )


def hostname(service):
    return service + "-" + identity()[0] + ".test"


def hosts_update(service=None, address=None):
    project, _ = identity()
    script = """import json,pathlib,sys
project=sys.argv[1];name,address=json.load(sys.stdin);p=pathlib.Path('/etc/hosts')
marker='# '+project;lines=p.read_text().splitlines()
if name is None:lines=[line for line in lines if not line.endswith(marker)]
else:
 lines=[line for line in lines if not (line.endswith(marker) and name in line.split())]
 lines.append(address+' '+name+' '+marker)
p.write_text('\\n'.join(lines)+'\\n')
"""
    command(
        ["sudo", "python3", "-c", script, project],
        data=json.dumps([hostname(service) if service else None, address]).encode(),
    )


def configuration(root, keys, last=None, *, remove=False, state_old=False):
    current = "old" if last is None else "new"
    finn = {
        "GIN_MODE": "release",
        "SERVER_PORT": "8443",
        "SERVER_TLS_CERT_FILE": "/run/tls/cert.pem",
        "SERVER_TLS_KEY_FILE": "/run/tls/key.pem",
        "SSL_CERT_FILE": "/run/tls/ca.crt",
        "DB_HOST": "mysql",
        "DB_PORT": "3306",
        "DB_NAME": "j02",
        "DB_USER": "j02",
        "DB_PASSWORD": keys["mysql-app"],
        "DB_MAX_OPEN_CONNS": "20",
        "DB_MAX_IDLE_CONNS": "5",
        "MIGRATE_AUTO": "false",
        "JWT_ALGORITHM": "HS256",
        "JWT_ISSUER": "finnapigo",
        "JWT_KEY_ID": "sign-" + current,
        "JWT_SECRET": keys["sign-" + current],
        "IDENTITY_STATE_KEY_ID": "state-" + current,
        "IDENTITY_STATE_SECRET": keys["state-" + current],
        "ACCESS_TOKEN_TTL": "15m",
        "RECOVERY_CODE_KEY": keys["recovery"],
        "METRICS_TOKEN": keys["metrics"],
        "AUDIT_KEY_ID": "audit",
        "AUDIT_SIGNING_KEYS": json.dumps({"audit": keys["audit"]}),
        "AUDIT_CHECKPOINT_KEY_ID": "checkpoint",
        "AUDIT_CHECKPOINT_KEY": keys["checkpoint"],
        "AUDIT_RETENTION_DAYS": "0",
        "REDIS_URL": "redis://:" + keys["redis"] + "@redis:6379/0",
        "SMTP_HOST": "mail",
        "SMTP_PORT": "1025",
        "SMTP_FROM": "j02@example.invalid",
        "REQUIRE_EMAIL_VERIFIED": "false",
        "BREACHED_PASSWORD_CHECK": "false",
    }
    jake = {
        "ENVIRONMENT": "production",
        "JWT_ALGORITHM": "HS256",
        "JWT_ISSUER": "finnapigo",
        "JWT_AUDIENCE": "jakeai-service",
        "JWT_KEY_ID": "sign-" + current,
        "JWT_SECRET_KEY": keys["sign-" + current],
        "IDENTITY_STATE_URL": "https://finn-a:8443/api/v1/identity/introspect",
        "IDENTITY_STATE_KEY_ID": "state-" + ("old" if state_old else current),
        "IDENTITY_STATE_SECRET": keys["state-" + ("old" if state_old else current)],
        "IDENTITY_STATE_CA_FILE": "/run/tls/ca.crt",
        "IDENTITY_STATE_TIMEOUT_SECONDS": "3",
        "INTERNAL_GATEWAY_SECRET": keys["internal"],
        "FINNAPIGO_SERVICE_SECRET": keys["legacy-service"],
        "AUDIT_HMAC_KEY": keys["jake-audit"],
        "BYOK_MASTER_KEY": keys["byok"],
        "BYOK_MASTER_KEY_ID": "j02-master",
        "BYOK_STORAGE_BACKEND": "redis",
        "BYOK_REDIS_URL": "redis://:" + keys["vault"] + "@vault:6379/0",
        "REDIS_URL": "redis://:" + keys["redis"] + "@redis:6379/2",
        "LOCAL_MODEL_ENABLED": "false",
        "COST_AWARE_ROUTING_ENABLED": "false",
        "J02_SYNTHETIC_PROVIDER": "1",
        "PYTHONPATH": "/app:/run/j02",
    }
    if last is not None and not remove:
        utc = lambda n: datetime.fromtimestamp(n, timezone.utc).strftime(
            "%Y-%m-%dT%H:%M:%SZ"
        )
        finn.update(
            JWT_PREVIOUS_KEY_ID="sign-old",
            JWT_SECRET_PREVIOUS=keys["sign-old"],
            JWT_PREVIOUS_LAST_ISSUED_AT=utc(last),
            IDENTITY_STATE_PREVIOUS_KEY_ID="state-old",
            IDENTITY_STATE_PREVIOUS_SECRET=keys["state-old"],
            IDENTITY_STATE_PREVIOUS_UNTIL=utc(last + 930),
        )
        jake.update(
            JWT_PREVIOUS_KEY_ID="sign-old",
            JWT_SECRET_PREVIOUS=keys["sign-old"],
            JWT_PREVIOUS_LAST_ISSUED_AT=str(last),
        )
    for name, values in [("finn", finn), ("jake", jake)]:
        private(
            root / (name + ".env"),
            "\n".join(k + "=" + v for k, v in values.items()) + "\n",
        )
    emit(
        "config",
        phase="baseline" if last is None else "removed" if remove else "overlap",
        final_old_issuance_unix=last,
        immutable_deadline_unix=last + 930 if last else None,
        finn_env_sha256=hashlib.sha256((root / "finn.env").read_bytes()).hexdigest(),
        jake_env_sha256=hashlib.sha256((root / "jake.env").read_bytes()).hexdigest(),
    )


def prepare():
    project, root = identity()
    root.mkdir(mode=0o700, exist_ok=False)
    keys = {
        n: mask(base64.b64encode(secrets.token_bytes(32)).decode())
        for n in [
            "sign-old",
            "sign-new",
            "state-old",
            "state-new",
            "audit",
            "checkpoint",
            "metrics",
            "byok",
        ]
    }
    keys.update(
        {
            n: mask(secrets.token_hex(32))
            for n in [
                "recovery",
                "redis",
                "vault",
                "mysql-root",
                "mysql-app",
                "internal",
                "legacy-service",
                "jake-audit",
            ]
        }
    )
    keys["password"] = mask("J02!aZ9-" + secrets.token_urlsafe(30))
    private(root / "keys.json", json.dumps(keys))
    for name in ["mysql-root", "mysql-app"]:
        private(root / name, keys[name], 0o444)
    private(
        root / "mysql-client.cnf",
        "[client]\nuser=root\npassword=" + keys["mysql-root"] + "\n",
        0o444,
    )
    private(
        root / "redis.conf",
        "bind 0.0.0.0\nprotected-mode yes\nappendonly yes\nmaxmemory 128mb\nmaxmemory-policy noeviction\nrequirepass "
        + keys["redis"]
        + "\n",
        0o444,
    )
    private(
        root / "vault.conf",
        "bind 0.0.0.0\nprotected-mode yes\nappendonly yes\nappendfsync always\nmaxmemory 64mb\nmaxmemory-policy noeviction\nrequirepass "
        + keys["vault"]
        + "\n",
        0o444,
    )
    tls = root / "tls"
    tls.mkdir(mode=0o755)
    command(
        [
            "openssl",
            "req",
            "-x509",
            "-newkey",
            "rsa:3072",
            "-nodes",
            "-sha256",
            "-days",
            "2",
            "-subj",
            "/CN=" + project,
            "-keyout",
            str(tls / "ca.key"),
            "-out",
            str(tls / "ca.crt"),
            "-addext",
            "basicConstraints=critical,CA:TRUE,pathlen:0",
            "-addext",
            "keyUsage=critical,keyCertSign,cRLSign",
            "-addext",
            "subjectKeyIdentifier=hash",
        ]
    )
    (tls / "ca.key").chmod(0o600)
    for name in ["finn-a", "jake", "mail"]:
        private(
            tls / (name + ".ext"),
            "subjectAltName=DNS:localhost,DNS:"
            + name
            + ",DNS:"
            + hostname(name)
            + ",IP:127.0.0.1\n"
            "basicConstraints=critical,CA:FALSE\nkeyUsage=critical,digitalSignature,keyEncipherment\nextendedKeyUsage=serverAuth\n"
            "subjectKeyIdentifier=hash\nauthorityKeyIdentifier=keyid,issuer\n",
        )
        command(
            [
                "openssl",
                "req",
                "-new",
                "-newkey",
                "rsa:3072",
                "-nodes",
                "-subj",
                "/CN=" + name,
                "-keyout",
                str(tls / (name + ".key")),
                "-out",
                str(tls / (name + ".csr")),
            ]
        )
        command(
            [
                "openssl",
                "x509",
                "-req",
                "-in",
                str(tls / (name + ".csr")),
                "-CA",
                str(tls / "ca.crt"),
                "-CAkey",
                str(tls / "ca.key"),
                "-CAcreateserial",
                "-days",
                "2",
                "-sha256",
                "-extfile",
                str(tls / (name + ".ext")),
                "-out",
                str(tls / (name + ".crt")),
            ]
        )
        (tls / (name + ".key")).chmod(0o644)
        command(
            [
                "openssl",
                "verify",
                "-x509_strict",
                "-CAfile",
                str(tls / "ca.crt"),
                str(tls / (name + ".crt")),
            ]
        )
    configuration(root, keys)
    common = {
        "read_only": True,
        "cap_drop": ["ALL"],
        "security_opt": ["no-new-privileges:true"],
        "networks": ["isolated"],
        "restart": "no",
        "tmpfs": ["/tmp"],
    }

    def tls_mounts(name):
        return [
            str(tls / (name + ".crt")) + ":/run/tls/cert.pem:ro",
            str(tls / (name + ".key")) + ":/run/tls/key.pem:ro",
            str(tls / "ca.crt") + ":/run/tls/ca.crt:ro",
        ]

    services = {
        "mysql": {
            "image": "j02-mysql:" + project,
            "user": "999:999",
            "networks": ["isolated"],
            "restart": "no",
            "mem_limit": "1g",
            "security_opt": ["no-new-privileges:true"],
            "environment": {
                "MYSQL_ROOT_PASSWORD_FILE": "/run/secrets/mysql-root",
                "MYSQL_DATABASE": "j02",
                "MYSQL_USER": "j02",
                "MYSQL_PASSWORD_FILE": "/run/secrets/mysql-app",
            },
            "volumes": [
                "mysql-data:/var/lib/mysql",
                *[
                    str(root / n) + ":/run/secrets/" + n + ":ro"
                    for n in ["mysql-root", "mysql-app", "mysql-client.cnf"]
                ],
            ],
            "command": ["--innodb-buffer-pool-size=134217728", "--max-connections=40"],
        },
        "redis": {
            **common,
            "image": REDIS,
            "user": "999:999",
            "mem_limit": "256m",
            "command": ["redis-server", "/run/secrets/redis.conf"],
            "volumes": [
                "redis-data:/data",
                str(root / "redis.conf") + ":/run/secrets/redis.conf:ro",
            ],
        },
        "vault": {
            **common,
            "image": REDIS,
            "user": "999:999",
            "mem_limit": "192m",
            "command": ["redis-server", "/run/secrets/vault.conf"],
            "volumes": [
                "vault-data:/data",
                str(root / "vault.conf") + ":/run/secrets/vault.conf:ro",
            ],
        },
        "mail": {
            **common,
            "image": MAIL,
            "user": "10001:10001",
            "mem_limit": "128m",
            "volumes": tls_mounts("mail"),
            "environment": {
                "MP_SMTP_TLS_CERT": "/run/tls/cert.pem",
                "MP_SMTP_TLS_KEY": "/run/tls/key.pem",
                "MP_SMTP_REQUIRE_STARTTLS": "true",
                "MP_DISABLE_VERSION_CHECK": "true",
            },
        },
        "finn-a": {
            **common,
            "image": "j02-finn:" + project,
            "user": "10001:10001",
            "mem_limit": "384m",
            "env_file": [str(root / "finn.env")],
            "ports": ["127.0.0.1:18443:8443"],
            "volumes": tls_mounts("finn-a"),
        },
        "jake": {
            **common,
            "image": "j02-jake:" + project,
            "user": "1000:1000",
            "mem_limit": "1200m",
            "healthcheck": {"disable": True},
            "env_file": [str(root / "jake.env")],
            "ports": ["127.0.0.1:19443:8443"],
            "volumes": [
                *tls_mounts("jake"),
                str(REPO / "scripts/j02_provider_fixture.py")
                + ":/run/j02/j02_provider_fixture.py:ro",
            ],
            "command": [
                "uvicorn",
                "j02_provider_fixture:app",
                "--host",
                "0.0.0.0",
                "--port",
                "8443",
                "--ssl-certfile",
                "/run/tls/cert.pem",
                "--ssl-keyfile",
                "/run/tls/key.pem",
                "--no-access-log",
            ],
        },
    }
    private(
        root / "compose.json",
        json.dumps(
            {
                "services": services,
                "networks": {"isolated": {"internal": True}},
                "volumes": {"mysql-data": {}, "redis-data": {}, "vault-data": {}},
            }
        ),
    )
    actual_finn = (
        command(["git", "-C", "finn-source", "rev-parse", "HEAD"])
        .stdout.decode()
        .strip()
    )
    if actual_finn != FINN_SHA:
        raise RuntimeError("Pinned Finn source mismatch")
    emit(
        "source",
        finn=actual_finn,
        tested_merge=command(["git", "rev-parse", "HEAD"]).stdout.decode().strip(),
        tested_tree=command(["git", "rev-parse", "HEAD^{tree}"])
        .stdout.decode()
        .strip(),
        head_sha=json.loads(Path(os.environ["GITHUB_EVENT_PATH"]).read_text())[
            "pull_request"
        ]["head"]["sha"],
        provider_fixture_sha256=hashlib.sha256(
            (REPO / "scripts/j02_provider_fixture.py").read_bytes()
        ).hexdigest(),
        mysql_base=MYSQL,
        mysql_recipe_sha256=hashlib.sha256(
            (REPO / "scripts/j02/mysql.Dockerfile").read_bytes()
        ).hexdigest(),
        redis=REDIS,
        cost="USD0 public standard ubuntu-24.04; no new uploads/caches",
    )


class NoRedirect(urllib.request.HTTPRedirectHandler):
    def redirect_request(self, req, fp, code, msg, headers, newurl):
        return None


def decode(token):
    return json.loads(base64.urlsafe_b64decode(token.split(".")[1] + "=="))


def signed(payload, kid, secret):
    enc = lambda obj: base64.urlsafe_b64encode(
        json.dumps(obj, separators=(",", ":")).encode()
    ).rstrip(b"=")
    data = enc({"alg": "HS256", "typ": "JWT", "kid": kid}) + b"." + enc(payload)
    return mask(
        (
            data
            + b"."
            + base64.urlsafe_b64encode(
                hmac.digest(base64.b64decode(secret), data, "sha256")
            ).rstrip(b"=")
        ).decode()
    )


class Rehearsal:
    def __init__(self):
        self.project, self.root = identity()
        self.keys = json.loads((self.root / "keys.json").read_text())
        for value in self.keys.values():
            mask(value)
        self.http = urllib.request.build_opener(
            urllib.request.ProxyHandler({}),
            NoRedirect(),
            urllib.request.HTTPSHandler(
                context=ssl.create_default_context(cafile=str(self.root / "tls/ca.crt"))
            ),
        )
        self.last = None
        self.count = 0

    def request(
        self, service, path, *, token=None, body=None, tenant="j02-a", method=None
    ):
        headers = {"Content-Type": "application/json", "X-Tenant-ID": tenant}
        if token:
            headers["Authorization"] = "Bearer " + token
        origin = (
            "https://" + hostname("finn-a" if service == "finn" else "jake") + ":8443"
        )
        req = urllib.request.Request(
            origin + path,
            headers=headers,
            data=json.dumps(body).encode() if body is not None else None,
            method=method,
        )
        try:
            response = self.http.open(req, timeout=8)
        except urllib.error.HTTPError as error:
            response = error
        with response:
            raw = response.read(65537)
            if len(raw) > 65536:
                raise RuntimeError("Response size bound")
            try:
                result = json.loads(raw)
            except ValueError:
                result = None
            return response.code, result

    def check(self, name, actual, expected):
        self.count += 1
        emit(
            "case",
            case=name,
            actual=actual,
            expected=expected,
            status="PASS" if actual == expected else "FAIL",
        )
        if actual != expected:
            raise RuntimeError("Rehearsal assertion: " + name)

    def sql(self, sql):
        return compose(
            "exec",
            "-T",
            "mysql",
            "mysql",
            "--defaults-extra-file=/run/secrets/mysql-client.cnf",
            "-N",
            "j02",
            data=sql.encode(),
        ).stdout.decode()

    def diagnostics(self, actual_service, cid, last_status=None, transport=None):
        raw = compose(
            "logs", "--no-color", "--tail", "60", actual_service, check=False
        ).stdout.decode(errors="replace")
        state = json.loads(command(["docker", "inspect", cid]).stdout)[0]["State"]
        emit(
            "readiness_failure",
            service=actual_service,
            last_status=last_status,
            transport_error_type=transport,
            state={k: state[k] for k in ["Status", "Running", "ExitCode", "OOMKilled"]},
            progress=[
                p
                for p in [
                    "database connected",
                    "store: Redis-backed",
                    "email: SMTP notifier enabled",
                    "server listening",
                    "finnapigo fatal",
                    "server error",
                    "server stopped cleanly",
                ]
                if p in raw
            ],
            categories=[
                p
                for p in [
                    "permission denied",
                    "certificate",
                    "audit",
                    "jwt",
                    "redis",
                    "mysql",
                    "byok_storage_unavailable",
                    "read-only",
                    "connection refused",
                    "no such file",
                ]
                if p in raw.lower()
            ],
        )

    def ready(self, service):
        actual_service = "finn-a" if service == "finn" else "jake"
        cid = compose("ps", "--all", "-q", actual_service).stdout.decode().strip()
        info = json.loads(command(["docker", "inspect", cid]).stdout)[0]
        if info["Config"]["Labels"]["com.docker.compose.project"] != self.project:
            raise RuntimeError("Owned readiness route guard")
        if not info["State"]["Running"]:
            self.diagnostics(actual_service, cid)
            raise RuntimeError("Actual release exited before readiness")
        networks = info["NetworkSettings"]["Networks"]
        if len(networks) != 1:
            raise RuntimeError("Single private route required")
        network = next(iter(networks.values()))
        owned = json.loads(
            command(["docker", "network", "inspect", network["NetworkID"]]).stdout
        )[0]
        address = network["IPAddress"]
        if (
            not owned["Internal"]
            or owned["Labels"]["com.docker.compose.project"] != self.project
            or not ipaddress.ip_address(address).is_private
        ):
            raise RuntimeError("Private readiness route required")
        hosts_update(actual_service, address)
        emit(
            "owned_direct_route",
            service=actual_service,
            container_id=cid,
            address_sha256=hashlib.sha256(address.encode()).hexdigest(),
        )
        deadline = time.monotonic() + 120
        last_status, transport = None, None
        while time.monotonic() < deadline:
            try:
                last_status = self.request(
                    service, "/healthz" if service == "finn" else "/health/live"
                )[0]
                if last_status == 200:
                    self.inventory("finn-a" if service == "finn" else "jake")
                    return
            except (OSError, ValueError) as error:
                transport = type(error).__name__
            time.sleep(2)
        self.diagnostics(actual_service, cid, last_status, transport)
        raise RuntimeError("Actual release readiness: " + service)

    def inventory(self, service):
        cid = compose("ps", "-q", service).stdout.decode().strip()
        info = json.loads(command(["docker", "inspect", cid]).stdout)[0]
        if info["Config"]["Labels"]["com.docker.compose.project"] != self.project:
            raise RuntimeError("Owned container guard")
        bindings = info["HostConfig"]["PortBindings"] or {}
        if not all(
            b["HostIp"] == "127.0.0.1"
            for values in bindings.values()
            for b in (values or [])
        ):
            raise RuntimeError("Loopback publishing required")
        for network in info["NetworkSettings"]["Networks"].values():
            net = json.loads(
                command(["docker", "network", "inspect", network["NetworkID"]]).stdout
            )[0]
            if (
                not net["Internal"]
                or net["Labels"]["com.docker.compose.project"] != self.project
            ):
                raise RuntimeError("Private owned network required")
        expected = (
            command(
                [
                    "docker",
                    "image",
                    "inspect",
                    "j02-"
                    + ("finn" if service == "finn-a" else "jake")
                    + ":"
                    + self.project,
                    "--format",
                    "{{.Id}}",
                ]
            )
            .stdout.decode()
            .strip()
        )
        self.check("scanned-image-identity-" + service, info["Image"], expected)
        emit(
            "container",
            service=service,
            container_id=cid,
            image_config_id=info["Image"],
            loopback_only=True,
            private_network=True,
        )

    def login(self, tenant="j02-a"):
        time.sleep(0.3)
        status, payload = self.request(
            "finn",
            "/api/v1/auth/login",
            tenant=tenant,
            body={
                "email": tenant + "@example.invalid",
                "password": self.keys["password"],
            },
        )
        self.check("actual-login-" + tenant, status, 200)
        data = payload.get("data", payload)
        if "tokens" in data:
            data = data["tokens"]
        access = data.get("accessToken") or data.get("access_token")
        refresh = data.get("refreshToken") or data.get("refresh_token")
        if not access or not refresh:
            raise RuntimeError("Actual token pair shape")
        mask(access)
        mask(refresh)
        emit(
            "issuance",
            tenant=tenant,
            iat=decode(access)["iat"],
            token_sha256=hashlib.sha256(access.encode()).hexdigest(),
        )
        return access, refresh

    def matrix(self, token, label):
        self.check(
            label + "-actual-model-list",
            self.request("jake", "/v1/models", token=token, tenant="forged")[0],
            200,
        )
        self.check(
            label + "-byok-read",
            self.request("jake", "/api/v1/byok/keys", token=token)[0],
            200,
        )
        payload = decode(token)
        key = self.keys["sign-old" if self.last is None else "sign-new"]
        kid = "sign-old" if self.last is None else "sign-new"
        for name in [
            "contract_ver",
            "iss",
            "aud",
            "sub",
            "uid",
            "type",
            "tid",
            "exp",
            "iat",
            "nbf",
            "jti",
            "sid",
            "pwdver",
            "auth_epoch",
            "perms",
        ]:
            value = dict(payload)
            value.pop(name)
            self.check(
                label + "-missing-" + name,
                self.request("jake", "/v1/models", token=signed(value, kid, key))[0],
                401,
            )
        for name, value in [
            ("uid", True),
            ("tid", "j02-b"),
            ("type", "sudo"),
            ("type", "service"),
            ("type", "obo"),
            ("permissions", []),
            ("UID", payload["uid"]),
            ("auth_epoch", payload["auth_epoch"] + 1),
        ]:
            self.check(
                label + "-wrong-" + name + "-" + str(value)[:12],
                self.request(
                    "jake",
                    "/v1/models",
                    token=signed(dict(payload, **{name: value}), kid, key),
                )[0],
                401,
            )

    def run(self):
        compose("up", "-d", "mysql", "redis", "vault", "mail")
        deadline = time.monotonic() + 120
        while time.monotonic() < deadline:
            try:
                if self.sql("SELECT 1;").strip() == "1":
                    break
            except RuntimeError:
                pass
            time.sleep(2)
        else:
            raise RuntimeError("MySQL readiness")
        for operation in [("up",), ("version",), ("check", "up")]:
            compose(
                "run",
                "--rm",
                "--no-deps",
                "--entrypoint",
                "/app/migrate",
                "finn-a",
                *operation,
            )
            emit("migration", operation=list(operation), status="PASS")
        compose("up", "-d", "finn-a")
        self.ready("finn")
        emit("issuer_first", status="actual Finn ready before actual Jake")
        self.sql(
            "INSERT INTO tenants(id,slug,name,is_active) VALUES ('j02-a','j02-a','J02 A',1),('j02-b','j02-b','J02 B',1);"
        )
        permissions = [
            "chat:read",
            "chat:write",
            "byok:read",
            "byok:write",
            "rag:read",
            "rag:write",
            "agent:read",
            "agent:write",
            "agent:execute",
            "agent:approve",
            "finops:read",
            "ops:read",
        ]
        for tenant in ["j02-a", "j02-b", "default"]:
            time.sleep(0.3)
            code, _ = self.request(
                "finn",
                "/api/v1/auth/register",
                tenant=tenant,
                body={
                    "username": "fixture-" + tenant,
                    "email": tenant + "@example.invalid",
                    "password": self.keys["password"],
                    "fullName": "Synthetic J02",
                },
            )
            self.check("actual-register-" + tenant, code, 201)
            self.sql(
                "INSERT IGNORE INTO permissions(name) VALUES "
                + ",".join("('" + p + "')" for p in permissions)
                + ";"
                "INSERT INTO roles(tenant_id,name) VALUES ('"
                + tenant
                + "','j02-explicit');"
                "INSERT INTO role_permissions SELECT r.id,p.id FROM roles r JOIN permissions p ON p.name IN ("
                + ",".join("'" + p + "'" for p in permissions)
                + ") WHERE r.tenant_id='"
                + tenant
                + "' AND r.name='j02-explicit';"
                "INSERT INTO user_roles SELECT u.id,r.id FROM users u JOIN roles r ON u.tenant_id=r.tenant_id WHERE u.tenant_id='"
                + tenant
                + "' AND r.name='j02-explicit';"
                "UPDATE users SET auth_epoch=auth_epoch+1 WHERE tenant_id='"
                + tenant
                + "';"
            )
        compose("up", "-d", "jake")
        self.ready("jake")
        pairs = {tenant: self.login(tenant) for tenant in ["j02-a", "j02-b", "default"]}
        for tenant, pair in pairs.items():
            self.check(
                "actual-signed-tenant-" + tenant,
                self.request("jake", "/v1/models", token=pair[0], tenant="forged")[0],
                200,
            )
        self.matrix(pairs["j02-a"][0], "baseline")
        self.check(
            "opaque-refresh-not-access",
            self.request("jake", "/v1/models", token=pairs["j02-a"][1])[0],
            401,
        )
        canary = mask(secrets.token_urlsafe(32))
        self.check(
            "actual-byok-write",
            self.request(
                "jake",
                "/api/v1/byok/keys",
                token=pairs["j02-a"][0],
                body={"provider": "openai", "api_key": canary},
            )[0],
            201,
        )
        self.check(
            "foreign-tenant-hidden",
            self.request(
                "jake",
                "/api/v1/byok/keys/openai",
                token=pairs["j02-b"][0],
                method="DELETE",
            )[0],
            404,
        )
        self.check(
            "actual-draft-create",
            self.request(
                "jake",
                "/api/v1/agent/tasks",
                token=pairs["j02-a"][0],
                body={"goal": "synthetic read-only draft"},
            )[0],
            201,
        )
        # Stop every real old issuer. Synthetic old-key probes below are deliberately
        # forged negative controls, never described as legitimate issuer issuance.
        old, _ = self.login()
        self.last = decode(old)["iat"]
        compose("stop", "-t", "30", "finn-a")
        emit(
            "old_issuance_ceased",
            replicas=["finn-a"],
            final_old_issuance_unix=self.last,
            deadline_unix=self.last + 930,
        )
        configuration(self.root, self.keys, self.last, state_old=True)
        compose("up", "-d", "--force-recreate", "finn-a")
        self.ready("finn")
        current, _ = self.login()
        self.check(
            "issuer-first-new-token-old-jake",
            self.request("jake", "/v1/models", token=current)[0],
            401,
        )
        compose("up", "-d", "--force-recreate", "jake")
        self.ready("jake")
        self.check(
            "service-overlap-old-service-key",
            self.request("jake", "/v1/models", token=current)[0],
            200,
        )
        self.check(
            "signing-overlap-actual-old-token",
            self.request("jake", "/v1/models", token=old)[0],
            200,
        )
        configuration(self.root, self.keys, self.last)
        compose("up", "-d", "--force-recreate", "jake")
        self.ready("jake")
        self.check(
            "service-overlap-current-service-key",
            self.request("jake", "/v1/models", token=current)[0],
            200,
        )
        self.matrix(current, "overlap")
        compose("restart", "-t", "20", "jake")
        self.ready("jake")
        self.check(
            "overlap-after-restart",
            self.request("jake", "/v1/models", token=old)[0],
            200,
        )
        while time.time() < self.last + 930:
            remaining = self.last + 930 - time.time()
            emit(
                "real_clock_wait",
                remaining_seconds=round(remaining, 1),
                immutable_deadline_unix=self.last + 930,
            )
            time.sleep(min(30, remaining))
        current, _ = self.login()
        fresh = decode(current)
        previous_probe = signed(fresh, "sign-old", self.keys["sign-old"])
        self.check(
            "retirement-fresh-current-live-state",
            self.request("jake", "/v1/models", token=current)[0],
            200,
        )
        self.check(
            "retirement-fresh-forged-old-not-expiry",
            self.request("jake", "/v1/models", token=previous_probe)[0],
            401,
        )
        compose("restart", "-t", "20", "jake")
        self.ready("jake")
        self.check(
            "retirement-restart-immutable",
            self.request("jake", "/v1/models", token=previous_probe)[0],
            401,
        )
        configuration(self.root, self.keys, self.last, state_old=True)
        compose("up", "-d", "--force-recreate", "jake")
        self.ready("jake")
        self.check(
            "service-old-retired-unavailable",
            self.request("jake", "/v1/models", token=current)[0],
            503,
        )
        configuration(self.root, self.keys, self.last, remove=True)
        compose("up", "-d", "--force-recreate", "finn-a", "jake")
        self.ready("finn")
        self.ready("jake")
        self.check(
            "old-reference-removal-current",
            self.request("jake", "/v1/models", token=current)[0],
            200,
        )
        for dependency in ["mysql", "redis"]:
            compose("stop", "-t", "20", dependency)
            try:
                self.check(
                    dependency + "-fault-closed",
                    self.request("jake", "/v1/models", token=current)[0],
                    503,
                )
            finally:
                compose("start", dependency)
            time.sleep(10)
            self.check(
                dependency + "-recovery-positive",
                self.request("jake", "/v1/models", token=current)[0],
                200,
            )
        self.sql(
            "UPDATE users SET admin_suspended=1,auth_epoch=auth_epoch+1 WHERE tenant_id='j02-a';"
        )
        self.check(
            "actual-administrative-suspension",
            self.request("jake", "/v1/models", token=current)[0],
            401,
        )
        self.sql("UPDATE users SET admin_suspended=0 WHERE tenant_id='j02-a';")
        self.check(
            "old-epoch-stays-invalid",
            self.request("jake", "/v1/models", token=current)[0],
            401,
        )
        current, _ = self.login()
        self.check(
            "forced-reauthentication",
            self.request("jake", "/v1/models", token=current)[0],
            200,
        )
        # Long actual gateway delivery with only the external provider replaced.
        req = urllib.request.Request(
            "https://" + hostname("jake") + ":8443/v1/chat/completions",
            headers={
                "Content-Type": "application/json",
                "Authorization": "Bearer " + current,
            },
            data=json.dumps(
                {
                    "model": "gpt-4o-mini",
                    "messages": [{"role": "user", "content": "synthetic stream"}],
                    "stream": True,
                }
            ).encode(),
        )
        with self.http.open(req, timeout=30) as stream:
            first = stream.readline()
            self.check("actual-gateway-stream-started", bool(first), True)
            revoked = time.monotonic()
            self.sql(
                "UPDATE users SET auth_epoch=auth_epoch+1 WHERE tenant_id='j02-a';"
            )
            total = len(first)
            try:
                while stream.readline():
                    total += 1
                    if time.monotonic() - revoked > 30:
                        raise RuntimeError("Revocation SLA exceeded")
            except (ConnectionError, urllib.error.URLError):
                pass
            elapsed = time.monotonic() - revoked
            self.check("in-flight-revocation-within-30s", elapsed <= 30, True)
            emit(
                "stream_revocation",
                elapsed_seconds=round(elapsed, 3),
                observed_lines_or_bytes=total,
                provider="synthetic adapter; actual Jake route/services/cache/budget/middleware",
            )
        compose("up", "-d", "--force-recreate", "finn-a", "jake")
        self.ready("finn")
        self.ready("jake")
        # Pacing keeps Finn's unchanged per-account login rate limit intact.
        time.sleep(65)
        current, _ = self.login()
        self.check(
            "same-image-safe-recreation",
            self.request("jake", "/v1/models", token=current)[0],
            200,
        )
        self.check(
            "recreation-old-key-still-denied",
            self.request("jake", "/v1/models", token=previous_probe)[0],
            401,
        )
        emit(
            "result",
            assertions=self.count,
            status="IMPLEMENTATION_REHEARSAL_PASSED_ACCEPTANCE_PENDING",
            approval_multiworker="BLOCKED_UNSUPPORTED_EFFECTS_DISABLED",
            distinct_version_rollback="NOT_RUN_IDENTICAL_IMAGE_RECREATION_ONLY",
            qdrant_acl_boundary="NOT_RUN",
            full_lifecycle="F04",
            production="NOT_RUN",
            additional_cost_usd=0,
        )


def cleanup():
    project, root = identity()
    if not root.exists():
        emit("cleanup", status="NO_RUNTIME_ROOT")
        return
    down = (
        compose("down", "--volumes", "--remove-orphans", check=False)
        if (root / "compose.json").exists()
        else None
    )
    counts = {}
    for resource, args in [
        ("containers", ["ps", "-aq"]),
        ("volumes", ["volume", "ls", "-q"]),
        ("networks", ["network", "ls", "-q"]),
    ]:
        counts[resource] = len(
            command(
                [
                    "docker",
                    *args,
                    "--filter",
                    "label=com.docker.compose.project=" + project,
                ]
            )
            .stdout.decode()
            .split()
        )
    emit(
        "cleanup",
        project=project,
        leftovers=counts,
        status="PASS"
        if not any(counts.values()) and (down is None or down.returncode == 0)
        else "FAIL",
    )
    if any(counts.values()) or (down is not None and down.returncode):
        raise RuntimeError(
            "Owned cleanup incomplete; private state retained for correction"
        )
    hosts_update()
    emit("hosts_cleanup", status="PASS", only_owned_marker_removed=True)
    shutil.rmtree(root)
    emit(
        "private_cleanup",
        runtime_root_removed=not root.exists(),
        secure_erasure_claim=False,
    )


if __name__ == "__main__":
    try:
        {"prepare": prepare, "run": lambda: Rehearsal().run(), "cleanup": cleanup}[
            sys.argv[1]
        ]()
    except Exception as error:  # noqa: BLE001 - redact arbitrary runtime failures at CLI boundary
        emit(
            "operation_failure",
            error_type=type(error).__name__,
            remaining_cases="NOT_RUN",
            acceptance="BLOCKED",
        )
        sys.exit(1)
