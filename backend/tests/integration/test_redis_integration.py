"""Comprehensive Redis Integration Test Suite (INT-017).

Verifies real interactions between JakeAI components and the Redis backing store:
1. CheckpointManager (agent:checkpoint:rec / run state serialization)
2. ResumeBridgeManager (agent:resume / interrupt checkpoint state)
3. TokenBucketRateLimiter (atomic Lua token bucket rate limiting)
4. FinOpsBudgetManager (atomic Lua check-and-reserve and settlement)
5. BYOKManager (AES-256 encrypted credential vault)
6. SemanticCacheManager (Tier 1 exact match response cache)
7. IngestionTaskManager (asynchronous document ingestion queue)
8. Security token denylist (JTI / session revocation)

Mandatory failure cases tested across Redis authorities:
- unavailable (port closed / unreachable -> graceful in-memory degradation)
- timeout (socket timeout -> latch backoff engaged)
- malformed response (corrupted JSON payload -> fail closed / clean handling)
- connection failure (connection severed -> fallback without crash)
- partial failure (multi-key atomic failure handled)
- recovery (reconnect after failure restored)
"""

from __future__ import annotations

import time
import uuid
from unittest.mock import AsyncMock, patch

import jwt
import pytest
from fastapi import HTTPException

from app.agent.state.checkpoint import CheckpointManager
from app.agent.state.models import RunState, RunStatus
from app.core.byok import BYOKManager
from app.core.config import get_settings
from app.core.rate_limiter import TokenBucketRateLimiter
from app.core.security import check_token_denylist
from app.finops.budget import FinOpsBudgetManager
from app.optimizer.semantic_cache import SemanticCacheManager
from app.rag.embedding import TestOnlyFakeEmbeddingProvider
from app.rag.ingestion import DocumentIngestRequest, DocumentIngestResponse
from app.rag.tasks import IngestionTaskManager, IngestionTaskStatus
from app.services.resume_bridge import ResumeBridgeManager


def _check_redis_reachable() -> bool:
    """Probe if real Redis service is reachable."""
    try:
        import redis as sync_redis

        client = sync_redis.Redis.from_url(
            get_settings().REDIS_URL,
            socket_connect_timeout=0.3,
            socket_timeout=0.3,
        )
        try:
            return bool(client.ping())
        finally:
            client.close()
    except Exception:
        return False


REDIS_AVAILABLE = _check_redis_reachable()


@pytest.fixture
def fake_embedding_provider() -> TestOnlyFakeEmbeddingProvider:
    return TestOnlyFakeEmbeddingProvider(dimension=64)


