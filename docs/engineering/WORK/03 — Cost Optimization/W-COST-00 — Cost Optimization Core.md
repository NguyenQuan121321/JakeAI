# W-COST-00 — Cost Optimization Core

## OBJECTIVE

Create one coherent optimization pipeline.

## REQUIRED FLOW

Request
→ capability analysis
→ cache lookup
→ context optimization
→ model routing
→ execution
→ token/cost accounting
→ telemetry

## RULE

Optimization decisions must not reduce quality below the defined quality contract.

## CANONICAL AUTHORITIES

One authority for:

- cache identity;
- token accounting;
- pricing;
- provider resolution;
- model routing.

Do not create parallel implementations.

## ACCEPTANCE

All cost-related optimizations use canonical shared contracts.