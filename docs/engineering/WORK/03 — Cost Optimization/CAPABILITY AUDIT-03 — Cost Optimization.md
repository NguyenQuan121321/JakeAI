# CAPABILITY AUDIT-03 — Cost Optimization

**Auditor**: JakeAI Universal AI Engineering Worker  
**Audit Capability**: Cost Optimization (Capability 03)  
**Assigned Specifications**: `docs/engineering/WORK/03 — Cost Optimization/` (`W-COST-00` to `W-COST-06`)  
**Repository Working Baseline**: `E:\JakeAI`  
**Audit Date**: 2026-09-10  
**Audit Standard**: Exhaustive runtime trace, static analysis, import/caller resolution, mathematical verification, and test execution parity. Code modifications, bug repairs, refactoring, and optimizations are strictly forbidden.

---

# 1. Executive Summary

A comprehensive architectural, algorithmic, and runtime code audit of the **Cost Optimization** capability within JakeAI was conducted. The audit inspected all files, classes, models, algorithms, entry points, and test suites across `backend/app/optimizer/`, `backend/app/routing/`, `backend/app/finops/`, `backend/app/providers/`, `backend/app/services/` (`ai_gateway.py`, `billing.py`), `backend/app/core/` (`llm_provider.py`), `backend/app/api/v1/endpoints/` (`chat.py`, `gateway.py`, `finops.py`), and related evals and unit tests.

### Core Audit Conclusions

1. **Intelligent Model Routing is Non-Existent (Static String Switch Masquerading as a Decision Engine)**:
   Despite architectural specifications requiring capability-aware, quality-bounded, and latency-weighted model selection (`W-COST-05`), JakeAI's `ModelRouter` ([`app/routing/router.py`](file:///e:/JakeAI/backend/app/routing/router.py#L89-L253)) contains **zero scoring algorithms, zero quality evaluations, zero latency considerations, and zero candidate pool filtering**. It operates purely on hardcoded `if/elif` string checks (e.g., if `workload_class == "simple_chat"`, hardcode `gpt-4o-mini`). Crucially, across all production inference entry points (`chat.py`, `ai_gateway.py`, `llm_provider.py`), **`workload_class` is never set, `cost_aware_routing` is never enabled, and `max_input_cost_per_million` is never passed**. The router acts merely as a static model-to-provider dictionary lookup.

2. **Self-Hosted / Local Inference is 100% Missing**:
   Specification `W-COST-06` requires first-class local inference integration (`LocalProviderAdapter`, endpoint configuration, health checks, local compute cost modeling). In reality, **zero lines of local model code exist in the entire repository**. There are no adapters for Ollama, vLLM, LM Studio, or llama.cpp, no health probe mechanisms, and no local operational cost accounting. Local model integration is classified as **MISSING**.

