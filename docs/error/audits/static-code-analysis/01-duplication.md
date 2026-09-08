# JakeAI — Static Code Analysis: Code Duplication & Internal Consistency Audit

**Audit Date:** September 2026  
**Status:** Audit Completed  
**Domain:** Code Duplication, Semantic Equivalence, and Canonicalization  

---

## 1. Executive Overview

An exhaustive scan across all 141 modules in `backend/app` reveals multiple instances where critical platform logic has been reimplemented independently across feature phases instead of reusing existing domain-owned components.

Duplication in JakeAI primarily falls into six high-risk operational categories:
1. **Connection Management (Redis Pools):** 9 separate modules independently instantiate `redis.asyncio` clients with disparate timeout and cooldown policies.
2. **Provider & Model Resolution:** Substring matching on model names is implemented with differing coverage across three independent files.
3. **Cost Calculation & Pricing Catalog:** FinOps pricing calculations and model pricing catalogs exist redundantly in both `app/finops` and `app/optimizer`.
4. **Token Estimation:** The original regex-based token estimator remains active across core paths despite the implementation of `BPETokenizer`.
5. **Synthetic Embeddings:** Vector store and semantic cache use incompatible synthetic pseudo-embeddings with different dimensionalities and algorithms.
6. **Quota & Budget Accounting:** `ai_gateway.py` maintains an in-memory `QuotaManager` that runs in parallel with `app/finops/budget.py`'s `BudgetManager`.

---

## 2. Comprehensive Duplication Inventory

### Finding DUP-01: Proliferation of Redis Client Connections and Cooldown Logic
- **Severity:** `HIGH`
- **Confidence:** `HIGH`
- **Duplicated Locations:**
  - `backend/app/api/v1/endpoints/health.py` (Line 94)
  - `backend/app/core/security.py` (Line 132)
  - `backend/app/finops/budget.py` (Line 49)
  - `backend/app/services/resume_bridge.py` (Line 93)
  - `backend/app/core/byok.py` (Line 186)
  - `backend/app/core/rate_limiter.py` (Line 72)
  - `backend/app/services/ai_gateway.py` (Line 115)
  - `backend/app/rag/tasks.py` (Line 97)
  - `backend/app/optimizer/semantic_cache.py` (Line 168)
- **Current Behavior:**  
  Each of the 9 modules implements its own `_get_redis()` helper function. Each manages private attributes: `self.redis_client`, `self._redis_available`, and `self._redis_retry_after`.
- **Problem:**  
  1. Connection pool fragmentation: Each module allocates its own pool of Redis sockets, multiplying open connections by 9x under concurrent load.
  2. Inconsistent timeout configurations: Some use default socket timeouts, while others configure `REDIS_CONNECT_TIMEOUT_SECONDS`.
  3. Shutdown resource leaks: In `backend/app/main.py`'s `lifespan` handler (lines 45–55), only `get_quota_manager()`, `get_semantic_cache_manager()`, and `get_task_manager()` clients are closed. The other 6 Redis clients are never closed, causing socket warnings on container termination.
- **Canonical Implementation Candidate:**  
  A centralized singleton connection manager in `app/core/redis.py`:
  ```python
  class RedisConnectionManager:
      async def get_client(self) -> redis.Redis: ...
      async def close(self) -> None: ...
  ```
- **Migration Risk:** Low. All 9 callers already follow an async `await get_redis()` pattern.
- **Expected Benefit:** 70–80% reduction in idle Redis TCP connections; zero connection leak warnings during container shutdown.

---

### Finding DUP-02: Model-to-Provider Substring Resolution Heuristics
- **Severity:** `HIGH`
- **Confidence:** `HIGH`
- **Duplicated Locations:**
  - `backend/app/services/ai_gateway.py` (Lines 342–350):
    ```python
    provider = (
        "gemini" if "gemini" in request.model.lower()
        else ("openai" if "gpt" in request.model.lower()
        else ("anthropic" if "claude" in request.model.lower() else "openrouter"))
    )
    ```
  - `backend/app/core/llm_provider.py` (Lines 65–77):
    ```python
    model_lower = model.lower()
    is_anthropic = "claude" in model_lower or "anthropic" in model_lower
    is_openai = any(k in model_lower for k in ("gpt", "o1", "o3"))
    is_groq = "groq" in model_lower or "llama" in model_lower
    is_deepseek = "deepseek" in model_lower
    is_openrouter = "openrouter" in model_lower or "/" in model_lower
    is_gemini = "gemini" in model_lower or (...)
    ```
  - `backend/app/providers/registry.py` (Lines 39–53):
    ```python
    def resolve_provider_name_for_model(self, model: str) -> str: ...
    ```
