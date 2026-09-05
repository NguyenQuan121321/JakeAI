"""StateGraph assembly and execution pipeline for LangGraph multi-agent system."""

from collections.abc import AsyncGenerator
from typing import Any

from langgraph.graph import END, StateGraph

from app.agents.financial_specialist import financial_specialist_node
from app.agents.finnapigo_tool import finnapigo_tool_node
from app.agents.state import AgentState
from app.agents.supervisor import supervisor_node
from app.agents.synthesizer import synthesizer_node
from app.agents.verifier import verifier_node
from app.core.context import TenantContext
from app.core.security import exchange_obo_token


def route_from_supervisor(state: AgentState) -> str:
    """Determine downstream branch based on supervisor decision."""
    target = state.get("next_agent", "synthesizer")
    if target == "financial_specialist":
        return "financial_specialist"
    if target == "finnapigo_tool":
        return "finnapigo_tool"
    return "synthesizer"


def route_from_verifier(state: AgentState) -> str:
    """Determine whether self-correction loop is needed or proceed to synthesis."""
    if state.get("verification_verdict") == "NEEDS_REVISION":
        return "supervisor"
    return "synthesizer"


def create_agent_graph() -> Any:
    """Construct and compile the multi-agent LangGraph workflow."""
    workflow = StateGraph(AgentState)

    # Register Nodes
    workflow.add_node("supervisor", supervisor_node)
    workflow.add_node("financial_specialist", financial_specialist_node)
    workflow.add_node("finnapigo_tool", finnapigo_tool_node)
    workflow.add_node("verifier", verifier_node)
    workflow.add_node("synthesizer", synthesizer_node)

    # Set Entry Point
    workflow.set_entry_point("supervisor")

    # Conditional Routing Edges
    workflow.add_conditional_edges(
        "supervisor",
        route_from_supervisor,
        {
            "financial_specialist": "financial_specialist",
            "finnapigo_tool": "finnapigo_tool",
            "synthesizer": "synthesizer",
        },
    )

    # Specialist Nodes Converge on Verifier
    workflow.add_edge("financial_specialist", "verifier")
    workflow.add_edge("finnapigo_tool", "verifier")

    # Verifier Decision: Critique Loop or Synthesis
    workflow.add_conditional_edges(
        "verifier",
        route_from_verifier,
        {
            "supervisor": "supervisor",
            "synthesizer": "synthesizer",
        },
    )

    # Exit Edge
    workflow.add_edge("synthesizer", END)

    return workflow.compile()


# Compiled Singleton Graph
agent_graph = create_agent_graph()


async def stream_multi_agent_workflow(
    prompt: str,
    context: TenantContext,
    conversation_id: str,
) -> AsyncGenerator[dict[str, Any], None]:
    """Execute LangGraph multi-agent workflow and stream incremental step events."""
    initial_state: AgentState = {
        "prompt": prompt,
        "tenant_id": context.tenant_id,
        "user_id": context.user_id,
        "roles": context.roles,
        "permissions": context.permissions,
        "conversation_id": conversation_id,
        "correlation_id": context.correlation_id,
        "obo_token": exchange_obo_token(context),
        "messages": [f"User query received: '{prompt}'"],
        "tool_calls": [],
        "financial_analysis": {},
        "revision_count": 0,
        "mascot_state": "thinking",
        "citations": [],
    }

    async for event in agent_graph.astream(initial_state):
        for node_name, node_state in event.items():
            yield {
                "node": node_name,
                "workflow_phase": node_state.get("workflow_phase", "executing"),
                "mascot_state": node_state.get("mascot_state", "thinking"),
                "message": node_state.get("messages", [""])[-1],
                "tool_calls": node_state.get("tool_calls", []),
                "final_response": node_state.get("final_response"),
                "citations": node_state.get("citations", []),
            }
