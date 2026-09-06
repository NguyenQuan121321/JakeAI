"""Dedicated Ingestion Background Worker Service.

Processes asynchronous document ingestion jobs from Redis task queue
with strict bounded concurrency (max_concurrency <= 2) to protect VPS
memory (< 300MB RAM budget) from PDF/OCR heap spikes.
"""

from __future__ import annotations

import asyncio
import logging
import signal
import sys
from typing import Any

from app.rag.ingestion import DocumentIngestRequest, default_ingestion_pipeline
from app.rag.tasks import (
    IngestionTaskManager,
    IngestionTaskState,
    get_task_manager,
)

logger = logging.getLogger("jakeai.worker")


class IngestionWorker:
    """Bounded background worker executing queued document ingestion jobs."""

    def __init__(
        self,
        task_manager: IngestionTaskManager | None = None,
        poll_interval: float = 0.5,
    ) -> None:
        self.task_mgr = task_manager or get_task_manager()
        self.poll_interval = poll_interval
        self._running = False
        self._shutdown_event = asyncio.Event()

    async def process_task(self, task: IngestionTaskState) -> None:
        """Process a single claimed ingestion task within the concurrency ceiling."""
        async with self.task_mgr.semaphore:
            logger.info(
                "Processing ingestion task %s for tenant %s (source: %s)",
                task.task_id,
                task.tenant_id,
                task.source,
            )
            try:
                request = DocumentIngestRequest(
                    content=task.content,
                    source=task.source,
                    metadata=task.metadata,
                    chunk_size=task.chunk_size,
                    chunk_overlap=task.chunk_overlap,
                )
                result = await default_ingestion_pipeline.ingest(
                    request=request,
                    tenant_id=task.tenant_id,
                )
                await self.task_mgr.complete_task(task.task_id, result)
                logger.info(
                    "Successfully completed ingestion task %s (%d chunks indexed)",
                    task.task_id,
                    result.indexed_chunks,
                )
            except Exception as exc:
                logger.exception("Failed processing task %s: %s", task.task_id, exc)
                await self.task_mgr.fail_task(task.task_id, str(exc))

    async def run_once(self) -> bool:
        """Claim and process a single pending task if available.

        Returns True if a task was processed, False otherwise.
        """
        task = await self.task_mgr.claim_next_task()
        if task is None:
            return False

        await self.process_task(task)
        return True

    async def start(self) -> None:
        """Start continuous worker loop until stopped."""
        self._running = True
        self._shutdown_event.clear()
        logger.info(
            "JakeAI Ingestion Worker started (max_concurrency=%d)",
            self.task_mgr.max_concurrency,
        )

        while self._running and not self._shutdown_event.is_set():
            try:
                processed = await self.run_once()
                if not processed:
                    await asyncio.sleep(self.poll_interval)
            except asyncio.CancelledError:
                break
            except Exception as exc:
                logger.error("Worker loop exception: %s", exc)
                await asyncio.sleep(self.poll_interval)

        logger.info("JakeAI Ingestion Worker stopped gracefully.")

    def stop(self) -> None:
        """Signal worker to stop gracefully."""
        self._running = False
        self._shutdown_event.set()


async def main() -> None:
    """Worker process entrypoint."""
    logging.basicConfig(
        level=logging.INFO,
        format="%(asctime)s [%(levelname)s] [%(name)s] %(message)s",
    )
    worker = IngestionWorker()

    loop = asyncio.get_running_loop()

    def handle_signal(*_: Any) -> None:
        logger.info("Received termination signal. Shutting down worker...")
        worker.stop()

    if sys.platform != "win32":
        for sig in (signal.SIGTERM, signal.SIGINT):
            loop.add_signal_handler(sig, handle_signal)

    try:
        await worker.start()
    except (KeyboardInterrupt, asyncio.CancelledError):
        worker.stop()


if __name__ == "__main__":
    asyncio.run(main())
