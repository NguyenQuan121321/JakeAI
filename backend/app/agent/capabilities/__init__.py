"""Canonical rule-based specialist capability logic.

Business semantics for deterministic specialists live in this package so that
every orchestration driver (canonical ExecutionEngine, LangGraph adapter
nodes, degraded planner fallbacks) delegates to one authority instead of
re-defining formulas per driver (R-ARCH-02 dependency boundaries).
"""

from app.agent.capabilities.financial_analysis import (
    DEFAULT_OPERATING_EXPENSES,
    DEFAULT_REVENUE,
    EBITDA_ADJUSTMENT_FACTOR,
    ebitda,
    extract_financial_figures,
    operating_income,
    operating_margin_pct,
)

__all__ = [
    "DEFAULT_OPERATING_EXPENSES",
    "DEFAULT_REVENUE",
    "EBITDA_ADJUSTMENT_FACTOR",
    "ebitda",
    "extract_financial_figures",
    "operating_income",
    "operating_margin_pct",
]
