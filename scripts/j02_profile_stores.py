"""Supplemental hosted profiling; never substitutes for uninstrumented gates."""

import asyncio
import cProfile
from collections import defaultdict
import functools
import json
from pathlib import Path
import platform
import pstats
import sys
import time
from unittest.mock import patch

from j02_rehearsal import identity


async def profile():
    identity()  # No local/fork/private execution or store access.
    backend = Path(__file__).resolve().parents[1] / "backend"
    sys.path.insert(0, str(backend))
    from tests.fixtures.identity import configure_asgi_benchmark_identity
    configure_asgi_benchmark_identity()
    from app.performance.runner import PerformanceBenchmarkRunner
    from app.performance.profiler import compute_distribution
    from app.core.redis_client import acquire_redis_client
    from redis.asyncio import Redis
    from qdrant_client import AsyncQdrantClient
    import httpx

    client = await acquire_redis_client()
    if client is None:
        raise RuntimeError("Real owned Redis required for profiling")
    info = await client.info("server")
    config = await client.config_get("appendonly", "appendfsync", "maxmemory-policy")
    rtt = []
    for _ in range(20):
        started = time.perf_counter()
        await client.ping()
        rtt.append((time.perf_counter() - started) * 1000)
    await client.aclose()
    vector = AsyncQdrantClient(url="http://127.0.0.1:6333", check_compatibility=False)
    q_rtt = []
    for _ in range(20):
        started = time.perf_counter()
        await vector.get_collections()
        q_rtt.append((time.perf_counter() - started) * 1000)
    await vector.close()
    print("J02_STORE_RTT " + json.dumps({"platform": platform.platform(), "python": platform.python_version(),
        "redis_version": info["redis_version"], "redis_config": config,
        "redis_ping_ms": compute_distribution(rtt).model_dump(),
        "qdrant_collections_ms": compute_distribution(q_rtt).model_dump()}), flush=True)

    runner = PerformanceBenchmarkRunner(mode="full")
    for name in ("redis_contention", "qdrant_access"):
        timings = defaultdict(list)
        events = defaultdict(int)
        loop_lag = []
        running = True
        def timed(label, original):
            @functools.wraps(original)
            async def call(*args, **kwargs):
                started = time.perf_counter()
                try:
                    return await original(*args, **kwargs)
                finally:
                    timings[label].append((time.perf_counter() - started) * 1000)
            return call

        send = httpx.AsyncClient.send
        async def trace_send(self, request, *args, **kwargs):
            original_trace = request.extensions.get("trace")
            async def trace(event, data):
                events[event] += 1
                if original_trace is not None:
                    await original_trace(event, data)
            request.extensions["trace"] = trace
            started = time.perf_counter()
            response = await send(self, request, *args, **kwargs)
            timings["http_send"].append((time.perf_counter() - started) * 1000)
            # Separate setup from timed query/upsert server work. Retain only
            # durations, never bodies/URLs/headers/credentials.
            operation = "query" if request.url.path.endswith("/query") else "upsert" if request.url.path.endswith("/points") and request.method == "PUT" else "setup"
            label = "qdrant_server_" + operation + "_ms"
            if len(timings[label]) < 100:
                server_time = response.json().get("time")
                if isinstance(server_time, (int, float)):
                    timings[label].append(server_time * 1000)
            return response

        async def ticker():
            while running:
                start = time.perf_counter()
                await asyncio.sleep(0.005)
                loop_lag.append(max(0, (time.perf_counter() - start) * 1000 - 5))

        cpu = cProfile.Profile()
        ticker_task = asyncio.create_task(ticker())
        try:
            with (patch.object(Redis, "execute_command", timed("redis_command", Redis.execute_command)),
                  patch.object(AsyncQdrantClient, "query_points", timed("qdrant_query", AsyncQdrantClient.query_points)),
                  patch.object(AsyncQdrantClient, "upsert", timed("qdrant_upsert", AsyncQdrantClient.upsert)),
                  patch.object(httpx.AsyncClient, "send", trace_send)):
                cpu.enable()
                result = await runner.run_scenario(name)
                cpu.disable()
        finally:
            cpu.disable()
            running = False
            await ticker_task
        expected = 50 if name == "redis_contention" else 30
        flag = "is_live_redis" if name == "redis_contention" else "is_live_qdrant"
        if result.total_requests != expected or result.error_count or result.success_count != expected or result.custom_metrics[flag] is not True:
            raise RuntimeError("Profiling measurement integrity failed")
        stats = pstats.Stats(cpu)
        top = sorted(stats.stats.items(), key=lambda entry: entry[1][3], reverse=True)[:45]
        print("J02_STORE_PROFILE " + json.dumps({"scenario": name,
            "scope": "supplemental cProfile/async timing; instrumented overhead is not a candidate performance gate",
            "result": result.model_dump(), "awaited_ms": {key: compute_distribution(values).model_dump() for key, values in timings.items()},
            "loop_lag_ms": compute_distribution(loop_lag).model_dump(), "network_events": dict(events),
            "cpu": [{"file": Path(key[0]).name, "line": key[1], "function": key[2],
                     "calls": value[1], "self_seconds": value[2], "cumulative_seconds": value[3]} for key, value in top]}), flush=True)


if __name__ == "__main__":
    asyncio.run(profile())
