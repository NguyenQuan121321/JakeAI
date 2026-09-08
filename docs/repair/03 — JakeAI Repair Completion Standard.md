# JAKEAI REPAIR COMPLETION STANDARD

A Repair task is COMPLETE only when all applicable requirements below are satisfied.

==================================================
A. ROOT CAUSE
==================================================

The actual defect has been identified.

The implementation addresses the root cause rather than only the symptom.

==================================================
B. INVARIANT
==================================================

The required invariant has been explicitly defined.

The implementation restores the invariant.

==================================================
C. CODE
==================================================

The implementation is scoped to the assigned task.

No unrelated refactor was introduced.

No unnecessary dependency was added.

==================================================
D. TESTS
==================================================

Required regression tests exist.

Focused tests pass.

Relevant subsystem tests pass.

==================================================
E. QUALITY
==================================================

Relevant checks pass:

- Ruff
- Mypy
- Bandit
- relevant contract tests

==================================================
F. SECURITY
==================================================

No security boundary was weakened.

Tenant isolation remains intact.

BYOK behavior remains correct.

Secrets remain protected.

==================================================
G. CI
==================================================

Required CI checks for the branch pass.

No failure is hidden with:
- continue-on-error
- skipped assertions
- disabled gates
- weakened thresholds
- deleted tests

==================================================
H. AI QUALITY
==================================================

For AI-related tasks, verify applicable:

- correctness
- context fidelity
- grounding
- tool correctness
- token usage
- cost
- latency
- regression behavior

==================================================
I. RESULT
==================================================

The task file must contain:

- status
- root cause
- changes
- files modified
- tests added/changed
- tests executed
- actual results
- acceptance criteria status
- remaining issues
- risks
- next task

==================================================
J. COMPLETION STATUS
==================================================

Allowed final states:

COMPLETED
COMPLETED WITH DOCUMENTED RISK
BLOCKED
INCOMPLETE

Never mark COMPLETED without evidence.