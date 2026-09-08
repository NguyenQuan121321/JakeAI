# JAKEAI REPAIR — REPAIR-00: BOOTSTRAP RESULT

> **Execution Date:** 2026-09-08  
> **Phase:** REPAIR-00 — Bootstrap  
> **Status:** COMPLETED  
> **Auditor / Worker:** Principal AI Platform Engineer (Antigravity Diagnostic Engine)  
> **Compliance Standard:** JakeAI Universal AI Engineering Worker & Repair Master Prompt  

---

## 1. Current System Understanding

### 1.1 What JakeAI Currently Is
JakeAI is an enterprise-grade embedded AI provider and multi-agent platform designed to integrate with **FinnApiGo** as its upstream Identity, Authorization, and Business Core service. The platform serves as a unified AI Gateway, context optimization engine, and autonomous agent runtime with:
- Multi-provider abstraction across 6 LLMs (OpenAI, Anthropic, Gemini, Groq, DeepSeek, OpenRouter);
- Tenant-isolated Bring-Your-Own-Key (BYOK) credential management;
- Sub-millisecond exact and semantic response caching;
- Multi-layer context and token optimization targeting $\ge 40\%$ net cost reduction at the benchmark portfolio level;
- Hybrid multi-tenant RAG (dense Qdrant vector retrieval + sparse BM25) with evidence-preserving context selection and verifiable citation generation;
- Trustworthy AI FinOps with separated token metrics, provider usage reconciliation, and dual quota/budget enforcement;
- Modular autonomous agent execution (`backend/app/agent/`) with bounded planning, sandbox isolation, and server-side human approval gates for high-risk operations.

### 1.2 Major Subsystem Boundaries
The codebase maintains clear boundaries across its packages in `backend/app/`:
1. **API Boundary (`app/api/v1/`):** FastAPI routers exposing versioned REST endpoints (`/chat`, `/models`, `/byok`, `/rag`, `/finops`, `/agent`, `/gateway`).
2. **AI Gateway (`app/services/ai_gateway.py`):** Central proxy implementing OpenAI-compatible `/v1/chat/completions`, local exact caching, quota checks, context optimization, and model routing.
3. **Core Platform (`app/core/`):** Pydantic configuration (`config.py`), JWT RS256 authentication & tenant context injection (`security.py`, `context.py`), BYOK encryption (`byok.py`), and upstream provider client dispatch (`llm_provider.py`).
4. **Provider Foundation (`app/providers/`):** Strict `LLMProvider` Protocol, isolated vendor adapters, `ModelCapabilityCatalog`, and normalized `ErrorCategory` taxonomy.
5. **Context Optimizer (`app/optimizer/`):** 8-tier optimization architecture (exact cache, vector semantic cache, redundancy compression, retrieval compression, two-zone prompt compilation, provider cache policies, code context compression, cost-aware routing).
6. **RAG Subsystem (`app/rag/`):** Document ingestion, chunking, dual indexing (Qdrant + BM25), hybrid candidate retrieval, reranking, `ContextSelector`, and inline citation mapping.
7. **Agent Subsystem (`app/agent/`):** Decoupled agent runtime with `AgentExecutionLoop`, `BoundedPlanner`, sandbox manager, server-side human approval gates, role-based tool registry, and episodic memory.
8. **FinOps Subsystem (`app/finops/`):** Authoritative billing reconciliation, disjoint savings attribution, tenant budget ledger, and alert/suspension governance.
9. **Evaluation Subsystem (`app/evals/`):** 7-dimension rubric evaluator, blinded LLM judge, and multi-severity regression detection.

