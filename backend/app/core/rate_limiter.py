"""Redis-backed Token Bucket Rate Limiter with In-Memory Resilient Fallback."""

import time
from typing import Any

import redis.asyncio as aioredis
from fastapi import HTTPException, Request, status

from app.core.config import get_settings

# Atomic Redis Lua script to eliminate TOCTOU race conditions under high concurrency
TOKEN_BUCKET_LUA = """
local key = KEYS[1]
local capacity = tonumber(ARGV[1])
local refill_rate = tonumber(ARGV[2])
local now = tonumber(ARGV[3])
local ttl = tonumber(ARGV[4])

local data = redis.call('HMGET', key, 'tokens', 'last_time')
local last_tokens = tonumber(data[1])
local last_time = tonumber(data[2])

if not last_tokens or not last_time then
    last_tokens = capacity
    last_time = now
end

local elapsed = math.max(0, now - last_time)
local current_tokens = math.min(capacity, last_tokens + (elapsed * refill_rate))

if current_tokens >= 1.0 then
    current_tokens = current_tokens - 1.0
    redis.call('HSET', key, 'tokens', tostring(current_tokens))
    redis.call('HSET', key, 'last_time', tostring(now))
    redis.call('EXPIRE', key, ttl)
    return {1, math.floor(current_tokens), 0}
else
    local wait_time = (1.0 - current_tokens) / refill_rate
    return {0, math.floor(current_tokens), math.ceil(wait_time)}
end
"""


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
                    socket_connect_timeout=0.2,
                    socket_timeout=0.2,
                )
                await client.ping()
                self._redis_client = client
            except Exception:
                self._redis_client = None
                self._redis_retry_after = now + 30.0  # Back off 30s before retrying
        return self._redis_client

    def _prune_memory_store(self, now: float) -> None:
        """Prevent unbounded memory growth by pruning stale in-memory bucket entries."""
        if len(self._memory_store) > 1000:
            stale_cutoff = now - 120.0
            stale_keys = [
                k
                for k, (_, last_refill) in self._memory_store.items()
                if last_refill < stale_cutoff
            ]
            for k in stale_keys:
                del self._memory_store[k]

    def _check_in_memory(self, key: str) -> tuple[bool, int, float]:
        """Evaluate token bucket consumption in local memory with leak protection."""
        now = time.time()
        self._prune_memory_store(now)

        tokens, last_refill = self._memory_store.get(key, (float(self.capacity), now))

        # Refill tokens based on elapsed time
        elapsed = max(0.0, now - last_refill)
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
        """Verify token bucket availability atomically.

        Returns:
            (is_allowed, remaining_tokens, retry_after_seconds)
        """
        key = f"ratelimit:{tenant_id}:{client_ip}"
        redis = await self._get_redis()

        if redis is None:
            return self._check_in_memory(key)

        now = time.time()

        try:
            # Execute atomic Lua script inside Redis
            result: Any = await redis.eval(
                TOKEN_BUCKET_LUA,
                1,
                key,
                self.capacity,
                self.refill_rate,
                now,
                60,
            )

            if isinstance(result, list) and len(result) >= 3:
                allowed = bool(result[0] == 1)
                remaining = int(result[1])
                wait_time = float(result[2])
                return allowed, remaining, wait_time

            return self._check_in_memory(key)
        except Exception:
            # On connection failure, reset client and fall back to memory
            self._redis_client = None
            self._redis_retry_after = now + 15.0
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