- **Current Behavior:**  
  Three separate files implement divergent substring-matching heuristics to map model names to provider keys.
- **Problem:**  
  - Semantic Divergence & Bug: `ai_gateway.py` does not check for `deepseek` or `groq`. A request for `deepseek-chat` or `llama-3.3-70b-versatile` passing through `ai_gateway.py` resolves to `"openrouter"`, breaking BYOK key injection for direct DeepSeek and Groq keys.
  - `llm_provider.py` checks `o1` and `o3`, but `ai_gateway.py` only checks `gpt`.
  - Tight coupling: Adding a new model or provider requires editing multiple disjoint files.
- **Canonical Implementation Candidate:**  
  `app.providers.registry.ProviderRegistry.resolve_provider_name_for_model()` backed by `app.providers.base.ModelCapabilityCatalog`.
- **Migration Risk:** Low. `ai_gateway.py` and `llm_provider.py` should import `get_provider_registry()`.
- **Expected Benefit:** Single source of truth for model dispatch; fixes silent Groq and DeepSeek BYOK resolution errors in AI Gateway.

---

### Finding DUP-03: Duplicated Cost Calculation & Pricing Catalog
- **Severity:** `MEDIUM`
- **Confidence:** `HIGH`
- **Duplicated Locations:**
  - `backend/app/finops/pricing.py`:
    - `calculate_baseline_cost(model, raw_input, output)`
    - `calculate_billed_cost(model, uncached_input, cached_input, cache_write, output)`
    - `calculate_provider_cache_savings(model, cached_input, cache_write)`
  - `backend/app/optimizer/provider_pricing.py`:
    - `PRICING_CATALOG: dict[str, ModelPricing]`
    - `calculate_provider_costs(...)` returning `ProviderCostBreakdown`
    - `measure_cost(...)` returning `CostMeasurement`
- **Current Behavior:**  
  Both modules define cost equations and model pricing. `app/finops/pricing.py` imports `get_model_pricing` from `app.optimizer.provider_pricing`, but then implements its own formulas returning primitive `float` values, while `optimizer` returns Pydantic models with different field names.
- **Problem:**  
  1. Two parallel FinOps representations: `ProviderCostBreakdown` (optimizer) vs `IncurredCostRecord` (finops ledger) vs raw floats (finops pricing).
  2. Formula discrepancy: `finops/pricing.py` implements an Anthropic write surcharge calculation (`pricing.cache_write_per_million - pricing.input_per_million`), while `optimizer/provider_pricing.py` computes actual cost with direct `cache_write_tokens * pricing.cache_write_per_million`.
- **Canonical Implementation Candidate:**  
  Consolidate all pricing schemas, catalogs, and calculations into `app/finops/pricing.py` and `app/finops/models.py`. The `app/optimizer/provider_pricing.py` file should re-export from `finops` for backward compatibility.
- **Migration Risk:** Low.
- **Expected Benefit:** Cohesive financial reconciliation without rounding drift or equation mismatches.

---

### Finding DUP-04: Dual Token Counting Implementations
- **Severity:** `MEDIUM`
- **Confidence:** `HIGH`
- **Duplicated Locations:**
  - `backend/app/optimizer/token_pruner.py` (`estimate_tokens`, line 76):
    `tokens = re.findall(r"\w+|[^\w\s]|\n|[ ]{2,}", text)`
  - `backend/app/optimizer/bpe_tokenizer.py` (`BPETokenizer.count_tokens`, line 90):
    `len(self._tiktoken_encoding.encode(text, disallowed_special=()))`
- **Current Behavior:**  
  Phase 03 developed `BPETokenizer` using `tiktoken` (cl100k_base / o200k_base). However, almost all production call sites (`ai_gateway.py`, `chat.py`, `context_optimizer.py`, `rag/context_selector.py`, `code_context_compressor.py`) continue to import and call `estimate_tokens` from `token_pruner.py`.
- **Problem:**  
  1. The regex estimator undercounts Vietnamese, CJK, and non-ASCII text by 30–60%, and undercounts code tokens with punctuation/indentation.
  2. `BPETokenizer` was created but remains underutilized (59% test coverage), creating an architectural split where the codebase claims BPE support while executing regex splits on production paths.
