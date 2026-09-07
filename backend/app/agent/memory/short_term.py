"""Short-term runtime memory for Agent execution runs.

Maintains bounded in-memory scratchpad and conversation history with FIFO
eviction to prevent unbounded memory growth during iterative loops.
"""

from __future__ import annotations

import time
import uuid
from typing import TYPE_CHECKING, Any

from app.agent.memory.base import MemoryEntry, MemoryScope

if TYPE_CHECKING:
    from app.agent.backends.base import AgentMessage


class ShortTermMemory:
    """Bounded, transient in-run memory buffer."""

    def __init__(self, max_entries: int = 50) -> None:
        self.max_entries = max_entries
        self._entries: list[MemoryEntry] = []
        self._messages: list[AgentMessage] = []

    def add_message(self, message: AgentMessage) -> None:
        """Append a conversation message, evicting oldest if capacity exceeded."""
        self._messages.append(message)
        if len(self._messages) > self.max_entries:
            # Retain system messages if present, evict earliest user/assistant message
            if self._messages[0].role == "system" and len(self._messages) > 2:
                self._messages.pop(1)
            else:
                self._messages.pop(0)

    def get_messages(self) -> list[AgentMessage]:
        """Retrieve active message history."""
        return list(self._messages)

    def store(
        self,
        key: str,
        value: Any,
        tenant_id: str = "default",
        user_id: str | None = None,
        summary: str | None = None,
    ) -> MemoryEntry:
        """Record an arbitrary variable or observation in short-term memory."""
        entry = MemoryEntry(
            entry_id=f"stm_{uuid.uuid4().hex[:12]}",
            tenant_id=tenant_id,
            user_id=user_id,
            scope=MemoryScope.SHORT_TERM,
            key=key,
            value=value,
            summary=summary,
            created_at=time.time(),
        )
        self._entries.append(entry)
        if len(self._entries) > self.max_entries:
            self._entries.pop(0)
        return entry

    def get(self, key: str) -> Any | None:
        """Retrieve most recent value for a key."""
        for entry in reversed(self._entries):
            if entry.key == key:
                return entry.value
        return None

    def list_entries(self) -> list[MemoryEntry]:
        """Return all active short-term memory entries."""
        return list(self._entries)

    def snapshot(self) -> list[dict[str, Any]]:
        """Export serialized representation for checkpointing."""
        return [e.model_dump() for e in self._entries]

    def restore(self, snapshot_data: list[dict[str, Any]]) -> None:
        """Restore entries from a checkpoint snapshot."""
        self._entries = [MemoryEntry.model_validate(item) for item in snapshot_data]

    def clear(self) -> None:
        """Flush short-term memory."""
        self._entries.clear()
        self._messages.clear()