### 1.3 Provider Architecture
The provider subsystem is anchored by the `LLMProvider` Protocol (`app/providers/base.py`), which mandates three operations: `complete()`, `stream()`, and `capabilities()`. Six vendor adapters exist: `OpenAIAdapter`, `AnthropicAdapter`, `GeminiAdapter`, `GroqAdapter`, `DeepSeekAdapter`, and `OpenRouterAdapter`. Key lifecycle and routing decisions are managed via `ProviderRegistry`, `ModelRouter`, and `FailoverManager`.
- *Observed Defect:* Adapters take `ProviderRequest` which lacks a native `messages` parameter, forcing multi-turn history to be flattened into a single prompt string (`PROV-02`). Upstream calls recreate an `httpx.AsyncClient` per request (`PROV-01`).

### 1.4 Gateway Architecture
`GatewayInferenceProxy` (`app/services/ai_gateway.py`) acts as the external OpenAI-compatible facade. It coordinates pre-flight quota checks, exact cache lookups, context optimization, provider resolution, BYOK decryption, model invocation, and post-inference usage settlement.
- *Observed Defect:* The gateway computes exact cache keys solely from `last_user_msg`, ignoring model, provider, temperature, tools, and preceding turns (`CACHE-01`). It uses a hardcoded ternary for provider resolution that omits `deepseek` and `groq` (`DUP-02`). Streaming is simulated by sleeping 2ms after completing a blocking call (`PROV-04`). Quota checks are non-atomic (`PERF-01`).

### 1.5 Cache Architecture
The caching hierarchy consists of:
- **Tier 1 (Exact Match Cache):** Redis-backed key-value store using SHA-256 prompt hashing.
- **Tier 2 (Semantic Response Cache):** Vector-backed cosine similarity matching ($\ge 0.95$ threshold) with tenant scoping.
- **Tier 5 (Provider Prompt Cache):** Upstream KV-cache reuse orchestrated by `TwoZonePromptCompiler`.
- *Observed Defect:* In addition to `CACHE-01` in the gateway, semantic cache explicitly discards generation parameters (`_ = parameters`, `CACHE-02`), and agent loop embeds `Current iteration: {N}` in the system prompt prefix, completely breaking upstream prompt caching (`CACHE-03`).

### 1.6 Token Accounting
Token accounting is governed by `TokenAccounting` (`app/optimizer/token_accounting.py`) and `FinOpsService` (`app/finops/service.py`). It distinguishes 8 separate metrics (raw input, optimized input, pruned tokens, provider cached tokens, provider uncached tokens, output tokens, billed cost, and saved cost).
- *Observed Defect:* `ai_gateway.py:291` computes `raw_prompt_tokens` solely using `estimate_tokens(last_user_msg)`, omitting system prompts and prior conversation turns from raw accounting and quota deductions (`TOK-02`). The regex estimator undercounts non-English and code tokens (`TOK-01`).

### 1.7 RAG Architecture
The RAG pipeline operates a unified 10-step lifecycle. Dense vectors are stored in Qdrant; sparse inverted indices are stored in BM25. `ContextSelector` performs adaptive score thresholding, containment deduplication, and budget bounding while preserving protected entities.
- *Observed Defect:* Dense vector embeddings are generated via a SHA-256 struct unpack (`vector_store.py:12-28`), which is avalanche-sensitive and semantically blind (`RAG-01`). Floating-point retrieval scores are injected into LLM prompt context (`RAG-02`).

### 1.8 Agent Architecture
The agent platform (`app/agent/`) executes multi-step tasks using `AgentExecutionLoop`, bounded by `max_iterations = 10` and `timeout_seconds = 60.0`. Human-in-the-loop approval is enforced server-side for shell and filesystem actions.
- *Observed Defect:* Tool outputs are converted to strings with `str(tool_res.output)` and appended to short-term memory without token budgeting (`AGT-01`). Memory eviction uses naive FIFO entry popping without structured compaction (`AGT-03`). All permissible tools are serialized into full JSON parameter schemas on every iteration (`AGT-02`).

