"""R-ARCH-04 — Contract Consistency Regression Test Suite.

Verifies:
1. PlanStep and ExecutionPlan domain contracts have first-class tool attributes and default factories.
2. RunState to_agent_state / from_agent_state round-trips preserve tool_results and steps.
3. Pydantic models use safe default factories instead of mutable defaults.
4. InternalResumeSubmission includes conversation_id, and agent metrics endpoint specifies response_model.
5. SSE streaming endpoints include standard headers.
6. ProviderRequest and adapters accept and normalize string / dict response_format consistently.
7. ToolSelection risk_level defaults to 'read_only' and TaskState user_id defaults to 'anonymous'.
"""

from __future__ import annotations

import time
from typing import Any

import pytest

from app.agent.domain.contracts import (
    ExecutionPlan,
    ToolSelection,
)
from app.agent.domain.contracts import (
    PlanStep as DomainPlanStep,
)
from app.agent.planning.models import Plan
from app.agent.state.checkpoint import CheckpointRecord as StateCheckpointRecord
from app.agent.state.models import (
    RunState,
    RunStatus,
    StepExecutionRecord,
    TaskState,
)
from app.agent.telemetry import AgentMetricsSnapshot
from app.agent.tools.base import ToolRiskLevel
from app.api.v1.endpoints.coding import InternalResumeSubmission
from app.core.context import TenantContext
from app.core.sse import streaming_sse_headers
from app.providers.base import ProviderRequest
from app.providers.deepseek import DeepSeekAdapter
from app.providers.groq import GroqAdapter
from app.providers.local import LocalModelAdapter
from app.providers.openai import OpenAIAdapter
from app.providers.openrouter import OpenRouterAdapter
from app.services.resume_bridge import (
    CheckpointRecord as BridgeCheckpointRecord,
)
from app.services.resume_bridge import (
    ResumedExecutionResult,
)

# ==============================================================================
# 1. PlanStep & ExecutionPlan Domain Contract Consistency
# ==============================================================================


def test_domain_plan_step_first_class_tool_attributes() -> None:
    """PlanStep must have first-class typed tool_name and tool_args attributes."""
    step = DomainPlanStep(
        step_id="step_1",
        description="Fetch account balance",
        tool_name="get_account_balance",
        tool_args={"account_id": "acc-999"},
    )
    assert step.tool_name == "get_account_balance"
    assert step.tool_args == {"account_id": "acc-999"}

    # Default tool_args is an independent dict
    step2 = DomainPlanStep(step_id="step_2", description="Compute summary")
    assert step2.tool_name is None
    assert step2.tool_args == {}
    step2.tool_args["key"] = "val"
    step3 = DomainPlanStep(step_id="step_3", description="Render summary")
    assert step3.tool_args == {}, "Mutable default leaked between instances"


def test_execution_plan_default_task_id_factory() -> None:
    """ExecutionPlan and Plan subclasses must both supply default task_id."""
    exec_plan = ExecutionPlan(goal="Audit quarterly earnings")
    assert exec_plan.task_id.startswith("task_")
    assert exec_plan.plan_id.startswith("plan_")

    plan = Plan(goal="Audit quarterly earnings")
    assert plan.task_id.startswith("task_")
    assert plan.plan_id.startswith("plan_")


def test_execution_engine_typed_step_tool_attributes() -> None:
    """ExecutionEngine inspects step.tool_name and step.tool_args directly."""
    step = DomainPlanStep(
        step_id="step-exec-1",
        description="Check user credit",
        tool_name="credit_check",
        tool_args={"user_id": "u-1"},
    )
    # Both direct attributes exist without falling back to getattr defaults
    assert hasattr(step, "tool_name")
    assert hasattr(step, "tool_args")
    assert step.tool_name == "credit_check"
    assert step.tool_args == {"user_id": "u-1"}


# ==============================================================================
# 2. State & LangGraph Adapter Round-Trip Contract Consistency
# ==============================================================================


