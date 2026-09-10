# W-RAG-01 — Ingestion

## OBJECTIVE

Create reliable document ingestion with deterministic normalization, chunking and tenant metadata.

## REQUIRED FLOW

raw document
→ parse
→ normalize
→ chunk
→ attach metadata
→ assign stable chunk_id
→ embedding
→ index

## CHUNKING

Use structure-aware recursive chunking.

Priority:

1. document structure;
2. headings/paragraph boundaries;
3. sentence boundaries;
4. token limit.

Do not cut arbitrarily in the middle of a sentence unless required by a hard size limit.

Use configured chunk size and overlap.

## METADATA

Every chunk must retain:

- tenant_id;
- document_id;
- chunk_id;
- source;
- page/section when available;
- document version;
- ingestion timestamp;
- embedding model/version.

## IDENTITY

chunk_id must be deterministic for the same document version and chunk position.

## TESTS

- plain text;
- repeated ingestion;
- same document version;
- new document version;
- empty document;
- malformed document;
- cross-tenant document.

## FORBIDDEN

- dropping tenant_id;
- random chunk identity;
- silent duplicate ingestion;
- storing provider secrets in metadata.

## ACCEPTANCE

The same document version produces deterministic, tenant-scoped chunks with complete metadata.