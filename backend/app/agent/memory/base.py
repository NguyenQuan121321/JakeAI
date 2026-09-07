"""Base memory interfaces and models for the Agent platform."""

from __future__ import annotations

import time
from enum import StrEnum
from typing import Any

from pydantic import BaseModel, Field


class MemoryScope(StrEnum):
    """Scope domain of stored memory."""

    SHORT_TERM = "short_term"  # Ephemeral, tied to current run / conversation loop
    SESSION = "session"        # Bound to current task session
    LONG_TERM = "long_term"    # Persistent across tasks, scoped by tenant/user


class MemoryEntry(BaseModel):
    """Normalized memory record."""

    entry_id: str = Field(..., description="Unique entry ID")
    tenant_id: str = Field(..., description="Tenant isolation boundary")
    user_id: str | None = Field(default=None, description="Optional user scope")
    scope: MemoryScope = Field(default=MemoryScope.SHORT_TERM)
    key: str = Field(..., description="Lookup or categorization key")
    value: Any = Field(..., description="Stored data payload")
    summary: str | None = Field(default=None, description="Human/LLM readable textual summary")
    created_at: float = Field(default_factory=time.time)
    expires_at: float | None = Field(default=None, description="Optional TTL expiration timestamp")
    metadata: dict[str, Any] = Field(default_factory=dict)
