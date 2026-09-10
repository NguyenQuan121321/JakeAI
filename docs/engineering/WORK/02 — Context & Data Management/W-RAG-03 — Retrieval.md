# W-RAG-03 — Retrieval

## OBJECTIVE

Implement reliable tenant-scoped hybrid retrieval.

## REQUIRED FLOW

query
→ query embedding
→ dense retrieval
+
BM25 sparse retrieval
→ candidate union
→ tenant validation
→ reranking

## PARALLELISM

Dense and sparse retrieval are independent I/O/computation paths.

Run them concurrently using asyncio concurrency.

Use:

asyncio.gather(
    dense_search(),
    sparse_search()
)

Do not claim parallel retrieval while executing them sequentially.

## TENANT FILTER

Apply tenant_id at vector-store retrieval.

Apply tenant_id validation again after retrieval as a defense-in-depth guard.

## CANDIDATE POOL

Use candidate_pool > final top_k.

Default:
candidate_pool = 3 × top_k
unless benchmark evidence dictates another value.

## DEDUPLICATION

Deduplicate by stable chunk_id.

Preserve strongest retrieval evidence.

## TESTS

- semantic match;
- keyword match;
- hybrid match;
- no match;
- wrong tenant;
- duplicate chunk;
- dense failure;
- sparse failure;
- concurrent execution.

## FAILURE

If one retrieval path fails:

Do not silently fabricate results.

Use explicit degraded mode only if configured.

Record degraded retrieval telemetry.

## ACCEPTANCE

Retrieval returns correct tenant-scoped candidates with dense+sparse hybrid behavior and actual concurrent execution.