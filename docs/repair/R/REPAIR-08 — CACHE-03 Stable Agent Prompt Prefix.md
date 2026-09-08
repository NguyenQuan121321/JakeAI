# REPAIR-08 — CACHE-03 STABLE AGENT PROMPT PREFIX

Finding:
CACHE-03

Objective:
Prevent volatile execution state from mutating the static prompt prefix.

Required invariant:

The static prefix remains byte-stable across iterations of the same agent execution unless a meaningful static configuration changes.

Current volatile data to isolate:
- iteration counter
- other execution-state values if found

Required work:

- inspect planner prompt construction;
- classify static vs dynamic context;
- move volatile state to dynamic context;
- preserve agent semantics;
- test prefix stability.

Required tests:

static prefix iteration 1 == iteration 2 == iteration 3

Dynamic execution state may change without changing static prefix identity.

Forbidden:
Do not remove useful execution state.
Do not claim provider cache improvement without telemetry evidence.