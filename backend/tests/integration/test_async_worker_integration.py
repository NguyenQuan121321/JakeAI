"""Comprehensive Asynchronous Worker & Task Queue Integration Test Suite (INT-023).

Verifies interactions between real JakeAI async worker components:
1. IngestionTaskManager + Redis task queue + bounded concurrency semaphore (max_concurrency <= 2).
2. IngestionWorker execution loop (claim -> process -> complete / fail).
3. Task state lifecycle progression: QUEUED -> PROCESSING -> COMPLETED / FAILED.
4. Multi-tenant isolation boundary across asynchronous task queues.

Mandatory failure cases tested across async worker subsystem:
- unavailable (Redis unavailable -> graceful transparent fallback to in-memory queue)
- timeout (Task processing exceeds timeout -> marked FAILED with timeout details)
- malformed response (Corrupted task state in queue -> handled fail-closed without crashing worker)
- connection failure (Redis connection reset during claim/complete -> caught and logged safely)
- partial failure (Pipeline failure midway through ingestion -> status=FAILED with recorded error)
- recovery (Worker recovers after transient failure, resumes processing remaining queue)
"""

from __future__ import annotations

import asyncio
import uuid
from typing import TYPE_CHECKING, Any
from unittest.mock import AsyncMock, patch

if TYPE_CHECKING:
    from collections.abc import AsyncGenerator

import pytest
import pytest_asyncio

from app.rag.ingestion import (
    DocumentIngestRequest,
)
from app.rag.tasks import (
    INGESTION_TASK_PREFIX,
    IngestionTaskManager,
    IngestionTaskStatus,
)
from app.worker import IngestionWorker


@pytest_asyncio.fixture
async def task_manager() -> AsyncGenerator[IngestionTaskManager, None]:
    """Isolated task manager instance with clean queue."""
    mgr = IngestionTaskManager(max_concurrency=2)
    await mgr.clear()
    try:
        yield mgr
    finally:
        await mgr.clear()


@pytest.mark.asyncio
class TestAsyncWorkerIntegration:
    """Integration tests verifying asynchronous worker and task queue orchestration."""

    async def test_async_worker_full_lifecycle_progression(
        self, task_manager: IngestionTaskManager
    ) -> None:
        """Integration 1: Enqueue -> claim -> worker process -> complete -> verify status."""
        worker = IngestionWorker(task_manager=task_manager)
        tenant_id = f"tenant-worker-{uuid.uuid4().hex[:8]}"

        req = DocumentIngestRequest(
            content="Q3 2024 Revenue: $150M. EBITDA: $40M.",
            source="Q3_Report.txt",
            metadata={"type": "earnings"},
        )

        # 1. Enqueue task
        enqueued = await task_manager.enqueue(req, tenant_id=tenant_id)
        assert enqueued.status == IngestionTaskStatus.QUEUED
        assert enqueued.tenant_id == tenant_id

        # 2. Worker claims and processes task
        processed = await worker.run_once()
        assert processed is True

        # 3. Verify task status progressed to COMPLETED
        final_task = await task_manager.get_task(enqueued.task_id, tenant_id=tenant_id)
        assert final_task is not None
        assert final_task.status == IngestionTaskStatus.COMPLETED
        assert final_task.completed_at is not None
        assert final_task.error is None
        assert final_task.result is not None
        assert final_task.result.indexed_chunks >= 1

    async def test_concurrency_bounded_worker_pool(
        self, task_manager: IngestionTaskManager
    ) -> None:
        """Integration 2: Semaphore strictly limits active concurrent worker jobs to max_concurrency."""
        worker = IngestionWorker(task_manager=task_manager)
        tenant_id = f"tenant-concur-{uuid.uuid4().hex[:8]}"

        # Enqueue 4 tasks
        task_ids: list[str] = []
        for i in range(4):
            req = DocumentIngestRequest(
                content=f"Document content chunk number {i}", source=f"doc_{i}.txt"
            )
            res = await task_manager.enqueue(req, tenant_id=tenant_id)
            task_ids.append(res.task_id)

        # Track concurrency
        active_concurrency = 0
        peak_concurrency = 0

        from app.rag.ingestion import default_ingestion_pipeline

        original_ingest = default_ingestion_pipeline.ingest

        async def _instrumented_ingest(*args: Any, **kwargs: Any) -> Any:
            nonlocal active_concurrency, peak_concurrency
            active_concurrency += 1
            peak_concurrency = max(peak_concurrency, active_concurrency)
            await asyncio.sleep(0.05)
            res = await original_ingest(*args, **kwargs)
            active_concurrency -= 1
            return res

        with patch.object(
            default_ingestion_pipeline, "ingest", side_effect=_instrumented_ingest
        ):
            # Run tasks concurrently
            tasks = [asyncio.create_task(worker.run_once()) for _ in range(4)]
            await asyncio.gather(*tasks)

        # Semaphore must ensure peak concurrent executions <= max_concurrency (2)
        assert peak_concurrency <= task_manager.max_concurrency

    async def test_worker_multi_tenant_isolation_boundary(
        self, task_manager: IngestionTaskManager
    ) -> None:
        """Integration 3: Worker respects multi-tenant boundaries; cross-tenant inspection is rejected."""
        tenant_a = f"tenant-a-{uuid.uuid4().hex[:8]}"
        tenant_b = f"tenant-b-{uuid.uuid4().hex[:8]}"

        req_a = DocumentIngestRequest(
            content="Secret Alpha financial records", source="Alpha.txt"
        )
        enqueued_a = await task_manager.enqueue(req_a, tenant_id=tenant_a)

        # Tenant A can access
        task_a = await task_manager.get_task(enqueued_a.task_id, tenant_id=tenant_a)
        assert task_a is not None
        assert task_a.tenant_id == tenant_a

        # Tenant B CANNOT access Tenant A's task (returns None)
        forbidden_task = await task_manager.get_task(
            enqueued_a.task_id, tenant_id=tenant_b
        )
        assert forbidden_task is None


