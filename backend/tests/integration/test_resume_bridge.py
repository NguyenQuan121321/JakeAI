"""Unit and integration tests for ADR-001 LangGraph interrupt checkpoint and resume bridge."""

import asyncio
import json
import time
import uuid
from typing import Any
from unittest.mock import AsyncMock

import pytest
from fastapi.testclient import TestClient

from app.core.config import get_settings
from app.main import app
from app.services.resume_bridge import ResumeBridgeManager, get_resume_bridge

client = TestClient(app)


def get_auth_headers(
    tenant_id: str = "tenant-resume-test", user_id: str = "user-resume-1"
) -> dict[str, str]:
    from tests.fixtures.auth import FULL_TEST_PERMISSIONS
    from tests.fixtures.auth import create_test_jwt as v1_fixture_jwt

    token = v1_fixture_jwt(
        sub=user_id,
        tenant_id=tenant_id,
        roles=["tenant_admin"],
        permissions=FULL_TEST_PERMISSIONS,
    )
    return {"Authorization": "Bearer " + token}


@pytest.mark.asyncio
async def test_resume_bridge_manager_lifecycle() -> None:
    """Validate save_checkpoint and resume_checkpoint in manager."""
    mgr = ResumeBridgeManager()
    call_id = f"call-{uuid.uuid4().hex[:12]}"
    tenant_id = "tenant-unit-test"

    # 1. Save checkpoint
    await mgr.save_checkpoint(
        call_id=call_id,
        tenant_id=tenant_id,
        state_data={"node": "view_file", "path": "app/main.py"},
    )

    # 2. Verify retrieval
    cp = await mgr.get_checkpoint(call_id)
    assert cp is not None
    assert cp["call_id"] == call_id
    assert cp["tenant_id"] == tenant_id

    # 3. Resume execution
    result = await mgr.resume_checkpoint(
        call_id=call_id,
        result_payload={"lines": 190, "content": "FastAPI app"},
        tenant_id=tenant_id,
    )
    assert result.status == "resumed"
    assert result.tool_acknowledged is True

    # 4. Subsequent resume must raise ValueError (idempotency guard)
    with pytest.raises(ValueError, match="already"):
        await mgr.resume_checkpoint(
            call_id=call_id,
            result_payload={"lines": 190},
            tenant_id=tenant_id,
        )


@pytest.mark.asyncio
async def test_resume_bridge_cross_tenant_isolation() -> None:
    """Validate Invariant 2: attempting to resume another tenant's checkpoint fails."""
    mgr = ResumeBridgeManager()
    call_id = f"call-{uuid.uuid4().hex[:12]}"

    await mgr.save_checkpoint(
        call_id=call_id,
        tenant_id="tenant-alpha",
        state_data={"action": "test"},
    )

    with pytest.raises(PermissionError, match="Tenant mismatch"):
        await mgr.resume_checkpoint(
            call_id=call_id,
            result_payload={"output": "ok"},
            tenant_id="tenant-beta",
        )


