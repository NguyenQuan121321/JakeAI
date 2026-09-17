#!/usr/bin/env python3
"""JakeAI Bruno CLI Automated Test Runner (TEST-08 / BRUNO-RECON-01).

Orchestrates automated execution of the Bruno API/E2E test suite using
`@usebruno/cli`. Implements:
  - Explicit profiles:
      * public-smoke (alias: smoke): Fast confidence smoke (<10s)
      * public-full (alias: full): Complete public test suite
      * private-security: Negative, security, and tenant isolation tests
      * private-full: Complete private verification suite
      * critical-e2e: End-to-end business workflows
      * live-release: Mandatory live provider & upstream identity verification
  - Clean dependency governance (BLOCKED reporting without false PASS or false FAIL)
  - Uvicorn backend server health verification and optional auto-start
  - Standardized reporting: JSON, JUnit XML, Markdown summary
  - CI / GitHub Actions integration
"""

from __future__ import annotations

import argparse
import base64
import hashlib
import hmac
import json
import os
import shutil
import subprocess
import sys
import time
import urllib.error
import urllib.request
import xml.etree.ElementTree as ET
from dataclasses import dataclass, field
from pathlib import Path

# Ensure UTF-8 console output across Windows and Linux
if hasattr(sys.stdout, "reconfigure"):
    sys.stdout.reconfigure(encoding="utf-8")
if hasattr(sys.stderr, "reconfigure"):
    sys.stderr.reconfigure(encoding="utf-8")

# Known requests targeting the external FinnApiGo identity authority
EXTERNAL_FINNAPIGO_REQUESTS = {
    "private/07 — Live FinnApiGo/01 — Healthz Probe.bru",
    "private/07 — Live FinnApiGo/02 — FinnApiGo Login.bru",
    "private/07 — Live FinnApiGo/03 — FinnApiGo OBO Token Exchange.bru",
    "private\\07 — Live FinnApiGo\\01 — Healthz Probe.bru",
    "private\\07 — Live FinnApiGo\\02 — FinnApiGo Login.bru",
    "private\\07 — Live FinnApiGo\\03 — FinnApiGo OBO Token Exchange.bru",
}

PUBLIC_SMOKE_TARGETS = [
    "public/00 — Setup/01 — Root Health Smoke.bru",
    "public/00 — Setup/02 — API Health Smoke.bru",
    "public/01 — Public Smoke/01 — Public Root Health.bru",
    "public/01 — Public Smoke/02 — Public API Health.bru",
    "public/01 — Public Smoke/03 — Public Models Catalog.bru",
    "public/02 — Chat/01 — Chat Stream.bru",
    "public/03 — Agent/01 — Create Task.bru",
    "public/04 — RAG/01 — Ingest Document.bru",
    "public/05 — Provider Examples/01 — List BYOK Keys.bru",
    "public/99 — Public Final Smoke/01 — Production-like Smoke.bru",
]

PUBLIC_FOLDERS = [
    "public/00 — Setup",
    "public/01 — Public Smoke",
    "public/02 — Chat",
    "public/03 — Agent",
    "public/04 — RAG",
    "public/05 — Provider Examples",
    "public/99 — Public Final Smoke",
]

PRIVATE_SECURITY_FOLDERS = [
    "private/01 — Authentication & Tenant Security",
    "private/02 — Security & Negative",
    "private/04 — Cross Tenant",
    "private/05 — Tool Security",
]

PRIVATE_FULL_FOLDERS = [
    "private/01 — Authentication & Tenant Security",
    "private/02 — Security & Negative",
    "private/03 — Failure & Recovery",
    "private/04 — Cross Tenant",
    "private/05 — Tool Security",
    "private/08 — Production Verification",
    "private/06 — Live Provider",
    "private/07 — Live FinnApiGo",
]

CRITICAL_E2E_TARGETS = [
    "public/01 — Public Smoke",
    "public/02 — Chat",
    "public/03 — Agent",
    "public/04 — RAG",
    "public/05 — Provider Examples/08 — Exact Cache Miss.bru",
    "public/05 — Provider Examples/09 — Exact Cache Hit.bru",
    "public/05 — Provider Examples/12 — FinOps Summary.bru",
    "public/99 — Public Final Smoke",
    "private/08 — Production Verification",
]


