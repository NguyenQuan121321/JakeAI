# JAKEAI REPAIR — BOOTSTRAP

You are starting the REPAIR phase of JakeAI.

You are NOT authorized to modify production code yet.

Your job is to reconstruct the current engineering context using the smallest sufficient context.

Read:

1. Project Constitution / Master Engineering Orchestrator
2. Project Vision and Engineering Direction
3. Current project state
4. Current architecture documentation
5. docs/audits/static-code-analysis/
6. current CI/CD configuration
7. relevant repository structure

Do not assume the audit is automatically correct.
Do not assume the existing implementation is correct.

Your output must contain:

## 1. Current System Understanding

Explain:
- what JakeAI currently is
- major subsystem boundaries
- provider architecture
- gateway architecture
- cache architecture
- token accounting
- RAG
- Agent
- FinOps
- infrastructure
- CI/CD

## 2. Current Repair Scope

Identify all currently known repair findings.

Classify each:

VERIFIED
PARTIALLY VERIFIED
OUTDATED
NOT VERIFIED
FALSE POSITIVE

## 3. Dependency Graph

Group findings by dependency rather than numeric order.

Identify:
- findings that must be repaired before others
- findings that can be repaired independently
- findings that should be deferred

## 4. Risk Map

Identify:
- correctness risks
- security risks
- data/accounting risks
- performance risks
- migration risks
- regression risks

## 5. Repair Workstreams

Propose the execution sequence for:

R1 — Request / Inference Correctness
R2 — Infrastructure Correctness
R3 — Streaming / Agent Correctness
R4 — RAG Correctness
R5 — Structural / Type / Exception Repair

## 6. Do Not Implement

Do NOT:
- edit source files
- refactor code
- modify tests
- change CI
- add dependencies

The purpose of this session is to create a verified repair map.

## Final Output

End with:

CURRENT STATE
REPAIR PRIORITIES
DEPENDENCY GRAPH
BLOCKERS
NEXT TASK

Choose exactly one next task.
