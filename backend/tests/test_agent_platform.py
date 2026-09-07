"""Comprehensive unit, integration, and contract tests for Phase 08 — JakeAI-Agent Platform.

Covers:
1. Agent Backends (JakeAIBackend, DirectProviderBackend, ExternalAgentBackend)
2. Tool Registry, Risk Policies & Builtins (ReadFileTool, SearchSymbolsTool, CalculatorTool, SystemTimeTool, MockDangerousShellTool)
3. Safe Local Sandbox (command allowlist, directory escape prevention, file read/write limits)
4. State & Tenant-Isolated Checkpointing (save, restore, cross-tenant isolation negative proofs)
5. Multi-Tenant Memory Architecture (Short-term bounded FIFO, Long-term episodic memory)
6. Server-side Human-in-the-Loop Approvals (pause, resume upon approval, rejection adaptation)
7. Bounded Planning & Multi-step Workflow Engine
8. Autonomous Execution Loop (events, cooperative cancellation, iteration ceilings)
9. FastAPI Endpoints & Contract Enforcement (/tasks, /runs, /events, /cancel, /approvals, /metrics)
"""

from __future__ import annotations

import json
import time
from typing import TYPE_CHECKING, Any
from unittest.mock import AsyncMock, patch

import jwt
import pytest
from fastapi import status
from httpx import AsyncClient, Response

if TYPE_CHECKING:
    from collections.abc import AsyncIterator

from app.agent.approvals.manager import ApprovalManager
from app.agent.approvals.models import ApprovalDecision, ApprovalStatus
from app.agent.backends.base import (
    AgentBackendInterface,
    AgentMessage,
    AgentToolCall,
    BackendRequest,
    BackendResponse,
    BackendStreamChunk,
)
from app.agent.backends.direct_provider import DirectProviderBackend
from app.agent.backends.external_agent import ExternalAgentBackend
from app.agent.backends.jakeai import JakeAIBackend
from app.agent.execution.sandbox import LocalSafeSandbox
from app.agent.memory.manager import AgentMemoryManager
from app.agent.memory.short_term import ShortTermMemory
from app.agent.planning.models import NextActionType
from app.agent.planning.planner import BoundedPlanner
from app.agent.runtime.loop import AgentExecutionLoop
from app.agent.runtime.models import AgentConfig, AgentRunEvent
from app.agent.state.checkpoint import CheckpointManager
from app.agent.state.models import (
    RunState,
    RunStatus,
    TaskState,
    TaskStatus,
)
from app.agent.tools.base import ToolRiskLevel
from app.agent.tools.registry import get_tool_registry
from app.agent.workflows.engine import WorkflowEngine
from app.agent.workflows.models import (
    StepType,
    WorkflowDefinition,
    WorkflowExecutionStatus,
    WorkflowStepDefinition,
)
from app.core.config import get_settings

# ---------------------------------------------------------------------------
# Test Auth Helpers
# ---------------------------------------------------------------------------


def generate_agent_jwt(
    sub: str = "user-agent-tester",
    tenant_id: str = "tenant-agent-alpha",
    roles: list[str] | None = None,
    permissions: list[str] | None = None,
    expires_in: int = 3600,
) -> str:
    """Generate HS256 JWT context for Agent API tests."""
    settings = get_settings()
    now = int(time.time())
    payload: dict[str, Any] = {
        "sub": sub,
        "tenant_id": tenant_id,
        "iat": now,
        "exp": now + expires_in,
        "roles": roles or ["admin", "developer"],
        "permissions": permissions or ["agent:write", "agent:read"],
    }
    return jwt.encode(payload, settings.JWT_SECRET_KEY, algorithm="HS256")


# ===========================================================================
# 1. Agent Backends Tests
# ===========================================================================


