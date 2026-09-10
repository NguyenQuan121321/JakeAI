# W-COST-05 — Intelligent Model Routing

## OBJECTIVE

Implement deterministic, capability-aware model selection.

## IMPORTANT

Do not route based only on model price.

The router must consider:

1. required capability;
2. quality requirement;
3. context requirements;
4. tool support;
5. reasoning requirement;
6. latency target;
7. estimated cost;
8. provider availability;
9. user/tenant policy.

## ROUTING FLOW

request
→ classify workload
→ determine hard requirements
→ filter incompatible models
→ score compatible models
→ select best model
→ construct RoutingDecision

## HARD FILTER

Reject candidate when:

- required context exceeds model limit;
- required tool capability unavailable;
- required modality unavailable;
- provider unavailable;
- policy forbids provider/model.

## SOFT SCORE

For remaining candidates calculate:

score =
quality_weight * quality_score
+
capability_weight * capability_score
+
latency_weight * latency_score
-
cost_weight * normalized_cost

All weights must be configuration, not hidden constants.

## COST SAFETY

Never choose an inferior model solely because it is cheaper when task quality requirements forbid it.

## LOCAL MODEL

A self-hosted/local model is eligible only when:

- capabilities satisfy task;
- quality threshold is met;
- model is available;
- latency/resource budget is acceptable.

## FALLBACK

Primary candidate
→ fallback candidates ordered by compatibility score.

Do not loop back to the same failed model.

## OUTPUT

RoutingDecision must contain:

- selected_provider;
- selected_model;
- fallback_chain;
- reason;
- estimated_cost;
- capability match;
- policy decision.

## TESTS

- simple task;
- reasoning task;
- tool task;
- long-context task;
- local model;
- provider outage;
- cost conflict;
- unavailable model;
- deterministic repeat.

## ACCEPTANCE

For the same inputs and same runtime configuration, routing is deterministic and capability-safe.