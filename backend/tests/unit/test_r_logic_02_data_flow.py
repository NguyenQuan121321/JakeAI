"""R-LOGIC-02 — Data Flow Verification Test Suite.

Traces critical identity/context data from ingress to egress and proves it is
not dropped, overwritten, defaulted, mistenanted, or stale:

DF-A  Identity propagation (HTTP boundary, real JWT): the correlation_id,
      roles, and permissions presented at run start survive into the RunState,
      its durable checkpoint, and the tool execution context.
DF-B  Approval binding: an approval decision submitted against the wrong run
      cannot finalize the gate (the decision must match run and task).
DF-C  LangGraph thread isolation: checkpointer thread state is namespaced per
      tenant, so one tenant's retrieved evidence can never leak into another
      tenant's workflow through a shared conversation id.
DF-D  Cache correctness: the chat response cache identity includes the
      model-visible RAG/dynamic context, so a cached answer generated against
      one retrieval context is never served for a different one.
DF-E  Model/provider flow: the chat path honors the requested model at the
      dispatcher, records the actually-served model and provider telemetry in
      accounting, and normalizes the absent-model default; the gateway
      response reports the served model, not the requested one.
DF-F  Scope correctness: the resume bridge fails closed when a checkpoint
      record carries no tenant; null JWT scopes are handled gracefully; the
      FinnApiGo tool default tenant matches the platform default.

Classification: HTTP/API behavior is exercised through the real FastAPI app
(ASGI transport + real JWT auth); upstream model calls are controlled doubles
at the module boundary (they verify data flow, not live provider integration).
"""

from __future__ import annotations

import json
import time
import uuid
from typing import Any
from unittest.mock import AsyncMock, MagicMock, patch

import jwt as pyjwt
import pytest
from httpx import ASGITransport, AsyncClient

from app.agent.approvals.manager import ApprovalManager
from app.agent.approvals.models import ApprovalDecision, ApprovalStatus
from app.agent.backends.jakeai import JakeAIBackend
from app.agent.runtime.manager import AgentRuntimeManager
from app.agent.state.models import RunStatus
from app.agents.finnapigo_tool import finnapigo_tool_node
from app.core.config import get_settings
from app.core.context import TenantContext
from app.main import app
from app.optimizer.semantic_cache import (
    CACHE_VERSION,
    SemanticCacheManager,
    compute_cache_identity,
)
from app.providers.base import ProviderCacheTelemetry, UpstreamLLMResponse
from app.services.resume_bridge import ResumeBridgeManager

_UNSET = object()


def make_jwt(
    tenant_id: str,
    user_id: str = "user-df",
    roles: list[str] | None = None,
    permissions: list[str] | None = None,
    scopes: Any = _UNSET,
) -> str:
    settings = get_settings()
    now = int(time.time())
    payload: dict[str, Any] = {
        "sub": user_id,
        "tenant_id": tenant_id,
        "iat": now,
        "exp": now + 3600,
        "roles": roles if roles is not None else ["admin", "operator"],
        "permissions": permissions
        if permissions is not None
        else ["agent:read", "agent:write", "tools:execute"],
    }
    if scopes is not _UNSET:
        payload["scopes"] = scopes  # may be explicitly None (present-but-null claim)
    return pyjwt.encode(payload, settings.JWT_SECRET_KEY, algorithm="HS256")


def tool_call_payload(tool_name: str, arguments: dict[str, Any]) -> dict[str, Any]:
    return {
        "content": f"```json\n{json.dumps({'action': 'tool_call', 'tool_name': tool_name, 'arguments': arguments, 'thought': 'need tool'})}\n```",
        "prompt_tokens": 40,
        "completion_tokens": 25,
        "total_tokens": 65,
        "model": "gpt-4o",
        "cost_usd": 0.0002,
    }


def finish_payload(output: str) -> dict[str, Any]:
    return {
        "content": f'{{"action": "finish", "output": "{output}", "thought": "done"}}',
        "prompt_tokens": 15,
        "completion_tokens": 10,
        "total_tokens": 25,
        "model": "gpt-4o",
        "cost_usd": 0.00003,
    }


def make_context(tenant_id: str) -> TenantContext:
    return TenantContext(
        tenant_id=tenant_id,
        user_id="user-df",
        roles=["admin"],
        permissions=["tools:execute"],
        correlation_id=f"corr-{tenant_id}",
    )


