# W-RAG-07 — Memory & Context

## OBJECTIVE

Combine conversation state, memory and retrieved evidence into one deterministic model-visible context.

## REQUIRED ORDER

system instructions
→ task constraints
→ relevant conversation history
→ verified memory
→ retrieved evidence
→ current user query

## RULE

Do not mix unverified memory with verified RAG evidence.

Mark evidence categories explicitly.

## CONTEXT PRIORITY

1. current task constraints;
2. verified source evidence;
3. verified durable memory;
4. relevant recent conversation;
5. lower-priority historical context.

## BUDGET

Build context within one explicit token budget.

Do not independently allocate incompatible budgets in multiple modules.

## TESTS

- multi-turn request;
- relevant memory;
- irrelevant memory;
- conflicting memory;
- RAG evidence;
- context overflow;
- tenant boundary.

## ACCEPTANCE

The final model-visible envelope is deterministic, bounded and evidence-aware.