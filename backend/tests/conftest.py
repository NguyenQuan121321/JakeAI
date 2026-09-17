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
