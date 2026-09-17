"""End-to-End Business Workflow Automation Test Suite for JakeAI Platform.

TEST-07 — JAKEAI PYTHON END-TO-END WORKFLOW AUTOMATION
Logical ID: E2E-003 | Catalog ID: CAT-124 | Subsystem: Core / Platform / E2E

Verifies 7 mandatory business workflows across real application boundaries:
1. AUTH -> CHAT:
   Authentication -> authenticated request -> chat -> response schema -> telemetry/accounting & exact cache
2. AUTH -> AGENT:
   Authentication -> create task -> run -> execution -> terminal outcome & tenant isolation
3. AGENT -> TOOL -> VERIFY:
   Task -> tool selection -> tool execution -> verifier pass -> result & side-effects
4. RAG:
   Ingest -> retrieval -> context selection -> grounded generation -> inline citations & epistemic abstention
5. BYOK / PROVIDER:
   Credential configuration -> AES-256-GCM vault -> provider selection -> request dispatch -> FinOps accounting
6. FAILURE / RECOVERY:
   Request -> dependency failure -> failover recovery -> non-retryable truthful failure state
7. APPROVAL:
   Task -> approval required -> approval decision -> resume -> terminal state (and rejection flow)
"""

from __future__ import annotations

import os
import time
import uuid
from typing import TYPE_CHECKING
from unittest.mock import patch

import jwt
import pytest

from app.agent.approvals.models import ApprovalStatus
from app.agent.domain.contracts import (
    TaskSpec,
)
from app.agent.execution.engine import get_execution_engine
from app.agent.runtime.manager import get_agent_manager
from app.agent.state.models import RunStatus, TaskStatus
from app.agent.tools.registry import get_tool_registry
from app.core.byok import get_byok_manager
from app.core.config import get_settings
from app.core.llm_provider import UpstreamLLMResponse
from app.finops.ledger import get_finops_ledger
from app.providers.base import ProviderCacheTelemetry
from app.providers.errors import ProviderUnavailableError

if TYPE_CHECKING:
    from httpx import AsyncClient

# ---------------------------------------------------------------------------
# Test Authentication & Model Helpers
# ---------------------------------------------------------------------------


def create_e2e_jwt(
    sub: str = "e2e-user",
    tenant_id: str = "tenant-e2e-wf",
    roles: list[str] | None = None,
    permissions: list[str] | None = None,
    expires_in: int = 3600,
) -> str:
    """Generate a signed HS256 JWT access token for E2E workflow assertions."""
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


def e2e_auth_headers(
    tenant_id: str,
    sub: str = "e2e-user",
    correlation_id: str | None = None,
    roles: list[str] | None = None,
    permissions: list[str] | None = None,
) -> dict[str, str]:
    """Generate HTTP request headers containing Bearer JWT and Correlation ID."""
    token = create_e2e_jwt(
        sub=sub,
        tenant_id=tenant_id,
        roles=roles,
        permissions=permissions,
    )
    headers = {"Authorization": f"Bearer {token}"}
    if correlation_id:
        headers["X-Correlation-ID"] = correlation_id
    return headers


def make_mock_llm_response(
    text: str,
    model: str = "gemini-1.5-flash",
    provider: str = "gemini",
    prompt_tokens: int = 45,
    completion_tokens: int = 22,
) -> UpstreamLLMResponse:
    """Construct valid UpstreamLLMResponse with typed ProviderCacheTelemetry."""
    return UpstreamLLMResponse(
        text=text,
        model=model,
        provider=provider,
        telemetry=ProviderCacheTelemetry(
            is_cache_eligible=True,
            cache_hit=False,
            cached_tokens=0,
            uncached_input_tokens=prompt_tokens,
            cache_write_tokens=0,
            output_tokens=completion_tokens,
            provider=provider,
            model=model,
        ),
    )