@dataclass
class TestItemResult:
    """Individual test item execution outcome."""

    name: str
    target: str
    status: str  # "passed", "failed", "blocked", "skipped"
    duration_ms: float = 0.0
    status_code: int | None = None
    tests_passed: int = 0
    tests_total: int = 0
    error_message: str | None = None
    is_external: bool = False


@dataclass
class SuiteSummary:
    """Aggregated test suite results."""

    suite: str
    environment: str
    total_requests: int = 0
    passed: int = 0
    failed: int = 0
    blocked: int = 0
    skipped: int = 0
    duration_seconds: float = 0.0
    items: list[TestItemResult] = field(default_factory=list)
    finnapigo_online: bool = False
    jakeai_online: bool = False

    @property
    def pass_rate(self) -> float:
        evaluated = self.passed + self.failed
        return (self.passed / evaluated * 100.0) if evaluated > 0 else 0.0

    @property
    def is_success(self) -> bool:
        if self.failed > 0:
            return False
        return not (self.suite == "live-release" and self.blocked > 0)


def check_http_endpoint(url: str, timeout_sec: float = 2.5) -> tuple[bool, int, str]:
    """Check if an HTTP endpoint is reachable and returning 200 OK."""
    try:
        req = urllib.request.Request(
            url,
            headers={
                "User-Agent": "JakeAI-Bruno-Runner/1.0",
                "Accept": "application/json",
            },
        )
        with urllib.request.urlopen(req, timeout=timeout_sec) as response:
            return (response.status == 200, response.status, "")
    except urllib.error.HTTPError as err:
        return (False, err.code, f"HTTP {err.code}: {err.reason}")
    except Exception as exc:  # noqa: BLE001
        return (False, 0, str(exc))


def find_workspace_root() -> Path:
    """Locate the root of the JakeAI repository."""
    current = Path(__file__).resolve()
    for parent in [current.parent, current.parent.parent, current.parent.parent.parent]:
        if (parent / "Bruno").is_dir() and (parent / "backend").is_dir():
            return parent
    return Path.cwd()


def resolve_npx() -> str:
    """Find the npx executable across platforms."""
    npx_bin = shutil.which("npx") or shutil.which("npx.cmd")
    if not npx_bin:
        raise RuntimeError(
            "Node.js 'npx' command not found in PATH. Please install Node.js (v18+) to run Bruno tests."
        )
    return npx_bin


def find_uvicorn_python(repo_root: Path) -> str:
    """Locate Python executable with uvicorn installed."""
    venv_python = repo_root / "backend" / ".venv" / "Scripts" / "python.exe"
    if venv_python.is_file():
        return str(venv_python)
    venv_python_unix = repo_root / "backend" / ".venv" / "bin" / "python"
    if venv_python_unix.is_file():
        return str(venv_python_unix)
    return sys.executable


def start_uvicorn_server(repo_root: Path, port: int = 8000) -> subprocess.Popen[str]:
    """Start local JakeAI backend server in the background."""
    python_bin = find_uvicorn_python(repo_root)
    cmd = [
        python_bin,
        "-m",
        "uvicorn",
        "app.main:app",
        "--host",
        "127.0.0.1",
        "--port",
        str(port),
    ]
    backend_dir = repo_root / "backend"
    print(f"[*] Starting JakeAI backend server on 127.0.0.1:{port}...")
    secret = resolve_authoritative_jwt_secret(repo_root)
    env = os.environ.copy()
    env["JWT_SECRET_KEY"] = secret

    proc = subprocess.Popen(
        cmd,
        cwd=str(backend_dir),
        env=env,
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
        text=True,
    )
    health_url = f"http://127.0.0.1:{port}/health"
    start_time = time.time()
    while time.time() - start_time < 20:
        ok, _, _ = check_http_endpoint(health_url, timeout_sec=1.0)
        if ok:
            print(
                f"[OK] JakeAI backend server is ready on port {port} (PID: {proc.pid})"
            )
            return proc
        time.sleep(0.5)

    proc.terminate()
    raise RuntimeError(
        f"Timed out waiting for JakeAI backend on port {port} to become healthy."
    )


