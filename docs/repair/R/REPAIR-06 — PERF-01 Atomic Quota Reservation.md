# REPAIR-06 — PERF-01 ATOMIC QUOTA RESERVATION

Finding:
PERF-01

Objective:
Prevent concurrent requests from bypassing tenant token quotas.

Required invariant:

Quota admission must be atomic.

Preferred lifecycle:

reserve estimated usage
→ execute inference
→ settle actual usage
→ release unused reservation

Required work:

- define reservation semantics;
- implement atomic Redis reservation;
- handle rejection;
- handle inference failure;
- handle cancellation;
- settle actual usage;
- release unused reservation.

Required concurrency test:

Configure a tenant with a small remaining quota.

Launch many concurrent requests.

Verify that requests cannot all pass the same remaining quota window.

Forbidden:
Do not simply increase quota.
Do not remove quota enforcement.

Definition of done:
Concurrent quota race regression test passes.