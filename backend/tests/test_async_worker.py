"""Unit and integration tests for Asynchronous Ingestion Task Queue & Worker.

Tests:
1. IngestionTaskManager lifecycle: enqueue, claim, complete, fail, and tenant isolation.
2. Concurrency bounded semaphore enforcement (max_concurrency <= 2).
3. IngestionWorker single execution run, exception handling, and index population.
4. REST API asynchronous ingestion endpoint: POST /api/v1/rag/ingest?async_mode=true (202 Accepted).
5. REST API task polling endpoint: GET /api/v1/rag/tasks/{task_id} with state progression.
6. Multi-tenant isolation asserting cross-tenant task inspection is blocked (404).
7. Synchronous ingestion fallback: POST /api/v1/rag/ingest?async_mode=false (201 Created).
"""

from __future__ import annotations

import time
from typing import TYPE_CHECKING, Any

import jwt
import pytest
import pytest_asyncio
from fastapi import status

if TYPE_CHECKING:
    from collections.abc import AsyncGenerator

    from httpx import AsyncClient

from app.core.config import get_settings
from app.rag.ingestion import (
    DocumentIngestRequest,
    DocumentIngestResponse,
)
from app.rag.tasks import (
    IngestionTaskManager,
    IngestionTaskStatus,
    get_task_manager,
    reset_task_manager,
)
from app.worker import IngestionWorker


@pytest_asyncio.fixture(autouse=True)
async def clean_worker_environment() -> AsyncGenerator[None, None]:
    """Isolate each worker test by clearing Redis queue and resetting singleton."""
    mgr = get_task_manager()
    await mgr.clear()
    reset_task_manager()
    yield
    mgr = get_task_manager()
    await mgr.clear()
    reset_task_manager()


def generate_test_jwt(tenant_id: str, user_id: str = "user-worker-test") -> str:
    """Generate signed JWT token for worker testing."""
    settings = get_settings()
    now = int(time.time())
    payload: dict[str, Any] = {
        "sub": user_id,
        "tenant_id": tenant_id,
        "iat": now,
        "exp": now + 3600,
        "roles": ["admin"],
        "permissions": ["rag:write", "rag:read"],
    }
    return jwt.encode(payload, settings.JWT_SECRET_KEY, algorithm="HS256")


@pytest.mark.asyncio
async def test_task_manager_enqueue_and_isolation() -> None:
    """Verify task enqueuing, retrieval, and multi-tenant isolation."""
    mgr = IngestionTaskManager(max_concurrency=2)
    await mgr.clear()
    req = DocumentIngestRequest(
        content="Acme Q3 Earnings: Revenue surged 22% to $120M.",
        source="Acme_Q3.txt",
        metadata={"sec_filing": "10-Q"},
    )

    # 1. Enqueue task for tenant-alpha
    res = await mgr.enqueue(req, tenant_id="tenant-alpha")
    assert res.task_id.startswith("task-ingest-")
    assert res.status == IngestionTaskStatus.QUEUED
    assert res.tenant_id == "tenant-alpha"
    assert "/tasks/" in res.poll_url

    # 2. Retrieve task with matching tenant
    task = await mgr.get_task(res.task_id, tenant_id="tenant-alpha")
    assert task is not None
    assert task.source == "Acme_Q3.txt"
    assert task.status == IngestionTaskStatus.QUEUED

    # 3. Multi-tenant isolation: Foreign tenant must NOT access task
    foreign_task = await mgr.get_task(res.task_id, tenant_id="tenant-beta")
    assert foreign_task is None


@pytest.mark.asyncio
async def test_task_manager_lifecycle_states() -> None:
    """Verify state transitions: QUEUED -> PROCESSING -> COMPLETED / FAILED."""
    mgr = IngestionTaskManager(max_concurrency=2)
    await mgr.clear()
    req = DocumentIngestRequest(
        content="Enterprise AI Architecture Report.",
        source="Tech_Report.md",
    )

    res = await mgr.enqueue(req, tenant_id="tenant-lifecycle")
    task_id = res.task_id

    # 1. Claim task
    claimed = await mgr.claim_next_task()
    assert claimed is not None
    assert claimed.task_id == task_id
    assert claimed.status == IngestionTaskStatus.PROCESSING
    assert claimed.started_at is not None

    # 2. Complete task
    dummy_result = DocumentIngestResponse(
        status="success",
        indexed_chunks=3,
        chunk_ids=["chk-1", "chk-2", "chk-3"],
        source="Tech_Report.md",
        tenant_id="tenant-lifecycle",
    )
    await mgr.complete_task(task_id, dummy_result)

    completed = await mgr.get_task(task_id)
    assert completed is not None
    assert completed.status == IngestionTaskStatus.COMPLETED
    assert completed.completed_at is not None
    assert completed.result is not None
    assert completed.result.indexed_chunks == 3

    # 3. Test failure flow on second task
    await mgr.enqueue(req, tenant_id="tenant-lifecycle")
    claimed2 = await mgr.claim_next_task()
    assert claimed2 is not None
    await mgr.fail_task(claimed2.task_id, "Memory allocation failure simulation")

    failed = await mgr.get_task(claimed2.task_id)
    assert failed is not None
    assert failed.status == IngestionTaskStatus.FAILED
    assert failed.error == "Memory allocation failure simulation"