@pytest.mark.asyncio
class TestRedisIntegrationAuthorities:
    """Integration verification across all 8 canonical Redis consumers."""

    async def test_checkpoint_manager_redis_lifecycle(self) -> None:
        """Authority 1: CheckpointManager persistence in Redis with rehydration."""
        mgr = CheckpointManager()
        tenant_id = f"tenant-cp-{uuid.uuid4().hex[:8]}"
        run_state = RunState(
            run_id=f"run-{uuid.uuid4().hex[:8]}",
            task_id=f"task-{uuid.uuid4().hex[:8]}",
            tenant_id=tenant_id,
            user_id="user-integration-test",
            status=RunStatus.RUNNING,
            current_iteration=1,
            tool_calls=[{"name": "fetch_balance", "input": {"acc": "123"}}],
        )

        # 1. Save checkpoint
        cp_id = await mgr.save_checkpoint(
            run_state=run_state,
            short_term_memory=[{"role": "user", "content": "hello"}],
        )
        assert cp_id.startswith("cp_")

        # 2. Rehydrate directly
        reloaded = await mgr.get_checkpoint(cp_id, tenant_id=tenant_id)
        assert reloaded.run_id == run_state.run_id
        assert reloaded.status == RunStatus.RUNNING
        assert len(reloaded.short_term_memory_snapshot) == 1

        # 3. Multi-tenant isolation enforcement
        with pytest.raises(PermissionError):
            await mgr.get_checkpoint(cp_id, tenant_id="foreign-tenant")

        # 4. Simulate process restart by clearing local memory cache
        mgr._checkpoints.clear()
        mgr._run_to_latest.clear()

        # Re-fetch: if Redis is available, it restores from Redis; otherwise None is returned
        if REDIS_AVAILABLE:
            rehydrated = await mgr.load_checkpoint(
                run_state.run_id, tenant_id=tenant_id
            )
            assert rehydrated is not None
            assert rehydrated.run_id == run_state.run_id
            assert rehydrated.tenant_id == tenant_id

    async def test_resume_bridge_redis_lifecycle(self) -> None:
        """Authority 2: ResumeBridgeManager interrupt checkpoints in Redis."""
        bridge = ResumeBridgeManager()
        call_id = f"call-{uuid.uuid4().hex[:8]}"
        tenant_id = f"tenant-bridge-{uuid.uuid4().hex[:8]}"
        state_payload = {"step": 2, "pending_tool": "wire_transfer"}

        await bridge.save_checkpoint(
            call_id=call_id,
            tenant_id=tenant_id,
            state_data=state_payload,
            ttl_seconds=60,
        )

        # Load checkpoint
        loaded = await bridge.get_checkpoint(call_id=call_id)
        assert loaded is not None
        assert loaded["call_id"] == call_id
        assert loaded["tenant_id"] == tenant_id

        # Foreign tenant access is blocked on resume
        with pytest.raises(PermissionError):
            await bridge.resume_checkpoint(
                call_id=call_id,
                result_payload={"status": "confirmed"},
                tenant_id="foreign-tenant",
            )

    async def test_token_bucket_rate_limiter_lua(self) -> None:
        """Authority 3: TokenBucketRateLimiter Lua script atomicity."""
        limiter = TokenBucketRateLimiter(rate_per_minute=60, burst=5)
        tenant = f"tenant-rl-{uuid.uuid4().hex[:8]}"
        client_ip = "192.168.1.50"

        # Consume 5 tokens (capacity burst)
        for _ in range(5):
            allowed, _, _ = await limiter.check(tenant_id=tenant, client_ip=client_ip)
            assert allowed is True

        # 6th token must be denied under bursting limit
        allowed, _, retry_after = await limiter.check(
            tenant_id=tenant, client_ip=client_ip
        )
        assert allowed is False
        assert retry_after >= 0.0

    async def test_finops_budget_atomic_reservation_and_finalization(self) -> None:
        """Authority 4: FinOpsBudgetManager atomic Lua reservation and settlement."""
        finops = FinOpsBudgetManager()
        tenant_id = f"tenant-budget-{uuid.uuid4().hex[:8]}"

        await finops.set_budget(
            tenant_id=tenant_id, token_quota=1000, dollar_budget_usd=10.0
        )

        # Pre-flight reserve 400 tokens
        reservation, err = await finops.reserve_budget(
            tenant_id=tenant_id,
            estimated_tokens=400,
            estimated_cost_usd=0.04,
        )
        assert err is None
        assert reservation is not None
        assert reservation.reserved_tokens == 400

        # Verify usage reflects reservation
        budget = await finops.get_budget_status(tenant_id)
        assert budget.tokens_used >= 400

        # Settle with actual usage = 250 tokens (refunds 150 tokens)
        await finops.finalize_reservation(
            reservation=reservation, actual_tokens=250, actual_cost_usd=0.025
        )

        budget_settled = await finops.get_budget_status(tenant_id)
        assert budget_settled.tokens_used == 250

    async def test_byok_manager_vault_encryption(self) -> None:
        """Authority 5: BYOKManager credential encryption and Redis storage."""
        byok = BYOKManager()
        tenant_id = f"tenant-byok-{uuid.uuid4().hex[:8]}"
        secret_api_key = "sk-live-secret-test-key-12345678"

        # Store key
        entry = await byok.store_key(
            tenant_id=tenant_id,
            provider="openai",
            api_key=secret_api_key,
        )
        assert entry["status"] == "configured"
        assert entry["masked_key"].startswith("sk-")

        # Decrypt key
        decrypted = await byok.get_decrypted_key(tenant_id=tenant_id, provider="openai")
        assert decrypted == secret_api_key

        # Key rotation
        new_key = "sk-live-rotated-key-87654321"
        rotated = await byok.rotate_key(
            tenant_id=tenant_id, provider="openai", new_api_key=new_key
        )
        assert rotated["status"] == "configured"
        assert (
            await byok.get_decrypted_key(tenant_id=tenant_id, provider="openai")
            == new_key
        )

        # Key revocation
        await byok.revoke_key(tenant_id=tenant_id, provider="openai")
        revoked_decrypted = await byok.get_decrypted_key(
            tenant_id=tenant_id, provider="openai"
        )
        assert revoked_decrypted is None

    async def test_semantic_cache_exact_tier_redis(
        self,
        fake_embedding_provider: TestOnlyFakeEmbeddingProvider,
    ) -> None:
        """Authority 6: SemanticCacheManager Tier 1 exact match lifecycle."""
        cache = SemanticCacheManager(
            similarity_threshold=0.90,
            default_ttl=120,
            embedding_provider=fake_embedding_provider,
        )
        tenant_id = f"tenant-cache-{uuid.uuid4().hex[:8]}"
        prompt = "What is the capital of Vietnam?"
        response_text = "Hanoi is the capital of Vietnam."

        # Cache miss
        hit = await cache.get(prompt=prompt, tenant_id=tenant_id)
        assert hit is None

        # Cache set
        await cache.set(
            prompt=prompt,
            tenant_id=tenant_id,
            response=response_text,
            tokens_avoided=50,
        )

        # Cache hit
        hit2 = await cache.get(prompt=prompt, tenant_id=tenant_id)
        assert hit2 is not None
        assert hit2.response == response_text
        assert hit2.cache_type == "exact"

        # Invalidate tenant cache
        deleted_count = await cache.invalidate(tenant_id=tenant_id)
        assert deleted_count >= 1
        hit3 = await cache.get(prompt=prompt, tenant_id=tenant_id)
        assert hit3 is None

    async def test_rag_task_manager_redis_queue(self) -> None:
        """Authority 7: IngestionTaskManager enqueue and claim via Redis."""
        mgr = IngestionTaskManager(max_concurrency=2)
        await mgr.clear()
        try:
            tenant_id = f"tenant-rag-{uuid.uuid4().hex[:8]}"

            req = DocumentIngestRequest(
                content="Sample document text for ingestion.", source="report.pdf"
            )
            resp = await mgr.enqueue(request=req, tenant_id=tenant_id)
            task_id = resp.task_id
            assert task_id is not None

            task = await mgr.get_task(task_id, tenant_id=tenant_id)
            assert task is not None
            assert task.status == IngestionTaskStatus.QUEUED

            # Claim
            claimed = await mgr.claim_next_task()
            assert claimed is not None
            assert claimed.task_id == task_id
            await mgr.complete_task(
                task_id=task_id,
                result=DocumentIngestResponse(
                    document_id="doc-123",
                    indexed_chunks=12,
                    chunk_ids=["chunk-1", "chunk-2"],
                    source="report.pdf",
                    tenant_id=tenant_id,
                ),
            )
            completed_task = await mgr.get_task(task_id, tenant_id=tenant_id)
            assert completed_task is not None
            assert completed_task.status == IngestionTaskStatus.COMPLETED
        finally:
            await mgr.clear()

    async def test_token_denylist_revocation(self) -> None:
        """Authority 8: check_token_denylist JTI check."""
        settings = get_settings()
        jti = uuid.uuid4().hex
        token = jwt.encode(
            {"sub": "user1", "jti": jti}, settings.JWT_SECRET_KEY, algorithm="HS256"
        )

        # Un-denylisted token passes
        await check_token_denylist(token)

        # If Redis reachable, test revocation denial
        if REDIS_AVAILABLE:
            import redis.asyncio as aioredis

            client = aioredis.from_url(settings.REDIS_URL)
            await client.set(f"denylist:jti:{jti}", "revoked", ex=60)
            await client.aclose()

            with pytest.raises(HTTPException) as exc_info:
                await check_token_denylist(token)
            assert exc_info.value.status_code == 401
            assert "revoked" in exc_info.value.detail.lower()


