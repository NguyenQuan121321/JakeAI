# R-LOGIC-03 — Accounting — Result

**Status**: VERIFIED — all confirmed defects fixed, regression-tested, all CI-equivalent checks green locally. One CI regression (RL03-F-08, Redis-path denial message) caught by run 1 (34751257085), fixed, and **GitHub CI GREEN** on run 2 (34751728486, all 9 check runs success, PR #41 mergeable: clean).
**Baseline**: `main` @ `ea95b07` (post R-LOGIC-02 merge, PR #40)
**Branch**: `chore/r-logic-03-accounting` → PR: see git log / GitHub
**Date**: 2026-09-13

---

## 1. Scope Inspected

Token, quota, cache-saving, provider-billing, cost and budget accounting across:

| Component | File | Classification |
|---|---|---|
| Canonical token accounting (envelope, dimensions, reconciliation, savings) | `backend/app/optimizer/token_accounting.py` | REAL (algorithmic; BPE tokenizer) |
| Budget & quota governance (pre-flight, settlement) | `backend/app/finops/budget.py` | REAL (Redis Lua / memory store) |
| FinOps ledger & summary aggregation | `backend/app/finops/ledger.py` | REAL (in-memory ring buffer) |
| Per-request FinOps record model | `backend/app/finops/models.py` | REAL (Pydantic contracts) |
| Billing reconciler (provider truth) | `backend/app/finops/reconciler.py` | REAL (algorithmic) |
| Non-overlapping savings attribution | `backend/app/finops/attribution.py` | REAL (algorithmic) |
| Pricing catalog & cost formulas | `backend/app/finops/pricing.py`, `app/optimizer/provider_pricing.py` | REAL (static catalog + arithmetic) |
| Unified FinOps service facade | `backend/app/finops/service.py` | REAL |
| Gateway inference proxy (non-stream + SSE stream) | `backend/app/services/ai_gateway.py` | REAL (upstream LLM is MOCK in tests — see §4) |
| Chat SSE endpoint | `backend/app/api/v1/endpoints/chat.py` | REAL (workflow MOCK in tests) |
| Gateway HTTP endpoints | `backend/app/api/v1/endpoints/gateway.py` | REAL (HTTP boundary exercised) |
| FinOps HTTP endpoints | `backend/app/api/v1/endpoints/finops.py` | REAL (HTTP boundary exercised) |

### Execution paths traced end-to-end

1. `POST /api/v1/gateway/chat/completions` (JSON) → `GatewayInferenceProxy.chat_completions` → quota gate → Tier-1 exact cache → BYOK → context optimization → two-zone compile → upstream call → `TokenAccounting.record_transaction` → `FinOpsService.record_upstream_inference` (reconcile + ledger + settlement).
2. `POST /api/v1/gateway/chat/completions` (SSE) → `GatewayInferenceProxy.chat_completions_stream` → quota gate → cache hit / upstream stream → `finally` settlement.
3. `POST /api/v1/chat/stream` → `chat_stream_endpoint` → `generate_chat_stream` (8 terminal paths: guardrail block, cache hit, timeout, disconnect ×2, leak block, normal completion, cancel, exception).
4. `FinOpsBudgetManager.check_budget` / `settle_request` / **new** `reserve_budget` / `finalize_reservation` (Redis Lua + memory critical sections).
5. `BillingReconciler.reconcile` (OpenAI `prompt_tokens` shape and telemetry `uncached_input_tokens` shape).
6. `FinOpsLedger.get_summary` / `get_reconciliation_report` aggregations.
7. `SavingsAttribution` non-overlap validator and attribution cases (cache hit, miss + provider cache, routing).

---

## 2. Findings

### RL03-F-01 — SEVERITY: HIGH — concurrent requests oversubscribe the shared budget (no atomic reservation)

- **EXPECTED**: When N concurrent requests share a tenant budget, the check-and-charge must be atomic: only the requests whose reservations fit the remaining quota are admitted; settled usage never exceeds the quota when actual usage is bounded by the reservation.
- **ACTUAL**: `check_budget` (read) and `settle_request` (increment) are independent non-atomic operations separated by the entire inference. Reproduction: 10 concurrent gateway requests, quota 500, each billing ~300 tokens — **10/10 allowed, 3000 tokens settled (3× oversubscription)**.
- **EVIDENCE**: Repro script output on pristine `main`: `[4] concurrency: allowed=10/10, settled=3000 tokens vs quota=1000`; post-fix: `allowed=4/10, settled=380 tokens vs quota=500`. Regression test `test_concurrent_requests_cannot_oversubscribe_budget`.
- **ROOT CAUSE**: Check-then-act race. The pre-flight check is advisory only; there was no reservation primitive in `FinOpsBudgetManager`.
- **AFFECTED FILES**: `backend/app/finops/budget.py`, `backend/app/services/ai_gateway.py`, `backend/app/api/v1/endpoints/chat.py`, `backend/app/finops/service.py`.
- **AFFECTED EXECUTION PATH**: All inference entry points (`gateway/chat/completions` JSON+SSE, `chat/stream`).
- **FIX**: New `reserve_budget()` — atomic check-and-increment (Lua script `EVAL` against Redis; `threading.Lock`-guarded critical section against the in-memory store, no `await` inside). New `finalize_reservation()` — exactly-once delta settlement (`SET NX` per-reservation marker inside the same Lua script / same memory critical section; repeated finalize can never double-refund or double-charge; clamped so a settlement can never fabricate a negative balance). Gateway JSON, gateway SSE and chat SSE endpoints reserve the model-visible envelope + `max_tokens` completion ceiling up front (429 / in-band `quota_exceeded` on denial) and finalize to provider-truth after inference; cache hits refund the reservation in full. Reservation estimates are upper bounds, so under honest provider reporting settled usage stays within quota; when provider-reported usage exceeds the local estimate, the delta is charged truthfully (provider telemetry takes precedence per W-COST-01) — documented residual risk in §7.
- **REGRESSION TEST**: `test_concurrent_requests_cannot_oversubscribe_budget`, `test_reservation_finalize_charges_actual_not_estimate_plus_actual`, `test_reservation_full_refund_restores_balance`, `test_reservation_boundary_allows_exactly_full_quota`, `test_reservation_denial_messages_match_hard_stop_semantics`, `test_negative_settlement_and_reservation_inputs_rejected`.
- **RETEST RESULT**: PASS — 10 concurrent requests against 500-token quota: 4 admitted, 6 denied with `quota exceeded`, 380 tokens settled (≤ 500). Runs against real Redis 7 in CI (Lua path) and memory store locally, asserted identically.

### RL03-F-02 — SEVERITY: HIGH — `POST /api/v1/chat/stream` never settles quota, dollars, or the FinOps ledger

- **EXPECTED**: Every model-visible billed token consumed via the public chat stream endpoint counts against the tenant's token quota and dollar budget and produces a per-request FinOps ledger record (W-COST-01 accounting dimensions; W-COST-00 single settlement authority).
- **ACTUAL**: The endpoint recorded optimizer telemetry (`TokenAccounting.record_transaction`) but never called any settlement authority: token quota unchanged, $0 settled, zero ledger records — a tenant could consume unlimited inference via streaming while `GET /api/v1/finops/summary` showed nothing. Additionally the **stream-timeout path returned without any accounting at all** (tokens consumed upstream, nothing recorded anywhere), and the leak-block path returned without accounting.
- **EVIDENCE**: `grep settle_request|record_usage app/` shows the chat path had no settlement call site; reproduction `[5b] gateway stream (baseline for /api/v1/chat/stream: no settlement at all)`. Regression tests: `test_chat_stream_http_settles_budget_and_ledger` (HTTP boundary, asserts ledger `total_requests == 1`, settled == record input+output, exactly once), `test_chat_stream_timeout_path_settles_accounting`, `test_chat_stream_guardrail_block_refunds_reservation`, `test_chat_stream_http_hard_stop_denies_with_429`.
- **ROOT CAUSE**: The stream endpoint was wired only to the telemetry layer; the FinOps settlement authority (`FinOpsService`) was never connected (gap recorded but not fixed by R-LOGIC-02 as RL02-O-02/RL02-O-03; unowned until this task).
- **AFFECTED FILES**: `backend/app/api/v1/endpoints/chat.py`.
- **AFFECTED EXECUTION PATH**: All 8 terminal paths of `generate_chat_stream`.
- **FIX**: Single settlement helper `_settle_stream_finops()` (exactly-once per request, failures logged not raised); endpoint performs the atomic reservation (HTTP 429 on hard stop) and passes the handle to the generator; every terminal path finalizes — refunded in full on pre-inference guardrail exit, trued up to actual usage on cache hit (`record_cache_hit`), timeout, disconnects, cancel, exception, leak-block and normal completion.
- **REGRESSION TEST**: See EVIDENCE; all in `backend/tests/test_r_logic_03_accounting.py`.
- **RETEST RESULT**: PASS (21/21 new tests green).

### RL03-F-03 — SEVERITY: MEDIUM — gateway SSE stream settled token counts only: $0 dollars, no FinOps ledger, cache hits recorded nothing

- **EXPECTED**: Streamed inference settles estimated dollars (pricing-catalog based, `is_estimate=True` since no provider telemetry) and writes a FinOps record; stream cache hits record `record_cache_hit` like the non-stream path (RL02-O-03).
- **ACTUAL**: `chat_completions_stream` called `QuotaManager.record_usage` (token-only absolute increment). Dollar budgets were bypassable entirely via streaming; `/api/v1/finops/summary` showed zero requests for streamed traffic; stream cache hits recorded no ledger entry.
- **EVIDENCE**: Baseline repro `[5b] tokens_used=86 dollars_spent=0.0 finops_ledger_requests=(0, 0.0)`; post-fix `dollars_spent=1.3e-05 finops_ledger_requests=(1, 1.3e-05)`.
- **ROOT CAUSE**: Stream path predated the unified settlement facade and kept a legacy token-only shortcut.
- **AFFECTED FILES**: `backend/app/services/ai_gateway.py`.
- **AFFECTED EXECUTION PATH**: `GatewayInferenceProxy.chat_completions_stream` (cache-hit and miss branches).
- **FIX**: Stream settlement routed through `FinOpsService.record_upstream_inference` (miss) / `record_cache_hit` (hit), finalizing the reservation; settlement failures logged, never swallowed silently.
- **REGRESSION TEST**: `test_gateway_stream_settles_dollars_and_ledger`, `test_gateway_stream_cache_hit_records_ledger_and_refunds`.
- **RETEST RESULT**: PASS.

### RL03-F-04 — SEVERITY: MEDIUM — client-facing `usage.total_tokens` was the provider-cache discount equivalent, not prompt + completion

- **EXPECTED**: OpenAI-compatible responses report `usage.total_tokens == prompt_tokens + completion_tokens`; the amount settled against quota is the provider-reported total (provider truth).
- **ACTUAL**: With provider prompt-cache telemetry (`cached_tokens=3000, uncached=1500, output=250`, claude-3-5-sonnet) the response reported `prompt=4500, completion=250, total=2050` (discount equivalent) while quota settled 4750 (provider truth) — three mutually inconsistent numbers in one transaction.
- **EVIDENCE**: Baseline repro `[6] usage: prompt=4500 completion=250 total=2050 prompt+completion=4750`; post-fix `total=4750` and settled == 4750.
- **ROOT CAUSE**: The response mapped `record.actual_billed_tokens` (the discount-equivalent savings basis) into the OpenAI `usage.total_tokens` field.
- **AFFECTED FILES**: `backend/app/services/ai_gateway.py`, `backend/app/optimizer/token_accounting.py` (documentation).
- **AFFECTED EXECUTION PATH**: `GatewayInferenceProxy.chat_completions` response construction.
- **FIX**: `usage.total_tokens = optimized_input_tokens + completion_tokens` (self-consistent, equals the settled provider-reported total when reconciled). `TokenUsageRecord.effective_billed_tokens` retained as the discount-equivalent savings basis with a corrected field description (conservation invariant `baseline == effective_billed + saved` and the ≥40% benchmark gate are unchanged).
- **REGRESSION TEST**: `test_gateway_usage_total_equals_prompt_plus_completion` (asserts total == prompt+completion == settled usage).
- **RETEST RESULT**: PASS.

### RL03-F-05 — SEVERITY: MEDIUM — zero/negative token values produced false savings and fabricated refunds

- **EXPECTED**: A zero-token transaction reports zero savings; negative token inputs are rejected; settlements can never be negative.
- **ACTUAL**: `record_transaction(raw=0, opt=0, completion=0)` reported `tokens_saved=1, reduction=100%` (false savings off the `max(1, …)` division guard). Negative inputs were accepted wholesale: `record_transaction(raw=-100, opt=-50, completion=-10)` produced `effective_billed_tokens=-60` — settling that would *decrement* the tenant's usage (quota refund fabrication); `settle_request` accepted negative amounts.
- **EVIDENCE**: Baseline repro `[1] saved=1 reduction=100.0%`, `[2] billed=-60 saved=61`; post-fix `[1] saved=0 reduction=0.0%`, `[2] rejected with ValidationError`.
- **ROOT CAUSE**: No domain constraints on `TokenUsageRecord` numeric fields and no input validation in `settle_request`.
- **AFFECTED FILES**: `backend/app/optimizer/token_accounting.py`, `backend/app/finops/budget.py`.
- **AFFECTED EXECUTION PATH**: `TokenAccounting.record_transaction` (all callers), `FinOpsBudgetManager.settle_request` / `reserve_budget` / `finalize_reservation`.
- **FIX**: `ge=0` constraints on all 14 token-count fields of `TokenUsageRecord` (Pydantic validation rejects negatives at the ledger boundary); explicit zero-work branch reporting 0 saved / 0% instead of a fabricated 100%; `ValueError` on negative settlement/reservation/finalize inputs (finalize deltas may legitimately be negative — refunds — only *actuals* are validated).
- **REGRESSION TEST**: `test_zero_token_request_reports_no_false_savings`, `test_zero_token_cache_hit_reports_no_false_avoidance`, `test_negative_token_values_rejected_everywhere`, `test_negative_settlement_and_reservation_inputs_rejected`, `test_very_large_token_values_settle_and_deny`, `test_rounding_boundaries_reduced_to_declared_precision`.
- **RETEST RESULT**: PASS.

### RL03-F-06 — SEVERITY: LOW — reconciler let stale local cache assumptions override an explicit provider-reported zero

- **EXPECTED**: Provider-reported usage is authoritative; an explicitly reported `cached_tokens: 0` must win over any local fallback.
- **ACTUAL**: `provider_usage.get("cached_tokens") or … or cached_tokens_param` treated explicit `0` as missing and fell through to the stale local assumption (repro: provider says 0 cached, local assumed 3000 → reconciler used 3000, inflating cache savings and mispricing the transaction).
- **EVIDENCE**: Baseline repro `[3] provider_cached=3000`; post-fix `provider_cached=0`.
- **ROOT CAUSE**: `or`-chain conflates "key absent" with "explicit zero".
- **AFFECTED FILES**: `backend/app/finops/reconciler.py`.
- **AFFECTED EXECUTION PATH**: `BillingReconciler.reconcile` (all shapes).
- **FIX**: Presence-based extraction (`_prov_int`: explicit key → explicit zero wins; fallback only when the key is genuinely absent) applied consistently to cached/uncached/completion/total/write tokens.
- **REGRESSION TEST**: `test_provider_explicit_zero_cached_wins_over_local_assumption` (also asserts the billed cost matches the zero-cached pricing).
- **RETEST RESULT**: PASS.

### RL03-F-07 — SEVERITY: LOW — settlement failures were silently swallowed on the gateway non-stream path

- **EXPECTED**: A settlement failure after successful inference is observable (logged) and cannot silently under-count usage.
- **ACTUAL**: `contextlib.suppress(Exception)` around `record_upstream_inference` hid every settlement error.
- **EVIDENCE**: Code inspection (`ai_gateway.py`, pre-fix line ~571).
- **ROOT CAUSE**: Suppression used as error handling.
- **AFFECTED FILES**: `backend/app/services/ai_gateway.py`.
- **AFFECTED EXECUTION PATH**: `GatewayInferenceProxy.chat_completions` settlement step.
- **FIX**: Replaced with `try/except` + `logger.exception` (behavior preserved: the response is still returned; with the reservation flow a failed finalize leaves the reservation counted — conservative direction, never free usage).
- **REGRESSION TEST**: Covered indirectly by `test_gateway_usage_total_equals_prompt_plus_completion` (settlement success path asserted exactly-once); failure-path logging is standard logging, not assertable without log capture (accepted).
- **RETEST RESULT**: PASS.

---

## 3. Conservation & Double-Counting Verification

- `raw_input_tokens == optimized_input_tokens + physical_tokens_pruned` holds on all miss paths, including provider-telemetry reconciliation (reconciliation rewrites `raw = provider_input + prior_pruned`). Covered by existing `test_conservation_of_tokens_invariant` (green) and new tests.
- `baseline_total == effective_billed_tokens + tokens_saved` (savings view) covered by existing conservation test (green).
- Exactly-once settlement proven at three boundaries: service (`test_provider_reported_total_settled_exactly_once`), gateway non-stream (`test_gateway_usage_total_equals_prompt_plus_completion`: used == usage.total == 4750), gateway stream and chat stream (`used == record.optimized_tokens + record.output_tokens`).
- No negative balances: refunds clamp at zero and are exactly-once (`test_reservation_full_refund_restores_balance`, finalize `SET NX` marker).
- Attribution non-overlap: existing validator tests green; summary attribution sums unchanged.

## 4. REAL / RULE-BASED / MOCK / NOT VERIFIED classification of this verification

| What was exercised | Classification |
|---|---|
| HTTP boundary: real FastAPI app via ASGI transport, real JWT auth, real quota reservation & settlement, real guardrails, real FinOps ledger | **REAL** |
| Quota atomicity: real asyncio concurrency; Redis Lua path executes against **real Redis 7 in CI** (service container), memory path locally | **REAL in CI / REAL (memory) locally** |
| Provider-reported usage reconciliation: controlled `ProviderCacheTelemetry` fixtures at the exact reconciliation boundary (provider HTTP not called) | **RULE-BASED / controlled integration** — reconciler + pricing math are real; live provider payloads not captured (see NOT VERIFIED) |
| Upstream LLM in gateway/chat tests | **MOCK** (mocked `call_upstream_llm*` / workflow) — proves accounting wiring, not live provider integration |
| Live commercial provider end-to-end billing (real OpenAI/Anthropic usage payloads incl. cache_creation fields) | **NOT VERIFIED** (no live keys in CI; identical gap was declared in RIGHT-00 §11 CLASS D) |

## 5. Tests Executed

New: `backend/tests/test_r_logic_03_accounting.py` — 21 tests (unit edge values; service-level reservation/finalize/refund semantics; real-asyncio concurrency; HTTP-boundary stream settlement, 429 hard stop, timeout settlement, guardrail refund; OpenAI usage consistency).

Existing suites rerun (selection per WSL 3.8 GB OOM constraint; full single-process suite is a known local env failure, green in CI):

| Suite | Result |
|---|---|
| `tests/test_r_logic_03_accounting.py` | 21 passed |
| `tests/test_finops_accounting.py` `tests/test_finops_endpoints.py` `tests/unit/test_canonical_token_accounting.py` | 40 passed |
| `tests/test_gateway.py` `tests/test_openai_compatibility.py` `tests/test_phase07_production_hardening.py` | 63 passed |
| `tests/test_cross_tier_pipeline.py` `tests/test_endpoints.py` `tests/test_multi_agent.py` `tests/test_r_func_00_api_behavior.py` | 77 passed |
| `tests/test_r_logic_00_invariants.py` `tests/test_r_logic_01_state_transitions.py` `tests/test_r_logic_02_data_flow.py` | 109 passed (with the 3 above = 109 total incl. finops chunk) |
| `tests/test_architecture_invariants.py` `tests/test_commercial_services.py` `tests/test_harmonization.py` | 19 passed |
| `tests/test_provider_prompt_caching.py` `tests/test_r_func_04_provider_behavior.py` | 32 passed |
| `tests/test_r_func_01_agent_behavior.py` | 12 passed |
| `tests/test_r_func_02_rag_behavior.py` | 14 passed (env-chunked; pristine-main OOM kill at 3.8 GB WSL limit = ENVIRONMENT FAILURE, documented in RIGHT-00/memory) |
| `tests/test_r_func_03_cache_behavior.py` | 72 passed, 2 skipped (Redis-gated locally, run in CI) |
| `tests/contract/` (incl. internal mutual auth + API contract) | 12 passed |
| `tests/evals/test_token_benchmark.py` | 3 passed (≥40% gate) |
| `tests/evals/test_portfolio_benchmark.py` + `scripts/run_ai_evaluation.py` | PASSED all gates |
| `tests/evals/test_rag_regression.py` `test_rag_metrics.py` `test_canary_leakage.py` `test_llm_judge_and_generation.py` `test_baseline_and_regression_gate.py` | 24 passed |

## 6. Exact Commands

```bash
# Reproductions (baseline on main, then re-run post-fix)
cd backend && .venv/bin/python /tmp/rl03_repro.py

# Regression + affected suites (chunked; full-suite single process OOMs in 3.8 GB WSL)
.venv/bin/python -m pytest tests/test_r_logic_03_accounting.py -p no:cacheprovider --tb=short -q
.venv/bin/python -m pytest tests/test_finops_accounting.py tests/test_finops_endpoints.py tests/unit/test_canonical_token_accounting.py -p no:cacheprovider --tb=short -q
.venv/bin/python -m pytest tests/test_gateway.py tests/test_openai_compatibility.py tests/test_phase07_production_hardening.py -p no:cacheprovider --tb=short -q
.venv/bin/python -m pytest tests/test_cross_tier_pipeline.py tests/test_endpoints.py tests/test_multi_agent.py tests/test_r_func_00_api_behavior.py -p no:cacheprovider --tb=short -q
.venv/bin/python -m pytest tests/test_r_logic_00_invariants.py tests/test_r_logic_01_state_transitions.py tests/test_r_logic_02_data_flow.py -p no:cacheprovider --tb=short -q
.venv/bin/python -m pytest tests/test_r_func_02_rag_behavior.py -k "scenario_08 or … or scenario_12" -q   # env-chunked (OOM split)
.venv/bin/python -m pytest tests/contract -p no:cacheprovider -q
.venv/bin/python -m pytest tests/evals/test_token_benchmark.py tests/evals/test_portfolio_benchmark.py -p no:cacheprovider -q

# CI-equivalent quality gates
.venv/bin/ruff check . && .venv/bin/ruff format --check .
.venv/bin/mypy --config-file mypy.ini app
.venv/bin/bandit -c pyproject.toml -r app/finops app/services/ai_gateway.py app/api/v1/endpoints/chat.py app/optimizer/token_accounting.py
.venv/bin/python -m app.main --export-openapi /tmp/openapi_rl03.json && diff -q openapi.json /tmp/openapi_rl03.json   # no drift
.venv/bin/python scripts/check_openapi_breaking_changes.py                                                            # PASSED
.venv/bin/python scripts/run_ai_evaluation.py --output-dir /tmp/rl03-benchmark                                        # PASSED all gates
```

**Actual results**: all commands green locally; `102 passed` on the combined core chunk; OpenAPI zero drift (no response-model changes → no `openapi.json` regeneration needed). CI: run 1 caught RL03-F-08 (fixed), run 2 green.

## 7. Remaining Issues & Risks

1. **NOT VERIFIED — live provider billing payloads**: reconciliation was proven against controlled provider-shaped telemetry, not captured live OpenAI/Anthropic usage JSON (no live keys in CI). Risk: provider field-name drift (e.g. Anthropic `cache_creation_input_tokens`) is handled explicitly in the reconciler, but a new provider shape would need a reconciler extension. Inherited CLASS-D gap from RIGHT-00; unchanged by this task.
2. **Reservation estimate vs provider truth**: reservations are upper bounds on what JakeAI controls (model-visible envelope + `max_tokens`). If a provider reports *more* input tokens than the local envelope (provider-side overhead), the finalize delta is charged truthfully and can push settled usage slightly past the quota. This is the spec-mandated direction (provider telemetry wins); it cannot oversubscribe beyond the per-request delta.
3. **Reservation leak on abandoned streams**: if a client never iterates the SSE response after the endpoint reserved, the reservation stays counted (conservative; no refund). No oversubscription risk; only over-counting for abandoned requests.
4. **RL02-O-07 (cross-cutting, unresolved)**: `POST /api/v1/gateway/quotas` and `POST /api/v1/finops/budget` still lack permission enforcement (`require_permissions` unused) — any authenticated tenant can raise its own quota, which now also grants reservation headroom. Ownership: architecture/authorization task; recorded, not changed here.
5. **Redis/memory split-brain**: if Redis flaps mid-request between reserve and finalize, delta bookkeeping can drift between stores. Read path prefers Redis; failure modes remain conservative (over-count, never free usage). Accepted.
6. **`FinOpsLedger` is per-process memory** (bounded ring buffer); ledger contents are not shared across Uvicorn workers. Quota/budget counters (the enforcement state) are Redis-atomic; ledger analytics are per-worker. Pre-existing architecture item (RISK-02/R-ARCH scope), unchanged here.

## 8. Security & Business Impact

- **Security**: positive — quota/dollar hard stops are now enforced on every public inference path (streaming previously bypassed dollar budgets entirely; `/api/v1/chat/stream` bypassed all budget enforcement); negative-settlement (refund fabrication) is rejected at the boundary. No new attack surface; bandit clean; no secrets introduced.
- **Business**: prevents revenue loss from unbilled streamed usage and quota oversubscription under concurrency; provider-truth settlement preserves correct customer billing; false savings (100% reduction on empty requests) eliminated so benchmark claims stay honest.

## 9. Manual Test Instructions for the Human Reviewer

```bash
cd backend && uv run uvicorn app.main:app --host 0.0.0.0 --port 8000
```

1. **Quota hard stop (gateway, non-stream)** — with a tenant JWT:
   `POST /api/v1/finops/budget {"token_quota": 30000}` → `POST /api/v1/gateway/chat/completions {"model":"gemini-1.5-flash","messages":[{"role":"user","content":"hello"}],"max_tokens":2048}`.
   Repeat until `GET /api/v1/gateway/quotas` shows `tokens_used` near the limit; the next call must return **HTTP 429** with `Monthly token quota exceeded`.
2. **Cache hit refunds** — send the identical gateway request twice with a small quota: the first settles usage (check `GET /api/v1/gateway/quotas`), the second returns `"cached": true` and leaves `tokens_used` **unchanged** (full refund), and `GET /api/v1/finops/summary` gains a cache-hit record.
3. **Stream settlement & dollar budget** — set `{"dollar_budget_usd": 0.0001, "token_quota": 1000000}`, then `POST /api/v1/chat/stream {"prompt": "Explain gross margin"}`: expect **HTTP 429** (dollar budget exceeded) — pre-fix this endpoint ignored dollar budgets entirely. Then raise the dollar budget and stream again; `GET /api/v1/finops/summary` must show ≥1 request with nonzero `total_actual_cost_usd`, and `GET /api/v1/finops/budget` must show tokens_used > 0.
4. **Concurrent oversubscription** — set quota 500, then fire ~10 parallel `POST /api/v1/gateway/chat/completions` (same tenant, `max_tokens: 64`): only the first few should succeed (200), the rest 429, and `GET /api/v1/gateway/quotas` must show `tokens_used ≤ 500`.
5. **Usage consistency** — on any non-cached gateway response, assert `usage.total_tokens == usage.prompt_tokens + usage.completion_tokens` and that `GET /api/v1/gateway/quotas` `tokens_used` increased by exactly that total.

### RL03-F-08 — SEVERITY: LOW — (CI regression, fixed) Redis denial results mislabeled the fired constraint

- **EXPECTED**: The Lua reserve contract `{allowed, tok_used, tok_limit, dol_spent, dol_limit}` uses `-1` as the "no dollar limit" sentinel; a token-quota denial must produce the token-quota denial message.
- **ACTUAL (CI run 34751257085, Python 3.11, real Redis)**: `test_reservation_denial_messages_match_hard_stop_semantics` failed — the token-quota denial produced "Monthly dollar budget exceeded ($0.0000/$-1.00 USD)". Only reachable on the Redis path (the memory path passes `None`), which is why local runs were green. **Classification: CURRENT TASK REGRESSION** (1 failed / 916 passed; all other jobs green).
- **ROOT CAUSE**: The Python-side denial branch passed the `-1.0` sentinel into `_denial_message` instead of mapping it to `None`.
- **FIX**: Map the sentinel to `None` in the Redis denial branch (`dol_limit_r if dol_limit_r >= 0 else None`), plus two contract-pinning tests (`test_redis_lua_denial_results_map_to_correct_messages`, `test_redis_lua_granted_result_builds_reservation`) exercising the exact Lua result shapes without requiring Redis locally.
- **REGRESSION TEST**: The two Lua-contract tests above.
- **RETEST RESULT**: PASS — post-fix CI run recorded in §10.

## 10. CI Status

| Check | Result |
|---|---|
| Run 1 — 34751257085 (8 check runs before fix) | 7 green; **Automated Tests (3.11) FAILED** → RL03-F-08 (CURRENT TASK REGRESSION, 1 failed / 916 passed); 3.12 cancelled by needs |
| Run 2 — 34751728486 attempt 1 | 8/9 jobs green; the 3.11 test job stalled >50 min inside the pytest coverage step on its runner (no test output; identical suite passed on 3.12 in 1.7 min). **ENVIRONMENT/INFRA STALL** — cancelled and re-run on fresh runners |
| Run 2 — 34751728486 attempt 2 (final) | **GREEN — all 9 check runs success**: Automated Tests & AI RAG Regression 3.11 AND 3.12 (real Redis 7 Lua reservation path, ≥85% coverage + patch gates), Token Optimization ≥40% gate, Phase 00 AI Evaluation gate, Internal Mutual Auth, RAG Quality, LLMOps Safety, OpenAPI contract & breaking-change, Ruff/Mypy/Bandit/pip-audit/licenses/gitleaks/hadolint/actionlint, frontend build, container build + Trivy |

---

**STOP**: R-LOGIC-03 verification complete. No further RIGHT tasks executed.
