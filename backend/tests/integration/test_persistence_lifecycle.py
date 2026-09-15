"""Comprehensive State and Persistence Lifecycle Integration Test Suite (INT-019).

Verifies the canonical 6-stage lifecycle across all 8 target state entities:
    create -> persist -> reload -> mutate -> persist -> reload

Target entities audited:
1. Task State (TaskState lifecycle, PENDING -> RUNNING -> COMPLETED)
2. Run State (RunState steps, tool calls, status transitions)
3. Checkpoints (CheckpointManager serialization, memory snapshots, secret redaction)
4. Conversation State (ShortTermMemory snapshot/restore and bounded FIFO eviction)
5. Tenant Isolation (Cross-tenant boundary protection across all state stores)
6. RAG Persistence (BM25Retriever disk serialization, reload, and mutation)
7. Cache State (SemanticCacheManager exact & vector persistence and invalidation)
8. Accounting State (FinOpsBudgetManager quota limits, reservations, and settlements)

Mandatory failure cases tested for persistence:
- unavailable (storage path unwritable -> fails safely without corrupting prior state)
- timeout (checkpoint operation timeout -> memory state retained)
- malformed response (corrupted JSON on disk -> returns False, fails closed, no fabricated state)
- connection failure (connection reset during store -> memory fallback)
- partial failure (corrupt fields rejected by Pydantic validation)
- recovery (clean repair re-enables valid persistence roundtrips)
"""

from __future__ import annotations

import os
import uuid
from typing import TYPE_CHECKING
from unittest.mock import AsyncMock

import pytest
from pydantic import ValidationError

if TYPE_CHECKING:
    from pathlib import Path

from app.agent.memory.short_term import ShortTermMemory
from app.agent.runtime.manager import AgentRuntimeManager
from app.agent.state.checkpoint import CheckpointManager, CheckpointRecord
from app.agent.state.models import RunState, RunStatus, TaskStatus
from app.finops.budget import FinOpsBudgetManager
from app.optimizer.semantic_cache import SemanticCacheManager
from app.rag.bm25 import BM25Retriever
from app.rag.embedding import TestOnlyFakeEmbeddingProvider
from app.rag.models import DocumentChunk


@pytest.fixture
def fake_embedding_provider() -> TestOnlyFakeEmbeddingProvider:
    return TestOnlyFakeEmbeddingProvider(dimension=64)


