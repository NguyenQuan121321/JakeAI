"""Representative Critical API HTTP Workflows Test Suite.

TEST-04 — JAKEAI API CONTRACT & HTTP AUTOMATION
Logical ID: CONTRACT-007 | Subsystem: Contract & Schema

Verifies end-to-end multi-step critical workflows across the actual FastAPI ASGI boundary:
1. Workflow 1: Autonomous Agent Planning, Execution & SSE Streaming Lifecycle
2. Workflow 2: RAG Ingestion (Sync & Async), Task Polling, Hybrid Query & Grounded Generation
3. Workflow 3: BYOK Cryptographic Keystore Lifecycle (Store, List Masked, Rotate, Revoke, Delete)
4. Workflow 4: Multi-Provider AI Gateway, Streaming & FinOps Accounting Lifecycle
5. Workflow 5: Human-in-the-Loop Approval Gate, Tool Result & Internal Resume Bridge
"""

import time
import uuid

import jwt
import pytest
from httpx import AsyncClient

from app.agent.runtime.manager import get_agent_manager
from app.core.config import get_settings
from app.services.resume_bridge import get_resume_bridge


def create_token(
    sub: str = "workflow-user",
    tenant_id: str = "tenant-workflow-01",
    roles: list[str] | None = None,
    permissions: list[str] | None = None,
    expires_in: int = 3600,
) -> str:
    """Generate valid test JWT access token."""
    settings = get_settings()
    now = int(time.time())
    payload = {
        "sub": sub,
        "tenant_id": tenant_id,
        "type": "access",
        "iat": now,
        "exp": now + expires_in,
        "roles": roles or ["admin", "developer"],
        "permissions": permissions or ["*"],
    }
    return jwt.encode(payload, settings.JWT_SECRET_KEY, algorithm="HS256")


def auth_headers(
    tenant_id: str = "tenant-workflow-01",
    sub: str = "workflow-user",
    correlation_id: str | None = None,
) -> dict[str, str]:
    """Generate HTTP authorization headers."""
    token = create_token(sub=sub, tenant_id=tenant_id)
    headers = {"Authorization": f"Bearer {token}"}
    if correlation_id:
        headers["X-Correlation-ID"] = correlation_id
    return headers


# ==============================================================================
# Workflow 1: Autonomous Agent Planning, Execution & Streaming Lifecycle
# ==============================================================================


@pytest.mark.asyncio
async def test_workflow_1_agent_planning_execution_and_streaming(
    async_client: AsyncClient,
) -> None:
    """Verify full Autonomous Agent lifecycle: create task -> inspect -> run -> SSE events -> metrics."""
    tenant_id = f"tenant-wf1-{uuid.uuid4().hex[:6]}"
    headers = auth_headers(tenant_id=tenant_id, correlation_id="wf1-corr-123")

    # Step 1: Create Task via POST /api/v1/agent/tasks
    r_task = await async_client.post(
        "/api/v1/agent/tasks",
        headers=headers,
        json={
            "goal": "Audit Q3 revenue metrics and generate summary report",
            "metadata": {"project": "FinAudit"},
        },
    )
    assert r_task.status_code == 201
    task_data = r_task.json()
    task_id = task_data["task_id"]
    assert task_data["status"] == "pending"
    assert task_data["tenant_id"] == tenant_id
    assert r_task.headers.get("X-Correlation-ID") == "wf1-corr-123"

    # Step 2: Retrieve Task via GET /api/v1/agent/tasks/{task_id}
    r_get_task = await async_client.get(
        f"/api/v1/agent/tasks/{task_id}", headers=headers
    )
    assert r_get_task.status_code == 200
    assert r_get_task.json()["task_id"] == task_id
    assert (
        r_get_task.json()["goal"]
        == "Audit Q3 revenue metrics and generate summary report"
    )

    # Step 3: Start Run via POST /api/v1/agent/tasks/{task_id}/runs
    r_run = await async_client.post(
        f"/api/v1/agent/tasks/{task_id}/runs",
        headers=headers,
        json={"max_iterations": 3, "async_execution": False},
    )
    assert r_run.status_code == 201
    run_data = r_run.json()
    run_id = run_data["run_id"]
    assert run_data["task_id"] == task_id

    # Step 4: Stream Run Events via GET /api/v1/agent/tasks/{task_id}/runs/{run_id}/events
    # The run has terminated, so the SSE stream must emit the terminal event and terminate cleanly without blocking
    r_events = await async_client.get(
        f"/api/v1/agent/tasks/{task_id}/runs/{run_id}/events",
        headers=headers,
    )
    assert r_events.status_code == 200
    assert "text/event-stream" in r_events.headers.get("content-type", "")
    event_body = r_events.text
    assert "data:" in event_body
    assert "event:" in event_body

    # Step 5: Verify Agent Telemetry via GET /api/v1/agent/metrics
    r_metrics = await async_client.get("/api/v1/agent/metrics", headers=headers)
    assert r_metrics.status_code == 200
    metrics_data = r_metrics.json()
    assert "tasks_created" in metrics_data
    assert "runs_started" in metrics_data
    assert metrics_data["tasks_created"] >= 1