### 1.9 FinOps Architecture
The FinOps subsystem enforces trustworthy accounting through `FinOpsLedger`, `UsageReconciler`, and `BudgetManager`. It supports dual token quota and USD dollar budgets with soft warnings (80%) and hard service suspension (100%).
- *Observed Defect:* Cost calculations and model pricing catalogs are duplicated between `app/finops/pricing.py` and `app/optimizer/provider_pricing.py` with diverging write surcharge equations (`DUP-03`). Quota tracking is duplicated between `QuotaManager` and `BudgetManager` (`DUP-06`).

### 1.10 Infrastructure
The platform utilizes FastAPI, Redis 7 (caching, rate limiting, quotas, task state), and Qdrant (vector storage).
- *Observed Defect:* 9 separate modules independently instantiate their own `redis.asyncio` clients, and application shutdown in `main.py` cleans up only 3 of the 9, leaking connections (`DUP-01`). Upstream LLM calls create unpooled `httpx.AsyncClient` instances (`PROV-01`).

### 1.11 CI/CD
The repository CI/CD pipeline (`.github/workflows/ci.yml`) enforces DevSecOps scanning (Gitleaks, Bandit, pip-audit, pip-licenses), Dockerfile and workflow linting (Hadolint, Actionlint), Ruff formatting & linting, MyPy strict type checking, frontend Vitest tests, and backend Pytest runs requiring $\ge 85\%$ branch coverage and empirical AI evaluation validation ($\ge 40\%$ token reduction).
- *Observed Defect:* Local containerless test runs achieve 84.25% coverage, failing the 85% floor when live Redis/Qdrant services are not running (`CI-01`).

---

## 2. Current Repair Scope & Finding Verification

Every finding identified in the static code analysis audit was directly inspected against the live codebase. All 30 findings are **VERIFIED** with concrete code evidence.

