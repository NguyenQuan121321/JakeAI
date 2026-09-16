"""Concurrent Redis Contention Performance Scenario (TEST-09).

Measures:
- Latency and throughput of competing atomic Redis operations:
  1. Atomic budget reservation & settlement (FinOps quota authority)
  2. Sliding window / token bucket rate limiter increments
  3. Tier 1 exact cache read/write locks
  4. Agent state checkpoint persistence
- Error rate and conflict resolution under multi-worker contention
- Graceful in-memory fallback when live Redis instance is unreachable
"""

from __future__ import annotations

import asyncio
import logging
import time
from typing import Any

from app.agent.state.checkpoint import CheckpointManager
from app.agent.state.models import RunState, RunStatus
from app.core.redis_client import acquire_redis_client
from app.finops.budget import FinOpsBudgetManager
from app.optimizer.semantic_cache import SemanticCacheManager
from app.performance.contracts import (
    CacheMetrics,
    LatencyMetrics,
    ScenarioResult,
)
from app.performance.profiler import (
    PerformanceProfiler,
    calculate_throughput,
    compute_distribution,
)
from app.rag.embedding import TestOnlyFakeEmbeddingProvider

logger = logging.getLogger(__name__)


class InMemoryContentionRedis:
    """High-fidelity thread-safe in-memory Redis simulation for offline test environments."""

    _mock_return_value = True

    def __init__(self) -> None:
        self._store: dict[str, Any] = {}
        self._lock = asyncio.Lock()

    async def get(self, key: str) -> Any | None:
        async with self._lock:
            return self._store.get(key)

    async def set(self, key: str, value: Any, _ex: int | None = None) -> bool:
        async with self._lock:
            self._store[key] = value
            return True

    async def exists(self, *keys: str) -> int:
        async with self._lock:
            return sum(1 for k in keys if k in self._store)

    async def delete(self, *keys: str) -> int:
        async with self._lock:
            count = 0
            for k in keys:
                if k in self._store:
                    del self._store[k]
                    count += 1
            return count

    async def incrby(self, key: str, amount: int) -> int:
        async with self._lock:
            curr = int(self._store.get(key, 0))
            curr += amount
            self._store[key] = curr
            return curr

    async def incrbyfloat(self, key: str, amount: float) -> float:
        async with self._lock:
            curr = float(self._store.get(key, 0.0))
            curr += amount
            self._store[key] = curr
            return curr

    async def ping(self) -> bool:
        return True

    async def eval(self, script: str, numkeys: int, *_keys_and_args: Any) -> list[Any]:
        async with self._lock:
            # FinOps finalize script check
            if "finalized" in script or numkeys == 3:
                return [120, 0.004]
            # FinOps reserve script check: allowed, tok_used, tok_limit, dol_spent, dol_limit
            return [1, 120, 1000000, 0.004, -1]


async def run_redis_contention_scenario(
    concurrency: int = 15,
    total_operations: int = 60,
) -> ScenarioResult:
    """Execute high-concurrency Redis contention benchmark."""
    client = await acquire_redis_client()
    is_live_redis = client is not None
    mock_redis = InMemoryContentionRedis() if not is_live_redis else client

    budget_mgr = FinOpsBudgetManager()
    budget_mgr.redis_client = mock_redis
    fake_emb = TestOnlyFakeEmbeddingProvider(dimension=384)
    cache_mgr = SemanticCacheManager(
        redis_client=mock_redis, embedding_provider=fake_emb
    )
    cache_mgr._qdrant_available = False
    cache_mgr._qdrant_retry_after = time.time() + 3600
    chk_mgr = CheckpointManager()
    chk_mgr.redis_client = mock_redis

    semaphore = asyncio.Semaphore(concurrency)
    latencies: list[float] = []
    errors = 0
    success = 0
    cache_hits = 0

    with PerformanceProfiler() as profiler:

        async def _contention_worker(idx: int) -> None:
            nonlocal errors, success, cache_hits
            # Target shared tenant key to force contention across coroutines
            tenant_id = f"tenant-contention-{idx % 3}"
            cache_key = f"perf-cache-prompt-{idx % 5}"

            async with semaphore:
                t0 = time.perf_counter()
                try:
                    # 1. Competing atomic budget reservation
                    res, _ = await budget_mgr.reserve_budget(
                        tenant_id=tenant_id,
                        estimated_tokens=150,
                        estimated_cost_usd=0.005,
                    )

                    # 2. Competing cache read & write
                    cached = await cache_mgr.get(
                        prompt=cache_key, tenant_id=tenant_id, exact_only=True
                    )
                    if cached:
                        cache_hits += 1
                    else:
                        await cache_mgr.set(
                            prompt=cache_key,
                            response="Contention test cached answer",
                            tenant_id=tenant_id,
                            model="gemini-1.5-flash",
                        )

                    # 3. Finalize budget settlement
                    if res:
                        await budget_mgr.finalize_reservation(
                            reservation=res,
                            actual_tokens=120,
                            actual_cost_usd=0.004,
                        )

                    # 4. Checkpoint state persistence under contention
                    run_state = RunState(
                        run_id=f"run-chk-{idx}",
                        task_id=f"task-chk-{idx}",
                        tenant_id=tenant_id,
                        user_id="user-perf",
                        status=RunStatus.COMPLETED,
                    )
                    await chk_mgr.save_checkpoint(run_state)
                    loaded = await chk_mgr.load_checkpoint(
                        run_state.run_id, tenant_id=tenant_id
                    )

                    t1 = time.perf_counter()
                    lat_ms = (t1 - t0) * 1000.0
                    latencies.append(lat_ms)

                    if loaded and loaded.run_id == run_state.run_id:
                        success += 1
                    else:
                        errors += 1
                except (RuntimeError, ValueError, KeyError, OSError) as exc:
                    logger.debug("Redis contention worker error: %s", exc)
                    errors += 1

        tasks = [_contention_worker(i) for i in range(total_operations)]
        await asyncio.gather(*tasks)

    dur = profiler.duration_seconds
    lat_dist = compute_distribution(latencies)
    throughput = calculate_throughput(total_operations, dur, concurrency)
    res_metrics = profiler.get_resource_metrics()

    err_rate = (
        round((errors / total_operations * 100.0), 2) if total_operations > 0 else 0.0
    )

    return ScenarioResult(
        scenario_name="redis_contention",
        concurrency=concurrency,
        total_requests=total_operations,
        success_count=success,
        error_count=errors,
        error_rate_pct=err_rate,
        latency=LatencyMetrics(overall_ms=lat_dist),
        throughput=throughput,
        resources=res_metrics,
        cache=CacheMetrics(
            tier1_exact_hits=cache_hits,
            tier1_exact_misses=max(0, success - cache_hits),
            cache_hit_rate_pct=round((cache_hits / max(1, success) * 100.0), 2),
        ),
        custom_metrics={
            "is_live_redis": is_live_redis,
            "contention_keys_pool": 5,
        },
    )