# ===========================================================================
# DF-A — Identity propagation (correlation_id / roles / permissions)
# ===========================================================================


@pytest.mark.asyncio
async def test_http_run_carries_request_identity() -> None:
    """The authenticated correlation_id, roles, and permissions must be persisted
    on the RunState they belong to (RL02-F-01 / RL02-F-02).

    EXPECTED: run.correlation_id == X-Correlation-ID sent by the client; run
    roles/permissions == the JWT claims of the caller that started the run.
    ACTUAL (pre-fix): create_run never populated the fields — the run record
    carried correlation_id=None and empty roles/permissions, and that null
    context was checkpointed and forwarded to tool execution.
    """
    tenant = f"tenant-df-{uuid.uuid4().hex[:8]}"
    correlation_id = f"corr-df-{uuid.uuid4().hex[:8]}"
    headers = {
        "Authorization": f"Bearer {make_jwt(tenant)}",
        "X-Correlation-ID": correlation_id,
    }

    with patch(
        "app.agent.backends.jakeai.call_upstream_llm_detailed",
        new_callable=AsyncMock,
        side_effect=[tool_call_payload("terminal_exec", {"command": "ls /tmp"})],
    ):
        async with AsyncClient(
            transport=ASGITransport(app=app), base_url="http://testserver"
        ) as client:
            res = await client.post(
                "/api/v1/agent/tasks",
                headers=headers,
                json={"goal": "identity propagation probe"},
            )
            assert res.status_code == 201, res.text
            task_id = res.json()["task_id"]

            res = await client.post(
                f"/api/v1/agent/tasks/{task_id}/runs",
                headers=headers,
                json={"async_execution": False},
            )
            assert res.status_code == 201, res.text
            run_id = res.json()["run_id"]

            res = await client.get(
                f"/api/v1/agent/tasks/{task_id}/runs/{run_id}", headers=headers
            )
            assert res.status_code == 200, res.text
            run = res.json()

    assert run["correlation_id"] == correlation_id, (
        f"run lost the caller correlation_id: {run['correlation_id']!r}"
    )
    assert run["roles"] == ["admin", "operator"], (
        f"run lost the caller roles: {run['roles']!r}"
    )
    assert run["permissions"] == ["agent:read", "agent:write", "tools:execute"], (
        f"run lost the caller permissions: {run['permissions']!r}"
    )


@pytest.mark.asyncio
async def test_run_identity_survives_checkpoint_restore_roundtrip() -> None:
    """Identity fields must survive the durable checkpoint round-trip
    (RL02-F-01 / RL02-F-02).

    EXPECTED: after a process boundary (in-memory store purged, run restored
    from its checkpoint), the restored run still carries the caller's
    correlation_id, roles, and permissions.
    ACTUAL (pre-fix): the fields were never written, so the checkpointed
    record and every restored run had correlation_id=None and empty authz.
    """
    from app.agent.runtime.manager import get_agent_manager

    tenant = f"tenant-df-{uuid.uuid4().hex[:8]}"
    correlation_id = f"corr-df-{uuid.uuid4().hex[:8]}"
    headers = {
        "Authorization": f"Bearer {make_jwt(tenant)}",
        "X-Correlation-ID": correlation_id,
    }
    manager = get_agent_manager()

    with patch(
        "app.agent.backends.jakeai.call_upstream_llm_detailed",
        new_callable=AsyncMock,
        side_effect=[tool_call_payload("terminal_exec", {"command": "ls /tmp"})],
    ):
        async with AsyncClient(
            transport=ASGITransport(app=app), base_url="http://testserver"
        ) as client:
            res = await client.post(
                "/api/v1/agent/tasks",
                headers=headers,
                json={"goal": "checkpoint identity probe"},
            )
            task_id = res.json()["task_id"]
            res = await client.post(
                f"/api/v1/agent/tasks/{task_id}/runs",
                headers=headers,
                json={"async_execution": False},
            )
            assert res.status_code == 201, res.text
            run_id = res.json()["run_id"]

    # Simulate a process restart: drop the in-memory run store and force the
    # checkpoint restore path through the HTTP boundary.
    manager._runs.clear()
    async with AsyncClient(
        transport=ASGITransport(app=app), base_url="http://testserver"
    ) as client:
        res = await client.get(
            f"/api/v1/agent/tasks/{task_id}/runs/{run_id}", headers=headers
        )
        assert res.status_code == 200, res.text
        restored = res.json()

    assert restored["run_id"] == run_id
    assert restored["status"] == RunStatus.PAUSED_APPROVAL.value
    assert restored["correlation_id"] == correlation_id, (
        f"checkpoint restore lost correlation_id: {restored['correlation_id']!r}"
    )
    assert restored["roles"] == ["admin", "operator"], (
        f"checkpoint restore lost roles: {restored['roles']!r}"
    )
    assert restored["permissions"] == ["agent:read", "agent:write", "tools:execute"], (
        f"checkpoint restore lost permissions: {restored['permissions']!r}"
    )


