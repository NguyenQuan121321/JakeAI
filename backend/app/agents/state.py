"""Shared state schemas for LangGraph multi-agent orchestration."""

from typing import Any

from typing_extensions import TypedDict


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
