# W-COST-02 — Prompt Compression

## OBJECTIVE

Reduce prompt tokens while preserving information required for task correctness.

## REQUIRED STRATEGY

Compress only content classified as redundant/non-essential.

Never remove:

- explicit user constraints;
- system safety instructions;
- required tool schemas;
- required structured output rules;
- unique evidence;
- facts needed to answer the request.

## COMPRESSION ORDER

1. remove exact duplicate content;
2. remove redundant historical turns;
3. compress repetitive prose;
4. reduce verbose tool output;
5. preserve high-value evidence;
6. stop when target budget is reached.

## QUALITY GUARD

Compression must produce:

before context
→ compressed context

and both must be available for evaluation.

## FALLBACK

If compression changes meaning or causes quality regression:
use original context.

## TESTS

- repetitive history;
- long tool output;
- RAG context;
- important constraint;
- structured JSON instruction;
- compression failure.

## ACCEPTANCE

Compression reduces token count without removing task-critical information.