@pytest.mark.asyncio
async def test_resume_bridge_redis_mock_paths() -> None:
    """Verify Redis read, write, lock, and delete branches in ResumeBridgeManager."""
    mgr = ResumeBridgeManager()
    call_id = f"call-redis-{uuid.uuid4().hex[:12]}"
    tenant_id = "tenant-redis-mock"

    mock_redis = AsyncMock()
    mock_redis.set.return_value = True
    record = {
        "call_id": call_id,
        "tenant_id": tenant_id,
        "state_data": {"op": "test"},
        "created_at": time.time(),
        "status": "pending",
    }
    mock_redis.get.return_value = json.dumps(record)
    mock_redis.delete.return_value = 1
    mgr.redis_client = mock_redis

    # Test save via Redis
    await mgr.save_checkpoint(call_id, tenant_id, {"op": "test"})
    assert mock_redis.set.called

    # Test get via Redis
    cp = await mgr.get_checkpoint(call_id)
    assert cp is not None
    assert cp["call_id"] == call_id

    # Test resume via Redis
    res = await mgr.resume_checkpoint(call_id, {"status": "ok"}, tenant_id)
    assert res.status == "resumed"
    assert mock_redis.delete.called

    # Test Redis lock collision (nx failed)
    mock_redis.set.return_value = False
    with pytest.raises(ValueError, match="already being processed"):
        await mgr.resume_checkpoint(call_id, {"status": "ok"}, tenant_id)

    # Test Redis read error fallback
    mock_redis.get.side_effect = Exception("Redis read timeout")
    missing_cp = await mgr.get_checkpoint("nonexistent")
    assert missing_cp is None

    # Test Redis delete error handling
    mock_redis.get.side_effect = None
    mock_redis.get.return_value = json.dumps(record)
    mock_redis.set.return_value = True
    mock_redis.delete.side_effect = Exception("Redis delete error")
    res2 = await mgr.resume_checkpoint(f"{call_id}-2", {"status": "ok"}, tenant_id)
    assert res2.status == "resumed"


def test_api_submit_tool_result_lifecycle() -> None:
    """Repeated HTTP submissions cannot consume an unbound checkpoint."""
    bridge = get_resume_bridge()
    call_id = f"call-disabled-{uuid.uuid4().hex[:8]}"
    asyncio.run(
        bridge.save_checkpoint(
            call_id=call_id,
            tenant_id="tenant-coding-api",
            state_data={"synthetic": True},
        )
    )
    before = asyncio.run(bridge.get_checkpoint(call_id))
    headers = get_auth_headers("tenant-coding-api")
    for _ in range(2):
        response = client.post(
            "/api/v1/coding/tool-result",
            headers=headers,
            json={"call_id": call_id, "result": {}},
        )
        assert response.status_code == 503
    assert asyncio.run(bridge.get_checkpoint(call_id)) == before


def test_internal_resume_perimeter_security() -> None:
    call_id = f"call-disabled-{uuid.uuid4().hex[:8]}"
    bridge = get_resume_bridge()
    asyncio.run(
        bridge.save_checkpoint(
            call_id=call_id,
            tenant_id="tenant-internal-test",
            state_data={"synthetic": True},
        )
    )
    before = asyncio.run(bridge.get_checkpoint(call_id))
    perimeter = {
        "X-Forwarded-By": "FinnApiGo",
        "X-Internal-Secret": get_settings().INTERNAL_GATEWAY_SECRET,
    }
    payload = {"call_id": call_id, "tenant_id": "tenant-internal-test", "result": {}}
    assert client.post("/internal/v1/coding/resume", json=payload).status_code == 401
    assert (
        client.post(
            "/internal/v1/coding/resume", headers=perimeter, json=payload
        ).status_code
        == 401
    )
    from tests.fixtures.auth import create_test_jwt

    perimeter["Authorization"] = "Bearer " + create_test_jwt(
        tenant_id="tenant-internal-test", permissions=["agent:execute"]
    )
    for _ in range(2):
        assert (
            client.post(
                "/internal/v1/coding/resume", headers=perimeter, json=payload
            ).status_code
            == 503
        )
    assert asyncio.run(bridge.get_checkpoint(call_id)) == before