@pytest.mark.asyncio
async def test_tool_context_receives_run_correlation_id() -> None:
    """Tool execution context must carry the run's correlation_id
    (RL02-F-01 — tool/telemetry leg of the trace).

    EXPECTED: the context dict handed to ToolRegistry.execute contains the
    correlation_id assigned to the run at creation time.
    ACTUAL (pre-fix): create_run left RunState.correlation_id=None, so every
    tool execution and its telemetry were uncorrelated to the request.
    """
    captured_contexts: list[dict[str, Any]] = []

    mock_registry = MagicMock()
    mock_tool = MagicMock()
    mock_tool.name = "capture_ctx"
    mock_tool.is_dangerous = False
    mock_registry.get.return_value = mock_tool
    mock_registry.discover.return_value = [mock_tool]

    async def mock_execute(tool_name, arguments, context):
        captured_contexts.append(context)
        res = MagicMock()
        res.success = True
        res.output = "ok"
        res.error = None
        return res

    mock_registry.execute = AsyncMock(side_effect=mock_execute)

    manager = AgentRuntimeManager(
        backend=JakeAIBackend(),
        tool_registry=mock_registry,
        approval_manager=ApprovalManager(),
    )
    correlation_id = f"corr-tool-{uuid.uuid4().hex[:8]}"

    with patch(
        "app.agent.backends.jakeai.call_upstream_llm_detailed",
        new_callable=AsyncMock,
        side_effect=[
            tool_call_payload("capture_ctx", {"probe": 1}),
            finish_payload("finished"),
        ],
    ):
        task = manager.create_task("identity tool probe", "tenant-df-tool", "user-df")
        run = manager.create_run(
            task_id=task.task_id,
            tenant_id="tenant-df-tool",
            user_id="user-df",
            correlation_id=correlation_id,
            roles=["admin"],
            permissions=["tools:execute"],
        )
        await manager.execute_run(
            task_id=task.task_id,
            run_id=run.run_id,
            tenant_id="tenant-df-tool",
            user_roles=["admin"],
            user_permissions=["tools:execute"],
        )

    assert len(captured_contexts) == 1
    ctx = captured_contexts[0]
    assert ctx.get("correlation_id") == correlation_id, (
        f"tool context lost the run correlation_id: {ctx.get('correlation_id')!r}"
    )
    assert ctx.get("tenant_id") == "tenant-df-tool"


@pytest.mark.asyncio
async def test_approval_decision_rejects_cross_run_binding() -> None:
    """An approval decision must be bound to the run in the request path
    (RL02-F-06).

    EXPECTED: submitting run A's approval_id against run B's decision URL is
    refused with ValueError (HTTP 409) and the approval stays PENDING.
    ACTUAL (pre-fix): decide_approval finalized the gate first and only
    detected the mismatch afterwards in the runner, leaving the approval
    consumed (APPROVED) while its own run was never resumed.
    """
    manager = AgentRuntimeManager(
        backend=JakeAIBackend(),
        tool_registry=MagicMock(),
        approval_manager=ApprovalManager(),
    )
    task = manager.create_task("approval binding probe", "tenant-df-appr", "user-df")
    run_a = manager.create_run(task.task_id, "tenant-df-appr", "user-df")
    run_b = manager.create_run(task.task_id, "tenant-df-appr", "user-df")

    appr = manager.approval_manager.create_request(
        task_id=task.task_id,
        run_id=run_a.run_id,
        tenant_id="tenant-df-appr",
        tool_name="terminal_exec",
        tool_args={"command": "ls"},
        reason="dangerous action",
    )

    with pytest.raises(ValueError):
        await manager.decide_approval(
            task_id=task.task_id,
            run_id=run_b.run_id,
            approval_id=appr.approval_id,
            decision=ApprovalDecision(approved=True, reason="mistaken submit"),
            tenant_id="tenant-df-appr",
            user_id="user-df",
        )

    stored = manager.approval_manager.get_request(appr.approval_id, "tenant-df-appr")
    assert stored.status == ApprovalStatus.PENDING, (
        f"cross-run decision mutated the gate to {stored.status}; run "
        f"{run_a.run_id} can no longer be resumed by its own decision"
    )

    # The correct-run decision still works.
    decided = await manager.decide_approval(
        task_id=task.task_id,
        run_id=run_a.run_id,
        approval_id=appr.approval_id,
        decision=ApprovalDecision(approved=True),
        tenant_id="tenant-df-appr",
        user_id="user-df",
    )
    assert decided.status == ApprovalStatus.APPROVED


