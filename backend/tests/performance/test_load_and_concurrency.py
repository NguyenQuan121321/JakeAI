"""Load and Concurrency Stability Test Suite (TEST-09 / PERF-004 / CAT-126).

Verifies system behavior under elevated multi-worker concurrency:
1. Concurrency stability across tenant boundaries.
2. Contention resolution in shared cache and budget managers.
3. Streaming frame integrity under concurrent SSE connections.
4. Error rate remains strictly at 0.0% under load.
"""

from __future__ import annotations

import pytest

from app.performance.scenarios.chat_scenario import run_concurrent_chat_scenario
from app.performance.scenarios.qdrant_scenario import run_concurrent_qdrant_scenario
from app.performance.scenarios.redis_contention_scenario import (
    run_redis_contention_scenario,
)
from app.performance.scenarios.sse_scenario import run_concurrent_sse_scenario


@pytest.mark.performance
@pytest.mark.asyncio
async def test_concurrent_chat_under_load() -> None:
    """PERF-004: Validate concurrent chat ASGI handling with 8 workers."""
    res = await run_concurrent_chat_scenario(
        concurrency=8,
        total_requests=16,
        simulated_provider_delay_ms=0.0,
    )
    assert res.error_count == 0
    assert res.error_rate_pct == 0.0
    assert res.success_count == 16
    assert res.latency.overall_ms.p95 > 0.0
    assert res.throughput.requests_per_second > 5.0


@pytest.mark.performance
@pytest.mark.asyncio
async def test_redis_contention_under_load() -> None:
    """PERF-004: Validate high-concurrency atomic budget and cache contention."""
    res = await run_redis_contention_scenario(
        concurrency=12,
        total_operations=36,
    )
    assert res.error_count == 0
    assert res.error_rate_pct == 0.0
    assert res.success_count == 36
    # Sub-millisecond to low millisecond contention resolution
    assert res.latency.overall_ms.p95 < 50.0
    assert res.throughput.requests_per_second > 50.0


@pytest.mark.performance
@pytest.mark.asyncio
async def test_sse_streaming_concurrency() -> None:
    """PERF-004: Validate SSE multi-agent streaming across concurrent connections."""
    res = await run_concurrent_sse_scenario(
        concurrency=6,
        total_streams=12,
        simulated_chunk_interval_ms=1.0,
    )
    assert res.error_count == 0
    assert res.error_rate_pct == 0.0
    assert res.success_count == 12
    assert res.latency.ttfc_ms.count == 12
    assert res.latency.ttfc_ms.p95 > 0.0


@pytest.mark.performance
@pytest.mark.asyncio
async def test_qdrant_vector_store_concurrency() -> None:
    """PERF-004: Validate concurrent vector search and upsert across multi-tenant spaces."""
    res = await run_concurrent_qdrant_scenario(
        concurrency=8,
        total_operations=24,
    )
    assert res.error_count == 0
    assert res.error_rate_pct == 0.0
    assert res.success_count == 24
    assert res.latency.overall_ms.p95 > 0.0
    assert res.throughput.requests_per_second > 20.0
