"""Asynchronous Bounded Task Queue for RAG Document Ingestion.

Implements Directive 11: Bulk Ingestion Bounded Queue Enforcement:
- Asynchronous task queuing backed by Redis with in-memory fallback.
- Strict bounded concurrency (max_concurrency <= 2) to lock peak RAM below 300MB VPS ceiling.
- Transparent task state lifecycle: QUEUED -> PROCESSING -> COMPLETED / FAILED.
"""

from __future__ import annotations

import asyncio
import contextlib
import logging
import time
import uuid
from enum import StrEnum
from typing import Any

from pydantic import BaseModel, Field

from app.core.config import get_settings
from app.rag.ingestion import (  # noqa: TC001
    DocumentIngestRequest,
    DocumentIngestResponse,
)

logger = logging.getLogger(__name__)

INGESTION_QUEUE_KEY = "rag:ingest:queue"
INGESTION_TASK_PREFIX = "rag:ingest:task:"
DEFAULT_TASK_TTL_SECONDS = 86400  # 24 hours
DEFAULT_MAX_CONCURRENCY = 2


class IngestionTaskStatus(StrEnum):
    """Lifecycle status of an asynchronous document ingestion job."""

    QUEUED = "queued"
    PROCESSING = "processing"
    COMPLETED = "completed"
    FAILED = "failed"


class IngestionTaskState(BaseModel):
    """Full persistent state of an ingestion task."""

    task_id: str
    tenant_id: str
    status: IngestionTaskStatus
    source: str
    content: str
    metadata: dict[str, Any] = Field(default_factory=dict)
    chunk_size: int = 500
    chunk_overlap: int = 50
    created_at: float = Field(default_factory=time.time)
    started_at: float | None = None
    completed_at: float | None = None
    error: str | None = None
    result: DocumentIngestResponse | None = None


class IngestionTaskResponse(BaseModel):
    """Client-facing response for enqueued ingestion job."""

    task_id: str
    tenant_id: str
    status: IngestionTaskStatus
    source: str
    created_at: float
    poll_url: str
    message: str = "Document ingestion job accepted for asynchronous processing"


class IngestionTaskManager:
    """Asynchronous bounded queue manager with Redis and in-memory fallback."""

    def __init__(self, max_concurrency: int = DEFAULT_MAX_CONCURRENCY) -> None:
        self.max_concurrency = max_concurrency
        self.semaphore = asyncio.Semaphore(max_concurrency)
        self._memory_tasks: dict[str, IngestionTaskState] = {}
        self._memory_queue: list[str] = []
        self.redis_client: Any | None = None
        self._redis_available = True

    async def _get_redis(self) -> Any | None:
        """Lazily initialize Redis connection with fast ping check."""
        if self.redis_client is not None:
            return self.redis_client
        if not self._redis_available:
            return None
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

    async def enqueue(
        self,
        request: DocumentIngestRequest,
        tenant_id: str,
    ) -> IngestionTaskResponse:
        """Enqueue document for asynchronous ingestion."""
        task_id = f"task-ingest-{uuid.uuid4().hex[:12]}"
        state = IngestionTaskState(
            task_id=task_id,
            tenant_id=tenant_id,
            status=IngestionTaskStatus.QUEUED,
            source=request.source,
            content=request.content,
            metadata=request.metadata,
            chunk_size=request.chunk_size,
            chunk_overlap=request.chunk_overlap,
        )

        redis = await self._get_redis()
        if redis is not None:
            try:
                task_key = f"{INGESTION_TASK_PREFIX}{task_id}"
                await redis.set(
                    task_key, state.model_dump_json(), ex=DEFAULT_TASK_TTL_SECONDS
                )
                await redis.rpush(INGESTION_QUEUE_KEY, task_id)
            except Exception as exc:
                logger.debug("Redis enqueue failed (%s), falling back to memory", exc)
                self._memory_tasks[task_id] = state
                self._memory_queue.append(task_id)
        else:
            self._memory_tasks[task_id] = state
            self._memory_queue.append(task_id)

        return IngestionTaskResponse(
            task_id=task_id,
            tenant_id=tenant_id,
            status=IngestionTaskStatus.QUEUED,
            source=request.source,
            created_at=state.created_at,
            poll_url=f"/api/v1/rag/tasks/{task_id}",
        )

    async def get_task(
        self, task_id: str, tenant_id: str | None = None
    ) -> IngestionTaskState | None:
        """Retrieve task state, enforcing tenant isolation if tenant_id is supplied."""
        redis = await self._get_redis()
        state: IngestionTaskState | None = None
        if redis is not None:
            try:
                raw = await redis.get(f"{INGESTION_TASK_PREFIX}{task_id}")
                if raw:
                    state = IngestionTaskState.model_validate_json(raw)
            except Exception as exc:
                logger.debug("Redis get_task failed (%s)", exc)

        if state is None:
            state = self._memory_tasks.get(task_id)

        if state and tenant_id and state.tenant_id != tenant_id:
            return None

        return state

    async def claim_next_task(self) -> IngestionTaskState | None:
        """Pop next task ID from queue and set status to PROCESSING."""
        redis = await self._get_redis()
        task_id: str | None = None
        if redis is not None:
            try:
                task_id = await redis.lpop(INGESTION_QUEUE_KEY)
            except Exception as exc:
                logger.debug("Redis lpop failed (%s)", exc)

        if not task_id and self._memory_queue:
            task_id = self._memory_queue.pop(0)

        if not task_id:
            return None

        task = await self.get_task(task_id)
        if task is None:
            return None

        task.status = IngestionTaskStatus.PROCESSING
        task.started_at = time.time()
        await self._save_task(task)
        return task

    async def complete_task(self, task_id: str, result: DocumentIngestResponse) -> None:
        """Mark task as successfully completed."""
        task = await self.get_task(task_id)
        if task is None:
            return
        task.status = IngestionTaskStatus.COMPLETED
        task.completed_at = time.time()
        task.result = result
        await self._save_task(task)

    async def fail_task(self, task_id: str, error_message: str) -> None:
        """Mark task as failed with error details."""
        task = await self.get_task(task_id)
        if task is None:
            return
        task.status = IngestionTaskStatus.FAILED
        task.completed_at = time.time()
        task.error = error_message
        await self._save_task(task)

    async def _save_task(self, task: IngestionTaskState) -> None:
        """Persist updated task state."""
        redis = await self._get_redis()
        if redis is not None:
            with contextlib.suppress(Exception):
                await redis.set(
                    f"{INGESTION_TASK_PREFIX}{task.task_id}",
                    task.model_dump_json(),
                    ex=DEFAULT_TASK_TTL_SECONDS,
                )
        self._memory_tasks[task.task_id] = task


_task_manager: IngestionTaskManager | None = None


def get_task_manager() -> IngestionTaskManager:
    """Singleton getter for IngestionTaskManager."""
    global _task_manager
    if _task_manager is None:
        _task_manager = IngestionTaskManager()
    return _task_manager
