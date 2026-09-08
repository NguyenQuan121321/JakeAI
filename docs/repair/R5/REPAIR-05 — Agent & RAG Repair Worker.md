# JAKEAI REPAIR — AGENT / RAG WORKER

You are repairing JakeAI Agent and RAG correctness.

Possible targets:

Agent:
- PROV-04
- CACHE-03
- AGT-01
- AGT-03

RAG:
- RAG-01
- RAG-02
- RAG-04

## Agent Rules

Preserve:

- permissions
- tool authorization
- approval gates
- cancellation
- timeouts
- iteration limits
- tenant isolation

Do not increase autonomy as part of repair.

### Tool Outputs

All tool output must pass through controlled ingestion.

The model-visible representation must have an intentional budget.

Preserve access to full output through:
- continuation
- artifact
- pagination
when required.

### Agent Memory

Memory must be evaluated by:
- token footprint
- information retention
- goal retention
- constraint retention
- stale observation removal

Do not replace FIFO with an arbitrary summary mechanism without testing information retention.

### Prompt Cache

Static instructions must remain stable.

Dynamic execution state belongs in dynamic context.

Verify static prefix stability with deterministic tests.

## RAG Rules

Dense retrieval must represent semantic similarity.

Do not replace pseudo-embeddings with a provider-specific implementation directly inside VectorStore.

Use an embedding abstraction.

Preserve:
- tenant filtering
- metadata
- citation
- BM25 fallback where intended

Any embedding dimension change requires explicit collection/version migration.

## RAG Verification

Measure where applicable:

- Recall@K
- MRR
- NDCG
- groundedness
- citation correctness
- token usage
- latency

Do not declare RAG fixed from unit tests alone.

Finish with standard Repair handoff.