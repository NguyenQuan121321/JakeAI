"""Shared authentication fixtures and JWT helpers for test execution."""

import time
from typing import Any

import jwt

from app.core.config import get_settings


def create_test_jwt(
    sub: str = "user-12345",
    tenant_id: str = "tenant-fin-corp",
    roles: list[str] | None = None,
    permissions: list[str] | None = None,
    expires_in: int = 3600,
    secret_key: str | None = None,
    algorithm: str = "HS256",
) -> str:
    """Generate a test JWT token for test assertions."""
    settings = get_settings()
    key = secret_key or settings.JWT_SECRET_KEY
    now = int(time.time())

    payload: dict[str, Any] = {
        "sub": sub,
        "tenant_id": tenant_id,
        "iat": now,
        "exp": now + expires_in,
        "roles": roles or ["user"],
        "permissions": permissions or ["chat:read", "chat:write"],
    }
    return jwt.encode(payload, key, algorithm=algorithm)


def generate_agent_jwt(
    sub: str = "user-agent-tester",
    tenant_id: str = "tenant-agent-alpha",
    roles: list[str] | None = None,
    permissions: list[str] | None = None,
    expires_in: int = 3600,
) -> str:
    """Generate HS256 JWT context for Agent API tests."""
    settings = get_settings()
    now = int(time.time())
    payload: dict[str, Any] = {
        "sub": sub,
        "tenant_id": tenant_id,
        "iat": now,
        "exp": now + expires_in,
        "roles": roles or ["admin", "developer"],
        "permissions": permissions or ["agent:write", "agent:read"],
    }
    return jwt.encode(payload, settings.JWT_SECRET_KEY, algorithm="HS256")