def test_run_state_roundtrip_preserves_tool_results_and_steps() -> None:
    """RunState.to_agent_state and from_agent_state must preserve tool_results and steps."""
    step_record = StepExecutionRecord(
        step_number=1,
        action_type="tool_call",
        description="Fetch inflation data",
        tool_name="fetch_data",
        tool_args={"q": "inflation"},
        observation="Inflation rate 2.4%",
        execution_time_ms=45.2,
    )
    original_run = RunState(
        run_id="run-100",
        task_id="task-200",
        tenant_id="tenant-alpha",
        user_id="user-bob",
        status=RunStatus.RUNNING,
        steps=[step_record],
        tool_calls=[{"id": "call-1", "name": "fetch_data"}],
        tool_results=[{"call_id": "call-1", "status": "success", "data": "2.4%"}],
        context={"financial_analysis": {"trend": "up"}},
    )

    # Convert to LangGraph agent state
    agent_state = original_run.to_agent_state()
    assert "tool_results" in agent_state
    assert len(agent_state["tool_results"]) == 1
    assert agent_state["tool_results"][0]["call_id"] == "call-1"

    assert "steps" in agent_state
    assert len(agent_state["steps"]) == 1
    assert agent_state["steps"][0]["step_number"] == 1

    # Rehydrate back from agent state
    rehydrated = RunState.from_agent_state(
        agent_state, task_id=original_run.task_id, run_id=original_run.run_id
    )
    assert rehydrated.run_id == original_run.run_id
    assert rehydrated.task_id == original_run.task_id
    assert rehydrated.tenant_id == original_run.tenant_id
    assert len(rehydrated.tool_results) == 1
    assert rehydrated.tool_results[0]["call_id"] == "call-1"
    assert len(rehydrated.steps) == 1
    assert isinstance(rehydrated.steps[0], StepExecutionRecord)
    assert rehydrated.steps[0].step_number == 1
    assert rehydrated.steps[0].observation == "Inflation rate 2.4%"


def test_task_state_user_id_default_anonymous() -> None:
    """TaskState must default user_id to 'anonymous', aligning with TaskSpec and ExecutionContext."""
    task = TaskState(
        task_id="t-1",
        tenant_id="ten-1",
        goal="Analyze risk",
    )
    assert task.user_id == "anonymous"


# ==============================================================================
# 3. Pydantic Mutable Default Safety
# ==============================================================================


def test_checkpoint_record_mutable_defaults_isolated() -> None:
    """StateCheckpointRecord.short_term_memory_snapshot must be an isolated list per instance."""
    cp1 = StateCheckpointRecord(
        run_id="r1",
        task_id="t1",
        tenant_id="ten1",
        user_id="u1",
        checkpoint_id="chk1",
        checkpoint_created_at=time.time(),
    )
    cp2 = StateCheckpointRecord(
        run_id="r2",
        task_id="t2",
        tenant_id="ten2",
        user_id="u2",
        checkpoint_id="chk2",
        checkpoint_created_at=time.time(),
    )
    cp1.short_term_memory_snapshot.append({"msg": "hello"})
    assert len(cp1.short_term_memory_snapshot) == 1
    assert len(cp2.short_term_memory_snapshot) == 0, (
        "Mutable default leaked between CheckpointRecords"
    )


def test_resume_bridge_mutable_defaults_isolated() -> None:
    """BridgeCheckpointRecord and ResumedExecutionResult mutable dict defaults must be isolated."""
    bcp1 = BridgeCheckpointRecord(
        call_id="c1",
        tenant_id="t1",
        created_at=time.time(),
    )
    bcp2 = BridgeCheckpointRecord(
        call_id="c2",
        tenant_id="t2",
        created_at=time.time(),
    )
    bcp1.arguments["param"] = 123
    assert len(bcp2.arguments) == 0, (
        "Mutable default leaked between BridgeCheckpointRecords"
    )

    res1 = ResumedExecutionResult(
        call_id="c1",
        status="resumed",
        resumed_at=time.time(),
        tenant_id="t1",
        message="ok",
        tool_acknowledged=True,
    )
    res2 = ResumedExecutionResult(
        call_id="c2",
        status="resumed",
        resumed_at=time.time(),
        tenant_id="t2",
        message="ok",
        tool_acknowledged=True,
    )
    res1.details["extra"] = "info"
    assert len(res2.details) == 0, (
        "Mutable default leaked between ResumedExecutionResults"
    )


