"""Unified Agent Memory Manager coordinating short-term and long-term memory."""

from __future__ import annotations

import logging
from typing import TYPE_CHECKING, Any

from app.agent.memory.long_term import LongTermMemory
from app.agent.memory.short_term import ShortTermMemory

if TYPE_CHECKING:
    from app.agent.memory.base import MemoryEntry

logger = logging.getLogger(__name__)


class AgentMemoryManager:
    """Coordinates runtime scratchpad and persistent multi-tenant memory."""

    def __init__(self) -> None:
        self.long_term = LongTermMemory()
        # Active short term memories keyed by run_id
        self._active_runs: dict[str, ShortTermMemory] = {}

    def get_run_memory(self, run_id: str, max_entries: int = 50) -> ShortTermMemory:
        """Get or initialize short-term memory buffer for a run."""
        if run_id not in self._active_runs:
            self._active_runs[run_id] = ShortTermMemory(max_entries=max_entries)
        return self._active_runs[run_id]

    def remove_run_memory(self, run_id: str) -> None:
        """Clean up ephemeral memory after run completion."""
        self._active_runs.pop(run_id, None)

    def remember_episodic(
        self,
        tenant_id: str,
        key: str,
        value: Any,
        user_id: str | None = None,
        summary: str | None = None,
    ) -> MemoryEntry:
        """Persist knowledge to long-term memory with strict tenant boundary."""
        return self.long_term.store(
            tenant_id=tenant_id,
            key=key,
            value=value,
            user_id=user_id,
            summary=summary,
        )

    def recall_relevant(
        self,
        tenant_id: str,
        query_key: str | None = None,
        user_id: str | None = None,
        limit: int = 5,
    ) -> list[MemoryEntry]:
        """Retrieve relevant tenant-scoped facts or observations."""
        return self.long_term.search(
            tenant_id=tenant_id,
            key_prefix=query_key,
            user_id=user_id,
            limit=limit,
        )


_memory_manager: AgentMemoryManager | None = None


def get_memory_manager() -> AgentMemoryManager:
    """Singleton accessor for AgentMemoryManager."""
    global _memory_manager
    if _memory_manager is None:
        _memory_manager = AgentMemoryManager()
    return _memory_manager
