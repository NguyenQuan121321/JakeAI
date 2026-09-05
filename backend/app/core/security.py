"""Security utilities and FinnApiGo JWT policy enforcement."""

from collections.abc import Callable, Coroutine
from typing import Any

import jwt
from fastapi import Depends, HTTPException, status
from fastapi.security import HTTPAuthorizationCredentials, HTTPBearer

from app.core.config import get_settings
from app.core.context import TenantContext, set_current_tenant_context

http_bearer = HTTPBearer(
    scheme_name="FinnApiGoAuth",
    description="Bearer JWT issued by FinnApiGo upstream identity provider",
    auto_error=True,
)


def verify_finnapigo_jwt(
    token: str,
    secret_key: str | None = None,
    algorithm: str | None = None,
) -> TenantContext:
    """Decode and validate a FinnApiGo JWT access token.

    Verifies signature, expiration, and extracts claims:
    sub, tenant_id, org_id, roles, scopes, permissions.
    """
    settings = get_settings()
    key = secret_key or settings.JWT_SECRET_KEY
    algo = algorithm or settings.JWT_ALGORITHM

    try:
        payload: dict[str, Any] = jwt.decode(
            token,
            key,
            algorithms=[algo],
            options={
                "verify_signature": True,
                "verify_exp": True,
                "require": ["sub", "tenant_id"],
            },
        )
    except jwt.ExpiredSignatureError as e:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Authentication token has expired",
            headers={"WWW-Authenticate": "Bearer"},
        ) from e
    except jwt.InvalidTokenError as e:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Invalid authentication token",
            headers={"WWW-Authenticate": "Bearer"},
        ) from e

    sub = str(payload.get("sub", ""))
    tenant_id = str(payload.get("tenant_id", ""))

    if not sub or not tenant_id:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Token missing mandatory subject (sub) or tenant_id claim",
            headers={"WWW-Authenticate": "Bearer"},
        )

    roles = payload.get("roles", [])
    if isinstance(roles, str):
        roles = [roles]

    scopes = payload.get("scopes", [])
    if isinstance(scopes, str):
        scopes = scopes.split(" ")

    permissions = payload.get("permissions", [])
    if isinstance(permissions, str):
        permissions = [permissions]

    context = TenantContext(
        tenant_id=tenant_id,
        user_id=sub,
        org_id=payload.get("org_id"),
        roles=[str(r) for r in roles],
        scopes=[str(s) for s in scopes],
        permissions=[str(p) for p in permissions],
    )
    set_current_tenant_context(context)
    return context


async def get_current_tenant(
    credentials: HTTPAuthorizationCredentials = Depends(http_bearer),
) -> TenantContext:
    """FastAPI security dependency resolving and validating TenantContext."""
    return verify_finnapigo_jwt(credentials.credentials)


def require_permissions(
    *required_permissions: str,
) -> Callable[..., Coroutine[Any, Any, TenantContext]]:
    """Dependency factory enforcing granular permissions on routes."""

    async def permission_checker(
        context: TenantContext = Depends(get_current_tenant),
    ) -> TenantContext:
        if not context.has_all_permissions(list(required_permissions)):
            missing = [p for p in required_permissions if not context.has_permission(p)]
            raise HTTPException(
                status_code=status.HTTP_403_FORBIDDEN,
                detail=f"Insufficient permissions. Required: {', '.join(missing)}",
            )
        return context

    return permission_checker
