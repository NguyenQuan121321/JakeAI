"""Exception Handling and Failure Masking Regression Tests (TEST-09 / PERF-006).

Validates that:
1. Warmup handles transient network exceptions (httpx.HTTPError) gracefully without aborting.
2. Warmup and workers do NOT swallow programming errors (TypeError, AttributeError).
3. Measured request errors are tracked in error_count rather than swallowed.
4. asyncio.CancelledError propagates cleanly without being intercepted.
5. Reporter handles OSError when writing to GITHUB_STEP_SUMMARY without swallowing defects.
"""

from __future__ import annotations

import asyncio
import os
import tempfile
from pathlib import Path
from typing import Any
from unittest.mock import patch

import httpx
import pytest

from app.performance.contracts import (
    LatencyMetrics,
    MetricDistribution,
    PerformanceBaseline,
    ScenarioBaseline,
    ScenarioResult,
    ThroughputMetrics,
)
from app.performance.regression_detector import PerformanceRegressionDetector
from app.performance.reporter import PerformanceReporter
from app.performance.runner import PerformanceBenchmarkRunner
from app.performance.scenarios.chat_scenario import run_concurrent_chat_scenario
from app.performance.scenarios.sse_scenario import run_concurrent_sse_scenario


def _create_minimal_scenario_result(name: str = "chat") -> ScenarioResult:
    dist = MetricDistribution(
        count=1,
        min=10.0,
        max=10.0,
        avg=10.0,
        median_p50=10.0,
        p90=10.0,
        p95=10.0,
        p99=10.0,
        std_dev=0.0,
    )
    return ScenarioResult(
        scenario_name=name,
        concurrency=1,
        total_requests=1,
        success_count=1,
        error_count=0,
        error_rate_pct=0.0,
        latency=LatencyMetrics(overall_ms=dist),
        throughput=ThroughputMetrics(
            total_requests=1,
            elapsed_seconds=0.1,
            requests_per_second=10.0,
            concurrency=1,
        ),
    )


@pytest.mark.performance
@pytest.mark.asyncio
async def test_chat_warmup_handles_transient_http_error() -> None:
    """Verify non-fatal network failure during warmup does not abort the test."""
    original_post = httpx.AsyncClient.post
    warmup_called = False

    async def _failing_warmup_post(
        self: httpx.AsyncClient, url: str, *args: Any, **kwargs: Any
    ) -> httpx.Response:
        nonlocal warmup_called
        payload = kwargs.get("json") or {}
        messages = payload.get("messages") or []
        if any(m.get("content") == "warmup" for m in messages):
            warmup_called = True
            raise httpx.ConnectError(
                "Transient DNS resolution error during warmup", request=None
            )
        return await original_post(self, url, *args, **kwargs)

    with patch.object(httpx.AsyncClient, "post", new=_failing_warmup_post):
        result = await run_concurrent_chat_scenario(
            concurrency=1,
            total_requests=1,
            simulated_provider_delay_ms=0,
        )
        assert warmup_called is True
        assert result.success_count == 1
        assert result.error_count == 0


@pytest.mark.performance
@pytest.mark.asyncio
async def test_sse_warmup_handles_transient_http_error() -> None:
    """Verify non-fatal network failure during SSE warmup does not abort the test."""
    with patch.object(
        httpx.AsyncClient,
        "stream",
        side_effect=httpx.ConnectTimeout("SSE connect failed"),
    ):
        result = await run_concurrent_sse_scenario(
            concurrency=1,
            total_streams=1,
            simulated_chunk_interval_ms=0,
        )
        assert result.total_requests == 1


@pytest.mark.performance
@pytest.mark.asyncio
async def test_warmup_propagates_fatal_programming_error() -> None:
    """Verify programming defect during warmup raises immediately and is NOT masked."""
    original_post = httpx.AsyncClient.post

    async def _failing_warmup_post(
        self: httpx.AsyncClient, url: str, *args: Any, **kwargs: Any
    ) -> httpx.Response:
        payload = kwargs.get("json") or {}
        messages = payload.get("messages") or []
        if any(m.get("content") == "warmup" for m in messages):
            raise TypeError("Fatal internal bug in request serializer")
        return await original_post(self, url, *args, **kwargs)

    with (
        patch.object(httpx.AsyncClient, "post", new=_failing_warmup_post),
        pytest.raises(TypeError, match="Fatal internal bug"),
    ):
        await run_concurrent_chat_scenario(
            concurrency=1,
            total_requests=1,
            simulated_provider_delay_ms=0,
        )


