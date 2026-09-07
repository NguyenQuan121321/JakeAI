# JakeAI — Static Code Analysis: RAG Efficiency & Evidence Optimization Audit

**Audit Date:** September 2026  
**Status:** Audit Completed  
**Domain:** RAG Ingestion, Chunking, Hybrid Retrieval, Reranking, Context Selection, and Citation Mechanics  

---

## 1. Architectural Baseline

The JakeAI RAG subsystem implements a 10-step enterprise retrieval and synthesis pipeline (`backend/app/rag/pipeline.py`):
1. Document Ingestion & normalization (`ingestion.py`)
2. Sliding-window chunking (`models.py`)
3. Metadata extraction & tenant tagging
4. Dual Indexing (Dense Qdrant + Sparse BM25)
5. Candidate Retrieval (`retriever.py`)
6. Hybrid Reciprocal Rank Fusion (RRF)
7. Cross-Encoder / Relative score reranking (`reranker.py`)
8. Evidence-preserving context selection (`context_selector.py`)
9. Inline footnote citation mapping (`citations.py`)
10. Grounded answer generation (`generate_grounded_answer`)

The context selector enforces an evidence-aware packing heuristic:
- Adaptive score thresholding (`min_relative_score = 0.30`)
- Redundancy pruning via containment ratio (`redundancy_threshold = 0.65`)
- Protected entity preservation (numerical figures, currencies, dates, quarterly tags)
- Strict multi-tenant candidate isolation

---

## 2. RAG Pipeline Findings

### Finding RAG-01: Cryptographic Pseudo-Hash Used as Dense Vector Embedding
- **Severity:** `HIGH`
- **Confidence:** `HIGH`
- **File / Symbol / Location:** `backend/app/rag/vector_store.py` (Lines 12–28)
- **Current Behavior:**  
  ```python
  def _generate_dense_embedding(text: str, dim: int = 64) -> list[float]:
      vec: list[float] = []
      for i in range(dim):
          seed = f"{text}_{i}".encode()
          h = hashlib.sha256(seed).digest()
          val = struct.unpack("f", h[:4])[0]
          ...
          vec.append(val)
      norm = math.sqrt(sum(v * v for v in vec)) or 1e-6
      return [round(v / norm, 6) for v in vec]
  ```
- **Problem:**  
  The dense vector store generates embeddings using `hashlib.sha256` seeded by text and dimension index!
  - SHA-256 is an avalanche-sensitive cryptographic hash: flipping even a single bit in the input text flips roughly 50% of the output bits.
  - Two sentences with identical semantic meaning (e.g. `"Revenue increased by 15%"` vs `"Sales grew by 15%"`) produce completely orthogonal vectors ($cos(\theta) \approx 0.0$).
  - Dense retrieval in Qdrant is functionally executing random partition matching rather than genuine semantic retrieval!
- **Evidence:**  
  Direct inspection of `_generate_dense_embedding` in `vector_store.py`. While this synthetic function enabled offline tests to pass without external embedding API keys, it breaks semantic search capability in production.
- **Impact:**  
  Dense retrieval fails to discover semantically relevant passages that don't share exact keyword overlap. The system is almost entirely reliant on BM25 sparse search for candidate retrieval.
- **Recommended Solution:**  
  Introduce an `EmbeddingProvider` abstraction:
  - Production mode: Connect to OpenAI `text-embedding-3-small` (1536-dim) or Gemini `text-embedding-004` (768-dim) via tenant BYOK or platform keys.
  - Offline/Test mode: Use a local deterministic embedding (e.g. `fastembed` or SentenceTransformers) or a vocabulary-based projection rather than SHA-256.
- **Complexity:** Medium.
- **Risk:** Medium (requires re-indexing existing Qdrant collections with updated vector dimensions).
- **Expected Benefit:** High increase in retrieval recall on complex semantic queries.

---

### Finding RAG-02: Score Injection & Volatility in LLM Context
- **Severity:** `MEDIUM`
- **Confidence:** `HIGH`
- **File / Symbol / Location:** `backend/app/rag/context_selector.py` (Lines 288–291)
- **Current Behavior:**  
  ```python
  formatted_parts.append(
      f"[{idx}] Source: {source_label} (Score: {chunk.score:.2f})\n"
      f'"{chunk.content.strip()}"'
  )
  ```