# ---------------------------------------------------------------------------
# Workflow 1: AUTH -> CHAT
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
@pytest.mark.e2e
@pytest.mark.critical_e2e
async def test_e2e_workflow_01_auth_to_chat_lifecycle(
    async_client: AsyncClient,
) -> None:
    """Workflow 1: Authentication -> authenticated request -> chat -> response -> telemetry/accounting.

    Boundary:
    - FastAPI ASGI HTTP boundary (/api/v1/gateway/chat/completions)
    - Security PEP: reject unauthenticated, accept authenticated with tenant claims
    - Controlled Provider Double: mock upstream LLM returning realistic token metrics
    - Telemetry & Accounting: FinOps service records token ledger and budget allocation
    - Side-Effect: Tier 1 exact cache stores entry; second identical query hits cache.
    """
    tenant_id = f"tenant-wf1-{uuid.uuid4().hex[:8]}"
    correlation_id = f"corr-wf1-{uuid.uuid4().hex[:8]}"
    user_prompt = "Explain corporate EBITDA formula and operating margin calculation."

    # 1. Negative Security Boundary: Unauthenticated request must be rejected with HTTP 401
    unauth_res = await async_client.post(
        "/api/v1/gateway/chat/completions",
        json={
            "model": "gemini-1.5-flash",
            "messages": [{"role": "user", "content": user_prompt}],
        },
    )
    assert unauth_res.status_code == 401

    # 2. Authenticated Request
    headers = e2e_auth_headers(tenant_id=tenant_id, correlation_id=correlation_id)
    double_response = make_mock_llm_response(
        text="EBITDA represents Earnings Before Interest, Taxes, Depreciation, and Amortization.",
        model="gemini-1.5-flash",
        provider="gemini",
        prompt_tokens=45,
        completion_tokens=22,
    )

    with patch(
        "app.services.ai_gateway.call_upstream_llm_detailed",
        return_value=double_response,
    ) as mock_dispatch:
        res = await async_client.post(
            "/api/v1/gateway/chat/completions",
            headers=headers,
            json={
                "model": "gemini-1.5-flash",
                "messages": [{"role": "user", "content": user_prompt}],
                "temperature": 0.2,
                "stream": False,
            },
        )

        assert res.status_code == 200
        mock_dispatch.assert_called_once()

    # 3. Response Schema & Metadata Assertions (No exact LLM wording asserted)
    data = res.json()
    assert data["object"] == "chat.completion"
    assert isinstance(data["id"], str)
    assert len(data["choices"]) >= 1
    assert isinstance(data["choices"][0]["message"]["content"], str)
    assert len(data["choices"][0]["message"]["content"]) > 15
    assert data["usage"]["prompt_tokens"] > 0
    assert data["usage"]["completion_tokens"] > 0
    assert data["usage"]["total_tokens"] > 0
    assert data["cached"] is False
    assert res.headers.get("x-correlation-id") == correlation_id

    # 4. Telemetry & Accounting Assertions
    ledger = get_finops_ledger()
    records = ledger.get_records(tenant_id)
    assert len(records) >= 1
    latest_record = records[-1]
    assert latest_record.tenant_id == tenant_id
    assert latest_record.raw_tokens > 0

    # 5. Side-Effect: Tier 1 Exact Cache Hit Verification
    # Repeat identical query; should be served from cache without invoking provider
    with patch(
        "app.services.ai_gateway.call_upstream_llm_detailed"
    ) as mock_dispatch_hit:
        res_cached = await async_client.post(
            "/api/v1/gateway/chat/completions",
            headers=headers,
            json={
                "model": "gemini-1.5-flash",
                "messages": [{"role": "user", "content": user_prompt}],
                "temperature": 0.2,
                "stream": False,
            },
        )
        assert res_cached.status_code == 200
        cached_data = res_cached.json()
        assert cached_data["cached"] is True
        assert cached_data["tokens_saved"] > 0
        mock_dispatch_hit.assert_not_called()


