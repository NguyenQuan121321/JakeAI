"""Authenticated, bounded Finn HTTPS introspection; no cross-request positive cache."""

import asyncio
import hashlib
import hmac
import json
import ssl
import time
from collections.abc import Mapping
from contextvars import ContextVar
from dataclasses import dataclass, field
from types import MappingProxyType
from typing import Any
from urllib.parse import urlsplit

import httpx
import jwt
from fastapi import HTTPException

from app.core.config import Settings, get_settings
from app.core.identity import configured_keys, decode_signing_key, unique_object
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

    async def check(self, token: str, claims: Mapping[str, Any]) -> None:
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
                            "Accept-Encoding": "identity",
                        },
                        json={"token": token, "tenant_id": claims["tid"]},
                    ) as response:
                        if (
                            response.headers.get("Content-Encoding", "identity")
                            != "identity"
                        ):
                            raise ValueError("Compressed state response is unsupported")
                        if not response.headers.get("Content-Type", "").startswith(
                            "application/json"
                        ):
                            raise ValueError("JSON state response required")
                        body = bytearray()
                        async for chunk in response.aiter_bytes(chunk_size=4097):
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
    claims: Mapping[str, Any] = field(repr=False)
    client: IdentityStateClient = field(repr=False)
    checked_monotonic: float = 0
    signing_kid: str = field(init=False, repr=False)
    signing_fingerprint: bytes = field(init=False, repr=False)
    denial: HTTPException | None = field(default=None, init=False, repr=False)
    operation_permissions: tuple[str, ...] = field(default=(), init=False)

    def __post_init__(self) -> None:
        # The factory passes signature-verified claims. Retain immutable authority,
        # rather than re-parsing/re-verifying the same signature on every byte.
        self.claims = MappingProxyType(
            {**self.claims, "perms": tuple(self.claims["perms"])}
        )
        self.signing_kid = jwt.get_unverified_header(self.token)["kid"]
        key = configured_keys(self.client.settings)[self.signing_kid]
        self.signing_fingerprint = hashlib.sha256(key).digest()

    async def check(self, *, force: bool = False) -> None:
        # Recheck expiry and the configured keyset/deadline even on recent state.
        if self.denial is not None:
            raise self.denial
        try:
            key = configured_keys(self.client.settings).get(self.signing_kid)
            now = time.time()
            if (
                key is None
                or not hmac.compare_digest(
                    hashlib.sha256(key).digest(), self.signing_fingerprint
                )
                or now >= self.claims["exp"] + 30
                or now + 30 < self.claims["nbf"]
                or now + 30 < self.claims["iat"]
            ):
                raise ValueError
        except (ValueError, TypeError, KeyError, UnicodeError, jwt.PyJWTError) as exc:
            # No exception text: token libraries can include attacker-controlled data.
            self.denial = HTTPException(401, "Invalid access credential")
            raise self.denial from exc
        if force or time.monotonic() - self.checked_monotonic >= 10:
            try:
                await self.client.check(self.token, self.claims)
            except HTTPException as exc:
                self.denial = exc
                raise
            if self.denial is not None:
                raise self.denial
            self.checked_monotonic = time.monotonic()


current_authority: ContextVar[AuthorityLease | None] = ContextVar(
    "authority", default=None
)


async def authorize_effect(*permissions: str) -> None:
    lease = current_authority.get()
    if lease is None:
        raise HTTPException(503, "Fresh user authority required")
    await lease.check(force=True)
    if not lease.operation_permissions:
        raise HTTPException(503, "Bound route authority required")
    if any(
        p not in lease.claims["perms"]
        for p in (*lease.operation_permissions, *permissions)
    ):
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