# ===========================================================================
# DF-C — LangGraph thread isolation across tenants
# ===========================================================================


@pytest.mark.asyncio
async def test_langgraph_thread_state_does_not_leak_across_tenants() -> None:
    """Checkpointer thread state must be tenant-namespaced (RL02-F-03).

    EXPECTED: two tenants using the same conversation id run in isolated
    checkpointer threads; tenant B's workflow can never observe tenant A's
    retrieved evidence left in the shared thread.
    ACTUAL (pre-fix): thread_id == client-supplied conversation_id against a
    process-global checkpointer — tenant B's run inherited tenant A's
    retrieved_chunks, skipped its own retrieval, and cited tenant A's
    confidential chunks in its answer.
    """
    from app.agents.graph import agent_graph, stream_multi_agent_workflow

    shared_conversation = f"leak-conv-{uuid.uuid4().hex[:8]}"

    # Seed the shared thread with tenant A's retrieved evidence — exactly the
    # state a tenant-A run leaves behind on the (pre-fix) shared thread.
    tenant_a_chunks = [
        {
            "chunk_id": "A-SECRET-1",
            "content": (
                "SECRET-TENANT-A-MARKER financial intelligence report tenant "
                "status verified JakeAI multi-agent pipeline operations ledger"
            ),
            "tenant_id": "tenant-a-leak",
            "source": "tenant-a-classified.pdf",
            "metadata": {},
            "score": 0.9,
        }
    ]
    await agent_graph.aupdate_state(
        {"configurable": {"thread_id": shared_conversation}},
        {"retrieved_chunks": tenant_a_chunks},
    )

    tenant_b = make_context("tenant-b-leak")
    events: list[dict[str, Any]] = []
    async for event in stream_multi_agent_workflow(
        "hello there", tenant_b, shared_conversation
    ):
        events.append(event)

    blob = json.dumps(events, default=str)
    assert "SECRET-TENANT-A-MARKER" not in blob, (
        "tenant B's workflow observed tenant A's retrieved evidence through the "
        "shared checkpointer thread"
    )
    assert "tenant-a-classified.pdf" not in blob, (
        "tenant B's answer cited tenant A's document source"
    )


# ===========================================================================
# DF-D — Cache identity includes model-visible retrieval context
# ===========================================================================


@pytest.mark.asyncio
async def test_chat_cache_does_not_serve_stale_answer_across_rag_contexts() -> None:
    """The chat response cache must not serve an answer generated against one
    RAG context for a request carrying a different one (RL02-F-04).

    EXPECTED: identical prompt/history but different supplied rag_context
    produces a cache MISS (the retrieval context is model-visible input).
    ACTUAL (pre-fix): rag_context was absent from the cache identity — the
    second request was served the first request's cached answer with citations
    grounded in the old corpus state.
    """
    from app.api.v1.endpoints.chat import _semantic_cache, generate_chat_stream

    await _semantic_cache.invalidate()
    tenant_id = f"tenant-cache-{uuid.uuid4().hex[:8]}"
    context = make_context(tenant_id)

    async def run_stream(conversation_id: str, rag_context: str) -> list[str]:
        chunks: list[str] = []
        async for chunk in generate_chat_stream(
            prompt="cache staleness probe",
            context=context,
            conversation_id=conversation_id,
            parameters={"rag_context": rag_context},
        ):
            chunks.append(chunk)
        return chunks

    rag_a = "Quarterly filing content set ALPHA with revenue 111111."
    rag_b = "Completely different manual content set BETA with revenue 222222."

    first = await run_stream(f"conv-{uuid.uuid4().hex[:8]}", rag_a)
    assert not any("cache_hit" in chunk for chunk in first), (
        "first request unexpectedly hit the cache"
    )

    second = await run_stream(f"conv-{uuid.uuid4().hex[:8]}", rag_b)
    assert not any("cache_hit" in chunk for chunk in second), (
        "stale cached answer served for a request with a different RAG context"
    )


