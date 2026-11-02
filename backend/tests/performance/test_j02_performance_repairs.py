"""Regressions for measured client costs and honest benchmark verdicts."""

import importlib.util
import sys
from pathlib import Path
from unittest.mock import AsyncMock, patch

import pytest

from app.core.redis_client import create_redis_client
from app.performance.contracts import PerformanceBaseline, RegressionVerdict
from app.performance.runner import PerformanceBenchmarkRunner
from app.rag.embedding import TestOnlyFakeEmbeddingProvider
from app.rag.vector_store import QdrantVectorStore
from tests.performance.test_performance_regression_gate import (
    _create_dummy_baseline,
    _create_dummy_result,
)


def test_redis_pool_resolves_driver_metadata_once():
    # Construct real pooled connections without opening sockets. The measured
    # bug repeatedly walked installed-package metadata on the event loop.
    with patch("redis.utils.get_lib_version", return_value="test-version") as version:
        client = create_redis_client("redis://127.0.0.1:6379/0")
        connections = [client.connection_pool.make_connection() for _ in range(15)]
        assert len(connections) == 15
        assert version.call_count == 1
        assert all(c.driver_info.lib_version == "test-version" for c in connections)


@pytest.mark.asyncio
async def test_qdrant_loopback_transport_keeps_connections():
    # Use the actual SDK transport: its loopback default disables keepalive.
    from qdrant_client import AsyncQdrantClient

    clients = []

    def factory(**kwargs):
        client = AsyncQdrantClient(**kwargs)
        clients.append(client)
        client.collection_exists = AsyncMock(return_value=False)
        client.create_collection = AsyncMock()
        return client

    store = QdrantVectorStore(
        url="http://127.0.0.1:6333",
        embedding_provider=TestOnlyFakeEmbeddingProvider(dimension=384),
    )
    with patch("qdrant_client.AsyncQdrantClient", factory):
        client = await store._get_client()
    try:
        pool = client.http.client._async_client._transport._pool
        assert pool._max_keepalive_connections >= 10
        assert store._is_qdrant_available
    finally:
        for client in clients:
            await client.close()


@pytest.mark.asyncio
async def test_green_confirmation_cannot_erase_initial_latency_failure(tmp_path):
    runner = PerformanceBenchmarkRunner(mode="full")
    baseline = PerformanceBaseline(scenarios={"chat": _create_dummy_baseline("chat")})
    bad = _create_dummy_result("chat", p95=200)
    good = _create_dummy_result("chat")
    with (
        patch.object(
            runner, "run_all_scenarios", AsyncMock(return_value={"chat": bad})
        ),
        patch.object(runner, "run_scenario", AsyncMock(return_value=good)),
        patch.object(runner.store, "load_baseline", return_value=baseline),
    ):
        results, report = await runner.run_benchmark_and_audit()
    assert results["chat"] == good  # Both measurements remain available.
    assert report.initial_scenarios["chat"] == bad
    assert report.verdict == RegressionVerdict.FAIL
    assert report.has_blocking_regressions
    assert any(f.verdict == RegressionVerdict.FAIL for f in report.initial_findings)


@pytest.fixture
def control_module():
    scripts = Path(__file__).resolve().parents[3] / "scripts"
    with patch.object(sys, "path", [str(scripts), *sys.path]):
        spec = importlib.util.spec_from_file_location(
            "j02_control_test", scripts / "j02_benchmark_control.py"
        )
        module = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(module)
    return module


def control_fixture():
    from copy import deepcopy

    counts = {
        "concurrent_chat": (30, 10),
        "concurrent_agent_runs": (15, 5),
        "concurrent_rag_queries": (30, 10),
        "sse_connections": (16, 8),
        "redis_contention": (50, 15),
        "qdrant_access": (30, 10),
    }
    scenarios = {}
    for name, (count, concurrency) in counts.items():
        result = _create_dummy_result(name).model_dump()
        result.update(
            total_requests=count,
            success_count=count,
            error_count=0,
            error_rate_pct=0,
            concurrency=concurrency,
        )
        result["latency"]["overall_ms"]["count"] = count
        result["throughput"].update(total_requests=count, concurrency_level=concurrency)
        scenarios[name] = result
    scenarios["redis_contention"]["custom_metrics"] = {"is_live_redis": True}
    scenarios["qdrant_access"]["custom_metrics"] = {"is_live_qdrant": True}
    report = {
        "scenarios": deepcopy(scenarios),
        "report": {
            "verdict": "FAIL",
            "has_blocking_regressions": True,
            "total_scenarios_evaluated": 6,
            "findings": [
                {
                    "scenario": name,
                    "metric_name": "latency_p95_ms",
                    "verdict": "FAIL" if name == "qdrant_access" else "PASS",
                }
                for name in counts
            ],
        },
    }
    return scenarios, report


def test_control_threshold_failure_is_explicit_diagnostic_measurement(control_module):
    initial, report = control_fixture()
    outcome = control_module.classify_control(1, initial, report)
    assert outcome["integrity"] == "VALID"
    assert outcome["performance_verdict"] == "FAIL"
    assert outcome["classification"] == "DIAGNOSTIC_THRESHOLD_FAILURE"
    assert outcome["step_exit_code"] == 0


@pytest.mark.parametrize(
    "mutation",
    [
        "missing",
        "fallback",
        "errors_initial",
        "errors_final",
        "count",
        "concurrency",
        "exit",
        "verdict",
        "detector",
    ],
)
def test_invalid_control_remains_blocking(control_module, mutation):
    initial, report = control_fixture()
    code = 1
    if mutation == "missing":
        del initial["concurrent_chat"]
    elif mutation == "fallback":
        report["scenarios"]["qdrant_access"]["custom_metrics"]["is_live_qdrant"] = False
    elif mutation.startswith("errors"):
        source = initial if mutation == "errors_initial" else report["scenarios"]
        source["concurrent_chat"].update(
            success_count=29, error_count=1, error_rate_pct=100 / 30
        )
    elif mutation == "count":
        initial["redis_contention"]["total_requests"] = 49
    elif mutation == "concurrency":
        initial["qdrant_access"]["concurrency"] = 1
    elif mutation == "exit":
        code = 2
    elif mutation == "verdict":
        report["report"]["verdict"] = "PASS"
    elif mutation == "detector":
        report["report"]["findings"].pop()
    with pytest.raises(ValueError):
        control_module.classify_control(code, initial, report)
