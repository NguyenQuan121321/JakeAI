# REPAIR-02 — TOK-02 CANONICAL TOKEN ACCOUNTING

Finding:
TOK-02

Priority:
CRITICAL

Objective:
Make token accounting reflect the actual model-visible input envelope.

Current defect to verify:
Gateway token accounting is based primarily on last_user_msg.

Required invariant:

Recorded prompt usage must represent all relevant model-visible input:

- system
- conversation history
- user query
- tools
- RAG context when present

Required accounting dimensions:

- raw_input_tokens
- optimized_input_tokens
- provider_cached_input_tokens
- completion_tokens
- physical_tokens_pruned
- response_cache_avoided_tokens
- effective_billed_tokens

Final usage should use provider-reported usage for reconciliation when available.

Required tests:

Given:
system = 2000
history = 3000
query = 50

the accounting layer must not report raw input as 50.

Also test:
- tools
- RAG context
- optimized context
- provider cache telemetry
- response cache hit

Forbidden:

Do not introduce a second accounting system.
Do not repair TOK-01 as a separate concern.

Definition of done:
Accounting reflects model-visible semantics and regression tests prove it.