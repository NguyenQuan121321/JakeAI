"""Review regressions use actual verification, requests and workflow entry points."""

from pathlib import Path

import httpx
import pytest
import yaml


def test_scheduled_offline_trust_never_uses_repository_credentials():
    root = Path(__file__).resolve().parents[3]
    for filename in ("nightly.yml", "performance-benchmark-scheduled.yml"):
        workflow = yaml.safe_load((root / ".github/workflows" / filename).read_text())
        for name, job in workflow["jobs"].items():
            for key, value in job.get("env", {}).items():
                if key in {
                    "JWT_SECRET_KEY",
                    "FINNAPIGO_SECRET_KEY",
                    "FINNAPIGO_JWT_SECRET",
                }:
                    assert "secrets." not in str(value), (filename, name, key)


@pytest.mark.asyncio
async def test_full_chat_adapter_has_no_request_errors(monkeypatch):
    from app.performance.scenarios.chat_scenario import run_concurrent_chat_scenario

    statuses = {}
    original = httpx.AsyncClient.post

    async def observe(self, *args, **kwargs):
        response = await original(self, *args, **kwargs)
        # Record only status and fixed public detail, never request credentials.
        detail = (
            response.json().get("detail", "") if response.status_code != 200 else ""
        )
        key = (response.status_code, str(detail)[:120])
        statuses[key] = statuses.get(key, 0) + 1
        return response

    monkeypatch.setattr(httpx.AsyncClient, "post", observe)
    result = await run_concurrent_chat_scenario(concurrency=10, total_requests=30)
    assert result.success_count == 30 and result.error_count == 0, statuses


def test_standalone_bootstrap_ignores_inherited_keys_and_provisions_vault():
    import os
    import subprocess
    import sys

    code = """
from tests.fixtures.identity import configure_asgi_benchmark_identity
configure_asgi_benchmark_identity()
from app.core.config import get_settings
from app.core.security import verify_finnapigo_jwt
from tests.fixtures.auth import create_test_jwt
from app.core.secret_material import decode_secret
s = get_settings()
assert verify_finnapigo_jwt(create_test_jwt()).user_id
assert s.BYOK_STORAGE_BACKEND == 'memory'
assert decode_secret(s.BYOK_MASTER_KEY, encoding='base64') != decode_secret(s.JWT_SECRET_KEY, encoding='base64')
"""
    env = {
        **os.environ,
        "ENVIRONMENT": "test",
        "JWT_SECRET_KEY": "legacy-configuration",
    }
    result = subprocess.run(
        [sys.executable, "-c", code], env=env, capture_output=True, timeout=30
    )
    assert result.returncode == 0, result.stderr.decode(errors="replace")


def test_report_current_revision_is_separate_from_baseline(monkeypatch):
    from app.performance.contracts import EnvironmentMetadata, PerformanceBaseline
    from app.performance.regression_detector import PerformanceRegressionDetector

    monkeypatch.setenv("GITHUB_SHA", "f" * 40)
    baseline = PerformanceBaseline(
        environment=EnvironmentMetadata(
            commit="old-windows-baseline", os_name="Windows"
        )
    )
    report = PerformanceRegressionDetector.evaluate_all({}, baseline)
    assert report.commit == "f" * 12
    assert report.baseline_environment.commit == "old-windows-baseline"
