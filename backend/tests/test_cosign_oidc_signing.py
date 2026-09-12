"""Automated verification suite for deterministic Cosign keyless OIDC signing.

Validates the requirements of CI/CD FIX — COSIGN KEYLESS OIDC SIGNING RELIABILITY:
1. Missing OIDC variables abort with clear diagnostic errors.
2. Bounded retry policy (max 3 attempts).
3. Fresh token acquisition per attempt (no reuse of expired tokens).
4. Non-interactive execution with --identity-token.
5. Strict failure gate when all retries are exhausted.
6. Token masking (::add-mask:: emitted for secret protection).
"""

from __future__ import annotations

import json
import os
import shutil
import subprocess
import threading
from http.server import BaseHTTPRequestHandler, HTTPServer
from pathlib import Path
from typing import Any

import pytest


def get_bash_executable() -> str:
    """Resolve standard bash executable across Windows Git-Bash and Linux runners."""
    for candidate in [
        r"E:\Program Files\Git\Git\bin\bash.exe",
        r"C:\Program Files\Git\bin\bash.exe",
        r"C:\Program Files\Git\usr\bin\bash.exe",
    ]:
        if Path(candidate).exists():
            return candidate
    return shutil.which("bash") or "bash"


class MockOidcServer(HTTPServer):
    def __init__(self, server_address: tuple[str, int]) -> None:
        super().__init__(server_address, MockOidcHandler)
        self.request_count = 0
        self.requested_audiences: list[str] = []
        self.issued_tokens: list[str] = []


class MockOidcHandler(BaseHTTPRequestHandler):
    server: MockOidcServer

    def do_GET(self) -> None:
        self.server.request_count += 1
        aud = "unknown"
        if "audience=" in self.path:
            aud = self.path.split("audience=")[-1].split("&")[0]
        self.server.requested_audiences.append(aud)

        token_value = f"mock-jwt-token-attempt-{self.server.request_count}"
        self.server.issued_tokens.append(token_value)

        payload = json.dumps({"count": 1, "value": token_value}).encode("utf-8")
        self.send_response(200)
        self.send_header("Content-Type", "application/json")
        self.send_header("Content-Length", str(len(payload)))
        self.end_headers()
        self.wfile.write(payload)

    def log_message(self, format: str, *args: Any) -> None:
        pass


@pytest.fixture
def oidc_server() -> Any:
    server = MockOidcServer(("127.0.0.1", 0))
    thread = threading.Thread(target=server.serve_forever, daemon=True)
    thread.start()
    yield server
    server.shutdown()
    server.server_close()


def test_missing_oidc_env_vars_fails_immediately() -> None:
    """Verify script fails immediately with diagnostic error if OIDC env vars are missing."""
    repo_root = Path(__file__).resolve().parent.parent.parent
    bash_bin = get_bash_executable()

    env = os.environ.copy()
    env.pop("ACTIONS_ID_TOKEN_REQUEST_URL", None)
    env.pop("ACTIONS_ID_TOKEN_REQUEST_TOKEN", None)
    env["COSIGN_RETRY_DELAYS"] = "0 0 0"

    proc = subprocess.run(
        [
            bash_bin,
            ".github/scripts/cosign_sign_with_retry.sh",
            "sign",
            "ghcr.io/test/backend@sha256:1234567890",
        ],
        cwd=str(repo_root),
        env=env,
        capture_output=True,
        text=True,
    )

    assert proc.returncode != 0
    assert "ACTIONS_ID_TOKEN_REQUEST_URL" in proc.stderr
    assert "OIDC_CONFIG_ERROR" in proc.stderr


