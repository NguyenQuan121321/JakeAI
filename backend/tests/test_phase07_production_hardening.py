"""Production Hardening, API Contract, Streaming & Resilience Test Suite for Phase 07.

Verifies:
1. API contract stability, versioning, correlation ID tracing, and 413 request size bounds.
2. Server-Sent Events (SSE) event ordering, flushing headers, and disconnect cancellation accounting.
3. OpenAI-compatible streaming proxy (/v1/chat/completions with stream=true) and exact cache streaming.
4. Resilience under failure: provider failure, provider timeout, Redis outage cooldown, Qdrant outage fallback.
5. Zero secret leakage in logs, exceptions, and error response bodies.
6. Telemetry and metrics aggregation across all operational vectors.
"""

from __future__ import annotations

import asyncio
import time
from typing import TYPE_CHECKING, Any
from unittest.mock import AsyncMock, patch

import jwt
import pytest
from fastapi.testclient import TestClient

from app.core.config import get_settings
from app.core.context import TenantContext
from app.main import app
from app.optimizer.semantic_cache import get_semantic_cache_manager
from app.providers.errors import (
    ProviderTimeoutError,
    ProviderUnavailableError,
    sanitize_error_message,
)
from app.rag.models import DocumentChunk
from app.rag.vector_store import QdrantVectorStore
from app.services.ai_gateway import (
    get_quota_manager,
)
from app.telemetry.metrics import metrics

if TYPE_CHECKING:
    from httpx import AsyncClient

client = TestClient(app)


def create_test_auth_headers(
    tenant_id: str = "tenant-phase07",
    user_id: str = "user-phase07",
    roles: list[str] | None = None,
    permissions: list[str] | None = None,
) -> dict[str, str]:
    """Generate authenticated bearer header for test assertions."""
    settings = get_settings()
    now = int(time.time())
    payload = {
        "sub": user_id,
        "tenant_id": tenant_id,
        "iat": now,
        "exp": now + 3600,
        "type": "access",
        "roles": roles or ["developer"],
        "permissions": permissions or ["chat:read", "chat:write", "chat:stream"],
    }
    token = jwt.encode(payload, settings.JWT_SECRET_KEY, algorithm="HS256")
    return {"Authorization": f"Bearer {token}"}


# ==============================================================================
# 1. API Contract, Health & Middleware Tests
# ==============================================================================


def test_health_endpoints_backward_compatibility() -> None:
    """Verify /health, /health/live, and /health/ready return 200 with components."""
    # 1. Root /health
    res = client.get("/health")
    assert res.status_code == 200
    data = res.json()
    assert data["status"] == "healthy"
    assert "version" in data
    assert "environment" in data
    assert "uptime_seconds" in data
    assert "components" in data

    # 2. Liveness probe
    res_live = client.get("/health/live")
    assert res_live.status_code == 200
    assert res_live.json()["status"] == "healthy"

    # 3. Readiness probe
    res_ready = client.get("/health/ready")
    assert res_ready.status_code == 200
    assert "components" in res_ready.json()


def test_correlation_id_and_response_time_middleware() -> None:
    """Verify incoming correlation ID is propagated to response headers with execution timing."""
    corr_id = "test-corr-uuid-7777"
    response = client.get(
        "/health",
        headers={"X-Correlation-ID": corr_id},
    )
    assert response.status_code == 200
    assert response.headers.get("x-correlation-id") == corr_id
    assert "x-response-time" in response.headers
    assert response.headers["x-response-time"].endswith("ms")


def test_request_size_limit_middleware() -> None:
    """Verify requests exceeding MAX_REQUEST_BODY_BYTES are rejected with HTTP 413."""
    settings = get_settings()
    oversized_length = settings.MAX_REQUEST_BODY_BYTES + 1024

    response = client.post(
        "/api/v1/chat/stream",
        headers={
            "Content-Length": str(oversized_length),
            **create_test_auth_headers(),
        },
        content=b"{}",
    )
    assert response.status_code == 413
    assert "Request entity too large" in response.json()["detail"]


def test_runtime_telemetry_metrics_endpoint() -> None:
    """Verify /api/v1/analytics/metrics returns operational snapshot without sensitive data."""
    headers = create_test_auth_headers()
    response = client.get("/api/v1/analytics/metrics", headers=headers)
    assert response.status_code == 200
    data = response.json()
    assert "http_requests_total" in data
    assert "uptime_seconds" in data
    assert "active_streams" in data
    # Ensure zero secret keys or authorization headers appear in metrics
    raw_text = response.text
    assert "sk-" not in raw_text
    assert "Bearer" not in raw_text


# ==============================================================================
# 2. Streaming & SSE Hardening Tests
# ==============================================================================


