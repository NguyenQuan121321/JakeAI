# JAKEAI REPAIR — REPAIR-03 TO REPAIR-04 HANDOFF

> **Execution Date:** 2026-09-08  
> **Source Phase:** REPAIR-03 — Correctness Repair Worker (`COMPLETED`)  
> **Target Phase:** REPAIR-04 — Infrastructure Repair Worker (`READY`)  
> **Target Task:** `TASK-R2-01: Centralized Redis Connection Lifecycle Manager` (`DUP-01`, `PERF-02`)  
> **Compliance Standard:** JakeAI Universal AI Engineering Worker & Repair Master Prompt  

---

## 1. Handoff Overview

Phase **REPAIR-03 (Correctness Repair Worker)** has completed all assigned tasks under **Workstream R1**:
- `TASK-R1-01` (`DUP-02`): Canonical Model-to-Provider Resolution via `ProviderRegistry`.
- `TASK-R1-02` (`PROV-02`): Structured Multi-Turn Messages (`list[ChatMessage]`) in `ProviderRequest` across all 6 provider adapters.
- `TASK-R1-03` (`CACHE-01`, `CACHE-02`, `CACHE-04`): Composite Exact Response Cache Key Isolation with parameters (system hash, history hash, tools hash, temperature).
- `TASK-R1-04` (`TOK-02`, `TOK-03`): Full-Envelope Model-Visible Token Accounting & Ledger Separation.

The entire test suite passes cleanly: **325 passed, 0 failed**, zero lint issues, zero type errors on all modified modules.

Phase **REPAIR-04 (Infrastructure Repair Worker)** is now unblocked and ready for immediate execution on **Workstream R2 (Infrastructure Correctness)**.

---

## 2. Invariants Restored and Active in the Codebase

The following architectural invariants are now guaranteed and active:

1. **Authoritative Model-to-Provider Resolution:**
   - Any model string passed to the gateway or core LLM caller routes through `get_provider_registry().resolve_provider_name_for_model(model_name)`.
   - Hardcoded substring checks in `ai_gateway.py` and `llm_provider.py` are eliminated.
   - Provider resolution emits structured log `provider_resolved`.

2. **Native Multi-Turn Conversation Forwarding:**
   - `ProviderRequest.messages` carries structured `list[ChatMessage]` (`role`, `content`, `name`).
   - Adapters for OpenAI, Anthropic, Gemini, Groq, DeepSeek, and OpenRouter natively serialize structured turns into vendor HTTP payloads, preserving role integrity (`user`, `assistant`, `tool`, `model`).
   - Legacy single `prompt: str` fallback is preserved for backward compatibility.

3. **Composite Cache Partitioning:**
   - Exact cache keys are derived from:
     $$\text{Key} = \text{SHA256}(\text{tenant\_id} \parallel \text{provider} \parallel \text{model} \parallel \text{version} \parallel \text{parameters\_json} \parallel \text{prompt\_nfc})$$
   - Parameter dictionary contains `temperature`, `system_hash` (Zone 1 static prefix fingerprint), `history_hash` (SHA-256 of prior non-system turns), and `tools_hash`.
   - Redis exact match, in-memory exact match, and semantic vector match strictly enforce tenant, model, provider, and parameter parity.

4. **Truthful Full-Envelope Token Accounting:**
   - `raw_prompt_tokens` is measured over all model-visible messages, system prompts, and tool declarations.
   - `TokenUsageRecord` segregates `physical_pruned_tokens` (client-side context reduction) from `provider_cached_tokens` (upstream KV prompt cache discounts).
   - Quota deductions meter the true full model-visible envelope.

---

## 3. Durable Guidance for Phase REPAIR-04 Engineer

When executing Phase **REPAIR-04**, the engineer must adhere to the following:

### Core Scope: Workstream R2 (Infrastructure Correctness)
1. **TASK-R2-01 (`DUP-01`, `PERF-02`): Centralized Redis Connection Lifecycle Manager**
   - **Target:** Create `backend/app/core/redis.py` with `RedisConnectionManager`.
   - **Problem:** Currently, 9 separate modules (`semantic_cache.py`, `ai_gateway.py`, `rate_limiter.py`, `byok.py`, `vector_store.py`, etc.) lazily instantiate uncoordinated `aioredis.from_url` clients. During shutdown, only 3 disconnect, leaking sockets.
   - **Prerequisite Invariant:** Do not break the cache operations repaired in `TASK-R1-03`. The new `RedisConnectionManager` must provide client connections to `SemanticCacheManager` and `QuotaManager` smoothly.
   - **Lifecycle:** Bind lifecycle strictly to FastAPI `lifespan` in `app/main.py`.

2. **TASK-R2-02 (`PROV-01`, `PERF-02`): Application-Scoped Pooled HTTP Client**
   - **Target:** Create `backend/app/core/http_client.py` with `SharedHTTPClientPool`.
   - **Problem:** `llm_provider.py:142` currently opens a new `httpx.AsyncClient()` on every inference call, causing socket churn and connection overhead under load.
   - **Prerequisite Invariant:** Provider adapters rely on `call_upstream_llm` and `call_upstream_llm_detailed`. The pooled client must maintain timeout, retry, and proxy compatibility.

3. **TASK-R2-03 (`PERF-01`): Atomic Concurrency Quota Reservation via Redis Lua Script**
   - **Target:** Update `QuotaManager` in `backend/app/services/ai_gateway.py` or move to `app/core/quota.py`.
   - **Problem:** Quota checks and updates in `QuotaManager` currently perform separate `get` and `incrby` operations, creating race conditions under high concurrent tenant requests.
   - **Prerequisite Invariant:** `QuotaManager.record_usage` and `QuotaManager.check_quota` must maintain exact accounting of `pruned_prompt_tokens` and full envelopes established in `TASK-R1-04`.

### Verification Mandate:
- Run unit regression tests in `backend/tests/unit/` first.
- Run full test suite: `uv run --project backend pytest`.
- Verify benchmarks: `uv run --project backend pytest backend/tests/evals/test_portfolio_benchmark.py backend/tests/evals/test_token_benchmark.py`.
- Run linter and type checker: `uv run --project backend ruff check backend/` and `uv run --project backend mypy backend/app`.
