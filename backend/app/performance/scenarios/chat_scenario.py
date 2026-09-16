"""Concurrent Chat Performance Scenario (TEST-09).

Measures:
- Latency (p50, p95, p99) of authenticated chat requests under concurrency
- Throughput (requests/sec)
- Error rate and concurrency stability
- Token consumption and multi-tier cache hits/misses
- Memory heap and CPU process time
"""

from __future__ import annotations

import asyncio
import logging
import time
from typing import Any
from unittest.mock import patch

import httpx
from httpx import ASGITransport, AsyncClient

from app.core.llm_provider import UpstreamLLMResponse
from app.main import app
from app.performance.contracts import (
    CacheMetrics,
    LatencyMetrics,
    ScenarioResult,
    TokenMetrics,
)
from app.performance.profiler import (
    PerformanceProfiler,
    calculate_throughput,
    compute_distribution,
)
from app.providers.base import ProviderCacheTelemetry
from tests.fixtures.auth import create_test_jwt

logger = logging.getLogger(__name__)


def _create_mock_chat_response(
    text: str = "Analysis: Q3 Operating Profit stood at $63.4M.",
) -> UpstreamLLMResponse:
    """Deterministic upstream LLM test double for pure platform performance measurement."""
    return UpstreamLLMResponse(
        text=text,
        model="gemini-1.5-flash",
        provider="gemini",
        telemetry=ProviderCacheTelemetry(
            is_cache_eligible=True,
            cache_hit=False,
            cached_tokens=0,
            uncached_input_tokens=85,
            cache_write_tokens=0,
            output_tokens=25,
            provider="gemini",
            model="gemini-1.5-flash",
        ),
    )


async def run_concurrent_chat_scenario(
    concurrency: int = 10,
    total_requests: int = 30,
    simulated_provider_delay_ms: float = 5.0,
) -> ScenarioResult:
    """Execute concurrent chat benchmark against ASGI application."""
    token = create_test_jwt(tenant_id="tenant-perf-chat", roles=["admin"])
    headers = {
        "Authorization": f"Bearer {token}",
        "Content-Type": "application/json",
    }

    latencies: list[float] = []
    errors = 0
    success = 0
    cache_hits = 0
    cache_misses = 0

    semaphore = asyncio.Semaphore(concurrency)
    transport = ASGITransport(app=app)

    async def _mock_call(*_args: Any, **_kwargs: Any) -> UpstreamLLMResponse:
        if simulated_provider_delay_ms > 0:
            await asyncio.sleep(simulated_provider_delay_ms / 1000.0)
        return _create_mock_chat_response()

    from app.rag.embedding import TestOnlyFakeEmbeddingProvider
    from app.services.ai_gateway import get_gateway_proxy

    proxy = get_gateway_proxy()
    orig_emb = proxy.cache_mgr._embedding_provider
    orig_qdrant_avail = proxy.cache_mgr._qdrant_available
    orig_retry = proxy.cache_mgr._qdrant_retry_after

    proxy.cache_mgr._embedding_provider = TestOnlyFakeEmbeddingProvider(dimension=384)
    if proxy.cache_mgr.qdrant_client is None:
        proxy.cache_mgr._qdrant_available = False
        proxy.cache_mgr._qdrant_retry_after = time.time() + 3600

    try:
        async with AsyncClient(
            transport=transport, base_url="http://testserver"
        ) as client:
            with (
                patch(
                    "app.services.ai_gateway.call_upstream_llm_detailed",
                    side_effect=_mock_call,
                ),
                patch(
                    "app.core.llm_provider.call_upstream_llm_detailed",
                    side_effect=_mock_call,
                ),
            ):
                # Pre-warm ASGI route & singleton handlers before starting profiler
                try:
                    await client.post(
                        "/api/v1/gateway/chat/completions",
                        json={"messages": [{"role": "user", "content": "warmup"}]},
                        headers=headers,
                        timeout=10.0,
                    )
                except httpx.HTTPError as exc:
                    logger.debug("Chat ASGI warmup request failed: %s", exc)

                with PerformanceProfiler() as profiler:

                    async def _worker(idx: int) -> None:
                        nonlocal errors, success, cache_hits, cache_misses
                        # Alternate queries between recurring (testing cache) and unique
                        query_id = idx % 5
                        payload = {
                            "messages": [
                                {
                                    "role": "user",
                                    "content": f"Summarize invoice batch #{query_id} for reconciliation",
                                }
                            ],
                            "model": "gemini-1.5-flash",
                        }

                        async with semaphore:
                            t0 = time.perf_counter()
                            try:
                                resp = await client.post(
                                    "/api/v1/gateway/chat/completions",
                                    json=payload,
                                    headers=headers,
                                    timeout=10.0,
                                )
                                t1 = time.perf_counter()
                                lat_ms = (t1 - t0) * 1000.0
                                latencies.append(lat_ms)

                                if resp.status_code == 200:
                                    success += 1
                                    data = resp.json()
                                    if (
                                        data.get("cached")
                                        or data.get("usage", {}).get("cached_tokens", 0)
                                        > 0
                                    ):
                                        cache_hits += 1
                                    else:
                                        cache_misses += 1
                                else:
                                    errors += 1
                            except (httpx.HTTPError, ValueError) as exc:
                                logger.debug("Chat worker request failed: %s", exc)
                                errors += 1

                    tasks = [_worker(i) for i in range(total_requests)]
                    await asyncio.gather(*tasks)
    finally:
        proxy.cache_mgr._embedding_provider = orig_emb
        proxy.cache_mgr._qdrant_available = orig_qdrant_avail
        proxy.cache_mgr._qdrant_retry_after = orig_retry

    dur = profiler.duration_seconds
    lat_dist = compute_distribution(latencies)
    throughput = calculate_throughput(total_requests, dur, concurrency)
    res_metrics = profiler.get_resource_metrics()

    err_rate = (
        round((errors / total_requests * 100.0), 2) if total_requests > 0 else 0.0
    )
    hit_rate = (
        round((cache_hits / (cache_hits + cache_misses) * 100.0), 2)
        if (cache_hits + cache_misses) > 0
        else 0.0
    )

    return ScenarioResult(
        scenario_name="concurrent_chat",
        concurrency=concurrency,
        total_requests=total_requests,
        success_count=success,
        error_count=errors,
        error_rate_pct=err_rate,
        latency=LatencyMetrics(overall_ms=lat_dist),
        throughput=throughput,
        resources=res_metrics,
        tokens=TokenMetrics(
            total_raw_tokens=total_requests * 85,
            total_optimized_tokens=total_requests * 85,
            total_cached_tokens=cache_hits * 85,
            total_output_tokens=success * 25,
            token_reduction_pct=round(hit_rate, 2),
        ),
        cache=CacheMetrics(
            tier1_exact_hits=cache_hits,
            tier1_exact_misses=cache_misses,
            cache_hit_rate_pct=hit_rate,
        ),
        custom_metrics={
            "simulated_provider_delay_ms": simulated_provider_delay_ms,
        },
    )
