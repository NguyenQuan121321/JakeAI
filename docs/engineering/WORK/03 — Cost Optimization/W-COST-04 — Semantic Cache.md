# W-COST-04 — Semantic Cache

## OBJECTIVE

Implement semantic response reuse only when semantic equivalence is sufficiently strong and safe.

## IMPORTANT

Semantic cache MUST NOT replace exact cache.

Exact cache:
exact identity.

Semantic cache:
similarity-based candidate search + safety validation.

## REQUIRED FLOW

request
→ semantic embedding
→ candidate search
→ similarity threshold
→ generation-relevant compatibility check
→ candidate acceptance/rejection

## SAFETY

Never return semantic cache results across tenants.

Do not reuse responses when differences affect:

- tools;
- response schema;
- system instruction;
- provider/model constraints;
- authorization context;
- sensitive data scope.

## THRESHOLD

Use a configurable similarity threshold.

Do not hard-code a threshold without benchmark evidence.

Start conservatively.

False positive cache hits are worse than false negatives.

## TESTS

- near duplicate query;
- unrelated query;
- changed tool;
- changed response schema;
- different tenant;
- different model;
- stale entry;
- threshold boundary.

## ACCEPTANCE

Semantic reuse occurs only when compatibility and similarity requirements are satisfied.