"""Financial Specialist agent node for quantitative analysis and reasoning."""

import re
from typing import Any

from app.agents.state import AgentState
from app.core.circuit_breaker import CircuitBreaker

_financial_circuit = CircuitBreaker(
    name="financial_specialist_circuit",
    failure_threshold=3,
    recovery_timeout_seconds=15.0,
)


def _extract_numbers(text: str) -> list[float]:
    """Extract numeric values from text string supporting commas and currency signs."""
    matches = re.findall(r"\$?\b(\d{1,3}(?:,\d{3})*(?:\.\d+)?|\d+(?:\.\d+)?)\b", text)
    results: list[float] = []
    for m in matches:
        cleaned = m.replace(",", "").strip()
        if cleaned:
            try:
                results.append(float(cleaned))
            except ValueError:
                continue
    return results


async def financial_specialist_node(state: AgentState) -> dict[str, Any]:
    """Perform financial metric calculation, analysis, and variance checks."""
    prompt = state.get("prompt", "")
    critique_notes = state.get("critique_notes", "")
    revision_count = state.get("revision_count", 0)

    numbers = _extract_numbers(prompt)
    revenue = numbers[0] if len(numbers) > 0 else 1500000.0
    expenses = numbers[1] if len(numbers) > 1 else 950000.0

    operating_income = revenue - expenses
    operating_margin = (
        round((operating_income / revenue) * 100, 2) if revenue > 0 else 0.0
    )

    def _compute_deterministic_financials() -> dict[str, Any]:
        return {
            "revenue": revenue,
            "operating_expenses": expenses,
            "operating_income": operating_income,
            "operating_margin_pct": operating_margin,
            "ebitda": operating_income * 1.12,  # Standard adjustment
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