# ==============================================================================
# 4. API Endpoint Schema & Contract Alignment
# ==============================================================================


def test_internal_resume_submission_conversation_id() -> None:
    """InternalResumeSubmission contract supports optional conversation_id."""
    sub = InternalResumeSubmission(
        call_id="call_abc",
        tenant_id="tenant_123",
        result={"status": "completed"},
        conversation_id="conv_xyz",
    )
    assert sub.conversation_id == "conv_xyz"

    sub_default = InternalResumeSubmission(
        call_id="call_def",
        tenant_id="tenant_123",
        result={"status": "completed"},
    )
    assert sub_default.conversation_id is None


def test_agent_metrics_endpoint_response_model() -> None:
    """GET /api/v1/agent/metrics specifies response_model=AgentMetricsSnapshot."""
    from app.api.v1.endpoints.agent import router

    route = next(
        (r for r in router.routes if getattr(r, "path", None) == "/metrics"), None
    )
    assert route is not None, "GET /metrics route not found in agent router"
    assert route.response_model is AgentMetricsSnapshot


def test_streaming_sse_headers_contract() -> None:
    """streaming_sse_headers produces standard headers with tenant and correlation tracking."""
    ctx = TenantContext(
        tenant_id="tenant-acme", correlation_id="corr-777", user_id="u-42"
    )
    headers = streaming_sse_headers(ctx)
    assert headers["Cache-Control"] == "no-cache"
    assert headers["Connection"] == "keep-alive"
    assert headers["X-Accel-Buffering"] == "no"
    assert headers["X-Tenant-ID"] == "tenant-acme"
    assert headers["X-Correlation-ID"] == "corr-777"


# ==============================================================================
# 5. Provider Contract Consistency & Format Normalization
# ==============================================================================


def test_provider_request_accepts_str_and_dict_response_format() -> None:
    """ProviderRequest.response_format accepts str, dict, and None."""
    req_str = ProviderRequest(
        model="gpt-4o",
        prompt="Output json",
        response_format="json_object",
    )
    assert req_str.response_format == "json_object"

    req_dict = ProviderRequest(
        model="gpt-4o",
        prompt="Output json",
        response_format={"type": "json_schema", "json_schema": {"name": "test"}},
    )
    assert isinstance(req_dict.response_format, dict)

    req_none = ProviderRequest(
        model="gpt-4o",
        prompt="Output plain",
    )
    assert req_none.response_format is None


@pytest.mark.parametrize(
    "adapter_cls",
    [OpenAIAdapter, DeepSeekAdapter, LocalModelAdapter, GroqAdapter, OpenRouterAdapter],
)
def test_provider_adapters_normalize_string_response_format(adapter_cls: Any) -> None:
    """Provider adapters normalize string response_format='json_object' into dict."""
    adapter = adapter_cls()
    req = ProviderRequest(
        model="gpt-4o",
        prompt="Generate data",
        response_format="json_object",
    )
    _, payload = adapter._prepare_payload(req, stream=False)
    assert "response_format" in payload
    assert payload["response_format"] == {"type": "json_object"}

    # And dict is preserved as-is
    dict_fmt = {"type": "json_schema", "schema": {"type": "object"}}
    req_dict = ProviderRequest(
        model="gpt-4o",
        prompt="Generate data",
        response_format=dict_fmt,
    )
    _, payload_dict = adapter._prepare_payload(req_dict, stream=False)
    assert payload_dict["response_format"] == dict_fmt


def test_tool_selection_default_risk_level() -> None:
    """ToolSelection.risk_level must default to 'read_only' within ToolRiskLevel."""
    tool_sel = ToolSelection(tool_name="get_quote")
    assert tool_sel.risk_level == "read_only"
    assert tool_sel.risk_level in [r.value for r in ToolRiskLevel]