def resolve_authoritative_jwt_secret(repo_root: Path | None = None) -> str:
    """Resolve authoritative JWT_SECRET_KEY across CI environment, .env, or defaults."""
    if os.environ.get("JWT_SECRET_KEY"):
        return os.environ["JWT_SECRET_KEY"]
    if os.environ.get("FINNAPIGO_JWT_SECRET"):
        return os.environ["FINNAPIGO_JWT_SECRET"]
    root = repo_root or find_workspace_root()
    backend_dir = root / "backend"
    if str(backend_dir) not in sys.path:
        sys.path.insert(0, str(backend_dir))
    try:
        from app.core.config import get_settings

        return get_settings().JWT_SECRET_KEY
    except Exception:
        return "insecure-development-secret-change-in-production"


def generate_runtime_dev_jwts(repo_root: Path | None = None) -> dict[str, str]:
    """Dynamically generate deterministic test JWTs at runtime using authoritative test generator."""
    root = repo_root or find_workspace_root()
    backend_dir = root / "backend"
    if str(backend_dir) not in sys.path:
        sys.path.insert(0, str(backend_dir))

    secret = resolve_authoritative_jwt_secret(root)

    try:
        from tests.fixtures.auth import create_test_jwt

        now = int(time.time())
        return {
            "token_a": create_test_jwt(
                sub="16",
                tenant_id="default",
                roles=["admin"],
                permissions=["*"],
                expires_in=3600,
                secret_key=secret,
                jti=f"test-token-16-{now}",
            ),
            "token_b": create_test_jwt(
                sub="user-beta",
                tenant_id="tenant_beta",
                roles=["user"],
                permissions=["read"],
                expires_in=3600,
                secret_key=secret,
                jti=f"test-token-user-beta-{now}",
            ),
            "token_expired": create_test_jwt(
                sub="16",
                tenant_id="default",
                roles=["admin"],
                permissions=["*"],
                expires_in=-3600,
                secret_key=secret,
                jti=f"test-token-16-{now}",
            ),
        }
    except Exception:
        now = int(time.time())

        def _b64url(b: bytes) -> str:
            return base64.urlsafe_b64encode(b).decode("utf-8").rstrip("=")

        def _make_jwt(
            sub: str, tenant_id: str, exp_offset: int, role: str = "admin"
        ) -> str:
            kid = hashlib.sha256(secret.encode("utf-8")).hexdigest()[:8]
            header = {"alg": "HS256", "typ": "JWT", "kid": kid}
            payload = {
                "sub": sub,
                "uid": sub,
                "tenant_id": tenant_id,
                "tid": tenant_id,
                "role": role,
                "roles": [role],
                "permissions": ["*"] if role == "admin" else ["read"],
                "perms": ["*"] if role == "admin" else ["read"],
                "type": "access",
                "iat": now,
                "exp": now + exp_offset,
                "jti": f"dev-token-{sub}-{now}",
            }
            h_str = _b64url(json.dumps(header, separators=(",", ":")).encode("utf-8"))
            p_str = _b64url(json.dumps(payload, separators=(",", ":")).encode("utf-8"))
            sig = hmac.new(
                secret.encode("utf-8"),
                f"{h_str}.{p_str}".encode("utf-8"),
                hashlib.sha256,
            ).digest()
            return f"{h_str}.{p_str}.{_b64url(sig)}"

        return {
            "token_a": _make_jwt("16", "default", exp_offset=3600, role="admin"),
            "token_b": _make_jwt(
                "user-beta", "tenant_beta", exp_offset=3600, role="user"
            ),
            "token_expired": _make_jwt("16", "default", exp_offset=-3600, role="admin"),
        }


