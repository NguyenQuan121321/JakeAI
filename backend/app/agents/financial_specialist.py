"""Financial Specialist agent node for quantitative analysis and reasoning.

Business semantics (figure extraction, operating income / margin / EBITDA
formulas, default figures) are owned by the canonical capability module
``app.agent.capabilities.financial_analysis``; this adapter node only wires
graph state, resilience, and messaging around it (R-ARCH-02).
"""

from typing import Any

from app.agent.capabilities.financial_analysis import (
    DEFAULT_OPERATING_EXPENSES,
    DEFAULT_REVENUE,
    extract_financial_figures,
)
from app.agent.capabilities.financial_analysis import (
    ebitda as compute_ebitda,
)
from app.agent.capabilities.financial_analysis import (
    operating_income as compute_operating_income,
)
from app.agent.capabilities.financial_analysis import (
    operating_margin_pct as compute_operating_margin_pct,
)
from app.agents.state import AgentState
from app.core.circuit_breaker import CircuitBreaker

_financial_circuit = CircuitBreaker(
    name="financial_specialist_circuit",
    failure_threshold=3,
    recovery_timeout_seconds=15.0,
)


async def financial_specialist_node(state: AgentState) -> dict[str, Any]:
    """Perform financial metric calculation, analysis, and variance checks."""
    prompt = state.get("prompt", "")
    critique_notes = state.get("critique_notes", "")
    revision_count = state.get("revision_count", 0)

    figures = extract_financial_figures(prompt)
    revenue = figures[0] if len(figures) > 0 else DEFAULT_REVENUE
    expenses = figures[1] if len(figures) > 1 else DEFAULT_OPERATING_EXPENSES

    operating_income = compute_operating_income(revenue, expenses)
    operating_margin = compute_operating_margin_pct(operating_income, revenue)

    def _compute_deterministic_financials() -> dict[str, Any]:
        return {
            "revenue": revenue,
            "operating_expenses": expenses,
            "operating_income": operating_income,
            "operating_margin_pct": operating_margin,
            "ebitda": compute_ebitda(operating_income),
            "tenant_id": state.get("tenant_id", "default"),
            "currency": "USD",
            "grounded": True,
        }

    analysis: dict[str, Any] = await _financial_circuit.call_with_fallback(
        primary_fn=_compute_deterministic_financials,
        deterministic_fallback_fn=_compute_deterministic_financials,
    )

    status_msg = (
        f"Financial Specialist: Computed operating income (${operating_income:,.2f}) "
        f"and operating margin ({operating_margin}%)."
    )
    if critique_notes:
        status_msg += f" (Corrected based on critique: {critique_notes})"

    return {
        "current_agent": "financial_specialist",
        "workflow_phase": "financial_analysis",
        "financial_analysis": analysis,
        "mascot_state": "thinking",
        "next_agent": "verifier",
        "messages": [
            *state.get("messages", []),
            status_msg,
        ],
        "revision_count": revision_count,
    }
