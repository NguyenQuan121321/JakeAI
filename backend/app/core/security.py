"""Security utilities and FinnApiGo JWT policy enforcement."""

import hashlib
import hmac
import logging
import time
import uuid
from collections.abc import Callable, Coroutine
from typing import Any

import jwt
from fastapi import Depends, HTTPException, Request, status
from fastapi.security import HTTPAuthorizationCredentials, HTTPBearer

from app.core.config import get_settings
from app.core.context import TenantContext, set_current_tenant_context

logger = logging.getLogger(__name__)

http_bearer = HTTPBearer(
    scheme_name="FinnApiGoAuth",
    description="Bearer JWT issued by FinnApiGo upstream identity provider",
    auto_error=True,
)


def _kid_for(secret: str) -> str:
    """Derive key identifier matching FinnApiGo's kid: first 8 hex chars of SHA-256(secret)."""
    return hashlib.sha256(secret.encode("utf-8")).hexdigest()[:8]


def verify_finnapigo_jwt(
    token: str,
    secret_key: str | None = None,
    algorithm: str | None = None,
    correlation_id: str | None = None,
) -> TenantContext:
    """Decode and validate a FinnApiGo JWT access token.

    Verifies signature (supporting key rotation and kid matching identical to FinnApiGo),
    expiration, and extracts claims supporting both FinnApiGo compact enterprise schema
    (tid, perms, role, uid) and standard expanded claims (tenant_id, permissions, roles, sub).
    Preserves single correlation ID (OPS-04).
    """
    settings = get_settings()
    algo = algorithm or settings.JWT_ALGORITHM

    # Build candidate keys
    if secret_key:
        candidate_keys = [secret_key]
    else:
        candidate_keys = []
        if settings.JWT_SECRET_KEY:
            candidate_keys.append(settings.JWT_SECRET_KEY)
        if (
            settings.JWT_SECRET_PREVIOUS
            and settings.JWT_SECRET_PREVIOUS not in candidate_keys
        ):
            candidate_keys.append(settings.JWT_SECRET_PREVIOUS)

        # In non-production environments, provide known dev secret fallbacks
        if getattr(settings, "ENVIRONMENT", "").lower() in (
            "development",
            "test",
            "testing",
            "local",
            "",
        ):
            dev_fallbacks = [
                "a04c1981ceded10b6ecadc8c0504f89f524b7b9057ed5036233803a78bee7fc8",
                "a8f3e2b1c9d7f6e5a4b3c2d1e0f9a8b7c6d5e4f3a2b1c0d9e8f7a6b5c4d3e2",
            ]
            for fb in dev_fallbacks:
                if fb not in candidate_keys:
                    candidate_keys.append(fb)

    # Inspect token header for kid and alg
    header_kid: str | None = None
    try:
        header = jwt.get_unverified_header(token)
        header_kid = header.get("kid")
        if header.get("alg") == "HS256" and algo.startswith("RS"):
            algo = "HS256"
    except jwt.PyJWTError as exc:
        logger.debug("Failed to inspect JWT header: %s", exc)

    if header_kid:
        candidate_keys.sort(
            key=lambda k: 0 if isinstance(k, str) and _kid_for(k) == header_kid else 1
        )

    payload: dict[str, Any] | None = None
    last_error: Exception | None = None

    for key in candidate_keys:
        current_algo = algo
        if current_algo.startswith("RS") and not (
            isinstance(key, str) and key.strip().startswith("-----BEGIN")
        ):
            current_algo = "HS256"

        try:
            payload = jwt.decode(
                token,
                key,
                algorithms=[current_algo],
                options={
                    "verify_signature": True,
                    "verify_exp": True,
                    "verify_aud": False,
                },
            )
            break
        except jwt.ExpiredSignatureError as e:
            raise HTTPException(
                status_code=status.HTTP_401_UNAUTHORIZED,
                detail="Authentication token has expired",
                headers={"WWW-Authenticate": "Bearer"},
            ) from e
        except jwt.InvalidTokenError as e:
            last_error = e
            continue

    if payload is None:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Invalid authentication token",
            headers={"WWW-Authenticate": "Bearer"},
        ) from last_error

    # Invariant 5: Token Type Isolation
    token_type = payload.get("type")
    if token_type and token_type != "access":
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail=f"Invalid token type '{token_type}': expected access token",
            headers={"WWW-Authenticate": "Bearer"},
        )

    # Invariant 5: Dual Claim Schema Resolution
    sub = str(payload.get("sub") or payload.get("uid") or "")
    tenant_id = str(payload.get("tenant_id") or payload.get("tid") or "default")

    if not sub:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Token missing mandatory subject (sub/uid)",
            headers={"WWW-Authenticate": "Bearer"},
        )

    raw_roles = payload.get("roles") or payload.get("role") or []
    roles = [raw_roles] if isinstance(raw_roles, str) else list(raw_roles)

    # `or []` also absorbs a present-but-null claim (same as roles/perms).
    scopes = payload.get("scopes") or []
    if isinstance(scopes, str):
        scopes = scopes.split(" ")

    raw_perms = payload.get("permissions") or payload.get("perms") or []
    permissions = [raw_perms] if isinstance(raw_perms, str) else list(raw_perms)

    # Preserve single correlation ID (TASK OPS-04)
    cid = correlation_id or payload.get("cid") or str(uuid.uuid4())
    context = TenantContext(
        tenant_id=tenant_id,
        user_id=sub,
        org_id=payload.get("org_id"),
        roles=[str(r) for r in roles],
        scopes=[str(s) for s in scopes],
        permissions=[str(p) for p in permissions],
        correlation_id=cid,
    )
    set_current_tenant_context(context)
    return context


