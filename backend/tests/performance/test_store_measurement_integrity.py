"""Invalid useful work must not become a fast successful benchmark sample."""

from unittest.mock import AsyncMock

import pytest

from app.performance.scenarios import qdrant_scenario, redis_contention_scenario
from app.rag.models import DocumentChunk


@pytest.mark.asyncio
@pytest.mark.parametrize("problem", ["valid", "empty", "foreign", "fallback"])
async def test_vector_measurement_rejects_missing_foreign_or_fallback_work(
    monkeypatch, problem
):
    class Store:
        dimension = 384
        _is_qdrant_available = True

        def __init__(self, **kwargs):
            self._client = self

        async def _get_client(self):
            return self

        async def upsert(self, chunks):
            pass

        async def search(self, **kwargs):
            if problem == "empty":
                return []
            if problem == "fallback":
                self._is_qdrant_available = False
            tenant = "foreign" if problem == "foreign" else kwargs["tenant_id"]
            return [
                DocumentChunk(chunk_id=str(i), content="synthetic", tenant_id=tenant)
                for i in range(3)
            ]

        async def close(self):
            pass

    monkeypatch.setattr(qdrant_scenario, "QdrantVectorStore", Store)
    monkeypatch.setattr(qdrant_scenario, "_is_qdrant_online", lambda: True)
    result = await qdrant_scenario.run_concurrent_qdrant_scenario(
        concurrency=2, total_operations=3
    )
    assert result.success_count == (3 if problem == "valid" else 0)
    assert result.error_count == (0 if problem == "valid" else 3)
    assert result.error_rate_pct == (0 if problem == "valid" else 100)


@pytest.mark.asyncio
async def test_denied_budget_cannot_count_as_successful_contention_work(monkeypatch):
    monkeypatch.setattr(
        redis_contention_scenario, "acquire_redis_client", AsyncMock(return_value=None)
    )
    monkeypatch.setattr(
        redis_contention_scenario.FinOpsBudgetManager,
        "reserve_budget",
        AsyncMock(return_value=(None, "denied")),
    )
    result = await redis_contention_scenario.run_redis_contention_scenario(
        concurrency=2, total_operations=4
    )
    assert result.success_count == 0
    assert result.error_count == 4
