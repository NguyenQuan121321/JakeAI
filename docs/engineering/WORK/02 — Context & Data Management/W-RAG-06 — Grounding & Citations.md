# W-RAG-06 — Grounding & Citations

## OBJECTIVE

Prevent unsupported claims from being presented as verified facts.

## REQUIRED FLOW

selected evidence
→ grounded prompt
→ LLM answer
→ claim extraction/verification
→ citation mapping
→ grounded answer

## PROMPT CONTRACT

System instruction must explicitly require:

- use only supplied evidence;
- do not invent unsupported facts;
- distinguish evidence from inference;
- abstain when evidence is insufficient;
- attach citation references to supported claims.

## CITATION

Every factual claim that requires external evidence must map to one or more retrieved passages.

Citation must point to actual source metadata.

Never fabricate citation IDs.

## VERIFICATION

For each answer claim:

SUPPORTED
→ retain.

UNSUPPORTED
→ remove/revise/abstain.

UNCERTAIN
→ explicitly qualify or abstain.

## IMPORTANT

Do not consider “the LLM said it was grounded” as proof of grounding.

Verification must compare answer claims against retrieved evidence.

## TESTS

- fully supported answer;
- partially supported answer;
- unsupported claim;
- conflicting sources;
- missing evidence;
- citation mismatch;
- hallucinated citation.

## ACCEPTANCE

An unsupported claim cannot silently pass as a verified RAG fact.