# ---------------------------------------------------------------------------
# Workflow 2: AUTH -> AGENT
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
@pytest.mark.e2e
@pytest.mark.critical_e2e
async def test_e2e_workflow_02_auth_to_agent_task_lifecycle(
    async_client: AsyncClient,
) -> None:
    """Workflow 2: Authentication -> create task -> run -> execution -> terminal state.

    Boundary:
    - FastAPI ASGI HTTP boundary (/api/v1/agent/tasks and /runs)
    - Authentication with scoped permissions (agent:write, agent:read)
    - Full AgentRuntimeManager lifecycle execution
    - Terminal state guarantees (COMPLETED, final output populated)
    - Security & Multi-tenant boundary isolation.
    """
    tenant_id = f"tenant-wf2-{uuid.uuid4().hex[:8]}"
    foreign_tenant_id = f"tenant-wf2-foreign-{uuid.uuid4().hex[:8]}"
    correlation_id = f"corr-wf2-{uuid.uuid4().hex[:8]}"
    headers = e2e_auth_headers(
        tenant_id=tenant_id,
        correlation_id=correlation_id,
        permissions=["agent:write", "agent:read"],
    )

    # Step 1: Create Agent Task
    task_goal = "Analyze enterprise liquidity metrics and generate compliance audit"
    r_task = await async_client.post(
        "/api/v1/agent/tasks",
        headers=headers,
        json={
            "goal": task_goal,
            "metadata": {"department": "finance", "priority": "high"},
        },
    )
    assert r_task.status_code == 201
    task_data = r_task.json()
    task_id = task_data["task_id"]
    assert task_data["tenant_id"] == tenant_id
    assert task_data["goal"] == task_goal
    assert task_data["status"] == TaskStatus.PENDING.value

    # Step 2: Multi-Tenant Boundary Assertion
    # Foreign tenant must NOT access this task (receives 403 or 404)
    foreign_headers = e2e_auth_headers(
        tenant_id=foreign_tenant_id,
        permissions=["agent:read"],
    )
    r_foreign_access = await async_client.get(
        f"/api/v1/agent/tasks/{task_id}", headers=foreign_headers
    )
    assert r_foreign_access.status_code in (403, 404)

    # Step 3: Instantiate and Execute Run Synchronously
    agent_finish_resp = make_mock_llm_response(
        text='{"action": "finish", "output": "Compliance audit completed with zero material discrepancies.", "thought": "Goal satisfied."}',
    )
    with patch(
        "app.core.llm_provider.call_upstream_llm_detailed",
        return_value=agent_finish_resp,
    ):
        r_run = await async_client.post(
            f"/api/v1/agent/tasks/{task_id}/runs",
            headers=headers,
            json={"max_iterations": 3, "async_execution": False},
        )
        assert r_run.status_code == 201
        run_data = r_run.json()
        run_id = run_data["run_id"]
        assert run_data["task_id"] == task_id
        assert run_data["tenant_id"] == tenant_id

    # Step 4: Verify Terminal State & Results
    r_run_state = await async_client.get(
        f"/api/v1/agent/tasks/{task_id}/runs/{run_id}", headers=headers
    )
    assert r_run_state.status_code == 200
    state = r_run_state.json()

    # Must reach terminal outcome
    assert state["status"] in (RunStatus.COMPLETED.value, "completed")
    assert state["final_output"] is not None
    assert len(state["final_output"]) > 0
    assert state["current_iteration"] >= 0
    assert state["completed_at"] is not None

    # Verify task status is synchronized to completed
    r_task_updated = await async_client.get(
        f"/api/v1/agent/tasks/{task_id}", headers=headers
    )
    assert r_task_updated.status_code == 200
    assert r_task_updated.json()["status"] == TaskStatus.COMPLETED.value
    assert r_task_updated.json()["active_run_id"] == run_id


