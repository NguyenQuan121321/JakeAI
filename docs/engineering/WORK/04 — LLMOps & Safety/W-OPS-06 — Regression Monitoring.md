# W-OPS-06 — Regression Monitoring

## OBJECTIVE

Detect AI and system quality regressions automatically.

## REQUIRED BASELINE

Store versioned baseline for:

- functional correctness;
- RAG metrics;
- latency;
- token usage;
- cost;
- safety results.

## CHANGE

Every relevant implementation change must produce a comparable result.

## REGRESSION RULES

Functional regression:
fail immediately.

Security regression:
fail immediately.

Cross-tenant leakage:
fail immediately.

Groundedness regression:
fail if threshold exceeded.

Quality regression:
fail if threshold exceeded.

Cost regression:
warn or fail according to configured budget.

## ACCEPTANCE

A change cannot silently degrade AI quality or safety while software tests remain green.