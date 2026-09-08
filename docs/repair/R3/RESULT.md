# JAKEAI REPAIR — REPAIR-03: CORRECTNESS REPAIR RESULT

> **Execution Date:** 2026-09-08  
> **Phase:** REPAIR-03 — Correctness Repair Worker  
> **Workstream:** Workstream R1 — Request / Inference Correctness  
> **Status:** COMPLETED  
> **Worker:** Correctness Repair Engineer (JakeAI Diagnostic & Repair Engine)  
> **Compliance Standard:** JakeAI Universal AI Engineering Worker & Repair Master Prompt  

---

## 1. Executive Summary of Work Completed

In session **REPAIR-03**, the engineering worker successfully executed the entire **Workstream R1 (Request / Inference Correctness)** comprising tasks `TASK-R1-01` through `TASK-R1-04`.

Following the invariant-first engineering methodology:
1. Every defect was isolated and proven with a failing unit regression test prior to repair.
2. The minimal architecture-consistent changes were implemented across the AI Gateway, provider abstraction, semantic cache, and token accounting ledger.
3. Zero existing tests were modified or deleted; all baseline tests passed without regressions.
4. Test suite expanded from 311 tests to **325 tests (100% passing)**.
5. All AI benchmarks passed:
   - **Portfolio Net Token Reduction:** **48.74%** (requirement $\ge 40\%$).
   - **Quality Score:** **1.0000** (requirement $\ge 0.95$).
   - **Fact Loss:** **0.0000** (requirement $0.0$).
   - **Token Optimization Net Reduction:** **63.51%** (requirement $\ge 40\%$).
6. Linting (`ruff check backend/`) and strict static type checking (`mypy`) passed with **zero errors**.

---

## 2. Detailed Task-by-Task Repair Breakdown

### TASK-R1-01: Canonical Model-to-Provider Resolution (`DUP-02`)
- **Defect & Root Cause:** `ai_gateway.py` (lines 342–355) and `llm_provider.py` (lines 65–105) employed crude, out-of-sync substring heuristics (e.g. `"llama" in model.lower() -> "openrouter"`, `"deepseek" in model.lower() -> "openrouter"`). This bypassed `ProviderRegistry.resolve_provider_name_for_model()`, routed DeepSeek and Groq models to OpenRouter, misallocated BYOK keys, and broke provider caching.
- **Invariant Restored:** Model-to-provider resolution MUST route exclusively through `get_provider_registry().resolve_provider_name_for_model(model_name)`. Any known model (`deepseek-*`, `llama-3.3-*`, `gemini-*`, `gpt-*`, `claude-*`) resolves to its canonical provider adapter.
- **Regression Test:** `backend/tests/unit/test_ai_gateway_routing.py`
  - Verified `deepseek-chat` resolves to `"deepseek"` and queries `"deepseek"` BYOK key.
  - Verified `llama-3.3-70b-versatile` resolves to `"groq"` and queries `"groq"` BYOK key.
- **Changes Applied:**
  - `backend/app/services/ai_gateway.py`: Replaced ternary check with `provider = get_provider_registry().resolve_provider_name_for_model(request.model)` and emitted structured log `provider_resolved`.
  - `backend/app/core/llm_provider.py`: Replaced ad-hoc mapping in `call_upstream_llm` and `call_upstream_llm_detailed` with canonical registry resolution.
- **Verification Status:** **PASS** (3/3 tests in `test_ai_gateway_routing.py`).

---

### TASK-R1-02: Structured Multi-Turn Messages in ProviderRequest (`PROV-02`)
- **Defect & Root Cause:** `ProviderRequest` lacked a structured `messages` field (`messages: list[ChatMessage] | None = None`). The AI Gateway extracted only `last_user_msg = next(m.content for m in reversed(request.messages) if m.role == "user")` and flattened all conversation turns into a single string. Provider adapters had no native multi-turn message serializer, destroying conversational context and role boundaries.
- **Invariant Restored:** `ProviderRequest` accepts `messages: list[ChatMessage] | None = None`. When `messages` is provided, all provider adapters preserve native role designations (`user`, `assistant`, `tool`, `model`) in vendor wire payloads.
- **Regression Test:** `backend/tests/unit/test_provider_multiturn.py`
  - Dispatched 3-turn history (`user` -> `assistant` -> `user`) across all 6 provider adapters (`openai`, `anthropic`, `gemini`, `groq`, `deepseek`, `openrouter`).
  - Proved native serialization: Gemini (`contents` array with roles `user` and `model`), Anthropic (`messages` array with roles `user` and `assistant`), OpenAI/Groq/DeepSeek/OpenRouter (`messages` array with system instruction and roles).