def test_signing_with_controlled_failures_and_fresh_tokens(
    oidc_server: MockOidcServer,
) -> None:
    """Verify retry logic: attempts 1 and 2 fail, attempt 3 succeeds, requesting a fresh token every time."""
    repo_root = Path(__file__).resolve().parent.parent.parent
    bash_bin = get_bash_executable()
    port = oidc_server.server_port
    oidc_url = f"http://127.0.0.1:{port}/oidctoken?"

    mock_dir = repo_root / "backend" / "tests" / ".mock_bin_test1"
    if mock_dir.exists():
        shutil.rmtree(mock_dir)
    mock_dir.mkdir(parents=True, exist_ok=True)

    try:
        invocations_log = mock_dir / "cosign_invocations.jsonl"
        counter_file = mock_dir / "call_counter.txt"
        counter_file.write_text("0\n", encoding="utf-8")

        mock_cosign = mock_dir / "cosign"
        mock_script_content = (
            "#!/usr/bin/env bash\n"
            "set -e\n"
            "COUNTER_FILE='backend/tests/.mock_bin_test1/call_counter.txt'\n"
            "LOG_FILE='backend/tests/.mock_bin_test1/cosign_invocations.jsonl'\n"
            'count=$(cat "$COUNTER_FILE")\n'
            "count=$((count + 1))\n"
            'echo "$count" > "$COUNTER_FILE"\n'
            'echo "{\\"call\\": $count, \\"args\\": [\\"$@\\"]}" >> "$LOG_FILE"\n'
            'if [ "$count" -lt 3 ]; then\n'
            '  echo "Simulated Fulcio transient failure on call $count" >&2\n'
            "  exit 1\n"
            "else\n"
            '  echo "Simulated Fulcio success on call $count"\n'
            "  exit 0\n"
            "fi\n"
        )
        mock_cosign.write_text(mock_script_content, encoding="utf-8")

        env = os.environ.copy()
        # Ensure mock cosign directory is first in PATH for git bash
        mock_dir_posix = str(mock_dir.resolve()).replace("\\", "/")
        env["PATH"] = f"{mock_dir_posix};{env.get('PATH', '')}"
        env["ACTIONS_ID_TOKEN_REQUEST_URL"] = oidc_url
        env["ACTIONS_ID_TOKEN_REQUEST_TOKEN"] = "mock-bearer-token"
        env["COSIGN_RETRY_DELAYS"] = "0 0 0"

        proc = subprocess.run(
            [
                bash_bin,
                ".github/scripts/cosign_sign_with_retry.sh",
                "sign",
                "ghcr.io/test/backend@sha256:1234567890",
            ],
            cwd=str(repo_root),
            env=env,
            capture_output=True,
            text=True,
        )

        assert proc.returncode == 0, (
            f"Script failed (rc={proc.returncode}):\nSTDOUT:\n{proc.stdout}\nSTDERR:\n{proc.stderr}"
        )
        assert "CONTAINER_SIGN_SUCCESS" in proc.stdout
        assert "Image successfully signed on attempt 3/3" in proc.stdout

        # Invariant 1: Exactly 3 fresh tokens were issued
        assert oidc_server.request_count == 3
        assert all(aud == "sigstore" for aud in oidc_server.requested_audiences)

        # Invariant 2: Masking directive was emitted to stderr
        assert "::add-mask::mock-jwt-token-attempt-1" in proc.stderr
        assert "::add-mask::mock-jwt-token-attempt-2" in proc.stderr
        assert "::add-mask::mock-jwt-token-attempt-3" in proc.stderr

        # Invariant 3: Cosign was invoked with each fresh identity-token
        lines = invocations_log.read_text(encoding="utf-8").strip().splitlines()
        assert len(lines) == 3
        record_1 = json.loads(lines[0])
        record_2 = json.loads(lines[1])
        record_3 = json.loads(lines[2])

        args_1 = record_1["args"][0]
        assert "--identity-token mock-jwt-token-attempt-1" in args_1
        assert "--timeout 10m" in args_1

        args_2 = record_2["args"][0]
        assert "--identity-token mock-jwt-token-attempt-2" in args_2
        assert "--timeout 10m" in args_2

        args_3 = record_3["args"][0]
        assert "--identity-token mock-jwt-token-attempt-3" in args_3
        assert "--timeout 10m" in args_3
    finally:
        if mock_dir.exists():
            shutil.rmtree(mock_dir)