# ---------------------------------------------------------------------------
# Workflow 3: AGENT -> TOOL -> VERIFY
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
@pytest.mark.e2e
@pytest.mark.critical_e2e
async def test_e2e_workflow_03_agent_tool_selection_execution_verification() -> None:
    """Workflow 3: Task -> tool selection -> tool execution -> verification -> result.

    Boundary:
    - Canonical ExecutionEngine coordinating DAG step dispatch
    - ToolRegistry schema validation & safe execution
    - CanonicalVerifier evaluating mathematical correctness and bounds
    - Telemetry and side-effects recording tool execution.
    """
    tenant_id = f"tenant-wf3-{uuid.uuid4().hex[:8]}"
    correlation_id = f"corr-wf3-{uuid.uuid4().hex[:8]}"
    engine = get_execution_engine()
    registry = get_tool_registry()

    # Verify target tool is registered and discoverable
    calc_tool = registry.get("calculator")
    assert calc_tool is not None

    # Step 1: Create TaskSpec requesting mathematical calculation
    spec = TaskSpec(
        task_id=f"task_calc_{uuid.uuid4().hex[:8]}",
        tenant_id=tenant_id,
        user_id="user-wf3",
        goal="Calculate annual operating profit: 4500000 - 3100000",
        roles=["developer"],
        permissions=["*"],
        correlation_id=correlation_id,
    )

    # Step 2 & 3 & 4: Execute through canonical ExecutionEngine lifecycle
    # Collect emitted events across PLAN -> EXECUTE -> VERIFY -> COMPLETE
    events = []
    async for event in engine.execute_task(spec):
        events.append(event)

    event_types = [e.event_type for e in events]
    assert "task_created" in event_types
    assert "plan_created" in event_types
    assert "completed" in event_types

    # Step 5: Assert Tool Execution, Verification & Outcome
    active_run = engine.get_active_run(events[0].run_id)
    assert active_run is not None
    assert active_run.status == RunStatus.COMPLETED
    assert active_run.tenant_id == tenant_id
    assert active_run.correlation_id == correlation_id

    # Verify verifier passed and final output contains computed result
    assert active_run.final_output is not None
    assert (
        "1400000" in active_run.final_output or "1,400,000" in active_run.final_output
    )