| Finding ID | Domain | Severity | Status | Verification Evidence & Location |
| :--- | :--- | :---: | :---: | :--- |
| **CACHE-01** | Exact Cache | **CRITICAL** | **VERIFIED** | `ai_gateway.py:289, 459-463` caches solely on `last_user_msg`; `model` and `provider` default to `"default"` and `"generic"`, causing cross-model and cross-conversation collisions. |
| **PROV-02** | Provider Abstraction | **CRITICAL** | **VERIFIED** | `base.py:137` `ProviderRequest` lacks `messages` field; `ai_gateway.py:284` extracts only `last_user_msg`, flattening or dropping structured multi-turn conversation turns. |
| **TOK-02** | Token Accounting | **CRITICAL** | **VERIFIED** | `ai_gateway.py:291` computes `raw_prompt_tokens = estimate_tokens(last_user_msg)`, omitting system prompts and prior turns from accounting and quota deduction. |
| **CACHE-03** | Agent / Prompt Cache | **HIGH** | **VERIFIED** | `planner.py:113` embeds `Current iteration: {current_iteration + 1}` into `system_instruction`, mutating the static prefix on every step and invalidating provider prompt caching. |
| **PROV-01** | Async Transport / Perf | **HIGH** | **VERIFIED** | `llm_provider.py:142` instantiates `async with httpx.AsyncClient(timeout=timeout)` on every call, destroying connection pools and TLS session caches. |
| **RAG-01** | RAG Efficiency | **HIGH** | **VERIFIED** | `vector_store.py:12-28` generates dense embeddings via `hashlib.sha256(f"{text}_{i}".encode())` and `struct.unpack`, producing orthogonal vectors for semantic equivalents. |
| **AGT-01** | Agent Context | **HIGH** | **VERIFIED** | `loop.py:250-263` converts tool output to string via `str(tool_res.output)` and appends directly to memory without budgeting, pagination, or truncation. |
| **DUP-01** | Connection Management | **HIGH** | **VERIFIED** | 9 files instantiate private `_get_redis()` pools; `main.py:45-55` closes only 3 clients on shutdown, leaking sockets. |
| **PERF-01** | Concurrency / Quotas | **HIGH** | **VERIFIED** | `ai_gateway.py:172-219` checks quota via `GET` and records usage via `INCRBY` post-generation without atomic reservations, permitting quota bypass via concurrency. |
| **DUP-02** | Model Routing | **HIGH** | **VERIFIED** | `ai_gateway.py:342-350` ternary lacks `deepseek` and `groq` branches (defaults to `"openrouter"`), breaking BYOK key injection for direct DeepSeek and Groq keys. |
| **TOK-01** | Tokenization | **HIGH** | **VERIFIED** | `token_pruner.py:76` uses regex word splitting on hot paths instead of `BPETokenizer`, undercounting non-English by 30-60% and code by 15-30%. |
| **PROV-04** | Streaming | **HIGH** | **VERIFIED** | `ai_gateway.py:605-643` executes a blocking non-streaming upstream call and simulates streaming by sleeping 2ms per word. |
| **CACHE-02** | Semantic Cache | **HIGH** | **VERIFIED** | `semantic_cache.py:198` explicitly discards `parameters` (`_ = parameters`), allowing deterministic requests to collide with non-deterministic or tool-bearing requests. |
| **PERF-02** | Host Sockets | **HIGH** | **VERIFIED** | Unpooled HTTP clients and 9 independent Redis pools produce TCP socket accumulation in `TIME_WAIT` under concurrent loads. |
| **DUP-03** | FinOps Pricing | **MEDIUM** | **VERIFIED** | Parallel cost equations in `finops/pricing.py` and `optimizer/provider_pricing.py` with diverging write surcharge calculations and return types. |
| **BYOK-01** | Cryptographic Security | **MEDIUM** | **VERIFIED** | `byok.py:50-55` uses raw SHA-256 concatenation `hashlib.sha256(secret + tenant_id)` despite docstring claiming HMAC-SHA256, deviating from RFC 5869 HKDF. |
| **AGT-02** | Agent Platform | **MEDIUM** | **VERIFIED** | `planner.py:100-108` serializes all permissible tools into full JSON schemas on every step, wasting 5,000-15,000 tokens per turn. |
| **AGT-03** | Agent Memory | **MEDIUM** | **VERIFIED** | `short_term.py:28-36` uses naive FIFO entry count popping (`>50`), dropping initial user constraints and causing amnesia on long tasks. |
| **RAG-02** | Prompt Stability | **MEDIUM** | **VERIFIED** | `context_selector.py:288-291` injects floating-point retrieval scores `(Score: X.XX)` into LLM prompt text, wasting tokens and breaking prefix caching. |
| **DUP-05** | Vector Embeddings | **MEDIUM** | **VERIFIED** | `semantic_cache.py:85` uses 128-dim MD5 bag-of-words while `vector_store.py:12` uses 64-dim SHA-256 unpack, creating incompatible synthetic vector implementations. |
| **DUP-06** | Quota Governance | **MEDIUM** | **VERIFIED** | `ai_gateway.py:94` `QuotaManager` and `finops/budget.py:38` `BudgetManager` maintain parallel token quota stores. |
| **TOK-03** | Token Accounting | **MEDIUM** | **VERIFIED** | `token_accounting.py:128-157` records only physical pruning in `tokens_saved`, omitting upstream provider prompt cache discounts from primary reduction metrics. |
| **CACHE-04** | Provider Caching | **MEDIUM** | **VERIFIED** | `openai.py` does not pass `prompt_cache_key` or explicit cache breakpoints. |
| **TYPE-01** | Static Typing | **MEDIUM** | **VERIFIED** | `ai_gateway.py:100`, `byok.py:47`, `vector_store.py:51` type client handles as `Any | None`, disabling static type verification on I/O pathways. |
| **TYPE-02** | Static Typing | **MEDIUM** | **VERIFIED** | `base.py:145, 153, 160`, `planner/models.py:24`, `ai_gateway.py:86` use untyped `dict[str, Any]` for tools and schemas. |
| **CI-01** | CI/CD | **MEDIUM** | **VERIFIED** | `pyproject.toml:66` enforces 85% branch coverage; containerless local runs achieve 84.25%, failing local test verification without live Docker containers. |
| **RAG-03** | Algorithmic Perf | **LOW** | **VERIFIED** | `context_selector.py:216` performs full $O(N \log N)$ sort on candidate pool instead of top-$K$ heap selection. |
| **RAG-04** | Context Accounting | **LOW** | **VERIFIED** | `context_selector.py:294-295` estimates selected tokens strictly from raw chunk text, ignoring formatted citation headers. |
| **PERF-03** | Memory Allocations | **LOW** | **VERIFIED** | `context_selector.py:199, 293, 294` creates repeated giant string allocations during context filtering. |
| **TYPE-03** | Exception Hygiene | **LOW** | **VERIFIED** | `ai_gateway.py`, `byok.py:93`, `vector_store.py:75, 130` catch generic `Exception`, masking unexpected programming errors. |

