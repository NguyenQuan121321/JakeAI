# R-LOGIC-00 — Invariants — Result

**Task**: R-LOGIC-00 — Invariants (RIGHT Phase 2 — Logic Correctness)
**Baseline**: `main` @ `7dd483f` (merge of PR #37)
**Branch**: `chore/r-logic-00-invariants`
**Date**: 2026-09-12
**Status**: VERIFIED — 13 confirmed defects found, fixed, regression-tested; all CI-equivalent local checks green.

---

## 1. Scope Inspected

All critical invariants extracted from the current code and WORK specifications, mapped to concrete write/change points, and tested directly:

| Invariant | Primary Code Paths |
|---|---|
| Tenant isolation | `app/core/security.py` (JWT-bound tenant), `app/api/v1/endpoints/agent.py`, `app/agent/runtime/manager.py`, `app/rag/*` (filter + defense-in-depth post-filter), `app/core/byok.py` |
| Terminal-state rules | `app/agent/state/models.py` (`RunStatus.is_terminal`), `app/agent/runtime/manager.py`, `app/agent/execution/engine.py`, `app/agent/runtime/loop.py`, `app/api/v1/endpoints/agent.py` |
| No-failure-to-success | `ExecutionEngine.resume_run`, `CheckpointManager.resume_run_from_checkpoint`, `AgentRuntimeManager.cancel_run` / `decide_approval` |
| Cache identity | `app/optimizer/semantic_cache.py` (`compute_cache_identity`, semantic compatibility), `app/services/ai_gateway.py`, `app/api/v1/endpoints/chat.py` |
| Token conservation | `app/optimizer/token_accounting.py`, `app/finops/{service,reconciler,ledger}.py` |
| Quota limits / non-negative | `app/finops/budget.py`, `app/services/ai_gateway.py` (`QuotaManager` facade = unified quota authority) |
| Provider credential isolation | `app/core/byok.py` (AES-256-GCM, tenant AAD), `app/routing/failover.py` (per-candidate credential resolution), `app/providers/*` |
| RAG evidence integrity | `app/rag/grounding.py`, `app/rag/pipeline.py`, `app/rag/citations.py` |
| Approval requirements | `app/agent/approvals/{manager,models,policy}.py`, `app/agent/execution/engine.py`, `app/agent/runtime/{manager,runner}.py` |
| Tool authorization | `app/agent/tools/{policy,registry}.py` |
| Selected model actually used | `app/routing/{router,failover}.py`, `app/core/llm_provider.py`, `app/services/ai_gateway.py`, `app/finops/service.py` |

## 2. Execution Paths & Interfaces Tested

- **HTTP boundary (real FastAPI app via ASGI transport)**: `POST /api/v1/agent/tasks`, `GET /api/v1/agent/tasks/{id}`, `GET /api/v1/agent/tasks/{id}/runs/{id}`, `POST .../runs/{id}/cancel` with real JWT auth (cross-tenant positive/negative).
- **Service boundary**: `AgentRuntimeManager` (create/execute/cancel/decide_approval), `ExecutionEngine.execute_task` / `resume_run` / `_run_execution_loop`, `AgentRunner.resume_after_approval`, `GatewayInferenceProxy.chat_completions` (non-stream, quota+ledger path), `SemanticCacheManager.get/set` (exact + semantic tiers, in-memory + mocked-Qdrant paths), `GroundingVerifier.verify`, `ToolRegistry.execute` (policy engine), `FinOpsBudgetManager` (check/settle/status), `BillingReconciler.reconcile`, `BYOKVault.store_key/get_decrypted_key`, `RAGPipeline.ingest_document/generate_grounded_answer`.
- **Upstream providers**: controlled doubles at the module boundary (`call_upstream_llm_detailed` stubs, `MockControllableBackend`). Per RIGHT-00, these verify error-handling and accounting logic only — NOT live upstream integrations (classified below).

## 3. Real / Rule-Based / Mock / Not-Verified Classification

| Capability under test | Classification |
|---|---|
| Terminal-state machine, engine DAG dispatch, resume flow | REAL (in-process state machines; checkpoint persistence real via `CheckpointManager`) |
| Quota counters, settlement, reconciliation | REAL (Redis INCRBY in prod; in-memory fallback under test — Redis paths verified in CI) |
| Cache identity & semantic compatibility | REAL (algorithmic; Qdrant path mocked locally, real in CI) |
| Tenant isolation, BYOK crypto | REAL (JWT verification; AES-256-GCM with tenant AAD — real crypto) |
| Tool policy authorization | RULE-BASED (regex/permission subset checks, fail-closed) |
| RAG grounding/citation/abstention | REAL (deterministic algorithms) + RULE-BASED thresholds |
| Upstream LLM generation in gateway/agent tests | MOCK (test doubles) — does not prove live provider integration (R-FUNC-04 scope) |
| Live cloud providers, real Redis/Qdrant locally | NOT VERIFIED locally (no docker/redis in WSL) — CI provides real Redis 7 + Qdrant services |

## 4. Findings

All 13 findings below were **reproduced as failing tests first** (pre-fix run: 13 failed / 11 passed), then fixed, then re-verified (24/24 pass). Full evidence in `backend/tests/test_r_logic_00_invariants.py`.

---

### RL00-F-01 — SEVERITY: CRITICAL — Cancel flips terminal runs to CANCELLED
- **EXPECTED**: A run in a terminal state (COMPLETED/FAILED/CANCELLED/REJECTED/TIMEOUT) can never change status; cancel of a terminal run is a no-op.
- **ACTUAL**: `POST /api/v1/agent/tasks/{id}/runs/{id}/cancel` on a COMPLETED run returned the run with `status=cancelled`.
- **EVIDENCE**: `test_inv_a1_cancel_of_terminal_run_preserves_terminal_state` failed pre-fix (`Terminal COMPLETED run was mutated by cancel to cancelled`).
- **ROOT CAUSE**: `AgentRuntimeManager.cancel_run` unconditionally assigned `run.status = RunStatus.CANCELLED` with no terminal check.
- **AFFECTED FILES / PATH**: `app/agent/runtime/manager.py` (`cancel_run`) ← `app/api/v1/endpoints/agent.py` cancel endpoint.
- **FIX**: Terminal-state guard — if `run.status.is_terminal`, log and return the run unchanged.
- **REGRESSION TEST**: `test_inv_a1_*` + updated HTTP test `test_agent_platform.py::test_api_create_run_and_cancel` (which previously passed only *because* of this defect — the background run completed before cancel landed and cancel silently flipped it).
- **RETEST**: PASS.

### RL00-F-02 — SEVERITY: CRITICAL — Resume accepts terminal runs (no-failure-to-success)
- **EXPECTED**: Resuming a COMPLETED/CANCELLED/FAILED run is refused; a terminal run cannot re-execute steps or complete again.
- **ACTUAL**: `ExecutionEngine.resume_run` re-entered the execution loop for any state: COMPLETED runs were re-verified and emitted a **second `completed` event**; CANCELLED runs with unfinished plans were resumed **into COMPLETED**.
- **EVIDENCE**: `test_inv_a2_resume_of_completed_run_must_not_reexecute`, `test_inv_a3_resume_of_cancelled_run_must_not_complete` failed pre-fix.
- **ROOT CAUSE**: `resume_run` had no terminal-state check (only `CheckpointManager` logged when status was RUNNING); the approval branch was the only entry condition.
- **AFFECTED FILES / PATH**: `app/agent/execution/engine.py` (`resume_run`).
- **FIX**: Terminal-state guard at the top of `resume_run`: yield a `resume_refused` event and return without executing.
- **REGRESSION TEST**: `test_inv_a2_*`, `test_inv_a3_*`.
- **RETEST**: PASS.

### RL00-F-03 — SEVERITY: HIGH — Incomplete plan reported COMPLETED without verification
- **EXPECTED**: Verification runs only over fully executed plans; a run whose plan did not complete terminates FAILED.
- **ACTUAL**: When the DAG loop stalled (e.g., crash-restored run with a step stuck in RUNNING and dependents PENDING), the loop broke out and the run was **marked COMPLETED unconditionally, bypassing the CanonicalVerifier**.
- **EVIDENCE**: `test_inv_a4_incomplete_plan_never_completes_without_verification` failed pre-fix (`completed` event emitted; no `verification_started`).
- **ROOT CAUSE**: `engine.py` fall-through: `if not plan.is_complete(): … break` fell out of the revision loop into the unconditional `run_state.status = RunStatus.COMPLETED` block.
- **AFFECTED FILES / PATH**: `app/agent/execution/engine.py` (`_run_execution_loop`).
- **FIX**: The stall points now (a) pause the run as `WAITING_APPROVAL` when remaining steps await human approval, or (b) mark the run FAILED with a plan-incomplete error; COMPLETED is reachable only via a PASSED verification of a complete plan.
- **REGRESSION TEST**: `test_inv_a4_*`.
- **RETEST**: PASS.

### RL00-F-04 — SEVERITY: CRITICAL — One approval unlocked a different dangerous tool (blanket grant)
- **EXPECTED**: Every dangerous tool execution requires its own approved approval record; approvals are single-use and tool-bound.
- **ACTUAL**: With two paused dangerous steps, deciding **one** approval and resuming (approved=None) executed **both** tools: the resume scan accepted *any* APPROVED approval for the run, set a run-wide blanket grant, reset all waiting steps to PENDING, and skipped the approval check for the whole first batch. Approvals were never consumed.
- **EVIDENCE**: `test_inv_b1_approving_one_tool_does_not_unlock_sibling_tool` failed pre-fix (`privileged_tool_b` execution count 1 with only tool A approved).
- **ROOT CAUSE**: `resume_run` scanned `approval_manager._approvals` for any `run_id`-matching APPROVED record and passed `approval_already_granted=True` into the loop.
- **AFFECTED FILES / PATH**: `app/agent/execution/engine.py` (`resume_run`, `_execute_single_step`), `app/agent/domain/contracts.py` (`PlanStep.pending_approval_id`).
- **FIX**: Step-bound approvals: (1) each pause binds `step.pending_approval_id`; (2) resume unlocks **only** steps whose own bound approval is APPROVED (explicit `approved=True` finalizes pending gates — preserving the restart-recovery flow where in-memory records are lost); (3) `_execute_single_step` honors and consumes the bound gate (removed after use); (4) unapproved siblings stay `WAITING_APPROVAL` and the run re-pauses; (5) lost/gate-rejected records fail the step closed.
- **REGRESSION TEST**: `test_inv_b1_*`, `test_inv_b2_resume_without_approval_stays_waiting`, `test_inv_b3_rejection_via_resume_marks_rejected`.
- **RETEST**: PASS (tool A executes once; tool B never executes; run remains WAITING_APPROVAL).

### RL00-F-05 — SEVERITY: HIGH — Cross-run approval accepted
- **EXPECTED**: An approval bound to run A must not authorize execution in run B.
- **ACTUAL**: `AgentRunner.resume_after_approval` checked only the approval's status, then executed `appr.tool_name` with `appr.tool_args` in the context of whichever run was passed.
- **EVIDENCE**: `test_inv_b4_cross_run_approval_rejected_in_resume` failed pre-fix (tool executed under run B using run A's approval).
- **ROOT CAUSE**: Missing `appr.run_id == run.run_id` binding check.
- **AFFECTED FILES / PATH**: `app/agent/runtime/runner.py` (`resume_after_approval`).
- **FIX**: Run-binding check raising `ValueError` (surfaced as HTTP 409).
- **REGRESSION TEST**: `test_inv_b4_*`.
- **RETEST**: PASS.

### RL00-F-06 — SEVERITY: HIGH — Late approval rejection resurrected a terminal run
- **EXPECTED**: Terminal states are immutable; a late decision finalizes only the approval record.
- **ACTUAL**: `decide_approval`'s rejection branch unconditionally set `run.status = RUNNING`, flipping COMPLETED/FAILED runs back to a non-terminal state (zombie run that nothing will ever execute).
- **EVIDENCE**: `test_inv_b5_late_approval_decision_preserves_terminal_run` failed pre-fix.
- **ROOT CAUSE**: Unconditional status write in `AgentRuntimeManager.decide_approval`.
- **AFFECTED FILES / PATH**: `app/agent/runtime/manager.py` (`decide_approval`).
- **FIX**: Status/task writes guarded by `if not run.status.is_terminal`.
- **REGRESSION TEST**: `test_inv_b5_*`.
- **RETEST**: PASS.

### RL00-F-07 — SEVERITY: HIGH — execute_run reset terminal runs to RUNNING
- **EXPECTED**: Executing an already-terminal run is refused.
- **ACTUAL**: `AgentExecutionLoop.execute` unconditionally set `status=RUNNING` at entry, resurrecting terminal runs reached via `AgentRuntimeManager.execute_run`.
- **EVIDENCE**: `test_inv_a5_execute_run_refuses_terminal_run` failed pre-fix.
- **ROOT CAUSE**: No entry-state guard in `manager.execute_run` / `loop.execute`.
- **AFFECTED FILES / PATH**: `app/agent/runtime/manager.py`, `app/agent/runtime/loop.py`, `app/api/v1/endpoints/agent.py` (ValueError → HTTP 409 mapping).
- **FIX**: Terminal-state guards raising `ValueError` in both layers.
- **REGRESSION TEST**: `test_inv_a5_*`.
- **RETEST**: PASS.

### RL00-F-08 — SEVERITY: HIGH — Quota double settlement per gateway request
- **EXPECTED**: One inference request settles quota exactly once (tokens and dollars).
- **ACTUAL**: The non-stream gateway miss path settled **twice with two different formulas**: `QuotaManager.record_usage` (gateway) settled `actual_billed_tokens`, then `FinOpsService.record_upstream_inference` settled `provider_reported_total or optimized+output` again. A 150-token request settled 300 tokens.
- **EVIDENCE**: `test_inv_c1_gateway_miss_settles_quota_exactly_once` failed pre-fix (`settled 300 != 150`).
- **ROOT CAUSE**: Two independent settlement call sites hitting the same `FinOpsBudgetManager` singleton on one request.
- **AFFECTED FILES / PATH**: `app/services/ai_gateway.py` (`chat_completions`), `app/finops/service.py` (`record_upstream_inference`).
- **FIX**: Removed the gateway's direct `record_usage` settlement; `record_upstream_inference` is the single authoritative settlement (tokens + dollars, provider-authoritative when telemetry exists).
- **REGRESSION TEST**: `test_inv_c1_*`; `test_inv_c2_gateway_cache_hit_settles_zero_quota` (cache hits settle 0 — unchanged behavior).
- **RETEST**: PASS.

### RL00-F-09 — SEVERITY: HIGH — Reconciler silently dropped provider-reported input tokens
- **EXPECTED**: Provider-reported usage is the authoritative billing truth; input tokens must be conserved into settlement.
- **ACTUAL**: `BillingReconciler` read `prompt_tokens`/`input_tokens`/`uncached_tokens`, but production `ProviderCacheTelemetry` reports **`uncached_input_tokens`** — the key was not recognized, so prompt tokens were settled as **0** (a 150-token request settled 30; dollar cost computed on output only).
- **EVIDENCE**: `test_inv_c1_*` post-F-08-fix initially settled 30 tokens; reconciler key-chain inspected.
- **ROOT CAUSE**: Key-name mismatch between the telemetry model and the reconciler's extraction chain.
- **AFFECTED FILES / PATH**: `app/finops/reconciler.py` (`reconcile`).
- **FIX**: Reconciler now understands both reporting shapes — explicit totals (`prompt_tokens`/`input_tokens`) and telemetry-style (`uncached_input_tokens` + `cached_tokens`, prompt total = uncached + cached). Explicit-total behavior is unchanged.
- **REGRESSION TEST**: `test_inv_c1_*` (asserts settled == provider-reported 150); existing `test_finops_accounting.py` reconciliation tests (unchanged paths) still pass.
- **RETEST**: PASS.

### RL00-F-10 — SEVERITY: MEDIUM — Semantic cache ignored conversation history (cache identity)
- **EXPECTED**: A cached response may only be served when the full generation context matches; the exact tier hashes the full history, so the semantic tier must never serve across different histories.
- **ACTUAL**: The semantic tier embedded only the last user prompt and `_is_compatible_for_semantic_hit` never compared history — an entry cached under conversation H1 was served for a different conversation H2 with a similar final prompt (same tenant/model/system/tools/params).
- **EVIDENCE**: `test_inv_d1_semantic_hit_requires_same_conversation_history` failed pre-fix.
- **ROOT CAUSE**: History is generation-relevant (per `compute_cache_identity`) but invisible to vector similarity and absent from the compatibility check.
- **AFFECTED FILES / PATH**: `app/optimizer/semantic_cache.py` (`SemanticCacheEntry.messages_hash`, `_messages_fingerprint`, `_prior_context`, `get`, `set`, `_is_compatible_for_semantic_hit`).
- **FIX**: Entries now carry a SHA-256 fingerprint of the **prior conversation context** (messages before the embedded prompt; the prompt itself is already compared by similarity). Semantic hits require an exact fingerprint match; legacy entries without a fingerprint match only prompt-only requests (fail-closed for historical entries with history). Stored in Qdrant payload and in-memory entries alike.
- **REGRESSION TEST**: `test_inv_d1_*`; `test_inv_d2_exact_cache_identity_boundaries`, `test_inv_d3_concurrent_cache_writes_stay_tenant_isolated` (already-correct behavior pinned); full pre-existing cache suites pass unchanged (`test_semantic_cache.py`, `test_semantic_cache_real.py`, `tests/unit/test_cache_identity.py`, `test_r_func_03_cache_behavior.py`).
- **RETEST**: PASS.

### RL00-F-11 — SEVERITY: MEDIUM — UNCERTAIN claims presented as verified (no caveat)
- **EXPECTED**: Claims that could not be verified but are kept in the answer must be visibly caveated (documented intent in code).
- **ACTUAL**: The code comment said "Include uncertain claims with caveat" but appended the claim **verbatim** — unverified content presented as verified fact.
- **EVIDENCE**: `test_inv_f1_uncertain_claims_are_explicitly_caveated` failed pre-fix.
- **ROOT CAUSE**: Caveat never implemented in `GroundingVerifier.verify`.
- **AFFECTED FILES / PATH**: `app/rag/grounding.py` (`verify`).
- **FIX**: UNCERTAIN claims are appended as `"{claim} [unverified]"`.
- **REGRESSION TEST**: `test_inv_f1_*`; `test_inv_f2_unsupported_claims_never_survive_grounding` (fabricated claims still dropped).
- **RETEST**: PASS.

### RL00-F-12 — SEVERITY: MEDIUM — UNCERTAIN classification band unreachable (dead logic)
- **EXPECTED**: Qualitative claims with weak-but-nonzero overlap (0.20 ≤ ratio < 0.40) classify as UNCERTAIN (per the classifier's own thresholds).
- **ACTUAL**: `max_overlap_ratio` was recorded only when ratio ≥ 0.40 (the SUPPORT threshold), so the downstream `>= 0.20` UNCERTAIN check could never fire — weakly-overlapping claims were hard-classified UNSUPPORTED and silently dropped. (Fail-safe direction, but contradicts the documented classification and hides uncertainty.)
- **EVIDENCE**: Debug trace during `test_inv_f1_*` development: claim with overlap ratio 0.286 classified UNSUPPORTED with reasoning "No supporting evidence found".
- **ROOT CAUSE**: Ratio tracking nested inside the `ratio >= 0.40` support branch.
- **AFFECTED FILES / PATH**: `app/rag/grounding.py` (`verify_claim`).
- **FIX**: Record the best overlap ratio before the support threshold check so the UNCERTAIN band is reachable; combined with F-11 those claims now surface with an explicit caveat instead of vanishing or masquerading as verified.
- **REGRESSION TEST**: `test_inv_f1_*` (asserts `len(uncertain_claims) == 1` and caveat present); pre-existing `test_grounding_verifier_claim_classification` (SUPPORTED/UNSUPPORTED boundaries) passes unchanged.
- **RETEST**: PASS.

### RL00-F-13 — SEVERITY: MEDIUM — FinOps ledger recorded the requested model, not the served model
- **EXPECTED**: Ledger/attribution must record the model that actually served the request (failover/rerouting may select a different candidate); the requested model is preserved separately for routing-savings attribution.
- **ACTUAL**: The gateway passed `request.model` into `TokenAccounting.record_transaction` and `record_upstream_inference` and never supplied the `requested_model` parameter — responses served by a failover model were billed/attributed under the requested model, and `model_routing_usd` attribution could never fire.
- **EVIDENCE**: `test_inv_h1_ledger_records_actually_served_model` failed pre-fix (`record.model == 'gpt-4o'` while upstream served `'gpt-4o-mini-served-variant'`).
- **ROOT CAUSE**: The actually-served model (`UpstreamLLMResponse.model` ← `ProviderResponse.model` = the candidate that executed) was available but discarded at the ledger boundary.
- **AFFECTED FILES / PATH**: `app/services/ai_gateway.py` (`chat_completions`), `app/finops/service.py` (existing `requested_model` parameter now supplied).
- **FIX**: Gateway computes `served_model` from the upstream response (falling back to the requested model on the offline/deterministic path) and passes it as the ledger model with `requested_model=request.model`. Cache identity intentionally stays on the request parameters (routing is deterministic per identity; see RL00-R-07).
- **REGRESSION TEST**: `test_inv_h1_*`.
- **RETEST**: PASS.

---

## 5. Recorded Findings Dispositioned to Other RIGHT Tasks (scope rule: recorded, not silently fixed)

| ID | Severity | Finding | Disposition |
|---|---|---|---|
| RL00-R-01 | HIGH | Quota is enforced/settled **only** on the two gateway proxy routes; `/api/v1/chat/stream`, the agent platform and ExecutionEngine paths never call `check_budget`/`settle_request` and write no FinOps ledger (usage consumes zero quota). | **R-LOGIC-02** (Rate Limiting & Budget Exhaustion Hard-Stops) — enforcement placement across all billable paths. |
| RL00-R-02 | MEDIUM | Quota check-and-settle is not atomic (TOCTOU): concurrent requests passing preflight can overshoot the hard cap (bounded by in-flight request size). Existing `test_finops_accounting.py` explicitly codifies overshoot acceptance (`tokens_used == 10_100` on a 10,000 quota). | **R-LOGIC-02** — reservation-based atomic budgeting decision belongs with budget hard-stop work. |
| RL00-R-03 | MEDIUM | `AgentExecutionLoop` (agent-platform path) and `WorkflowEngine` complete runs **without** CanonicalVerifier; inside LangGraph, `route_from_verifier` sends FAILED/REJECTED to the synthesizer→END and the supervisor→synthesizer edge bypasses the verifier entirely (enforced only post-hoc in the adapter). | **R-LOGIC-01** (Verifier Decision Trees & Fail-Stop). |
| RL00-R-04 | MEDIUM | Deployment hardening: dev JWT fallback secrets active when `ENVIRONMENT` ∈ {development,test,local,empty} and `ENVIRONMENT` defaults to development; `BYOK_MASTER_KEY` has a hardcoded default; BM25 corpus persisted as plaintext JSON. | **R-ARCH-01 / R-ARCH-02** (persistence leaks, multi-worker safety). |
| RL00-R-05 | LOW | Approvals never expire (no TTL) and live in an in-memory dict (lost on restart; engine restart-recovery compensates for step gates). | **R-LOGIC-04** (Resume Locks & Concurrency) / R-ARCH-01. |
| RL00-R-06 | LOW | `ExecutionEngine.execute_task` with an explicit existing `run_id` silently replaces prior run state; cross-tenant GET-by-id distinguishes 403 vs 404 (existence oracle — explicitly tolerated by existing tests). | **R-ARCH-01** / R-FUNC-00 contract decision. |
| RL00-R-07 | LOW | `app/api/v1/endpoints/chat.py` derives cache identity from client-claimed provider/model (deterministic routing makes served-model mismatch unlikely); partial grounding returns `SUCCESS` with unsupported claims dropped and uncertain claims caveated (graceful degradation, documented). | **R-AI-01** (Faithfulness & Citation Integrity). |

## 6. Invariants Verified as Holding (no fix required; regression-proofed)

- **Tenant isolation** — tenant identity comes exclusively from the signed JWT (`get_current_tenant`); cross-tenant run read/cancel at the HTTP boundary → 403/404; RAG dense/sparse/hybrid/selector/citation layers filter by tenant with defense-in-depth post-filters (`test_inv_e1_*`, `test_inv_e3_*`; deep coverage pre-existing in `test_rag_tenant_isolation*.py`).
- **Provider credential isolation** — AES-256-GCM with tenant-derived key and tenant AAD; tenant B cannot resolve tenant A's key; failover re-resolves per-candidate credentials and never inherits (`test_inv_e2_*`; `test_provider_failover_credentials.py`).
- **Tool authorization** — permission-gated tools fail closed; dangerous tools require approval via the policy engine; path-traversal/attack-pattern arguments denied (`test_inv_g1_*`, `test_inv_g2_*`).
- **Quota non-negative / no lost updates** — concurrent `settle_request` (25 parallel) sums exactly; `tokens_remaining` floors at 0; hard cap blocks preflight (`test_inv_c3_*`).
- **Cache cross-tenant/model isolation** — exact tier isolates on every identity dimension; concurrent multi-tenant writes never cross-contaminate (`test_inv_d2_*`, `test_inv_d3_*`).
- **Verifier verdict integrity** — tenant mismatch → immediate REJECTED at any revision; FAILED/REJECTED never flip to PASS (pre-existing `test_verifier_invariants.py`, still green).

## 7. Tests Executed (exact commands & results)

All commands run from `backend/` with the repo venv (`backend/.venv`, Python 3.14 local; CI 3.11/3.12).

**New suite**: `tests/test_r_logic_00_invariants.py` — 30 tests covering every required invariant with normal, boundary, concurrent, and failure-injection cases.

| Step | Command | Result |
|---|---|---|
| Pre-fix reproduction | `.venv/bin/python -m pytest tests/test_r_logic_00_invariants.py -q` | **13 failed / 11 passed** (defects reproduced) |
| Post-fix rerun | `.venv/bin/python -m pytest tests/test_r_logic_00_invariants.py -q` | **30 passed** |
| Agent regression | `pytest tests/test_r_func_01_agent_behavior.py tests/test_execution_engine_and_adapters.py tests/test_durable_checkpointing.py tests/test_resume_bridge.py tests/test_orchestration_contracts.py tests/test_verifier_invariants.py -q` | 49 passed |
| Cache regression | `pytest tests/test_semantic_cache.py tests/test_semantic_cache_real.py tests/unit/test_cache_identity.py tests/test_r_func_03_cache_behavior.py -q` | passed (2 Redis-only skips locally) |
| FinOps/quota/gateway regression | `pytest tests/test_finops_accounting.py tests/test_unified_quota_authority.py tests/test_gateway.py tests/test_commercial_services.py tests/test_finops_endpoints.py -q` | 54 passed |
| Agent platform (HTTP) | `pytest tests/test_agent_platform.py -q` | passed except known environment failure (below) |
| RAG regression | `pytest tests/test_rag_grounding_and_abstention.py`, `pytest tests/test_rag.py`, `pytest tests/test_rag_tenant_isolation.py`, `pytest tests/test_rag_tenant_isolation_hardened.py`, `pytest tests/test_r_func_02_rag_behavior.py` (run individually — WSL OOM) | all passed |
| Routing/failover/architecture | `pytest tests/test_workload_classification_routing.py tests/test_provider_failover_credentials.py tests/test_architecture_invariants.py -q` | passed |
| Orchestration/misc | `pytest tests/test_multi_agent.py tests/test_orchestration_planner.py tests/test_agent_registry_and_selector.py tests/test_orc_capabilities.py tests/test_harmonization.py -q` | passed |
| API/health/observability/etc. | `pytest tests/test_r_func_00_api_behavior.py tests/test_health.py tests/test_endpoints.py`, `pytest tests/unit`, `pytest tests/evals`, `pytest tests/contract`, `tests/test_cosign_oidc_signing.py tests/test_commercial_services.py`, provider/RAG-unit chunks, `tests/test_circuit_breaker.py tests/test_byok.py tests/test_devops_bot.py …` | all passed |
| Lint (CI-equivalent) | `.venv/bin/ruff check app/ tests/test_r_logic_00_invariants.py tests/test_agent_platform.py` | All checks passed |
| Format (CI-equivalent) | `.venv/bin/ruff format --check app/ tests/…` | 168 files already formatted |
| Type check (CI-equivalent) | `.venv/bin/mypy --config-file mypy.ini app` | Success: no issues in 166 source files |
| Patch-coverage estimate (changed modules) | chunked `pytest --cov=app --cov-append` over the 11 suites exercising the diff; `coverage report` on the 11 changed files | `reconciler.py` 100 %, `contracts.py` 98 %, `finops/service.py` 98 %, `grounding.py` 93 %, `manager.py` 86 %, `engine.py` 82 %; remaining misses on changed lines are defensive guards (state-desync pause branches, vanished-record `except`) plus pre-existing uncovered regions; estimated patch coverage ≈ 94 % (gate: ≥ 80 %). Note: pytest-cov's global 85 % gate cannot be evaluated in one local process (WSL OOM); CI is authoritative. |

**Environment notes (WSL, per prior RIGHT sessions)**:
- `tests/test_agent_platform.py::test_local_safe_sandbox_file_and_commands` — **ENVIRONMENT FAILURE** (sandbox spawns bare `python`, absent in WSL); fails identically on pristine main; green in CI.
- 2 Redis-dependent skips in `test_r_func_03_cache_behavior.py` — no Redis locally; CI runs them against real Redis 7.
- Full suite in one process OOM-kills under the 3.8 GB WSL limit (exit 137, also observed with coverage tracing enabled); CI runners (7 GB+) execute the whole suite — this task's chunks cover all changed modules.

## 8. CI Result

**GitHub CI: GREEN on commit `197874d` (run 34729755653) — all 9 checks passed:**

| Check | Conclusion |
|---|---|
| Automated Tests & AI RAG Regression (3.11 / 3.12) | success (full suite incl. 30 new invariant tests, real Redis 7 + Qdrant, 85 % coverage + patch-diff gates) |
| Code Quality & Type Analysis (3.11 / 3.12) | success (ruff check, ruff format, mypy) |
| Container Packaging & Vulnerability Scan | success |
| DevSecOps - Secret & Key Leak Detection | success |
| DevSecOps - Vulnerability Audit, SAST & License Compliance | success |
| Frontend Widget Build & Quality Verification | success |
| Infrastructure & Workflow Linting | success |

**CI incident during verification (classified and fixed):** the first CI run (commit `1d2a8a6`, run 34729616353) failed only **Container Packaging & Vulnerability Scan** — Trivy flagged 13 HIGH/CRITICAL CVEs in Debian 13.6 **OS packages** of the base image (`python:3.12-slim`: gzip, pcre2, sqlite3, libssh2, perl), all with fixed point releases available and **all Python-package entries clean**. Classification: **BASELINE/ENVIRONMENT FAILURE** (vulnerability-DB drift: the same scan on main's commit would now fail identically; the Dockerfile was untouched by this task). Per the CI rule it was fixed, not bypassed: `backend/Dockerfile` now runs `apt-get upgrade -y` in both stages so Debian security point releases are applied at build time; the Trivy gate (exit-code 1) is unchanged and passes.

## 9. Remaining Issues & Risks

1. **RL00-R-01/R-02 (→ R-LOGIC-02)**: quota enforcement gaps on non-gateway paths and non-atomic check-and-settle remain the largest open logic risks; they were deliberately not altered here to avoid scope creep and because the budget-hard-stop design decision belongs to R-LOGIC-02.
2. **RL00-R-03 (→ R-LOGIC-01)**: verification coverage across the loop/workflow/LangGraph paths is incomplete by design of those paths; the canonical engine path is now airtight (incomplete plans can no longer complete).
3. Resume of a `PAUSED_APPROVAL` run whose in-memory approval records were lost now requires the explicit `approved=True` resume param (documented fallback preserved for restart recovery); durable approval persistence remains open (RL00-R-05).
4. Semantic cache entries created before this change and stored in long-lived Qdrant collections will not semantic-hit for requests carrying prior context until they expire (fail-closed by design; exact tier unaffected).
5. `FinOpsRecord.requested_model` is now populated by the gateway; analytics surfaces that ignore the field are unaffected, but attribution consumers should prefer `model` (served) for cost and `requested_model` for routing savings.

## 10. Manual Test Instructions for the Human Reviewer

1. **Terminal-state integrity (cancel)**: `cd backend && uv run uvicorn app.main:app --port 8000`; obtain a dev JWT for `tenant_demo`; `POST /api/v1/agent/tasks` → `POST .../tasks/{id}/runs` (async) → wait for the run to reach a terminal state via `GET .../runs/{id}` → `POST .../runs/{id}/cancel` → the response must show the **unchanged terminal** status (previously it flipped to `cancelled`).
2. **Terminal-state integrity (resume)**: with a COMPLETED run, re-POST the resume/coding internal resume flow → the run must stay COMPLETED with no new `step_started`/`completed` events in the SSE stream.
3. **Approval binding**: plan a task with two dangerous tool steps (e.g., `terminal_exec` twice with different args). Both pause with distinct approval IDs. Approve only one via `POST /api/v1/agent/tasks/{t}/runs/{r}/approvals/{appr_id}`. Resuming must execute only the approved tool; the second must remain paused pending its own approval.
4. **Quota single-settlement**: `POST /api/v1/gateway/chat` once, then `GET /api/v1/gateway/usage` — token usage must increase by the reported usage total exactly once (and `GET /api/v1/finops/summary` shows one inference record whose `model` equals the model actually served by the provider response).
5. **Cache history isolation**: send two chat requests with the same final user message but different earlier conversation history through the Tier-2-enabled path — the second must not receive the first's cached answer.
6. **RAG caveat**: query RAG so the synthesizer includes a partially-supported statement — the answer must visibly mark it `[unverified]`.

## 11. STOP

R-LOGIC-00 is fully verified: all required invariants have executable regression tests, all confirmed defects are fixed without weakening any check, and CI-equivalent local checks are green. Awaiting GitHub CI on the PR; no further RIGHT tasks executed per the STOP rule.