- **Changes Applied:**
  - `backend/app/providers/base.py`: Defined `ChatMessage` model, added `messages: list[ChatMessage] | None = None` to `ProviderRequest`, and added `turn_count: int = Field(default=1)` to `ProviderCacheTelemetry`.
  - `backend/app/core/llm_provider.py`: Threaded `messages` through `call_upstream_llm` and `call_upstream_llm_detailed`.
  - Provider adapters (`openai.py`, `anthropic.py`, `gemini.py`, `groq.py`, `deepseek.py`, `openrouter.py`): Implemented native `request.messages` serialization with role mapping, falling back to legacy single-prompt behavior when `request.messages` is absent.
  - `backend/app/providers/openai.py`: Passed `prompt_cache_key` when static prefix hash is available (`CACHE-04`).
- **Verification Status:** **PASS** (6/6 tests in `test_provider_multiturn.py`).

---

### TASK-R1-03: Composite Exact Response Cache Key Isolation (`CACHE-01`, `CACHE-02`, `CACHE-04`)
- **Defect & Root Cause:** `ai_gateway.py` computed cache keys purely on `last_user_msg` (`cache_mgr.get(last_user_msg)`), completely discarding model, provider, temperature, system instructions, and preceding turns. In `semantic_cache.py:198`, `_ = parameters` explicitly discarded execution parameters. This caused cross-model collisions (e.g. Claude request returning GPT-4 response), system instruction leaks, and conversation history cross-talk.
- **Invariant Restored:** Different semantic request identities MUST produce distinct exact cache keys:
  $$\text{Key} = \text{SHA256}(\text{tenant\_id} \parallel \text{provider} \parallel \text{model} \parallel \text{version} \parallel \text{parameters\_json} \parallel \text{prompt\_nfc})$$
  Where `parameters` contains `temperature`, `system_hash`, `history_hash`, and `tools_hash`.
- **Regression Test:** `backend/tests/unit/test_exact_cache_isolation.py`
  - Verified different models with identical prompt produce cache MISS (`test_exact_cache_model_isolation`).
  - Verified different system instructions with identical query produce cache MISS (`test_exact_cache_system_instruction_isolation`).
  - Verified different preceding conversation histories produce cache MISS (`test_exact_cache_conversation_history_isolation`).
- **Changes Applied:**
  - `backend/app/optimizer/semantic_cache.py`:
    - Updated `_compute_hash` to include normalized sorted JSON of `parameters`.
    - Removed `_ = parameters` discard in `get()`. Enforced parameter, model, and provider matching across Redis tier, in-memory tier, and vector tier.
    - Updated `set()` to pass `parameters` into `_compute_hash`.
  - `backend/app/services/ai_gateway.py`:
    - Added `_extract_request_cache_context()` to extract `last_user_msg`, calculate raw envelope tokens, compile two-zone prefix hash (`system_hash`), compute SHA-256 of preceding history turns (`history_hash`), and hash tools (`tools_hash`).
    - Updated `chat_completions` and `chat_completions_stream` to pass `model=request.model`, `provider=provider`, and `parameters=cache_params` into `cache_mgr.get()` and `cache_mgr.set()`.
- **Verification Status:** **PASS** (3/3 tests in `test_exact_cache_isolation.py`).

---

### TASK-R1-04: Full-Envelope Model-Visible Token Accounting (`TOK-02`, `TOK-03`)
- **Defect & Root Cause:** `ai_gateway.py:291` calculated `raw_prompt_tokens = estimate_tokens(last_user_msg)`. A request with a 1,000-token system instruction, 500-token conversation history, and 50-token query was accounted as only 50 tokens, allowing tenants to evade up to 95% of quota consumption. Furthermore, `token_accounting.py` did not record `physical_pruned_tokens` or distinguish client-side pruning savings from Layer B provider prompt cache discounts.
- **Invariant Restored:** `raw_prompt_tokens` must account for all model-visible tokens:
  $$\text{Raw Prompt Tokens} = \text{tokens}(\text{system}) + \sum_{m \in \text{messages}} \text{tokens}(m) + \text{tokens}(\text{tools})$$
  Tenant quota deductions and FinOps ledgers meter the full model-visible prompt envelope. Physical pruning savings (`physical_pruned_tokens`) and provider cache savings (`provider_cached_tokens`) are segregated in distinct ledger fields.
