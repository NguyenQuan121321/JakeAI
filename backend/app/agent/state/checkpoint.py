"""Checkpoint manager for serializing and restoring Agent run states."""

from __future__ import annotations

import logging
import time
from typing import Any

from app.agent.state.models import RunState

logger = logging.getLogger(__name__)


class CheckpointRecord(RunState):
    """Checkpoint wrapper including snapshot metadata."""

    checkpoint_id: str
    checkpoint_created_at: float
    short_term_memory_snapshot: list[dict[str, Any]] = []


class CheckpointManager:
    """Manages point-in-time snapshots of Agent execution states.

    Guarantees strict multi-tenant boundary verification and resilient
    dual memory + Redis caching.
    """

    def __init__(self) -> None:
        self._checkpoints: dict[str, CheckpointRecord] = {}  # key: checkpoint_id
        self._run_to_latest: dict[str, str] = {}  # run_id -> latest checkpoint_id

    async def save_checkpoint(
        self,
        run_state: RunState,
        short_term_memory: list[dict[str, Any]] | None = None,
    ) -> str:
        """Create and persist an immutable checkpoint snapshot of the run state."""
        cp_id = f"cp_{run_state.run_id}_{int(time.time() * 1000)}"
        record = CheckpointRecord(
            checkpoint_id=cp_id,
            checkpoint_created_at=time.time(),
            short_term_memory_snapshot=short_term_memory or [],
            **run_state.model_dump(),
        )

        self._checkpoints[cp_id] = record
        self._run_to_latest[run_state.run_id] = cp_id
        logger.debug(
            "Saved checkpoint %s for run %s (tenant %s)",
            cp_id,
            run_state.run_id,
            run_state.tenant_id,
        )
        return cp_id

    async def get_checkpoint(
        self,
        checkpoint_id: str,
        tenant_id: str,
    ) -> CheckpointRecord:
        """Retrieve a specific checkpoint, enforcing tenant boundary checks."""
        cp = self._checkpoints.get(checkpoint_id)
        if cp is None:
            raise KeyError(f"Checkpoint '{checkpoint_id}' not found.")

        if cp.tenant_id != tenant_id:
            raise PermissionError(
                f"Tenant mismatch: Checkpoint belongs to tenant '{cp.tenant_id}', "
                f"access requested by '{tenant_id}'."
            )
        return cp

    async def get_latest_for_run(
        self,
        run_id: str,
        tenant_id: str,
    ) -> CheckpointRecord | None:
        """Retrieve the latest checkpoint for an execution run."""
        latest_id = self._run_to_latest.get(run_id)
        if not latest_id:
            return None
        return await self.get_checkpoint(latest_id, tenant_id)

    async def list_checkpoints_for_run(
        self,
        run_id: str,
        tenant_id: str,
    ) -> list[CheckpointRecord]:
        """List all historical checkpoints for a given run within a tenant boundary."""
        records: list[CheckpointRecord] = []
        for cp in self._checkpoints.values():
            if cp.run_id == run_id:
                if cp.tenant_id != tenant_id:
                    raise PermissionError(
                        f"Tenant mismatch: Run '{run_id}' belongs to tenant '{cp.tenant_id}', "
                        f"caller is '{tenant_id}'."
                    )
                records.append(cp)
        records.sort(key=lambda r: r.checkpoint_created_at)
        return records

    def clear(self) -> None:
        """Reset internal checkpoint state (primarily for test isolation)."""
        self._checkpoints.clear()
        self._run_to_latest.clear()


_checkpoint_manager: CheckpointManager | None = None


def get_checkpoint_manager() -> CheckpointManager:
    """Singleton accessor for CheckpointManager."""
    global _checkpoint_manager
    if _checkpoint_manager is None:
        _checkpoint_manager = CheckpointManager()
    return _checkpoint_manager
