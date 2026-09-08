# REPAIR-12 — RAG-01 REAL EMBEDDING ARCHITECTURE

Finding:
RAG-01

Objective:
Replace cryptographic pseudo-embeddings with a real semantic embedding architecture.

Current defect:
Dense vectors are derived from SHA-256 text hashes.

Required invariant:

Semantically similar inputs must have meaningful vector similarity.

Required architecture:

EmbeddingProvider abstraction
→ embedding implementation
→ versioned vector collection

Required work:

- define embedding provider contract;
- select production embedding implementation;
- define test/offline implementation;
- preserve tenant isolation;
- define vector dimension metadata;
- version collections;
- plan re-index/migration;
- preserve BM25 fallback if intended.

Required evaluation:

- semantic paraphrases
- multilingual queries where supported
- Recall@K
- MRR or equivalent
- grounding/citation regression

Forbidden:
Do not simply replace one hard-coded vendor call inside VectorStore.

Definition of done:
Real semantic retrieval is demonstrated by measured retrieval quality.