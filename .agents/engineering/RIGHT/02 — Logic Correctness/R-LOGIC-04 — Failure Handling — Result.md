# R-LOGIC-04 — Failure Handling — Result

**Status**: VERIFIED — all confirmed defects fixed, regression-tested, all CI-equivalent checks green locally. GitHub CI: **run 34759080380 GREEN (9/9 check runs), PR #42 mergeable: clean** (see §7).
**Baseline**: `main` @ `f69a389` (post R-LOGIC-03 merge, PR #41)
**Branch**: `chore/r-logic-04-failure-handling` → PR #42
**Date**: 2026-09-13

---

## 1. Scope Inspected

Failure classification, retry/replan/switch/fallback behavior, and terminal-state integrity across:

| Component | File | Classification |
|---|---|---|
| Provider error taxonomy & normalizer (401/403/429/402/502/503/504/529/408/400, transport, policy, context-limit) | `backend/app/providers/errors.py` | REAL (rule-based classifier, zero-secret sanitization) |
| Bounded failover manager (retry budget, attempt ceiling, exponential backoff + jitter, Retry-After, cross-provider fallback) | `backend/app/routing/failover.py` | REAL (algorithmic) |
| Centralized upstream dispatcher + streaming dispatcher | `backend/app/core/llm_provider.py` | REAL (failover wired); streaming error path was defective (RL04-F-05) |
| Canonical ExecutionEngine (DAG dispatch, recovery integration, run timeout, cancellation, resume) | `backend/app/agent/execution/engine.py` | REAL; backend-failure path was defective (RL04-F-01) |
| Bounded recovery engine (step-failure classification, verification verdict mapping, bounded limits) | `backend/app/agent/recovery/recovery.py` | REAL (rule-based); classification was defective (RL04-F-02, F-07) |
| Circuit breaker (CLOSED/OPEN/HALF_OPEN + fallback chain) | `backend/app/core/circuit_breaker.py` | REAL; never reachable from gateway path (RL04-F-04) |
| Gateway inference proxy (JSON + SSE, quota reservation, Tier-1 cache) | `backend/app/services/ai_gateway.py` | REAL; outage fallback was cached and breaker-blind (RL04-F-03/04) |
| JakeAI backend adapter (+ stream fallback) | `backend/app/agent/backends/jakeai.py` | REAL; mid-stream failure silent (RL04-F-05) |
| Direct provider backend | `backend/app/agent/backends/direct_provider.py` | REAL (error finish-reasons `http_*`/`exception`/`error_missing_credentials` now classified) |
| LangGraph workflow (supervisor/specialists/verifier/synthesizer) | `backend/app/agents/graph.py`, `app/agents/synthesizer.py` | REAL; labeled synthetic greeting on provider failure (accepted degradation, see §6) |
| Tool registry + policy engine | `backend/app/agent/tools/registry.py`, `policy.py` | REAL (timeout, policy denial, validation — all fail-closed) |
| RAG hybrid retriever (dense/sparse degradation modes) | `backend/app/rag/retriever.py` | REAL (per-leg degradation classified: `sparse_degraded`/`dense_degraded`/`failed`) |
| RAG generation pipeline (abstention classes) | `backend/app/rag/pipeline.py`, `app/rag/models.py` | REAL; total retrieval failure misclassified (RL04-F-06) |
| RAG ingestion worker queue | `backend/app/rag/tasks.py`, `app/worker.py` | REAL (bounded concurrency 2; task exception → `FAILED` status, loop survives) |
| Checkpoint manager (Redis durability, corrupt record handling) | `backend/app/agent/state/checkpoint.py` | REAL (fail-closed verified; see §6 observation on Redis cooldown) |
| Chat SSE endpoint (8 terminal paths, stream timeout, settlement) | `backend/app/api/v1/endpoints/chat.py` | REAL (workflow errors surfaced as SSE `error` events — verified correct) |
| Run/Task state machine terminality | `backend/app/agent/state/models.py` | REAL (`TIMEOUT`/`REJECTED`/`FAILED`/`CANCELLED` terminal; verified) |

## 2. Execution Paths Tested

1. **Provider boundary**: `FailoverManager.execute_with_failover` with injected 401, 403, 429 (rate-limit), 429 (quota message), 503, timeout — per-provider retry counts, total attempt ceiling, cross-provider fallback.
2. **Engine boundary (real `JakeAIBackend` + provider outage injection at the dispatch boundary)**: full task lifecycle → terminal event, run state, fabricated-output check.
3. **Recovery engine**: classification matrix (12 error shapes × action), first-attempt edge values (retries=0), verification verdict mapping.
4. **Gateway JSON**: outage → labeled fallback, breaker failure counting, breaker OPEN fast-fallback, recovery → provider answer, cache-population suppression.
5. **Gateway SSE**: outage → labeled fallback streamed, no cache population; recovery → provider content.
6. **Streaming dispatch**: mid-stream `ProviderUnavailableError` propagation; `JakeAIBackend.generate_stream` error terminal chunk.
7. **RAG**: both retrieval legs failed → `RETRIEVAL_FAILURE`; healthy-but-empty index → `NO_RELEVANT_EVIDENCE` (unchanged).
8. **Persistence**: corrupt Redis checkpoint record → `load_checkpoint=None` → resume `KeyError`; Redis write failure → memory-only degradation, no crash.
9. **Tools**: execution timeout → failed result; policy denial → failed result with `Forbidden`; engine-level permission-denied step → run FAILED with zero retries.
10. **Run terminality**: run timeout → `RunStatus.TIMEOUT` + `status: "timeout"` event + `resume_refused` on subsequent resume.
11. **Planner**: malformed model plan output → deterministic fallback plan (`planner_mode="degraded_fallback"`).

## 3. Tests Executed (REAL / RULE-BASED / MOCK / NOT VERIFIED)

| Area | Boundary | Classification |
|---|---|---|
| Failover retry/failover matrix, backoff math, attempt ceiling | Service-level with adapter doubles behind the real `FailoverManager` | REAL logic under test; provider adapters are controlled doubles (real HTTP not required for classification logic — live provider contract separately covered by R-FUNC-04 suite) |
| Provider HTTP status → category normalization | Adapter-level (existing suite re-verified: `test_r_func_04_provider_behavior.py`, `test_provider_foundation.py`) | RULE-BASED mapping, verified |
| Engine outage / timeout / non-retryable terminality | Service-level engine with real `JakeAIBackend` + injected outage at the provider dispatch seam | REAL path; upstream itself simulated (no live LLM in CI — see NOT VERIFIED) |
| Gateway cache/breaker behavior | Service-level proxy with injected outage | REAL path; upstream simulated |
| Corrupt checkpoint | `CheckpointManager` against a minimal async Redis double | REAL degradation logic; Redis network path NOT VERIFIED locally (real-Redis path exercised in CI service container by pre-existing suite) |
| Live cloud LLM failures (real 401/429/503 from OpenAI/Gemini/etc.) | — | **NOT VERIFIED** (no live provider credentials; the typed-error handling for real HTTP statuses is covered at adapter level via normalized-status tests, and transport-error tests exist) |
| Live Ollama / FinnApiGo backend failures | — | **NOT VERIFIED** (mock/synthetic upstream per inventory) |

## 4. Findings

### RL04-F-01 — SEVERITY: CRITICAL — total provider failure reported as run success with fabricated output

- **EXPECTED**: When every upstream provider fails (the dispatcher returns no content), the step must FAIL, recovery must classify the failure, and the run must terminate FAILED. A failure must never be converted into a success.
- **ACTUAL**: `JakeAIBackend.generate` returned `content=""`, `finish_reason="error"`; `ExecutionEngine._execute_single_step` converted this into `StepStatus.COMPLETED` with fabricated output `"Completed step execution."`. The run then passed verification and emitted `completed` with `final_output="Completed step execution."`. Reproduction on pristine main: terminal event `completed`, `RunState.status: completed`.
- **EVIDENCE**: Repro `[1]` on pristine `f69a389`: `[1] engine provider-outage terminal event: completed` / `step_completed output: {'output': 'Completed step execution.'}`; post-fix: `terminal event: failed`, `RunState.status: failed`. Regression tests `test_provider_outage_fails_run_without_fabricated_success`, `test_backend_error_finish_reason_fails_step_not_fabricates`.
- **ROOT CAUSE**: The engine treated any `BackendResponse` as success and papered over empty content with the literal fallback string `resp.content or "Completed step execution."`; error finish-reasons (`error`, `exception`, `http_*`, `error_missing_credentials`) were never inspected.
- **AFFECTED FILES**: `backend/app/agent/execution/engine.py`.
- **AFFECTED EXECUTION PATH**: `execute_task → _run_execution_loop → _execute_single_step` (ReAct/backend-model step path) for every orchestration run whose model dispatch fails.
- **FIX**: Detect `(resp.finish_reason or "").startswith(("error", "exception", "http_"))` or blank content → `StepStatus.FAILED` with `error="Backend model generation failed (finish_reason=...)"` (the finish reason is embedded so recovery can classify non-retryable shapes); removed the fabricated-output fallback.
- **REGRESSION TEST**: see EVIDENCE (in `backend/tests/test_r_logic_04_failure_handling.py`).
- **RETEST RESULT**: PASS — outage run now terminates FAILED; zero `step_completed` events; `RunStatus.FAILED.is_terminal`.

### RL04-F-02 — SEVERITY: HIGH — recovery engine retried non-retryable failures

- **EXPECTED**: Retry only retryable failures. Authentication (401/403), quota exhaustion, provider policy rejection, context-limit, and tool-permission denials must terminate immediately (bounded switch/replan may apply to retryable classes only).
- **ACTUAL**: `BoundedRecoveryEngine.evaluate_step_failure` classified by substring and had no notion of the provider error taxonomy: auth 401 → `retry`, quota → `switch_model` (matched bare "429"), policy rejection → `retry`, tool-permission denial → `retry`. Each non-retryable failure burned the full retry budget (3 retries + up to 2 agent switches) before terminating.
- **EVIDENCE**: Repro `[2]` on pristine main: `AUTHENTICATION (HTTP 401) → retry`, `QUOTA (HTTP 429) → switch_model`, `POLICY_REJECTED → retry`, `Forbidden: ... permissions → retry`; post-fix all four → `terminate_failed` while transient `ConnectError → retry` (correctly preserved). Regression test `test_recovery_classification_matrix` (12 cases) and `test_non_retryable_step_failure_terminates_without_retry` (asserts exactly one backend call, zero retry/switch events).
- **ROOT CAUSE**: Classification matrix lacked non-retryable markers; `ProviderError.__str__` embeds the category (`[openai] AUTHENTICATION (HTTP 401)`) but the marker list only covered transient classes.
- **AFFECTED FILES**: `backend/app/agent/recovery/recovery.py`.
- **AFFECTED EXECUTION PATH**: every failed-step recovery evaluation in `ExecutionEngine._run_execution_loop`.
- **FIX**: Non-retryable marker set (authentication/forbidden/401/403/api-key/missing_credentials, quota/billing, policy/safety/moderation/content_filter/context-limit, approval-gate refusals) checked before the transient classification; returns `TERMINATE_FAILED`.
- **REGRESSION TEST**: see EVIDENCE.
- **RETEST RESULT**: PASS.

### RL04-F-03 — SEVERITY: HIGH — gateway cached the outage fallback into the Tier 1 exact cache

- **EXPECTED**: A deterministic offline fallback may preserve availability, but it must not be persisted as a genuine provider response; after provider recovery the same prompt must be served by the provider.
- **ACTUAL**: Both `chat_completions` and `chat_completions_stream` cached the synthetic fallback text. Reproduction on pristine main: outage call → fallback; provider "recovers"; identical call → `cached: True` serving the outage fallback (cache poisoned permanently for that prompt/TTL).
- **EVIDENCE**: Repro `[3]` pristine: `after recovery, content served: [JakeAI Gateway Response ...] cached: True`; post-fix: `content served: REAL PROVIDER ANSWER, cached: False`. Regression tests `test_gateway_outage_fallback_not_cached_and_breaker_counts`, `test_gateway_stream_outage_fallback_not_cached`.
- **ROOT CAUSE**: The cache population step did not distinguish genuine upstream responses from the deterministic fallback.
- **AFFECTED FILES**: `backend/app/services/ai_gateway.py`.
- **AFFECTED EXECUTION PATH**: `chat_completions` (JSON) and `chat_completions_stream` (SSE) miss-branch on total upstream failure.
- **FIX**: Cache population is now gated on genuine upstream success (`upstream_response is not None` / truthy `upstream_output_text`). The fallback remains labeled (`[JakeAI Gateway Response via …]`) and the existing `provider_cache.miss_reason="offline_fallback"` telemetry already flags it to clients.
- **REGRESSION TEST**: see EVIDENCE.
- **RETEST RESULT**: PASS.

### RL04-F-04 — SEVERITY: MEDIUM — gateway circuit breaker could never trip

- **EXPECTED**: Consecutive total upstream failures must increment the breaker's failure count; after the threshold the breaker opens and requests fast-fall back without touching the dead provider (the "multi-provider circuit-breaker fallback" contract).
- **ACTUAL**: `call_model` swallowed the upstream failure (`call_upstream_llm_detailed` → `None` → synthetic fallback return) so `CircuitBreaker.call_with_fallback` recorded a success: `failure_count` stayed 0, state stayed `CLOSED` forever.
- **EVIDENCE**: Repro `[3]` pristine: `breaker state after outage: CLOSED failures: 0`; post-fix: `failures: 1`, and after 3 consecutive outages `state == OPEN` with the provider no longer called (fast fallback). Regression test `test_gateway_breaker_opens_after_consecutive_outages`.
- **ROOT CAUSE**: The breaker requires the wrapped callable to raise on failure; the gateway converted failure into a fallback return inside the wrapped callable.
- **AFFECTED FILES**: `backend/app/services/ai_gateway.py`.
- **AFFECTED EXECUTION PATH**: `GatewayInferenceProxy.chat_completions` (JSON path, the only path wrapped by the breaker).
- **FIX**: `call_model` raises `ProviderUnavailableError` when both the detailed and legacy dispatchers return nothing; the identical deterministic fallback is passed as `deterministic_fallback_fn` to `call_with_fallback`, preserving the no-HTTP-500 availability contract while restoring breaker semantics (failure counting, OPEN fast-fallback, half-open probe recovery).
- **REGRESSION TEST**: see EVIDENCE.
- **RETEST RESULT**: PASS.

### RL04-F-05 — SEVERITY: MEDIUM — mid-stream provider failure silently truncated streams

- **EXPECTED**: A streaming failure must be observable to the consumer: the dispatcher must propagate the error, and the backend stream must signal a failure terminal state rather than ending as if complete.
- **ACTUAL**: `call_upstream_llm_stream` swallowed all exceptions (`except Exception: logger.debug`), and `JakeAIBackend.generate_stream` ended silently after partial content (`streamed_any=True` → no fallback, no error signal). Repro `[4]` pristine: `chunks=['partial'] exception_propagated=False`.
- **EVIDENCE**: Post-fix: `exception_propagated=True`; `generate_stream` yields terminal chunk `finish_reason="error", is_complete=True` after partial content (content already billed cannot be re-generated without duplicating output/side effects). Regression tests `test_midstream_failure_propagates_not_silently_truncates`, `test_backend_stream_signals_error_terminal_chunk`.
- **ROOT CAUSE**: Broad exception suppression at the streaming dispatcher; no error terminal state existed in the backend stream protocol.
- **AFFECTED FILES**: `backend/app/core/llm_provider.py`, `backend/app/agent/backends/jakeai.py`.
- **AFFECTED EXECUTION PATH**: `call_upstream_llm_stream` → `JakeAIBackend.generate_stream` (streaming backend path).
- **FIX**: Dispatcher re-raises typed `ProviderError`s; backend stream distinguishes pre-stream failure (falls back to non-streaming generate — unchanged) from mid-stream failure (error terminal chunk, no duplicate generation).
- **REGRESSION TEST**: see EVIDENCE.
- **RETEST RESULT**: PASS.

### RL04-F-06 — SEVERITY: MEDIUM — RAG reported total retrieval failure as "no relevant evidence"

- **EXPECTED**: Empty-evidence abstention (`NO_RELEVANT_EVIDENCE`) and search-infrastructure failure are different failure classes; the task matrix requires exact classification.
- **ACTUAL**: When both dense (Qdrant) and sparse (BM25) legs raised, `HybridRetriever` correctly reported `retrieval_mode="failed"`, but the pipeline ignored it and returned `ABSTAINED / NO_RELEVANT_EVIDENCE`. Repro `[5]` pristine: `status=ABSTAINED reason=NO_RELEVANT_EVIDENCE`.
- **EVIDENCE**: Post-fix: `status=ABSTAINED reason=RETRIEVAL_FAILURE`; healthy-empty index still yields `NO_RELEVANT_EVIDENCE`. Regression tests `test_rag_total_retrieval_failure_classified_as_retrieval_failure`, `test_rag_empty_index_still_no_relevant_evidence`.
- **ROOT CAUSE**: Pipeline consumed only `context_res.selected_chunks`, dropping the retriever's degradation classification.
- **AFFECTED FILES**: `backend/app/rag/pipeline.py`, `backend/app/rag/models.py` (new `AbstentionReason.RETRIEVAL_FAILURE`).
- **AFFECTED EXECUTION PATH**: `RAGPipeline.generate_grounded_answer` when both retrieval legs fail.
- **FIX**: `retrieval_mode == "failed"` with no selected chunks → explicit `RETRIEVAL_FAILURE` abstention with an infrastructure-specific message.
- **REGRESSION TEST**: see EVIDENCE.
- **RETEST RESULT**: PASS.

### RL04-F-07 — SEVERITY: MEDIUM — recovery decision crashed on first-attempt timeout / verifier rejection (edge value)

- **EXPECTED**: `evaluate_step_failure(step, msg, current_step_retries=0, elapsed≥limit)` and `evaluate_verification_result(REJECTED, current_replans=0)` must return terminal decisions (the most common first-failure shapes).
- **ACTUAL**: `RecoveryDecision.attempt` is contract-bound `ge=1`, but the time-limit and non-retryable branches pass `current_step_retries` (0 on first failure) and the PASS/REJECTED/time-limit/terminal branches pass `current_replans` (0 on first cycle) → `pydantic ValidationError` raised inside the recovery engine instead of a decision. Found while testing the F-02 fix (the very first auth failure crashed the recovery path).
- **EVIDENCE**: Repro crash traceback (pre-fix): `ValidationError: attempt — Input should be greater than or equal to 1, input_value=0`; post-fix all branches return decisions. Regression tests `test_recovery_first_attempt_timeout_does_not_crash`, `test_recovery_first_attempt_non_retryable_does_not_crash`, `test_recovery_verification_rejection_never_replans`.
- **ROOT CAUSE**: Branch code never clamped the attempt counter to the contract minimum.
- **AFFECTED FILES**: `backend/app/agent/recovery/recovery.py` (5 branches clamped to `max(1, ...)`).
- **AFFECTED EXECUTION PATH**: any first-attempt step failure hitting the time limit or a non-retryable error; any first-cycle verification evaluation through the recovery engine API.
- **REGRESSION TEST**: see EVIDENCE.
- **RETEST RESULT**: PASS.

### Test-realignments required by the fixes (not defects; intent preserved)

- `tests/unit/test_canonical_provider_resolution.py` (2 tests), `tests/unit/test_cache_identity.py::test_gateway_exact_cache_isolation_across_dimensions`, `tests/test_commercial_services.py::test_gateway_inference_proxy_caching`, `tests/test_openai_compatibility.py::test_chat_completions_exact_caching`, `tests/test_r_func_03_cache_behavior.py::test_scenario_21/22`: these asserted that the **outage fallback** gets cached / replay-hit. Their stated intent (cache-identity attribution, exact-cache lifecycle, tool-call structure in identity) is preserved by injecting a **genuine** `UpstreamLLMResponse` instead of relying on the outage fallback. No assertions were weakened.

## 5. Verification of correct behaviors (no defect — confirmed by tests)

- **Bounded exponential backoff with jitter**: nominal `base·factor^attempt` with up to 10% jitter, capped at `max_delay_seconds`; `Retry-After` honored and capped (`test_backoff_is_bounded_exponential_with_jitter`, `test_retry_after_respected_and_capped`).
- **No infinite loops / retry storms**: per-provider retry budget, `max_total_attempts` ceiling with leftover budget reserved for failover, duplicate-candidate suppression (`test_total_attempt_ceiling_prevents_retry_storm` — exactly 4 attempts with 5 candidates × repeated failures).
- **Security failures never retry into success**: verifier `REJECTED` → `TERMINATE_REJECTED` (engine terminates run `REJECTED`, terminal); tool policy denial → run FAILED with zero retries.
- **Terminal states remain terminal**: `TIMEOUT`/`FAILED`/`CANCELLED`/`REJECTED` are terminal; resume on a timed-out run yields `resume_refused` (`test_run_timeout_is_terminal_and_never_resumable`; state-machine invariants additionally covered by R-LOGIC-01 suite).
- **No duplicated side effects**: single tool execution per step dispatch; mid-stream failure never re-generates (error terminal chunk instead of fallback regeneration); quota reservation/settlement exactly-once per R-LOGIC-03 (suite re-verified green).
- **Partial-outage graceful degradation**: one retrieval leg failing continues on the other (`sparse_degraded`/`dense_degraded`); circuit-breaker HALF_OPEN probe recovery covered by `test_circuit_breaker.py`.
- **Malformed model output**: invalid plan JSON → bounded deterministic fallback plan; malformed tool-call JSON → logged, ignored; `extract_json_dict` → `None` (no eval/exec).

## 6. Remaining Issues / Risks / Observations

- **RL04-O-01 (LOW, not fixed — resilience, not classification)**: `CheckpointManager._get_redis` and `FinOpsBudgetManager._get_redis` permanently disable Redis after the first connection failure (no reconnect cooldown), unlike `QuotaManager`/`IngestionTaskManager` which retry after 30 s. A transient Redis blip degrades the process to memory-only checkpointing until restart. Failure handling remains correct (no crash, no fabricated success); suggested follow-up: adopt the cooldown pattern.
- **RL04-O-02 (LOW, design trade-off)**: the LangGraph chat workflow (`app/agents/synthesizer.py`) substitutes a labeled hardcoded greeting when the LLM returns nothing and finishes the stream normally. The label distinguishes it from a genuine answer; changing this to an error event would alter accepted product behavior (graceful-degradation contract) and is recorded here for the human reviewer.
- **NOT VERIFIED**: live cloud-provider failure injection (real 401/429/503 HTTP responses from OpenAI/Gemini/Anthropic), real Redis checkpoint corruption over the network path, live Ollama/FinnApiGo failures. CI runs the adapter-level normalized-status matrix and (where applicable) real-Redis integration tests.
- **500 classification note**: `normalize_provider_error` maps HTTP 500 to `NON_RETRYABLE` (asserted baseline behavior in the existing provider matrix). Recovery is still achieved via cross-provider failover (no same-provider retry). Recorded as accepted baseline; revisit only if same-provider 500-retry is desired.

## 7. Commands & Results

```bash
# Reproduction on pristine main (evidence for F-01..F-06)
.venv/bin/python /tmp/rl04_repro.py
#   [1] engine provider-outage terminal event: completed   (defect)
#   [2] AUTHENTICATION (HTTP 401) -> retry                 (defect)
#   [3] after recovery, content served: [JakeAI Gateway...] cached: True (defect)
#   [3] breaker state after outage: CLOSED failures: 0     (defect)
#   [4] chunks=['partial'] exception_propagated=False      (defect)
#   [5] status=ABSTAINED reason=NO_RELEVANT_EVIDENCE       (defect)
# Post-fix rerun: failed / terminate_failed / REAL PROVIDER ANSWER cached: False /
#   failures: 1 (OPEN after 3) / exception_propagated=True / RETRIEVAL_FAILURE

# New regression suite (38 tests)
.venv/bin/python -m pytest tests/test_r_logic_04_failure_handling.py -q
#   ......................................   [100%]  (38 passed)

# Full suite file-by-file (WSL OOM constraint; every file green individually)
.venv/bin/python -m pytest tests/unit -q                       # 121 passed
.venv/bin/python -m pytest tests/test_r_func_00_api_behavior.py -q   # 39 passed
.venv/bin/python -m pytest tests/test_r_func_01_agent_behavior.py -q # 12 passed
.venv/bin/python -m pytest tests/test_r_func_02_rag_behavior.py -q   # 14 passed (incl. scenario_14 standalone)
.venv/bin/python -m pytest tests/test_r_func_03_cache_behavior.py -q # passed (1 skip: local Redis absent)
.venv/bin/python -m pytest tests/test_r_func_04_provider_behavior.py -q # 22 passed
.venv/bin/python -m pytest tests/test_r_logic_00..03 ...        # all passed
.venv/bin/python -m pytest tests/evals/...                      # all 13 eval files passed
.venv/bin/python -m pytest tests/contract -q                    # passed
# (all remaining root test files run individually — green; one known WSL-only
#  environment failure: test_local_safe_sandbox_file_and_commands invokes the
#  `python` binary which does not exist in this WSL env; CI runners have it)

# CI-equivalent gates
.venv/bin/python -m ruff check app tests          # All checks passed!
.venv/bin/python -m ruff format --check app tests # 253 files already formatted
.venv/bin/python -m mypy app                      # Success: no issues found in 166 source files
.venv/bin/python -m bandit -r <changed files>     # no findings
.venv/bin/python -m pytest tests/contract/test_api_contract.py -q  # passed
.venv/bin/python -m app.main --export-openapi openapi.json
git diff --exit-code openapi.json                 # no diff (exit 0)
```

**GitHub CI**: run **34759080380** — **GREEN**, 9/9 check runs success (Secrets, Vulnerability/SAST/License, Workflow Linting, Code Quality & Type (3.11 + 3.12), Frontend, Automated Tests & Coverage incl. OpenAPI contract gate ×2, Container Packaging). PR #42 mergeable: **clean**.

## 8. Manual Test Instructions for Human Reviewer

1. **Engine outage (F-01)**: with no provider API keys configured, `POST /api/v1/agent/tasks` with a general goal. Observe the run terminates with `failed` (RunState `FAILED`) — it must NOT complete with the text "Completed step execution.".
2. **Gateway outage + recovery (F-03/04)**: `POST /api/v1/gateway/chat/completions` with the same prompt twice while upstream is unavailable: both responses are labeled `[JakeAI Gateway Response via …]` and `provider_cache.miss_reason == "offline_fallback"`. Restore a valid key, repeat the prompt: the response is the genuine provider answer (`cached=false`), not the cached fallback. After 3 consecutive outages the breaker opens (subsequent outage responses return without provider latency).
3. **Chat stream failure (chat.py path)**: `POST /api/v1/chat/stream` while the workflow raises: client receives an SSE `event: error` frame — never a `done` frame with a fabricated answer.
4. **Corrupt checkpoint**: manually corrupt `agent:checkpoint:rec:{id}` in Redis, then `POST /api/v1/agent/tasks/{task_id}/runs/{run_id}/resume`: response is 404 (`No checkpoint found`), never a fabricated resumed run.
5. **RAG retrieval failure (F-06)**: stop Qdrant and clear the BM25 index file, `POST /api/v1/rag/generate`: response `status=ABSTAINED`, `abstention_reason=RETRIEVAL_FAILURE` (not `NO_RELEVANT_EVIDENCE`).
