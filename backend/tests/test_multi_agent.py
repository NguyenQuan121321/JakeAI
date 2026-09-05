"""Unit and integration tests for LangGraph multi-agent orchestration."""

from typing import TYPE_CHECKING

import pytest
from httpx import AsyncClient

from app.agents.financial_specialist import financial_specialist_node
from app.agents.finnapigo_tool import finnapigo_tool_node
from app.agents.graph import (
    create_agent_graph,
    stream_multi_agent_workflow,
)
from app.agents.supervisor import classify_intent
from app.agents.synthesizer import synthesizer_node
from app.agents.verifier import verifier_node
from app.core.config import get_settings
from app.core.context import TenantContext
from tests.test_gateway import create_test_jwt

if TYPE_CHECKING:
    from app.agents.state import AgentState


def test_supervisor_intent_classification() -> None:
    """Verify intent classifier directs queries to appropriate specialized nodes."""
    assert (
        classify_intent("Calculate Q3 operating margin and EBITDA")
        == "financial_specialist"
    )
    assert (
        classify_intent("Show me account balance and ledger") == "financial_specialist"
    )
    assert classify_intent("Fetch customer profile from finnapi") == "finnapigo_tool"
    assert classify_intent("What transactions occurred today?") == "finnapigo_tool"
    assert classify_intent("Hello! How can you help me?") == "synthesizer"


@pytest.mark.asyncio
async def test_financial_specialist_node() -> None:
    """Verify Financial Specialist extracts figures and computes formulas."""
    state: AgentState = {
        "prompt": "Revenue is $2000000 and expenses are $1200000. Calculate margin.",
        "tenant_id": "tenant-test-corp",
        "user_id": "user-01",
    }
    result = await financial_specialist_node(state)

    assert result["current_agent"] == "financial_specialist"
    analysis = result["financial_analysis"]
    assert analysis["revenue"] == 2000000.0
    assert analysis["operating_expenses"] == 1200000.0
    assert analysis["operating_income"] == 800000.0
    assert analysis["operating_margin_pct"] == 40.0
    assert result["next_agent"] == "verifier"


@pytest.mark.asyncio
async def test_financial_specialist_node_formatted_currencies() -> None:
    """Verify Financial Specialist extracts comma-separated currency values."""
    state: AgentState = {
        "prompt": (
            "Revenue is $1,500,000.50 and expenses are $950,000.25. Calculate margin."
        ),
        "tenant_id": "tenant-test-corp",
        "user_id": "user-01",
    }
    result = await financial_specialist_node(state)
    analysis = result["financial_analysis"]
    assert analysis["revenue"] == 1500000.50
    assert analysis["operating_expenses"] == 950000.25
    assert round(analysis["operating_income"], 2) == 550000.25


@pytest.mark.asyncio
async def test_finnapigo_tool_node() -> None:
    """Verify FinnApiGo Tool Executor dispatches authenticated upstream calls."""
    state: AgentState = {
        "prompt": "Get current account balance",
        "tenant_id": "tenant-beta",
        "user_id": "user-99",
        "tool_calls": [],
    }
    result = await finnapigo_tool_node(state)

    assert result["current_agent"] == "finnapigo_tool"
    assert len(result["tool_calls"]) == 1
    call = result["tool_calls"][0]
    assert call["tool_name"] == "get_account_balance"
    assert call["tenant_id"] == "tenant-beta"
    assert result["next_agent"] == "verifier"


