"""Authenticated, bounded Finn HTTPS introspection; no cross-request positive cache."""

import asyncio
import hashlib
import json
import ssl
import time
from contextvars import ContextVar
from dataclasses import dataclass, field
from typing import Any
from urllib.parse import urlsplit

import httpx
import jwt
from fastapi import HTTPException

from app.core.config import Settings, get_settings
from app.core.identity import decode_signing_key, unique_object, verify_access
from app.core.secret_material import validate_key_id


class IdentityStateClient:
    def __init__(self, settings: Settings):
        target = urlsplit(settings.IDENTITY_STATE_URL)
        if (
            target.scheme != "https"
            or not target.hostname
            or target.username
            or target.password
            or target.query
            or target.fragment
            or target.path != "/api/v1/identity/introspect"
        ):
            raise ValueError("Verified HTTPS introspection endpoint required")
        decode_signing_key(settings.IDENTITY_STATE_SECRET)
        validate_key_id(settings.IDENTITY_STATE_KEY_ID)
        self.settings = settings
        self.slots = asyncio.Semaphore(settings.IDENTITY_STATE_CONCURRENCY)
        ca = ssl.create_default_context(cafile=settings.IDENTITY_STATE_CA_FILE or None)
        self.client = httpx.AsyncClient(
            verify=ca,
            follow_redirects=False,
            trust_env=False,
            timeout=settings.IDENTITY_STATE_TIMEOUT_SECONDS,
            limits=httpx.Limits(
                max_connections=settings.IDENTITY_STATE_CONCURRENCY,
                max_keepalive_connections=settings.IDENTITY_STATE_CONCURRENCY,
            ),
        )

    async def close(self) -> None:
        await self.client.aclose()

    async def check(self, token: str, claims: dict[str, Any]) -> None:
        s = self.settings
        try:
            async with asyncio.timeout(s.IDENTITY_STATE_TIMEOUT_SECONDS):
                async with self.slots:
                    async with self.client.stream(
                        "POST",
                        s.IDENTITY_STATE_URL,
                        headers={
                            "Authorization": "Bearer " + s.IDENTITY_STATE_SECRET,
                            "X-Service-Key-ID": s.IDENTITY_STATE_KEY_ID,
                        },
                        json={"token": token, "tenant_id": claims["tid"]},
                    ) as response:
                        body = bytearray()
                        async for chunk in response.aiter_bytes():
                            body.extend(chunk)
                            if len(body) > 4096:
                                raise ValueError("Oversize state response")
                        result = unique_object(bytes(body))
                        if response.status_code == 401 and result == {"active": False}:
                            raise HTTPException(
                                401,
                                "Inactive access credential",
                                headers={"WWW-Authenticate": "Bearer"},
                            )
                        if response.status_code != 200:
                            raise ValueError(
                                "State service unavailable or misconfigured"
                            )
                        for name in (
                            "contract_ver",
                            "tid",
                            "sub",
                            "sid",
                            "jti",
                            "pwdver",
                            "auth_epoch",
                        ):
                            if (
                                type(result.get(name)) is not type(claims[name])
                                or result[name] != claims[name]
                            ):
                                raise ValueError("Mismatched state identity")
                        now = time.time()
                        if (
                            result.get("active") is not True
                            or type(result.get("checked_at")) is not int
                            or not now - 5 <= result["checked_at"] <= now + 1
                            or type(result.get("max_cache_seconds")) is not int
                            or not 0 <= result["max_cache_seconds"] <= 15
                        ):
                            raise ValueError("Unknown or stale state")
        except HTTPException:
            raise
        except (httpx.HTTPError, TimeoutError, ValueError, KeyError, TypeError):
            raise HTTPException(503, "Identity authority unavailable") from None


@dataclass
class AuthorityLease:
    """Request-local state only; raw credentials never serialize or appear in repr."""

    token: str = field(repr=False)
    claims: dict[str, Any] = field(repr=False)
    client: IdentityStateClient = field(repr=False)
    checked_monotonic: float = 0

    async def check(self, *, force: bool = False) -> None:
        # Re-verify expiry/key retirement even on a recent state result.
        try:
            verify_access(self.token, self.client.settings)
        except (ValueError, TypeError, KeyError, UnicodeError, jwt.PyJWTError) as exc:
            # No exception text: token libraries can include attacker-controlled data.
            raise HTTPException(401, "Invalid access credential") from exc
        if force or time.monotonic() - self.checked_monotonic >= 10:
            await self.client.check(self.token, self.claims)
            self.checked_monotonic = time.monotonic()


current_authority: ContextVar[AuthorityLease | None] = ContextVar(
    "authority", default=None
)


async def authorize_effect(*permissions: str) -> None:
    lease = current_authority.get()
    if lease is None:
        raise HTTPException(503, "Fresh user authority required")
    await lease.check(force=True)
    if any(p not in lease.claims["perms"] for p in permissions):
        raise HTTPException(403, "Insufficient permission")


def principal_namespace(tenant_id: str) -> str:
    """Prevent cache reuse across subjects, sessions and authorization versions."""
    lease = current_authority.get()
    if lease is None:
        return tenant_id
    if tenant_id != lease.claims["tid"]:
        raise HTTPException(404, "Not found")
    fields = {
        k: lease.claims[k]
        for k in ("tid", "sub", "sid", "jti", "pwdver", "auth_epoch", "perms")
    }
    return (
        "principal:"
        + hashlib.sha256(json.dumps(fields, sort_keys=True).encode()).hexdigest()
    )


async def authorize_bound_effect(tenant_id: str, *permissions: str) -> None:
    lease = current_authority.get()
    if lease is None and get_settings().ENVIRONMENT.lower() != "production":
        return  # Explicit offline component fixtures; never a production authority.
    if lease is not None and tenant_id != lease.claims["tid"]:
        raise HTTPException(404, "Not found")
    await authorize_effect(*permissions)


def get_state_client(request: Any) -> IdentityStateClient:
    client = getattr(request.app.state, "identity_client", None)
    if client is None:
        try:
            client = IdentityStateClient(get_settings())
        except (ValueError, OSError):
            raise HTTPException(503, "Identity authority unavailable") from None
        request.app.state.identity_client = client
    return client