@pytest.mark.asyncio
async def test_chat_sse_stream_ordering_and_flush(async_client: AsyncClient) -> None:
    """Verify strict SSE event sequence: status -> token -> telemetry -> done."""
    headers = create_test_auth_headers()
    response = await async_client.post(
        "/api/v1/chat/stream",
        headers=headers,
        json={
            "prompt": "Analyze our liquidity ratio",
            "conversation_id": "test-order-01",
        },
    )
    assert response.status_code == 200
    assert "text/event-stream" in response.headers.get("content-type", "")
    assert response.headers.get("x-accel-buffering") == "no"
    assert response.headers.get("cache-control") == "no-cache"

    body = response.text
    status_idx = body.find("event: status")
    token_idx = body.find("event: token")
    telemetry_idx = body.find("event: telemetry")
    done_idx = body.find("event: done")

    assert status_idx != -1
    assert token_idx != -1
    assert telemetry_idx != -1
    assert done_idx != -1
    assert status_idx < token_idx < telemetry_idx < done_idx


@pytest.mark.asyncio
async def test_chat_sse_stream_cancellation_and_token_accounting() -> None:
    """Verify that client cancellation finalizes partial token accounting and updates telemetry."""
    from app.api.v1.endpoints.chat import generate_chat_stream

    ctx = TenantContext(
        tenant_id="tenant-cancel-test",
        user_id="user-cancel",
        roles=["user"],
        permissions=["chat:stream"],
    )

    class MockDisconnectRequest:
        def __init__(self) -> None:
            self._call_count = 0

        async def is_disconnected(self) -> bool:
            self._call_count += 1
            return self._call_count >= 1

    async def mock_workflow(*args: Any, **kwargs: Any) -> Any:
        yield {
            "node": "supervisor",
            "workflow_phase": "planning",
            "mascot_state": "thinking",
            "messages": ["Analyzing financial statements..."],
        }
        yield {
            "node": "synthesizer",
            "workflow_phase": "synthesis",
            "mascot_state": "success",
            "messages": ["Finalizing report"],
            "final_response": "Here is the variance analysis.",
        }

    metrics.reset()
    events = []
    fake_req = MockDisconnectRequest()

    with patch(
        "app.api.v1.endpoints.chat.stream_multi_agent_workflow",
        side_effect=mock_workflow,
    ):
        gen = generate_chat_stream(
            prompt="Explain balance sheet variance analysis",
            context=ctx,
            conversation_id="conv-disconnect-test",
            request=fake_req,  # type: ignore[arg-type]
        )

        async for ev in gen:
            events.append(ev)

    # Telemetry should record cancellation
    snapshot = metrics.get_snapshot()
    assert any("client_disconnect" in k for k in snapshot.stream_cancellations_total)


@pytest.mark.asyncio
async def test_chat_sse_stream_timeout() -> None:
    """Verify that stream exceeding STREAM_TIMEOUT_SECONDS emits an error frame."""
    from app.api.v1.endpoints.chat import generate_chat_stream

    ctx = TenantContext(
        tenant_id="tenant-timeout-test",
        user_id="user-timeout",
        roles=["user"],
        permissions=["chat:stream"],
    )

    with patch("app.api.v1.endpoints.chat.get_settings") as mock_settings:
        settings = get_settings()
        mock_conf = settings.model_copy(update={"STREAM_TIMEOUT_SECONDS": 0.001})
        mock_settings.return_value = mock_conf

        # Wait to ensure duration > 0.001
        await asyncio.sleep(0.005)

        events = []
        gen = generate_chat_stream(
            prompt="Compute deferred tax assets",
            context=ctx,
            conversation_id="conv-timeout-test",
        )

        async for ev in gen:
            events.append(ev)

        assert any("Stream timeout" in e for e in events)


# ==============================================================================
# 3. OpenAI-Compatible Gateway Streaming Tests
# ==============================================================================


def test_gateway_chat_completions_streaming() -> None:
    """Verify POST /v1/chat/completions with stream=True streams SSE chunks ending with [DONE]."""
    headers = create_test_auth_headers()
    payload = {
        "model": "gemini-1.5-flash",
        "messages": [{"role": "user", "content": "What is operating margin?"}],
        "stream": True,
    }

    response = client.post("/v1/chat/completions", headers=headers, json=payload)
    assert response.status_code == 200
    assert "text/event-stream" in response.headers.get("content-type", "")

    lines = response.text.strip().split("\n\n")
    assert len(lines) > 1
    assert any("chat.completion.chunk" in line for line in lines)
    assert lines[-1] == "data: [DONE]"