# ==============================================================================
# Workflow 2: RAG Ingestion, Task Polling, Query & Grounded Generation
# ==============================================================================


@pytest.mark.asyncio
async def test_workflow_2_rag_ingest_query_and_grounded_generation(
    async_client: AsyncClient,
) -> None:
    """Verify full RAG lifecycle: ingest document -> poll async task -> query -> grounded answer."""
    tenant_id = f"tenant-rag-{uuid.uuid4().hex[:6]}"
    headers = auth_headers(tenant_id=tenant_id)

    sample_doc = (
        "Project Orion was approved on August 15, 2026. "
        "The total approved budget is $4,500,000 USD. "
        "The project lead is Dr. Elena Vance."
    )

    # Step 1: Synchronous Document Ingestion via POST /api/v1/rag/ingest
    r_sync = await async_client.post(
        "/api/v1/rag/ingest",
        headers=headers,
        json={
            "content": sample_doc,
            "filename": "project_orion.txt",
            "async_mode": False,
        },
    )
    assert r_sync.status_code == 201
    sync_data = r_sync.json()
    assert sync_data["indexed_chunks"] > 0
    assert len(sync_data["chunk_ids"]) > 0
    assert sync_data["tenant_id"] == tenant_id

    # Step 2: Asynchronous Document Ingestion via POST /api/v1/rag/ingest?async_mode=true
    r_async = await async_client.post(
        "/api/v1/rag/ingest?async_mode=true",
        headers=headers,
        json={
            "content": "Addendum: Project Orion phase 2 commences in Q1 2027.",
            "filename": "orion_addendum.txt",
        },
    )
    assert r_async.status_code == 202
    async_data = r_async.json()
    task_id = async_data["task_id"]
    assert async_data["status"] in ("queued", "completed", "processing")

    # Step 3: Poll Ingestion Task Status via GET /api/v1/rag/tasks/{task_id}
    r_task_status = await async_client.get(
        f"/api/v1/rag/tasks/{task_id}", headers=headers
    )
    assert r_task_status.status_code == 200
    assert r_task_status.json()["task_id"] == task_id

    # Step 4: Hybrid Query via POST /api/v1/rag/query
    r_query = await async_client.post(
        "/api/v1/rag/query",
        headers=headers,
        json={"query": "What is the budget for Project Orion?", "top_k": 3},
    )
    assert r_query.status_code == 200
    query_data = r_query.json()
    assert query_data["tenant_id"] == tenant_id
    assert "chunks" in query_data

    # Step 5: Grounded Answer Generation via POST /api/v1/rag/generate
    r_gen = await async_client.post(
        "/api/v1/rag/generate",
        headers=headers,
        json={
            "query": "Who is the project lead for Project Orion and what is the budget?",
            "top_k": 3,
        },
    )
    assert r_gen.status_code == 200
    gen_data = r_gen.json()
    assert "answer" in gen_data
    assert "status" in gen_data
    assert gen_data["status"] in ("SUCCESS", "ABSTAINED")


# ==============================================================================
# Workflow 3: BYOK Cryptographic Keystore Lifecycle
# ==============================================================================


