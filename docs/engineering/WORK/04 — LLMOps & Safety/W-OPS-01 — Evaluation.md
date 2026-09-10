# W-OPS-01 — Evaluation

## OBJECTIVE

Create repeatable evaluation of AI correctness.

## REQUIRED EVALUATION TYPES

1. deterministic software tests;
2. retrieval evaluation;
3. groundedness evaluation;
4. answer quality evaluation;
5. safety evaluation.

## RAG METRICS

At minimum support:

- Recall@K;
- Precision@K;
- MRR or NDCG;
- citation correctness;
- groundedness;
- unsupported claim rate.

## AGENT METRICS

Track:

- task success;
- tool success;
- revision count;
- termination reason;
- execution latency.

## COST METRICS

Track:

- input tokens;
- output tokens;
- effective billed tokens;
- cost;
- cache savings.

## RULE

Evaluation datasets must be versioned.

Do not change expected answers simply to make a new implementation pass.

## ACCEPTANCE

JakeAI can compare one implementation against another using repeatable datasets and metrics.