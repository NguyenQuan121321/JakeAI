"""Root pytest fixtures and configuration registering shared test fixtures."""

import base64
import os
import secrets

import pytest

# Synthetic provisioning belongs in tests, never in runtime defaults or CI credentials.
os.environ.setdefault(
    "JWT_SECRET_KEY", base64.b64encode(secrets.token_bytes(32)).decode()
)
os.environ.setdefault("JWT_KEY_ID", "test-current")
os.environ.setdefault("JWT_ALGORITHM", "HS256")
os.environ.setdefault("JWT_ISSUER", "finnapigo")
os.environ.setdefault("INTERNAL_GATEWAY_SECRET", secrets.token_hex(32))
os.environ.setdefault(
    "BYOK_MASTER_KEY", base64.b64encode(secrets.token_bytes(32)).decode()
)
os.environ.setdefault("BYOK_MASTER_KEY_ID", "test-current")
os.environ.setdefault("BYOK_STORAGE_BACKEND", "memory")

from tests.fixtures.auth import create_test_jwt, generate_agent_jwt
from tests.fixtures.client import async_client

__all__ = [
    "async_client",
    "create_test_jwt",
    "generate_agent_jwt",
]


@pytest.fixture
def component_decision_store(monkeypatch):
    """Opt-in only: exercise orchestration from a pre-decided component record."""
    from app.agent.approvals.manager import ApprovalManager
    from tests.fixtures.approvals import component_decision

    monkeypatch.setattr(ApprovalManager, "decide", component_decision)
    monkeypatch.setattr(ApprovalManager, "decide_request", component_decision)


@pytest.fixture(autouse=True)
def offline_identity_transport(monkeypatch, request):
    """Ordinary suites isolate Finn state, never token verification or grants.

    Actual adapter tests install their own app.state client. Hosted J02 runs the
    release processes outside pytest and never loads this synthetic fixture.
    """
    if request.node.get_closest_marker("live_finnapigo"):
        return
    from app.core.config import get_settings
    from app.core.identity_state import get_state_client

    class OfflineState:
        @property
        def settings(self):
            return get_settings()

        async def check(self, token, claims):
            # Signature/purpose/types/expiry are enforced by AuthorityLease.
            assert token and claims["contract_ver"] == 1

    def choose(incoming):
        if getattr(incoming.app.state, "identity_client", None) is not None:
            return get_state_client(incoming)
        return OfflineState()

    monkeypatch.setattr("app.core.security.get_state_client", choose)


def pytest_collection_modifyitems(
    config: pytest.Config, items: list[pytest.Item]
) -> None:
    """Centrally assign canonical pytest markers based on directory hierarchy (TEST-11)."""
    for item in items:
        # Normalize path separator for cross-platform Windows/Linux consistency
        path_str = str(item.fspath).replace("\\", "/")
        if "/tests/unit/" in path_str:
            item.add_marker(pytest.mark.unit)
        elif "/tests/integration/" in path_str:
            item.add_marker(pytest.mark.integration)
        elif "/tests/contract/" in path_str:
            item.add_marker(pytest.mark.contract)
        elif "/tests/security/" in path_str:
            item.add_marker(pytest.mark.security)
        elif "/tests/evals/" in path_str:
            item.add_marker(pytest.mark.ai)
            item.add_marker(pytest.mark.evals)
        elif "/tests/e2e/" in path_str:
            item.add_marker(pytest.mark.e2e)
        elif "/tests/performance/" in path_str:
            item.add_marker(pytest.mark.performance)


def pytest_runtest_setup(item: pytest.Item) -> None:
    """Enforce credential gating for live provider and live FinnApiGo tests (TEST-12).

    A live-provider test with missing credentials must become BLOCKED, not PASS.
    """
    import os

    # 1. Gate live provider tests
    live_prov_marker = item.get_closest_marker("live_provider")
    if live_prov_marker:
        req_provider = live_prov_marker.kwargs.get("provider") or "any"
        key_map = {
            "openai": ["OPENAI_API_KEY", "BENCHMARK_OPENAI_API_KEY"],
            "gemini": ["GEMINI_API_KEY", "BENCHMARK_GEMINI_API_KEY"],
            "anthropic": ["ANTHROPIC_API_KEY"],
            "deepseek": ["DEEPSEEK_API_KEY"],
            "groq": ["GROQ_API_KEY"],
            "openrouter": ["OPENROUTER_API_KEY"],
        }

        has_creds = False
        if req_provider == "any":
            # Any valid live provider key or explicit LIVE_EXTERNAL_TESTS flag
            all_keys = [k for keys in key_map.values() for k in keys]
            has_creds = any(bool(os.getenv(k)) for k in all_keys) or bool(
                os.getenv("LIVE_EXTERNAL_TESTS")
            )
        else:
            cand_keys = key_map.get(
                req_provider.lower(), [f"{req_provider.upper()}_API_KEY"]
            )
            has_creds = any(bool(os.getenv(k)) for k in cand_keys)

        if not has_creds:
            pytest.skip(
                f"BLOCKED: Live provider test '{item.name}' requires valid credentials for '{req_provider}', but none were provided through secure CI secrets or environment."
            )

    # 2. Gate live FinnApiGo integration tests
    live_finn_marker = item.get_closest_marker("live_finnapigo")
    if live_finn_marker:
        finn_url = os.getenv("FINNAPIGO_LIVE_URL") or os.getenv("FINNAPIGO_BASE_URL")
        enable_flag = os.getenv("FINNAPIGO_LIVE_TESTS")
        if not (finn_url and enable_flag):
            pytest.skip(
                f"BLOCKED: Live FinnApiGo integration test '{item.name}' requires running FinnApiGo authority and FINNAPIGO_LIVE_TESTS=1, but authority credentials/URL were not provided."
            )
