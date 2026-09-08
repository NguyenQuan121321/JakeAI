# JakeAI Repair Master Prompt

You are operating in the REPAIR phase of JakeAI.

The purpose of REPAIR is to restore correctness, eliminate verified defects, preserve valid behavior, and establish regression protection for the official Repair scope.

REPAIR is not a feature-development phase.

==================================================
1. REPAIR OBJECTIVE
==================================================

The objective of REPAIR is:

identify verified defects
→ repair root causes
→ prove corrected behavior
→ preserve system contracts
→ preserve security
→ preserve AI quality
→ preserve CI/CD integrity
→ leave durable evidence.

The official Repair scope consists of the findings explicitly authorized by the current Repair plan and task files.

Do not expand the official scope without explicit authorization.

==================================================
2. REPAIR BASELINE
==================================================

Repair must start from the authorized clean baseline.

Do not inherit code from abandoned repair branches.

Do not treat previous failed repair attempts as trusted implementation.

Use the current approved main baseline and its verified repository state.

==================================================
3. OFFICIAL FINDINGS VS ADDITIONAL OBSERVATIONS
==================================================

Official findings are those explicitly included in the Repair execution plan.

If a worker discovers another defect:

- classify it as an additional observation;
- do not automatically add it to the official Repair scope;
- do not change severity counts;
- do not silently create another repair task;
- preserve the information for later disposition.

An additional defect must never replace an official finding.

==================================================
4. ONE TASK = ONE REPAIR UNIT
==================================================

Each Repair task must represent:

one root cause
or
one tightly coupled defect group that cannot be safely separated.

A task must not opportunistically repair multiple unrelated findings.

The worker must remain inside the task's declared scope.

==================================================
5. REQUIRED REPAIR LOOP
==================================================

Every Repair task follows:

UNDERSTAND
→ VERIFY
→ DEFINE INVARIANT
→ REPRODUCE
→ REGRESSION TEST
→ IMPLEMENT
→ FOCUSED VALIDATION
→ BROADER VALIDATION
→ CI
→ RESULT

Do not skip the verification stage.

==================================================
6. AUDIT IS EVIDENCE, NOT AUTHORITY FOR IMPLEMENTATION
==================================================

Audit findings provide evidence and recommendations.

They do not automatically determine the final architecture.

The worker must verify:

- current source;
- current contracts;
- existing tests;
- dependencies;
- downstream behavior.

Treat:

finding
and
recommended solution

as separate concepts.

==================================================
7. CORRECTNESS PRIORITY
==================================================

Repair priority order:

1. correctness
2. security
3. contract integrity
4. reliability
5. observability
6. performance
7. optimization

Never perform an optimization that preserves or worsens an underlying correctness defect.

==================================================
8. CRITICAL SYSTEM INVARIANTS
==================================================

Repair must protect these categories.

### Request Integrity

The model must receive the intended semantic request.

### Conversation Integrity

Multi-turn history must preserve required roles, ordering, and meaning.

### Provider Integrity

The intended provider and model must be resolved consistently.

### Cache Integrity

Different semantic requests must not produce incorrect exact-cache reuse.

### Accounting Integrity

Usage, quota, cost, savings, and provider usage must not contradict one another.

### Resource Integrity

Shared infrastructure must have explicit ownership and lifecycle.

### Agent Integrity

Tools, memory, context, permissions, cancellation, and execution state must remain controlled.

### RAG Integrity

Retrieval, grounding, tenant filtering, evidence, and citations must remain correct.

### Security Integrity

No repair may weaken tenant isolation, BYOK protection, authorization, secret handling, or execution controls.

==================================================
9. TOKEN / COST DISCIPLINE
==================================================

Token reduction is not automatically a success.

Any optimization must preserve:

- correctness
- quality
- grounding
- relevant context
- security

When measuring optimization:

baseline
→ optimized
→ quality comparison
→ cost/token comparison

Do not double-count savings.

Do not confuse:

physical tokens removed
provider cached tokens
response-cache avoided tokens
effective billed tokens.

==================================================
10. RAG DISCIPLINE
==================================================

RAG repairs must preserve:

- tenant isolation
- metadata
- source identity
- citation integrity
- grounding
- retrieval semantics.

Replacing a retrieval mechanism requires measurable evidence.

Do not declare semantic retrieval fixed solely because vectors exist.

==================================================
11. AGENT DISCIPLINE
==================================================

Agent repairs must preserve:

- tool authorization;
- risk controls;
- approval boundaries;
- cancellation;
- timeout behavior;
- execution limits;
- tenant context.

Context optimization must not silently remove essential user constraints.

Tool output must not become an uncontrolled context injection path.

==================================================
12. PROVIDER DISCIPLINE
==================================================

Provider architecture must have one authoritative source for:

- provider resolution;
- provider contract;
- supported model capabilities;
- provider-specific transformation.

Do not create competing routing or request-transformation logic.

==================================================
13. INFRASTRUCTURE DISCIPLINE
==================================================

Infrastructure changes must define:

- ownership;
- initialization;
- reuse;
- failure behavior;
- shutdown.

A resource must not have multiple competing lifecycle owners.

==================================================
14. MIGRATION DISCIPLINE
==================================================

Any change affecting:

- encryption
- cache schemas
- vector dimensions
- persisted data
- API contracts
- serialized formats

must explicitly consider migration and backward compatibility.

Never make an incompatible persistence change without a migration strategy.

==================================================
15. TEST REQUIREMENTS
==================================================

Every Repair task must have tests appropriate to its defect.

At minimum:

- regression test for the defect;
- affected subsystem validation.

Where relevant also require:

- concurrency tests;
- provider contract tests;
- security tests;
- RAG evaluation;
- AI evaluation;
- benchmark;
- migration tests.

Tests must validate behavior.

==================================================
16. CI/CD REQUIREMENTS
==================================================

Existing CI/CD remains authoritative verification infrastructure.

Do not rebuild or redesign CI merely because Repair is running.

A Repair task is not complete while required CI checks remain unexplained or failing.

Do not modify CI to hide an implementation problem.

==================================================
17. ACCEPTANCE
==================================================

A Repair task may only be declared complete when:

- root cause is identified;
- required invariant is restored;
- implementation is within scope;
- regression protection exists;
- required tests pass;
- required static/security checks pass;
- CI passes where applicable;
- acceptance criteria are explicitly evaluated;
- remaining risks are recorded.

==================================================
18. TASK RESULT
==================================================

The assigned task file must record:

STATUS

ROOT CAUSE

INVARIANT

CHANGES

MODIFIED FILES

TESTS ADDED/CHANGED

TESTS EXECUTED

ACTUAL RESULTS

ACCEPTANCE CRITERIA

SECURITY VERIFICATION

CI VERIFICATION

REMAINING ISSUES

RISKS

NEXT TASK

Do not report "completed" without evidence.

==================================================
19. REPAIR EXIT
==================================================

REPAIR ends only after every official finding has been:

FIXED
or
EXPLICITLY DISPOSITIONED WITH EVIDENCE.

The final integration check must confirm:

- no official finding was silently omitted;
- no repair introduced a known regression;
- CI remains healthy;
- security boundaries remain intact;
- AI/RAG quality gates remain valid.

Only then may the project move to STABILIZE.

==================================================
20. FINAL RULE
==================================================

REPAIR is successful when JakeAI is more correct and more defensible than before.

Not when more code has been written.

Not when documentation says "fixed".

Not when CI was manipulated into green.

Evidence determines completion.