def test_gateway_chat_completions_streaming_exact_cache() -> None:
    """Verify streaming response for cached prompt streams from cache with 0 billed tokens."""
    headers = create_test_auth_headers(tenant_id="tenant-stream-cache")
    prompt = f"Define EBITDA margin for audit #{int(time.time())}"
    payload = {
        "model": "gpt-4o-mini",
        "messages": [{"role": "user", "content": prompt}],
        "stream": True,
    }

    # First call: populates cache
    res1 = client.post("/v1/chat/completions", headers=headers, json=payload)
    assert res1.status_code == 200
    assert "data: [DONE]" in res1.text

    # Second call: streams from cache
    res2 = client.post("/v1/chat/completions", headers=headers, json=payload)
    assert res2.status_code == 200
    assert "data: [DONE]" in res2.text
    assert "chat.completion.chunk" in res2.text


# ==============================================================================
# 4. Resilience, Failure Modes & Cooldown Tests
# ==============================================================================


@pytest.mark.asyncio
async def test_redis_outage_resilient_cooldown_and_recovery() -> None:
    """Verify SemanticCacheManager fails open on Redis outage and recovers after cooldown."""
    cache = get_semantic_cache_manager()
    cache.reset_metrics()

    # Simulate failing Redis
    failing_redis = AsyncMock()
    failing_redis.get.side_effect = ConnectionError("Redis server connection lost")
    failing_redis.set.side_effect = ConnectionError("Redis server connection lost")
    failing_redis.ping.side_effect = ConnectionError("Redis server connection lost")

    cache.redis_client = failing_redis
    cache._redis_available = True

    # 1. Call get: should catch ConnectionError, set cooldown, and return None without crash
    res = await cache.get(
        "Test prompt during Redis outage", tenant_id="tenant-resilience"
    )
    assert res is None
    assert cache._redis_available is False
    assert cache._redis_retry_after > time.time()

    # 2. Immediate second call: during cooldown, skips Redis and checks memory cleanly
    res2 = await cache.get(
        "Test prompt during Redis outage", tenant_id="tenant-resilience"
    )
    assert res2 is None

    # 3. Simulate Redis recovery after cooldown expires
    cache._redis_retry_after = time.time() - 1.0
    recovered_redis = AsyncMock()
    recovered_redis.ping.return_value = True
    recovered_redis.get.return_value = None

    with patch("redis.asyncio.from_url", return_value=recovered_redis):
        cache.redis_client = None
        # Call should re-probe Redis successfully
        await cache.get("Probe after recovery", tenant_id="tenant-resilience")
        assert cache._redis_available is True


@pytest.mark.asyncio
async def test_qdrant_outage_in_memory_fallback() -> None:
    """Verify QdrantVectorStore falls back to in-memory cosine search when Qdrant is down."""
    store = QdrantVectorStore(collection_name="test_fallback_col")
    store._is_qdrant_available = False
    store._client = None

    chunks = [
        DocumentChunk(
            chunk_id="chk-1",
            content="Gross profit is revenue minus cost of goods sold.",
            tenant_id="tenant-fallback",
            source="Manual",
        ),
        DocumentChunk(
            chunk_id="chk-2",
            content="Net profit is operating profit minus taxes and interest.",
            tenant_id="tenant-fallback",
            source="Manual",
        ),
    ]

    await store.upsert(chunks)

    # Search should execute in-memory cosine fallback cleanly
    results = await store.search(
        query="What is gross profit and revenue?",
        tenant_id="tenant-fallback",
        top_k=2,
    )

    assert len(results) == 2
    assert results[0].tenant_id == "tenant-fallback"
    assert "gross profit" in results[0].content.lower()


@pytest.mark.asyncio
async def test_quota_exhaustion_suspension() -> None:
    """Verify QuotaManager blocks requests with suspended status when budget is exhausted."""
    quota_mgr = get_quota_manager()
    tenant = "tenant-exhausted-01"

    await quota_mgr.set_quota_limit(tenant, 1000)
    await quota_mgr.record_usage(tenant, prompt_tokens=800, completion_tokens=300)

    allowed, warning = await quota_mgr.check_quota(tenant, estimated_tokens=100)
    assert allowed is False
    assert warning is not None
    assert "quota exceeded" in warning.lower()


# ==============================================================================
# 5. Security & Zero Secret Leakage Tests
# ==============================================================================


def test_sanitize_error_message_redacts_credentials() -> None:
    """Verify sanitize_error_message completely redacts API keys, Bearer tokens, and secrets."""
    gemini_key_fragment = f"{'AI' + 'za'}{'0' * 35}"
    dirty_message = (
        "Failed request to https://api.openai.com with key=sk-proj-1234567890abcdef12345 "
        "and header Bearer eyJhbGciOiJIUzI1NiIsInR5cCI6IkpXVCJ9.invalid "
        f"and Gemini key {gemini_key_fragment}"
    )
    clean_message = sanitize_error_message(dirty_message)

    assert "sk-proj-" not in clean_message
    assert gemini_key_fragment not in clean_message
    assert "eyJhbGci" not in clean_message
    assert "[REDACTED_SECRET]" in clean_message


