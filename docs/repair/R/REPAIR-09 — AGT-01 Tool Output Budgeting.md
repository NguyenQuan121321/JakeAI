# REPAIR-09 — AGT-01 TOOL OUTPUT BUDGETING

Finding:
AGT-01

Objective:
Prevent unbounded tool output from entering agent context.

Required invariant:

Every tool observation entering model-visible memory must pass through an explicit output budget/policy.

Required work:

- define default tool output token budget;
- normalize result;
- project important fields where applicable;
- truncate safely;
- preserve continuation/access to full result;
- support artifact/reference mode for large outputs;
- preserve error information.

Required tests:

- small result preserved
- large result bounded
- structured JSON projection
- continuation/reference
- error result

Forbidden:
Do not silently discard information required to complete the task.
Do not solve by arbitrary character truncation alone.

Definition of done:
A large tool response cannot exhaust the agent context budget.