@pytest.mark.asyncio
async def test_semantic_cache_context_dimension_at_service_boundary() -> None:
    """SemanticCacheManager get/set must accept and isolate the retrieval
    context dimension (RL02-F-04 — exact and semantic tiers).

    EXPECTED: entries cached under rag context A are not returned for the same
    prompt under rag context B (exact tier via identity, semantic tier via the
    compatibility guard).
    """
    manager = SemanticCacheManager()
    prompt = "context dimension probe"

    await manager.set(
        prompt=prompt,
        tenant_id="tenant-df-cache",
        response="answer generated against context ALPHA",
        provider="openai",
        model="gpt-4o",
        rag_context="ALPHA retrieval content",
    )

    hit_alpha = await manager.get(
        prompt=prompt,
        tenant_id="tenant-df-cache",
        provider="openai",
        model="gpt-4o",
        rag_context="ALPHA retrieval content",
    )
    assert hit_alpha is not None, "identical context must exact-hit"

    miss_beta = await manager.get(
        prompt=prompt,
        tenant_id="tenant-df-cache",
        provider="openai",
        model="gpt-4o",
        rag_context="BETA retrieval content",
    )
    assert miss_beta is None, (
        f"cached answer from context ALPHA served under context BETA "
        f"(type={miss_beta.cache_type if miss_beta else None})"
    )

    # Identical context still hits.
    hit_alpha_again = await manager.get(
        prompt=prompt,
        tenant_id="tenant-df-cache",
        provider="openai",
        model="gpt-4o",
        rag_context="ALPHA retrieval content",
    )
    assert hit_alpha_again is not None


def test_cache_identity_includes_retrieval_context_dimension() -> None:
    """compute_cache_identity must fold rag/dynamic context into the identity."""
    base = {
        "tenant_id": "t",
        "provider": "openai",
        "model": "gpt-4o",
        "system_instructions": "sys",
        "messages": [{"role": "user", "content": "hi"}],
    }
    ident_a = compute_cache_identity(**base, rag_context="ALPHA", dynamic_context="D")
    ident_b = compute_cache_identity(**base, rag_context="BETA", dynamic_context="D")
    ident_plain = compute_cache_identity(**base)
    assert ident_a != ident_b
    assert ident_a != ident_plain
    # Identical inputs produce identical identities (determinism).
    assert ident_a == compute_cache_identity(
        **base, rag_context="ALPHA", dynamic_context="D"
    )


# ===========================================================================
# DF-E — Model/provider/token usage flow
# ===========================================================================


