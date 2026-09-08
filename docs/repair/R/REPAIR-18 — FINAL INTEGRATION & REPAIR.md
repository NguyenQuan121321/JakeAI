# REPAIR-18 — FINAL INTEGRATION & REPAIR VERIFICATION

Objective:

Determine whether the entire REPAIR phase is actually complete.

Do not introduce new feature work.

Do not perform opportunistic refactoring.

==================================================
1. FINDING STATUS
==================================================

Verify every official Repair finding:

CACHE-01
PROV-02
TOK-02
CACHE-03
PROV-01
RAG-01
AGT-01
DUP-01
PERF-01
DUP-02
TOK-01
PROV-04
DUP-03
BYOK-01
AGT-02
AGT-03
RAG-02
CI-01

Each must be:

FIXED
or
EXPLICITLY DISPOSITIONED WITH EVIDENCE

==================================================
2. CROSS-SYSTEM REVIEW
==================================================

Check interactions between:

- cache and provider identity
- message contract and token accounting
- token accounting and FinOps
- provider routing and BYOK
- HTTP lifecycle and streaming
- Redis lifecycle and quota
- Agent context and prompt caching
- Agent tools and memory
- RAG context and token accounting
- embedding architecture and tenant isolation

==================================================
3. GLOBAL VALIDATION
==================================================

Run relevant:

- unit tests
- integration tests
- contract tests
- Ruff
- Mypy
- Bandit
- coverage
- AI benchmark
- token benchmark
- RAG regression
- OpenAPI contract
- container checks
- CI

Existing CI gates must remain intact.

==================================================
4. REGRESSION REVIEW
==================================================

Verify the Repair did not:

- break public APIs
- weaken security
- break BYOK isolation
- break tenant isolation
- reduce AI quality
- reduce RAG grounding
- break streaming
- corrupt accounting
- introduce duplicate authorities

==================================================
5. FINAL DECISION
==================================================

Return exactly one:

REPAIR COMPLETE

REPAIR COMPLETE WITH DOCUMENTED RISKS

REPAIR INCOMPLETE

If incomplete:
identify the highest-priority blocker and the exact task required to resolve it.

Do not begin Stabilize.

==================================================
6. RESULT
==================================================

Create:

docs/repair/R/REPAIR-18 — Final Integration & Repair Verification.md

Record:

- finding-by-finding status
- tests
- CI
- security validation
- AI benchmark
- RAG regression
- remaining risks
- deferred items
- final decision
- entry conditions for STABILIZE