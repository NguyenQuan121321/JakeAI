"""Unit tests for end-to-end Correlation ID propagation across JakeAI components (TASK OPS-04)."""

from unittest.mock import AsyncMock, MagicMock, patch

import jwt
import pytest

from app.agent.planning.models import NextAction, NextActionType, Plan, PlanStep
from app.agent.runtime.loop import AgentExecutionLoop
from app.agent.runtime.models import AgentConfig
from app.agent.state.models import RunState, TaskState
from app.agents.finnapigo_tool import finnapigo_tool_node
from app.core.context import TenantContext
from app.core.security import exchange_obo_token
from app.rag.pipeline import RAGPipeline
from app.routing.router import ModelRouter, RoutingPolicy


def test_tenant_context_and_obo_token_correlation_id():
    cid = "corr-test-tenant-1234"
    ctx = TenantContext(
        tenant_id="tenant_a",
        user_id="user_1",
        roles=["developer"],
        permissions=["read"],
        correlation_id=cid,
    )
    assert ctx.correlation_id == cid
    obo_token = exchange_obo_token(ctx)
    decoded = jwt.decode(obo_token, options={"verify_signature": False})
    assert decoded.get("cid") == cid
    assert decoded.get("sub") == "user_1"
    assert decoded.get("tenant_id") == "tenant_a"


def test_router_correlation_id_propagation():
    cid = "corr-test-router-5678"
    policy = RoutingPolicy(
        requested_model="gemini-1.5-flash",
        tenant_id="tenant_a",
        correlation_id=cid,
    )
    router = ModelRouter()
    decision = router.route(policy)
    assert decision.correlation_id == cid
    data = decision.to_dict()
    assert data["correlation_id"] == cid


@pytest.mark.asyncio
async def test_llm_provider_correlation_id_propagation():
    from app.core.llm_provider import call_upstream_llm_detailed
    from app.providers.base import ProviderCacheTelemetry, UpstreamLLMResponse

    cid = "corr-test-provider-9999"

    mock_resp = UpstreamLLMResponse(
        text="Mock response",
        model="gemini-1.5-flash",
        provider="gemini",
        telemetry=ProviderCacheTelemetry(uncached_input_tokens=10),
    )

    with patch("app.core.llm_provider.get_failover_manager") as mock_failover_getter:
        mock_failover = AsyncMock()
        mock_failover.execute_with_failover = AsyncMock(return_value=mock_resp)
        mock_failover_getter.return_value = mock_failover

        resp = await call_upstream_llm_detailed(
            prompt="Test prompt",
            tenant_id="tenant_a",
            correlation_id=cid,
        )
        assert resp is not None
        assert mock_failover.execute_with_failover.call_count == 1
        call_kwargs = mock_failover.execute_with_failover.call_args.kwargs
        assert call_kwargs["request"].correlation_id == cid
        assert call_kwargs["decision"].correlation_id == cid


@pytest.mark.asyncio
async def test_rag_pipeline_correlation_id_propagation():
    pipeline = RAGPipeline()
    cid = "corr-test-rag-4321"
    # Grounded answer with correlation_id
    result = await pipeline.generate_grounded_answer(
        query="What is the status?",
        tenant_id="tenant_a",
        correlation_id=cid,
    )
    assert result.correlation_id == cid


@pytest.mark.asyncio
async def test_agent_execution_loop_correlation_id_propagation():
    cid = "corr-test-agent-8765"
    task = TaskState(
        task_id="task-1",
        tenant_id="tenant_a",
        user_id="user_1",
        goal="Read file",
    )
    run = RunState(
        run_id="run-1",
        task_id="task-1",
        tenant_id="tenant_a",
        user_id="user_1",
        correlation_id=cid,
        max_iterations=2,
    )

    mock_planner = MagicMock()
    mock_planner.create_initial_plan.return_value = Plan(
        plan_id="p-1",
        goal="Read file",
        steps=[PlanStep(step_id="s-1", description="read")],
    )

    # First iteration: tool call; second iteration: finish
    mock_planner.determine_next_action = AsyncMock(
        side_effect=[
            NextAction(
                action_type=NextActionType.TOOL_CALL,
                tool_name="calculator",
                tool_args={"expression": "1+1"},
            ),
            NextAction(action_type=NextActionType.FINISH, final_output="2"),
        ]
    )

    captured_contexts = []
    mock_tool_registry = MagicMock()
    mock_tool = MagicMock()
    mock_tool.name = "calculator"
    mock_tool.is_dangerous = False
    mock_tool_registry.discover.return_value = [mock_tool]
    mock_tool_registry.get.return_value = mock_tool

    async def mock_execute(tool_name, arguments, context):
        captured_contexts.append(context)
        res = MagicMock()
        res.success = True
        res.output = "2"
        res.error = None
        return res

    mock_tool_registry.execute = AsyncMock(side_effect=mock_execute)
    mock_mem = MagicMock()
    mock_mem.get_run_memory.return_value.get_messages.return_value = []
    mock_checkpoint = MagicMock()
    mock_checkpoint.save_checkpoint = AsyncMock()
    mock_approval = MagicMock()

    loop = AgentExecutionLoop(
        planner=mock_planner,
        tool_registry=mock_tool_registry,
        memory_manager=mock_mem,
        checkpoint_manager=mock_checkpoint,
        approval_manager=mock_approval,
        config=AgentConfig(require_human_approval_for_dangerous=False),
    )

    events = []
    async for evt in loop.execute(task=task, run=run):
        events.append(evt)

    assert len(captured_contexts) == 1
    assert captured_contexts[0].get("correlation_id") == cid
    assert captured_contexts[0].get("tenant_id") == "tenant_a"


@pytest.mark.asyncio
async def test_finnapigo_tool_node_correlation_id_propagation():
    cid = "corr-test-finnapigo-1357"
    state = {
        "prompt": "Check limits",
        "tenant_id": "tenant_a",
        "user_id": "user_1",
        "roles": ["developer", "tenant_admin"],
        "permissions": ["execute"],
        "correlation_id": cid,
        "tool_calls": [],
        "messages": [],
    }

    with patch("app.agent.tools.registry.get_tool_registry") as mock_get_reg:
        mock_reg = MagicMock()
        captured_context = {}

        async def mock_exec(tool_name, arguments, context):
            nonlocal captured_context
            captured_context = context
            res = MagicMock()
            res.success = True
            res.output = {"rate_limit": 100}
            res.error = None
            return res

        mock_reg.execute = AsyncMock(side_effect=mock_exec)
        mock_get_reg.return_value = mock_reg

        res_node = await finnapigo_tool_node(state)
        assert res_node["workflow_phase"] != "tool_blocked"
        assert captured_context.get("correlation_id") == cid