@pytest.mark.asyncio
async def test_chat_stream_records_served_model_and_provider_telemetry() -> None:
    """The requested model must reach the LLM dispatcher, and accounting must
    record the actually-served model and provider telemetry (RL02-F-05).

    EXPECTED: dispatcher called with model="gpt-4o" (the request's parameter);
    TokenAccounting records model="gpt-4o-x" (the served model) and the
    provider telemetry returned by the dispatch; the done frame names the
    served model.
    ACTUAL (pre-fix): the synthesizer dropped the model entirely (dispatcher
    default applied), accounting priced the client-asserted label, and the
    provider telemetry event key was never emitted by the workflow.
    """
    from app.api.v1.endpoints.chat import generate_chat_stream
    from app.optimizer.token_accounting import TokenAccounting, TokenUsageRecord

    served = UpstreamLLMResponse(
        text="SERVED-MODEL-PROOF answer body",
        model="gpt-4o-x",
        provider="openai",
        telemetry=ProviderCacheTelemetry(
            uncached_input_tokens=120,
            output_tokens=30,
        ),
    )
    tenant_id = f"tenant-df-model-{uuid.uuid4().hex[:8]}"
    context = make_context(tenant_id)

    with (
        patch(
            "app.core.llm_provider.call_upstream_llm_detailed",
            new_callable=AsyncMock,
            return_value=served,
        ) as mock_llm,
        patch(
            "app.optimizer.token_accounting.TokenAccounting.record_transaction",
            wraps=TokenAccounting.record_transaction,
        ) as mock_record,
    ):
        mock_record.return_value = TokenUsageRecord(
            request_id="test",
            tenant_id=tenant_id,
            model="gpt-4o-x",
            raw_input_tokens=150,
            optimized_input_tokens=100,
            completion_tokens=30,
            actual_billed_tokens=130,
            tokens_saved=20,
            reduction_percentage=13.3,
            cache_hit=False,
            cache_type="none",
        )
        events = [
            chunk
            async for chunk in generate_chat_stream(
                prompt="model flow probe",
                context=context,
                conversation_id=f"conv-{uuid.uuid4().hex[:8]}",
                parameters={"model": "gpt-4o"},
            )
        ]

    assert mock_llm.call_count >= 1, (
        "the workflow never dispatched through the LLM dispatcher with the "
        "request's model"
    )
    dispatch_models = [call.kwargs.get("model") for call in mock_llm.call_args_list]
    assert "gpt-4o" in dispatch_models, (
        f"dispatcher was not called with the requested model; got {dispatch_models}"
    )

    assert mock_record.called, "no token accounting recorded"
    record_kwargs = mock_record.call_args.kwargs
    assert record_kwargs["model"] == "gpt-4o-x", (
        f"accounting recorded model {record_kwargs['model']!r} instead of the "
        "actually-served model"
    )
    assert record_kwargs.get("provider_telemetry") is served.telemetry, (
        "provider telemetry was not propagated into token accounting"
    )

    done_frames = [e for e in events if "event: done" in e]
    assert done_frames and "gpt-4o-x" in done_frames[-1], (
        "done frame does not report the served model"
    )


@pytest.mark.asyncio
async def test_chat_stream_normalizes_default_model_for_accounting() -> None:
    """A request without a model parameter must be accounted under the model
    that actually serves it, not the fictional label "default" (RL02-F-05).

    EXPECTED: record_transaction(model="gemini-1.5-flash") — the dispatcher's
    effective default — so cost pricing reflects the real serving tier.
    ACTUAL (pre-fix): model_name defaulted to the string "default", which
    priced the request at the fallback pricing catalog (~27x the real rate).
    """
    from app.api.v1.endpoints.chat import generate_chat_stream
    from app.optimizer.token_accounting import TokenAccounting, TokenUsageRecord

    tenant_id = f"tenant-df-defmodel-{uuid.uuid4().hex[:8]}"
    context = make_context(tenant_id)

    with patch(
        "app.optimizer.token_accounting.TokenAccounting.record_transaction",
        wraps=TokenAccounting.record_transaction,
    ) as mock_record:
        mock_record.return_value = TokenUsageRecord(
            request_id="test",
            tenant_id=tenant_id,
            model="gemini-1.5-flash",
            raw_input_tokens=100,
            optimized_input_tokens=80,
            completion_tokens=10,
            actual_billed_tokens=90,
            tokens_saved=10,
            reduction_percentage=10.0,
            cache_hit=False,
            cache_type="none",
        )
        _ = [
            chunk
            async for chunk in generate_chat_stream(
                prompt="default model probe",
                context=context,
                conversation_id=f"conv-{uuid.uuid4().hex[:8]}",
                parameters={},
            )
        ]

    assert mock_record.called
    assert mock_record.call_args.kwargs["model"] == "gemini-1.5-flash", (
        f"absent-model request accounted as {mock_record.call_args.kwargs['model']!r}"
    )


