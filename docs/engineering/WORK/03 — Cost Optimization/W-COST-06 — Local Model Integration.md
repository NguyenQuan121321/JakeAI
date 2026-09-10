# W-COST-06 — Local Model Integration

## OBJECTIVE

Add self-hosted/local inference as a first-class provider path without coupling the rest of JakeAI to one local runtime.

## REQUIRED ARCHITECTURE

Provider interface
→ LocalProviderAdapter
→ configurable local inference endpoint/runtime.

The provider layer must not assume Ollama, vLLM, LM Studio or another runtime directly unless configured.

## REQUIRED CONFIGURATION

- endpoint;
- model name;
- context limit;
- capabilities;
- timeout;
- concurrency limit;
- health status.

## HEALTH

Before routing:
verify provider capability/health.

Do not repeatedly route traffic to an unavailable local model.

## COST

Local inference cost must be represented as configured operational cost:

compute_cost
+
energy/infra estimate if available.

Do not claim zero cost merely because no API bill exists.

## TESTS

- local model reachable;
- unreachable;
- timeout;
- capability mismatch;
- context overflow;
- routing selection;
- fallback to external provider.

## ACCEPTANCE

Local inference can be selected by the canonical router using the same provider contract as external models.