def run_bruno_cli_target(
    npx_bin: str,
    bruno_dir: Path,
    target: str,
    environment: str,
    temp_json_path: Path,
    verbose: bool = False,
    extra_env_vars: dict[str, str] | None = None,
) -> tuple[int, list[TestItemResult]]:
    """Execute Bruno CLI for a specific folder or request and parse output."""
    is_dir = (bruno_dir / target).is_dir()
    cmd = [
        npx_bin,
        "--yes",
        "@usebruno/cli",
        "run",
        target,
    ]
    if is_dir:
        cmd.append("-r")

    cmd.extend([
        "--env",
        environment,
        "--reporter-json",
        str(temp_json_path),
        "--reporter-skip-headers",
        "Authorization",
    ])

    if extra_env_vars:
        for k, v in extra_env_vars.items():
            cmd.extend(["--env-var", f"{k}={v}"])

    if verbose:
        print(f"[DEBUG] Executing: {' '.join(cmd)}")

    res = subprocess.run(
        cmd,
        cwd=str(bruno_dir),
        capture_output=True,
        text=True,
        encoding="utf-8",
        errors="replace",
        check=False,
    )

    if verbose or res.returncode != 0:
        if res.stdout:
            print(res.stdout)
        if res.stderr:
            print(res.stderr, file=sys.stderr)

    results: list[TestItemResult] = []
    if temp_json_path.is_file():
        try:
            with open(temp_json_path, "r", encoding="utf-8") as f:
                data = json.load(f)
            for iteration in data:
                for item in iteration.get("results", []):
                    rel_name = (
                        item.get("name")
                        or item.get("test", {}).get("filename")
                        or target
                    )
                    filename = item.get("test", {}).get("filename") or target
                    duration = float(item.get("response", {}).get("duration", 0.0))
                    status_code = item.get("response", {}).get("status")
                    test_results = item.get("testResults", [])
                    t_total = len(test_results)
                    t_passed = sum(1 for t in test_results if t.get("status") == "pass")

                    item_status = "passed" if item.get("status") == "pass" else "failed"
                    error_msg = item.get("error")
                    if not error_msg and item_status == "failed":
                        failures = [
                            t.get("error")
                            for t in test_results
                            if t.get("status") == "fail"
                        ]
                        error_msg = "; ".join(filter(None, failures))

                    results.append(
                        TestItemResult(
                            name=rel_name,
                            target=filename,
                            status=item_status,
                            duration_ms=duration,
                            status_code=status_code,
                            tests_passed=t_passed,
                            tests_total=t_total,
                            error_message=error_msg,
                        )
                    )
        except Exception as exc:  # noqa: BLE001
            if verbose:
                print(f"[WARN] Failed parsing Bruno JSON report {temp_json_path}: {exc}")

    if not results and res.returncode != 0:
        results.append(
            TestItemResult(
                name=target,
                target=target,
                status="failed",
                error_message=res.stderr or res.stdout or "Command failed",
            )
        )

    return res.returncode, results


def generate_junit_xml(summary: SuiteSummary, output_path: Path) -> None:
    """Generate JUnit XML report from the aggregated summary."""
    testsuites = ET.Element(
        "testsuites",
        name=f"Bruno-{summary.suite}",
        tests=str(summary.total_requests),
        failures=str(summary.failed),
        errors="0",
        skipped=str(summary.blocked + summary.skipped),
        time=f"{summary.duration_seconds:.3f}",
    )
    testsuite = ET.SubElement(
        testsuites,
        "testsuite",
        name=summary.suite,
        tests=str(summary.total_requests),
        failures=str(summary.failed),
        errors="0",
        skipped=str(summary.blocked + summary.skipped),
        time=f"{summary.duration_seconds:.3f}",
    )

    for item in summary.items:
        tc = ET.SubElement(
            testsuite,
            "testcase",
            name=item.name,
            classname=item.target.replace("\\", ".").replace("/", "."),
            time=f"{item.duration_ms / 1000.0:.3f}",
        )
        if item.status == "failed":
            failure = ET.SubElement(
                tc, "failure", message=item.error_message or "Assertion failure"
            )
            failure.text = item.error_message or "Assertion failed in Bruno test"
        elif item.status in ("blocked", "skipped"):
            skipped = ET.SubElement(
                tc, "skipped", message=item.error_message or f"Test {item.status}"
            )
            skipped.text = (
                item.error_message or f"Dependency unavailable: {item.status}"
            )

    output_path.parent.mkdir(parents=True, exist_ok=True)
    tree = ET.ElementTree(testsuites)
    tree.write(str(output_path), encoding="utf-8", xml_declaration=True)


