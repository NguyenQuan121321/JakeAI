# W-OPS-02 — Benchmark

## OBJECTIVE

Create a reproducible benchmark for the four JakeAI capabilities.

## BENCHMARK AXES

ORCHESTRATION
- task success;
- execution time;
- tool success;
- recovery.

RAG
- Recall@K;
- MRR/NDCG;
- groundedness;
- citation accuracy;
- hallucination/unsupported-claim rate.

COST
- tokens;
- cost;
- cache hit rate;
- compression ratio;
- routing cost.

LLMOPS
- detection latency;
- regression detection;
- leakage detection;
- evaluation stability.

## BASELINE

Every optimization benchmark requires:

baseline
→ change
→ measurement
→ comparison.

## QUALITY GATE

Optimization is accepted only when:

cost decreases
AND
quality remains above defined threshold.

## ACCEPTANCE

Benchmarks produce machine-readable comparable results.