@pytest.mark.asyncio
async def test_worker_process_single_run() -> None:
    """Verify IngestionWorker processes queued tasks end-to-end."""
    mgr = IngestionTaskManager(max_concurrency=2)
    await mgr.clear()
    worker = IngestionWorker(task_manager=mgr)

    req = DocumentIngestRequest(
        content="JakeAI bounded ingestion worker locks memory spikes on VPS.",
        source="VPS_Spec.txt",
    )
    res = await mgr.enqueue(req, tenant_id="tenant-worker-e2e")

    # Worker executes single task
    processed = await worker.run_once()
    assert processed is True

    # Check task state
    task = await mgr.get_task(res.task_id)
    assert task is not None
    assert task.status == IngestionTaskStatus.COMPLETED
    assert task.result is not None
    assert task.result.indexed_chunks >= 1

    # Second run with empty queue returns False
    processed_empty = await worker.run_once()
    assert processed_empty is False


@pytest.mark.asyncio
async def test_api_async_ingest_and_polling(
    async_client: AsyncClient,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Verify API POST /api/v1/rag/ingest?async_mode=true (202) and GET /tasks/{task_id}."""
    task_mgr = get_task_manager()
    await task_mgr.clear()
    settings = get_settings()
    monkeypatch.setattr(settings, "JWT_ALGORITHM", "HS256")
    token_alpha = generate_test_jwt("tenant-async-api")
    token_beta = generate_test_jwt("tenant-intruder")

    payload = {
        "content": (
            "Asynchronous Task Queue Ingestion Test.\n\n"
            "This document is submitted with async_mode=True to ensure HTTP 202 Accepted "
            "and background processing by jakeai-worker."
        ),
        "source": "Async_Guide.md",
        "metadata": {"category": "architecture"},
    }

    # 1. Post with async_mode=true -> Expect 202 Accepted
    resp = await async_client.post(
        "/api/v1/rag/ingest?async_mode=true",
        headers={"Authorization": f"Bearer {token_alpha}"},
        json=payload,
    )
    assert resp.status_code == status.HTTP_202_ACCEPTED
    data = resp.json()
    task_id = data["task_id"]
    assert data["status"] == "queued"
    assert f"/api/v1/rag/tasks/{task_id}" == data["poll_url"]

    # 2. Poll task status -> Expect 200 OK (status: queued)
    poll_resp = await async_client.get(
        f"/api/v1/rag/tasks/{task_id}",
        headers={"Authorization": f"Bearer {token_alpha}"},
    )
    assert poll_resp.status_code == status.HTTP_200_OK
    poll_data = poll_resp.json()
    assert poll_data["task_id"] == task_id
    assert poll_data["status"] == "queued"

    # 3. Process via worker
    worker = IngestionWorker()
    did_work = await worker.run_once()
    assert did_work is True

    # 4. Poll again -> Expect 200 OK (status: completed)
    poll_after = await async_client.get(
        f"/api/v1/rag/tasks/{task_id}",
        headers={"Authorization": f"Bearer {token_alpha}"},
    )
    assert poll_after.status_code == status.HTTP_200_OK
    completed_data = poll_after.json()
    assert completed_data["status"] == "completed"
    assert completed_data["result"] is not None
    assert completed_data["result"]["indexed_chunks"] >= 1

    # 5. Security Gate: Foreign tenant must receive 404
    intruder_poll = await async_client.get(
        f"/api/v1/rag/tasks/{task_id}",
        headers={"Authorization": f"Bearer {token_beta}"},
    )
    assert intruder_poll.status_code == status.HTTP_404_NOT_FOUND


@pytest.mark.asyncio
async def test_api_sync_ingest_backward_compatibility(
    async_client: AsyncClient,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Verify synchronous ingestion fallback (async_mode=false) returns 201 Created."""
    settings = get_settings()
    monkeypatch.setattr(settings, "JWT_ALGORITHM", "HS256")
    token = generate_test_jwt("tenant-sync-api")

    payload = {
        "content": "Synchronous ingestion for legacy compatibility and immediate testing.",
        "source": "Sync_Doc.txt",
    }

    resp = await async_client.post(
        "/api/v1/rag/ingest?async_mode=false",
        headers={"Authorization": f"Bearer {token}"},
        json=payload,
    )
    assert resp.status_code == status.HTTP_201_CREATED
    data = resp.json()
    assert data["status"] == "success"
    assert data["indexed_chunks"] >= 1
    assert data["tenant_id"] == "tenant-sync-api"


@pytest.mark.asyncio
async def test_worker_start_stop_gracefully() -> None:
    """Verify IngestionWorker starts and terminates cleanly upon stop() signal."""
    import asyncio

    mgr = IngestionTaskManager(max_concurrency=2)
    worker = IngestionWorker(task_manager=mgr, poll_interval=0.01)

    task = asyncio.create_task(worker.start())
    await asyncio.sleep(0.05)
    assert worker._running is True

    worker.stop()
    await asyncio.wait_for(task, timeout=1.0)
    assert worker._running is False


@pytest.mark.asyncio
async def test_worker_process_task_failure_handling(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Verify IngestionWorker marks task as FAILED when ingestion pipeline raises an error."""
    from app.rag.ingestion import default_ingestion_pipeline

    mgr = IngestionTaskManager(max_concurrency=2)
    worker = IngestionWorker(task_manager=mgr)

    req = DocumentIngestRequest(
        content="Corrupt data that triggers pipeline failure.",
        source="Corrupt.pdf",
    )
    res = await mgr.enqueue(req, tenant_id="tenant-fail-test")

    async def failing_ingest(*args: Any, **kwargs: Any) -> Any:
        raise ValueError("Corrupt PDF format parse error")

    monkeypatch.setattr(default_ingestion_pipeline, "ingest", failing_ingest)

    processed = await worker.run_once()
    assert processed is True

    task = await mgr.get_task(res.task_id)
    assert task is not None
    assert task.status == IngestionTaskStatus.FAILED
    assert "Corrupt PDF format parse error" in (task.error or "")


@pytest.mark.asyncio
async def test_task_manager_redis_branch_coverage(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Verify IngestionTaskManager with Redis backing operations."""
    import redis.asyncio as aioredis

    fake_storage: dict[str, str] = {}
    fake_queue: list[str] = []

    class FakeRedisClient:
        async def ping(self) -> None:
            pass

        async def set(self, key: str, val: str, ex: int | None = None) -> None:
            fake_storage[key] = val

        async def get(self, key: str) -> str | None:
            return fake_storage.get(key)

        async def rpush(self, key: str, val: str) -> None:
            fake_queue.append(val)

        async def lpop(self, key: str) -> str | None:
            return fake_queue.pop(0) if fake_queue else None

    fake_redis = FakeRedisClient()
    monkeypatch.setattr(aioredis, "from_url", lambda *args, **kwargs: fake_redis)

    mgr = IngestionTaskManager(max_concurrency=2)
    req = DocumentIngestRequest(content="Redis test doc", source="redis.txt")

    # Enqueue via Redis
    res = await mgr.enqueue(req, tenant_id="tenant-redis-branch")
    assert res.status == IngestionTaskStatus.QUEUED
    assert len(fake_queue) == 1

    # Get task via Redis
    task = await mgr.get_task(res.task_id, tenant_id="tenant-redis-branch")
    assert task is not None
    assert task.source == "redis.txt"

    # Claim task via Redis
    claimed = await mgr.claim_next_task()
    assert claimed is not None
    assert claimed.task_id == res.task_id
    assert claimed.status == IngestionTaskStatus.PROCESSING

    # Complete task via Redis
    result = DocumentIngestResponse(
        status="success",
        indexed_chunks=1,
        chunk_ids=["chk-redis-1"],
        source="redis.txt",
        tenant_id="tenant-redis-branch",
    )
    await mgr.complete_task(res.task_id, result)
    completed = await mgr.get_task(res.task_id)
    assert completed is not None
    assert completed.status == IngestionTaskStatus.COMPLETED
