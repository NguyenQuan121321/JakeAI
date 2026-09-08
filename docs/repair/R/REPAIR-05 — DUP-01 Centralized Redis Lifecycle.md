# REPAIR-05 — DUP-01 CENTRALIZED REDIS LIFECYCLE

Finding:
DUP-01

Objective:
Establish one authoritative Redis connection lifecycle.

Required invariant:

Shared Redis infrastructure has one lifecycle owner and does not leak connections.

Required work:

1. Locate every Redis client construction.
2. Map all lifecycle ownership.
3. Create/reuse one canonical Redis manager.
4. Migrate callers incrementally.
5. Preserve fail-open/fallback semantics where intentionally required.
6. Ensure shutdown closes the owned resource.
7. Add Redis failure and lifecycle tests.

Forbidden:
Do not alter Redis data semantics unnecessarily.
Do not remove fallback behavior without evidence.

Definition of done:
No active duplicate Redis client ownership remains.