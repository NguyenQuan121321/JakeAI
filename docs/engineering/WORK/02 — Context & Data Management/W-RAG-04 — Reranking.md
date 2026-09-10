# W-RAG-04 — Reranking

## OBJECTIVE

Make candidate ranking semantically accurate and deterministic.

## REQUIRED PRIORITY

Primary:
real cross-encoder/reranker model.

Secondary:
RRF fusion only when model-based reranking is unavailable and degraded mode is explicitly allowed.

## RRF FORMULA

For rank r:

score = 1 / (k + r)

Use one configured RRF k value.

Do not arbitrarily multiply ranks until a benchmark proves the calibration.

## CROSS-ENCODER

Input:

query
+
candidate passage

Return one relevance score per candidate.

Preserve candidate-to-score alignment.

## SORTING

Sort descending by final relevance score.

Use deterministic tie-breaking by chunk_id.

## FALLBACK

Fallback must be explicit and observable.

Do not describe heuristic overlap as semantic model scoring.

## TESTS

- correct relevant passage;
- irrelevant passage;
- ordering;
- tie-breaking;
- duplicate candidate;
- cross-encoder failure;
- fallback mode;
- score alignment.

## ACCEPTANCE

Ranking is deterministic and uses a real semantic reranker on the production path when configured.