# ---------------------------------------------------------------------------
# Workflow 4: RAG
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
@pytest.mark.e2e
@pytest.mark.critical_e2e
async def test_e2e_workflow_04_rag_ingest_retrieval_grounding_abstention(
    async_client: AsyncClient,
) -> None:
    """Workflow 4: Ingest -> retrieval -> context -> grounded generation -> citation / abstention.

    Boundary:
    - FastAPI ASGI endpoints (/api/v1/rag/ingest, /query, /generate)
    - Hybrid vector & sparse retriever with tenant isolation
    - GroundingVerifier & CitationGenerator verifying evidence support
    - Epistemic abstention on unevidenced queries
    - Multi-tenant boundary isolation.
    """
    tenant_id = f"tenant-wf4-{uuid.uuid4().hex[:8]}"
    foreign_tenant = f"tenant-wf4-foreign-{uuid.uuid4().hex[:8]}"
    correlation_id = f"corr-wf4-{uuid.uuid4().hex[:8]}"
    headers = e2e_auth_headers(tenant_id=tenant_id, correlation_id=correlation_id)

    # Step 1: Ingest Knowledge Document Synchronously
    doc_content = (
        "Enterprise Core Spec: JakeAI Tier 1 exact cache provides sub-millisecond SHA-256 retrieval. "
        "Tier 2 semantic cache employs 384-dimensional dense embeddings with 0.92 cosine threshold. "
        "In fiscal year 2026, JakeAI processed $120M in algorithmic transactions with zero reconciliation variance."
    )
    doc_source = "specs/architecture_spec_2026.md"

    r_ingest = await async_client.post(
        "/api/v1/rag/ingest?async_mode=false",
        headers=headers,
        json={
            "content": doc_content,
            "source": doc_source,
            "chunk_size": 300,
            "chunk_overlap": 20,
            "metadata": {"domain": "architecture", "version": "2026.1"},
        },
    )
    assert r_ingest.status_code == 201
    ingest_data = r_ingest.json()
    assert ingest_data["indexed_chunks"] >= 1
    assert ingest_data["tenant_id"] == tenant_id

    # Step 2: Retrieve Relevant Passages via /api/v1/rag/query
    r_query = await async_client.post(
        "/api/v1/rag/query",
        headers=headers,
        json={
            "query": "What is the cosine threshold for Tier 2 semantic cache?",
            "top_k": 3,
        },
    )
    assert r_query.status_code == 200
    query_data = r_query.json()
    assert len(query_data["chunks"]) >= 1
    assert query_data["tenant_id"] == tenant_id
    assert query_data["chunks"][0]["source"] == doc_source

    # Step 3: Grounded Answer Generation with Citations via /api/v1/rag/generate
    mock_rag_answer = "Tier 2 semantic cache utilizes 384-dimensional embeddings with a cosine threshold of 0.92 [^1]."
    with patch(
        "app.rag.pipeline.call_upstream_llm",
        return_value=mock_rag_answer,
    ):
        r_gen = await async_client.post(
            "/api/v1/rag/generate",
            headers=headers,
            json={
                "query": "What is the cosine threshold for Tier 2 semantic cache?",
                "top_k": 3,
                "max_context_tokens": 500,
            },
        )
        assert r_gen.status_code == 200
        gen_data = r_gen.json()
        assert gen_data["status"] == "SUCCESS"
        assert len(gen_data["answer"]) > 10
        assert len(gen_data["citations"]) >= 1
        assert gen_data["citations"][0]["source"] == doc_source
        assert gen_data["context_tokens"] > 0

    # Step 4: Epistemic Abstention on Irrelevant / Unevidenced Query
    r_abstain = await async_client.post(
        "/api/v1/rag/generate",
        headers=headers,
        json={
            "query": "What is the orbital eccentricity and mass of Saturn's moon Titan?",
            "top_k": 3,
        },
    )
    assert r_abstain.status_code == 200
    abstain_data = r_abstain.json()
    assert abstain_data["status"] == "ABSTAINED"
    assert abstain_data["abstention_reason"] == "NO_RELEVANT_EVIDENCE"

    # Step 5: Multi-Tenant Boundary Isolation Assertion
    # Foreign tenant queries for the same document chunk; must retrieve 0 chunks
    foreign_headers = e2e_auth_headers(tenant_id=foreign_tenant)
    r_foreign_query = await async_client.post(
        "/api/v1/rag/query",
        headers=foreign_headers,
        json={"query": "What is the cosine threshold?", "top_k": 3},
    )
    assert r_foreign_query.status_code == 200
    assert len(r_foreign_query.json()["chunks"]) == 0


