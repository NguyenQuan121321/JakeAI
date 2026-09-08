# JAKEAI REPAIR — INFRASTRUCTURE WORKER

You are repairing infrastructure correctness in JakeAI.

Target tasks may include:

- PROV-01
- DUP-01
- PERF-01

Primary concerns:

- HTTP connection lifecycle
- Redis connection lifecycle
- connection pooling
- shutdown
- concurrency
- atomicity
- resource ownership
- observability

## Required Principles

1. Resource ownership must be explicit.
2. Application-scoped resources must not be recreated per request.
3. Shared resources must have one lifecycle owner.
4. Shutdown must close resources deterministically.
5. Quota enforcement must be atomic where strict limits are required.
6. Operational failures must be distinguishable from programming errors.

## HTTP

If fixing HTTP client lifecycle:

- use application-scoped pooling
- configure explicit limits
- preserve timeout behavior
- preserve provider-specific transport requirements
- verify shutdown

Do not claim latency improvements without benchmarks.

## Redis

If consolidating Redis:

- identify all current clients
- identify all lifecycle owners
- define one canonical ownership model
- migrate callers incrementally
- preserve fallback behavior where intentionally supported
- preserve tenant isolation

## Quota

If fixing quota concurrency:

- define reservation semantics
- make reservation atomic
- settle against actual usage
- handle cancellation/failure
- release unused reservation

Test concurrent requests.

## Verification

Required where applicable:

- concurrent test
- shutdown test
- resource ownership test
- Redis failure test
- timeout test
- quota race test
- integration test

Do not proceed to unrelated application refactoring.

Finish with the standard Repair handoff.