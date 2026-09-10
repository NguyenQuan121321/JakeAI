import logging
import re
from typing import Any, Literal

from pydantic import BaseModel, Field

from app.agents.state import AgentState
from app.rag.context_selector import get_context_selector
from app.rag.retriever import get_hybrid_retriever

logger = logging.getLogger(__name__)


class SupervisorDecision(BaseModel):
    """Structured decision schema for multi-agent supervisor dispatch (TASK ORC-07)."""

    target_agent: Literal["financial_specialist", "finnapigo_tool", "synthesizer"]
    reasoning: str
    confidence: float = Field(default=1.0, ge=0.0, le=1.0)
    specialist_guidance: str | None = None


FINANCIAL_PATTERNS = [
    r"(?i)\b(?:ebitda|margins?|revenues?|profits?|expenses?|ratios?|balances?|debts?|equity)\b",
    r"(?i)\b(?:cash\s*flow|incomes?|statements?|financial|ledgers?|taxes?|roi)\b",
    r"\$\d+",
]

TOOL_PATTERNS = [
    r"(?i)\b(?:finnapi|transactions?|profiles?|transfers?|invoices?|limits?)\b",
    r"(?i)\b(?:fetch|lookup|api\s*calls?|endpoints?|query\s*data)\b",
]


def classify_intent(prompt: str) -> str:
    """Classify prompt into target agent destination (deterministic heuristic)."""
    if re.search(r"(?i)\bfinnapi\b", prompt):
        return "finnapigo_tool"

    for pattern in FINANCIAL_PATTERNS:
        if re.search(pattern, prompt):
            return "financial_specialist"

    for pattern in TOOL_PATTERNS:
        if re.search(pattern, prompt):
            return "finnapigo_tool"

    return "synthesizer"


async def decide_supervisor_route(
    prompt: str, tenant_id: str = "default"
) -> SupervisorDecision:
    """Produce a structured routing decision using model reasoning with fallback heuristic."""
    try:
        from app.agent.backends.base import AgentMessage, BackendRequest
        from app.agent.backends.jakeai import JakeAIBackend

        backend = JakeAIBackend()
        system_instruction = (
            "You are the Supervisor Agent in JakeAI. You must analyze the user query and route it "
            "to exactly one specialized downstream agent: 'financial_specialist', 'finnapigo_tool', or 'synthesizer'.\n"
            "- 'financial_specialist': Quantitative calculations, EBITDA, margins, revenues, expenses, profit/loss.\n"
            "- 'finnapigo_tool': FinnApiGo banking integrations, account balance lookup, transactions list, tenant limits.\n"
            "- 'synthesizer': General conversation, greetings, overview questions, questions not requiring financial analysis or banking tools.\n"
            "Respond strictly with a JSON object format:\n"
            '{"target_agent": "<agent>", "reasoning": "<short rationale>"}'
        )
        req = BackendRequest(
            messages=[
                AgentMessage(role="system", content=system_instruction),
                AgentMessage(role="user", content=prompt),
            ],
            temperature=0.0,
            max_tokens=150,
            tenant_id=tenant_id,
        )
        resp = await backend.generate(req)
        if resp.content:
            import json

            cleaned = resp.content.strip()
            if "```json" in cleaned:
                cleaned = cleaned.split("```json")[1].split("```")[0].strip()
            elif "```" in cleaned:
                cleaned = cleaned.split("```")[1].split("```")[0].strip()
            data = json.loads(cleaned)
            target = data.get("target_agent")
            if target in ("financial_specialist", "finnapigo_tool", "synthesizer"):
                return SupervisorDecision(
                    target_agent=target,
                    reasoning=data.get("reasoning", "Model-driven routing decision"),
                    confidence=0.95,
                )
    except Exception as exc:
        logger.debug("Model supervisor routing fallback to heuristic: %s", exc)

    fallback_target = classify_intent(prompt)
    return SupervisorDecision(
        target_agent=fallback_target,  # type: ignore[arg-type]
        reasoning=f"Classified intent via rule: {fallback_target}",
        confidence=0.85,
    )


_retriever = get_hybrid_retriever()
_context_selector = get_context_selector()


async def supervisor_node(state: AgentState) -> dict[str, Any]:
    """Execute supervisor routing logic across specialized agents and retrieve tenant context."""
    prompt = state.get("prompt", "")
    tenant_id = state.get("tenant_id", "default")
    revision_count = state.get("revision_count", 0)
    retrieved_chunks = state.get("retrieved_chunks", [])

    # Populate contextual chunks from hybrid retriever & context selector if not already provided
    if not retrieved_chunks and prompt.strip():
        try:
            retrieval_res = await _retriever.retrieve(
                query=prompt,
                tenant_id=tenant_id,
                top_k=5,
            )
            selection_res = _context_selector.select_context(
                candidates=retrieval_res.chunks,
                query=prompt,
                tenant_id=tenant_id,
                max_tokens=600,
            )
            retrieved_chunks = [c.model_dump() for c in selection_res.selected_chunks]
        except Exception:
            retrieved_chunks = []

    # If already under revision from verifier critique, preserve specialized route
    if state.get("verification_verdict") == "NEEDS_REVISION" and revision_count < 2:
        target = state.get("next_agent", "financial_specialist")
        if target in ("supervisor", "verifier", "", None):
            decision = await decide_supervisor_route(prompt, tenant_id=tenant_id)
            target = (
                "financial_specialist"
                if decision.target_agent == "synthesizer"
                else decision.target_agent
            )
        return {
            "current_agent": "supervisor",
            "workflow_phase": "re_routing",
            "next_agent": target,
            "mascot_state": "thinking",
            "retrieved_chunks": retrieved_chunks,
            "messages": [
                *state.get("messages", []),
                f"Supervisor: Routing to '{target}' for revision {revision_count + 1}.",
            ],
        }

    decision = await decide_supervisor_route(prompt, tenant_id=tenant_id)
    target = decision.target_agent
    return {
        "current_agent": "supervisor",
        "workflow_phase": "routing",
        "next_agent": target,
        "mascot_state": "thinking",
        "revision_count": revision_count,
        "retrieved_chunks": retrieved_chunks,
        "messages": [
            *state.get("messages", []),
            f"Supervisor: {decision.reasoning}. Dispatching to '{target}'.",
        ],
    }
