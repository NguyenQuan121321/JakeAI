# JAKEAI REPAIR — BASELINE & AUDIT VERIFICATION

Objective:

Verify the audit findings against the actual repository before any production repair.

Read:
- repair state
- audit findings
- affected source files
- relevant tests
- relevant CI configuration

For each finding:

1. Locate the claimed implementation.
2. Inspect the actual code path.
3. Determine whether the reported behavior is reproducible or provable.
4. Identify callers and downstream effects.
5. Identify existing tests that already cover the behavior.
6. Identify whether the finding conflicts with another subsystem.

For every finding produce:

FINDING ID:
SEVERITY:
AUDIT CLAIM:
ACTUAL IMPLEMENTATION:
STATUS:
- VERIFIED
- PARTIALLY VERIFIED
- OUTDATED
- NOT VERIFIED
- FALSE POSITIVE

ROOT CAUSE:

AFFECTED COMPONENTS:

SECURITY IMPACT:

DATA / ACCOUNTING IMPACT:

REGRESSION RISK:

RECOMMENDED REPAIR:

DEPENDENCIES:

REQUIRED TEST:

Do not change source code.

Do not "fix" findings during this task.

At the end create or update:

docs/ai-engineering/state/repair-findings.md

with the verified classification.

Then identify the highest-value repair that is unblocked.

Return exactly one recommended next task.