- **Regression Test:** `backend/tests/unit/test_token_accounting_envelope.py`
  - Dispatched request with ~1,000-token system prompt, ~550-token conversation history, and ~50-token query.
  - Verified `usage["prompt_tokens"] >= 1500` and `quota_mgr.record_usage` called with full envelope tokens.
  - Verified `TokenAccounting.record_transaction` segregates `physical_pruned_tokens == 0` from `provider_cached_tokens == 5000` with `tokens_saved >= 5000` (`test_token_accounting_provider_cache_savings_segregation`).
- **Changes Applied:**
  - `backend/app/optimizer/token_accounting.py`: Added `physical_pruned_tokens`, `response_cache_avoided_tokens`, `effective_billed_tokens` to `TokenUsageRecord`. Added optional `physical_pruned_tokens` and `response_cache_avoided_tokens` parameters to `record_transaction()`.
  - `backend/app/services/ai_gateway.py`:
    - Computed `raw_prompt_tokens = max(1, sum(estimate_tokens(m.content) for m in request.messages) + tool_tokens)`.
    - Computed context pruning savings: `context_pruning_savings = max(0, optimized_result.raw_tokens - optimized_result.optimized_tokens)`.
    - Calculated `pruned_prompt_tokens = max(1, raw_prompt_tokens - context_pruning_savings)`.
    - Passed `raw_prompt_tokens` and `pruned_prompt_tokens` to `record_transaction`, `quota_mgr.record_usage`, FinOps ledger, and response usage payload.
- **Verification Status:** **PASS** (2/2 tests in `test_token_accounting_envelope.py`).

---

## 3. Status of Acceptance Criteria

| Workstream Task | Acceptance Criterion | Status | Verification Evidence |
| :--- | :--- | :---: | :--- |
| **TASK-R1-01** | Substring checks removed; `get_provider_registry().resolve_provider_name_for_model` used | **MET** | `ai_gateway.py:342-352`, `llm_provider.py:65-105` |
| **TASK-R1-01** | `deepseek-chat` and `llama-3.3-70b-versatile` resolve to `deepseek` and `groq` | **MET** | `test_ai_gateway_routing.py` passed |
| **TASK-R1-01** | Existing gateway and routing tests pass | **MET** | 44 tests passed in gateway/provider suites |
| **TASK-R1-02** | `ProviderRequest` contains `messages: list[ChatMessage] \| None = None` | **MET** | `app/providers/base.py:145` |
| **TASK-R1-02** | All 6 provider adapters serialize `messages` with native role mappings | **MET** | `test_provider_multiturn.py` (6 passed) |
| **TASK-R1-02** | `ai_gateway.py` forwards full `request.messages` to upstream providers | **MET** | `ai_gateway.py:387, 401, 600` |
| **TASK-R1-03** | Exact cache keys include composite envelope (model, provider, parameters, system, history) | **MET** | `test_exact_cache_isolation.py` (3 passed) |
| **TASK-R1-03** | `semantic_cache.py` incorporates parameters into Redis, memory, and vector matching | **MET** | `semantic_cache.py:82-89, 231-236, 263-268, 295-298` |
| **TASK-R1-03** | `openai.py` passes `prompt_cache_key` when static prefix hash is available | **MET** | `openai.py:112-115` |
| **TASK-R1-04** | `raw_prompt_tokens` accounts for full envelope (system + history + query + tools) | **MET** | `test_token_accounting_envelope.py` passed ($\ge 1500$ tokens) |
| **TASK-R1-04** | `token_accounting.py` separates `physical_pruned_tokens` and `provider_cached_tokens` | **MET** | `token_accounting.py:31, 147-154` |
| **TASK-R1-04** | Portfolio benchmark maintains quality $\ge 0.95$ and net reduction $\ge 40\%$ | **MET** | Quality 1.0000, Net Token Reduction 48.74% |

---

## 4. Created and Modified Files

### Files Created:
1. `backend/tests/unit/__init__.py`: Unit test package initialization.
2. `backend/tests/unit/test_ai_gateway_routing.py`: Canonical provider resolution regression tests (`TASK-R1-01`).
3. `backend/tests/unit/test_provider_multiturn.py`: Multi-turn serialization regression tests for 6 adapters (`TASK-R1-02`).
4. `backend/tests/unit/test_exact_cache_isolation.py`: Composite cache isolation regression tests (`TASK-R1-03`).
5. `backend/tests/unit/test_token_accounting_envelope.py`: Full-envelope token accounting regression tests (`TASK-R1-04`).

