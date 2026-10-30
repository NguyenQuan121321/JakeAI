"""Strict Finn identity dependencies and explicit backend permission checks."""

import hashlib
import hmac
import logging
import time
import uuid
from collections.abc import Callable, Coroutine
from typing import Any

import jwt
from fastapi import Depends, HTTPException, Request
from fastapi.security import HTTPAuthorizationCredentials, HTTPBearer

from app.core.config import get_settings
from app.core.context import TenantContext, set_current_tenant_context
from app.core.identity import verify_access
from app.core.identity_state import AuthorityLease, current_authority, get_state_client

logger = logging.getLogger(__name__)
http_bearer = HTTPBearer(scheme_name="FinnApiGoAuth", auto_error=False)


def _verified_identity(
    token: str,
    secret_key: str | None = None,
    algorithm: str | None = None,
    correlation_id: str | None = None,
) -> tuple[TenantContext, dict[str, Any]]:
    try:
        if secret_key is not None or algorithm is not None:
            raise ValueError("Per-call trust overrides are disabled")
        payload = verify_access(token, get_settings())
    except (ValueError, TypeError, KeyError, UnicodeError, jwt.PyJWTError):
        raise HTTPException(
            401, "Invalid access credential", headers={"WWW-Authenticate": "Bearer"}
        ) from None
    context = TenantContext(
        tenant_id=payload["tid"],
        user_id=payload["sub"],
        explicit_tenant=True,
        roles=[payload["role"]] if payload.get("role") else [],
        permissions=payload["perms"],
        correlation_id=correlation_id or str(uuid.uuid4()),
    )
    set_current_tenant_context(context)
    return context, payload


def verify_finnapigo_jwt(
    token: str,
    secret_key: str | None = None,
    algorithm: str | None = None,
    correlation_id: str | None = None,
) -> TenantContext:
    return _verified_identity(token, secret_key, algorithm, correlation_id)[0]


async def check_token_denylist(token: str) -> None:
    """Compatibility entry point requires actual Finn authority, never local Redis absence."""
    lease = current_authority.get()
    if lease is None or lease.token != token:
        raise HTTPException(503, "Identity authority unavailable")
    await lease.check(force=True)


def verify_internal_perimeter_secret(request: Request | None) -> bool:
    """Verify that request claiming FinnApiGo edge provenance carries valid internal credentials.

    Enforces Invariant 4: Mutual Perimeter Authentication & Network Isolation.
    Accepts either static X-Internal-Secret or timestamped HMAC X-Internal-Sig.
    """
    if request is None or not hasattr(request, "headers"):
        return False

    forwarded_by = request.headers.get("x-forwarded-by", "").strip().lower()
    if forwarded_by != "finnapigo":
        return False

    settings = get_settings()
    configured_secret = settings.INTERNAL_GATEWAY_SECRET
    if not configured_secret:
        return False

    # 1. Check direct X-Internal-Secret header
    internal_secret = request.headers.get("x-internal-secret", "").strip()
    if internal_secret and hmac.compare_digest(internal_secret, configured_secret):
        return True

    # 2. Check timestamped HMAC X-Internal-Sig: t=<unix>;v1=<hmac>
    sig_header = request.headers.get("x-internal-sig", "").strip()
    if sig_header and "v1=" in sig_header and "t=" in sig_header:
        try:
            parts = dict(
                item.split("=", 1) for item in sig_header.split(";") if "=" in item
            )
            ts = int(parts.get("t", "0"))
            v1 = parts.get("v1", "")
            now = int(time.time())
            if abs(now - ts) <= 60:  # 60s replay defense window
                expected = hmac.new(
                    configured_secret.encode(),
                    f"{request.method}|{request.url.path}|{ts}".encode(),
                    hashlib.sha256,
                ).hexdigest()
                if hmac.compare_digest(v1, expected):
                    return True
        except (ValueError, KeyError, TypeError) as exc:
            logger.debug(
                "Failed to parse or verify internal perimeter signature: %s", exc
            )

    return False


async def get_current_tenant(
    request: Request,
    credentials: HTTPAuthorizationCredentials | None = Depends(http_bearer),
) -> TenantContext:
    existing = getattr(request.state, "verified_tenant", None)
    if isinstance(existing, TenantContext):
        return existing
    if credentials is None or credentials.scheme.lower() != "bearer":
        raise HTTPException(
            401, "Access credential required", headers={"WWW-Authenticate": "Bearer"}
        )
    context, claims = _verified_identity(
        credentials.credentials,
        correlation_id=getattr(request.state, "correlation_id", None)
        or request.headers.get("x-correlation-id")
        or request.headers.get("x-request-id"),
    )
    lease = AuthorityLease(credentials.credentials, claims, get_state_client(request))
    await lease.check(force=True)
    current_authority.set(lease)
    request.state.verified_tenant = context
    request.state.authority_lease = lease
    return context


def require_permissions(
    *required_permissions: str,
) -> Callable[..., Coroutine[Any, Any, TenantContext]]:
    async def permission_checker(
        context: TenantContext = Depends(get_current_tenant),
    ) -> TenantContext:
        if not context.has_all_permissions(list(required_permissions)):
            missing = [p for p in required_permissions if not context.has_permission(p)]
            raise HTTPException(403, "Insufficient permissions: " + ", ".join(missing))
        return context

    return permission_checker


def exchange_obo_token(
    context: TenantContext,
    target_audience: str = "finnapigo-api",
    requested_scopes: list[str] | None = None,
    expires_in_seconds: int = 300,
    secret_key: str | None = None,
    algorithm: str | None = None,
) -> str:
    """No broad service-to-user or OBO issuance is authorized by Finn v1."""
    _ = (
        context,
        target_audience,
        requested_scopes,
        expires_in_seconds,
        secret_key,
        algorithm,
    )
    raise HTTPException(503, "OBO issuance is disabled pending a scoped tool contract")
