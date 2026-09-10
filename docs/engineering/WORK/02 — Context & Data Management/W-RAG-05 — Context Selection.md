# W-RAG-05 — Context Selection

## OBJECTIVE

Select the minimum sufficient evidence needed by the model.

## REQUIRED ALGORITHM

Input:
ranked candidates

1. remove candidates below relevance threshold;
2. remove semantic duplicates above redundancy threshold;
3. preserve highest-scoring evidence;
4. add candidates until token budget is reached;
5. never exceed max_context_tokens.

## PRIORITY

Higher relevance first.

When relevance is similar:
prefer:
- source diversity;
- coverage of distinct claims;
- shorter passages when equally relevant.

## TOKEN BUDGET

Estimate the actual serialized context tokens using the canonical tokenizer/estimator already approved by JakeAI.

Do not count only raw character length.

## EVIDENCE PRESERVATION

Never remove all evidence for a unique claim only because it is longer.

## EMPTY CONTEXT

Return explicit no-sufficient-evidence result.

## TESTS

- token limit;
- duplicate passages;
- low-score passages;
- unique evidence;
- exact budget boundary;
- empty results.

## ACCEPTANCE

Context stays within token budget while preserving the strongest non-redundant evidence.