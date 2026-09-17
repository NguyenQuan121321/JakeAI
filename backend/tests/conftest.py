"""Root pytest fixtures and configuration registering shared test fixtures."""

import pytest

from tests.fixtures.auth import create_test_jwt, generate_agent_jwt
from tests.fixtures.client import async_client

__all__ = [
    "async_client",
    "create_test_jwt",
    "generate_agent_jwt",
]


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