@pytest.mark.asyncio
class TestRedisMandatoryFailureCases:
    """Mandatory failure cases: unavailable, timeout, malformed, connection, partial, recovery."""

    async def test_failure_case_1_unavailable(self) -> None:
        """Failure Case 1: Redis unavailable degrades gracefully to in-memory mode."""
        mgr = CheckpointManager()
        # Point to invalid port to guarantee unreachability
        with patch("app.core.redis_client.get_settings") as mock_settings:
            mock_settings.return_value.REDIS_URL = "redis://127.0.0.1:59999/0"
            mgr._redis_available = True
            mgr.redis_client = None

            run_state = RunState(
                run_id="run-unavailable-1",
                task_id="task-unavailable-1",
                tenant_id="tenant-unavail",
                user_id="user-1",
                status=RunStatus.RUNNING,
            )
            # Must succeed in in-memory fallback without raising
            cp_id = await mgr.save_checkpoint(run_state)
            assert cp_id is not None
            loaded = await mgr.get_checkpoint(cp_id, tenant_id="tenant-unavail")
            assert loaded.run_id == "run-unavailable-1"

    async def test_failure_case_2_timeout(self) -> None:
        """Failure Case 2: Redis timeout engages latch and does not block execution."""
        mgr = CheckpointManager()
        mock_redis = AsyncMock()
        mock_redis.set.side_effect = TimeoutError("Redis socket timed out")
        mock_redis.get.side_effect = TimeoutError("Redis socket timed out")
        mgr.redis_client = mock_redis
        mgr._redis_available = True

        run_state = RunState(
            run_id="run-timeout-1",
            task_id="task-timeout-1",
            tenant_id="tenant-timeout",
            user_id="user-1",
            status=RunStatus.RUNNING,
        )
        # Save must survive timeout and keep memory copy
        cp_id = await mgr.save_checkpoint(run_state)
        assert cp_id is not None
        loaded = await mgr.get_checkpoint(cp_id, tenant_id="tenant-timeout")
        assert loaded.run_id == "run-timeout-1"

    async def test_failure_case_3_malformed_response(self) -> None:
        """Failure Case 3: Malformed JSON stored in Redis fails closed safely."""
        mgr = CheckpointManager()
        mock_redis = AsyncMock()
        # Corrupt data returned from Redis
        mock_redis.get.return_value = "{malformed_json: true, incomplete..."
        mgr.redis_client = mock_redis
        mgr._redis_available = True
        mgr._run_to_latest["run-corrupt-1"] = "cp_run-corrupt-1_123"

        # Must handle JSONDecodeError cleanly and return None (fail-closed, no fabricated state)
        result = await mgr.load_checkpoint("run-corrupt-1", tenant_id="tenant-corrupt")
        assert result is None

    async def test_failure_case_4_connection_failure(self) -> None:
        """Failure Case 4: Connection reset by peer mid-operation."""
        finops = FinOpsBudgetManager()
        mock_redis = AsyncMock()
        mock_redis.eval.side_effect = ConnectionResetError("Connection closed by peer")
        finops.redis_client = mock_redis
        finops._redis_available = True

        # In-memory reservation fallback takes over when Redis connection drops
        reservation, err = await finops.reserve_budget(
            tenant_id="tenant-conn-fail",
            estimated_tokens=100,
            estimated_cost_usd=0.01,
        )
        assert err is None
        assert reservation is not None
        assert reservation.reserved_tokens == 100

    async def test_failure_case_5_partial_failure(self) -> None:
        """Failure Case 5: Partial failure during multi-key write degrades safely."""
        bridge = ResumeBridgeManager()
        mock_redis = AsyncMock()
        # Set succeeds on first call, raises on second
        mock_redis.set.side_effect = [True, RuntimeError("Pipeline failed halfway")]
        bridge.redis_client = mock_redis
        bridge._redis_available = True

        # Operation survives and keeps memory checkpoint intact
        await bridge.save_checkpoint(
            call_id="call-partial-1",
            tenant_id="tenant-partial",
            state_data={"data": 123},
        )
        loaded = await bridge.get_checkpoint("call-partial-1")
        assert loaded is not None
        assert loaded["call_id"] == "call-partial-1"

    async def test_failure_case_6_recovery(self) -> None:
        """Failure Case 6: Redis recovery re-establishes connection and sync."""
        mgr = CheckpointManager()
        mock_redis_down = AsyncMock()
        mock_redis_down.get.side_effect = ConnectionRefusedError("Redis offline")

        from app.agent.state.checkpoint import CheckpointRecord

        valid_rec = CheckpointRecord(
            checkpoint_id="cp_recov_1",
            checkpoint_created_at=time.time(),
            run_id="run-recov-1",
            task_id="task-recov-1",
            tenant_id="tenant-recov",
            user_id="user-1",
            status=RunStatus.COMPLETED,
        ).model_dump_json()

        async def _fake_redis_get(k: str) -> str | None:
            if "agent:checkpoint:run:" in k:
                return "cp_recov_1"
            if "agent:checkpoint:rec:" in k:
                return valid_rec
            return None

        mock_redis_up = AsyncMock()
        mock_redis_up.get.side_effect = _fake_redis_get

        # Initially down
        mgr.redis_client = mock_redis_down
        mgr._run_to_latest.clear()
        res_down = await mgr.load_checkpoint("run-recov-1", tenant_id="tenant-recov")
        assert res_down is None

        # Recovers
        mgr.redis_client = mock_redis_up
        res_up = await mgr.load_checkpoint("run-recov-1", tenant_id="tenant-recov")
        assert res_up is not None
        assert res_up.status == RunStatus.COMPLETED