async def check_token_denylist(token: str) -> None:
    """Verify that caller token JTI or session UUID is not denylisted in Redis."""
    try:
        payload = jwt.decode(
            token,
            options={"verify_signature": False, "verify_exp": False},
        )
    except jwt.PyJWTError:
        return

    jti = str(payload.get("jti") or payload.get("id") or "")
    sid = str(payload.get("sid") or "")
    if not jti and not sid:
        return

    settings = get_settings()
    try:
        import redis.asyncio as aioredis

        client = aioredis.from_url(
            settings.REDIS_URL,
            socket_connect_timeout=0.2,
            socket_timeout=0.2,
        )
        if jti and await client.exists(f"denylist:jti:{jti}"):
            await client.aclose()
            raise HTTPException(
                status_code=status.HTTP_401_UNAUTHORIZED,
                detail="Token has been revoked",
                headers={"WWW-Authenticate": "Bearer"},
            )
        if sid and await client.exists(f"denylist:sid:{sid}"):
            await client.aclose()
            raise HTTPException(
                status_code=status.HTTP_401_UNAUTHORIZED,
                detail="Session has been revoked",
                headers={"WWW-Authenticate": "Bearer"},
            )
        await client.aclose()
    except HTTPException:
        raise
    except Exception as exc:
        # Bounded resilience: if Redis is unreachable, fail open bounded by access token TTL
        logger.warning("Redis token denylist check unavailable, failing open: %s", exc)


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
    credentials: HTTPAuthorizationCredentials = Depends(http_bearer),
) -> TenantContext:
    """FastAPI security dependency resolving and validating TenantContext (TASK OPS-04)."""
    cid = (
        getattr(request.state, "correlation_id", None)
        if hasattr(request, "state")
        else None
    )
    if not cid and hasattr(request, "headers"):
        cid = request.headers.get("x-correlation-id") or request.headers.get(
            "x-request-id"
        )
    context = verify_finnapigo_jwt(credentials.credentials, correlation_id=cid)
    await check_token_denylist(credentials.credentials)
    return context


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


def exchange_obo_token(
    context: TenantContext,
    target_audience: str = "finnapigo-api",
    requested_scopes: list[str] | None = None,
    expires_in_seconds: int = 300,
    secret_key: str | None = None,
    algorithm: str | None = None,
) -> str:
    """Exchange caller TenantContext for a signed On-Behalf-Of (OBO) JWT token.

    Adheres to RFC 8693 token exchange standards with an 'act' (actor) claim
    identifying JakeAI Platform as the authorized executor on behalf of the user.
    """
    settings = get_settings()
    key = secret_key or settings.JWT_SECRET_KEY
    algo = algorithm or settings.JWT_ALGORITHM

    # If algorithm is RSA but key is a symmetric secret string, fall back to HS256
    if algo.startswith("RS") and not (
        isinstance(key, str) and key.strip().startswith("-----BEGIN")
    ):
        algo = "HS256"

    now = int(time.time())
    scopes = requested_scopes if requested_scopes is not None else context.scopes

    payload: dict[str, Any] = {
        "sub": context.user_id,
        "tenant_id": context.tenant_id,
        "org_id": context.org_id,
        "roles": context.roles,
        "scopes": scopes,
        "permissions": context.permissions,
        "cid": context.correlation_id,
        "aud": target_audience,
        "iss": "jakeai-gateway",
        "act": {
            "sub": "jakeai-platform",
            "client_id": "jakeai-gateway",
        },
        "iat": now,
        "exp": now + expires_in_seconds,
    }

    return jwt.encode(payload, key, algorithm=algo)