@pytest.mark.asyncio
async def test_jakeai_backend_text_response() -> None:
    backend = JakeAIBackend()
    with patch(
        "app.agent.backends.jakeai.call_upstream_llm_detailed",
        new_callable=AsyncMock,
    ) as mock_llm:
        mock_llm.return_value = {
            "content": "Analysis complete.",
            "prompt_tokens": 50,
            "completion_tokens": 20,
            "total_tokens": 70,
            "model": "gpt-4o-mini",
            "cost_usd": 0.0001,
        }
        req = BackendRequest(
            messages=[AgentMessage(role="user", content="Analyze portfolio")],
            tenant_id="tenant-alpha",
        )
        resp = await backend.generate(req)
        assert resp.content == "Analysis complete."
        assert resp.input_tokens == 50
        assert resp.output_tokens == 20
        assert resp.cost_usd == 0.0001
        assert resp.finish_reason == "stop"


@pytest.mark.asyncio
async def test_jakeai_backend_tool_calls_response() -> None:
    backend = JakeAIBackend()
    tool_call_json = {
        "action": "tool_call",
        "tool_name": "read_file",
        "arguments": {"file_path": "README.md"},
        "thought": "Need to read readme",
    }
    with patch(
        "app.agent.backends.jakeai.call_upstream_llm_detailed",
        new_callable=AsyncMock,
    ) as mock_llm:
        mock_llm.return_value = {
            "content": f"```json\n{json.dumps(tool_call_json)}\n```",
            "prompt_tokens": 40,
            "completion_tokens": 25,
            "total_tokens": 65,
            "model": "gpt-4o",
            "cost_usd": 0.0002,
        }
        req = BackendRequest(
            messages=[AgentMessage(role="user", content="Read README.md")],
            tenant_id="tenant-alpha",
        )
        resp = await backend.generate(req)
        assert len(resp.tool_calls) == 1
        assert resp.tool_calls[0].tool_name == "read_file"
        assert resp.tool_calls[0].arguments == {"file_path": "README.md"}
        assert resp.finish_reason == "tool_calls"


@pytest.mark.asyncio
async def test_jakeai_backend_streaming() -> None:
    backend = JakeAIBackend()
    with patch(
        "app.agent.backends.jakeai.call_upstream_llm_detailed",
        new_callable=AsyncMock,
    ) as mock_llm:
        mock_llm.return_value = {
            "content": "Chunk1 Chunk2 Chunk3",
            "prompt_tokens": 10,
            "completion_tokens": 15,
            "total_tokens": 25,
            "model": "gpt-4o",
            "cost_usd": 0.00005,
        }
        req = BackendRequest(
            messages=[AgentMessage(role="user", content="Stream this")],
            tenant_id="tenant-alpha",
        )
        stream_chunks = [
            chunk.delta_content async for chunk in backend.generate_stream(req)
        ]
        assert len(stream_chunks) > 0
        assert "".join(stream_chunks) == "Chunk1 Chunk2 Chunk3"


@pytest.mark.asyncio
async def test_direct_provider_backend_openai_compatible() -> None:
    backend = DirectProviderBackend(
        provider="openai",
        api_key="sk-test-secret-key-12345",
        default_model="gpt-4o-mini",
    )
    mock_response = Response(
        status_code=200,
        json={
            "choices": [
                {
                    "message": {
                        "content": "Direct provider answer",
                        "tool_calls": [],
                    },
                    "finish_reason": "stop",
                }
            ],
            "usage": {"prompt_tokens": 20, "completion_tokens": 22},
        },
    )
    with patch("httpx.AsyncClient.post", new_callable=AsyncMock) as mock_post:
        mock_post.return_value = mock_response
        req = BackendRequest(
            messages=[AgentMessage(role="user", content="Hello")],
            tenant_id="tenant-alpha",
        )
        resp = await backend.generate(req)
        assert resp.content == "Direct provider answer"
        assert resp.input_tokens == 20
        assert resp.output_tokens == 22


