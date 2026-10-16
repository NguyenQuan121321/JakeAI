"""BYOK ciphertext custody with atomic compare-and-swap; no implicit fallback."""

import asyncio
from typing import Any

from app.core.redis_client import create_redis_client


class BYOKError(ValueError):
    """Fixed public code, independent of dependency exception messages/secret values."""

    def __init__(self, code: str, status_code: int = 503) -> None:
        self.code = code
        self.status_code = status_code
        super().__init__(code)


class MemoryStore:
    """Explicit development/test store, shared only when injected by its owner."""

    def __init__(self) -> None:
        self.records: dict[str, str] = {}
        self.lock = asyncio.Lock()

    async def get(self, key: str) -> str | None:
        return self.records.get(key)

    async def cas(self, key: str, expected: str | None, value: str | None) -> bool:
        async with self.lock:
            if self.records.get(key) != expected:
                return False
            if value is None:
                self.records.pop(key, None)
            else:
                self.records[key] = value
            return True

    async def scan(self, cursor: str, count: int) -> tuple[str, list[str]]:
        keys = sorted(self.records)
        start = int(cursor)
        end = start + count
        return (str(end) if end < len(keys) else "0", keys[start:end])


class RedisStore:
    """A dedicated persistent, non-evicting Redis is required in production."""

    _CAS = """
local prior = redis.call('GET', KEYS[1])
if (ARGV[1] == '0' and prior) or (ARGV[1] == '1' and prior ~= ARGV[2]) then
    return 0
end
if ARGV[3] == '0' then redis.call('DEL', KEYS[1])
else redis.call('SET', KEYS[1], ARGV[4]) end
return 1
"""

    def __init__(self, url: str) -> None:
        self.client: Any = create_redis_client(url)

    async def check(self, *, durable: bool = False) -> None:
        try:
            await self.client.ping()
            if durable:
                configuration = await self.client.config_get(
                    "maxmemory-policy", "appendonly", "appendfsync"
                )
                if (
                    configuration.get("maxmemory-policy") != "noeviction"
                    or configuration.get("appendonly") != "yes"
                    or configuration.get("appendfsync") != "always"
                ):
                    raise ValueError
        except Exception:
            raise BYOKError("BYOK_STORAGE_UNAVAILABLE") from None

    async def get(self, key: str) -> str | None:
        try:
            value: str | None = await self.client.get(key)
            return value
        except Exception:
            raise BYOKError("BYOK_STORAGE_UNAVAILABLE") from None

    async def cas(self, key: str, expected: str | None, value: str | None) -> bool:
        try:
            return bool(
                await self.client.eval(
                    self._CAS,
                    1,
                    key,
                    "0" if expected is None else "1",
                    expected or "",
                    "0" if value is None else "1",
                    value or "",
                )
            )
        except Exception:
            # A lost reply may follow a committed write; caller must reconcile by read.
            raise BYOKError("BYOK_STORAGE_UNAVAILABLE") from None

    async def scan(self, cursor: str, count: int) -> tuple[str, list[str]]:
        try:
            next_cursor, keys = await self.client.scan(
                cursor=cursor, match="byok:*", count=count
            )
            return str(next_cursor), list(keys)
        except Exception:
            raise BYOKError("BYOK_STORAGE_UNAVAILABLE") from None
