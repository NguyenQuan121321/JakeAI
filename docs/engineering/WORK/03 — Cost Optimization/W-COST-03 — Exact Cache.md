# W-COST-03 — Exact Cache

## OBJECTIVE

Provide deterministic exact response caching.

## IDENTITY ALGORITHM

Use:

SHA-256(
UTF-8(
version
+ separator
+ tenant_id
+ separator
+ provider
+ separator
+ model
+ separator
+ canonical_system_instructions
+ separator
+ canonical_messages
+ separator
+ canonical_tools
+ separator
+ canonical_response_format
+ separator
+ canonical_generation_parameters
))

## CANONICALIZATION

Use deterministic JSON for structured values:

- UTF-8;
- sorted object keys;
- compact separators;
- preserve list order;
- preserve semantic message order;
- normalize Unicode consistently;
- do not lowercase arbitrary user content;
- do not collapse semantically meaningful whitespace.

## MESSAGE FIELDS

Include all generation-relevant message fields:

- role;
- content;
- name;
- tool_call_id;
- tool_calls.

## GET/SET

GET and SET MUST use the exact same identity function.

Do not create separate key builders.

## TENANT

tenant_id is mandatory.

## TESTS

Different:
- tenant;
- provider;
- model;
- system prompt;
- message;
- tool;
- tool_call_id;
- response format;
- generation parameter

must produce different identities.

Identical requests must produce identical identity.

## ACCEPTANCE

No generation-relevant request dimensions collide.