def test_exhausted_retries_aborts_and_fails_job(
    oidc_server: MockOidcServer,
) -> None:
    """Verify that when all 3 attempts fail, the script terminates with exit code 1 (fails the job)."""
    repo_root = Path(__file__).resolve().parent.parent.parent
    bash_bin = get_bash_executable()
    port = oidc_server.server_port
    oidc_url = f"http://127.0.0.1:{port}/oidctoken?"

    mock_dir = repo_root / "backend" / "tests" / ".mock_bin_test2"
    if mock_dir.exists():
        shutil.rmtree(mock_dir)
    mock_dir.mkdir(parents=True, exist_ok=True)

    try:
        mock_cosign = mock_dir / "cosign"
        mock_script_content = (
            "#!/usr/bin/env bash\n"
            'echo "Simulated persistent Fulcio failure" >&2\n'
            "exit 1\n"
        )
        mock_cosign.write_text(mock_script_content, encoding="utf-8")

        env = os.environ.copy()
        mock_dir_posix = str(mock_dir.resolve()).replace("\\", "/")
        env["PATH"] = f"{mock_dir_posix};{env.get('PATH', '')}"
        env["ACTIONS_ID_TOKEN_REQUEST_URL"] = oidc_url
        env["ACTIONS_ID_TOKEN_REQUEST_TOKEN"] = "mock-bearer-token"
        env["COSIGN_RETRY_DELAYS"] = "0 0 0"

        proc = subprocess.run(
            [
                bash_bin,
                ".github/scripts/cosign_sign_with_retry.sh",
                "sign",
                "ghcr.io/test/backend@sha256:1234567890",
            ],
            cwd=str(repo_root),
            env=env,
            capture_output=True,
            text=True,
        )

        assert proc.returncode != 0
        assert "SECURITY_GATE_FAILURE" in proc.stderr
        assert "Cryptographic container signing failed after 3 attempts" in proc.stderr
        assert oidc_server.request_count == 3
    finally:
        if mock_dir.exists():
            shutil.rmtree(mock_dir)


def test_attestation_with_predicate_and_retries(
    oidc_server: MockOidcServer,
) -> None:
    """Verify attest subcommand passes predicate file, cyclonedx type, and fresh identity token."""
    repo_root = Path(__file__).resolve().parent.parent.parent
    bash_bin = get_bash_executable()
    port = oidc_server.server_port
    oidc_url = f"http://127.0.0.1:{port}/oidctoken?"

    mock_dir = repo_root / "backend" / "tests" / ".mock_bin_test3"
    if mock_dir.exists():
        shutil.rmtree(mock_dir)
    mock_dir.mkdir(parents=True, exist_ok=True)

    try:
        sbom_file = mock_dir / "sbom.json"
        sbom_file.write_text('{"bomFormat": "CycloneDX"}', encoding="utf-8")

        invocations_log = mock_dir / "attest_invocations.jsonl"
        mock_cosign = mock_dir / "cosign"
        mock_script_content = (
            "#!/usr/bin/env bash\n"
            "set -e\n"
            "LOG_FILE='backend/tests/.mock_bin_test3/attest_invocations.jsonl'\n"
            'echo "{\\"args\\": [\\"$@\\"]}" >> "$LOG_FILE"\n'
            "exit 0\n"
        )
        mock_cosign.write_text(mock_script_content, encoding="utf-8")

        env = os.environ.copy()
        mock_dir_posix = str(mock_dir.resolve()).replace("\\", "/")
        env["PATH"] = f"{mock_dir_posix};{env.get('PATH', '')}"
        env["ACTIONS_ID_TOKEN_REQUEST_URL"] = oidc_url
        env["ACTIONS_ID_TOKEN_REQUEST_TOKEN"] = "mock-bearer-token"
        env["COSIGN_RETRY_DELAYS"] = "0 0 0"

        proc = subprocess.run(
            [
                bash_bin,
                ".github/scripts/cosign_sign_with_retry.sh",
                "attest",
                "ghcr.io/test/backend@sha256:1234567890",
                "backend/tests/.mock_bin_test3/sbom.json",
            ],
            cwd=str(repo_root),
            env=env,
            capture_output=True,
            text=True,
        )

        assert proc.returncode == 0, f"Script failed: {proc.stderr}"
        assert "CONTAINER_ATTEST_SUCCESS" in proc.stdout

        lines = invocations_log.read_text(encoding="utf-8").strip().splitlines()
        assert len(lines) == 1
        record = json.loads(lines[0])
        args = record["args"][0]
        assert "attest" in args
        assert "--identity-token mock-jwt-token-attempt-1" in args
        assert "--predicate" in args
        assert "--type cyclonedx" in args
    finally:
        if mock_dir.exists():
            shutil.rmtree(mock_dir)