3. **Two-Faced Token Accounting (Production Path vs Test Illusion)**:
   In the main user-facing chat streaming endpoint ([`app/api/v1/endpoints/chat.py:110`](file:///e:/JakeAI/backend/app/api/v1/endpoints/chat.py#L110)), raw input tokens are counted exclusively from the latest user message string (`raw_prompt_tokens = estimate_tokens(sanitized_prompt)`). System instructions, developer prompts, multi-turn conversation history, tool definitions, tool results, and RAG context are **completely excluded from input accounting**, in direct violation of `W-COST-01`. Furthermore, `pruned_prompt_tokens` is hardcoded to equal `raw_prompt_tokens` (0% pruning reduction). While a comprehensive `calculate_envelope_tokens()` function exists in `token_accounting.py`, the live chat API completely ignores it.

4. **Synthetic Simulation Masquerading as "40% Token Reduction" Proof**:
   The benchmark test that "proves" >= 40% token reduction ([`tests/evals/test_token_benchmark.py`](file:///e:/JakeAI/backend/tests/evals/test_token_benchmark.py#L108-L195)) does not execute a single real LLM call, does not measure latency, and does not evaluate task quality. Instead, it hardcodes a loop of 35 synthetic cache-hit records and 65 synthetic text prunings of a static, boilerplate-stuffed 10-Q filing string. The reported 63.51% savings is a mathematical artifact of a hardcoded test harness, not an observed capability of the live system.

5. **Exact Cache Key Collisions Due to Aggressive Text Normalization & Dropped Fields**:
   The exact cache identity function ([`compute_cache_identity`](file:///e:/JakeAI/backend/app/optimizer/semantic_cache.py#L155-L206)) unconditionally lowercases user input and collapses internal whitespace (`_normalize_text`), violating `W-COST-03` which explicitly forbids lowercasing user content and collapsing semantically meaningful whitespace. This causes case-sensitive code (Python syntax, SQL identifiers, API tokens, cryptographic hashes) and indentation-sensitive blocks to collide. Furthermore, `_canonical_messages_repr` completely omits `name`, `tool_call_id`, and `tool_calls`, causing requests with different tool execution histories to collide.

6. **Pseudo-Semantic Cache Using Word Hash Bucketing**:
   Tier 2 "Semantic Cache" does not use an embedding model or vector database. Instead, it hashes individual words using MD5 into a 128-dimensional floating-point bucket ([`semantic_cache.py:209-233`](file:///e:/JakeAI/backend/app/optimizer/semantic_cache.py#L209-L233)). Synonyms (e.g., "car" and "automobile") produce orthogonal pseudo-vectors with zero similarity, while semantically opposing sentences sharing stopwords produce high similarity. Furthermore, semantic vectors are stored solely in volatile Python dictionaries (`_memory_vectors`), wiped completely on worker restart, and candidate lookup is an exhaustive in-memory $O(N)$ linear loop.

7. **Double Quota Infrastructure and State Desynchronization**:
   The codebase contains two competing, duplicate quota governance managers:
   - `QuotaManager` in `app/services/ai_gateway.py` (uses Redis key `quota:`)
   - `FinOpsBudgetManager` in `app/finops/budget.py` (uses Redis key `finops:`)
   When a customer upgrades their tier via VietQR / PayOS in `app/services/billing.py`, only `QuotaManager` is updated. `FinOpsBudgetManager` remains set to the default 1M tokens, causing `/api/v1/finops/budget` to report out-of-date quota and triggering false suspensions if `FinOpsService.check_budget` is evaluated.

8. **Provider Prompt Caching Billed-Token Distortions**:
   In `TokenAccounting.record_transaction()` ([`token_accounting.py:402`](file:///e:/JakeAI/backend/app/optimizer/token_accounting.py#L402)), provider cached tokens (`prov_cached`) are completely subtracted from billed tokens: `billed = (opt_in - prov_cached) + completion_tokens`. In reality, providers bill for cached input (OpenAI charges 50%, Gemini charges 25%, Anthropic charges 10% plus a 1.25x write surcharge). JakeAI bills the tenant 0 tokens for provider-cached reads, absorbing provider charges without billing against quota.

---

# 2. Cost Optimization Capability Matrix

| Capability Dimension | Classification | Specification | Primary Location | Algorithmic Reality | Verification / Reality Gap | Impact / Severity |
| :--- | :--- | :--- | :--- | :--- | :--- | :--- |
| **Token Counting Engine** | `PARTIAL` | `W-COST-01` | [`bpe_tokenizer.py:44`](file:///e:/JakeAI/backend/app/optimizer/bpe_tokenizer.py#L44), [`token_pruner.py:76`](file:///e:/JakeAI/backend/app/optimizer/token_pruner.py#L76) | BPE `tiktoken` (cl100k) with regex fallback. | `TokenAccounting.calculate_envelope_tokens()` discards model parameter (`_ = model`) and uses regex heuristic instead of BPE. | Medium |
| **Token Accounting Envelope** | `BROKEN` | `W-COST-01` | [`token_accounting.py:183`](file:///e:/JakeAI/backend/app/optimizer/token_accounting.py#L183), [`chat.py:110`](file:///e:/JakeAI/backend/app/api/v1/endpoints/chat.py#L110) | Multi-turn envelope accounting implemented in library. | Disconnected from live chat stream: `/api/v1/chat/stream` derives input tokens purely from latest user prompt string, ignoring history, tools, system prompt, and RAG. | Critical |
| **Exact Response Cache** | `PARTIAL` | `W-COST-03` | [`semantic_cache.py:155`](file:///e:/JakeAI/backend/app/optimizer/semantic_cache.py#L155), [`semantic_cache.py:374`](file:///e:/JakeAI/backend/app/optimizer/semantic_cache.py#L374) | Redis GET/SET with 64-char SHA-256 digest. | Text normalization lowercases and collapses whitespace, violating W-COST-03; message canonicalization drops `name`, `tool_call_id`, `tool_calls`. In `chat.py`, all parameters default to empty. | Critical |
| **Semantic Response Cache** | `BROKEN` | `W-COST-04` | [`semantic_cache.py:209`](file:///e:/JakeAI/backend/app/optimizer/semantic_cache.py#L209), [`semantic_cache.py:415`](file:///e:/JakeAI/backend/app/optimizer/semantic_cache.py#L415) | MD5 word-hash trick into 128-dim bucket. Linear scan over Python dict. | Pseudo-embeddings have no semantic capability. No Qdrant/vector storage; in-memory entries wiped on server restart. | Critical |
| **Prompt Compression (Heuristic)**| `PARTIAL` | `W-COST-02` | [`token_pruner.py:109`](file:///e:/JakeAI/backend/app/optimizer/token_pruner.py#L109) | Strips boilerplate disclaimers, whitespace compaction, Jaccard sentence deduplication. | Preserves numbers/currencies, but is bypassed entirely on `/api/v1/chat/stream` (`pruned = raw`). | High |
| **Code Context Compression** | `PARTIAL` | `W-COST-02` | [`code_context_compressor.py:63`](file:///e:/JakeAI/backend/app/optimizer/code_context_compressor.py#L63) | Prunes unchanged lines in git diffs, excludes lockfiles/minified assets. | Well-tested in isolation, but completely unintegrated into chat streaming and agent workflows. | Medium |
| **AST Code Skeletonizer** | `WORKING` | `W-COST-02` | [`ast_skeletonizer.py:53`](file:///e:/JakeAI/backend/app/optimizer/ast_skeletonizer.py#L53) | Python AST `NodeTransformer` replacing function bodies with `...` based on task keywords. | Syntax-safe with unparse and fail-closed fallback; disconnected from live agent loop. | Low |
| **Retrieval Context Compression**| `DUPLICATED`| `W-COST-02` | [`retrieval_compressor.py:52`](file:///e:/JakeAI/backend/app/optimizer/retrieval_compressor.py#L52) vs [`context_selector.py:125`](file:///e:/JakeAI/backend/app/rag/context_selector.py#L125) | Score cutoff and Jaccard deduplication. | `RetrievalCompressor` in optimizer is completely unused by RAG pipeline; RAG uses `ContextSelector` in `app/rag/`. | Medium |
| **Two-Zone Prompt Compiler** | `WORKING` | `W-COST-00` | [`prompt_compiler.py:116`](file:///e:/JakeAI/backend/app/optimizer/prompt_compiler.py#L116) | Partitions prompt into Zone 1 (static prefix) and Zone 2 (dynamic suffix) with volatile data detection. | Deterministic prefix hashing, sorted tool serialization. Effectively isolates static prefix for caching. | Low |
| **Provider Prompt Caching** | `WORKING` | `W-COST-00` | [`provider_cache_policy.py:254`](file:///e:/JakeAI/backend/app/optimizer/provider_cache_policy.py#L254), [`anthropic.py:113`](file:///e:/JakeAI/backend/app/providers/anthropic.py#L113) | Injects Anthropic `cache_control: ephemeral` breakpoint, OpenAI automatic prefix caching. | Provider adapters extract `cached_tokens` from response usage metadata. Fully functional when upstream provider is called. | Low |
| **Intelligent Model Routing** | `PLACEHOLDER`| `W-COST-05` | [`router.py:89`](file:///e:/JakeAI/backend/app/routing/router.py#L89) | Static dictionary lookup with hardcoded if/elif branches on model string. | Zero quality scoring, zero latency weights, zero candidate scoring. Production callers pass None for workload/policy, resulting in no routing. | Critical |
| **Provider Failover Chaining** | `BROKEN` | `W-COST-05` | [`failover.py:52`](file:///e:/JakeAI/backend/app/routing/failover.py#L52), [`llm_provider.py:91`](file:///e:/JakeAI/backend/app/core/llm_provider.py#L91) | Bounded retries and fallback execution across ordered candidate tuples. | In `llm_provider.py`, `api_key` is set to primary provider's key. During failover, the primary provider's key is passed to fallback adapters, causing 401 Auth crashes. | Critical |
| **Local / Self-Hosted Models** | `MISSING` | `W-COST-06` | None | None. Zero adapters for Ollama, vLLM, LM Studio, or local runtimes. | No code, no adapters, no configuration schema, no health check endpoints. | Critical |
| **Pricing Matrix & Catalog** | `PARTIAL` | `W-COST-00` | [`provider_pricing.py:65`](file:///e:/JakeAI/backend/app/optimizer/provider_pricing.py#L65) | Centralized pricing dictionary for 12 models with input, cache read, cache write, output $/1M rates. | Hardcoded static dictionary. Missing newer model families (Claude 3.7, Gemini 2.0, GPT-4.5); falls back to arbitrary $2.00/$8.00 pricing. | Medium |
| **Cost Accounting & Attribution**| `PARTIAL` | `W-COST-01` | [`attribution.py:21`](file:///e:/JakeAI/backend/app/finops/attribution.py#L21), [`service.py:116`](file:///e:/JakeAI/backend/app/finops/service.py#L116) | Mathematical partitioning across cache hit, physical reduction, prompt cache, routing, retries. | Write surcharges are ignored in total savings (`max(0.0, prov_cache_saved)`), overstating savings. Provider cached tokens are billed at 0 tokens in token accounting. | High |
| **Quota & Budget Governance** | `DUPLICATED` | `W-COST-00` | [`ai_gateway.py:95`](file:///e:/JakeAI/backend/app/services/ai_gateway.py#L95) vs [`budget.py:27`](file:///e:/JakeAI/backend/app/finops/budget.py#L27) | Atomic Redis counters for token limits and dollar budgets. | Two competing quota managers with separate Redis keys. PayOS billing updates `QuotaManager` but leaves `FinOpsBudgetManager` desynchronized. | High |
| **Optimization Telemetry** | `PARTIAL` | `W-COST-00` | [`metrics.py:56`](file:///e:/JakeAI/backend/app/telemetry/metrics.py#L56), [`token_accounting.py:22`](file:///e:/JakeAI/backend/app/optimizer/token_accounting.py#L22) | In-memory Prometheus metrics collector and Pydantic records. | Chat streaming endpoint omits provider telemetry. In-memory metric buffers are wiped on process restart. | Medium |
| **Empirical 40% Reduction Proof**| `PLACEHOLDER`| `W-COST-02` | [`test_token_benchmark.py:108`](file:///e:/JakeAI/backend/tests/evals/test_token_benchmark.py#L108) | Synthetic test harness running 35 fake cache hits and 65 static text prunes. | Zero live model calls, zero latency measurements, zero real-world traffic evaluation. | Critical |

---

# 3. Actual Optimization Data Flow

The repository contains three distinct, disconnected paths through which cost optimization is attempted or claimed:

### Path A: The Live User-Facing Chat Endpoint (`POST /api/v1/chat/stream`)
This is the primary user-facing production path:
```
Client Request (POST /api/v1/chat/stream)
  │
  ├── 1. GuardrailsEngine.inspect_input(prompt)
  ├── 2. GuardrailsEngine.redact_pii(prompt)
  │      └─ raw_prompt_tokens = estimate_tokens(sanitized_prompt)  [EXCLUDES SYSTEM, TOOLS, HISTORY]
  │
  ├── 3. SemanticCache.get(sanitized_prompt, tenant_id)
  │      └─ [FLAW: Bypasses all generation dimensions: model, provider, messages, tools default to empty]
  │      ├─ [IF HIT]: Yields simulated tokens by splitting cached response text;
  │      │            TokenAccounting.record_transaction(raw=prompt, pruned=0, completion=est, hit=True);
  │      │            Exits immediately.
  │      └─ [IF MISS]: Continues to LangGraph graph execution.
  │
  ├── 4. stream_multi_agent_workflow(sanitized_prompt, context, conversation_id)
  │      ├─ supervisor_node: Regex intent classification.
  │      ├─ financial_specialist_node: Hardcoded regex arithmetic (NO LLM CALL).
  │      ├─ finnapigo_tool_node: Hardcoded mock dict (NO LLM CALL).
  │      ├─ verifier_node: Regex number verification (FAILS OPEN to PASS after 2 revisions).
  │      └─ synthesizer_node:
  │           └─ [IF no financial or tool data]: Calls call_upstream_llm(prompt, tenant_id)
  │                └─ HARDCODED model="gemini-1.5-flash" (NO ModelRouter, NO compression)
  │
  ├── 5. Output Guardrail & Cache Population:
  │      └─ SemanticCache.set(sanitized_prompt, tenant_id, final_response)
  │           └─ [FLAW: Omits model, provider, messages, tools from cache identity]
  │
  └── 6. Token Accounting Telemetry:
         └─ TokenAccounting.record_transaction(
                raw_prompt_tokens=raw_prompt_tokens,
                pruned_prompt_tokens=raw_prompt_tokens,   [0% PRUNED TOKENS]
                completion_tokens=comp_tokens,
                cache_hit=False
            )  [FLAW: Provider telemetry is completely ignored, 100% tokens billed]
```

### Path B: The AI Gateway Proxy (`POST /api/v1/gateway/chat/completions`)
This is an alternate reverse-proxy path:
```
Client Request (POST /api/v1/gateway/chat/completions)
  │
  ├── 1. Quota Pre-check: QuotaManager.check_quota(tenant_id)
  │
  ├── 2. Identity Generation:
  │      └─ compute_cache_identity(tenant_id, provider, model, system, messages, tools, params)
  │           └─ [FLAW: Lowers text, collapses whitespace, omits tool_call_id/name]
  │
  ├── 3. Cache Lookup: SemanticCache.get(..., exact_only=True)
  │      └─ [IF HIT]: Returns cached response; records tokens saved to QuotaManager & FinOpsService.
  │
  ├── 4. Context Optimization:
  │      └─ ContextOptimizer.optimize_dynamic_context(last_user_msg)
  │           └─ [FLAW: Only optimizes the last user query; ignores entire conversation history]
  │
  ├── 5. Two-Zone Compilation:
  │      └─ PromptCompiler.partition_messages(request.messages)
  │
  ├── 6. Provider Dispatch:
  │      └─ call_upstream_llm_detailed(..., model=request.model, compiled_prompt=compiled)
  │           ├─ ModelRouter.route(RoutingPolicy(requested_model=model, tenant_id=tenant_id))
  │           │    └─ [FLAW: No workload_class or budget passed; returns requested model unchanged]
  │           └─ FailoverManager.execute_with_failover()
  │                └─ ProviderAdapter (Anthropic/OpenAI/Gemini/DeepSeek)
  │                     └─ Provider Prompt Caching (KV breakpoints attached)
  │
  ├── 7. Token Accounting & Reconciliation:
  │      └─ TokenAccounting.record_transaction(provider_telemetry=telemetry)
  │           └─ [FLAW: Subtracts 100% of provider cached tokens from billed token count]
  │
  └── 8. Quota & FinOps Settlement:
         ├─ QuotaManager.record_usage() [Redis key: quota:]
         └─ FinOpsService.record_upstream_inference() -> FinOpsBudgetManager [Redis key: finops:]
              └─ [FLAW: Updates two separate, unsynced Redis quota structures]
```

### Path C: The Agent Platform REST Endpoint (`POST /api/v1/agent/tasks`)
This is the autonomous ReAct agent path:
```
Client Request (POST /api/v1/agent/tasks/{id}/runs)
  │
  ├── AgentExecutionLoop.execute()
  │     ├─ ShortTermMemory: FIFO message queue (entry bounded, not token bounded).
  │     ├─ BoundedPlanner: Calls JakeAIBackend.generate()
  │     │    └─ call_upstream_llm_detailed(model="gemini-1.5-flash")
  │     │         └─ Hardcoded model string; zero dynamic model routing.
  │     └─ Zero context compression, zero response caching, zero AST skeletonization.
```

---

# 4. Token Accounting Reality

### What is Actually Counted vs Ignored

Specification `W-COST-01` dictates that token accounting must reflect the complete model-visible request envelope. The code inspection reveals a complete bifurcation between library helper functions and live execution paths:

1. **In `app/optimizer/token_accounting.py:calculate_envelope_tokens()`**:
   - System instructions: Counted (+4 delimiter overhead).
   - Conversation messages: Counted (+4 overhead per turn).
   - Message roles: Counted.
   - Message names & tool call IDs: Counted (+1 overhead).
   - Tool calls: Serialized JSON counted.
   - Tool definitions (schemas): Serialized JSON counted (+8 overhead).
   - RAG context & dynamic context: Counted if passed.
   - Framing overhead: Explicitly accounted for.
   - **Flaw**: It completely ignores the `model` parameter ([`token_accounting.py:205`](file:///e:/JakeAI/backend/app/optimizer/token_accounting.py#L205): `_ = model`), delegating token estimation to the regex counter `estimate_tokens()` instead of the model-specific `BPETokenizer`.

2. **In `app/api/v1/endpoints/chat.py` (The Live Chat Stream)**:
   - System instructions: **0 tokens counted (IGNORED)**.
   - Conversation history: **0 tokens counted (IGNORED)**.
   - Tool definitions / outputs: **0 tokens counted (IGNORED)**.
   - RAG context passages: **0 tokens counted (IGNORED)**.
   - Total input tokens counted: Derived exclusively from `estimate_tokens(sanitized_prompt)` (only the latest user message string).
   - Pruned input tokens: Derived as `pruned_prompt_tokens = raw_prompt_tokens` (0 physical tokens removed).

### Double Counting and Free-Token Flaws in Billed Tokens

In `TokenAccounting.record_transaction()` ([`token_accounting.py:401-404`](file:///e:/JakeAI/backend/app/optimizer/token_accounting.py#L401-L404)):
```python
if effective_billed_tokens is not None:
    billed = effective_billed_tokens
elif prov_cached > 0:
    billed = (opt_in - prov_cached) + completion_tokens
else:
    billed = opt_in + completion_tokens
```
This formula contains a fundamental accounting error:
- Upstream providers do **not** provide KV prompt caching for free. OpenAI charges 50% of the input rate ($1.25/M on GPT-4o); Anthropic charges 10% ($0.30/M on Claude 3.5 Sonnet) plus a 1.25x creation surcharge ($3.75/M); Gemini charges 25% ($0.875/M on 1.5 Pro).
- JakeAI calculates `billed = (opt_in - prov_cached) + completion_tokens`, which treats all provider cached tokens as 100% free (zero tokens billed).
- Consequently, the tenant is credited with 0 tokens consumed for cached inputs, while JakeAI incurs real billing charges from the upstream provider.

---

# 5. Cache Reality

### Exact Cache (`W-COST-03`)

The exact cache implementation is split across `compute_cache_identity()` and `SemanticCacheManager`:

1. **Identity Generation Algorithm**:
   [`app/optimizer/semantic_cache.py:192-206`](file:///e:/JakeAI/backend/app/optimizer/semantic_cache.py#L192-L206):
   $$\text{Identity} = \text{SHA-256}\left( \text{v} \parallel \text{t} \parallel \text{p} \parallel \text{m} \parallel \text{si} \parallel \text{msgs} \parallel \text{tools} \parallel \text{rf} \parallel \text{params} \right)$$
   Separated by ASCII Unit Separator `\x1f`.

2. **Severe Normalization & Collision Vulnerabilities**:
   - `_normalize_text(text)` executes:
     ```python
     nfc_text = unicodedata.normalize("NFC", text.strip().lower())
     return re.sub(r"\s+", " ", nfc_text)
     ```
     This lowercases all text and collapses multiple spaces, newlines, and tabs into a single space.
   - **Violation of `W-COST-03:42-43`**: Specification explicitly mandates: *"do not lowercase arbitrary user content; do not collapse semantically meaningful whitespace"*.
   - **Impact**: In coding workloads, Python indentation is destroyed (different indentation levels collapse to the same cache key). In SQL or data workloads, case-sensitive strings and password/token hashes collide.
   - **Omission of Message Fields**: In `_canonical_messages_repr` ([`semantic_cache.py:108-112`](file:///e:/JakeAI/backend/app/optimizer/semantic_cache.py#L108-L112)), only `role` and `content` are serialized. The fields `name`, `tool_call_id`, and `tool_calls` are completely discarded. Two multi-turn tool sessions with different tool outputs will generate identical cache keys.

3. **Get/Set Identity Symmetry**:
   In `GatewayInferenceProxy` ([`ai_gateway.py:330, 528`](file:///e:/JakeAI/backend/app/services/ai_gateway.py#L330)), `get()` and `set()` pass the identical set of keyword arguments to `compute_cache_identity()`. However, on `/api/v1/chat/stream` ([`chat.py:136, 293`](file:///e:/JakeAI/backend/app/api/v1/endpoints/chat.py#L136)), neither `get()` nor `set()` passes model, provider, messages, tools, or params. The identity function is bypassed and falls back to a 1-message synthesized prompt.

### Semantic Cache (`W-COST-04`)

Specification `W-COST-04` requires semantic candidate retrieval using vector embeddings, cosine similarity thresholding, and cross-tenant isolation.

1. **Pseudo-Vector Reality**:
   JakeAI uses **zero vector embedding models**. In `_generate_synthetic_embedding()` ([`semantic_cache.py:209-233`](file:///e:/JakeAI/backend/app/optimizer/semantic_cache.py#L209-L233)):
   ```python
   words = re.findall(r"\b\w+\b", text.lower())
   vec = [0.0] * dim
   for word in words:
       token_hash = int(hashlib.md5(word.encode(), usedforsecurity=False).hexdigest(), 16)
       idx = token_hash % dim
       vec[idx] += 1.0
   ```
   This is a feature-hashing trick on token frequency, not a semantic embedding:
   - Synonymous terms ("revenue" vs "turnover", "bug" vs "defect") hash to unrelated buckets; cosine similarity between them is 0.0.
   - Completely opposing statements sharing common words ("revenue increased by 50%" vs "revenue dropped by 50%") share 80% of buckets and yield high similarity (> 0.85).

2. **Storage and Query Scalability**:
   - While exact matches are stored in Redis (`cache:exact:{tenant_id}:{exact_key}`), semantic entries are stored **exclusively in a transient Python dictionary** (`self._memory_vectors`).
   - Querying the semantic cache runs a brute-force linear loop `for entry in tenant_entries` in worker heap memory.
   - All semantic cache entries are permanently lost on ASGI process restart.

---

# 6. Compression Reality

Specification `W-COST-02` requires prompt compression to remove non-essential tokens while preserving constraints, safety instructions, tool schemas, and unique evidence.

### What is Preserved vs Pruned in Algorithms

| Module | Location | Pruning Mechanism | Preserved Elements | Failure / Risk |
| :--- | :--- | :--- | :--- | :--- |
| **`HeuristicTokenPruner`** | [`token_pruner.py:109`](file:///e:/JakeAI/backend/app/optimizer/token_pruner.py#L109) | Strips regex boilerplate (disclaimers, headers/footers), collapses whitespace, deduplicates sentences via Jaccard overlap (> 0.85). | Currencies ($€£¥₫), percentages, dates, quarters (Q1-Q4), citation tags (`[SEC-...]`), dotted code identifiers, markdown code blocks. | If input is JSON, minifies JSON via `compact_json`. |
| **`CodeSkeletonizer`** | [`ast_skeletonizer.py:53`](file:///e:/JakeAI/backend/app/optimizer/ast_skeletonizer.py#L53) | Python AST transformer replacing function bodies with `...` under `BALANCED` or `AGGRESSIVE` mode. | Module docstrings, class inheritance, method signatures, parameter defaults, type annotations, imports, route decorators (`router`, `endpoint`), dunder methods (`__init__`). | Fails closed: on `SyntaxError`, returns unmodified code. |
| **`CodeContextCompressor`** | [`code_context_compressor.py:63`](file:///e:/JakeAI/backend/app/optimizer/code_context_compressor.py#L63) | Prunes unchanged lines in unified diffs (`> 6` lines collapsed to `... [N lines omitted] ...`), summarizes lockfiles (`package-lock.json`, `go.sum`). | Unified diff headers, additions (`+`), deletions (`-`), active hunk headers (`@@`). Strictly NO-OP for non-coding tasks. | Non-Python code cannot be AST-skeletonized (regex fallback). |
| **`RetrievalCompressor`** | [`retrieval_compressor.py:52`](file:///e:/JakeAI/backend/app/optimizer/retrieval_compressor.py#L52) | Drops chunks below relative score threshold (`< 0.35 * max_score`), bounds chunks to top 5. | Citation anchors (`[SEC-...]`), numerical facts. | Completely orphaned; RAG pipeline uses `ContextSelector` instead. |

### Connection to Live Model Path

The prompt compression engine is **almost completely disconnected from live production inference**:
1. In `app/api/v1/endpoints/chat.py`: Neither `ContextOptimizer`, `HeuristicTokenPruner`, nor `CodeContextCompressor` is invoked. Context compression is 100% inactive.
2. In `app/services/ai_gateway.py:405`: `ContextOptimizer.optimize_dynamic_context()` is called, but passed **only the last user message string** (`dynamic_context=last_user_msg, user_query=last_user_msg`). It never compresses conversation history, retrieved documents, or tool schemas.
3. In `app/agent/backends/jakeai.py`: Compression is never called; raw messages are formatted and sent directly.

---

# 7. Intelligent Routing Reality

Specification `W-COST-05` mandates a deterministic, capability-aware decision engine that classifies workloads, applies hard capability filters, and computes multi-objective soft scores (quality, capability, latency, cost).

### Trace Analysis of `ModelRouter`

In [`backend/app/routing/router.py:95-253`](file:///e:/JakeAI/backend/app/routing/router.py#L95-L253), the routing algorithm executes as follows:
```python
# Step 1: Lookup default provider from model name
provider_name = policy.preferred_provider or self.registry.resolve_provider_name_for_model(model)

# Step 2: Check allowed / disallowed provider lists
if policy.allowed_providers and provider_name not in policy.allowed_providers:
    provider_name = policy.allowed_providers[0]

# Step 3: Check capability requirements (only supports_reasoning is implemented)
for req_cap in policy.required_capabilities:
    if req_cap == "supports_reasoning":
        if provider_name == "openai": selected_model = "o3-mini"
        elif provider_name == "deepseek": selected_model = "deepseek-reasoner"
        else: provider_name = "openai"; selected_model = "o3-mini"

# Step 4: Cost-Aware check (HARDCODED STRING REPLACEMENT)
if ((policy.cost_aware_routing or policy.workload_class == "simple_chat")
    and policy.workload_class == "simple_chat"
    and cap.input_pricing > 0.50):
    if provider_name == "openai" and "mini" not in selected_model: selected_model = "gpt-4o-mini"
    elif provider_name == "anthropic" and "haiku" not in selected_model: selected_model = "claude-3-haiku"
    elif provider_name == "gemini" and "flash" not in selected_model: selected_model = "gemini-1.5-flash"

# Step 5: Cost budget check (HARDCODED STRING REPLACEMENT)
if policy.max_input_cost_per_million is not None and cap.input_pricing > policy.max_input_cost_per_million:
    if provider_name == "openai": selected_model = "gpt-4o-mini"
    elif provider_name == "anthropic": selected_model = "claude-3-haiku"
    elif provider_name == "gemini": selected_model = "gemini-1.5-flash"
```

### Reality vs Specification Gap

1. **No Decision Engine**:
   - There is no workload classification engine. Workload classification is expected as an input string (`policy.workload_class`).
   - There is no model scoring formula ($\text{Score} = w_q Q + w_c C + w_l L - w_{\$} \$_{\text{norm}}$). No weights exist.
   - Latency targets are completely ignored.
   - Context window limits are completely ignored (the router never checks if input tokens exceed model context limit).
2. **Hardcoded Fallback Chains**:
   - In [`router.py:197-224`](file:///e:/JakeAI/backend/app/routing/router.py#L197-L224), fallback candidates are hardcoded tuples:
     - `anthropic` $\rightarrow$ `[("openai", "gpt-4o"), ("gemini", "gemini-1.5-flash")]`
     - `openai` $\rightarrow$ `[("gemini", "gemini-1.5-flash"), ("groq", "llama-3.1-8b-instant")]`
   - Candidates are not selected dynamically based on availability, health, or capability match.
3. **Disconnected Production Callers**:
   - In `app/core/llm_provider.py:72`, `router.route()` is called with only `requested_model` and `tenant_id`. It never passes `workload_class`, `cost_aware_routing`, or `max_input_cost_per_million`.
   - In `app/api/v1/endpoints/chat.py`, `ModelRouter` is never called.
   - In `app/agent/backends/jakeai.py`, `ModelRouter` is never called.

---

# 8. Local Model Reality

Specification `W-COST-06` mandates self-hosted and local model integration as a first-class provider path.

### Audit Inspection Findings

1. **Provider Registry**:
   In [`app/providers/registry.py:25-32`](file:///e:/JakeAI/backend/app/providers/registry.py#L25-L32), the registered providers are:
   `anthropic`, `openai`, `gemini`, `groq`, `deepseek`, `openrouter`.
   There is **no `local` provider**, no `ollama` provider, and no `vllm` provider.
2. **Adapters and Endpoints**:
   A repository-wide search for `LocalProviderAdapter`, `ollama`, `vllm`, `llama.cpp`, and `self_hosted` yielded zero results across all source files in `backend/app/`.
3. **Health Check and Connectivity**:
   No runtime endpoint pinging, no local GPU/CPU availability checks, and no local concurrency limiters exist.
4. **Local Cost Modeling**:
   Specification requires local compute/energy operational cost representation. Zero operational cost modeling exists.

**Classification**: `MISSING`.

---

# 9. Pricing / Cost Accounting Reality

### Source and Centralization of Pricing

Pricing is defined in [`app/optimizer/provider_pricing.py:65-167`](file:///e:/JakeAI/backend/app/optimizer/provider_pricing.py#L65-L167) in a static dictionary `PRICING_CATALOG` containing rates for 12 models.
- `app/finops/pricing.py` imports from `app.optimizer.provider_pricing`.
- `app/providers/base.py` copies rates into `ModelCapabilityCatalog`.

### Price Divergence and Fallback Vulnerability

1. **Static Table Staleness**:
   The pricing catalog contains fixed rates (e.g., Claude 3.5 Sonnet at $3.00/$15.00, GPT-4o at $2.50/$10.00). Models introduced after Phase 01 (e.g., Claude 3.5 Haiku, Claude 3.7 Sonnet, Gemini 2.0 Flash, GPT-4.5) are absent.
2. **Default Pricing Fallback**:
   When an unknown model string is passed, [`provider_pricing.py:206`](file:///e:/JakeAI/backend/app/optimizer/provider_pricing.py#L206) falls back to `DEFAULT_FALLBACK_PRICING` ($2.00 input, $8.00 output per million). If a cheap model like `gemini-2.0-flash` ($0.10/M) is passed, JakeAI estimates its cost at $2.00/M (a 20x overestimation).

### Mathematical Correctness of Savings Calculations

In `compute_savings_attribution()` ([`app/finops/attribution.py:21-113`](file:///e:/JakeAI/backend/app/finops/attribution.py#L21-L113)):
- **Telescoping Sum**: The theoretical partitioning:
  $$\text{Total Savings} = \text{Routing Savings} + \text{Physical Pruning Savings} + \text{Provider Prompt Cache Savings}$$
  is mathematically disjoint and avoids double-counting between input reduction and provider cache discounts.
- **Flaw in Negative Cache Savings (Write Surcharges)**:
  Line 101 states:
  ```python
  total_savings = round(routing_saved + physical_saved + max(0.0, prov_cache_saved) + retries_saved, 6)
  ```
  When an Anthropic request writes to cache without a read hit, `prov_cache_saved` is negative (surcharge incurred). By taking `max(0.0, prov_cache_saved)`, the write penalty is discarded, artificially inflating reported savings.
- **Avoided Retries Savings Fabrication**:
  `avoided_retries_usd` is added directly to `total_savings_usd`, despite baseline cost not including multiple retry executions.

---

# 10. Optimization Measurement Reality

### Analysis of the "40% Token Reduction" Claim

The repository documentation repeatedly cites a verified "$\ge 40\%$ net token reduction". An exhaustive inspection of how this claim is verified reveals:

1. **Synthetic Generation in Test Suite**:
   In [`tests/evals/test_token_benchmark.py:108-174`](file:///e:/JakeAI/backend/tests/evals/test_token_benchmark.py#L108-L174):
   - 35 transactions are generated in a synthetic loop with `cache_hit=True` (simulating a 35% cache hit rate).
   - 65 transactions are generated in a synthetic loop by running `pruner.prune_context()` on a static mock string (`ENTERPRISE_RAG_CORPUS`) specifically constructed with repetitive boilerplate sentences and disclaimers.
   - The test aggregates these synthetic records via `TokenAccounting.aggregate_benchmark()` and asserts `net_reduction_percentage >= 40.0%`.
2. **Zero Reality in Production Streaming**:
   In [`app/api/v1/endpoints/chat.py:339`](file:///e:/JakeAI/backend/app/api/v1/endpoints/chat.py#L339), when a cache miss occurs, `pruned_prompt_tokens` is set equal to `raw_prompt_tokens`. **The actual physical token reduction on the live chat path is exactly 0.0%**.

### Measurement of Latency and Quality

1. **Quality Oracle**:
   [`app/evals/quality_oracle.py`](file:///e:/JakeAI/backend/app/evals/quality_oracle.py#L67) contains a rule-based evaluation evaluator checking regex facts, bracket citations, and JSON validity.
2. **No Quality vs Cost Regression Tracking**:
   In `test_coding_intelligence_regression.py`, bug-fix preservation is tested by taking the optimizer output, running a Python string replacement `res.content.replace(...)`, and executing `exec()`. An LLM is never called to evaluate whether context compression impacts model generation accuracy.

---

# 11. Logic Risks

1. **API Key Poisoning During Provider Failover** (`CRITICAL`):
   In [`app/core/llm_provider.py:91-95`](file:///e:/JakeAI/backend/app/core/llm_provider.py#L91-L95), `explicit_key` is resolved strictly for `decision.selected_provider` and attached to `provider_req.api_key`. When `FailoverManager` catches a failure on the primary provider and iterates to the fallback candidate ([`failover.py:109`](file:///e:/JakeAI/backend/app/routing/failover.py#L109)), `request.api_key` remains populated with the *first* provider's secret. When `OpenAIAdapter._resolve_api_key()` ([`openai.py:52`](file:///e:/JakeAI/backend/app/providers/openai.py#L52)) checks `if request.api_key: return request.api_key`, it forwards the Anthropic key to OpenAI, resulting in an unrecoverable 401 Authentication failure.

2. **Exact Cache Key Collisions for Code and Case-Sensitive Data** (`HIGH`):
   In [`app/optimizer/semantic_cache.py:74-78`](file:///e:/JakeAI/backend/app/optimizer/semantic_cache.py#L74-L78), `_normalize_text()` lowercases text and collapses `\s+` to `" "`. Python code blocks differing only in whitespace indentation or case-sensitive variables produce identical SHA-256 digests, returning corrupted cached responses across different user programs.

3. **Tool Execution History Dropped from Cache Identity** (`HIGH`):
   In [`app/optimizer/semantic_cache.py:108-112`](file:///e:/JakeAI/backend/app/optimizer/semantic_cache.py#L108-L112), `_canonical_messages_repr` ignores `tool_call_id`, `name`, and `tool_calls`. Consecutive turns in an agent tool-calling loop collide in cache if the text contents match.

4. **Zero-Token Billing Leak for Provider Prompt Caching** (`HIGH`):
   In [`app/optimizer/token_accounting.py:402`](file:///e:/JakeAI/backend/app/optimizer/token_accounting.py#L402), `prov_cached` is subtracted 1:1 from billed tokens, deducting 0 tokens from the tenant's quota for cached prompt reads.

---

# 12. Duplicate / Conflicting Implementations

1. **Duplicate Quota Governance**:
   - Implementation 1: `QuotaManager` in [`app/services/ai_gateway.py:95`](file:///e:/JakeAI/backend/app/services/ai_gateway.py#L95) (`f"quota:used:{tenant_id}:{period}"`).
   - Implementation 2: `FinOpsBudgetManager` in [`app/finops/budget.py:27`](file:///e:/JakeAI/backend/app/finops/budget.py#L27) (`f"finops:used:tokens:{tenant_id}:{period}"`).
   - Conflict: `app/services/billing.py` updates only `QuotaManager`. The two quota tracking stores operate completely out of sync.

2. **Duplicate Retrieval Compression**:
   - Implementation 1: `RetrievalCompressor` in [`app/optimizer/retrieval_compressor.py:52`](file:///e:/JakeAI/backend/app/optimizer/retrieval_compressor.py#L52).
   - Implementation 2: `ContextSelector` in [`app/rag/context_selector.py:125`](file:///e:/JakeAI/backend/app/rag/context_selector.py#L125).
   - Conflict: Both implement relative thresholding, Jaccard deduplication, and budget packing. `RetrievalCompressor` is dead code; `ContextSelector` is the active module.

3. **Conflicting Provider Resolution Substring Parsers**:
   - Implementation 1: `ProviderRegistry.resolve_provider_name_for_model()` in `app/providers/registry.py`.
   - Implementation 2: `get_provider_cache_policy()` in `app/optimizer/provider_cache_policy.py`.
   - Implementation 3: `get_model_pricing()` in `app/optimizer/provider_pricing.py`.
   - Conflict: Substring matches differ. E.g., `llama-3.3-70b` resolves to `groq` in `registry.py` and `provider_pricing.py`, but resolves to `unknown` in `provider_cache_policy.py`.

---

# 13. Missing Functional Requirements

Against the assigned specifications (`W-COST-00` to `W-COST-06`):

1. **`W-COST-01` (Token Management)**:
   - Live chat streaming input envelope accounting reflecting system prompt, history, tools, and RAG is **MISSING** on `/api/v1/chat/stream`.
2. **`W-COST-02` (Prompt Compression)**:
   - Connection of `ContextOptimizer` to the live chat streaming path and agent execution loop is **MISSING**.
   - Safe fallback to raw context upon detected quality regression during live inference is **MISSING**.
3. **`W-COST-03` (Exact Cache)**:
   - Preservation of case and meaningful whitespace in user content is **MISSING**.
   - Inclusion of `name`, `tool_call_id`, and `tool_calls` in message serialization is **MISSING**.
4. **`W-COST-04` (Semantic Cache)**:
   - Real semantic embedding vector generation and Qdrant vector storage are **MISSING**.
   - Dynamic threshold calibration based on benchmark evidence is **MISSING**.
5. **`W-COST-05` (Intelligent Model Routing)**:
   - Dynamic workload classification in inference requests is **MISSING**.
   - Multi-objective soft scoring engine ($\text{quality}, \text{capability}, \text{latency}, \text{cost}$) is **MISSING**.
   - Context window capacity pre-filtering is **MISSING**.
6. **`W-COST-06` (Local Model Integration)**:
   - `LocalProviderAdapter` for self-hosted engines (Ollama, vLLM) is **MISSING**.
   - Health check and capability probing before routing to local instances are **MISSING**.
   - Local operational cost modeling (compute/energy estimation) is **MISSING**.

---

# 14. Required Work Order

To bring the Cost Optimization capability to production readiness without breaking existing contracts, the following sequential work order is recommended for subsequent engineering phases:

### Phase 1: Security & Defect Repair (Make It Right)
1. **Fix Cross-Provider Failover Key Poisoning**:
   In `app/routing/failover.py`, ensure `current_request` clears `api_key` or resolves the specific credential for `provider_name` before invoking `adapter.complete()`.
2. **Correct Exact Cache Normalization & Message Dimensions**:
   In `app/optimizer/semantic_cache.py`:
   - Modify `_normalize_text()` to preserve case and meaningful whitespace for user message content and code blocks.
   - Update `_canonical_messages_repr()` to serialize `name`, `tool_call_id`, and `tool_calls`.
3. **Eliminate Duplicate Quota Governance**:
   Deprecate `QuotaManager` in `app/services/ai_gateway.py`. Unify all quota and budget operations around `FinOpsBudgetManager` in `app/finops/budget.py`. Update `billing.py` to target the unified budget manager.
4. **Fix Provider Cache Billed-Token Derivation**:
   In `app/optimizer/token_accounting.py`, calculate effective billed tokens using provider discount ratios rather than subtracting 100% of cached tokens.

### Phase 2: Live Path Integration (Make It Work)
5. **Connect Canonical Envelope Accounting to Chat Stream**:
   In `app/api/v1/endpoints/chat.py`, replace `estimate_tokens(sanitized_prompt)` with `TokenAccounting.calculate_envelope_tokens()` including conversation history, system prompt, and RAG passages.
6. **Wire Compression into Active Inference Paths**:
   Integrate `ContextOptimizer` into `app/api/v1/endpoints/chat.py` and `app/agent/backends/jakeai.py`.
7. **Deprecate Orphaned Retrieval Compressor**:
   Consolidate `RetrievalCompressor` into `ContextSelector` to eliminate parallel implementations.

### Phase 3: Capability Completion (Make It Right)
8. **Implement Genuine Intelligent Model Routing**:
   In `app/routing/router.py`, implement the full specification:
   - Add workload classifier or extract task tags.
   - Filter candidates by context limit and capability flags.
   - Calculate configurable soft scores across quality, latency, capability, and cost.
9. **Implement `LocalProviderAdapter`**:
   Build `app/providers/local.py` implementing `LLMProvider` with configurable OpenAI-compatible endpoints (vLLM / Ollama), health probes, and operational cost accounting.
10. **Implement True Vector-Based Semantic Caching**:
    Replace the MD5 word-hash trick in `app/optimizer/semantic_cache.py` with real dense embeddings and Qdrant tenant-isolated collections.

---

# 15. Evidence

### Evidence 1: Latest User Prompt Only Counted in Live Chat
File: [`backend/app/api/v1/endpoints/chat.py:110, 335-344`](file:///e:/JakeAI/backend/app/api/v1/endpoints/chat.py#L110)
```python
109: sanitized_prompt, _ = GuardrailsEngine.redact_pii(prompt)
110: raw_prompt_tokens = estimate_tokens(sanitized_prompt)
...
335: comp_tokens = max(1, estimate_tokens(final_response)) if final_response else 10
336: record = TokenAccounting.record_transaction(
337:     request_id=f"stream-{conversation_id}",
338:     tenant_id=context.tenant_id,
339:     model="stream",
340:     raw_prompt_tokens=raw_prompt_tokens,
341:     pruned_prompt_tokens=raw_prompt_tokens,
342:     completion_tokens=comp_tokens,
343:     cache_hit=False,
344:     cache_type="none",
345: )
```

### Evidence 2: Exact Cache Key Omits Message Dimensions & Destroys Whitespace/Case
File: [`backend/app/optimizer/semantic_cache.py:74-77, 108-112`](file:///e:/JakeAI/backend/app/optimizer/semantic_cache.py#L74-L77)
```python
74: def _normalize_text(text: str) -> str:
75:     """Apply deterministic Unicode NFC normalization and whitespace collapsing."""
76:     nfc_text = unicodedata.normalize("NFC", text.strip().lower())
77:     return re.sub(r"\s+", " ", nfc_text)
...
108: for msg in messages:
109:     role = msg.get("role", "").strip().lower()
110:     content = _normalize_text(msg.get("content", ""))
111:     parts.append(f"{role}:{content}")
112: return "\x1e".join(parts)  # ASCII record separator
```

### Evidence 3: Pseudo-Vector Word-Hash Trick in Semantic Cache
File: [`backend/app/optimizer/semantic_cache.py:209-228`](file:///e:/JakeAI/backend/app/optimizer/semantic_cache.py#L209-L228)
```python
209: def _generate_synthetic_embedding(text: str, dim: int = 128) -> list[float]:
215:     words = re.findall(r"\b\w+\b", text.lower())
216:     vec = [0.0] * dim
217:     if not words:
218:         return vec
219: 
220:     for word in words:
221:         # Hash each token across vector buckets
222:         token_hash = int(
223:             hashlib.md5(word.encode(), usedforsecurity=False).hexdigest(), 16
224:         )
225:         idx = token_hash % dim
226:         vec[idx] += 1.0
```

### Evidence 4: Model Router Disconnected from Production Callers
File: [`backend/app/core/llm_provider.py:71-77`](file:///e:/JakeAI/backend/app/core/llm_provider.py#L71-L77)
```python
71: router = get_model_router()
72: routing_policy = RoutingPolicy(
73:     requested_model=model,
74:     tenant_id=tenant_id,
75:     allow_fallback=True,
76: )
77: decision = router.route(routing_policy)
```

### Evidence 5: Cross-Provider Failover Key Poisoning
File: [`backend/app/core/llm_provider.py:91-97`](file:///e:/JakeAI/backend/app/core/llm_provider.py#L91-L97) and [`backend/app/providers/openai.py:51-53`](file:///e:/JakeAI/backend/app/providers/openai.py#L51-L53)
```python
# app/core/llm_provider.py:
90: settings_key = provider_settings_keys.get(decision.selected_provider)
93: explicit_key = await byok_mgr.get_decrypted_key(tenant_id, decision.selected_provider) or getattr(settings, settings_key, None)
...
97: provider_req = ProviderRequest(..., api_key=explicit_key)

# app/providers/openai.py:
51: async def _resolve_api_key(self, request: ProviderRequest) -> str:
52:     if request.api_key:
53:         return request.api_key  # Inherits Anthropic key on failover -> 401 Auth Error
```

### Evidence 6: Free Billed Tokens Flaw in Provider Cache Accounting
File: [`backend/app/optimizer/token_accounting.py:401-404`](file:///e:/JakeAI/backend/app/optimizer/token_accounting.py#L401-L404)
```python
401: elif prov_cached > 0:
402:     billed = (opt_in - prov_cached) + completion_tokens
403: else:
404:     billed = opt_in + completion_tokens
```

### Evidence 7: Synthetic Benchmark Test Loop Creating Illusion of 40% Reduction
File: [`backend/tests/evals/test_token_benchmark.py:120-136, 170`](file:///e:/JakeAI/backend/tests/evals/test_token_benchmark.py#L120-L136)
```python
120: # 1. 35 Cache Hit Requests (FAQ / Repeat queries)
121: for i in range(35):
122:     record = TokenAccounting.record_transaction(
125:         raw_prompt_tokens=250,
126:         pruned_prompt_tokens=0,
127:         completion_tokens=150,
128:         cache_hit=True,
129:     )
130:     records.append(record)
...
170: assert summary.is_claim_verified, (
171:     f"Claim FAILED: Net token reduction was {summary.net_reduction_percentage}%"
172: )
```

---
*Audit completed under strict zero-modification constraints in accordance with `docs/JakeAI — Universal AI Engineering Worker.md` and `docs/engineering/00 — JakeAI Engineering Master.md`.*
