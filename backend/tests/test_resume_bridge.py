"""Unit and integration tests for ADR-001 LangGraph interrupt checkpoint and resume bridge."""

import asyncio
import json
import time
import uuid
from typing import Any
from unittest.mock import AsyncMock

import jwt
import pytest
from fastapi.testclient import TestClient

from app.core.config import get_settings
from app.main import app
from app.services.resume_bridge import ResumeBridgeManager, get_resume_bridge

client = TestClient(app)


def get_auth_headers(
    tenant_id: str = "tenant-resume-test",
    user_id: str = "user-resume-1",
) -> dict[str, str]:
    """Generate valid JWT authentication headers."""
    settings = get_settings()
    now = int(time.time())
    payload: dict[str, Any] = {
        "sub": user_id,
        "tenant_id": tenant_id,
        "iat": now,
        "exp": now + 3600,
        "type": "access",
        "roles": ["developer"],
        "permissions": ["chat:read", "chat:write"],
    }
    token = jwt.encode(payload, settings.JWT_SECRET_KEY, algorithm="HS256")
    return {"Authorization": f"Bearer {token}"}


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
    """POST /api/v1/coding/tool-result lifecycle with 200, 404, 409, and 403 codes."""
    headers = get_auth_headers(tenant_id="tenant-coding-api")
    call_id = f"call-api-{uuid.uuid4().hex[:12]}"
    bridge = get_resume_bridge()

    # Pre-populate checkpoint
    asyncio.run(
        bridge.save_checkpoint(
            call_id=call_id,
            tenant_id="tenant-coding-api",
            state_data={"step": "ast_search"},
        )
    )

    # 1. Successful tool result submission
    payload = {
        "call_id": call_id,
        "result": {"matches": 3, "symbols": ["create_application"]},
    }
    response = client.post(
        "/api/v1/coding/tool-result",
        headers=headers,
        json=payload,
    )
    assert response.status_code == 200
    data = response.json()
    assert data["status"] == "resumed"
    assert data["call_id"] == call_id
    assert data["tool_acknowledged"] is True

    # 2. Duplicate submission triggers 409 Conflict
    dup_res = client.post(
        "/api/v1/coding/tool-result",
        headers=headers,
        json=payload,
    )
    assert dup_res.status_code == 409

    # 3. Non-existent call_id triggers 404 Not Found
    missing_res = client.post(
        "/api/v1/coding/tool-result",
        headers=headers,
        json={"call_id": "call-does-not-exist-999", "result": {}},
    )
    assert missing_res.status_code == 404

    # 4. Cross-tenant submission triggers 403 Forbidden
    cross_call_id = f"call-cross-{uuid.uuid4().hex[:12]}"
    asyncio.run(
        bridge.save_checkpoint(
            call_id=cross_call_id,
            tenant_id="tenant-other-owner",
            state_data={"secret": "abc"},
        )
    )
    cross_res = client.post(
        "/api/v1/coding/tool-result",
        headers=headers,  # belongs to tenant-coding-api
        json={"call_id": cross_call_id, "result": {}},
    )
    assert cross_res.status_code == 403


def test_internal_resume_perimeter_security() -> None:
    """POST /internal/v1/coding/resume enforces Invariant 4 perimeter credentials and error mapping."""
    call_id = f"call-int-{uuid.uuid4().hex[:12]}"
    bridge = get_resume_bridge()

    asyncio.run(
        bridge.save_checkpoint(
            call_id=call_id,
            tenant_id="tenant-internal-test",
            state_data={"task": "diff_prune"},
        )
    )

    payload = {
        "call_id": call_id,
        "tenant_id": "tenant-internal-test",
        "result": {"pruned_bytes": 1024},
    }

    # 1. Missing perimeter headers -> 403 Forbidden
    res_no_sec = client.post("/internal/v1/coding/resume", json=payload)
    assert res_no_sec.status_code == 403

    # 2. Valid internal perimeter headers -> 200 OK
    settings = get_settings()
    perimeter_headers = {
        "X-Forwarded-By": "FinnApiGo",
        "X-Internal-Secret": settings.INTERNAL_GATEWAY_SECRET,
    }
    res_valid = client.post(
        "/internal/v1/coding/resume",
        headers=perimeter_headers,
        json=payload,
    )
    assert res_valid.status_code == 200
    assert res_valid.json()["status"] == "resumed"

    # 3. Duplicate internal resume -> 409 Conflict
    res_dup = client.post(
        "/internal/v1/coding/resume",
        headers=perimeter_headers,
        json=payload,
    )
    assert res_dup.status_code == 409

    # 4. Non-existent call_id -> 404 Not Found
    res_404 = client.post(
        "/internal/v1/coding/resume",
        headers=perimeter_headers,
        json={
            "call_id": "call-unknown-9999",
            "tenant_id": "tenant-internal-test",
            "result": {},
        },
    )
    assert res_404.status_code == 404

    # 5. Cross-tenant mismatch -> 403 Forbidden
    cross_id = f"call-mismatch-{uuid.uuid4().hex[:12]}"
    asyncio.run(
        bridge.save_checkpoint(
            call_id=cross_id,
            tenant_id="tenant-alpha",
            state_data={},
        )
    )
    res_mismatch = client.post(
        "/internal/v1/coding/resume",
        headers=perimeter_headers,
        json={"call_id": cross_id, "tenant_id": "tenant-beta", "result": {}},
    )
    assert res_mismatch.status_code == 403