- **Problem:**  
  The context selector injects internal floating-point retrieval scores (e.g. `(Score: 0.87)`, `(Score: 0.93)`) into the context block sent to the LLM.
  1. Token waste: Repeating `(Score: X.XX)` across 5–10 chunks consumes unnecessary input tokens.
  2. Cache invalidation: Small changes in reranking scores alter the exact byte sequence of the context, invalidating prompt prefix caching.
  3. Model confusion: Downstream LLMs have been observed to cite or discuss the internal retrieval score rather than focusing purely on document facts.
- **Impact:** Context token waste and prompt cache misses.
- **Recommended Solution:**  
  Omit internal retrieval scores from model-visible context:
  ```python
  formatted_parts.append(f"[{idx}] Source: {source_label}\n{chunk.content.strip()}")
  ```
  Retain chunk scores in metadata and API response telemetry rather than prompt text.
- **Complexity:** Low.
- **Risk:** Low.
- **Expected Benefit:** 15–30 tokens saved per request; improved prompt prefix stability for caching.

---

### Finding RAG-03: Full Sort on Candidate Ranking Pool
- **Severity:** `LOW`
- **Confidence:** `HIGH`
- **File / Symbol / Location:** `backend/app/rag/context_selector.py` (Line 216)
- **Current Behavior:**  
  `relevant_candidates.sort(key=lambda x: x.score, reverse=True)`
- **Problem:**  
  Performs full $O(N \log N)$ sort on candidate pool. When `candidate_pool` is large (e.g., 50–100 items), only the top $K$ ($K \le 5$) are ever evaluated for packing.
- **Impact:** Minor CPU overhead on high-throughput retrieval.
- **Recommended Solution:**  
  Use `heapq.nlargest(top_k, relevant_candidates, key=lambda x: x.score)` to achieve $O(N \log K)$ selection complexity.
- **Complexity:** Low.
- **Risk:** Low.
- **Expected Benefit:** Microsecond latency reduction on candidate selection.

---

### Finding RAG-04: Inaccurate Selected Token Accounting in Context Selection
- **Severity:** `LOW`
- **Confidence:** `HIGH`
- **File / Symbol / Location:** `backend/app/rag/context_selector.py` (Lines 294–295)
- **Current Behavior:**  
  ```python
  selected_content_text = "\n\n".join(c.content for c in budget_chunks)
  selected_tokens = estimate_tokens(selected_content_text)
  ```
- **Problem:**  
  `selected_tokens` estimates ONLY raw chunk content, ignoring the formatted metadata headers:
  `f"[{idx}] Source: {source_label} (Score: {chunk.score:.2f})\n\"{chunk.content.strip()}\""`.
  The actual prompt sent to the LLM contains 15–25 additional tokens per chunk that are not accounted for in `selected_tokens` or `tokens_saved`.
- **Impact:** 5–10% undercounting of actual RAG context tokens.
- **Recommended Solution:**  
  Calculate `selected_tokens = estimate_tokens(formatted_context)`.
- **Complexity:** Low.
- **Risk:** Low.
- **Expected Benefit:** Exact context budget tracking.

---

## 3. Algorithm Comparison for RAG Subsystems

| Subsystem Component | Current Algorithm | Alternative Considered | Time Complexity | Space Complexity | Accuracy | Decision |
| :--- | :--- | :--- | :---: | :---: | :---: | :---: |
| **Dense Vector Embeddings** | SHA-256 Pseudo-Hash | FastEmbed / Provider API (`text-embedding-3-small`) | $O(N)$ | $O(D)$ | High vs None | **REPLACE** |
| **Sparse Retrieval** | In-memory BM25 | Qdrant Sparse Vectors (BM25 / SPLADE) | $O(N)$ | $O(V)$ | High | **IMPROVE** |
| **Redundancy Pruning** | Jaccard Containment Ratio | MinHash / LSH | $O(W_1 + W_2)$ | $O(W)$ | High | **KEEP** |
| **Candidate Ranking** | Python Timsort ($O(N \log N)$) | Min-Heap Top-K (`heapq.nlargest`) | $O(N \log K)$ | $O(K)$ | Exact | **IMPROVE** |
| **Citation Extraction** | Regex Pattern Anchoring | AST / Span Annotation | $O(L)$ | $O(C)$ | High | **KEEP** |
