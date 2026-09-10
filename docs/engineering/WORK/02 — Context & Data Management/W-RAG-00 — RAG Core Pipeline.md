# W-RAG-00 — RAG Core Pipeline

## OBJECTIVE

Make the complete RAG pipeline function end-to-end using real retrieval and verified evidence.

## REQUIRED PIPELINE

Document
→ ingestion
→ normalization
→ chunking
→ metadata
→ embedding
→ indexing
→ retrieval
→ reranking
→ context selection
→ grounded generation
→ citation mapping
→ verification

## RULE

Every stage must pass structured data to the next stage.

Do not rebuild context from unrelated global state.

## REQUIRED RESULT

The pipeline must return:

- answer;
- citations;
- retrieved chunks;
- selected context;
- retrieval metadata;
- tenant_id;
- confidence/evidence metadata.

## NO EMPTY-CONTEXT HALLUCINATION

If sufficient evidence is unavailable:
→ return abstention/insufficient-evidence result.

Do not invent an answer.

## ACCEPTANCE

A document can be ingested and later retrieved to produce a grounded cited answer.