# JAKEAI REPAIR — REPAIR PLANNING

Using:

- verified repair findings
- current architecture
- repository state
- dependency graph
- existing tests

construct the executable Repair plan.

Do not implement code.

Group work into:

## R1 — Request / Inference Correctness

Primary:
- CACHE-01
- PROV-02
- TOK-02
- DUP-02

## R2 — Infrastructure Correctness

Primary:
- PROV-01
- DUP-01
- PERF-01

## R3 — Streaming / Agent Correctness

Primary:
- PROV-04
- CACHE-03
- AGT-01
- AGT-03

## R4 — RAG Correctness

Primary:
- RAG-01
- RAG-02
- RAG-04

## R5 — Structural Repair

Primary:
- TYPE-01
- TYPE-02
- TYPE-03
- DUP-03
- DUP-04
- DUP-06

For each task define:

TASK ID
OBJECTIVE
WHY NOW
DEPENDENCIES
AFFECTED FILES
INVARIANT
REGRESSION TEST
SECURITY REQUIREMENTS
OBSERVABILITY REQUIREMENTS
ACCEPTANCE CRITERIA
FORBIDDEN CHANGES

Build a dependency graph.

Rules:

- correctness before optimization
- architectural prerequisite before dependent repair
- no parallel work on overlapping contracts
- no task may silently modify another task's invariant

Do not start implementation.

Write:

docs/ai-engineering/repair/repair-plan.md

and update:

docs/ai-engineering/state/repair-state.md

End with exactly one next task.