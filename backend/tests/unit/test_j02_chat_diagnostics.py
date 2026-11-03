"""Failure-only observer behavior; synthetic ASGI/Redis, no external load."""

import asyncio
import importlib
import sys
import types
from pathlib import Path

import httpx
import pytest


@pytest.fixture
def worker(monkeypatch):
    monkeypatch.syspath_prepend(str(Path(__file__).resolve().parents[3] / "scripts"))
    return importlib.import_module("j02_paired_worker")


async def synthetic_app(scope, receive, send):
    from redis.asyncio import Redis

    await Redis().execute_command("GET", "private-key-never-captured")
    await send({"type": "http.response.start", "status": 200, "headers": []})
    await send({"type": "http.response.body", "body": b"private-body-never-captured"})


@pytest.mark.asyncio
async def test_actual_diagnostic_runner_observes_one_request_and_restores_bindings(
    worker, monkeypatch
):
    from redis.asyncio import Redis

    module = types.ModuleType("app.performance.scenarios.chat_scenario")
    module.app = synthetic_app
    monkeypatch.setitem(sys.modules, module.__name__, module)

    async def command(self, *args, **kwargs):
        # More than one scheduling interval also works with coarse native timers.
        for _ in range(2):
            await asyncio.sleep(0.01)
        return b"private-redis-result-never-captured"

    monkeypatch.setattr(Redis, "execute_command", command)
    calls = []

    async def run(name):
        calls.append(name)
        async with httpx.AsyncClient(
            transport=httpx.ASGITransport(app=module.app), base_url="http://test"
        ) as client:
            assert (
                await client.post(
                    "/private-path",
                    headers={"Authorization": "Bearer private-token-never-captured"},
                    content=b"private-request-never-captured",
                )
            ).status_code == 200
        return types.SimpleNamespace(model_dump=lambda **_: {"retained_sample": True})

    report = await worker.diagnostic_profile(
        types.SimpleNamespace(run_scenario=run), ["concurrent_chat"]
    )
    row = report["scenarios"]["concurrent_chat"]
    observation = row["request_observer"]
    assert calls == ["concurrent_chat"]
    assert row["instrumented_sample"] == {"retained_sample": True}
    assert observation["requests"][0]["status"] == 200
    assert observation["redis_commands"][0]["operation"] == "GET"
    assert observation["redis_commands"][0]["request_id"] == 1
    assert observation["event_loop_lag_ms"]
    assert observation["dropped_records"] == 0
    assert "private-" not in repr(observation)
    assert module.app is synthetic_app and Redis.execute_command is command


@pytest.mark.asyncio
async def test_diagnostic_runner_error_restores_bindings_and_cancels_observer(
    worker, monkeypatch
):
    from redis.asyncio import Redis

    module = types.ModuleType("app.performance.scenarios.chat_scenario")
    module.app = synthetic_app
    monkeypatch.setitem(sys.modules, module.__name__, module)
    original = Redis.execute_command
    before = set(asyncio.all_tasks())

    async def fail(name):
        raise ValueError("private-diagnostic-error")

    with pytest.raises(ValueError):
        await worker.diagnostic_profile(
            types.SimpleNamespace(run_scenario=fail), ["concurrent_chat"]
        )
    assert module.app is synthetic_app and Redis.execute_command is original
    assert set(asyncio.all_tasks()) == before