@pytest.mark.performance
@pytest.mark.asyncio
async def test_measured_request_failure_increments_error_count() -> None:
    """Verify measured request errors are properly accounted for in error_count."""
    original_post = httpx.AsyncClient.post

    async def _failing_measured_post(
        self: httpx.AsyncClient, url: str, *args: Any, **kwargs: Any
    ) -> httpx.Response:
        payload = kwargs.get("json") or {}
        messages = payload.get("messages") or []
        # Allow warmup to pass, fail the actual measured requests
        if not any(m.get("content") == "warmup" for m in messages):
            raise httpx.RemoteProtocolError("Connection dropped by peer", request=None)
        return await original_post(self, url, *args, **kwargs)

    with patch.object(httpx.AsyncClient, "post", new=_failing_measured_post):
        result = await run_concurrent_chat_scenario(
            concurrency=2,
            total_requests=4,
            simulated_provider_delay_ms=0,
        )
        assert result.error_count == 4
        assert result.success_count == 0
        assert result.error_rate_pct == 100.0


@pytest.mark.performance
@pytest.mark.asyncio
async def test_cancellation_propagates_without_interception() -> None:
    """Verify asyncio.CancelledError is never swallowed by worker exception handlers."""

    async def _cancel_worker() -> None:
        task = asyncio.create_task(
            run_concurrent_chat_scenario(
                concurrency=5,
                total_requests=20,
                simulated_provider_delay_ms=200,
            )
        )
        await asyncio.sleep(0.02)
        task.cancel()
        await task

    with pytest.raises(asyncio.CancelledError):
        await _cancel_worker()


def test_reporter_handles_oserror_on_step_summary() -> None:
    """Verify reporter gracefully ignores OSError when writing to GITHUB_STEP_SUMMARY."""
    with tempfile.TemporaryDirectory() as tmpdir:
        reporter = PerformanceReporter(output_dir=Path(tmpdir))
        res = _create_minimal_scenario_result("chat")
        scen_base = ScenarioBaseline(
            scenario_name="chat",
            concurrency=1,
            input_size="1 req",
            baseline_metrics={
                "latency_p95_ms": 10.0,
                "throughput_rps": 10.0,
                "error_rate_pct": 0.0,
            },
        )
        report = PerformanceRegressionDetector.evaluate_all(
            {"chat": res},
            PerformanceBaseline(version="v1", scenarios={"chat": scen_base}),
        )

        # Point to a path where writing will cause an OSError
        invalid_path = Path(tmpdir) / "nonexistent_dir" / "summary.md"
        with patch.dict(os.environ, {"GITHUB_STEP_SUMMARY": str(invalid_path)}):
            artifacts = reporter.save_artifacts(report, {"chat": res})
            # Local report files should still be saved cleanly
            assert Path(artifacts["markdown"]).exists()


def test_reporter_propagates_programming_error() -> None:
    """Verify reporter does NOT mask unexpected programming bugs (e.g. AttributeError)."""
    with tempfile.TemporaryDirectory() as tmpdir:
        reporter = PerformanceReporter(output_dir=Path(tmpdir))
        res = _create_minimal_scenario_result("chat")
        scen_base = ScenarioBaseline(
            scenario_name="chat",
            concurrency=1,
            input_size="1 req",
            baseline_metrics={
                "latency_p95_ms": 10.0,
                "throughput_rps": 10.0,
                "error_rate_pct": 0.0,
            },
        )
        report = PerformanceRegressionDetector.evaluate_all(
            {"chat": res},
            PerformanceBaseline(version="v1", scenarios={"chat": scen_base}),
        )

        with (
            patch.object(
                reporter,
                "generate_markdown_report",
                side_effect=AttributeError("Corrupted reporter object"),
            ),
            pytest.raises(AttributeError, match="Corrupted reporter object"),
        ):
            reporter.save_artifacts(report, {"chat": res})


@pytest.mark.performance
@pytest.mark.asyncio
async def test_runner_warmup_handles_transient_network_error() -> None:
    """Verify PerformanceBenchmarkRunner._warmup gracefully handles transient HTTP errors."""
    runner = PerformanceBenchmarkRunner(mode="smoke")

    with patch(
        "app.performance.runner.run_concurrent_chat_scenario",
        side_effect=httpx.ConnectError("Warmup cluster unreachable", request=None),
    ):
        # Should complete cleanly without raising
        await runner._warmup()


@pytest.mark.performance
@pytest.mark.asyncio
async def test_runner_warmup_propagates_fatal_programming_error() -> None:
    """Verify PerformanceBenchmarkRunner._warmup does NOT mask real code defects."""
    runner = PerformanceBenchmarkRunner(mode="smoke")

    with (
        patch(
            "app.performance.runner.run_concurrent_chat_scenario",
            side_effect=TypeError("Fatal engine bug in runner warmup"),
        ),
        pytest.raises(TypeError, match="Fatal engine bug in runner warmup"),
    ):
        await runner._warmup()