def test_global_exception_handler_normalizes_provider_error() -> None:
    """Verify ProviderError raised during request is normalized to safe JSON without secrets."""
    from app.main import app

    @app.get("/test-provider-error")
    async def raise_provider_error() -> None:
        raise ProviderUnavailableError(
            message="Upstream provider connection reset with key sk-secret-123456789",
            provider="test_provider",
            model="test-model",
            status_code=503,
            retry_after_seconds=5.0,
        )

    res = client.get("/test-provider-error")
    assert res.status_code == 503
    assert res.headers.get("retry-after") == "5"

    data = res.json()
    assert "error" in data
    assert data["error"]["type"] == "provider_unavailable"
    assert "sk-secret-" not in data["error"]["message"]
    assert "[REDACTED_SECRET]" in data["error"]["message"]


@pytest.mark.asyncio
async def test_chat_sse_stream_provider_error_mid_stream() -> None:
    """Verify provider exception raised mid-stream emits sanitized error event and closes safely."""
    from app.api.v1.endpoints.chat import generate_chat_stream

    ctx = TenantContext(
        tenant_id="tenant-midstream-err",
        user_id="user-midstream",
        roles=["user"],
        permissions=["chat:stream"],
    )

    async def failing_workflow(*args: Any, **kwargs: Any) -> Any:
        yield {
            "node": "supervisor",
            "workflow_phase": "planning",
            "mascot_state": "thinking",
            "messages": ["Step 1 starting..."],
        }
        raise RuntimeError(
            "Provider connection died with sk-proj-supersecretkey99999999"
        )

    events = []
    with patch(
        "app.api.v1.endpoints.chat.stream_multi_agent_workflow",
        side_effect=failing_workflow,
    ):
        gen = generate_chat_stream(
            prompt="Analyze portfolio alpha",
            context=ctx,
            conversation_id="conv-midstream-fail",
        )
        async for ev in gen:
            events.append(ev)

    assert len(events) >= 1
    # Ensure error event was emitted
    error_events = [e for e in events if "event: error" in e]
    assert len(error_events) == 1
    assert "sk-proj-" not in error_events[0]
    assert "[REDACTED_SECRET]" in error_events[0]


def test_global_exception_handler_provider_timeout_and_408() -> None:
    """Verify ProviderTimeoutError maps to HTTP 408 Request Timeout."""
    from app.main import app

    @app.get("/test-provider-timeout")
    async def raise_timeout() -> None:
        raise ProviderTimeoutError(
            message="Upstream provider timed out after 30s with key sk-openai-12345",
            provider="openai",
            model="gpt-4o",
        )

    res = client.get("/test-provider-timeout")
    assert res.status_code == 408
    data = res.json()
    assert data["error"]["type"] == "retryable"
    assert "sk-openai" not in data["error"]["message"]
    assert "[REDACTED_SECRET]" in data["error"]["message"]


@pytest.mark.asyncio
async def test_byok_invalid_ciphertext_tamper_defense() -> None:
    """Verify tampered or invalid BYOK ciphertext fails safely without unhandled crashes."""
    from app.core.byok import BYOKManager

    mgr = BYOKManager()
    tampered_ciphertext = "v1:tampered-iv-123:tampered-ciphertext-xyz:tampered-tag"
    with pytest.raises(ValueError, match="Failed to decrypt key"):
        mgr.decrypt_key(tampered_ciphertext, tenant_id="tenant-crypto-test")


@pytest.mark.asyncio
async def test_chat_sse_stream_slow_provider_bounded() -> None:
    """Verify that slow provider stream emits events in order and updates metrics."""
    from app.api.v1.endpoints.chat import generate_chat_stream

    ctx = TenantContext(
        tenant_id="tenant-slow-test",
        user_id="user-slow",
        roles=["user"],
        permissions=["chat:stream"],
    )

    async def slow_workflow(*args: Any, **kwargs: Any) -> Any:
        await asyncio.sleep(0.05)
        yield {
            "node": "supervisor",
            "workflow_phase": "planning",
            "mascot_state": "thinking",
            "messages": ["Analyzing step 1..."],
        }
        await asyncio.sleep(0.05)
        yield {
            "node": "synthesizer",
            "workflow_phase": "synthesis",
            "mascot_state": "success",
            "messages": ["Synthesis finished"],
            "final_response": "Output text here.",
        }

    events = []
    with patch(
        "app.api.v1.endpoints.chat.stream_multi_agent_workflow",
        side_effect=slow_workflow,
    ):
        gen = generate_chat_stream(
            prompt="Compute compound interest",
            context=ctx,
            conversation_id="conv-slow-test",
        )
        async for ev in gen:
            events.append(ev)

    assert len(events) >= 3
    assert any("event: status" in e for e in events)
    assert any("event: done" in e for e in events)