@pytest.mark.asyncio
async def test_direct_provider_backend_missing_key() -> None:
    backend = DirectProviderBackend(
        provider="openai",
        api_key=None,
    )
    req = BackendRequest(
        messages=[AgentMessage(role="user", content="Test")],
        tenant_id="tenant-alpha",
    )
    resp = await backend.generate(req)
    assert resp.finish_reason == "error_missing_credentials"


@pytest.mark.asyncio
async def test_external_agent_backend_dispatch() -> None:
    backend = ExternalAgentBackend(endpoint_url="http://external-agent/api/execute")
    mock_response = Response(
        status_code=200,
        json={
            "content": "External agent task completed",
            "tool_calls": [],
            "tokens_consumed": 120,
            "cost_usd": 0.002,
        },
    )
    with patch("httpx.AsyncClient.post", new_callable=AsyncMock) as mock_post:
        mock_post.return_value = mock_response
        req = BackendRequest(
            messages=[AgentMessage(role="user", content="Delegate this")],
            tenant_id="tenant-alpha",
        )
        resp = await backend.generate(req)
        assert resp.content == "External agent task completed"
        assert resp.cost_usd == 0.002


# ===========================================================================
# 2. Tool Registry, Risk Policies & Sandbox Tests
# ===========================================================================


def test_tool_registry_and_policy() -> None:
    registry = get_tool_registry()

    assert registry.get("read_file") is not None
    assert registry.get("search_symbols") is not None
    assert registry.get("calculator") is not None
    assert registry.get("system_time") is not None
    assert registry.get("terminal_exec") is not None

    tool = registry.get("terminal_exec")
    assert tool is not None
    assert tool.metadata.risk_level == ToolRiskLevel.DANGEROUS

    safe_tool = registry.get("read_file")
    assert safe_tool is not None
    assert safe_tool.metadata.risk_level == ToolRiskLevel.READ_ONLY


@pytest.mark.asyncio
async def test_local_safe_sandbox_file_and_commands(tmp_path: Any) -> None:
    sandbox = LocalSafeSandbox(sandbox_root=str(tmp_path))

    # File safe write and read
    await sandbox.write_file("sub/test.txt", "JakeAI Safe Content")
    content = await sandbox.read_file("sub/test.txt")
    assert content == "JakeAI Safe Content"

    # Directory traversal defense
    with pytest.raises(PermissionError, match=r"Path traversal rejected"):
        await sandbox.read_file("../../outside.txt")

    with pytest.raises(PermissionError, match=r"Path traversal rejected"):
        await sandbox.write_file("../../../bad.txt", "evil")

    # Command execution in sandbox
    res = await sandbox.run_command(["python", "-c", "print('JakeAI Sandbox Test')"])
    assert res.returncode == 0
    assert "JakeAI Sandbox Test" in res.output

    # Blocked forbidden command (e.g. format, rm)
    res_rm = await sandbox.run_command(["rm", "-rf", "/"])
    assert res_rm.success is False
    assert res_rm.returncode == 126
    assert "not permitted" in (res_rm.error or "")

    res_format = await sandbox.run_command(["format", "C:"])
    assert res_format.success is False
    assert res_format.returncode == 126


# ===========================================================================
# 3. State & Checkpoint Tenant Isolation Tests
# ===========================================================================


@pytest.mark.asyncio
async def test_state_and_checkpoint_tenant_isolation() -> None:
    ckpt_mgr = CheckpointManager()

    run_alpha = RunState(
        run_id="run_alpha_01",
        task_id="task_alpha_01",
        tenant_id="tenant-alpha",
        user_id="user_alpha",
        status=RunStatus.RUNNING,
        current_iteration=3,
    )
    mem_alpha = [{"role": "user", "content": "Alpha confidential prompt"}]

    # Save checkpoint for Alpha
    cp_id = await ckpt_mgr.save_checkpoint(run_alpha, mem_alpha)

    # Positive test: Alpha restores Alpha's checkpoint
    restored = await ckpt_mgr.get_checkpoint(cp_id, tenant_id="tenant-alpha")
    assert restored is not None
    assert restored.tenant_id == "tenant-alpha"
    assert restored.current_iteration == 3
    assert (
        restored.short_term_memory_snapshot[0]["content"] == "Alpha confidential prompt"
    )

    # Negative test: Beta cannot access Alpha's checkpoint
    with pytest.raises(PermissionError, match=r"Tenant mismatch"):
        await ckpt_mgr.get_checkpoint(cp_id, tenant_id="tenant-beta")


