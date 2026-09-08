# JAKEAI REPAIR EXECUTION PLAN

Official Repair Scope:
18 findings from the audited main baseline.

Baseline:
main / audited baseline commit ae90424

==================================================
ORDER
==================================================

REPAIR-00
CACHE-01 — Exact Cache Identity

REPAIR-01
PROV-02 — Structured Conversation Contract

REPAIR-02
TOK-02 — Canonical Token Accounting

REPAIR-03
DUP-02 — Canonical Provider Resolution

REPAIR-04
PROV-01 — Shared HTTP Lifecycle

REPAIR-05
DUP-01 — Centralized Redis Lifecycle

REPAIR-06
PERF-01 — Atomic Quota Reservation

REPAIR-07
PROV-04 — Real Streaming

REPAIR-08
CACHE-03 — Stable Agent Prompt Prefix

REPAIR-09
AGT-01 — Tool Output Budgeting

REPAIR-10
AGT-03 — Token-Aware Agent Memory

REPAIR-11
AGT-02 — Deferred Tool Discovery

REPAIR-12
RAG-01 — Real Embedding Architecture

REPAIR-13
RAG-02 — RAG Context Metadata

REPAIR-14
TOK-01 — Canonical Tokenizer Adoption

REPAIR-15
DUP-03 — Pricing Authority

REPAIR-16
BYOK-01 — Key Derivation Hardening

REPAIR-17
CI-01 — Local Verification Parity

REPAIR-18
Final Integration & Repair Verification

==================================================
DEPENDENCY RULES
==================================================

Request correctness precedes accounting and routing.

Cache identity precedes cache-related optimization.

Structured message contracts precede multi-turn accounting and provider behavior.

Shared infrastructure precedes concurrency/resource optimization.

Agent context budgeting precedes advanced agent context optimization.

Real embedding architecture precedes RAG optimization.

Structural consolidation follows correctness stabilization.

==================================================
EXECUTION RULE
==================================================

Only one Repair task is actively executed at a time.

A task must reach its completion criteria before the next task begins.

If CI fails:
the current task is not complete.

If a new defect is discovered outside scope:
record it as an additional observation;
do not silently merge it into the current task.

==================================================
REPAIR SUCCESS
==================================================

All official findings must be:

FIXED
or
EXPLICITLY DISPOSITIONED WITH EVIDENCE

No finding may be silently ignored.

No additional defect may silently replace an official finding.