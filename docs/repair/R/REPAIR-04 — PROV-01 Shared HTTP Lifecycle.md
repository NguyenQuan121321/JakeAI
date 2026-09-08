# REPAIR-04 — PROV-01 SHARED HTTP LIFECYCLE

Finding:
PROV-01

Objective:
Stop creating a new httpx.AsyncClient for every upstream inference.

Required invariant:

Application-scoped HTTP connections are reused safely across inference requests.

Required work:

- define resource ownership;
- create shared pooled client;
- configure timeouts and connection limits;
- integrate lifecycle startup/shutdown;
- migrate upstream calls;
- test concurrent requests;
- test shutdown.

Do not claim latency improvement without benchmark evidence.

Required tests:
- client reuse
- timeout behavior
- shutdown
- concurrent requests

Forbidden:
Do not redesign provider routing.

Definition of done:
Upstream inference no longer creates a fresh AsyncClient per request.