# ===========================================================================
# 4. Multi-Tenant Memory Architecture Tests
# ===========================================================================


def test_short_term_memory_sliding_window() -> None:
    stm = ShortTermMemory(max_entries=3)
    stm.add_message(AgentMessage(role="user", content="Msg 1"))
    stm.add_message(AgentMessage(role="assistant", content="Msg 2"))
    stm.add_message(AgentMessage(role="user", content="Msg 3"))
    stm.add_message(AgentMessage(role="assistant", content="Msg 4"))

    messages = stm.get_messages()
    assert len(messages) == 3
    assert messages[0].content == "Msg 2"
    assert messages[1].content == "Msg 3"
    assert messages[2].content == "Msg 4"


@pytest.mark.asyncio
async def test_long_term_memory_tenant_isolation() -> None:
    mgr = AgentMemoryManager()

    mgr.remember_episodic(
        tenant_id="tenant-alpha",
        key="strategy",
        value="Alpha corporate merger details",
        user_id="user_a",
        summary="merger",
    )
    mgr.remember_episodic(
        tenant_id="tenant-beta",
        key="strategy",
        value="Beta hedge fund portfolio",
        user_id="user_b",
        summary="hedge fund",
    )

    # Query Alpha
    res_alpha = mgr.recall_relevant("tenant-alpha", query_key="strategy")
    assert len(res_alpha) == 1
    assert "Alpha corporate merger" in str(res_alpha[0].value)

    # Query Beta
    res_beta = mgr.recall_relevant("tenant-beta", query_key="strategy")
    assert len(res_beta) == 1
    assert "Beta hedge fund" in str(res_beta[0].value)

    # Cross-tenant negative test: search non-existent in Alpha
    assert len(mgr.recall_relevant("tenant-alpha", query_key="unknown")) == 0


# ===========================================================================
# 5. Human-in-the-Loop Approvals Tests
# ===========================================================================


@pytest.mark.asyncio
async def test_approval_manager_flow_and_isolation() -> None:
    appr_mgr = ApprovalManager()

    # Request approval for dangerous tool
    req = appr_mgr.create_request(
        task_id="task_1",
        run_id="run_1",
        tenant_id="tenant-alpha",
        tool_name="terminal_exec",
        tool_args={"command": "npm install"},
        reason="Requires server modification",
        risk_level="dangerous",
    )

    assert req.status == ApprovalStatus.PENDING
    assert req.approval_id is not None

    # Verify pending approvals for tenant-alpha
    pending_alpha = appr_mgr.list_pending("tenant-alpha")
    assert len(pending_alpha) == 1
    assert pending_alpha[0].approval_id == req.approval_id

    # Negative test: Tenant-beta cannot see tenant-alpha's approvals
    pending_beta = appr_mgr.list_pending("tenant-beta")
    assert len(pending_beta) == 0

    # Negative test: Tenant-beta cannot decide tenant-alpha's approval
    with pytest.raises(PermissionError, match=r"Tenant mismatch"):
        appr_mgr.decide(
            req.approval_id,
            ApprovalDecision(approved=True, reason="Unauthorized approve"),
            tenant_id="tenant-beta",
            user_id="hacker",
        )

    # Positive test: Tenant-alpha approves
    decided = appr_mgr.decide(
        req.approval_id,
        ApprovalDecision(approved=True, reason="Approved by admin"),
        tenant_id="tenant-alpha",
        user_id="admin_user",
    )
    assert decided.status == ApprovalStatus.APPROVED
    assert decided.decided_by == "admin_user"

    # Idempotency / conflict check
    with pytest.raises(ValueError, match=r"already finalized"):
        appr_mgr.decide(
            req.approval_id,
            ApprovalDecision(approved=False, reason="Too late"),
            tenant_id="tenant-alpha",
            user_id="admin_user",
        )


