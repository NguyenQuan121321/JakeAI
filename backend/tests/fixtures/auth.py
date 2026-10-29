import base64
import binascii
import hashlib
import time
from typing import Any

import jwt

from app.core.config import get_settings

FULL_TEST_PERMISSIONS = [
    "chat:read",
    "chat:write",
    "rag:read",
    "rag:write",
    "byok:read",
    "byok:write",
    "finops:read",
    "finops:write",
    "ops:read",
    "agent:read",
    "agent:write",
    "agent:execute",
    "agent:approve",
]


def subject_id(sub: str) -> str:
    return str(
        int(sub)
        if sub.isdecimal()
        else int(hashlib.sha256(sub.encode()).hexdigest()[:12], 16) + 1
    )


def create_test_jwt(
    sub: str = "user-12345",
    tenant_id: str = "tenant-fin-corp",
    roles: list[str] | None = None,
    permissions: list[str] | None = None,
    expires_in: int = 900,
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

    uid = int(subject_id(sub))
    payload: dict[str, Any] = {
        "contract_ver": 1,
        "iss": "finnapigo",
        "aud": ["finnapigo-api", "jakeai-service"],
        "sub": str(uid),
        "uid": uid,
        "tid": tenant_id,
        "iat": now,
        "nbf": now,
        "exp": now + expires_in,
        "sid": "synthetic-session-" + str(uid),
        "jti": "synthetic-token-" + str(uid),
        "pwdver": 0,
        "auth_epoch": 0,
        "role": primary_role,
        "perms": effective_perms,
        "type": token_type,
    }
    if "jti" in extra_claims:
        payload["jti"] = extra_claims.pop("jti")
    payload.update(extra_claims)

    jwt_headers = dict(headers or {})
    if "kid" not in jwt_headers and isinstance(key, str):
        jwt_headers["kid"] = settings.JWT_KEY_ID

    try:
        signing_bytes = base64.b64decode(key)
    except binascii.Error:
        signing_bytes = key.encode()  # Deliberately invalid-signature fixture keys.
    return jwt.encode(payload, signing_bytes, algorithm=algorithm, headers=jwt_headers)


def generate_agent_jwt(
    sub: str = "user-agent-tester",
    tenant_id: str = "tenant-agent-alpha",
    roles: list[str] | None = None,
    permissions: list[str] | None = None,
    expires_in: int = 900,
) -> str:
    """Generate HS256 JWT context for Agent API tests."""
    return create_test_jwt(
        sub=sub,
        tenant_id=tenant_id,
        roles=roles or ["admin", "developer"],
        permissions=permissions
        if permissions is not None
        else ["agent:write", "agent:read", "agent:execute", "agent:approve"],
        expires_in=expires_in,
    )
