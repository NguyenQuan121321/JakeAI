# W-OPS-05 — Leakage Detection

## OBJECTIVE

Detect cross-tenant, credential and sensitive-data leakage.

## REQUIRED TEST CATEGORIES

1. Cross-tenant RAG retrieval.
2. Cross-tenant cache hit.
3. Cross-tenant memory.
4. Tool authorization leakage.
5. Provider credential leakage.
6. Prompt-to-output secret leakage.
7. Logs/traces containing secrets.

## TEST METHOD

Create synthetic tenant-specific canary values.

Example:

TENANT_A_SECRET = unique marker A
TENANT_B_SECRET = unique marker B

Attempt every relevant data path.

Assert:

Tenant A cannot retrieve B marker.
Tenant B cannot retrieve A marker.

## SECRET TEST

Insert synthetic secret marker into controlled test input.

Verify it never appears in:

- logs;
- telemetry;
- cache key;
- RAG metadata;
- agent memory;
- error output.

## ACCEPTANCE

Unauthorized data cannot cross tenant/security boundaries and secrets do not appear in protected observability surfaces.