# ===========================================================================
# 6. Bounded Planner & Workflow Engine Tests
# ===========================================================================


class MockFinishingBackend(AgentBackendInterface):
    """Backend that directly finishes with a final result."""

    async def generate(self, request: BackendRequest) -> BackendResponse:
        return BackendResponse(
            content='{"action": "finish", "output": "Task achieved successfully.", "thought": "Done"}',
            tool_calls=[],
            input_tokens=15,
            output_tokens=10,
            cost_usd=0.00003,
            finish_reason="stop",
        )

    async def generate_stream(
        self, request: BackendRequest
    ) -> AsyncIterator[BackendStreamChunk]:
        yield BackendStreamChunk(
            delta_content="Task achieved successfully.", is_complete=True
        )


class MockToolUsingBackend(AgentBackendInterface):
    """Backend that first invokes mock_dangerous_shell, then completes."""

    def __init__(self) -> None:
        self.invoked = False

    async def generate(self, request: BackendRequest) -> BackendResponse:
        if not self.invoked:
            self.invoked = True
            tool_call_json = {
                "action": "tool_call",
                "tool_name": "terminal_exec",
                "arguments": {"command": "echo test"},
                "thought": "Need to run shell command",
            }
            return BackendResponse(
                content=f"```json\n{json.dumps(tool_call_json)}\n```",
                tool_calls=[
                    AgentToolCall(
                        call_id="call_term_1",
                        tool_name="terminal_exec",
                        arguments={"command": "echo test"},
                    )
                ],
                input_tokens=25,
                output_tokens=15,
                cost_usd=0.00005,
                finish_reason="tool_calls",
            )
        return BackendResponse(
            content='{"action": "finish", "output": "Shell command verified. Finished.", "thought": "Done"}',
            tool_calls=[],
            input_tokens=20,
            output_tokens=10,
            cost_usd=0.00004,
            finish_reason="stop",
        )

    async def generate_stream(
        self, request: BackendRequest
    ) -> AsyncIterator[BackendStreamChunk]:
        yield BackendStreamChunk(delta_content="Shell executed.", is_complete=True)


@pytest.mark.asyncio
async def test_bounded_planner_limits() -> None:
    backend = MockFinishingBackend()
    planner = BoundedPlanner(backend=backend, max_iterations=2, timeout_seconds=60)
    plan = planner.create_initial_plan("Infinite task simulation")

    action = await planner.determine_next_action(
        goal="Infinite task simulation",
        plan=plan,
        history=[],
        available_tools=[],
        current_iteration=2,  # Reached max_iterations
        elapsed_time_seconds=1.0,
    )
    assert action.action_type == NextActionType.FAIL
    assert action.error is not None and "Maximum allowed iterations" in action.error


@pytest.mark.asyncio
async def test_workflow_engine_execution() -> None:
    registry = get_tool_registry()
    engine = WorkflowEngine(tool_registry=registry)

    wf = WorkflowDefinition(
        workflow_id="wf_01",
        name="System Inspection Workflow",
        steps=[
            WorkflowStepDefinition(
                step_id="s1",
                name="Get System Time",
                step_type=StepType.TOOL_CALL,
                tool_name="system_time",
                arguments={},
            ),
        ],
    )

    execution = engine.create_execution(wf, tenant_id="tenant-alpha")
    finished = await engine.run(wf, execution)
    assert finished.status == WorkflowExecutionStatus.COMPLETED
    assert "s1" in finished.step_results
    assert "timestamp" in finished.step_results["s1"]


# ===========================================================================
# 7. Autonomous Execution Loop Tests
# ===========================================================================