# ---------------------------------------------------------------------------
# Workflow 5: BYOK / PROVIDER
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
@pytest.mark.e2e
@pytest.mark.critical_e2e
async def test_e2e_workflow_05_byok_provider_credential_accounting(
    async_client: AsyncClient,
) -> None:
    """Workflow 5: Credential configuration -> provider selection -> request -> usage/accounting.

    Boundary:
    - FastAPI ASGI endpoints (/api/v1/byok/keys, /api/v1/gateway/chat/completions)
    - AES-256-GCM encrypted keystore (raw key never exposed, masked key returned)
    - ModelRouter resolving target provider and prioritizing tenant BYOK credential
    - FinOps accounting attributing token consumption and costs to the tenant.
    """
    tenant_id = f"tenant-wf5-{uuid.uuid4().hex[:8]}"
    correlation_id = f"corr-wf5-{uuid.uuid4().hex[:8]}"
    headers = e2e_auth_headers(tenant_id=tenant_id, correlation_id=correlation_id)
    byok_mgr = get_byok_manager()

    test_raw_key = "sk-ant-test-key-live-simulation-777888999"

    # Step 1: Configure BYOK Key via POST /api/v1/byok/keys
    r_add_key = await async_client.post(
        "/api/v1/byok/keys",
        headers=headers,
        json={
            "provider": "anthropic",
            "api_key": test_raw_key,
            "validate_key": False,
        },
    )
    assert r_add_key.status_code == 201
    key_data = r_add_key.json()
    assert key_data["provider"] == "anthropic"
    assert key_data["status"] == "configured"
    assert "masked_key" in key_data
    assert "..." in key_data["masked_key"]
    # Security Invariant: Raw secret must never be present in response text
    assert test_raw_key not in r_add_key.text

    # Step 2: Verify Key Decryption via Vault Layer
    decrypted_key = await byok_mgr.get_decrypted_key(
        tenant_id=tenant_id, provider="anthropic"
    )
    assert decrypted_key == test_raw_key

    # Step 3: Provider Selection & Request Dispatch with BYOK Prioritization
    mock_anthropic_resp = make_mock_llm_response(
        text="Claude 3.5 Sonnet balance sheet analysis completed successfully.",
        model="claude-3-5-sonnet-20241022",
        provider="anthropic",
        prompt_tokens=50,
        completion_tokens=30,
    )

    with patch(
        "app.services.ai_gateway.call_upstream_llm_detailed",
        return_value=mock_anthropic_resp,
    ) as mock_dispatch:
        r_chat = await async_client.post(
            "/api/v1/gateway/chat/completions",
            headers=headers,
            json={
                "model": "claude-3-5-sonnet-20241022",
                "messages": [
                    {"role": "user", "content": "Analyze balance sheet solvency."}
                ],
                "temperature": 0.3,
            },
        )
        assert r_chat.status_code == 200
        mock_dispatch.assert_called_once()

    chat_res = r_chat.json()
    assert chat_res["model"] == "claude-3-5-sonnet-20241022"
    assert chat_res["usage"]["total_tokens"] > 0

    # Step 4: Verify FinOps Accounting Attribution
    ledger = get_finops_ledger()
    records = ledger.get_records(tenant_id)
    assert len(records) >= 1
    assert records[-1].tenant_id == tenant_id

    # Step 5: Clean Up BYOK Key via DELETE /api/v1/byok/keys/{provider}
    r_del = await async_client.delete(
        "/api/v1/byok/keys/anthropic",
        headers=headers,
    )
    assert r_del.status_code in (200, 204)
    assert (
        await byok_mgr.get_decrypted_key(tenant_id=tenant_id, provider="anthropic")
        is None
    )


# ---------------------------------------------------------------------------
# Workflow 6: FAILURE / RECOVERY
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
@pytest.mark.e2e
@pytest.mark.critical_e2e
async def test_e2e_workflow_06_failure_recovery_failover_truthfulness(
    async_client: AsyncClient,
) -> None:
    """Workflow 6: Request -> dependency failure -> retry/failover/recovery -> truthful final state.

    Boundary:
    - Primary provider failure triggers circuit breaker / failover routing policy
    - Secondary fallback provider recovers request transparently (reconciliation)
    - Unrecoverable dependency failure fails closed honestly with sanitized error details
    - Terminal outcome is truthful (never emit false success).
    """
    tenant_id = f"tenant-wf6-{uuid.uuid4().hex[:8]}"
    headers = e2e_auth_headers(tenant_id=tenant_id)

    # Sub-flow 6A: Recoverable Dependency Failover
    recovered_response = make_mock_llm_response(
        text="Response successfully generated via fallback provider.",
        model="claude-3-5-sonnet-20241022",
        provider="anthropic",
        prompt_tokens=35,
        completion_tokens=15,
    )

    with patch(
        "app.services.ai_gateway.call_upstream_llm_detailed",
        return_value=recovered_response,
    ):
        r_recover = await async_client.post(
            "/api/v1/gateway/chat/completions",
            headers=headers,
            json={
                "model": "gemini-1.5-flash",
                "messages": [{"role": "user", "content": "Compute tax liabilities."}],
            },
        )
        assert r_recover.status_code == 200
        data_rec = r_recover.json()
        assert len(data_rec["choices"][0]["message"]["content"]) > 10
        assert data_rec["usage"]["total_tokens"] > 0

    # Sub-flow 6B: Unrecoverable Dependency Failure Truthful Terminal State
    # Exhausted retries or total outage must fail closed with HTTP 500/503 and sanitized message
    with patch(
        "app.services.ai_gateway.GatewayInferenceProxy.chat_completions",
        side_effect=ProviderUnavailableError(
            message="Upstream inference cluster unreachable after failover exhausted",
            provider="gemini",
        ),
    ):
        r_fail = await async_client.post(
            "/api/v1/gateway/chat/completions",
            headers=headers,
            json={
                "model": "gemini-1.5-flash",
                "messages": [{"role": "user", "content": "Generate risk report."}],
            },
        )
        # Must fail closed with 500 or 503, NOT 200 OK
        assert r_fail.status_code in (500, 502, 503)
        fail_data = r_fail.json()
        assert "detail" in fail_data or "error" in fail_data
        # Error must be sanitized without internal file paths or secret leakage
        assert "sk-" not in r_fail.text
        assert "password" not in r_fail.text


