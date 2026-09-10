"""Tests for Durable Redis Checkpointing (TASK ORC-05)."""

import json
import time
import uuid
from unittest.mock import AsyncMock

import pytest

from app.agent.state.checkpoint import CheckpointManager
from app.agent.state.models import RunState, RunStatus


@pytest.mark.asyncio
async def test_durable_checkpointing_lifecycle() -> None:
    """Validate save, load, delete, and resume in CheckpointManager."""
    mgr = CheckpointManager()
    run_id = f"run_{uuid.uuid4().hex[:12]}"
    task_id = f"task_{uuid.uuid4().hex[:12]}"
    tenant_id = "tenant-durable-test"

    run = RunState(
        run_id=run_id,
        task_id=task_id,
        tenant_id=tenant_id,
        user_id="user-1",
        status=RunStatus.RUNNING,
        current_iteration=3,
        metadata={"obo_token": "secret-obo-12345678", "custom_key": "safe_value"},
    )

    # 1. Save Checkpoint
    cp_id = await mgr.save_checkpoint(run)
    assert cp_id.startswith("cp_")

    # 2. Load Checkpoint
    loaded = await mgr.load_checkpoint(run_id, tenant_id=tenant_id)
    assert loaded is not None
    assert loaded.run_id == run_id
    assert loaded.current_iteration == 3
    # Verify secrets were redacted
    assert loaded.metadata.get("obo_token") == "[REDACTED]"
    assert loaded.metadata.get("custom_key") == "safe_value"

    # 3. Resume Run from Checkpoint
    resumed = await mgr.resume_run_from_checkpoint(run_id, tenant_id=tenant_id)
    assert resumed.run_id == run_id
    assert resumed.tenant_id == tenant_id
    assert resumed.current_iteration == 3

    # 4. Cross-Tenant Protection
    with pytest.raises(PermissionError, match="Tenant mismatch"):
        await mgr.load_checkpoint(run_id, tenant_id="tenant-intruder")

    with pytest.raises(PermissionError, match="Tenant mismatch"):
        await mgr.resume_run_from_checkpoint(run_id, tenant_id="tenant-intruder")

    # 5. Delete Checkpoint
    deleted = await mgr.delete_checkpoint(run_id, tenant_id=tenant_id)
    assert deleted is True

    # 6. Subsequent load returns None
    after_del = await mgr.load_checkpoint(run_id, tenant_id=tenant_id)
    assert after_del is None


@pytest.mark.asyncio
async def test_durable_checkpointing_survives_process_restart_via_redis() -> None:
    """Simulate complete process memory loss: state is restored from Redis."""
    mgr = CheckpointManager()
    run_id = f"run_restart_{uuid.uuid4().hex[:8]}"
    tenant_id = "tenant-restart"

    mock_redis = AsyncMock()
    mock_redis.set.return_value = True
    mgr.redis_client = mock_redis

    run = RunState(
        run_id=run_id,
        task_id="task-123",
        tenant_id=tenant_id,
        user_id="user-1",
        status=RunStatus.PAUSED_APPROVAL,
        current_iteration=5,
        final_output="In-flight analysis",
    )

    # Save to Redis
    cp_id = await mgr.save_checkpoint(run)
    assert mock_redis.set.called

    # Simulate Process Restart: Wipe heap memory
    mgr.clear()
    assert mgr._checkpoints == {}
    assert mgr._run_to_latest == {}

    # Setup Redis mock returns
    mock_redis.get.side_effect = lambda key: (
        cp_id if key == f"agent:checkpoint:run:{run_id}"
        else json.dumps({
            "checkpoint_id": cp_id,
            "checkpoint_created_at": time.time(),
            "run_id": run_id,
            "task_id": "task-123",
            "tenant_id": tenant_id,
            "user_id": "user-1",
            "status": "paused_approval",
            "current_iteration": 5,
            "final_output": "In-flight analysis",
            "metadata": {},
        }) if key == f"agent:checkpoint:rec:{cp_id}"
        else None
    )

    # Rehydration from Redis
    rehydrated = await mgr.load_checkpoint(run_id, tenant_id=tenant_id)
    assert rehydrated is not None
    assert rehydrated.run_id == run_id
    assert rehydrated.current_iteration == 5
    assert rehydrated.status == RunStatus.PAUSED_APPROVAL

    # Resuming after restart
    resumed = await mgr.resume_run_from_checkpoint(run_id, tenant_id=tenant_id)
    assert resumed.run_id == run_id
    assert resumed.status == RunStatus.PAUSED_APPROVAL
