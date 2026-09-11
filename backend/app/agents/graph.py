"""StateGraph assembly and execution pipeline for LangGraph multi-agent system."""

import uuid
from collections.abc import AsyncGenerator
from typing import Any

from langgraph.checkpoint.memory import MemorySaver
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


class AutoConfigGraph:
    """Wrapper ensuring thread_id configurable config is automatically provided to checkpointer."""

    def __init__(self, graph: Any) -> None:
        self._graph = graph

    def __getattr__(self, item: str) -> Any:
        return getattr(self._graph, item)

    async def ainvoke(
        self,
        input: Any,
        config: dict[str, Any] | None = None,
        **kwargs: Any,
    ) -> Any:
        if config is None:
            thread_id = "default_thread"
            if isinstance(input, dict):
                thread_id = (
                    input.get("conversation_id")
                    or input.get("correlation_id")
                    or "default_thread"
                )
            config = {"configurable": {"thread_id": thread_id}}
        return await self._graph.ainvoke(input, config=config, **kwargs)

    async def astream(
        self,
        input: Any,
        config: dict[str, Any] | None = None,
        **kwargs: Any,
    ) -> AsyncGenerator[Any, None]:
        if config is None:
            thread_id = "default_thread"
            if isinstance(input, dict):
                thread_id = (
                    input.get("conversation_id")
                    or input.get("correlation_id")
                    or "default_thread"
                )
            config = {"configurable": {"thread_id": thread_id}}
        async for item in self._graph.astream(input, config=config, **kwargs):
            yield item


def create_agent_graph(checkpointer: Any = None) -> Any:
    """Construct and compile the multi-agent LangGraph workflow with checkpointer (TASK ORC-06)."""
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

    saver = checkpointer if checkpointer is not None else MemorySaver()
    compiled = workflow.compile(checkpointer=saver)
    return AutoConfigGraph(compiled)


# Compiled Singleton Graph with Real Checkpointer
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
        "execution_plan": {},
    }

    config = {"configurable": {"thread_id": conversation_id}}
    async for event in agent_graph.astream(initial_state, config=config):
        for node_name, node_state in event.items():
            yield {
                "node": node_name,
                "workflow_phase": node_state.get("workflow_phase", "executing"),
                "mascot_state": node_state.get("mascot_state", "thinking"),
                "message": node_state.get("messages", [""])[-1],
                "tool_calls": node_state.get("tool_calls", []),
                "final_response": node_state.get("final_response"),
                "citations": node_state.get("citations", []),
                "verification_verdict": node_state.get("verification_verdict"),
            }


class LangGraphExecutionAdapter:
    """Execution adapter allowing the canonical OrchestrationKernel to execute via LangGraph."""

    def __init__(self, graph: Any | None = None) -> None:
        self.graph = graph or agent_graph

    async def execute(
        self,
        task_spec: Any,
        run_id: str | None = None,
        plan: Any | None = None,
    ) -> AsyncGenerator[Any, None]:
        """Execute a canonical TaskSpec through LangGraph and yield canonical AgentRunEvents."""
        from app.agent.runtime.models import AgentRunEvent

        active_run_id = run_id or f"run_lg_{uuid.uuid4().hex[:12]}"
        conversation_id = task_spec.task_id

        yield AgentRunEvent(
            event_type="task_created",
            task_id=task_spec.task_id,
            run_id=active_run_id,
            data={"goal": task_spec.goal, "tenant_id": task_spec.tenant_id},
        )

        initial_state: AgentState = {
            "prompt": task_spec.goal,
            "tenant_id": task_spec.tenant_id,
            "user_id": task_spec.user_id,
            "roles": task_spec.roles,
            "permissions": task_spec.permissions,
            "conversation_id": conversation_id,
            "correlation_id": task_spec.correlation_id,
            "obo_token": "",
            "messages": [f"Task goal: '{task_spec.goal}'"],
            "tool_calls": [],
            "financial_analysis": {},
            "revision_count": 0,
            "mascot_state": "thinking",
            "citations": [],
            "execution_plan": (
                plan.model_dump()
                if plan is not None and hasattr(plan, "model_dump")
                else {}
            ),
        }

        config = {"configurable": {"thread_id": conversation_id}}
        final_output = ""
        verdict = "PASS"

        async for event in self.graph.astream(initial_state, config=config):
            for node_name, node_state in event.items():
                phase = node_state.get("workflow_phase", "executing")
                verdict = node_state.get("verification_verdict", verdict)
                if node_state.get("final_response"):
                    final_output = node_state["final_response"]

                yield AgentRunEvent(
                    event_type="step_started",
                    task_id=task_spec.task_id,
                    run_id=active_run_id,
                    data={"step_id": node_name, "node": node_name, "phase": phase},
                )

                if node_name == "verifier":
                    yield AgentRunEvent(
                        event_type="verification_result",
                        task_id=task_spec.task_id,
                        run_id=active_run_id,
                        data={
                            "verdict": verdict,
                            "reason": node_state.get("critique_notes", ""),
                            "groundedness_score": node_state.get(
                                "groundedness_score", 1.0
                            ),
                        },
                    )

        if verdict in ("FAILED", "REJECTED"):
            yield AgentRunEvent(
                event_type="failed",
                task_id=task_spec.task_id,
                run_id=active_run_id,
                data={
                    "error": final_output or f"Execution halted by {verdict}",
                    "verdict": verdict,
                },
            )
        else:
            yield AgentRunEvent(
                event_type="completed",
                task_id=task_spec.task_id,
                run_id=active_run_id,
                data={"output": final_output, "verdict": "PASS"},
            )

    execute_task_spec = execute