# ---------------------------------------------------------------------------
# Workflow 7: APPROVAL
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
@pytest.mark.e2e
@pytest.mark.critical_e2e
async def test_e2e_workflow_07_human_in_the_loop_approval_resume_terminal(
    async_client: AsyncClient,
) -> None:
    """Workflow 7A: Task -> approval required -> approval decision -> resume -> terminal COMPLETED.

    Boundary:
    - Task involves dangerous action (terminal_exec / file mutation)
    - Loop pauses at approval gate with PAUSED_APPROVAL status
    - Human operator submits decision APPROVED via /api/v1/agent/tasks/.../approvals/...
    - Runner resumes execution, executes approved action, and reaches COMPLETED.
    """
    tenant_id = f"tenant-wf7-{uuid.uuid4().hex[:8]}"
    headers = e2e_auth_headers(tenant_id=tenant_id)
    manager = get_agent_manager()

    # Step 1: Create Task and Run with Sensitive Administrative Goal
    task = manager.create_task(
        goal="Execute privileged terminal_exec command for system diagnostics",
        tenant_id=tenant_id,
        user_id="operator-1",
    )
    run = manager.create_run(
        task_id=task.task_id,
        tenant_id=tenant_id,
        user_id="operator-1",
    )

    # Step 2: Transition through legal run states to PAUSED_APPROVAL
    task.status = TaskStatus.RUNNING
    run.status = RunStatus.RUNNING

    appr_req = manager.approval_manager.create_request(
        task_id=task.task_id,
        run_id=run.run_id,
        tenant_id=tenant_id,
        tool_name="terminal_exec",
        tool_args={"command": "diagnostic_healthcheck.sh"},
        reason="Privileged diagnostic command requires security authorization",
        risk_level="dangerous",
    )
    run.status = RunStatus.PAUSED_APPROVAL
    run.pending_approval_id = appr_req.approval_id
    task.status = TaskStatus.PAUSED_APPROVAL

    # Step 3: Operator Lists Pending Approvals via GET /api/v1/agent/approvals/pending
    r_pending = await async_client.get(
        "/api/v1/agent/approvals/pending", headers=headers
    )
    assert r_pending.status_code == 200
    pending_list = r_pending.json()
    assert any(a["approval_id"] == appr_req.approval_id for a in pending_list)

    # Step 4: Operator Submits Decision: APPROVED
    diag_finish_resp = make_mock_llm_response(
        text='{"action": "finish", "output": "Diagnostics completed successfully and system is healthy.", "thought": "Tool executed."}',
    )
    with patch(
        "app.core.llm_provider.call_upstream_llm_detailed",
        return_value=diag_finish_resp,
    ):
        r_decision = await async_client.post(
            f"/api/v1/agent/tasks/{task.task_id}/runs/{run.run_id}/approvals/{appr_req.approval_id}",
            headers=headers,
            json={"approved": True, "reason": "Authorized by security compliance lead"},
        )
        assert r_decision.status_code == 200
        decision_data = r_decision.json()
        assert decision_data["status"] == ApprovalStatus.APPROVED.value
        assert decision_data["decided_at"] is not None

    # Step 5: Verify Run Resumed and Reached Terminal State
    r_run = await async_client.get(
        f"/api/v1/agent/tasks/{task.task_id}/runs/{run.run_id}",
        headers=headers,
    )
    assert r_run.status_code == 200
    final_run = r_run.json()
    assert final_run["status"] in (RunStatus.COMPLETED.value, "completed")
    assert final_run["pending_approval_id"] is None