### Files Modified:
1. `backend/app/services/ai_gateway.py`:
   - Canonical provider resolution before cache check.
   - `_extract_request_cache_context()` for composite cache params and full-envelope token counting.
   - Composite parameters passed to `cache_mgr.get()` and `cache_mgr.set()`.
   - Full envelope tokens used in `TokenAccounting.record_transaction()`, `quota_mgr.record_usage()`, and response usage.
   - Explicit `__all__` export to preserve typing and lint compliance.
2. `backend/app/core/llm_provider.py`:
   - Canonical model resolution via `ProviderRegistry`.
   - Forwarding `messages: list[ChatMessage] | None = None` in `call_upstream_llm` and `call_upstream_llm_detailed`.
3. `backend/app/providers/base.py`:
   - Defined `ChatMessage` class (`role`, `content`, `name`).
   - Added `messages: list[ChatMessage] | None = None` to `ProviderRequest`.
   - Added `turn_count: int = Field(default=1)` to `ProviderCacheTelemetry`.
4. `backend/app/providers/openai.py`:
   - Structured multi-turn message serialization into `payload["messages"]`.
   - Added `prompt_cache_key` injection from static prefix hash.
5. `backend/app/providers/anthropic.py`:
   - Structured multi-turn message serialization into `payload["messages"]` with system instruction extraction.
6. `backend/app/providers/gemini.py`:
   - Structured multi-turn message serialization into `payload["contents"]` mapping `assistant` -> `model`.
7. `backend/app/providers/groq.py`:
   - Structured multi-turn message serialization with native roles.
8. `backend/app/providers/deepseek.py`:
   - Structured multi-turn message serialization with native roles.
9. `backend/app/providers/openrouter.py`:
   - Structured multi-turn message serialization with native roles.
10. `backend/app/optimizer/semantic_cache.py`:
    - Updated `_compute_hash` to include normalized sorted JSON `parameters`.
    - Removed parameter discard in `get()`. Enforced composite parameter match in Redis, memory, and semantic tiers.
    - Updated `set()` to pass `parameters` into hash computation.
11. `backend/app/optimizer/token_accounting.py`:
    - Added `physical_pruned_tokens`, `response_cache_avoided_tokens`, `effective_billed_tokens` to `TokenUsageRecord`.
    - Segregated physical context pruning from provider prompt cache discounts in `record_transaction()`.

---

## 5. Test and Verification Evidence

| Verification Suite | Command | Result | Summary Output |
| :--- | :--- | :---: | :--- |
| **New Unit Regressions** | `uv run --project backend pytest backend/tests/unit/` | **PASS** | 14 passed in 8.75s |
| **Subsystem Tests** | `uv run --project backend pytest backend/tests/test_commercial_services.py backend/tests/test_provider_prompt_caching.py backend/tests/test_semantic_cache.py backend/tests/test_gateway.py` | **PASS** | 35 passed in 9.46s |
| **AI Evaluation Benchmark** | `uv run --project backend pytest backend/tests/evals/test_portfolio_benchmark.py backend/tests/evals/test_token_benchmark.py` | **PASS** | 5 passed; 48.74% Net Reduction, Quality 1.0000, 63.51% Token Opt |
| **Full Pytest Suite** | `uv run --project backend pytest` | **PASS** | **325 passed**, 1 warning in 109.40s |
| **Linter Check** | `uv run --project backend ruff check backend/` | **PASS** | `All checks passed!` |
| **Static Type Check** | `uv run --project backend mypy backend/app/services/ai_gateway.py backend/app/providers backend/app/optimizer backend/app/core/llm_provider.py` | **PASS** | `Success: no issues found in 27 source files` |

---

## 6. Remaining Issues, Risks, and Blockers

- **Zero blockers for Phase R4:** Workstream R1 is completely verified and sealed.
- **Identified Infrastructure Risks (to be addressed in Phase R4):**
  - Finding `DUP-01`: Multiple uncoordinated Redis connection pools across 9 modules remain unmanaged during lifespan. Addressed by `TASK-R2-01`.
  - Finding `PROV-01`: Upstream HTTP calls in `llm_provider.py` spawn transient `httpx.AsyncClient` instances instead of reusing a shared pool. Addressed by `TASK-R2-02`.
  - Finding `PERF-01`: Quota checks and token reservations in `QuotaManager` remain non-atomic under high concurrency. Addressed by `TASK-R2-03`.

---

## 7. Next Task

- **Phase:** **`REPAIR-04 — Infrastructure Repair Worker`**
- **Workstream:** **`Workstream R2 — Infrastructure Correctness`**
- **Initial Task:** **`TASK-R2-01: Centralized Redis Connection Lifecycle Manager`** (`DUP-01`, `PERF-02`)
- **Status:** **`READY`**