@pytest.mark.asyncio
async def test_resume_bridge_redis_lock_cleanup_and_error_branches() -> None:
    """Exercise Redis lock release on 404, 403, in-flight locks, and lock acquisition exceptions."""
    mgr = ResumeBridgeManager()
    mock_redis = AsyncMock()
    mock_redis.set.return_value = True
    mock_redis.delete.return_value = 1
    mock_redis.get.return_value = None
    mgr.redis_client = mock_redis

    # 1. Non-existent checkpoint with Redis: deletes lock and raises KeyError
    missing_id = f"call-missing-{uuid.uuid4().hex[:8]}"
    with pytest.raises(KeyError):
        await mgr.resume_checkpoint(missing_id, {}, "tenant-any")
    assert mock_redis.delete.called

    # 2. Non-existent checkpoint with Redis delete error: logs debug and raises KeyError
    mock_redis.delete.side_effect = Exception("Redis connection reset")
    with pytest.raises(KeyError):
        await mgr.resume_checkpoint(f"{missing_id}-del-err", {}, "tenant-any")

    # 3. Tenant mismatch with Redis: deletes lock and raises PermissionError
    mock_redis.delete.side_effect = None
    tenant_mismatch_id = f"call-mismatch-{uuid.uuid4().hex[:8]}"
    mismatch_record = {
        "call_id": tenant_mismatch_id,
        "tenant_id": "tenant-owner",
        "state_data": {},
        "created_at": time.time(),
        "status": "pending",
    }
    mock_redis.get.return_value = json.dumps(mismatch_record)
    with pytest.raises(PermissionError):
        await mgr.resume_checkpoint(tenant_mismatch_id, {}, "tenant-intruder")
    assert mock_redis.delete.called

    # 4. In-flight call ID guard
    in_flight_id = f"call-inflight-{uuid.uuid4().hex[:8]}"
    mgr._in_flight_call_ids.add(in_flight_id)
    in_flight_record = {
        "call_id": in_flight_id,
        "tenant_id": "tenant-ok",
        "state_data": {},
        "created_at": time.time(),
        "status": "pending",
    }
    mock_redis.get.return_value = json.dumps(in_flight_record)
    with pytest.raises(ValueError, match="already being processed"):
        await mgr.resume_checkpoint(in_flight_id, {}, "tenant-ok")
    mgr._in_flight_call_ids.discard(in_flight_id)

    # 5. Redis lock acquisition exception: falls back gracefully and proceeds
    lock_err_id = f"call-lockerr-{uuid.uuid4().hex[:8]}"
    lock_record = {
        "call_id": lock_err_id,
        "tenant_id": "tenant-ok",
        "state_data": {},
        "created_at": time.time(),
        "status": "pending",
    }
    mock_redis.get.return_value = json.dumps(lock_record)
    mock_redis.set.side_effect = Exception("Redis cluster unavailable")
    res = await mgr.resume_checkpoint(lock_err_id, {"status": "ok"}, "tenant-ok")
    assert res.status == "resumed"


@pytest.mark.asyncio
async def test_resume_bridge_event_loop_validation_branches() -> None:
    """Verify loop rehydration in _get_redis for closed, active, and invalid client loops."""
    mgr = ResumeBridgeManager()

    # Custom non-mock fake client class so it enters the inspection block
    class FakeRedisClient:
        def __init__(self, loop: Any):
            self._loop = loop

    current_loop = asyncio.get_running_loop()

    # Case A: client loop matches current running loop -> returns client
    fake_valid = FakeRedisClient(current_loop)
    mgr.redis_client = fake_valid  # type: ignore[assignment]
    client_res = await mgr._get_redis()
    assert client_res is fake_valid

    # Case B: client loop is closed or different -> discards stale client
    other_loop = asyncio.new_event_loop()
    other_loop.close()
    fake_closed = FakeRedisClient(other_loop)
    mgr.redis_client = fake_closed  # type: ignore[assignment]
    mgr._redis_available = True
    client_res2 = await mgr._get_redis()
    assert client_res2 is not fake_closed
    assert mgr.redis_client is not fake_closed

    # Case C: Exception during loop check -> discards corrupted client
    class FaultyRedisClient:
        @property
        def connection_pool(self) -> None:
            raise RuntimeError("Corrupted connection pool state")

    faulty = FaultyRedisClient()
    mgr._redis_available = True
    mgr.redis_client = faulty  # type: ignore[assignment]
    client_res3 = await mgr._get_redis()
    assert client_res3 is not faulty
    assert mgr.redis_client is not faulty
