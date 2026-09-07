"""Long-term persistent episodic and semantic memory for Agent platform.

Enforces strict tenant isolation and provides bounded scoped memory across runs.
"""

from __future__ import annotations

import time
import uuid
from typing import Any

from app.agent.memory.base import MemoryEntry, MemoryScope


class LongTermMemory:
    """Persistent, tenant-partitioned memory store."""

    def __init__(self, default_ttl_seconds: float = 86400.0 * 30) -> None:
        self.default_ttl_seconds = default_ttl_seconds
        # Mapping: tenant_id -> dict[entry_id, MemoryEntry]
        self._store: dict[str, dict[str, MemoryEntry]] = {}

    def store(
        self,
        tenant_id: str,
        key: str,
        value: Any,
        user_id: str | None = None,
        summary: str | None = None,
        ttl_seconds: float | None = None,
        metadata: dict[str, Any] | None = None,
    ) -> MemoryEntry:
        """Store long-term memory entry isolated by tenant."""
        now = time.time()
        ttl = ttl_seconds if ttl_seconds is not None else self.default_ttl_seconds
        entry_id = f"ltm_{uuid.uuid4().hex[:12]}"

        entry = MemoryEntry(
            entry_id=entry_id,
            tenant_id=tenant_id,
            user_id=user_id,
            scope=MemoryScope.LONG_TERM,
            key=key,
            value=value,
            summary=summary,
            created_at=now,
            expires_at=now + ttl if ttl > 0 else None,
            metadata=metadata or {},
        )

        if tenant_id not in self._store:
            self._store[tenant_id] = {}
        self._store[tenant_id][entry_id] = entry
        return entry

    def get(self, tenant_id: str, entry_id: str) -> MemoryEntry | None:
        """Retrieve a specific memory entry within tenant boundary."""
        tenant_entries = self._store.get(tenant_id, {})
        entry = tenant_entries.get(entry_id)
        if entry is None:
            return None

        # Check expiry
        if entry.expires_at and time.time() > entry.expires_at:
            del tenant_entries[entry_id]
            return None
        return entry

    def search(
        self,
        tenant_id: str,
        key_prefix: str | None = None,
        user_id: str | None = None,
        limit: int = 10,
    ) -> list[MemoryEntry]:
        """Search entries within tenant boundary with optional key prefix and user filter."""
        now = time.time()
        tenant_entries = self._store.get(tenant_id, {})
        results: list[MemoryEntry] = []
        expired_ids: list[str] = []

        for eid, entry in tenant_entries.items():
            if entry.expires_at and now > entry.expires_at:
                expired_ids.append(eid)
                continue

            if key_prefix and not entry.key.startswith(key_prefix):
                continue

            if user_id and entry.user_id and entry.user_id != user_id:
                continue

            results.append(entry)
            if len(results) >= limit:
                break

        # Cleanup expired
        for eid in expired_ids:
            tenant_entries.pop(eid, None)

        return results

    def delete(self, tenant_id: str, entry_id: str) -> bool:
        """Delete an entry, returning whether it existed."""
        tenant_entries = self._store.get(tenant_id, {})
        if entry_id in tenant_entries:
            del tenant_entries[entry_id]
            return True
        return False

    def clear_tenant(self, tenant_id: str) -> None:
        """Purge all entries for a given tenant."""
        self._store.pop(tenant_id, None)
