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
    r"debts?|equity|cash\s*flow|incomes?|roi"
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
    r"retriev\w+|search(?:es|ing)?|lookup|documents?|qdrant|bm25|rag|sources?|"
    r"query\s+docs?|find\s+documents?|cite"
    r")\b"
)


__all__ = [
    "BANKING_PATTERN",
    "FINANCIAL_PATTERN",
    "RETRIEVAL_PATTERN",
]
