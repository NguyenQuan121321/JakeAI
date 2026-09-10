# W-OPS-00 — LLMOps Core

## OBJECTIVE

Create one observable lifecycle for every AI request.

## REQUIRED TELEMETRY

request_id
tenant_id
user_id where permitted
workflow/run_id
provider
model
latency
TTFT when streaming
input tokens
output tokens
cache result
RAG result
tool usage
routing decision
cost
quality/evaluation metadata

## PRIVACY

Never record:

- API keys;
- authorization secrets;
- raw credentials.

Sensitive prompts/responses must follow explicit retention/redaction policy.

## CORRELATION

All events for one request must share one correlation identifier.

## ACCEPTANCE

An AI request can be traced across routing, inference, cache, RAG, tools and final response without exposing secrets.