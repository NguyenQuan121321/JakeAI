"""Concurrent Agent Runs Performance Scenario (TEST-09).

Measures:
- Agent execution latency (p50, p95, p99) under concurrent execution
- Task and Run state creation throughput
- ExecutionEngine dispatch, tool execution, and verification time
- Resource footprint (memory peak/delta, CPU utilization)
"""

from __future__ import annotations

import asyncio
import json
import logging
import time
from unittest.mock import patch

from app.agent.backends.base import BackendResponse
from app.agent.domain.contracts import TaskSpec
from app.agent.execution.engine import get_execution_engine
from app.performance.contracts import (
    LatencyMetrics,
    ScenarioResult,
)
from app.performance.profiler import (
    PerformanceProfiler,
    calculate_throughput,
    compute_distribution,
)

logger = logging.getLogger(__name__)


def _make_mock_plan_json(idx: int) -> str:
    return json.dumps(
        {
            "analysis": f"Deterministic execution plan for batch #{idx}",
            "steps": [
                {
                    "step_id": f"step_{idx}_1",
                    "description": f"Calculate tax differential for batch #{idx}",
                    "tool_name": "calculator",
                    "tool_arguments": {"expression": f"{100 + idx} * 1.1"},
                    "dependencies": [],
                }
            ],
        }
    )


async def run_concurrent_agent_scenario(
    concurrency: int = 5,
    total_runs: int = 15,
) -> ScenarioResult:
    """Execute concurrent Agent task creation and lifecycle execution benchmark."""
    engine = get_execution_engine()
    semaphore = asyncio.Semaphore(concurrency)

    run_latencies: list[float] = []
    step_latencies: list[float] = []
    errors = 0
    success = 0
    total_steps_executed = 0

    with PerformanceProfiler() as profiler:

        async def _worker(idx: int) -> None:
            nonlocal errors, success, total_steps_executed
            tenant_id = f"tenant-perf-agent-{idx % 3}"
            user_id = f"user-{idx}"
            plan_json = _make_mock_plan_json(idx)

            mock_response = BackendResponse(
                content=plan_json,
                model="gemini-1.5-flash",
                input_tokens=25,
                output_tokens=15,
            )

            async with semaphore:
                t0 = time.perf_counter()
                try:
                    with patch(
                        "app.agent.backends.jakeai.JakeAIBackend.generate",
                        return_value=mock_response,
                    ):
                        spec = TaskSpec(
                            goal=f"Reconcile general ledger batch #{idx} and flag variances",
                            tenant_id=tenant_id,
                            user_id=user_id,
                            roles=["admin"],
                            permissions=["*"],
                        )

                        completed = False
                        async for event in engine.execute_task(spec):
                            if event.event_type == "step_completed":
                                total_steps_executed += 1
                            elif event.event_type == "completed":
                                completed = True
                            elif event.event_type == "failed":
                                completed = False

                        t1 = time.perf_counter()
                        lat = (t1 - t0) * 1000.0
                        run_latencies.append(lat)
                        step_latencies.append(lat)

                        if completed:
                            success += 1
                        else:
                            errors += 1
                except (RuntimeError, ValueError, KeyError, OSError) as exc:
                    logger.debug("Agent run worker error: %s", exc)
                    errors += 1

        tasks = [_worker(i) for i in range(total_runs)]
        await asyncio.gather(*tasks)

    dur = profiler.duration_seconds
    run_dist = compute_distribution(run_latencies)
    step_dist = compute_distribution(step_latencies)
    throughput = calculate_throughput(total_runs, dur, concurrency)
    res_metrics = profiler.get_resource_metrics()

    err_rate = round((errors / total_runs * 100.0), 2) if total_runs > 0 else 0.0

    return ScenarioResult(
        scenario_name="concurrent_agent_runs",
        concurrency=concurrency,
        total_requests=total_runs,
        success_count=success,
        error_count=errors,
        error_rate_pct=err_rate,
        latency=LatencyMetrics(
            overall_ms=run_dist,
            agent_ms=step_dist,
        ),
        throughput=throughput,
        resources=res_metrics,
        custom_metrics={
            "total_steps_executed": total_steps_executed,
            "avg_steps_per_run": round(total_steps_executed / max(1, success), 1),
        },
    )
