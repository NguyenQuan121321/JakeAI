# JAKEAI REPAIR PRINCIPLES

This document defines the engineering rules for the REPAIR phase.

REPAIR exists to restore correctness, remove verified defects, preserve valid behavior, and establish regression protection.

REPAIR is not a feature-development phase.

==================================================
1. BASELINE
==================================================

The official Repair baseline is the clean main branch at the audited baseline commit.

Do not use abandoned repair branches as architectural baselines.

Do not inherit unverified changes from previous repair attempts.

==================================================
2. SCOPE
==================================================

One task addresses one concrete root cause or one tightly coupled defect group explicitly named by the task.

Do not silently absorb other findings.

If another finding becomes necessary to complete the current task:
- identify the dependency;
- stop scope expansion;
- report it;
- wait for an explicit task/dependency decision.

==================================================
3. CORRECTNESS FIRST
==================================================

Priority order:

1. correctness
2. security
3. contract integrity
4. reliability
5. observability
6. performance
7. optimization

Do not optimize incorrect behavior.

==================================================
4. EVIDENCE FIRST
==================================================

Distinguish:

OBSERVATION
INFERENCE
RECOMMENDATION
IMPLEMENTATION

Never treat an audit recommendation as proof that the recommended implementation is correct.

Verify the actual repository.

==================================================
5. MINIMAL CHANGE
==================================================

Implement the smallest change that restores the required invariant.

Do not perform unrelated refactoring.

Do not rewrite working subsystems only because another architecture appears cleaner.

==================================================
6. REGRESSION PROTECTION
==================================================

Every repaired defect must have regression protection.

Preferred sequence:

reproduce defect
→ add regression test
→ implement fix
→ verify

Never weaken, remove, skip, suppress, or bypass tests.

==================================================
7. SECURITY
==================================================

Never weaken:

- tenant isolation
- authorization
- BYOK isolation
- secret protection
- approval gates
- tool permissions
- sandbox boundaries
- timeout controls
- cancellation behavior

==================================================
8. CI/CD
==================================================

Existing CI/CD is part of the verification system.

Do not redesign CI/CD during unrelated repair tasks.

A CI failure must be diagnosed and corrected before a task is considered complete.

Do not modify CI merely to hide a code defect.

==================================================
9. TEST TRUTH
==================================================

Never claim:
- test passed
- CI passed
- benchmark passed
- bug fixed

unless the result was actually verified.

==================================================
10. STATE
==================================================

The repository is the durable engineering memory.

Do not rely on conversation history.

Every task must leave a durable result in its task file.

==================================================
11. STOP CONDITION
==================================================

Stop when the assigned task is complete and verified.

Do not continue into the next Repair task.

==================================================
12. REPAIR GOAL
==================================================

The final Repair result is:

all official findings resolved or explicitly dispositioned
+
regression coverage
+
security preserved
+
CI green
+
architecture more consistent than before