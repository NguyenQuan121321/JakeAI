# R-FUNC-04 — Provider Behavior — Execution Result

**JakeAI Universal AI Engineering Worker**
**Verification Target**: `R-FUNC-04 — Provider Behavior`
**Baseline Commit**: `99144cb` (`main`, PR #36 merge, CI green)
**Working Branch**: `chore/r-func-04-provider-behavior`
**Execution Mode**: STRICT RIGHT Verification & Correction
**Date**: September 12, 2026
**Final Status**: **PASSED (Verified, 4 Defects Resolved, 1 Finding Dispositioned, 0 Regressions, GitHub CI GREEN — run 34722099787)**

---

## 1. Executive Summary

In strict accordance with `.agents/engineering/RIGHT/00 — Right Master.md` and `.agents/engineering/RIGHT/01 — Functional Correctness/R-FUNC-04 — Provider Behavior.md`, this report documents the verification of JakeAI's LLM provider abstraction: provider/model resolution, request transformation, credential selection, success responses, streaming, error normalization (401/403/429/5xx, timeout, malformed response), provider unavailability, and failover.

Verification exercised the complete production provider execution paths:

- **Dispatch path**: `call_upstream_llm_detailed` / `call_upstream_llm` (`app/core/llm_provider.py`) → workload classification → `ModelRouter.route` → per-provider credential resolution (BYOK → platform key) → `FailoverManager.execute_with_failover` → `LLMProvider.complete` (real `httpx.AsyncClient`).
- **Streaming path**: `call_upstream_llm_stream` → `FailoverManager.stream_with_failover` → `LLMProvider.stream` → `StreamChunk` deltas → `JakeAIBackend.generate_stream` (agent-run SSE).
- **Adapter path**: `OpenAIAdapter`, `AnthropicAdapter`, `GeminiAdapter`, `GroqAdapter`, `DeepSeekAdapter`, `OpenRouterAdapter`, `LocalModelAdapter` — payload construction, header/credential injection, SSE parsing, telemetry extraction, error normalization.

Testing was performed at the **provider-contract boundary**: the real `httpx.AsyncClient` stack driven against controlled HTTP doubles (`httpx.MockTransport`) that emulate real provider contracts (OpenAI-compatible SSE, Anthropic Messages SSE, Gemini Generative Language), including deliberately injected failure modes. A mocked transport proves the adapter/failover/dispatcher code paths exactly; it does **not** prove live upstream availability (marked NOT VERIFIED below, per the Real-vs-Mock Rule).

During verification, **4 confirmed defects** were found, reproduced at the correct boundary (RED), fixed with minimal correct changes, and locked with regression tests (GREEN):

1. `FINDING-01` (**CRITICAL**): `call_upstream_llm_stream` read `chunk.delta` — a non-existent attribute of `StreamChunk` (the real field is `delta_text`). Every chunk raised `AttributeError`, which was swallowed by a broad `except Exception`, so **all agent-run provider streaming yielded zero tokens** and silently degraded to non-streaming full-text fallback.
2. `FINDING-02` (**HIGH**): The six cloud adapters leaked raw `httpx.TimeoutException` / `httpx.TransportError` on network-level failures instead of typed `ProviderError`s. Inside `FailoverManager` these were misclassified as `NON_RETRYABLE` (no retry), and direct callers received untyped exceptions. Only `LocalModelAdapter` normalized them.
3. `FINDING-03` (**HIGH**): A provider responding HTTP 200 with an unparseable body raised a raw `json.JSONDecodeError` out of the adapters (untyped, misclassified) instead of a normalized provider-unavailable error.
4. `FINDING-04` (**HIGH**): Under production defaults (`max_retries_per_provider=2`, `max_total_attempts=3`), a primary provider persistently failing with a *retryable* error consumed the entire total attempt ceiling, so **cross-provider failover was unreachable for exactly the provider-down scenarios the fallback chain exists for**.

The task's acceptance criteria are now proven by tests: no cross-provider credential reuse (wire-level), the selected provider/model is actually invoked (wire-level), real streaming remains incremental, and failures are correctly classified.

---

## 2. Scope & Verified Inventory

| Layer | Component | Verified Capability |
|---|---|---|
| Provider contract | `app/providers/base.py` | `LLMProvider` protocol (`complete`/`stream`/`capabilities`), `ProviderRequest`/`ProviderResponse`/`StreamChunk` contracts, `format_openai_chat_messages` / `format_anthropic_chat_messages` / `format_gemini_chat_contents` transformation, `ModelCapabilityCatalog` explicit capabilities. |
| Registry / resolution | `app/providers/registry.py` | Provider registration, model→provider name resolution (`claude→anthropic`, `gpt/o1/o3→openai`, `gemini→gemini`, `llama→groq`, `deepseek→deepseek`, `x/→openrouter`, `local/ollama→local`), preferred-provider override, unknown-model fallback. |
| Adapters (6 cloud + local) | `app/providers/{openai,anthropic,gemini,groq,deepseek,openrouter,local}.py` | URL, payload (model, messages, temperature, max_tokens, tools, response_format), credential injection (BYOK tenant key → platform key → typed auth rejection), success parsing, usage extraction, SSE parsing, error normalization. |
| Error taxonomy | `app/providers/errors.py` | `normalize_provider_error` classification matrix, secret-redaction invariant, typed error categories. |
| Routing | `app/routing/router.py` | Multi-objective routing, hard pre-filters (allowed/disallowed providers, context window, capabilities, cost budget, quality floor), fallback-chain construction. |
| Failover | `app/routing/failover.py` | Bounded retries, backoff with jitter, total attempt ceiling, cross-provider fallback, per-candidate credential resolution, failover metrics. |
| Dispatcher | `app/core/llm_provider.py` | `call_upstream_llm_detailed`, `call_upstream_llm`, `call_upstream_llm_stream`; workload classification → routing → BYOK/platform credential resolution → failover execution; provider metrics recording. |
| Consumer | `app/agent/backends/jakeai.py` | `JakeAIBackend.generate/generate_stream` — agent-run streaming consuming dispatcher deltas. |

---

## 3. Real vs Rule-Based vs Mock vs NOT VERIFIED Classification

- **REAL (verified by execution)**:
  - Adapter request translation and credential injection — real `httpx.AsyncClient` request construction inspected at the wire (URL, headers, JSON payload).
  - SSE stream parsing (OpenAI-compatible, Anthropic, Gemini event shapes) — real streaming through `httpx` line iteration with incremental chunk emission.
  - Error normalization and classification — real `httpx` status codes and exceptions injected at the transport.
  - Failover orchestration — real `FailoverManager` retry/backoff/fallback loops with real adapters.
  - Dispatcher wiring — real `call_upstream_llm_detailed` / `call_upstream_llm_stream` with real routing + credential resolution (platform keys); BYOK vault integration covered by `tests/unit/test_canonical_provider_resolution.py`.
- **RULE-BASED / DETERMINISTIC**: provider/model name resolution heuristics (`resolve_provider_name_for_model`), workload classification, router scoring (deterministic multi-objective scoring), silent default-model substitution for unknown model names (documented legacy behavior).
- **CONTROLLED DOUBLES (identified)**: `httpx.MockTransport` provider-contract doubles emulating upstream APIs — used because cloud adapter base URLs are hardcoded production endpoints. These verify JakeAI's code paths, **not** live upstream behavior.
- **NOT VERIFIED (live upstream)**: real network calls to api.openai.com / api.anthropic.com / generativelanguage.googleapis.com / api.groq.com / api.deepseek.com / openrouter.ai (requires live credentials; excluded by design from CI). Real local GPU Ollama instance.

---

## 4. Findings

### FINDING-01 — Streaming dispatcher dead: `chunk.delta` AttributeError swallowed (CRITICAL)

- **EXPECTED**: `call_upstream_llm_stream` yields each provider `StreamChunk.delta_text` incrementally to `JakeAIBackend.generate_stream`.
- **ACTUAL**: `chunk.delta` raised `AttributeError` on the first chunk (StreamChunk's field is `delta_text`, `app/providers/base.py:519`); the broad `except Exception` in `call_upstream_llm_stream` swallowed it, so the generator **always yielded zero tokens**. Every agent-run stream silently degraded to the non-streaming full-text fallback in `JakeAIBackend.generate_stream` (`streamed_any=False` path).
- **EVIDENCE**: RED test `test_streaming_dispatcher_yields_incremental_deltas` (pre-fix: `deltas == []`); code at `app/core/llm_provider.py:344` (`chunk.delta`); consumed by `app/agent/backends/jakeai.py:211-225`.
- **ROOT CAUSE**: Dispatcher written against a different/older chunk attribute name than the actual `StreamChunk` contract; no test exercised the dispatcher streaming path end-to-end.
- **AFFECTED FILES**: `backend/app/core/llm_provider.py`.
- **AFFECTED EXECUTION PATH**: `call_upstream_llm_stream` → `FailoverManager.stream_with_failover` → `adapter.stream` → `JakeAIBackend.generate_stream` → agent-run SSE.
- **FIX**: `chunk.delta` → `chunk.delta_text`.
- **REGRESSION TEST**: `tests/test_r_func_04_provider_behavior.py::test_streaming_dispatcher_yields_incremental_deltas`.
- **RETEST RESULT**: PASS — deltas `["Chunk 1 ", "Chunk 2"]` asserted incrementally.

### FINDING-02 — Cloud adapters leak raw httpx exceptions on timeout / connection failure (HIGH)

- **EXPECTED**: Per the adapter contract ("Error normalization into typed ProviderErrors"), a read timeout raises `ProviderTimeoutError` (retryable) and a connection failure raises `ProviderUnavailableError` (retryable) — as `LocalModelAdapter` already does.
- **ACTUAL**: Raw `httpx.ReadTimeout` / `httpx.ConnectError` propagated out of all six cloud adapters. Inside `FailoverManager` they hit the generic `except Exception` handler and were wrapped as `NON_RETRYABLE` — so a timeout was **never retried** and was misclassified; direct adapter callers received untyped exceptions.
- **EVIDENCE**: RED tests `test_cloud_adapter_timeout_normalized_to_typed_error`, `test_cloud_adapter_connect_error_normalized_to_unavailable`, `test_cloud_adapter_stream_timeout_normalized`, `test_cloud_adapter_stream_connect_error_normalized`; failover log: `Unexpected non-ProviderError from [openai]: timed out`.
- **ROOT CAUSE**: `await c.post(...)` / `c.stream(...)` not wrapped in exception normalization in the cloud adapters (only HTTP status responses were).
- **AFFECTED FILES**: `backend/app/providers/{openai,anthropic,gemini,groq,deepseek,openrouter}.py` (complete + stream paths).
- **AFFECTED EXECUTION PATH**: any provider completion/stream invocation crossing a network failure (timeout, connect/read/write errors, DNS).
- **FIX**: wrap network calls in `except httpx.TimeoutException → ProviderTimeoutError` and `except httpx.TransportError → ProviderUnavailableError` in all six cloud adapters, complete and stream paths.
- **REGRESSION TESTS**: the four RED tests above.
- **RETEST RESULT**: PASS.

### FINDING-03 — Malformed HTTP 200 response raises raw JSONDecodeError (HIGH)

- **EXPECTED**: a provider returning HTTP 200 with an unparseable body surfaces as a typed `ProviderError`; a provider-side protocol violation is classified `provider_unavailable` (retryable → failover possible).
- **ACTUAL**: `res.json()` raised a raw `json.JSONDecodeError` out of the adapters.
- **EVIDENCE**: RED test `test_cloud_adapter_malformed_response_normalized` (Groq adapter, 200 + `<html>not json {{{</html>`).
- **ROOT CAUSE**: response body parsing not guarded in cloud adapters.
- **AFFECTED FILES**: `backend/app/providers/{openai,anthropic,gemini,groq,deepseek,openrouter}.py`.
- **AFFECTED EXECUTION PATH**: adapter `complete()` response parsing.
- **FIX**: wrap `res.json()` and raise `ProviderUnavailableError("Provider returned a malformed JSON response: …")` (message sanitized by the `ProviderError` base).
- **REGRESSION TEST**: `test_cloud_adapter_malformed_response_normalized`.
- **RETEST RESULT**: PASS — typed `provider_unavailable`, retryable.

### FINDING-04 — Cross-provider failover unreachable under production defaults for retryable failures (HIGH)

- **EXPECTED**: Task acceptance "provider A failure → provider B selection": a primary persistently failing with a retryable error (e.g. 503/timeout) must hand off to the fallback chain.
- **ACTUAL**: with default `FailoverConfig(max_retries_per_provider=2, max_total_attempts=3)`, the primary consumed all 3 total attempts; the ceiling check (`total_attempts >= max_total_attempts`) aborted before the first fallback candidate was evaluated. Failover only worked for non-retryable errors (401/429-quota/etc.).
- **EVIDENCE**: RED test `test_failover_reaches_provider_b_under_default_config` (pre-fix: `ProviderUnavailableError` raised, gemini never invoked); production uses `FailoverManager()` defaults via `get_failover_manager()`.
- **ROOT CAUSE**: per-provider retry budget not coordinated with the total attempt ceiling — the defaults left zero budget for the fallback chain.
- **AFFECTED FILES**: `backend/app/routing/failover.py`.
- **AFFECTED EXECUTION PATH**: `FailoverManager.execute_with_failover` retry loop for all dispatch traffic.
- **FIX**: default `max_retries_per_provider` 2 → 1 (invariant documented: per-provider retries must stay below the total ceiling) and the total attempt ceiling is now additionally enforced inside the retry decision (`total_attempts < max_total_attempts`), preventing a single candidate from overshooting the ceiling.
- **REGRESSION TESTS**: `test_failover_reaches_provider_b_under_default_config`, `test_failover_timeout_is_retried_then_fails_over` (proves timeout → 1 retry → failover to provider B end-to-end).
- **RETEST RESULT**: PASS — openai attempted exactly 2× (initial + 1 retry), then gemini succeeded.
- **PRESERVED BEHAVIOR**: all pre-existing failover tests pass unchanged (`max_retries_per_provider` remains overridable; explicit configs unaffected; bounded retry semantics retained — worst case remains bounded by `max_total_attempts`).

### FINDING-05 — VERIFIED (no defect): zero cross-provider credential reuse (wire-level proof)

- **EXPECTED**: provider B receives provider B credentials; the failed provider's secret is never reused.
- **VERIFIED**: `test_failover_wire_credentials_are_provider_specific` proves at the HTTP wire that (a) provider A's request carries `Authorization: Bearer sk-openai-credential-A`, (b) provider B's request carries its own credential in its own scheme (`key=gemini-credential-B` in the URL), and (c) provider A's secret is absent from provider B's URL and headers. The no-resolver path is pinned by `test_provider_failover_credentials.py` (fallback receives per-provider/`None` resolution, never the primary's key; original `ProviderRequest` never mutated). Manager-level: `credential_resolver(tenant_id, provider)` is invoked per candidate; without a resolver, `request.api_key` is used only before any provider has executed (`has_executed_provider` guard).

### FINDING-06 — VERIFIED (no defect): provider-reported usage reconciles to accounting

- **VERIFIED**: `test_provider_reported_usage_reconciles_to_accounting` — provider-reported `prompt_tokens=100 / cached=50 / completion_tokens=20` flow unmodified into `ProviderCacheTelemetry` (`cached_tokens=50`, `uncached_input_tokens=50`, `output_tokens=20`, `uncached+cached == 100`), `raw_usage` preserved verbatim, and cost derived from those reported tokens at provider pricing (`$0.0003875` for gpt-4o; baseline `$0.00045`). The dispatcher records these exact values via `metrics.record_provider_request(prompt_tokens=telemetry.uncached+telemetry.cached, completion_tokens=telemetry.output_tokens, cost_usd=telemetry.actual_cost_usd)`.

### FINDING-07 — Router silently returns the requested model when an explicitly required capability is unsatisfiable (MEDIUM — recorded, dispositioned to R-AI-04)

- **EXPECTED** ("unsupported model/capability rejected" required test): when no model — including the requested one — satisfies `required_capabilities`, the router should reject with a typed error rather than silently return an incapable model.
- **ACTUAL**: e.g. `RoutingPolicy(requested_model="gpt-4o", required_capabilities=["supports_embeddings"])` eliminates every candidate, then the emergency fallback returns the requested model, which itself lacks the capability. Achievable capability conflicts (e.g. `supports_reasoning`) ARE re-routed correctly (proven by `test_model_router_reasoning_workload`, `test_router_constraints_and_downgrades_extended`).
- **ROOT CAUSE**: emergency fallback branch in `ModelRouter.route()` bypasses hard filters for the requested model.
- **DISPOSITION**: not fixed in this task. (1) Raising from `route()` would create new unhandled exception paths: `call_upstream_llm_detailed` invokes `route()` outside its try block and `JakeAIBackend.generate` does not wrap the dispatcher call — the minimal fix requires caller-side error-path design that belongs to routing/degradation semantics. (2) Router degradation-fallback behavior is explicitly owned by **R-AI-04: "Model Router Complexity Classification & Degradation Fallbacks"** per RIGHT-00 §15 execution order. Recorded here with evidence so it is not lost.
- **RELATED OBSERVATION (LOW, accepted legacy)**: unknown (non-catalog) model names are silently substituted to provider defaults by adapters (e.g. any non-`gpt/o1/o3` model → `gpt-4o-mini` on the OpenAI adapter). This is pinned as accepted behavior by the pre-existing `test_registry_methods_extended` / `test_failover_limits_and_unexpected_errors` tests; catalog models are always passed through verbatim (proven at the wire by `test_selected_model_reaches_provider_payload`).

### Environment note (not a defect)

`tests/test_agent_platform.py::test_local_safe_sandbox_file_and_commands` fails identically on the clean baseline commit `99144cb` in this WSL environment (sandboxed shell behavior). Classified **ENVIRONMENT FAILURE** (pre-existing, unrelated to provider behavior; it fails on `main` without any of this task's changes). It does not fail in GitHub CI.

---

## 5. Tests Executed

**New R-FUNC-04 verification suite** — `backend/tests/test_r_func_04_provider_behavior.py` (22 tests):

| # | Test | Required-test mapping |
|---|---|---|
| 1 | `test_dispatch_invokes_selected_provider_and_model_on_the_wire` | selected provider/model actually invoked (dispatcher → wire) |
| 2 | `test_selected_model_reaches_provider_payload` | request transformation; no silent substitution for catalog models |
| 3 | `test_structured_output_forwarded_to_provider` | structured output |
| 4 | `test_provider_reported_usage_reconciles_to_accounting` | usage reconciliation |
| 5 | `test_streaming_dispatcher_yields_incremental_deltas` | streaming deltas (real incremental) |
| 6 | `test_cloud_adapter_timeout_normalized_to_typed_error` | timeout |
| 7 | `test_cloud_adapter_connect_error_normalized_to_unavailable` | provider unavailability |
| 8 | `test_cloud_adapter_malformed_response_normalized` | malformed response |
| 9 | `test_cloud_adapter_stream_timeout_normalized` | timeout (streaming) |
| 10 | `test_cloud_adapter_stream_connect_error_normalized` | provider unavailability (streaming) |
| 11 | `test_error_status_matrix_classification` (401/403/429/500/502/503) | failure classification |
| 12 | `test_429_with_quota_message_maps_to_quota_error` | 429 quota vs rate-limit |
| 13 | `test_429_respects_retry_after_header` | 429 retry-after |
| 14 | `test_failover_reaches_provider_b_under_default_config` | provider A failure → provider B selection |
| 15 | `test_failover_wire_credentials_are_provider_specific` | provider B receives provider B credentials |
| 16 | `test_failover_fallback_model_reaches_the_wire` | fallback provider/model actually invoked |
| 17 | `test_failover_timeout_is_retried_then_fails_over` | timeout → retry → failover |
| 18–22 | (remaining matrix/variant cases within the above groups) | — |

**Regression suites executed (all PASS)**: `test_provider_foundation.py` (24), `test_provider_prompt_caching.py`, `test_provider_failover_credentials.py`, `tests/unit/test_canonical_provider_resolution.py`, `tests/unit/test_direct_provider.py` — 143 tests; then full suite in chunks: `tests/contract` + `tests/evals`, `tests/unit`, and three root-file batches — 0 failures except the pre-existing environment failure noted above.

---

## 6. Exact Commands & Actual Results

```bash
# 1. Baseline (defect reproduction — RED)
cd backend && .venv/bin/pytest tests/test_r_func_04_provider_behavior.py -q
#   PRE-FIX RESULT: 8 failed, 14 passed  (8 = confirmed defect reproductions)

# 2. Post-fix verification (GREEN)
.venv/bin/pytest tests/test_r_func_04_provider_behavior.py -q
#   RESULT: 22 passed

# 3. Provider regression suites
.venv/bin/pytest tests/test_provider_foundation.py tests/test_provider_prompt_caching.py \
  tests/test_provider_failover_credentials.py tests/unit/test_canonical_provider_resolution.py \
  tests/unit/test_direct_provider.py -q
#   RESULT: 143 passed

# 4. Full-suite regression (chunked for WSL memory limits; exit code = gate)
.venv/bin/pytest tests/contract tests/evals -q -p no:cacheprovider      # 0 failures
.venv/bin/pytest tests/unit -q -p no:cacheprovider                      # 0 failures
.venv/bin/pytest <root batch 1> -q -p no:cacheprovider  # 1 pre-existing env failure (sandbox, fails on baseline too)
.venv/bin/pytest <root batch 2> -q -p no:cacheprovider  # EXIT=0
.venv/bin/pytest <root batch 3> -q -p no:cacheprovider  # EXIT=0

# 5. CI-equivalent quality gates
backend/.venv/bin/ruff check backend/            # All checks passed!
backend/.venv/bin/ruff format --check backend/   # 253 files already formatted
backend/.venv/bin/mypy --config-file backend/mypy.ini backend/app
#   Success: no issues found in 166 source files
cd backend && .venv/bin/bandit -c pyproject.toml -r app/
#   Low: 0, Medium: 0, High: 0
```

---

## 7. CI Result

| Check | Local | GitHub CI (run 34722099787) |
|---|---|---|
| ruff check / format | PASS | PASS (Code Quality & Type Analysis 3.11 + 3.12) |
| mypy (166 files) | PASS | PASS (Code Quality & Type Analysis 3.11 + 3.12) |
| bandit SAST | PASS (0 issues) | PASS (DevSecOps Vulnerability Audit, SAST & License Compliance) |
| pytest full suite + coverage floor (≥85%) | PASS (chunked locally) | PASS (Automated Tests & AI RAG Regression 3.11 + 3.12, incl. patch coverage diff gate) |
| Secret scanning (gitleaks) | — | PASS |
| Infrastructure & workflow linting | — | PASS |
| Frontend build & quality | — | PASS |
| Container build & Trivy scan | — | PASS |

**All 9 CI checks: success.** Mergeable state at verification time: `clean`.

**PR**: https://github.com/NguyenQuan121321/JakeAI/pull/37
**CI run**: https://github.com/NguyenQuan121321/JakeAI/actions/runs/34722099787 (Continuous Integration, conclusion `success` on head SHA `9d6ff94`)

---

## 8. Remaining Issues & Risks

1. **FINDING-07 (MEDIUM, dispositioned)**: router emergency fallback can return a model lacking explicitly-required capabilities; owned by R-AI-04 (degradation fallbacks). No security impact; no cost impact (no call is mis-billed); behavior is observable in `decision_reasons`.
2. **Live upstream verification (NOT VERIFIED)**: adapter paths are proven against controlled provider-contract doubles. A one-shot live credential smoke test (real OpenAI/Anthropic/Gemini keys) remains the only way to prove live upstream integration; excluded from CI by design.
3. **Streaming usage telemetry**: cloud-adapter stream chunks do not carry provider-reported usage (only `LocalModelAdapter` emits a final telemetry chunk). Non-streaming usage reconciliation is fully verified; streaming-side accounting still relies on estimation downstream. Pre-existing behavior, recorded for the FinOps/accounting owner (R-FUNC-03 / R-LOGIC-02 adjacent).
4. **`stream_with_failover` streams only from the selected provider**: mid-stream failures are not retried/failovered (retrying a partially-consumed stream risks duplicated output). Pre-existing, bounded design; recorded.
5. **500 classification**: HTTP 500 maps to generic `non_retryable` `ProviderError` (failover still proceeds immediately to the next candidate). Some providers' 500s are transient; changing this alters retry semantics and is left as-is (documented classification matrix test pins current behavior).
6. **Environment**: `test_local_safe_sandbox_file_and_commands` fails locally in WSL on the clean baseline (pre-existing environment failure; green in GitHub CI).

---

## 9. Manual Test Instructions for Human Reviewer

1. **Incremental streaming (FINDING-01)**: with a configured provider key, launch the server (`cd backend && uv run uvicorn app.main:app --host 0.0.0.0 --port 8000`) and start an agent run with streaming:
   `curl -N -X POST http://localhost:8000/api/v1/agent/tasks -H "X-Tenant-ID: tenant_demo" -H "Content-Type: application/json" -d '{"goal":"Say hello in five words","stream":true}'`
   Then poll the run events SSE endpoint (`GET /api/v1/agent/tasks/{task_id}/runs/{run_id}/events`): token deltas must arrive **incrementally** (multiple partial deltas), not as one final blob.
2. **Failover + credential isolation (FINDING-04/05)**: register a deliberately invalid OpenAI BYOK key and a valid Gemini key for the tenant (`POST /api/v1/byok/keys`), then request `model=gpt-4o`. Server logs must show `[openai] … AUTHENTICATION` followed by fallback to `gemini`, with the gemini request carrying the tenant's gemini key (never the OpenAI key). Response must be produced by the fallback provider.
3. **Regression suite**: run `cd backend && .venv/bin/pytest tests/test_r_func_04_provider_behavior.py tests/test_provider_foundation.py tests/test_provider_failover_credentials.py -v` — all green.

---

## 10. Verification Log (chronological evidence)

| Step | Evidence |
|---|---|
| Baseline | `99144cb` = origin/main (PR #36, CI green); branch `chore/r-func-04-provider-behavior` created from it |
| RED | `pytest tests/test_r_func_04_provider_behavior.py` → 8 failed / 14 passed (8 defect reproductions; 2 initial harness issues corrected — real adapters require resolvable credentials; accepted simple_chat cost-aware down-tiering documented) |
| Fix | commits `5492d5f` (fix(providers)) + `9d6ff94` (test(providers)) |
| GREEN | 22/22 new tests; 143/143 provider regression tests; full-suite chunks 0 failures (1 pre-existing WSL env failure, fails on baseline) |
| Quality gates | ruff check ✓, ruff format ✓, mypy ✓ (166 files), bandit ✓ (0 issues) |
| CI | run 34722099787 — Continuous Integration, **all 9 checks `success`** (head SHA `9d6ff94`): Code Quality & Type Analysis (3.11/3.12), Automated Tests & AI RAG Regression (3.11/3.12) incl. ≥85% coverage floor + patch coverage diff gate, DevSecOps Secret Scanning, DevSecOps Vulnerability Audit/SAST, Infrastructure Linting, Frontend Build, Container Build & Trivy Scan |
