"""Supervisor and intent routing node for LangGraph multi-agent orchestration."""

import re
from typing import Any

from app.agents.state import AgentState

FINANCIAL_PATTERNS = [
    r"(?i)\b(?:ebitda|margins?|revenues?|profits?|expenses?|ratios?|balances?|debts?|equity)\b",
    r"(?i)\b(?:cash\s*flow|incomes?|statements?|financial|ledgers?|taxes?|roi)\b",
    r"\$\d+",
]

TOOL_PATTERNS = [
    r"(?i)\b(?:finnapi|accounts?|transactions?|profiles?|transfers?|invoices?|limits?)\b",
    r"(?i)\b(?:fetch|lookup|api\s*calls?|endpoints?|query\s*data)\b",
]


def classify_intent(prompt: str) -> str:
    """Classify prompt into target agent destination."""
    for pattern in FINANCIAL_PATTERNS:
        if re.search(pattern, prompt):
            return "financial_specialist"

    for pattern in TOOL_PATTERNS:
        if re.search(pattern, prompt):
            return "finnapigo_tool"

    return "synthesizer"


async def supervisor_node(state: AgentState) -> dict[str, Any]:
    """Execute supervisor routing logic across specialized agents."""
    prompt = state.get("prompt", "")
    revision_count = state.get("revision_count", 0)

    # If already under revision from verifier critique, preserve specialized route
    if state.get("verification_verdict") == "NEEDS_REVISION" and revision_count < 2:
        target = state.get("next_agent", "financial_specialist")
        return {
            "current_agent": "supervisor",
            "workflow_phase": "re_routing",
            "next_agent": target,
            "mascot_state": "thinking",
            "messages": [
                *state.get("messages", []),
                f"Supervisor: Routing to '{target}' for revision {revision_count + 1}.",
            ],
        }

    target = classify_intent(prompt)
    return {
        "current_agent": "supervisor",
        "workflow_phase": "routing",
        "next_agent": target,
        "mascot_state": "thinking",
        "revision_count": revision_count,
        "messages": [
            *state.get("messages", []),
            f"Supervisor: Classified query intent. Dispatching to '{target}'.",
        ],
    }
