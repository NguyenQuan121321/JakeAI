# W-OPS-03 — Observability

## OBJECTIVE

Make system behavior diagnosable without leaking sensitive information.

## REQUIRED SIGNALS

Logs
Metrics
Traces
AI evaluation results

## LOGGING

Use structured logging.

Every major event must include correlation identifiers.

Never log raw secrets.

## METRICS

At minimum:

- request count;
- error count;
- latency;
- TTFT;
- provider failures;
- cache hit rate;
- RAG retrieval latency;
- agent execution time;
- token usage;
- cost.

## TRACING

Propagate correlation ID through:

Gateway
→ Router
→ Cache
→ RAG
→ Agent
→ Tool
→ Provider.

## ACCEPTANCE

A failed request can be traced to the subsystem responsible without exposing sensitive data.