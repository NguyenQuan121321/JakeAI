"""Canonical deterministic financial-analysis capability (single formula authority).

Defines the rule-based financial specialist business semantics — default
figures, figure extraction, and the operating-income / operating-margin /
EBITDA formulas — exactly once. Drivers consume this module:

- ``app/agent/execution/engine.py`` (canonical DAG engine financial branch),
- ``app/agents/financial_specialist.py`` (LangGraph adapter node),
- ``app/agent/planning/planner.py`` (degraded deterministic fallback).

Driver-specific input derivation (prompt extraction, ledger coupling) and
presentation rounding stay with the callers; the formulas and business
constants may not be re-defined elsewhere (R-ARCH-02 dependency boundaries).
"""

from __future__ import annotations

import re

DEFAULT_REVENUE = 1_500_000.0
DEFAULT_OPERATING_EXPENSES = 950_000.0
EBITDA_ADJUSTMENT_FACTOR = 1.12

_FIGURE_PATTERN = re.compile(r"\$?\b(\d{1,3}(?:,\d{3})*(?:\.\d+)?|\d+(?:\.\d+)?)\b")


def extract_financial_figures(text: str) -> list[float]:
    """Extract numeric figures from text, supporting commas and currency signs."""
    results: list[float] = []
    for m in _FIGURE_PATTERN.findall(text):
        cleaned = m.replace(",", "").strip()
        if cleaned:
            try:
                results.append(float(cleaned))
            except ValueError:
                continue
    return results


def operating_income(revenue: float, operating_expenses: float) -> float:
    """Operating income = revenue - operating expenses."""
    return revenue - operating_expenses


def operating_margin_pct(income: float, revenue: float) -> float:
    """Operating margin as a percentage, rounded to two decimals."""
    return round((income / revenue) * 100, 2) if revenue > 0 else 0.0


def ebitda(income: float) -> float:
    """Standard adjusted EBITDA derived from operating income."""
    return income * EBITDA_ADJUSTMENT_FACTOR