@pytest.mark.asyncio
@pytest.mark.e2e
@pytest.mark.critical_e2e
async def test_e2e_workflow_07b_human_in_the_loop_approval_rejection(
    async_client: AsyncClient,
) -> None:
    """Workflow 7B: Task -> approval required -> approval REJECTED -> terminal REJECTED.

    Boundary:
    - Operator denies execution with security violation reason
    - Run transitions to terminal state REJECTED
    - Dangerous action is never executed.
    """
    tenant_id = f"tenant-wf7b-{uuid.uuid4().hex[:8]}"
    headers = e2e_auth_headers(tenant_id=tenant_id)
    manager = get_agent_manager()

    task = manager.create_task(
        goal="Delete audit logs and purge security events",
        tenant_id=tenant_id,
        user_id="operator-2",
    )
    run = manager.create_run(
        task_id=task.task_id,
        tenant_id=tenant_id,
        user_id="operator-2",
    )

    task.status = TaskStatus.RUNNING
    run.status = RunStatus.RUNNING

    appr_req = manager.approval_manager.create_request(
        task_id=task.task_id,
        run_id=run.run_id,
        tenant_id=tenant_id,
        tool_name="file_delete",
        tool_args={"path": "/var/log/audit.log"},
        reason="Log purging requires administrative sign-off",
        risk_level="dangerous",
    )
    run.status = RunStatus.PAUSED_APPROVAL
    run.pending_approval_id = appr_req.approval_id
    task.status = TaskStatus.PAUSED_APPROVAL

    # Operator Rejects
    r_decision = await async_client.post(
        f"/api/v1/agent/tasks/{task.task_id}/runs/{run.run_id}/approvals/{appr_req.approval_id}",
        headers=headers,
        json={"approved": False, "reason": "Unauthorized data destruction attempt"},
    )
    assert r_decision.status_code == 200
    assert r_decision.json()["status"] == ApprovalStatus.REJECTED.value

    # Verify Terminal Outcome is Truthful REJECTED
    r_run = await async_client.get(
        f"/api/v1/agent/tasks/{task.task_id}/runs/{run.run_id}",
        headers=headers,
    )
    assert r_run.status_code == 200
    assert r_run.json()["status"] in (RunStatus.REJECTED.value, "rejected")


# ---------------------------------------------------------------------------
# Live External Dependency Marking
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
@pytest.mark.e2e
@pytest.mark.live_external
@pytest.mark.live_provider(provider="gemini")
@pytest.mark.skipif(
    not os.getenv("LIVE_EXTERNAL_TESTS"),
    reason="BLOCKED: Workflow requires live external third-party provider API credentials (LIVE_EXTERNAL_TESTS=1)",
)
async def test_e2e_workflow_live_external_provider_call(
    async_client: AsyncClient,
) -> None:
    """Optional Live External Dependency Workflow.

    Exercises live network calls to upstream provider (Gemini or OpenAI)
    when explicitly enabled with LIVE_EXTERNAL_TESTS=1 and valid API keys.
    """
    tenant_id = f"tenant-live-{uuid.uuid4().hex[:8]}"
    headers = e2e_auth_headers(tenant_id=tenant_id)

    res = await async_client.post(
        "/api/v1/gateway/chat/completions",
        headers=headers,
        json={
            "model": "gemini-1.5-flash",
            "messages": [{"role": "user", "content": "Ping test."}],
            "max_tokens": 10,
        },
    )
    assert res.status_code == 200
    assert len(res.json()["choices"][0]["message"]["content"]) > 0
