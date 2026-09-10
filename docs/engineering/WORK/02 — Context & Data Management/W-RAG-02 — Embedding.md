# W-RAG-02 — Embedding

## OBJECTIVE

Replace the current deterministic hash-derived vector implementation with a real semantic embedding architecture.

## CURRENT PROBLEM

Do not use:
SHA-256-derived pseudo vectors
as semantic embeddings.

A cryptographic hash is not a semantic embedding model.

## REQUIRED ARCHITECTURE

Create an embedding provider abstraction:

EmbeddingProvider
    ↓
Concrete embedding implementation
    ↓
real embedding model/API
    ↓
vector

## REQUIRED INTERFACE

embed_text(text) -> vector
embed_batch(texts) -> vectors

The batch method must preserve input order.

## MODEL

Use one explicitly configured embedding model.

The model name, vector dimension and version must be part of configuration/metadata.

Do not silently change models.

## DIMENSION

The configured vector dimension MUST equal the vector-store collection dimension.

Mismatch:
→ fail clearly.

Do not truncate or pad vectors to hide dimension mismatch.

## NORMALIZATION

Use the embedding model's documented similarity behavior.

If cosine similarity is used:
normalize vectors consistently at ingestion and query time.

Use the same embedding implementation for:

document ingestion
and
query embedding.

## BATCHING

Implement bounded batch embedding to reduce network overhead.

Batch size must be configurable.

## RETRY

Retry only transient embedding-provider failures.

Use bounded exponential backoff.

Do not retry malformed input indefinitely.

## VERSIONING

Store:

embedding_model
embedding_dimension
embedding_version

with collection/index metadata.

When model changes incompatibly:
create/rebuild a compatible vector collection instead of mixing vector spaces.

## FALLBACK

A development-only fallback may exist only if explicitly configured.

It must NOT silently masquerade as production semantic embedding.

Production configuration must fail closed when the required embedding provider is unavailable.

## TESTS

- semantic model returns expected dimension;
- batch preserves order;
- ingestion/query use same model;
- dimension mismatch fails;
- transient retry;
- permanent failure;
- model version mismatch;
- production mode rejects fake embedding fallback.

## FORBIDDEN

- SHA-256 pseudo embeddings;
- random vectors;
- zero vectors;
- hash-based semantic similarity;
- mixing different embedding spaces.

## ACCEPTANCE

JakeAI uses a real semantic embedding implementation end-to-end for the production RAG path.