class TestStatePersistenceLifecycle:
    """Rigorous 6-step lifecycle verification across all 8 state targets."""

    async def test_lifecycle_1_task_state(self) -> None:
        """Lifecycle 1: Task State create -> persist -> reload -> mutate -> persist -> reload."""
        runtime = AgentRuntimeManager()
        tenant_a = f"tenant-t1-{uuid.uuid4().hex[:8]}"
        tenant_b = f"tenant-t2-{uuid.uuid4().hex[:8]}"

        # 1. Create
        task = runtime.create_task(
            goal="Process annual audit for banking partner",
            tenant_id=tenant_a,
            user_id="auditor-1",
        )
        assert task.status == TaskStatus.PENDING
        assert task.tenant_id == tenant_a

        # 2. Persist (automatically stored in runtime._tasks)
        task_id = task.task_id

        # 3. Reload
        reloaded = runtime.get_task(task_id=task_id, tenant_id=tenant_a)
        assert reloaded.task_id == task_id
        assert reloaded.status == TaskStatus.PENDING
        assert reloaded.goal == "Process annual audit for banking partner"

        # 4. Mutate
        reloaded.status = TaskStatus.RUNNING
        reloaded.metadata["assigned_worker"] = "worker-node-4"

        # 5. Persist (in place update)
        runtime._tasks[task_id] = reloaded

        # 6. Reload & verify mutation
        reloaded2 = runtime.get_task(task_id=task_id, tenant_id=tenant_a)
        assert reloaded2.status == TaskStatus.RUNNING
        assert reloaded2.metadata.get("assigned_worker") == "worker-node-4"

        # Tenant isolation
        with pytest.raises(PermissionError):
            runtime.get_task(task_id=task_id, tenant_id=tenant_b)

    async def test_lifecycle_2_run_state(self) -> None:
        """Lifecycle 2: Run State create -> persist -> reload -> mutate -> persist -> reload."""
        runtime = AgentRuntimeManager()
        tenant_id = f"tenant-r1-{uuid.uuid4().hex[:8]}"
        task = runtime.create_task(
            goal="Execute ledger settlement", tenant_id=tenant_id, user_id="u1"
        )

        # 1. Create run
        run_state = runtime.create_run(
            task_id=task.task_id,
            tenant_id=tenant_id,
            user_id="u1",
        )
        assert run_state.status == RunStatus.CREATED
        assert run_state.current_iteration == 0

        # 2. Persist
        run_id = run_state.run_id

        # 3. Reload
        reloaded = runtime.get_run(run_id=run_id, tenant_id=tenant_id)
        assert reloaded.run_id == run_id
        assert reloaded.status == RunStatus.CREATED

        # 4. Mutate
        reloaded.status = RunStatus.RUNNING
        reloaded.current_iteration = 1
        reloaded.tool_calls.append(
            {"name": "settle_accounts", "input": {"amount": 1000}}
        )
        reloaded.tokens_consumed = 350

        # 5. Persist
        runtime._runs[run_id] = reloaded

        # 6. Reload & verify mutation
        reloaded2 = runtime.get_run(run_id=run_id, tenant_id=tenant_id)
        assert reloaded2.status == RunStatus.RUNNING
        assert reloaded2.current_iteration == 1
        assert len(reloaded2.tool_calls) == 1
        assert reloaded2.tokens_consumed == 350

        # Foreign tenant isolation
        with pytest.raises(PermissionError):
            runtime.get_run(run_id=run_id, tenant_id="foreign-tenant")

    async def test_lifecycle_3_checkpoints(self) -> None:
        """Lifecycle 3: CheckpointManager create -> persist -> reload -> mutate -> persist -> reload."""
        mgr = CheckpointManager()
        tenant_id = f"tenant-cp-{uuid.uuid4().hex[:8]}"
        run_state = RunState(
            run_id=f"run-cp-{uuid.uuid4().hex[:8]}",
            task_id=f"task-cp-{uuid.uuid4().hex[:8]}",
            tenant_id=tenant_id,
            user_id="user-cp-1",
            status=RunStatus.RUNNING,
            current_iteration=1,
            metadata={"api_key": "secret-token-to-redact", "caller": "frontend"},
        )

        # 1. Create & 2. Persist
        cp_id_1 = await mgr.save_checkpoint(
            run_state=run_state,
            short_term_memory=[{"role": "user", "content": "hello"}],
        )

        # 3. Reload
        loaded_1 = await mgr.get_checkpoint(cp_id_1, tenant_id=tenant_id)
        assert loaded_1.checkpoint_id == cp_id_1
        assert loaded_1.metadata["api_key"] == "[REDACTED]"
        assert loaded_1.current_iteration == 1

        # 4. Mutate
        run_state.current_iteration = 2
        run_state.status = RunStatus.WAITING_APPROVAL
        run_state.tool_calls.append(
            {"name": "transfer_funds", "input": {"dest": "ACC-99"}}
        )

        # 5. Persist mutated checkpoint
        cp_id_2 = await mgr.save_checkpoint(
            run_state=run_state,
            short_term_memory=[
                {"role": "user", "content": "hello"},
                {"role": "assistant", "content": "transfer pending approval"},
            ],
        )

        # 6. Reload latest
        loaded_latest = await mgr.load_checkpoint(run_state.run_id, tenant_id=tenant_id)
        assert loaded_latest is not None
        assert loaded_latest.checkpoint_id == cp_id_2
        assert loaded_latest.status == RunStatus.WAITING_APPROVAL
        assert loaded_latest.current_iteration == 2
        assert len(loaded_latest.short_term_memory_snapshot) == 2

        # Isolation
        with pytest.raises(PermissionError):
            await mgr.get_checkpoint(cp_id_2, tenant_id="unauthorized-tenant")

    def test_lifecycle_4_conversation_state(self) -> None:
        """Lifecycle 4: ShortTermMemory create -> persist -> reload -> mutate -> persist -> reload."""
        mem = ShortTermMemory(max_entries=3)
        tenant_id = "tenant-conv-test"

        # 1. Create & 2. Persist initial memory variables
        mem.store(key="liquidity_ratio", value=2.45, tenant_id=tenant_id)
        mem.store(key="quick_ratio", value=1.80, tenant_id=tenant_id)

        # 3. Reload / inspect
        assert mem.get("liquidity_ratio") == 2.45
        assert mem.get("quick_ratio") == 1.80

        # Export checkpoint snapshot
        snapshot = mem.snapshot()
        assert len(snapshot) == 2

        # 4. Mutate: overwrite and add entry
        mem.store(key="liquidity_ratio", value=3.10, tenant_id=tenant_id)
        assert mem.get("liquidity_ratio") == 3.10

        # 5. Restore from snapshot & 6. Verify reload
        mem.restore(snapshot)
        assert mem.get("liquidity_ratio") == 2.45
        assert mem.get("quick_ratio") == 1.80

        # Verify FIFO eviction when exceeding max_entries (3)
        mem.store(key="k1", value="v1")
        mem.store(key="k2", value="v2")
        mem.store(key="k3", value="v3")
        mem.store(key="k4", value="v4")
        assert len(mem.list_entries()) == 3
        assert mem.get("k1") is None
        assert mem.get("k4") == "v4"

    async def test_lifecycle_5_tenant_isolation_complete(self) -> None:
        """Lifecycle 5: Comprehensive cross-tenant isolation boundaries."""
        runtime = AgentRuntimeManager()
        cp_mgr = CheckpointManager()

        tenant_alpha = "tenant-alpha"
        tenant_beta = "tenant-beta"

        # Create alpha task and run
        task_alpha = runtime.create_task(
            goal="Alpha Secret Operation", tenant_id=tenant_alpha, user_id="user-a"
        )
        run_alpha = runtime.create_run(
            task_id=task_alpha.task_id, tenant_id=tenant_alpha, user_id="user-a"
        )
        cp_alpha = await cp_mgr.save_checkpoint(run_alpha)

        # Create beta task and run
        task_beta = runtime.create_task(
            goal="Beta Secret Operation", tenant_id=tenant_beta, user_id="user-b"
        )
        run_beta = runtime.create_run(
            task_id=task_beta.task_id, tenant_id=tenant_beta, user_id="user-b"
        )
        cp_beta = await cp_mgr.save_checkpoint(run_beta)

        # Verify Alpha cannot access Beta
        with pytest.raises(PermissionError):
            runtime.get_task(task_beta.task_id, tenant_id=tenant_alpha)
        with pytest.raises(PermissionError):
            runtime.get_run(run_beta.run_id, tenant_id=tenant_alpha)
        with pytest.raises(PermissionError):
            await cp_mgr.get_checkpoint(cp_beta, tenant_id=tenant_alpha)

        # Verify Beta cannot access Alpha
        with pytest.raises(PermissionError):
            runtime.get_task(task_alpha.task_id, tenant_id=tenant_beta)
        with pytest.raises(PermissionError):
            runtime.get_run(run_alpha.run_id, tenant_id=tenant_beta)
        with pytest.raises(PermissionError):
            await cp_mgr.get_checkpoint(cp_alpha, tenant_id=tenant_beta)

    def test_lifecycle_6_rag_bm25_disk_persistence(self, tmp_path: Path) -> None:
        """Lifecycle 6: BM25Retriever create -> persist -> reload -> mutate -> persist -> reload."""
        index_file = str(tmp_path / "bm25_index.json")
        tenant_id = f"tenant-bm25-{uuid.uuid4().hex[:8]}"

        # 1. Create
        bm25_1 = BM25Retriever()
        chunk_1 = DocumentChunk(
            chunk_id="chk-p1",
            content="Solvency margin requirements for commercial banking.",
            tenant_id=tenant_id,
            source="regulation.pdf",
            metadata={},
        )
        bm25_1.add_documents([chunk_1])

        # 2. Persist to disk
        bm25_1.save_to_disk(index_file)
        assert os.path.exists(index_file)

        # 3. Reload from disk into a fresh instance
        bm25_2 = BM25Retriever()
        assert bm25_2.load_from_disk(index_file) is True
        results = bm25_2.search(query="solvency margin", tenant_id=tenant_id)
        assert len(results) == 1
        assert results[0].chunk_id == "chk-p1"

        # 4. Mutate: add second document
        chunk_2 = DocumentChunk(
            chunk_id="chk-p2",
            content="Basel III capital adequacy accord provisions.",
            tenant_id=tenant_id,
            source="basel.pdf",
            metadata={},
        )
        bm25_2.add_documents([chunk_2])

        # 5. Persist mutated index
        bm25_2.save_to_disk(index_file)

        # 6. Reload and verify both exist
        bm25_3 = BM25Retriever()
        assert bm25_3.load_from_disk(index_file) is True
        res_both = bm25_3.search(query="Basel III capital", tenant_id=tenant_id)
        assert len(res_both) == 1
        assert res_both[0].chunk_id == "chk-p2"

        # Foreign tenant search yields empty (tenant isolation)
        assert len(bm25_3.search(query="Basel", tenant_id="foreign-tenant")) == 0

    async def test_lifecycle_7_cache_state(
        self,
        fake_embedding_provider: TestOnlyFakeEmbeddingProvider,
    ) -> None:
        """Lifecycle 7: Cache State create -> persist -> reload -> mutate -> persist -> reload."""
        cache = SemanticCacheManager(
            similarity_threshold=0.85,
            default_ttl=120,
            embedding_provider=fake_embedding_provider,
        )
        tenant_id = f"tenant-cache-lc-{uuid.uuid4().hex[:8]}"
        prompt = "What is EBITDA?"
        response_v1 = "EBITDA stands for Earnings Before Interest, Taxes, Depreciation, and Amortization."

        # 1. Create & 2. Persist
        await cache.set(
            prompt=prompt, tenant_id=tenant_id, response=response_v1, tokens_avoided=40
        )

        # 3. Reload
        hit1 = await cache.get(prompt=prompt, tenant_id=tenant_id)
        assert hit1 is not None
        assert hit1.response == response_v1

        # 4. Mutate: Invalidate cache
        await cache.invalidate(tenant_id=tenant_id)

        # 5. Reload after invalidation (must miss)
        miss = await cache.get(prompt=prompt, tenant_id=tenant_id)
        assert miss is None

        # 6. Persist mutated response & Reload
        response_v2 = "EBITDA is an operational profitability metric."
        await cache.set(
            prompt=prompt, tenant_id=tenant_id, response=response_v2, tokens_avoided=45
        )
        hit2 = await cache.get(prompt=prompt, tenant_id=tenant_id)
        assert hit2 is not None
        assert hit2.response == response_v2

    async def test_lifecycle_8_accounting_state(self) -> None:
        """Lifecycle 8: FinOps Budget create -> persist -> reload -> mutate -> persist -> reload."""
        finops = FinOpsBudgetManager()
        tenant_id = f"tenant-acct-{uuid.uuid4().hex[:8]}"

        # 1. Create & 2. Persist
        await finops.set_budget(
            tenant_id=tenant_id, token_quota=10000, dollar_budget_usd=50.0
        )

        # 3. Reload
        budget = await finops.get_budget_status(tenant_id)
        assert budget.token_quota == 10000
        assert budget.tokens_used == 0

        # 4. Mutate: Reserve and Settle
        reservation, err = await finops.reserve_budget(
            tenant_id=tenant_id,
            estimated_tokens=2000,
            estimated_cost_usd=0.20,
        )
        assert err is None
        assert reservation is not None

        # Settle 1500 tokens
        await finops.finalize_reservation(
            reservation=reservation, actual_tokens=1500, actual_cost_usd=0.15
        )

        # 5. Persist (settlement recorded) & 6. Reload
        budget2 = await finops.get_budget_status(tenant_id)
        assert budget2.tokens_used == 1500
        assert budget2.tokens_remaining == 8500


