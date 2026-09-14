"""Canonical capability keyword patterns for goal/step classification (R-ARCH-01).

Single authority for the "which specialist capability does this text belong to"
keyword heuristics. Every consumer (BoundedPlanner plan construction, AgentSelector
scoring/degraded fallback, LangGraph supervisor intent fallback) must classify via
these patterns so the layers cannot drift into divergent routing decisions.

Layer-specific concerns that are NOT capability classification stay local to their
layer (e.g. the planner's multi-source/approval plan-shaping rules, the supervisor's
generic tool-verb routing vocabulary for its own node vocabulary).
"""

from __future__ import annotations

import re

# Financial / quantitative analysis signal. Union of the historically divergent
# planner, agent-selector and supervisor keyword sets; plural forms included so a
# single pattern matches singular and plural surface forms. Balance lookups are
# banking operations, not financial analysis — they live in BANKING_PATTERN.
FINANCIAL_PATTERN = re.compile(
    r"(?i)\b(?:"
    r"ebitda|margins?|revenues?|expenses?|profits?|operating income|financial|"
    r"ratios?|variance|statements?|taxes?|tax|ledgers?|ledger|costs?|cost|"
    r"debts?|equity|cash\s*flow|incomes?|roi|turnovers?|spending|outlays?|"
    r"expenditures?|surplus(?:es)?|deficits?|profitability|earnings?|fiscal|"
    r"valuations?"
    r")\b|\$\d+"
)

# Banking / FinnApiGo API operation signal.
BANKING_PATTERN = re.compile(
    r"(?i)\b(?:"
    r"finnapi|account balance|balances?|bank|banking|transactions?|transfers?|"
    r"invoices?|limits?|account_id|profiles?"
    r")\b"
)

# Knowledge retrieval / RAG signal.
RETRIEVAL_PATTERN = re.compile(
    r"(?i)\b(?:"
    r"retriev\w+|search(?:es|ing)?|lookup|look\s+up|documents?|qdrant|bm25|rag|sources?|"
    r"query\s+docs?|find\s+documents?|cite|knowledge\s*(?:base|index)|handbooks?|"
    r"policies|policy|manuals?|reference\s*materials?"
    r")\b"
)

# Negative constraint patterns: detecting explicit user prohibitions
_NEGATION_PREFIX = re.compile(
    r"(?i)\b(?:do\s+not|don'?t|never|no\s+(?:need|use|call|access|run|execute)|without|refrain\s+from|avoid|forbid|prohibit)\s+(?:\w+\s+){0,3}"
)

_FINANCIAL_NEGATION = re.compile(
    _NEGATION_PREFIX.pattern
    + r"(?:financial|calculat\w+|ebitda|margin|revenue|expense|profit|cost|turnover)",
    re.IGNORECASE,
)

_BANKING_NEGATION = re.compile(
    _NEGATION_PREFIX.pattern
    + r"(?:finnapi|bank|banking|balance|transaction|account|transfer)",
    re.IGNORECASE,
)

_TERMINAL_NEGATION = re.compile(
    _NEGATION_PREFIX.pattern
    + r"(?:terminal|terminal_exec|shell|bash|exec|cmd|delete|dangerous|maintenance\s+script)",
    re.IGNORECASE,
)


def has_negative_constraint(constraint_type: str, text: str) -> bool:
    """Check if the text explicitly forbids a specific category of capability or tool."""
    if not text:
        return False
    c_lower = constraint_type.lower().strip()
    if c_lower in ("financial", "finance", "financial_analysis"):
        return bool(_FINANCIAL_NEGATION.search(text))
    if c_lower in ("banking", "bank", "banking_api", "finnapi"):
        return bool(_BANKING_NEGATION.search(text))
    if c_lower in ("terminal", "shell", "dangerous", "code_execution", "approval"):
        return bool(_TERMINAL_NEGATION.search(text))
    return False


__all__ = [
    "BANKING_PATTERN",
    "FINANCIAL_PATTERN",
    "RETRIEVAL_PATTERN",
    "has_negative_constraint",
]
