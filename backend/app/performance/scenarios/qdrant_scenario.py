"""Concurrent Qdrant Vector Store Access Performance Scenario (TEST-09).

Measures:
- Latency and throughput of concurrent vector upserts (embeddings + payloads)
- Dense vector similarity search latency (p50, p95, p99) under multi-tenant filters
- Semantic vector cache lookup speed
- Concurrency stability across tenant vector spaces
- Seamless operation with live Qdrant service or high-fidelity in-memory fallback
"""

from __future__ import annotations

import asyncio
import logging
import socket
import time
from urllib.parse import urlparse

from app.core.config import get_settings
from app.performance.contracts import (
    LatencyMetrics,
    ScenarioResult,
)
from app.performance.profiler import (
    PerformanceProfiler,
    calculate_throughput,
    compute_distribution,
)
from app.rag.embedding import TestOnlyFakeEmbeddingProvider
from app.rag.models import DocumentChunk
from app.rag.vector_store import QdrantVectorStore

logger = logging.getLogger(__name__)


def _is_qdrant_online(url: str | None = None, timeout: float = 0.05) -> bool:
    """Fast probe checking if Qdrant socket is reachable to avoid slow client timeouts."""
    target_url = url or get_settings().QDRANT_URL
    parsed = urlparse(target_url)
    host = parsed.hostname or "localhost"
    port = parsed.port or 6333
    try:
        with socket.create_connection((host, port), timeout=timeout):
            return True
    except OSError:
        return False


async def run_concurrent_qdrant_scenario(
    concurrency: int = 10,
    total_operations: int = 30,
) -> ScenarioResult:
    """Execute concurrent vector store upsert and search benchmark."""
    fake_emb = TestOnlyFakeEmbeddingProvider(dimension=384)
    vector_store = QdrantVectorStore(embedding_provider=fake_emb)
    semaphore = asyncio.Semaphore(concurrency)

    # Probe connectivity to determine whether to exercise live Qdrant or in-memory fallback
    if not _is_qdrant_online():
        vector_store._client = False
        vector_store._is_qdrant_available = False
        is_live_qdrant = False
    else:
        is_live_qdrant = (
            await vector_store._get_client() is not None
            and vector_store._is_qdrant_available
        )
        if not is_live_qdrant:
            vector_store._client = False

    # Seed initial vectors across 3 tenants
    initial_chunks = [
        DocumentChunk(
            chunk_id=f"seed-chunk-{i}",
            content=f"Enterprise financial report segment #{i} detailing balance sheet assets and liabilities.",
            metadata={"source": f"report_{i}.pdf", "section": "finance"},
            tenant_id=f"tenant-qdrant-{i % 3}",
        )
        for i in range(15)
    ]
    await vector_store.upsert(initial_chunks)

    search_latencies: list[float] = []
    upsert_latencies: list[float] = []
    errors = 0
    success = 0

    with PerformanceProfiler() as profiler:

        async def _vector_worker(idx: int) -> None:
            nonlocal errors, success
            tenant_id = f"tenant-qdrant-{idx % 3}"

            async with semaphore:
                try:
                    # 1. Concurrent Search
                    t0 = time.perf_counter()
                    await vector_store.search(
                        query="balance sheet assets and financial report",
                        tenant_id=tenant_id,
                        top_k=3,
                    )
                    t1 = time.perf_counter()
                    search_latencies.append((t1 - t0) * 1000.0)

                    # 2. Concurrent Upsert
                    new_chunk = DocumentChunk(
                        chunk_id=f"dynamic-chunk-{idx}",
                        content=f"Dynamic audit addendum #{idx} for tenant quarterly compliance.",
                        metadata={"type": "addendum"},
                        tenant_id=tenant_id,
                    )
                    t_up0 = time.perf_counter()
                    await vector_store.upsert([new_chunk])
                    t_up1 = time.perf_counter()
                    upsert_latencies.append((t_up1 - t_up0) * 1000.0)

                    success += 1
                except (RuntimeError, ValueError, KeyError, OSError) as exc:
                    logger.debug("Qdrant access worker operation failed: %s", exc)
                    errors += 1

        tasks = [_vector_worker(i) for i in range(total_operations)]
        await asyncio.gather(*tasks)

    dur = profiler.duration_seconds
    search_dist = compute_distribution(search_latencies)
    upsert_dist = compute_distribution(upsert_latencies)
    throughput = calculate_throughput(total_operations, dur, concurrency)
    res_metrics = profiler.get_resource_metrics()

    err_rate = (
        round((errors / total_operations * 100.0), 2) if total_operations > 0 else 0.0
    )

    return ScenarioResult(
        scenario_name="qdrant_access",
        concurrency=concurrency,
        total_requests=total_operations,
        success_count=success,
        error_count=errors,
        error_rate_pct=err_rate,
        latency=LatencyMetrics(
            overall_ms=search_dist,
            rag_ms=upsert_dist,
        ),
        throughput=throughput,
        resources=res_metrics,
        custom_metrics={
            "is_live_qdrant": is_live_qdrant,
            "vector_dimension": vector_store.dimension,
            "avg_search_latency_ms": search_dist.avg_val,
            "avg_upsert_latency_ms": upsert_dist.avg_val,
        },
    )