- **Canonical Implementation Candidate:**  
  `app.optimizer.bpe_tokenizer.get_bpe_tokenizer().count_tokens(text, model=model)`.
- **Migration Risk:** Low to Medium. Need to verify that regex-calibrated tests do not fail on exact BPE counts.
- **Expected Benefit:** Accurate token estimation for quota governance and exact provider cost prediction.

---

### Finding DUP-05: Conflicting Synthetic Embedding Generators
- **Severity:** `MEDIUM`
- **Confidence:** `HIGH`
- **Duplicated Locations:**
  - `backend/app/optimizer/semantic_cache.py` (`_generate_synthetic_embedding`, line 85):
    128-dimensional bag-of-words vector hashed using `hashlib.md5`.
  - `backend/app/rag/vector_store.py` (`_generate_dense_embedding`, line 12):
    64-dimensional vector hashed using `hashlib.sha256(f"{text}_{i}".encode())`.
- **Current Behavior:**  
  Both modules need dense vectors to calculate cosine similarity. Each implements a synthetic embedding function with different dimensions (128 vs 64), different hash algorithms (MD5 vs SHA-256), and completely different mathematical properties.
- **Problem:**  
  - Neither is a true semantic embedding.
  - The SHA-256 seed approach in `vector_store.py` is avalanche-sensitive: changing 1 word makes the vector orthogonal (0 similarity), completely failing the premise of dense vector retrieval.
- **Canonical Implementation Candidate:**  
  A unified embedding provider interface in `app.core.embeddings` that defaults to a lightweight deterministic fast-embed or provider-backed embedding (`text-embedding-3-small` / `gemini-embedding`), with an in-memory fallback.
- **Migration Risk:** Medium. Affects vector database collection dimensions.
- **Expected Benefit:** Real semantic search in RAG and semantic cache; shared vector infrastructure.

---

### Finding DUP-06: Dual Quota Tracking Systems
- **Severity:** `MEDIUM`
- **Confidence:** `HIGH`
- **Duplicated Locations:**
  - `backend/app/services/ai_gateway.py` (`QuotaManager`, line 94)
  - `backend/app/finops/budget.py` (`BudgetManager`, line 38)
- **Current Behavior:**  
  `QuotaManager` in `ai_gateway.py` stores token usage at `gateway:usage:{tenant_id}:{period}` in Redis or memory. Simultaneously, `BudgetManager` in `finops/budget.py` stores token quotas at `finops:budget:{tenant}:{period}`. `ai_gateway.py` lines 156, 209, 217 make best-effort suppress calls to sync with `get_budget_manager()`.
- **Problem:**  
  - Double accounting: Two separate Redis keys track the same tenant token usage.
  - State drift: If `ai_gateway.py` fails to call `BudgetManager`, or if requests enter via direct endpoints, quota records diverge.
- **Canonical Implementation Candidate:**  
  Let `app.finops.budget.BudgetManager` be the single authority for token budgets and quotas. `QuotaManager` in `ai_gateway.py` should be a thin wrapper or deprecated.
- **Migration Risk:** Medium.
- **Expected Benefit:** Unified tenant usage tracking and single-source financial governance.

---

## 3. Algorithm Comparison for Duplication Remediation

| Domain | Current Algorithm / Implementation | Canonical Alternative | Time Complexity | Space Complexity | Maintainability | Recommendation |
| :--- | :--- | :--- | :---: | :---: | :---: | :---: |
| **Redis Clients** | 9 ad-hoc `_get_redis()` pools | Singleton `RedisConnectionManager` | $O(1)$ | $O(1)$ | High | **REPLACE** |
| **Model Resolution** | Substring checks across 3 files | Catalog-backed `ProviderRegistry` | $O(1)$ | $O(1)$ | High | **REPLACE** |
| **Token Estimation** | Regex `\w+\|[^\w\s]` | Tiered `BPETokenizer` (BPE + calibrated fallback) | $O(N)$ | $O(N)$ | High | **IMPROVE** |
| **Pricing Catalog** | Parallel dicts & functions | Single `app.finops.pricing` catalog | $O(1)$ | $O(1)$ | High | **REPLACE** |
| **Quota Checking** | Dual `QuotaManager` + `BudgetManager` | Unified `BudgetManager` | $O(1)$ | $O(1)$ | High | **REPLACE** |
