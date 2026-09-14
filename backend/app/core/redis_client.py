"""Shared lazy Redis client acquisition plumbing (single authority).

R-ARCH-03: the eight near-identical ``_get_redis`` helpers across
infrastructure modules (checkpoint, resume_bridge, rate_limiter, budget, byok,
semantic_cache, rag/tasks, ai_gateway) all duplicated the same
construct-from-URL + ping sequence, each with slightly diverging timeouts and
decode modes. Construction and availability verification live here exactly
once; every caller keeps its own availability-latch / reconnect-cooldown
policy and test-double handling (``is_mock_redis_client``,
``is_client_bound_to_current_loop``).

Per-request lifecycle clients that must distinguish connect-failure from
ping-failure (health probes, token denylist checks) construct and close their
own short-lived clients and intentionally do not use this module.
"""

from __future__ import annotations

import asyncio
from typing import Any

from app.core.config import get_settings


def is_mock_redis_client(client: Any) -> bool:
    """True when the caller-injected client is a test double (Mock/AsyncMock)."""
    return type(client).__name__.startswith(("Mock", "AsyncMock")) or hasattr(
        client, "_mock_return_value"
    )


def is_client_bound_to_current_loop(client: Any) -> bool:
    """False when a cached client is bound to a different or closed event loop.

    Such clients must be discarded and re-created on the current loop; any
    introspection failure counts as unusable.
    """
    try:
        current_loop = asyncio.get_running_loop()
        pool = getattr(client, "connection_pool", None)
        client_loop = (
            getattr(pool, "_loop", None)
            if pool is not None
            else getattr(client, "_loop", None)
        )
        if isinstance(client_loop, asyncio.AbstractEventLoop) and (
            client_loop is not current_loop or client_loop.is_closed()
        ):
            return False
    except Exception:
        return False
    return True


async def acquire_redis_client(
    *,
    decode_responses: bool = True,
    connect_timeout: float = 0.2,
    socket_timeout: float = 0.2,
) -> Any | None:
    """Create a Redis client from configured REDIS_URL and verify it with ping.

    Returns the connected client, or None when construction/ping fails for any
    reason. Callers decide their own retry/latch policy on a None result.
    """
    try:
        from redis import asyncio as aioredis

        settings = get_settings()
        client = aioredis.from_url(
            settings.REDIS_URL,
            encoding="utf-8",
            decode_responses=decode_responses,
            socket_connect_timeout=connect_timeout,
            socket_timeout=socket_timeout,
        )
        await client.ping()
        return client
    except Exception:
        return None
