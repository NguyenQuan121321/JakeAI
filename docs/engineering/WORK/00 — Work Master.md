# JakeAI — Work Master

## 1. PURPOSE

WORK exists to make missing JakeAI capabilities functionally complete.

WORK is NOT a rewrite phase.

WORK is NOT a performance optimization phase.

WORK is NOT a general cleanup phase.

---

## 2. CORE RULE

MAKE THE MISSING PART WORK WITHOUT BREAKING THE PART THAT ALREADY WORKS.

---

## 3. FIRST ACTION: DISCOVERY

Before editing code:

1. inspect repository structure;
2. inspect the relevant subsystem;
3. trace the active call path;
4. inspect related models/interfaces;
5. inspect existing tests;
6. determine which code is active;
7. identify existing functionality;
8. identify missing functionality;
9. identify blockers.

Do not begin implementation before this classification is complete.

---

## 4. COMPONENT CLASSIFICATION

For every relevant file/class/function, classify:

KEEP
EXTEND
REPAIR
REPLACE
REMOVE
DO NOT TOUCH

Record why.

---

## 5. REQUIRED IMPLEMENTATION ORDER

Step 1:
Identify the exact missing behavior.

Step 2:
Identify the existing component responsible.

Step 3:
Reuse an existing abstraction if it can satisfy the requirement.

Step 4:
Repair the responsible abstraction if its current behavior is incorrect.

Step 5:
Add only the missing functionality.

Step 6:
Connect the new functionality to the active execution path.

Step 7:
Add regression tests.

Step 8:
Run targeted verification.

Step 9:
Run broader relevant verification.

Step 10:
Stop.

---

## 6. IMPLEMENTATION RULE

Every task must explicitly state:

TARGET FUNCTION
TARGET INPUT
TARGET OUTPUT
TARGET DATA FLOW
TARGET ALGORITHM
TARGET FAILURE BEHAVIOR

The worker must implement the specified behavior.

---

## 7. DO NOT INVENT ALGORITHMS

If the task specifies an algorithm, use it.

Examples:

- SHA-256 canonical identity → use SHA-256.
- Reciprocal Rank Fusion → use RRF formula.
- cosine similarity → use cosine similarity.
- bounded retries → use specified retry policy.
- exact cache → exact identity, not semantic similarity.
- real embedding model → use a real embedding model, not a hash-based surrogate.

Do not substitute an easier heuristic.

---

## 8. DO NOT FAKE A CAPABILITY

The following are prohibited:

- fake embeddings;
- fake parallelism;
- hard-coded routing disguised as intelligence;
- test-only implementations;
- mocked production behavior;
- placeholder algorithms presented as production behavior;
- “future support” represented as current support.

---

## 9. COMPATIBILITY

Preserve compatible public behavior unless the task explicitly changes the contract.

When replacing an implementation:

- preserve the public contract where possible;
- migrate callers;
- remove the obsolete active path;
- prevent two competing authorities from remaining active.

---

## 10. OPTIMIZATION BOUNDARY

Do not perform optimization during WORK unless optimization is required for basic functionality.

Do not prematurely optimize:

- CPU;
- memory;
- latency;
- network;
- token usage;
- database queries.

Those belong primarily to FAST or later lifecycle phases.

---

## 11. TEST STANDARD

Every WORK task must prove:

1. capability exists;
2. capability is reachable through the intended path;
3. existing behavior remains intact;
4. relevant failure cases behave correctly.

---

## 12. COMPLETION

WORK is complete when the assigned capability or missing portion actually runs through its intended path.

Do not claim the capability is optimized.

Do not claim it is production-perfect.

Do not claim it has passed RIGHT or FAST.

Only claim:
FUNCTIONALLY IMPLEMENTED AND VERIFIED.