---

## 3. Dependency Graph

Repair findings are structured according to architectural prerequisites and functional dependencies:

```text
========================================================================================
                          REPAIR DEPENDENCY TOPOLOGY
========================================================================================

    [DUP-02: Provider Resolution] ──┐
                                    ▼
[PROV-02: Structured Messages] ──> [CACHE-01: Composite Cache Key] ──> [TOK-02: Full Token Accounting]
                                    │
                                    └──────────────────────────────────> [PROV-04: Real SSE Streaming]

[DUP-01: Centralized Redis] ─────> [PERF-01: Atomic Lua Quotas] ──────> [DUP-06: Unified Budget Authority]
          │
          └──────────────────────> [PROV-01 / PERF-02: Pooled HTTP Transport]

[CACHE-03: Static System Prefix] ─> [AGT-01: Tool Output Budgeting] ───> [AGT-03: Memory Compaction]
                                                                          │
                                                                          └─> [AGT-02: Deferred Discovery]

[RAG-02: Score Stripping] ───────> [RAG-04: Header Accounting] ────────> [RAG-01: Semantic Embeddings]
                                                                          │
                                                                          └─> [DUP-05: Unified Embeddings]

[DUP-03: Consolidated Pricing] ──> [TOK-03: Segregated Ledger] ────────> [TOK-01: BPETokenizer Hot Paths]

[TYPE-01: Protocol Typing] ──────> [TYPE-02: Typed Tool Models] ───────> [TYPE-03: Narrowed Exceptions]
                                                                          │
                                                                          └─> [CI-01: Containerless Mocks]
```

### 3.1 Critical Path (Must Be Repaired First)
1. **`DUP-02` (Provider Resolution):** Must be resolved before caching or streaming fixes so that provider names and models resolve consistently across all endpoints.
2. **`PROV-02` (Structured Multi-Turn Messages):** Must be added to `ProviderRequest` before `CACHE-01` because exact cache hashing requires access to the structured message sequence.
3. **`CACHE-01` (Composite Exact Cache Key):** Prerequisite for multi-model inference correctness and preventing cross-tenant response pollution.
4. **`TOK-02` (Request Token Accounting):** Prerequisite for quota deduction and billing truth.

### 3.2 Independent Workstreams (Can Be Repaired in Parallel or Sequentially)
- **Infrastructure:** `DUP-01` (Centralized Redis) -> `PROV-01` (Pooled HTTP) -> `PERF-01` (Atomic Quotas).
- **Agent Platform:** `CACHE-03` (Static Prefix) -> `AGT-01` (Tool Output Budgeting) -> `AGT-03` (Memory Compaction).
- **RAG Subsystem:** `RAG-02` (Score Stripping) -> `RAG-04` (Header Accounting).
- **FinOps:** `DUP-03` (Consolidated Pricing) -> `TOK-03` (Segregated Ledger).