@pytest.mark.asyncio
async def test_workflow_3_byok_cryptographic_keystore_lifecycle(
    async_client: AsyncClient,
) -> None:
    """Verify full BYOK lifecycle: Store key -> List (Masked) -> Validate -> Rotate -> Revoke -> Delete."""
    tenant_id = f"tenant-byok-{uuid.uuid4().hex[:6]}"
    headers = auth_headers(tenant_id=tenant_id)
    provider = "groq"

    # Step 1: Store Provider Key (AES-256-GCM encrypted) via POST /api/v1/byok/keys
    r_store = await async_client.post(
        "/api/v1/byok/keys",
        headers=headers,
        json={
            "provider": provider,
            "api_key": "gsk_test_key_secret_12345678",
            "validate_key": False,
        },
    )
    assert r_store.status_code == 201
    store_data = r_store.json()
    assert store_data["provider"] == provider
    assert store_data["status"] == "configured"
    assert "12345678" not in store_data["masked_key"]  # Must be masked

    # Step 2: List Provider Keys via GET /api/v1/byok/keys
    r_list = await async_client.get("/api/v1/byok/keys", headers=headers)
    assert r_list.status_code == 200
    list_data = r_list.json()
    groq_item = next((k for k in list_data["keys"] if k["provider"] == provider), None)
    assert groq_item is not None
    assert groq_item["configured"] is True

    # Step 3: Validate Candidate Key via POST /api/v1/byok/keys/validate
    r_val = await async_client.post(
        "/api/v1/byok/keys/validate",
        headers=headers,
        json={"provider": provider, "api_key": "gsk_test_key_secret_12345678"},
    )
    assert r_val.status_code == 200
    assert "is_valid" in r_val.json()

    # Step 4: Rotate Provider Key via POST /api/v1/byok/keys/{provider}/rotate
    r_rotate = await async_client.post(
        f"/api/v1/byok/keys/{provider}/rotate",
        headers=headers,
        json={"new_api_key": "gsk_rotated_new_key_87654321", "validate_key": False},
    )
    assert r_rotate.status_code == 200
    assert r_rotate.json()["status"] == "configured"

    # Step 5: Revoke Provider Key via POST /api/v1/byok/keys/{provider}/revoke
    r_revoke = await async_client.post(
        f"/api/v1/byok/keys/{provider}/revoke",
        headers=headers,
    )
    assert r_revoke.status_code == 200
    assert r_revoke.json()["status"] == "revoked"

    # Step 6: Delete Provider Key via DELETE /api/v1/byok/keys/{provider}
    r_del = await async_client.delete(
        f"/api/v1/byok/keys/{provider}",
        headers=headers,
    )
    assert r_del.status_code == 200
    assert r_del.json()["status"] in ("revoked", "deleted")

    # Step 7: Verify Key Is Purged via GET /api/v1/byok/keys
    r_post_list = await async_client.get("/api/v1/byok/keys", headers=headers)
    assert r_post_list.status_code == 200
    groq_post = next(
        (k for k in r_post_list.json()["keys"] if k["provider"] == provider), None
    )
    assert groq_post is None or groq_post["configured"] is False


# ==============================================================================
# Workflow 4: AI Gateway & FinOps Accounting Lifecycle
# ==============================================================================


@pytest.mark.asyncio
async def test_workflow_4_gateway_inference_and_finops_accounting(
    async_client: AsyncClient,
) -> None:
    """Verify Gateway inference (sync + SSE) -> Quota monitoring -> FinOps budget and summary."""
    tenant_id = f"tenant-gw-{uuid.uuid4().hex[:6]}"
    headers = auth_headers(tenant_id=tenant_id)

    # Step 1: Model Discovery via GET /v1/models and GET /api/v1/gateway/models
    r_models = await async_client.get("/v1/models", headers=headers)
    assert r_models.status_code == 200
    models_data = r_models.json()
    assert models_data["object"] == "list"
    assert len(models_data["data"]) > 0

    # Step 2: Query Tenant Quota via GET /api/v1/gateway/quotas
    r_quota = await async_client.get("/api/v1/gateway/quotas", headers=headers)
    assert r_quota.status_code == 200
    quota_data = r_quota.json()
    assert quota_data["tenant_id"] == tenant_id
    assert "quota_limit" in quota_data

    # Step 3: Synchronous Chat Completion via POST /api/v1/gateway/chat/completions
    r_chat = await async_client.post(
        "/api/v1/gateway/chat/completions",
        headers=headers,
        json={
            "model": "gemini-1.5-flash",
            "messages": [
                {"role": "user", "content": "Explain quantum computing in one sentence"}
            ],
            "stream": False,
        },
    )
    assert r_chat.status_code == 200
    chat_data = r_chat.json()
    assert "choices" in chat_data
    assert len(chat_data["choices"]) > 0

    # Step 4: Streaming Chat Completion via POST /v1/chat/completions (stream=True)
    r_stream = await async_client.post(
        "/v1/chat/completions",
        headers=headers,
        json={
            "model": "gemini-1.5-flash",
            "messages": [{"role": "user", "content": "Stream response"}],
            "stream": True,
        },
    )
    assert r_stream.status_code == 200
    assert "text/event-stream" in r_stream.headers.get("content-type", "")
    assert "data: [DONE]" in r_stream.text

    # Step 5: Update Tenant Quota via POST /api/v1/gateway/quotas
    r_upd_quota = await async_client.post(
        "/api/v1/gateway/quotas",
        headers=headers,
        json={"new_limit": 500000},
    )
    assert r_upd_quota.status_code == 200
    assert r_upd_quota.json()["quota_limit"] == 500000

    # Step 6: Configure FinOps Budget via POST /api/v1/finops/budget
    r_budget = await async_client.post(
        "/api/v1/finops/budget",
        headers=headers,
        json={
            "dollar_budget_usd": 1000.0,
            "token_quota": 500000,
            "warning_threshold": 0.8,
        },
    )
    assert r_budget.status_code == 200
    assert r_budget.json()["dollar_budget_usd"] == 1000.0

    # Step 7: Inspect FinOps Summary via GET /api/v1/finops/summary
    r_summary = await async_client.get("/api/v1/finops/summary", headers=headers)
    assert r_summary.status_code == 200
    summary_data = r_summary.json()
    assert "total_actual_cost_usd" in summary_data
    assert "total_baseline_cost_usd" in summary_data
    assert "total_savings_usd" in summary_data
    assert "budget_status" in summary_data


