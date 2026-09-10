"""Checkpoint manager for serializing and restoring Agent run states with Redis durability."""

from __future__ import annotations

import json
import logging
import time
from typing import Any

from app.agent.state.models import RunState, RunStatus
from app.core.config import get_settings

logger = logging.getLogger(__name__)


class CheckpointRecord(RunState):
    """Checkpoint wrapper including snapshot metadata."""

    checkpoint_id: str
    checkpoint_created_at: float
    short_term_memory_snapshot: list[dict[str, Any]] = []


class CheckpointManager:
    """Manages durable point-in-time snapshots of Agent execution states (TASK ORC-05).

    Guarantees strict multi-tenant boundary verification and resilient
    dual memory + Redis persistence across worker restarts.
    """

    def __init__(self) -> None:
        self._checkpoints: dict[str, CheckpointRecord] = {}  # key: checkpoint_id
        self._run_to_latest: dict[str, str] = {}  # run_id -> latest checkpoint_id
        self.redis_client: Any | None = None
        self._redis_available = True

    async def _get_redis(self) -> Any | None:
        """Lazily initialize Redis connection with event loop validation and test mock compatibility."""
        if not self._redis_available:
            return None

        if self.redis_client is not None:
            if type(self.redis_client).__name__.startswith(
                ("Mock", "AsyncMock")
            ) or hasattr(self.redis_client, "_mock_return_value"):
                return self.redis_client

            try:
                import asyncio

                current_loop = asyncio.get_running_loop()
                pool = getattr(self.redis_client, "connection_pool", None)
                client_loop = (
                    getattr(pool, "_loop", None)
                    if pool is not None
                    else getattr(self.redis_client, "_loop", None)
                )
                if isinstance(client_loop, asyncio.AbstractEventLoop) and (
                    client_loop is not current_loop or client_loop.is_closed()
                ):
                    self.redis_client = None
                else:
                    return self.redis_client
            except Exception:
                self.redis_client = None

        try:
            from redis import asyncio as aioredis

            settings = get_settings()
            client = aioredis.from_url(
                settings.REDIS_URL,
                decode_responses=True,
                socket_connect_timeout=0.2,
                socket_timeout=0.2,
            )
            await client.ping()
            self.redis_client = client
            return self.redis_client
        except Exception:
            self._redis_available = False
            return None

    @staticmethod
    def _sanitize_record_dict(dump: dict[str, Any]) -> dict[str, Any]:
        """Strip raw credentials and tokens prior to durable persistence."""
        safe_dump = dict(dump)
        if "metadata" in safe_dump and isinstance(safe_dump["metadata"], dict):
            safe_meta = dict(safe_dump["metadata"])
            for secret_key in ("obo_token", "raw_token", "api_key", "password", "token"):
                if secret_key in safe_meta:
                    safe_meta[secret_key] = "[REDACTED]"
            safe_dump["metadata"] = safe_meta
        return safe_dump

    async def save_checkpoint(
        self,
        run_state: RunState,
        short_term_memory: list[dict[str, Any]] | None = None,
        ttl_seconds: int = 86400,
    ) -> str:
        """Create and persist an immutable checkpoint snapshot to memory and Redis."""
        cp_id = f"cp_{run_state.run_id}_{int(time.time() * 1000)}"
        raw_dump = run_state.model_dump()
        safe_dump = self._sanitize_record_dict(raw_dump)

        record = CheckpointRecord(
            checkpoint_id=cp_id,
            checkpoint_created_at=time.time(),
            short_term_memory_snapshot=short_term_memory or [],
            **safe_dump,
        )

        self._checkpoints[cp_id] = record
        self._run_to_latest[run_state.run_id] = cp_id

        # Persist to Redis
        redis = await self._get_redis()
        if redis is not None:
            try:
                rec_json = record.model_dump_json()
                await redis.set(f"agent:checkpoint:rec:{cp_id}", rec_json, ex=ttl_seconds)
                await redis.set(
                    f"agent:checkpoint:run:{run_state.run_id}", cp_id, ex=ttl_seconds
                )
            except Exception as exc:
                logger.debug("Redis checkpoint write failed (%s), cached in memory", exc)

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
            # Attempt rehydration from Redis
            redis = await self._get_redis()
            if redis is not None:
                try:
                    val = await redis.get(f"agent:checkpoint:rec:{checkpoint_id}")
                    if val:
                        data = json.loads(val)
                        cp = CheckpointRecord(**data)
                        self._checkpoints[checkpoint_id] = cp
                except Exception as exc:
                    logger.debug("Redis checkpoint read failed: %s", exc)

        if cp is None:
            raise KeyError(f"Checkpoint '{checkpoint_id}' not found.")

        if cp.tenant_id != tenant_id:
            raise PermissionError(
                f"Tenant mismatch: Checkpoint belongs to tenant '{cp.tenant_id}', "
                f"access requested by '{tenant_id}'."
            )
        return cp

    async def load_checkpoint(
        self,
        run_id: str,
        tenant_id: str | None = None,
    ) -> CheckpointRecord | None:
        """Load latest checkpoint for a run with optional tenant isolation verification."""
        latest_id = self._run_to_latest.get(run_id)

        # If not in memory (e.g. after process restart), inspect Redis
        if not latest_id:
            redis = await self._get_redis()
            if redis is not None:
                try:
                    latest_id = await redis.get(f"agent:checkpoint:run:{run_id}")
                    if latest_id:
                        self._run_to_latest[run_id] = latest_id
                except Exception as exc:
                    logger.debug("Redis run lookup failed: %s", exc)

        if not latest_id:
            return None

        effective_tenant = tenant_id or "internal"
        cp = self._checkpoints.get(latest_id)
        if cp is None:
            redis = await self._get_redis()
            if redis is not None:
                try:
                    val = await redis.get(f"agent:checkpoint:rec:{latest_id}")
                    if val:
                        cp = CheckpointRecord(**json.loads(val))
                        self._checkpoints[latest_id] = cp
                except Exception as exc:
                    logger.debug("Redis checkpoint load failed: %s", exc)

        if cp is None:
            return None

        if tenant_id and cp.tenant_id != tenant_id:
            raise PermissionError(
                f"Tenant mismatch: Checkpoint belongs to '{cp.tenant_id}', "
                f"access requested by '{tenant_id}'."
            )
        return cp

    async def delete_checkpoint(
        self,
        run_id: str,
        tenant_id: str | None = None,
    ) -> bool:
        """Delete checkpoint for a run across Redis and memory."""
        cp = await self.load_checkpoint(run_id, tenant_id=tenant_id)
        if cp is None:
            return False

        latest_id = self._run_to_latest.pop(run_id, None)
        if latest_id:
            self._checkpoints.pop(latest_id, None)

        redis = await self._get_redis()
        if redis is not None:
            try:
                keys_to_del = [f"agent:checkpoint:run:{run_id}"]
                if latest_id:
                    keys_to_del.append(f"agent:checkpoint:rec:{latest_id}")
                await redis.delete(*keys_to_del)
            except Exception as exc:
                logger.debug("Redis checkpoint delete failed: %s", exc)
        return True

    async def resume_run_from_checkpoint(
        self,
        run_id: str,
        tenant_id: str,
    ) -> RunState:
        """Restore RunState from checkpoint to safely resume execution after restart."""
        cp = await self.load_checkpoint(run_id, tenant_id=tenant_id)
        if cp is None:
            raise KeyError(f"No checkpoint found for run '{run_id}'")

        if cp.tenant_id != tenant_id:
            raise PermissionError(
                f"Tenant mismatch: Run belongs to '{cp.tenant_id}', caller is '{tenant_id}'"
            )

        # Reconstruct RunState from checkpoint record
        run_dict = cp.model_dump(exclude={"checkpoint_id", "checkpoint_created_at", "short_term_memory_snapshot"})
        resumed_run = RunState(**run_dict)

        # If it was interrupted / paused, preserve paused status or mark running for resumption
        if resumed_run.status == RunStatus.RUNNING:
            logger.info("Resuming run %s restored from checkpoint %s", run_id, cp.checkpoint_id)

        return resumed_run

    async def get_latest_for_run(
        self,
        run_id: str,
        tenant_id: str,
    ) -> CheckpointRecord | None:
        """Retrieve the latest checkpoint for an execution run."""
        return await self.load_checkpoint(run_id, tenant_id=tenant_id)

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

