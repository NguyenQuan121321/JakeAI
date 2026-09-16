"""Concurrent Server-Sent Events (SSE) Streaming Performance Scenario (TEST-09).

Measures:
- Time to First Chunk (TTFC) latency (p50, p95, p99) across concurrent streams
- Inter-chunk latency distributions (arrival cadence consistency)
- Stream throughput and total duration
- Connection concurrency stability and chunk integrity
- Memory footprint under concurrent active streaming
"""

from __future__ import annotations

import asyncio
import time
from collections.abc import AsyncGenerator
from typing import Any
from unittest.mock import patch

from httpx import ASGITransport, AsyncClient

from app.main import app
from app.performance.contracts import (
    LatencyMetrics,
    ScenarioResult,
)
from app.performance.profiler import (
    PerformanceProfiler,
    StreamMetricsCollector,
    calculate_throughput,
    compute_distribution,
)
from app.providers.base import ProviderCacheTelemetry
from tests.fixtures.auth import create_test_jwt


async def _mock_stream_workflow(
    prompt: str,
    context: Any,
    conversation_id: str,
    model: str | None = None,
    chunk_delay_ms: float = 3.0,
) -> AsyncGenerator[dict[str, Any], None]:
    """Mock multi-agent streaming workflow generator for deterministic performance profiling."""
    delay_s = chunk_delay_ms / 1000.0
    if delay_s > 0:
        await asyncio.sleep(delay_s)
    yield {
        "node": "supervisor",
        "workflow_phase": "planning",
        "mascot_state": "thinking",
        "message": "Analyzing query and formulating plan...",
    }
    if delay_s > 0:
        await asyncio.sleep(delay_s)
    yield {
        "node": "financial_analyst",
        "workflow_phase": "executing",
        "mascot_state": "working",
        "message": "Computing ledger balances and tax margins...",
    }
    if delay_s > 0:
        await asyncio.sleep(delay_s)
    yield {
        "node": "verifier",
        "workflow_phase": "completed",
        "mascot_state": "success",
        "message": "Audited financials confirm 14.2% YoY revenue expansion.",
        "final_response": "Audited financials confirm 14.2% YoY revenue expansion.",
        "provider_telemetry": ProviderCacheTelemetry(
            is_cache_eligible=True,
            cache_hit=False,
            cached_tokens=0,
            uncached_input_tokens=70,
            cache_write_tokens=0,
            output_tokens=20,
            provider="gemini",
            model="gemini-1.5-flash",
        ),
        "model_used": "gemini-1.5-flash",
    }


async def run_concurrent_sse_scenario(
    concurrency: int = 8,
    total_streams: int = 16,
    simulated_chunk_interval_ms: float = 3.0,
) -> ScenarioResult:
    """Execute concurrent SSE chat stream benchmark."""
    tokens = [
        create_test_jwt(tenant_id=f"tenant-perf-sse-{i}", roles=["admin"])
        for i in range(4)
    ]
    headers_pool = [
        {"Authorization": f"Bearer {tok}", "Content-Type": "application/json"}
        for tok in tokens
    ]

    ttfc_samples: list[float] = []
    inter_chunk_samples: list[float] = []
    stream_durations: list[float] = []
    errors = 0
    success = 0
    total_chunks_received = 0

    semaphore = asyncio.Semaphore(concurrency)
    transport = ASGITransport(app=app)

    async def _mock_stream_patch(prompt: str, context: Any, conversation_id: str, model: str | None = None) -> AsyncGenerator[dict[str, Any], None]:
        async for chunk in _mock_stream_workflow(prompt, context, conversation_id, model, simulated_chunk_interval_ms):
            yield chunk

    async with AsyncClient(transport=transport, base_url="http://testserver") as client:
        with patch(
            "app.api.v1.endpoints.chat.stream_multi_agent_workflow",
            side_effect=_mock_stream_patch,
        ):
            # Pre-warm SSE endpoint before starting profiler
            try:
                async with client.stream(
                    "POST",
                    "/api/v1/chat/stream",
                    json={"prompt": "warmup"},
                    headers=headers_pool[0],
                    timeout=10.0,
                ) as warm_resp:
                    async for _ in warm_resp.aiter_lines():
                        pass
            except Exception:
                pass

            with PerformanceProfiler() as profiler:
                async def _stream_worker(idx: int) -> None:
                    nonlocal errors, success, total_chunks_received
                    collector = StreamMetricsCollector()
                    payload = {
                        "prompt": f"Stream audit overview for portfolio #{idx}",
                        "parameters": {"model": "gemini-1.5-flash"},
                    }
                    worker_headers = headers_pool[idx % len(headers_pool)]

                    async with semaphore:
                        try:
                            async with client.stream(
                                "POST",
                                "/api/v1/chat/stream",
                                json=payload,
                                headers=worker_headers,
                                timeout=15.0,
                            ) as response:
                                if response.status_code != 200:
                                    errors += 1
                                    return

                                async for line in response.aiter_lines():
                                    if line.startswith("data:"):
                                        collector.record_chunk()

                            collector.finish()
                            if collector.chunk_count > 0:
                                success += 1
                                total_chunks_received += collector.chunk_count
                                ttfc_samples.append(collector.ttfc_ms)
                                stream_durations.append(collector.total_duration_ms)
                                inter_chunk_samples.extend(collector.inter_chunk_delays_ms[1:])
                            else:
                                errors += 1
                        except Exception:
                            errors += 1

                tasks = [_stream_worker(i) for i in range(total_streams)]
                await asyncio.gather(*tasks)

    dur = profiler.duration_seconds
    ttfc_dist = compute_distribution(ttfc_samples)
    inter_chunk_dist = compute_distribution(inter_chunk_samples)
    stream_dur_dist = compute_distribution(stream_durations)
    throughput = calculate_throughput(total_streams, dur, concurrency)
    res_metrics = profiler.get_resource_metrics()

    err_rate = round((errors / total_streams * 100.0), 2) if total_streams > 0 else 0.0

    return ScenarioResult(
        scenario_name="sse_connections",
        concurrency=concurrency,
        total_requests=total_streams,
        success_count=success,
        error_count=errors,
        error_rate_pct=err_rate,
        latency=LatencyMetrics(
            overall_ms=stream_dur_dist,
            ttfc_ms=ttfc_dist,
            inter_chunk_ms=inter_chunk_dist,
        ),
        throughput=throughput,
        resources=res_metrics,
        custom_metrics={
            "total_chunks_received": total_chunks_received,
            "avg_chunks_per_stream": round(total_chunks_received / max(1, success), 1),
            "median_ttfc_ms": ttfc_dist.median_p50,
            "p95_ttfc_ms": ttfc_dist.p95,
        },
    )