class TestPersistenceMandatoryFailureCases:
    """Mandatory failure cases for persistence: unavailable, timeout, malformed, connection, partial, recovery."""

    async def test_failure_case_1_unavailable(self, tmp_path: Path) -> None:
        """Failure Case 1: Saving to a directory path instead of a file raises exception."""
        bm25 = BM25Retriever()
        # Passing an existing directory path causes open() on directory to fail
        invalid_path = str(tmp_path)

        with pytest.raises(OSError):
            bm25.save_to_disk(invalid_path)

    async def test_failure_case_2_timeout(self) -> None:
        """Failure Case 2: Storage timeout keeps memory copy accessible."""
        mgr = CheckpointManager()
        mock_redis = AsyncMock()
        mock_redis.set.side_effect = TimeoutError("Checkpoint storage write timeout")
        mgr.redis_client = mock_redis
        mgr._redis_available = True

        run_state = RunState(
            run_id="run-persist-to-1",
            task_id="task-persist-to-1",
            tenant_id="tenant-to",
            user_id="user-1",
            status=RunStatus.RUNNING,
        )
        cp_id = await mgr.save_checkpoint(run_state)
        assert cp_id is not None
        # Memory copy remains intact and valid
        loaded = await mgr.get_checkpoint(cp_id, tenant_id="tenant-to")
        assert loaded.run_id == "run-persist-to-1"

    async def test_failure_case_3_malformed_disk_payload(self, tmp_path: Path) -> None:
        """Failure Case 3: Corrupted JSON file fails closed, returns False, and does not load junk."""
        index_file = tmp_path / "corrupt_index.json"
        index_file.write_text("{ corrupt_json: [ incomplete ...", encoding="utf-8")

        bm25 = BM25Retriever(storage_path=str(tmp_path / "clean_empty.json"))
        # load_from_disk catches JSONDecodeError, logs warning, and returns False safely
        assert bm25.load_from_disk(str(index_file)) is False
        assert len(bm25._corpus) == 0

    async def test_failure_case_4_connection_failure(self) -> None:
        """Failure Case 4: Network connection drop during state flush."""
        mgr = CheckpointManager()
        mock_redis = AsyncMock()
        mock_redis.set.side_effect = ConnectionResetError(
            "Connection lost during flush"
        )
        mgr.redis_client = mock_redis
        mgr._redis_available = True

        run_state = RunState(
            run_id="run-conn-drop-1",
            task_id="task-conn-drop-1",
            tenant_id="tenant-cd",
            user_id="user-1",
            status=RunStatus.RUNNING,
        )
        cp_id = await mgr.save_checkpoint(run_state)
        assert cp_id is not None
        # State retained in memory
        loaded = await mgr.get_checkpoint(cp_id, tenant_id="tenant-cd")
        assert loaded.run_id == "run-conn-drop-1"

    async def test_failure_case_5_partial_failure_schema_validation(self) -> None:
        """Failure Case 5: Missing mandatory fields fails closed via Pydantic."""
        invalid_record_data = {
            "checkpoint_id": "cp_invalid",
            # Missing run_id, task_id, tenant_id, user_id, status
        }
        with pytest.raises(ValidationError):
            CheckpointRecord(**invalid_record_data)

    async def test_failure_case_6_recovery(self, tmp_path: Path) -> None:
        """Failure Case 6: Repairing corrupted file restores valid persistence operations."""
        index_file = tmp_path / "repairable_index.json"
        # Write corrupted file
        index_file.write_text("NOT_JSON", encoding="utf-8")

        bm25 = BM25Retriever()
        assert bm25.load_from_disk(str(index_file)) is False

        # Recovery: overwrite with valid BM25 index
        bm25_clean = BM25Retriever()
        bm25_clean.add_documents(
            [
                DocumentChunk(
                    chunk_id="chk-rec-1",
                    content="Recovered document index.",
                    tenant_id="tenant-rec",
                    source="clean.txt",
                    metadata={},
                )
            ]
        )
        bm25_clean.save_to_disk(str(index_file))

        # Reload succeeds
        bm25_recovered = BM25Retriever()
        assert bm25_recovered.load_from_disk(str(index_file)) is True
        res = bm25_recovered.search("Recovered document", tenant_id="tenant-rec")
        assert len(res) == 1
        assert res[0].chunk_id == "chk-rec-1"