def generate_markdown_summary(summary: SuiteSummary) -> str:
    """Create GitHub Flavored Markdown summary report."""
    status_badge = "🟢 **PASS**" if summary.is_success else "🔴 **FAIL**"
    lines = [
        f"## 🐶 JakeAI Bruno CLI Automated Test Summary — `{summary.suite}`",
        "",
        f"- **Suite Profile**: `{summary.suite}`",
        f"- **Environment**: `{summary.environment}`",
        f"- **Overall Status**: {status_badge}",
        f"- **Pass Rate**: `{summary.pass_rate:.1f}%`",
        f"- **Total Requests Evaluated**: `{summary.total_requests}`",
        f"- **Passed**: `✓ {summary.passed}` | **Failed**: `✗ {summary.failed}` | **Blocked (External)**: `⏸ {summary.blocked}` | **Skipped**: `○ {summary.skipped}`",
        f"- **Execution Duration**: `{summary.duration_seconds:.2f}s`",
        f"- **FinnApiGo Authority**: `{'ONLINE' if summary.finnapigo_online else 'OFFLINE (Dev Fallback Active)'}`",
        "",
        "### Request Breakdown",
        "",
        "| Status | Request / Target | Tests | Status Code | Duration (ms) | Notes |",
        "| :---: | :--- | :---: | :---: | :---: | :--- |",
    ]

    for item in summary.items:
        if item.status == "passed":
            icon = "✓ PASS"
        elif item.status == "failed":
            icon = "✗ FAIL"
        elif item.status == "blocked":
            icon = "⏸ BLOCKED"
        else:
            icon = "○ SKIP"

        tests_str = (
            f"{item.tests_passed}/{item.tests_total}" if item.tests_total > 0 else "-"
        )
        sc_str = str(item.status_code) if item.status_code else "-"
        notes = item.error_message or (
            "External Dependency" if item.is_external else ""
        )
        if len(notes) > 70:
            notes = notes[:67] + "..."
        lines.append(
            f"| {icon} | `{item.name}` | {tests_str} | {sc_str} | {item.duration_ms:.1f} | {notes} |"
        )

    lines.append("")
    return "\n".join(lines)


def print_console_summary(summary: SuiteSummary) -> None:
    """Print high-contrast console summary."""
    print("\n" + "=" * 76)
    print(
        f" JAKEAI BRUNO AUTOMATION SUITE: {summary.suite.upper()} (Env: {summary.environment})"
    )
    print("=" * 76)
    print(f" Overall Status : {'✓ PASS' if summary.is_success else '✗ FAIL'}")
    print(f" Requests Total : {summary.total_requests}")
    print(f" Passed         : {summary.passed}")
    print(f" Failed         : {summary.failed}")
    print(f" Blocked (Ext)  : {summary.blocked} (Dependency Governance)")
    print(f" Skipped        : {summary.skipped}")
    print(f" Pass Rate      : {summary.pass_rate:.1f}%")
    print(f" Duration       : {summary.duration_seconds:.2f}s")
    print(
        f" FinnApiGo Auth : {'ONLINE' if summary.finnapigo_online else 'OFFLINE (Fallback Active)'}"
    )
    print("-" * 76)

    if summary.failed > 0:
        print("\n[!] Failed Requests:")
        for item in summary.items:
            if item.status == "failed":
                print(f"  - {item.name}: {item.error_message or 'Assertion failed'}")

    if summary.blocked > 0:
        print("\n[i] Blocked Requests (Unverified external dependency):")
        for item in summary.items:
            if item.status == "blocked":
                print(f"  - {item.name}: {item.error_message}")

    print("=" * 76 + "\n")


