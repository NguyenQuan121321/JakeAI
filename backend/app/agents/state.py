from __future__ import annotations

from typing import TYPE_CHECKING, Any, cast

from typing_extensions import TypedDict

if TYPE_CHECKING:
    from app.agent.state.models import RunState


class AgentState(TypedDict, total=False):
    """Execution state container passed across all LangGraph agent nodes."""

    # Input & Security Context
    prompt: str
    tenant_id: str
    user_id: str
    roles: list[str]
    permissions: list[str]
    conversation_id: str
    correlation_id: str
    obo_token: str
    raw_token: str

    # Dynamic Workflow Routing
    next_agent: str
    current_agent: str
    workflow_phase: str

    # Agent Intermediary Buffers
    messages: list[str]
    tool_calls: list[dict[str, Any]]
    financial_analysis: dict[str, Any]

    # RAG Context & Retrieval Buffers
    retrieved_chunks: list[dict[str, Any]]
    groundedness_score: float

    # Quality Assurance & Self-Correction
    verification_verdict: str  # "PASS" or "NEEDS_REVISION"
    critique_notes: str
    revision_count: int

    # Final Output Delivery
    final_response: str
    mascot_state: str  # "idle", "thinking", "success", "alert"
    citations: list[dict[str, Any]]


def run_state_to_agent_state(run: Any) -> AgentState:
    """Convert canonical RunState instance into LangGraph AgentState dictionary."""
    if hasattr(run, "to_agent_state"):
        raw_dict = run.to_agent_state()
        if isinstance(raw_dict, dict):
            return cast("AgentState", raw_dict)

    from app.agent.state.models import RunState

    if isinstance(run, RunState):
        return cast("AgentState", run.to_agent_state())
    if isinstance(run, dict):
        return cast("AgentState", dict(run))
    return cast("AgentState", {})


def agent_state_to_run_state(state: AgentState, task_id: str, run_id: str) -> RunState:
    """Construct canonical RunState from LangGraph AgentState dictionary."""
    from app.agent.state.models import RunState

    return RunState.from_agent_state(state, task_id=task_id, run_id=run_id)