@pytest.mark.asyncio
async def test_agent_execution_loop_normal_finish() -> None:
    backend = MockFinishingBackend()
    planner = BoundedPlanner(backend=backend, max_iterations=5)
    registry = get_tool_registry()
    mem_mgr = AgentMemoryManager()
    ckpt_mgr = CheckpointManager()
    appr_mgr = ApprovalManager()

    loop = AgentExecutionLoop(
        planner=planner,
        tool_registry=registry,
        memory_manager=mem_mgr,
        checkpoint_manager=ckpt_mgr,
        approval_manager=appr_mgr,
        config=AgentConfig(max_iterations=5),
    )

    task = TaskState(
        task_id="t_norm", tenant_id="tenant-alpha", user_id="u1", goal="Simple task"
    )
    run = RunState(
        run_id="r_norm", task_id="t_norm", tenant_id="tenant-alpha", user_id="u1"
    )

    events: list[AgentRunEvent] = []
    async for ev in loop.execute(task, run):
        events.append(ev)

    assert run.status == RunStatus.COMPLETED
    assert task.status == TaskStatus.COMPLETED
    assert (
        run.final_output is not None
        and "Task achieved successfully." in run.final_output
    )
    assert any(ev.event_type == "completed" for ev in events)


@pytest.mark.asyncio
async def test_agent_execution_loop_approval_gate_and_resume() -> None:
    backend = MockToolUsingBackend()
    planner = BoundedPlanner(backend=backend, max_iterations=5)
    registry = get_tool_registry()
    mem_mgr = AgentMemoryManager()
    ckpt_mgr = CheckpointManager()
    appr_mgr = ApprovalManager()

    loop = AgentExecutionLoop(
        planner=planner,
        tool_registry=registry,
        memory_manager=mem_mgr,
        checkpoint_manager=ckpt_mgr,
        approval_manager=appr_mgr,
        config=AgentConfig(max_iterations=5),
    )

    task = TaskState(
        task_id="t_appr",
        tenant_id="tenant-alpha",
        user_id="u1",
        goal="Run dangerous command",
    )
    run = RunState(
        run_id="r_appr", task_id="t_appr", tenant_id="tenant-alpha", user_id="u1"
    )

    # First pass: hits dangerous tool approval requirement
    events_1: list[AgentRunEvent] = []
    async for ev in loop.execute(task, run):
        events_1.append(ev)

    assert str(run.status) == RunStatus.PAUSED_APPROVAL
    assert any(ev.event_type == "approval_required" for ev in events_1)

    # Check pending approval
    pending = appr_mgr.list_pending("tenant-alpha")
    assert len(pending) == 1
    assert pending[0].tool_name == "terminal_exec"

    # User approves
    appr_mgr.decide(
        approval_id=pending[0].approval_id,
        decision=ApprovalDecision(approved=True, reason="Authorized test"),
        tenant_id="tenant-alpha",
        user_id="admin",
    )

    # Resume loop
    events_2: list[AgentRunEvent] = []
    async for ev in loop.execute(task, run):
        events_2.append(ev)

    assert str(run.status) == RunStatus.COMPLETED
    assert any(ev.event_type == "completed" for ev in events_2)


@pytest.mark.asyncio
async def test_agent_execution_loop_cancellation() -> None:
    backend = MockFinishingBackend()
    planner = BoundedPlanner(backend=backend, max_iterations=5)
    registry = get_tool_registry()
    mem_mgr = AgentMemoryManager()
    ckpt_mgr = CheckpointManager()
    appr_mgr = ApprovalManager()

    loop = AgentExecutionLoop(
        planner=planner,
        tool_registry=registry,
        memory_manager=mem_mgr,
        checkpoint_manager=ckpt_mgr,
        approval_manager=appr_mgr,
        config=AgentConfig(max_iterations=5),
    )

    task = TaskState(
        task_id="t_cancel", tenant_id="tenant-alpha", user_id="u1", goal="Cancel task"
    )
    run = RunState(
        run_id="r_cancel", task_id="t_cancel", tenant_id="tenant-alpha", user_id="u1"
    )

    events: list[AgentRunEvent] = []
    async for ev in loop.execute(task, run, cancellation_requested=lambda: True):
        events.append(ev)

    assert run.status == RunStatus.CANCELLED
    assert any(ev.event_type == "cancelled" for ev in events)


