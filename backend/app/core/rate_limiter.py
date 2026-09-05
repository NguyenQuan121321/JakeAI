"""Redis-backed Token Bucket Rate Limiter with In-Memory Resilient Fallback."""

import time
from typing import Any

import redis.asyncio as aioredis
from fastapi import HTTPException, Request, status

from app.core.config import get_settings


class TokenBucketRateLimiter:
    """Token bucket rate limiter supporting Redis and in-memory local caching."""

    def __init__(
        self,
        rate_per_minute: int = 60,
        burst: int = 10,
        enable_redis: bool = True,
    ) -> None:
        self.rate_per_minute = rate_per_minute
        self.capacity = burst
        self.refill_rate = rate_per_minute / 60.0  # Tokens per second
        self.enable_redis = enable_redis
        self._memory_store: dict[str, tuple[float, float]] = {}
        self._redis_client: aioredis.Redis | None = None
        self._redis_retry_after: float = 0.0

    async def _get_redis(self) -> aioredis.Redis | None:
        """Lazily initialize Redis async connection with connection failure backoff."""
        if not self.enable_redis:
            return None

        now = time.time()
        if self._redis_client is None:
            if now < self._redis_retry_after:
                return None
            settings = get_settings()
            try:
                client = aioredis.from_url(
                    settings.REDIS_URL,
                    encoding="utf-8",
                    decode_responses=True,
                    socket_connect_timeout=0.1,
                    socket_timeout=0.1,
                )
                await client.ping()
                self._redis_client = client
            except Exception:
                self._redis_client = None
                self._redis_retry_after = now + 30.0  # Back off 30s before retrying
        return self._redis_client

    def _check_in_memory(self, key: str) -> tuple[bool, int, float]:
        """Evaluate token bucket consumption in local memory."""
        now = time.time()
        tokens, last_refill = self._memory_store.get(key, (float(self.capacity), now))

        # Refill tokens based on elapsed time
        elapsed = now - last_refill
        tokens = min(float(self.capacity), tokens + (elapsed * self.refill_rate))

        if tokens >= 1.0:
            tokens -= 1.0
            self._memory_store[key] = (tokens, now)
            return True, int(tokens), 0.0

        wait_time = (1.0 - tokens) / self.refill_rate
        return False, int(tokens), round(wait_time, 2)

    async def check(
        self,
        tenant_id: str,
        client_ip: str,
    ) -> tuple[bool, int, float]:
        """Verify token bucket availability.

        Returns:
            (is_allowed, remaining_tokens, retry_after_seconds)
        """
        key = f"ratelimit:{tenant_id}:{client_ip}"
        redis = await self._get_redis()

        if redis is None:
            return self._check_in_memory(key)

        # Atomic Redis token bucket evaluation
        now = time.time()
        token_key = f"{key}:tokens"
        time_key = f"{key}:timestamp"

        try:
            async with redis.pipeline(transaction=True) as pipe:
                pipe.get(token_key)
                pipe.get(time_key)
                results: list[Any] = await pipe.execute()

            raw_tokens, raw_time = results[0], results[1]
            last_tokens = (
                float(raw_tokens) if raw_tokens is not None else float(self.capacity)
            )
            last_time = float(raw_time) if raw_time is not None else now

            elapsed = now - last_time
            current_tokens = min(
                float(self.capacity),
                last_tokens + (elapsed * self.refill_rate),
            )

            if current_tokens >= 1.0:
                current_tokens -= 1.0
                async with redis.pipeline(transaction=True) as pipe:
                    pipe.set(token_key, current_tokens, ex=60)
                    pipe.set(time_key, now, ex=60)
                    await pipe.execute()
                return True, int(current_tokens), 0.0

            wait_time = (1.0 - current_tokens) / self.refill_rate
            return False, int(current_tokens), round(wait_time, 2)
        except Exception:
            # Resilient fallback to memory if Redis operation times out
            return self._check_in_memory(key)


default_rate_limiter = TokenBucketRateLimiter(rate_per_minute=60, burst=10)


async def enforce_rate_limit(
    request: Request,
    tenant_id: str,
    limiter: TokenBucketRateLimiter = default_rate_limiter,
) -> None:
    """Enforce rate limits per tenant and client IP address."""
    client_ip = request.client.host if request.client else "127.0.0.1"
    allowed, remaining, retry_after = await limiter.check(tenant_id, client_ip)

    if not allowed:
        raise HTTPException(
            status_code=status.HTTP_429_TOO_MANY_REQUESTS,
            detail="Rate limit exceeded. Please throttle your requests.",
            headers={
                "Retry-After": str(int(retry_after) + 1),
                "X-RateLimit-Limit": str(limiter.capacity),
                "X-RateLimit-Remaining": str(remaining),
                "X-RateLimit-Reset": str(int(time.time() + retry_after)),
            },
        )