@pytest.mark.asyncio
async def test_verifier_critique_and_pass() -> None:
    """Verify Verifier critiques arithmetic variance and passes grounded data."""
    # Scenario A: Inconsistent math triggers self-correction
    invalid_state: AgentState = {
        "prompt": "Revenue calculation",
        "tenant_id": "tenant-01",
        "financial_analysis": {
            "revenue": 100.0,
            "operating_expenses": 30.0,
            "operating_income": 999.0,  # Intentional math discrepancy
        },
        "tool_calls": [],
        "revision_count": 0,
    }
    critique_result = await verifier_node(invalid_state)
    assert critique_result["verification_verdict"] == "NEEDS_REVISION"
    assert critique_result["next_agent"] == "supervisor"
    assert critique_result["revision_count"] == 1

    # Scenario B: Grounded and consistent data passes
    valid_state: AgentState = {
        "prompt": "Revenue calculation",
        "tenant_id": "tenant-01",
        "financial_analysis": {
            "revenue": 100.0,
            "operating_expenses": 30.0,
            "operating_income": 70.0,
        },
        "tool_calls": [],
        "revision_count": 0,
    }
    pass_result = await verifier_node(valid_state)
    assert pass_result["verification_verdict"] == "PASS"
    assert pass_result["next_agent"] == "synthesizer"


@pytest.mark.asyncio
async def test_synthesizer_node() -> None:
    """Verify Synthesizer formats Markdown reports with citations."""
    state: AgentState = {
        "prompt": "Summary of Q3",
        "tenant_id": "tenant-acme",
        "financial_analysis": {
            "revenue": 500000.0,
            "operating_expenses": 350000.0,
            "operating_income": 150000.0,
            "operating_margin_pct": 30.0,
            "ebitda": 168000.0,
        },
        "tool_calls": [],
    }
    result = await synthesizer_node(state)

    assert result["current_agent"] == "synthesizer"
    assert result["workflow_phase"] == "completed"
    assert "Financial Performance Metrics" in result["final_response"]
    assert "$500,000.00" in result["final_response"]
    assert len(result["citations"]) > 0


@pytest.mark.asyncio
async def test_end_to_end_graph_execution() -> None:
    """Verify complete LangGraph traversal from supervisor through synthesizer."""
    graph = create_agent_graph()
    initial_state: AgentState = {
        "prompt": "Calculate margin for revenue $1000000 and cost $600000",
        "tenant_id": "tenant-e2e",
        "user_id": "user-e2e",
        "roles": ["analyst"],
        "permissions": ["all"],
        "conversation_id": "conv-e2e-1",
        "correlation_id": "corr-e2e-1",
        "messages": [],
        "tool_calls": [],
        "financial_analysis": {},
        "revision_count": 0,
        "citations": [],
    }

    final_state = await graph.ainvoke(initial_state)

    assert "final_response" in final_state
    assert final_state["verification_verdict"] == "PASS"
    assert "$1,000,000.00" in final_state["final_response"]
    assert "40.0% Margin" in final_state["final_response"]
    assert final_state["mascot_state"] == "idle"


@pytest.mark.asyncio
async def test_stream_multi_agent_workflow() -> None:
    """Verify async streaming generator yields incremental node events."""
    context = TenantContext(
        tenant_id="tenant-stream",
        user_id="user-stream",
    )

    events: list[dict] = []
    async for event in stream_multi_agent_workflow(
        prompt="Check balance and revenue $5000",
        context=context,
        conversation_id="conv-stream-01",
    ):
        events.append(event)

    nodes_visited = [e["node"] for e in events]
    assert "supervisor" in nodes_visited
    assert "synthesizer" in nodes_visited
    assert any(e.get("final_response") for e in events)


@pytest.mark.asyncio
async def test_chat_sse_stream_multi_agent(
    async_client: AsyncClient,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Verify /api/v1/chat/stream delivers multi-agent LangGraph SSE frames."""
    settings = get_settings()
    monkeypatch.setattr(settings, "JWT_ALGORITHM", "HS256")

    token = create_test_jwt(
        sub="user-sse",
        tenant_id="tenant-sse",
    )

    response = await async_client.post(
        "/api/v1/chat/stream",
        headers={"Authorization": f"Bearer {token}"},
        json={
            "prompt": "Calculate Q3 revenue of $800000 with expenses $500000",
            "conversation_id": "conv-sse-test",
        },
    )

    assert response.status_code == 200
    assert "text/event-stream" in response.headers.get("content-type", "")

    body = response.text
    assert "event: status" in body
    assert "event: token" in body
    assert "event: done" in body
    assert "supervisor" in body
    assert "$800,000.00" in body