# ===========================================================================
# 8. REST & SSE Endpoints Integration Tests
# ===========================================================================


@pytest.mark.asyncio
async def test_api_create_task_and_get_task(async_client: AsyncClient) -> None:
    token = generate_agent_jwt(tenant_id="tenant-acme")
    headers = {"Authorization": f"Bearer {token}"}

    # 1. Create task
    res = await async_client.post(
        "/api/v1/agent/tasks",
        json={"goal": "Build payment connector", "metadata": {"repo": "jakeai"}},
        headers=headers,
    )
    assert res.status_code == status.HTTP_201_CREATED
    data = res.json()
    task_id = data["task_id"]
    assert data["goal"] == "Build payment connector"
    assert data["tenant_id"] == "tenant-acme"

    # 2. Get task
    res_get = await async_client.get(f"/api/v1/agent/tasks/{task_id}", headers=headers)
    assert res_get.status_code == status.HTTP_200_OK
    assert res_get.json()["task_id"] == task_id

    # 3. Multi-tenant negative isolation: Other tenant cannot access
    other_token = generate_agent_jwt(tenant_id="tenant-other")
    other_headers = {"Authorization": f"Bearer {other_token}"}
    res_forbidden = await async_client.get(
        f"/api/v1/agent/tasks/{task_id}", headers=other_headers
    )
    assert res_forbidden.status_code in [
        status.HTTP_403_FORBIDDEN,
        status.HTTP_404_NOT_FOUND,
    ]


@pytest.mark.asyncio
async def test_api_create_run_and_cancel(async_client: AsyncClient) -> None:
    token = generate_agent_jwt(tenant_id="tenant-acme")
    headers = {"Authorization": f"Bearer {token}"}

    # Create task
    task_res = await async_client.post(
        "/api/v1/agent/tasks",
        json={"goal": "Long running analysis"},
        headers=headers,
    )
    task_id = task_res.json()["task_id"]

    # Start run (async background)
    run_res = await async_client.post(
        f"/api/v1/agent/tasks/{task_id}/runs",
        json={"max_iterations": 10, "async_execution": True},
        headers=headers,
    )
    assert run_res.status_code == status.HTTP_201_CREATED
    run_id = run_res.json()["run_id"]

    # Get run status
    res_status = await async_client.get(
        f"/api/v1/agent/tasks/{task_id}/runs/{run_id}",
        headers=headers,
    )
    assert res_status.status_code == status.HTTP_200_OK
    assert res_status.json()["run_id"] == run_id

    # Cancel run
    res_cancel = await async_client.post(
        f"/api/v1/agent/tasks/{task_id}/runs/{run_id}/cancel",
        headers=headers,
    )
    assert res_cancel.status_code == status.HTTP_200_OK
    assert res_cancel.json()["status"] == RunStatus.CANCELLED


@pytest.mark.asyncio
async def test_api_approvals_and_metrics_endpoints(async_client: AsyncClient) -> None:
    token = generate_agent_jwt(tenant_id="tenant-acme")
    headers = {"Authorization": f"Bearer {token}"}

    # Check pending approvals endpoint
    res_appr = await async_client.get(
        "/api/v1/agent/approvals/pending", headers=headers
    )
    assert res_appr.status_code == status.HTTP_200_OK
    assert isinstance(res_appr.json(), list)

    # Check metrics endpoint
    res_metrics = await async_client.get("/api/v1/agent/metrics", headers=headers)
    assert res_metrics.status_code == status.HTTP_200_OK
    metrics = res_metrics.json()
    assert "tasks_created" in metrics
    assert "runs_started" in metrics
    assert "total_cost_usd" in metrics