### 3.3 Deferred Findings (Requires Architecture Decisions or Migration Strategy)
- **`RAG-01` / `DUP-05` (Dense Vector Embeddings):** Replacing SHA-256 with genuine embeddings alters vector collection dimensionality in Qdrant (64-dim to 768/1536-dim), requiring collection re-indexing.
- **`BYOK-01` (HKDF Key Derivation):** Changing key derivation alters ciphertext decryption, requiring an automated key re-encryption migration for existing tenants.
- **`AGT-04` (Programmatic Tool Calling):** Requires secure Docker/Wasm sandbox environment.

---

## 4. Risk Map

| Risk Category | Key Vulnerabilities & Sources | Impact | Remediation Safeguard |
| :--- | :--- | :--- | :--- |
| **Correctness Risks** | `CACHE-01` (key collapse), `PROV-02` (dropped history), `PROV-04` (false streaming) | Cross-model answer leakage, amnesia in multi-turn chat, poor UI responsiveness | Composite SHA-256 cache key, structured message protocol, native adapter streaming |
| **Security Risks** | `CACHE-01` (cross-tenant prompt hit), `BYOK-01` (raw SHA-256 derivation), `PERF-01` (quota bypass) | Data leakage between tenants, non-standard cryptography, unmetered resource abuse | Tenant ID in cache hash, RFC 5869 HKDF derivation, atomic Redis token reservation |
| **Data / Accounting Risks** | `TOK-02` (omitted prompt tokens), `TOK-01` (multilingual undercounting), `DUP-03` (pricing drift) | FinOps reports undercount usage by up to 95%, tenant quota slippage | Full-envelope token accounting, BPE tokenizer migration, unified pricing catalog |
| **Performance Risks** | `PROV-01` (per-request HTTP client), `DUP-01` (9 Redis pools), `CACHE-03` (broken prompt caching) | 50-150ms unnecessary latency, socket exhaustion, 0% agent prompt cache hit rate | Shared `httpx.AsyncClient` pool, centralized Redis manager, static system instructions |
| **Migration Risks** | `RAG-01` (embedding dimension change), `BYOK-01` (ciphertext re-encryption) | Qdrant collection incompatibility, unreadable existing BYOK keys | Collection migration script, versioned ciphertext prefix fallback |
| **Regression Risks** | Modifying `ProviderRequest` or `ai_gateway.py` breaks existing passing tests | Failing 311 unit tests or reducing 48.74% token reduction benchmark | Test-first repair with focused regression tests before implementation |

---

## 5. Repair Workstreams Execution Plan

In accordance with Section 5 of the Bootstrap specification, repair execution is planned into five progressive workstreams:

```text
+---------------------------------------------------------------------------------------+
| WORKSTREAM R1: Request & Inference Correctness                                         |
| Target Findings: CACHE-01, PROV-02, TOK-02, DUP-02                                    |
| Objective      : Guarantee multi-turn chat fidelity, composite exact cache isolation,  |
|                  canonical provider resolution, and full request token accounting.     |
+---------------------------------------------------------------------------------------+
                                           |
                                           v
+---------------------------------------------------------------------------------------+
| WORKSTREAM R2: Infrastructure Correctness                                             |
| Target Findings: PROV-01, DUP-01, PERF-01, DUP-06                                     |
| Objective      : Centralize Redis connection management, pool persistent HTTP clients, |
|                  and implement atomic token quota reservation via Redis Lua script.   |
+---------------------------------------------------------------------------------------+
                                           |
                                           v
+---------------------------------------------------------------------------------------+
| WORKSTREAM R3: Streaming & Agent Correctness                                          |
| Target Findings: PROV-04, CACHE-03, AGT-01, AGT-03                                    |
| Objective      : True token-by-token SSE streaming, byte-stable agent system prompt,  |
|                  tool output budgeting (<=2,000 tokens), and structured memory safety. |
+---------------------------------------------------------------------------------------+
                                           |
                                           v
+---------------------------------------------------------------------------------------+
| WORKSTREAM R4: RAG Correctness & Prompt Stability                                     |
| Target Findings: RAG-02, RAG-04, RAG-01, DUP-05                                       |
| Objective      : Strip retrieval scores from prompt context, exact context accounting,|
|                  and introduce pluggable embedding interface with migration plan.      |
+---------------------------------------------------------------------------------------+
                                           |
                                           v
+---------------------------------------------------------------------------------------+
| WORKSTREAM R5: Structural, Type, & Exception Repair                                   |
| Target Findings: TYPE-01, TYPE-02, TYPE-03, DUP-03, TOK-01, CI-01, BYOK-01           |
| Objective      : Protocol typing for client handles, typed tool schemas, narrowed     |
|                  exceptions, unified pricing catalog, and containerless mock fixtures.|
+---------------------------------------------------------------------------------------+
```

