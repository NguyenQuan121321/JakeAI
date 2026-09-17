import hashlib
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
    token_type: str = "access",
    headers: dict[str, Any] | None = None,
    **extra_claims: Any,
) -> str:
    """Generate an authoritative test JWT token matching JakeAI and FinnApiGo contracts."""
    settings = get_settings()
    key = secret_key or settings.JWT_SECRET_KEY
    now = int(time.time())

    effective_roles = roles if roles is not None else ["user"]
    primary_role = effective_roles[0] if effective_roles else "user"
    effective_perms = (
        permissions if permissions is not None else ["chat:read", "chat:write"]
    )

    payload: dict[str, Any] = {
        "sub": sub,
        "uid": sub,
        "tenant_id": tenant_id,
        "tid": tenant_id,
        "iat": now,
        "exp": now + expires_in,
        "roles": effective_roles,
        "role": primary_role,
        "permissions": effective_perms,
        "perms": effective_perms,
        "type": token_type,
    }
    if "jti" in extra_claims:
        payload["jti"] = extra_claims.pop("jti")
    payload.update(extra_claims)

    jwt_headers = dict(headers or {})
    if "kid" not in jwt_headers and isinstance(key, str):
        jwt_headers["kid"] = hashlib.sha256(key.encode("utf-8")).hexdigest()[:8]

    return jwt.encode(payload, key, algorithm=algorithm, headers=jwt_headers)


def generate_agent_jwt(
    sub: str = "user-agent-tester",
    tenant_id: str = "tenant-agent-alpha",
    roles: list[str] | None = None,
    permissions: list[str] | None = None,
    expires_in: int = 3600,
) -> str:
    """Generate HS256 JWT context for Agent API tests."""
    return create_test_jwt(
        sub=sub,
        tenant_id=tenant_id,
        roles=roles or ["admin", "developer"],
        permissions=permissions or ["agent:write", "agent:read"],
        expires_in=expires_in,
    )
