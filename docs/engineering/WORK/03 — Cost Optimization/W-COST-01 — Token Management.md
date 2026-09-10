# W-COST-01 — Token Management

## OBJECTIVE

Make token accounting reflect the complete model-visible request.

## REQUIRED INPUT

Count:

- system instructions;
- developer messages;
- all conversation messages;
- tool definitions;
- tool calls;
- tool results;
- RAG context;
- current user query;
- required protocol framing.

## REQUIRED ACCOUNTING

raw_input_tokens
optimized_input_tokens
physical_tokens_pruned
provider_cached_input_tokens
response_cache_avoided_tokens
effective_billed_tokens

## RULE

Do not derive total input from only the latest user message.

## CONSERVATION

When context compression occurs:

raw_input_tokens
=
optimized_input_tokens
+
physical_tokens_pruned

unless provider-specific accounting semantics explicitly require another representation.

## PROVIDER TELEMETRY

Provider-reported usage takes precedence for actual billed usage.

Local estimation is an estimate, not ground truth.

## TESTS

- multi-turn;
- tools;
- tool outputs;
- RAG;
- compression;
- cache hit;
- provider telemetry;
- missing provider telemetry.

## ACCEPTANCE

Token accounting reflects the complete model-visible envelope and distinguishes estimated from billed usage.