---

## 6. Do Not Implement Compliance

In strict compliance with REPAIR-00 Section 6:
- **Zero source code files were edited** (`backend/app/` is untouched).
- **Zero refactoring was performed.**
- **Zero tests were modified or deleted.**
- **Zero CI workflows were altered.**
- **Zero external dependencies were added.**

---

## Final Output

### CURRENT STATE
- **Baseline:** 311 tests passing, 0 Ruff errors across 184 files, 0 MyPy errors across 141 modules under strict mode, 0 Bandit security issues across 19,636 LOC.
- **Empirical Optimization:** 48.74% portfolio net token reduction verified with zero fact loss.
- **Branch Coverage:** 84.25% in containerless local environment (fails 85% floor due to unexercised Redis/Qdrant connection fallback branches per finding `CI-01`).
- **Defects:** 30 verified findings cataloged and confirmed live in repository source.

### REPAIR PRIORITIES
1. **P0 (Critical Correctness):** `CACHE-01` (Composite cache key), `PROV-02` (Structured conversation messages), `TOK-02` (Full request token accounting), `DUP-02` (Canonical model routing).
2. **P1 (High Stability & Efficiency):** `CACHE-03` (Agent prefix stability), `PROV-01` (Pooled HTTP transport), `DUP-01` (Centralized Redis manager), `PERF-01` (Atomic Lua quotas), `PROV-04` (Real SSE streaming).
3. **P2 (Agent & RAG Integrity):** `AGT-01` (Tool output budgeting), `RAG-02` (Prompt score stripping), `TOK-01` (BPE tokenizer hot paths), `AGT-03` (Memory compaction).
4. **P3 (Structural & Long-Term):** `DUP-03` (FinOps pricing consolidation), `TYPE-01` / `TYPE-02` (Protocol & schema typing), `CI-01` (Containerless test mocks), `RAG-01` (Semantic embeddings migration), `BYOK-01` (HKDF migration).

### DEPENDENCY GRAPH
- `DUP-02` -> `PROV-02` -> `CACHE-01` -> `TOK-02` -> `PROV-04`.
- `DUP-01` -> `PROV-01` / `PERF-01` -> `DUP-06`.
- `CACHE-03` -> `AGT-01` -> `AGT-03` -> `AGT-02`.
- `RAG-02` -> `RAG-04` -> `RAG-01` -> `DUP-05`.
- `DUP-03` -> `TOK-03` -> `TOK-01`.

### BLOCKERS
- None for starting R1. All prerequisites for audit verification are satisfied.

### NEXT TASK
**`docs/repair/R1/REPAIR-01 — Baseline & Audit Verification.md`**  
The next task will perform deep, caller-level verification and downstream impact analysis for each finding, creating `docs/ai-engineering/state/repair-findings.md` prior to any code modifications.