def main() -> int:
    parser = argparse.ArgumentParser(
        description="JakeAI Bruno CLI Automated Test Runner (TEST-08 / BRUNO-RECON-01)"
    )
    parser.add_argument(
        "--suite",
        choices=[
            "public-smoke",
            "public-full",
            "private-security",
            "private-full",
            "critical-e2e",
            "live-release",
            "smoke",
            "full",
        ],
        default="public-smoke",
        help="Test suite profile (default: public-smoke)",
    )
    parser.add_argument(
        "--folder", default=None, help="Execute only a specific Bruno folder"
    )
    parser.add_argument(
        "--request", default=None, help="Execute only a specific .bru request file"
    )
    parser.add_argument(
        "--env", default="Local", help="Bruno environment name (default: Local)"
    )
    parser.add_argument(
        "--base-url", default="http://localhost:8000", help="JakeAI base URL"
    )
    parser.add_argument(
        "--finnapigo-url", default="http://localhost:8081", help="FinnApiGo base URL"
    )
    parser.add_argument(
        "--report-dir", default=None, help="Directory to store JSON and JUnit reports"
    )
    parser.add_argument(
        "--auto-start", action="store_true", help="Auto-start uvicorn server if offline"
    )
    parser.add_argument(
        "--verbose", action="store_true", help="Print verbose execution details"
    )

    args = parser.parse_args()

    # Aliases
    suite = args.suite
    if suite == "smoke":
        suite = "public-smoke"
    elif suite == "full":
        suite = "public-full"

    start_time = time.time()
    repo_root = find_workspace_root()
    bruno_dir = repo_root / "Bruno"

    if not bruno_dir.is_dir():
        print(f"[ERROR] Bruno collection directory not found at {bruno_dir}", file=sys.stderr)
        return 1

    npx_bin = resolve_npx()

    if args.report_dir:
        report_dir = Path(args.report_dir).resolve()
    else:
        report_dir = repo_root / "backend" / "reports" / "bruno"
    report_dir.mkdir(parents=True, exist_ok=True)

    # 1. Health Verification
    jakeai_ok, _, _ = check_http_endpoint(f"{args.base_url}/health")
    if not jakeai_ok:
        jakeai_ok, _, _ = check_http_endpoint(f"{args.base_url}/api/v1/health")

    server_proc = None
    if not jakeai_ok:
        if args.auto_start or os.environ.get("CI"):
            print("[*] JakeAI server not detected. Auto-starting backend...")
            server_proc = start_uvicorn_server(repo_root)
            jakeai_ok = True
        else:
            print(
                f"[ERROR] JakeAI server is offline at {args.base_url}. Start uvicorn or pass --auto-start.",
                file=sys.stderr,
            )
            return 1

    # Check external dependency (FinnApiGo)
    finnapigo_ok, _, _ = check_http_endpoint(
        f"{args.finnapigo_url}/healthz", timeout_sec=1.5
    )
    print(
        f"[*] Identity Authority (FinnApiGo): {'ONLINE' if finnapigo_ok else 'OFFLINE (Dev Fallback Active)'}"
    )

    summary = SuiteSummary(
        suite=suite if not (args.folder or args.request) else "custom",
        environment=args.env,
        finnapigo_online=finnapigo_ok,
        jakeai_online=jakeai_ok,
    )

    try:
        # Determine targets based on suite profile
        if args.request:
            targets = [args.request]
        elif args.folder:
            all_known = PUBLIC_FOLDERS + PRIVATE_SECURITY_FOLDERS + PRIVATE_FULL_FOLDERS
            matched = [f for f in all_known if args.folder.lower() in f.lower()]
            targets = [matched[0]] if matched else [args.folder]
        elif suite == "public-smoke":
            targets = PUBLIC_SMOKE_TARGETS
        elif suite == "public-full":
            targets = PUBLIC_FOLDERS
        elif suite == "private-security":
            targets = PRIVATE_SECURITY_FOLDERS
        elif suite == "private-full":
            targets = PRIVATE_FULL_FOLDERS
        elif suite == "critical-e2e":
            targets = CRITICAL_E2E_TARGETS
        elif suite == "live-release":
            targets = PUBLIC_FOLDERS + PRIVATE_FULL_FOLDERS
        else:
            targets = PUBLIC_FOLDERS

        temp_json = report_dir / "temp_run.json"
        runtime_dev_jwts = generate_runtime_dev_jwts()

        for target in targets:
            target_path = bruno_dir / target
            if not target_path.exists():
                # If target is private and gitignored/absent (e.g. in PR CI)
                if "private" in target:
                    summary.items.append(
                        TestItemResult(
                            name=Path(target).name,
                            target=target,
                            status="skipped",
                            error_message="Private suite omitted in non-privileged environment",
                        )
                    )
                    continue
                else:
                    print(f"[WARN] Target not found: {target}")
                    continue

            is_folder_target = target_path.is_dir()

            # Dependency governance for FinnApiGo requests
            norm_target = target.replace("\\", "/")
            if not finnapigo_ok and (
                norm_target in EXTERNAL_FINNAPIGO_REQUESTS
                or "Live FinnApiGo" in norm_target
            ):
                if suite == "live-release":
                    summary.items.append(
                        TestItemResult(
                            name=Path(target).name,
                            target=target,
                            status="failed",
                            error_message=f"Live release mandates online FinnApiGo at {args.finnapigo_url}",
                            is_external=True,
                        )
                    )
                else:
                    summary.items.append(
                        TestItemResult(
                            name=Path(target).name,
                            target=target,
                            status="blocked",
                            error_message=f"FinnApiGo offline at {args.finnapigo_url} (dev fallback active)",
                            is_external=True,
                        )
                    )
                continue

            # Governance for live third-party provider keys
            if "Live Provider" in norm_target and not os.environ.get("GEMINI_API_KEY"):
                if suite == "live-release":
                    summary.items.append(
                        TestItemResult(
                            name=Path(target).name,
                            target=target,
                            status="failed",
                            error_message="Live release mandates live provider credentials in environment",
                            is_external=True,
                        )
                    )
                else:
                    summary.items.append(
                        TestItemResult(
                            name=Path(target).name,
                            target=target,
                            status="blocked",
                            error_message="Live provider keys not configured in local environment (gated)",
                            is_external=True,
                        )
                    )
                continue

            _, res_items = run_bruno_cli_target(
                npx_bin=npx_bin,
                bruno_dir=bruno_dir,
                target=target,
                environment=args.env,
                temp_json_path=temp_json,
                verbose=args.verbose,
                extra_env_vars=runtime_dev_jwts,
            )
            summary.items.extend(res_items)

        if temp_json.is_file():
            temp_json.unlink(missing_ok=True)

    finally:
        if server_proc:
            print("[*] Terminating auto-started JakeAI backend...")
            server_proc.terminate()
            try:
                server_proc.wait(timeout=5)
            except subprocess.TimeoutExpired:
                server_proc.kill()

    summary.duration_seconds = time.time() - start_time
    summary.total_requests = len(summary.items)
    summary.passed = sum(1 for i in summary.items if i.status == "passed")
    summary.failed = sum(1 for i in summary.items if i.status == "failed")
    summary.blocked = sum(1 for i in summary.items if i.status == "blocked")
    summary.skipped = sum(1 for i in summary.items if i.status == "skipped")

    json_path = report_dir / "bruno-results.json"
    junit_path = report_dir / "bruno-junit.xml"
    summary_md_path = report_dir / "bruno-summary.md"

    with open(json_path, "w", encoding="utf-8") as f:
        json.dump(
            {
                "suite": summary.suite,
                "environment": summary.environment,
                "is_success": summary.is_success,
                "pass_rate": summary.pass_rate,
                "total_requests": summary.total_requests,
                "passed": summary.passed,
                "failed": summary.failed,
                "blocked": summary.blocked,
                "skipped": summary.skipped,
                "duration_seconds": summary.duration_seconds,
                "items": [
                    {
                        "name": i.name,
                        "target": i.target,
                        "status": i.status,
                        "duration_ms": i.duration_ms,
                        "status_code": i.status_code,
                        "tests_passed": i.tests_passed,
                        "tests_total": i.tests_total,
                        "error_message": i.error_message,
                    }
                    for i in summary.items
                ],
            },
            f,
            indent=2,
        )

    generate_junit_xml(summary, junit_path)
    md_content = generate_markdown_summary(summary)
    summary_md_path.write_text(md_content, encoding="utf-8")

    print_console_summary(summary)
    print(f"[OK] Reports written to:\n  - {json_path}\n  - {junit_path}\n  - {summary_md_path}")

    return 0 if summary.is_success else 1


if __name__ == "__main__":
    sys.exit(main())
