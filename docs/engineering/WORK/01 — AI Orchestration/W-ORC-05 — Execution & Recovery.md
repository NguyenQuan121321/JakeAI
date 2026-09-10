# W-ORC-05 — Execution & Recovery

## OBJECTIVE

Complete bounded, cancellable and recoverable agent execution.

## REQUIRED STATE MACHINE

CREATED
→ RUNNING
→ PAUSED_APPROVAL
→ RUNNING
→ COMPLETED

Failure:
RUNNING
→ FAILED

Cancellation:
RUNNING
→ CANCELLED

## REQUIRED CONTROLS

- maximum iterations;
- timeout;
- cancellation;
- checkpoint;
- bounded retry;
- terminal failure.

## RETRY

Retry only transient failures.

Do not retry:

- authorization failure;
- invalid arguments;
- permanent provider rejection;
- policy denial.

Use exponential backoff for transient retry.

Do not use unbounded retry.

## RECOVERY

After restart:

checkpoint
→ validate checkpoint
→ restore run state
→ resume from last safe state

Never replay a dangerous side-effect automatically unless idempotency has been established.

## TESTS

- timeout;
- cancel;
- transient failure;
- permanent failure;
- checkpoint recovery;
- duplicate retry;
- approval pause/resume;
- maximum iteration.

## ACCEPTANCE

A run cannot execute indefinitely and can safely stop, resume or terminate.