@pytest.mark.asyncio
async def test_gateway_response_reports_served_model() -> None:
    """The OpenAI-compatible gateway response must name the model that actually
    served the request (RL02-F-09).

    EXPECTED: after failover/rerouting the response `model` field is the served
    model, consistent with what accounting and FinOps recorded.
    ACTUAL (pre-fix): the response echoed request.model even when a different
    candidate served the request.
    """
    served = UpstreamLLMResponse(
        text="gateway served proof",
        model="gpt-4o-x-served",
        provider="openai",
        telemetry=ProviderCacheTelemetry(uncached_input_tokens=50, output_tokens=10),
    )
    tenant = f"tenant-df-gw-{uuid.uuid4().hex[:8]}"
    headers = {"Authorization": f"Bearer {make_jwt(tenant)}"}

    with patch(
        "app.services.ai_gateway.call_upstream_llm_detailed",
        new_callable=AsyncMock,
        return_value=served,
    ):
        async with AsyncClient(
            transport=ASGITransport(app=app), base_url="http://testserver"
        ) as client:
            res = await client.post(
                "/api/v1/gateway/chat/completions",
                headers=headers,
                json={
                    "model": "gpt-4o",
                    "messages": [{"role": "user", "content": "gateway probe"}],
                },
            )
    assert res.status_code == 200, res.text
    data = res.json()
    assert data["model"] == "gpt-4o-x-served", (
        f"gateway response reported requested model {data['model']!r} instead "
        "of the served model"
    )


# ===========================================================================
# DF-F — Scope correctness (resume bridge, JWT claims, tool defaults)
# ===========================================================================


@pytest.mark.asyncio
async def test_resume_bridge_fails_closed_on_unscoped_checkpoint() -> None:
    """A checkpoint record without a tenant must not be resumable by any
    caller (RL02-F-11).

    EXPECTED: resume_checkpoint raises PermissionError when the stored record
    lacks tenant_id — the caller's ownership cannot be verified.
    ACTUAL (pre-fix): `if cp_tenant and cp_tenant != tenant_id` failed open —
    an unscoped record was applied for whatever tenant submitted the result.
    """
    bridge = ResumeBridgeManager()
    bridge._memory_checkpoints["call-unscoped"] = {
        "call_id": "call-unscoped",
        "state_data": {"op": "probe"},
        "created_at": time.time(),
        "status": "pending",
    }

    with pytest.raises(PermissionError):
        await bridge.resume_checkpoint(
            "call-unscoped", {"result": 1}, tenant_id="tenant-df-bridge"
        )


@pytest.mark.asyncio
async def test_jwt_null_scopes_claim_handled_gracefully() -> None:
    """A JWT whose scopes claim is present but null must not crash request
    handling (RL02-F-12).

    EXPECTED: null scopes are treated as an empty scope set (mirroring the
    roles/permissions fallbacks) and the request proceeds.
    ACTUAL (pre-fix): payload.get("scopes", []) returned None → TypeError →
    HTTP 500 on every authenticated endpoint.
    """
    tenant = f"tenant-df-scopes-{uuid.uuid4().hex[:8]}"
    headers = {"Authorization": f"Bearer {make_jwt(tenant, scopes=None)}"}
    async with AsyncClient(
        transport=ASGITransport(app=app), base_url="http://testserver"
    ) as client:
        res = await client.get("/api/v1/agent/approvals/pending", headers=headers)
    assert res.status_code == 200, (
        f"null scopes claim produced {res.status_code} instead of a handled "
        f"response: {res.text}"
    )


@pytest.mark.asyncio
async def test_finnapigo_tool_default_tenant_matches_platform_default() -> None:
    """The FinnApiGo tool node's missing-tenant default must match the
    platform's tenant default ("default", per core/security.py) — not a third
    divergent namespace (RL02-F-13).

    EXPECTED: state without tenant_id resolves to tenant "default".
    ACTUAL (pre-fix): the tool node defaulted to "default_tenant" — the same
    missing-claim condition landed in a different tenant namespace than the
    security layer's "default".
    """
    result = await finnapigo_tool_node({"prompt": "Show me account limits please"})
    blob = json.dumps(result, default=str)
    assert '"default_tenant"' not in blob and "default_tenant" not in blob, (
        "finnapigo tool node used the divergent default_tenant namespace"
    )
    assert "default" in blob


# ===========================================================================
# CACHE_VERSION hygiene — the identity schema change must be visible
# ===========================================================================


def test_cache_version_bumped_for_context_dimension() -> None:
    """The identity schema gained the retrieval-context dimension; the version
    tag must move so stale pre-change entries can never alias new ones."""
    assert CACHE_VERSION != "v2.0", (
        "cache identity schema changed (retrieval-context dimension) without "
        "a version bump"
    )
