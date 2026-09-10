# JakeAI — Engineering Master

## 1. PURPOSE

JakeAI is developed around four core capabilities:

1. Complex AI Orchestration
2. Context & Data Management
3. Cost Optimization
4. LLMOps & AI Safety

All engineering work must serve one or more of these capabilities.

A task that does not materially contribute to one of these capabilities must be treated as out of scope unless explicitly justified.

---

## 2. ENGINEERING MODEL

Every capability follows:

MAKE IT WORK
→ MAKE IT RIGHT
→ MAKE IT FAST

### MAKE IT WORK

Goal:
The required capability actually functions end-to-end.

Focus:
- missing functionality;
- broken integration;
- required interfaces;
- required data flow.

Do not optimize aggressively.

### MAKE IT RIGHT

Goal:
The capability is logically correct and architecturally coherent.

Focus:
- invariants;
- contracts;
- canonical authority;
- correctness;
- data integrity;
- security boundaries;
- failure semantics.

### MAKE IT FAST

Goal:
The capability is efficient, scalable, observable and resilient.

Focus:
- latency;
- throughput;
- token consumption;
- memory;
- I/O;
- concurrency;
- caching;
- resource usage.

Optimization is only valid after correctness is established.

---

## 3. WORK RULE

WORK is incremental capability completion.

WORK MUST:

- inspect existing implementation;
- preserve working components;
- implement missing functionality;
- repair blocking defects;
- integrate with existing active paths.

WORK MUST NOT:

- rewrite the whole subsystem;
- optimize unrelated code;
- remove working implementations without evidence;
- introduce duplicate architecture;
- perform broad cleanup.

---

## 4. IMPLEMENTATION CLASSIFICATION

Before coding, classify every relevant component as:

KEEP
Already working and compatible.

EXTEND
Working component requiring additional capability.

REPAIR
Existing component whose incorrect behavior blocks the capability.

REPLACE
Existing component that cannot satisfy the required contract.

REMOVE
Only if proven obsolete or explicitly required.

DO NOT TOUCH
Unrelated component.

---

## 5. REQUIRED IMPLEMENTATION STYLE

Each WORK task must define:

- target behavior;
- target architecture;
- target data flow;
- exact algorithm;
- exact interfaces;
- exact implementation location;
- test matrix;
- forbidden alternatives.

The worker must not invent important architecture when the task has already specified it.

---

## 6. CORE CAPABILITY QUALITY BAR

A capability is not considered complete merely because:

- a module exists;
- tests pass;
- an API returns 200;
- a framework is installed;
- a README claims support.

Completion requires real executable behavior.

---

## 7. CORE CAPABILITY PRIORITY

When conflicts occur:

Correctness
>
Security
>
Data integrity
>
Capability completeness
>
Performance
>
Code elegance

Do not trade correctness for performance.

Do not trade security for convenience.

---

## 8. ENGINEERING STOP CONDITION

Do exactly the assigned WORK task.

Do not automatically continue into RIGHT or FAST.

Those stages are separate verification activities.