@pytest.mark.asyncio
class TestAsyncWorkerMandatoryFailureCases:
    """Mandatory failure cases: unavailable, timeout, malformed, connection, partial, recovery."""

    async def test_failure_case_1_unavailable_redis(self) -> None:
        """Failure Case 1: Redis unavailable transparently falls back to in-memory queue."""
        mgr = IngestionTaskManager(max_concurrency=2)
        with patch.object(mgr, "_get_redis", return_value=None):
            req = DocumentIngestRequest(content="Offline content", source="Offline.txt")
            res = await mgr.enqueue(req, tenant_id="ten-offline")
            assert res.status == IngestionTaskStatus.QUEUED

            # Task remains retrievable in-memory
            in_mem = await mgr.get_task(res.task_id, tenant_id="ten-offline")
            assert in_mem is not None
            assert in_mem.task_id == res.task_id
            assert in_mem.content == "Offline content"
            assert in_mem.tenant_id == "ten-offline"

            claimed = await mgr.claim_next_task()
            assert claimed is not None
            assert claimed.task_id == res.task_id
            assert claimed.status == IngestionTaskStatus.PROCESSING

    async def test_failure_case_2_timeout(
        self, task_manager: IngestionTaskManager
    ) -> None:
        """Failure Case 2: Ingestion pipeline timeout marks task FAILED with error details."""
        worker = IngestionWorker(task_manager=task_manager)
        tenant_id = f"tenant-to-{uuid.uuid4().hex[:8]}"

        req = DocumentIngestRequest(content="Hanging document", source="Hanging.txt")
        enqueued = await task_manager.enqueue(req, tenant_id=tenant_id)
        task = await task_manager.claim_next_task()
        assert task is not None

        # Simulate timeout in default_ingestion_pipeline
        with patch(
            "app.worker.default_ingestion_pipeline.ingest",
            side_effect=TimeoutError(
                "Ingestion exceeded maximum allowed duration of 30.0s"
            ),
        ):
            await worker.process_task(task)

        # Task must be marked FAILED
        updated = await task_manager.get_task(enqueued.task_id, tenant_id=tenant_id)
        assert updated is not None
        assert updated.status == IngestionTaskStatus.FAILED
        assert updated.error is not None
        assert (
            "exceeded maximum allowed duration" in updated.error
            or "TimeoutError" in updated.error
        )

    async def test_failure_case_3_malformed_response_json(
        self, task_manager: IngestionTaskManager
    ) -> None:
        """Failure Case 3: Malformed JSON payload in Redis queue handled fail-closed."""
        task_id = "task-corrupt-json"
        redis = await task_manager._get_redis()

        if redis is not None:
            # Inject corrupt non-JSON string into Redis
            await redis.set(f"{INGESTION_TASK_PREFIX}{task_id}", "NOT_VALID_JSON{")
            # get_task should handle JSONDecodeError and return None or fall back safely
            res = await task_manager.get_task(task_id)
            assert res is None

    async def test_failure_case_4_connection_failure(
        self, task_manager: IngestionTaskManager
    ) -> None:
        """Failure Case 4: Redis connection failure during task operations caught cleanly."""
        req = DocumentIngestRequest(content="Connection drop test", source="Conn.txt")
        enqueued = await task_manager.enqueue(req, tenant_id="ten-conn")

        # Simulate Redis connection drop on _save_task and get_task
        task = await task_manager.get_task(enqueued.task_id)
        assert task is not None
        task.status = IngestionTaskStatus.PROCESSING

        # _save_task suppresses Redis exceptions and updates memory cache
        mock_redis = AsyncMock()
        mock_redis.set.side_effect = ConnectionResetError("Redis dropped during save")
        mock_redis.get.side_effect = ConnectionResetError("Redis dropped during get")
        with patch.object(task_manager, "_get_redis", return_value=mock_redis):
            # Should not raise
            await task_manager._save_task(task)

            # Verify task is still preserved in memory despite Redis failure
            saved = await task_manager.get_task(enqueued.task_id)
            assert saved is not None
            assert saved.task_id == enqueued.task_id
            assert saved.status == IngestionTaskStatus.PROCESSING

    async def test_failure_case_5_partial_failure_pipeline(
        self, task_manager: IngestionTaskManager
    ) -> None:
        """Failure Case 5: Partial failure midway through ingestion sets status FAILED."""
        worker = IngestionWorker(task_manager=task_manager)
        tenant_id = "tenant-part-fail"

        req = DocumentIngestRequest(content="Crashing document", source="Crash.pdf")
        enqueued = await task_manager.enqueue(req, tenant_id=tenant_id)
        task = await task_manager.claim_next_task()
        assert task is not None

        with patch(
            "app.worker.default_ingestion_pipeline.ingest",
            side_effect=ValueError("Unsupported PDF encoding structure"),
        ):
            await worker.process_task(task)

        failed_task = await task_manager.get_task(enqueued.task_id, tenant_id=tenant_id)
        assert failed_task is not None
        assert failed_task.status == IngestionTaskStatus.FAILED
        assert "Unsupported PDF encoding" in (failed_task.error or "")

    async def test_failure_case_6_recovery_subsequent_tasks(
        self, task_manager: IngestionTaskManager
    ) -> None:
        """Failure Case 6: Worker recovers from a failed task and successfully completes subsequent task."""
        worker = IngestionWorker(task_manager=task_manager)
        tenant_id = "tenant-rec"

        # Task 1 fails
        req1 = DocumentIngestRequest(content="Fail doc", source="Failing.txt")
        res1 = await task_manager.enqueue(req1, tenant_id=tenant_id)
        task1 = await task_manager.claim_next_task()
        assert task1 is not None

        with patch(
            "app.worker.default_ingestion_pipeline.ingest",
            side_effect=RuntimeError("Transient error"),
        ):
            await worker.process_task(task1)

        t1_state = await task_manager.get_task(res1.task_id, tenant_id=tenant_id)
        assert t1_state is not None
        assert t1_state.status == IngestionTaskStatus.FAILED

        # Task 2 succeeds (recovery)
        req2 = DocumentIngestRequest(content="Healthy doc", source="Healthy.txt")
        res2 = await task_manager.enqueue(req2, tenant_id=tenant_id)

        processed = await worker.run_once()
        assert processed is True

        t2_state = await task_manager.get_task(res2.task_id, tenant_id=tenant_id)
        assert t2_state is not None
        assert t2_state.status == IngestionTaskStatus.COMPLETED