# ==============================================================================
# Workflow 5: Human-in-the-Loop Approval & Tool Resume Bridge
# ==============================================================================


@pytest.mark.asyncio
async def test_workflow_5_human_in_the_loop_and_tool_resume_bridge(
    async_client: AsyncClient,
) -> None:
    """Verify Human-in-the-Loop approval gate -> decision -> tool result -> internal resume."""
    tenant_id = f"tenant-hitl-{uuid.uuid4().hex[:6]}"
    headers = auth_headers(tenant_id=tenant_id)
    manager = get_agent_manager()
    bridge = get_resume_bridge()
    settings = get_settings()

    # Step 1: Create Task and Run
    task = manager.create_task(
        goal="Perform automated code refactor requiring human approval",
        tenant_id=tenant_id,
        user_id="engineer-1",
    )
    run = manager.create_run(task.task_id, tenant_id=tenant_id, user_id="engineer-1")

    # Step 2: Register Dangerous Action Approval Gate
    appr = manager.approval_manager.create_request(
        task_id=task.task_id,
        run_id=run.run_id,
        tenant_id=tenant_id,
        tool_name="shell_execute",
        tool_args={"command": "rm -rf /tmp/cache"},
        reason="Purge stale local cache artifacts",
        risk_level="dangerous",
    )

    # Step 3: Operator Lists Pending Approvals via GET /api/v1/agent/approvals/pending
    r_pending = await async_client.get(
        "/api/v1/agent/approvals/pending", headers=headers
    )
    assert r_pending.status_code == 200
    pending_list = r_pending.json()
    assert any(a["approval_id"] == appr.approval_id for a in pending_list)

    # Step 4: Operator Submits Approval via POST /api/v1/agent/tasks/{tid}/runs/{rid}/approvals/{aid}
    r_decision = await async_client.post(
        f"/api/v1/agent/tasks/{task.task_id}/runs/{run.run_id}/approvals/{appr.approval_id}",
        headers=headers,
        json={"approved": True, "reason": "Authorized by security lead"},
    )
    assert r_decision.status_code == 200
    assert r_decision.json()["status"] == "approved"

    # Step 5: Register tool checkpoint and submit tool result via POST /api/v1/coding/tool-result
    call_id = f"call_refactor_{uuid.uuid4().hex[:8]}"
    await bridge.save_checkpoint(
        call_id=call_id,
        tenant_id=tenant_id,
        state_data={"tool": "shell_execute", "status": "pending"},
    )

    r_tool_result = await async_client.post(
        "/api/v1/coding/tool-result",
        headers=headers,
        json={
            "call_id": call_id,
            "result": {"exit_code": 0, "output": "Cache purged successfully"},
        },
    )
    assert r_tool_result.status_code == 200
    assert r_tool_result.json()["status"] == "resumed"

    # Step 6: Internal Perimeter Resume via POST /internal/v1/coding/resume
    call_id_internal = f"call_internal_{uuid.uuid4().hex[:8]}"
    await bridge.save_checkpoint(
        call_id=call_id_internal,
        tenant_id=tenant_id,
        state_data={"tool": "ast_patch", "status": "pending"},
    )

    internal_headers = {
        "x-forwarded-by": "finnapigo",
        "x-internal-secret": settings.INTERNAL_GATEWAY_SECRET,
    }
    r_internal = await async_client.post(
        "/internal/v1/coding/resume",
        headers=internal_headers,
        json={
            "call_id": call_id_internal,
            "tenant_id": tenant_id,
            "result": {"applied_patches": 3},
        },
    )
    assert r_internal.status_code == 200
    assert r_internal.json()["status"] == "resumed"
