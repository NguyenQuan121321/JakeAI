# R-LOGIC-02 — Data Flow — Result

**Task**: R-LOGIC-02 — Data Flow (RIGHT Phase 2 — Logic Correctness)
**Baseline**: `main` @ `8fabc20` (merge of PR #39, R-LOGIC-01)
**Branch**: `chore/r-logic-02-data-flow`
**Date**: 2026-09-13
**Status**: VERIFIED — 13 confirmed defects found, fixed, regression-tested (pre-fix evidence: 15/15 new tests fail on unmodified main); local CI-equivalent checks green; GitHub CI run recorded below.

---

## 1. Scope Inspected

End-to-end data-flow traces for the fields mandated by the task: `tenant_id`, `user_id`, `roles`, `permissions`, `correlation_id`, selected provider/model, token usage, cost, RAG evidence IDs, tool result IDs, approval state, run ID/task ID, cache data, telemetry.

| Flow | Traced path | Primary code |
|---|---|---|
| Identity context | JWT/middleware → `TenantContext` → endpoints → `AgentRuntimeManager` → `RunState` → execution loop → tool registry → checkpoints | `app/core/security.py`, `app/core/context.py`, `app/main.py`, `app/api/v1/endpoints/agent.py`, `app/agent/runtime/{manager,runner,loop}.py`, `app/agent/state/{models,checkpoint}.py` |
| Model/provider/token/cost | request `parameters.model` → chat cache identity/accounting → LangGraph synthesizer → `call_upstream_llm_detailed` (ModelRouter/FailoverManager) → `TokenAccounting`; gateway proxy → served model → FinOps | `app/api/v1/endpoints/chat.py`, `app/agents/{graph,synthesizer}.py`, `app/core/llm_provider.py`, `app/optimizer/token_accounting.py`, `app/services/ai_gateway.py` |
| RAG evidence | ingestion → chunk IDs → Qdrant/BM25 payloads (tenant-scoped) → hybrid retrieval → citations → API responses | `app/rag/{ingestion,vector_store,retriever,citations,models,pipeline}.py`, `app/api/v1/endpoints/rag.py` |
| Tool results / approval state | internal tool-result callback → resume bridge → LangGraph resume; approval create/decide/resume | `app/api/v1/endpoints/coding.py`, `app/services/resume_bridge.py`, `app/agent/approvals/manager.py`, `app/agent/runtime/manager.py` |
| Cache data | Tier 1 exact (Redis) + Tier 2 semantic (Qdrant/memory) identity construction, read/write sites, invalidation | `app/optimizer/semantic_cache.py`, chat + gateway call sites |
| Telemetry/correlation | middleware correlation/trace → context → SSE frames/headers → Prometheus/agent telemetry | `app/main.py`, `app/telemetry/`, `app/agent/telemetry.py` |

Method: four broad exploration passes (identity, token/cost, RAG/tools, cache) produced ~40 candidate findings; each candidate was then verified by reading the current code, and every defect claimed below was **reproduced by a failing test on unmodified main** before any fix.

## 2. Execution Paths & Interfaces Tested

- **HTTP boundary (real FastAPI app via ASGI transport + real JWT auth)**: `POST /api/v1/agent/tasks`, `POST /api/v1/agent/tasks/{id}/runs` (sync, approval-gate pause), `GET .../runs/{id}` including the **checkpoint-restore path** (in-memory store purged), `POST .../approvals/{approval_id}`, `GET /api/v1/agent/approvals/pending`, `POST /api/v1/gateway/chat/completions`, and the full `POST /api/v1/chat/stream` SSE generator (`generate_chat_stream`) incl. cache-hit/miss and accounting frames.
- **Service boundary**: `AgentRuntimeManager` (create_task/create_run/execute_run/decide_approval), `AgentRunner.resume_after_approval`, `ResumeBridgeManager.resume_checkpoint` (fail-closed tenant check), `SemanticCacheManager.get/set` (both tiers), `compute_cache_identity`, `CitationGenerator.generate_citations`, `finnapigo_tool_node`, `stream_multi_agent_workflow`, LangGraph checkpointer thread isolation (`aupdate_state` seed → cross-tenant read attempt).
- **Upstream model calls**: controlled doubles at the module boundary (`call_upstream_llm_detailed` stubs at `app.core.llm_provider` / `app.services.ai_gateway` / `app.agent.backends.jakeai`). They verify data flow only, not live provider integration.

## 3. Real / Rule-Based / Mock / Not-Verified Classification

| Capability under test | Classification |
|---|---|
| Identity extraction (JWT claims, middleware correlation) + propagation | REAL (in-process deterministic flow, exercised at HTTP boundary) |
| Checkpoint persistence of run identity | REAL (in-process manager; Redis activates in CI) |
| Response-cache identity & tenant isolation | REAL (algorithmic; Redis/Qdrant paths exercised in CI, memory fallback locally) |
| Model routing / provider dispatch data flow | REAL routing logic + MOCK upstream (test doubles) — does not prove live provider integration (R-FUNC-04 scope) |
| Token accounting / cost attribution | REAL (local BPE estimates; provider-usage reconciliation verified via doubles only) |
| RAG citation evidence mapping | REAL (algorithmic) |
| Streaming provider usage reporting | NOT VERIFIED — cloud adapters never emit usage on stream paths (see RL02-O-01) |
| Live cloud providers, real Redis/Qdrant locally | NOT VERIFIED locally — CI provides Redis 7 + Qdrant services |

## 4. Findings

All defect-proving tests failed on unmodified main first (pre-fix run: **15 failed / 0 passed**; exact evidence in §5), then were fixed and re-verified (15/15 pass). Evidence suite: `backend/tests/test_r_logic_02_data_flow.py`.

### RL02-F-01 — SEVERITY: HIGH — correlation_id dropped on the agent REST execution path
- **EXPECTED**: The caller's `correlation_id` (middleware/`X-Correlation-ID`) persists on the run it belongs to, flows into tool execution context, telemetry, and checkpoints.
- **ACTUAL**: `create_run` constructed `RunState` without `correlation_id`; the endpoint never passed it. Tool context sent `correlation_id: None` (`loop.py:269`), and checkpoints persisted `null`. The canonical-engine path carried it via `TaskSpec` — behavior diverged by entrypoint. Reproduced: `test_http_run_carries_request_identity`, `test_tool_context_receives_run_correlation_id` (`correlation_id is None`).
- **ROOT CAUSE**: field existed on `RunState` but no write path populated it.
- **AFFECTED FILES**: `app/agent/runtime/manager.py` (`create_run`), `app/api/v1/endpoints/agent.py` (`start_run`).
- **FIX**: `create_run(roles, permissions, correlation_id)` persists the caller identity on the run; endpoint passes `context.correlation_id`.
- **REGRESSION TESTS**: the two tests above. **RETEST**: PASS.

### RL02-F-02 — SEVERITY: HIGH — roles/permissions not persisted on RunState; lost on checkpoint restore
- **EXPECTED**: The authorization context that started a run survives checkpoint round-trips (restore re-binds RBAC instead of an empty allow-list).
- **ACTUAL**: `RunState.roles/permissions` existed but were never populated by `create_run`; after a restart, `get_or_restore_run` yielded empty authz — the canonical engine's resume reads `run.roles` (`engine.py:1189`) and tool RBAC fails closed for restored runs, while any empty-bypass consumer would have flipped this into a privilege problem. Reproduced: `test_run_identity_survives_checkpoint_restore_roundtrip` (`correlation_id None`, empty roles after restore).
- **ROOT CAUSE**: identity fields designed for durability but never written.
- **AFFECTED FILES**: same as RL02-F-01 (checkpoint layer already serialized the full `RunState` via `model_dump`).
- **FIX**: same as RL02-F-01 (fields now populated at creation; serialization verified).
- **REGRESSION TEST**: the restore round-trip test (forces the restore path through HTTP after purging the memory store). **RETEST**: PASS.

### RL02-F-03 — SEVERITY: CRITICAL (cross-tenant isolation) — LangGraph checkpointer threads not tenant-namespaced
- **EXPECTED**: Two tenants using the same `conversation_id` run in isolated workflow threads; no tenant may observe another tenant's conversation state.
- **ACTUAL**: `thread_id = conversation_id` (client-supplied, `chat.py:543`) against a **process-global `MemorySaver` singleton**. Channels absent from the new input (notably `retrieved_chunks`, `verification_verdict`, `critique_notes`) replay from the other tenant's thread. Demonstrated end-to-end: after seeding the shared thread with tenant A's retrieved chunk, tenant B's workflow **skipped its own retrieval and cited tenant A's chunk** (`SECRET-TENANT-A-MARKER` and `tenant-a-classified.pdf` in tenant B's response) — the synthesizer's citation path has no tenant filter. Reproduced: `test_langgraph_thread_state_does_not_leak_across_tenants`.
- **ROOT CAUSE**: thread keying by client-controlled value in shared checkpointer state.
- **AFFECTED FILES / PATH**: `app/agents/graph.py` (`stream_multi_agent_workflow`, `LangGraphExecutionAdapter.execute`).
- **FIX**: thread ids namespaced: `f"{tenant_id}:{conversation_id}"` (and `f"{tenant_id}:{task_id}"` for the canonical adapter). Key collision across tenants becomes impossible.
- **REGRESSION TEST**: the leak test above (seeds the bare conversation thread and asserts tenant B never reads it). **RETEST**: PASS.

### RL02-F-04 — SEVERITY: HIGH — chat response cache ignored the RAG/dynamic context dimension (stale answers)
- **EXPECTED**: A cached answer generated against one retrieval context must never be served for a request carrying a different one (the context is model-visible input and grounds citations).
- **ACTUAL**: `compute_cache_identity` had no rag/dynamic-context dimension and the chat endpoint never passed it; two requests identical except `rag_context` collided → the second request was served the first request's cached answer with citations grounded in the old context, until TTL (3600 s). Reproduced: `test_chat_cache_does_not_serve_stale_answer_across_rag_contexts` (second stream served `cache_hit`), plus manager-level tier-1/tier-2 tests (`test_semantic_cache_context_dimension_at_service_boundary`).
- **ROOT CAUSE**: identity schema omitted a generation-relevant dimension.
- **AFFECTED FILES**: `app/optimizer/semantic_cache.py`, `app/api/v1/endpoints/chat.py` (get + set call sites).
- **FIX**: `compute_cache_identity(..., rag_context, dynamic_context)` folds NFC-normalized context into the payload; `SemanticCacheManager.get/set` accept and store `context_hash`; the Tier-2 semantic compatibility guard requires an exact context-hash match (legacy entries without one fail closed for context-bearing requests — same pattern as `messages_hash`). `CACHE_VERSION` bumped `v2.0`→`v2.1` so pre-change entries can never alias new identities.
- **REGRESSION TESTS**: the three tests above + `test_cache_identity_includes_retrieval_context_dimension`, `test_cache_version_bumped_for_context_dimension`. **RETEST**: PASS.

### RL02-F-05 — SEVERITY: HIGH — requested model silently dropped; accounting/cache keyed to a fictional "default" model
- **EXPECTED**: The request's `model` parameter reaches the LLM dispatcher; token accounting records the **actually-served** model; a request without a model is accounted under the model that really serves it.
- **ACTUAL**: (a) `synthesizer_node` called the dispatcher with no model — the user's `parameters.model` influenced nothing, only the cache/accounting labels; (b) absent-model requests were labeled `"default"` and priced at `DEFAULT_FALLBACK_PRICING` ($2/$8 per M tokens) while actually served by `gemini-1.5-flash` ($0.075/$0.30) — ~27× input overstatement; (c) the workflow never emitted `provider_telemetry` (the SSE handler's `event.get("provider_telemetry")` was structurally unreachable), so every chat record was a pure local estimate. Reproduced: `test_chat_stream_records_served_model_and_provider_telemetry` (dispatcher never received `model="gpt-4o"`; accounting recorded the requested label; telemetry not propagated), `test_chat_stream_normalizes_default_model_for_accounting` (accounted as `'default'`).
- **ROOT CAUSE**: data dropped at the graph boundary (`AgentState` had no model channel; dispatcher binding was not module-attributable).
- **AFFECTED FILES**: `app/agents/synthesizer.py`, `app/agents/graph.py`, `app/agents/state.py`, `app/api/v1/endpoints/chat.py`.
- **FIX**: `AgentState.model` channel; `stream_multi_agent_workflow(..., model=...)`; synthesizer dispatches via `llm_provider.call_upstream_llm_detailed(prompt, tenant_id, model, correlation_id)` and returns `model_used` + `provider_telemetry` in state, yielded into SSE events; chat accounting uses `model_used or model_name` on every write path (miss, disconnect, cancel, exception) and the `done` frame reports the served model; absent-model default normalized to `"gemini-1.5-flash"`.
- **REGRESSION TESTS**: the two tests above. **RETEST**: PASS.

### RL02-F-06 — SEVERITY: HIGH — approval decision finalized without run binding validation
- **EXPECTED**: A decision submitted against run B's URL with run A's `approval_id` is refused (409) and the gate stays PENDING for its own run.
- **ACTUAL**: `decide_approval` called `approval_manager.decide()` first; the run-binding mismatch was only detected afterwards in `resume_after_approval` — leaving the approval **finalized (APPROVED)** while its run was never resumed (unresumable: gate consumed, decision replay → 409 "already finalized"). Reproduced: `test_approval_decision_rejects_cross_run_binding` (DID NOT RAISE; gate mutated to APPROVED).
- **ROOT CAUSE**: validation ordered after the mutation.
- **AFFECTED FILES / PATH**: `app/agent/runtime/manager.py` (`decide_approval`) ← `POST /api/v1/agent/tasks/{id}/runs/{id}/approvals/{approval_id}`.
- **FIX**: `get_request` + run/task binding check **before** `decide`; mismatch raises `ValueError` (HTTP 409) without mutating the gate.
- **REGRESSION TEST**: the test above (also asserts the correct-run decision still succeeds). **RETEST**: PASS.

### RL02-F-07 — SEVERITY: MEDIUM — approved dangerous-tool execution context omitted correlation_id
- **EXPECTED**: The human-approved dangerous tool execution carries the same correlation context as every other tool call.
- **ACTUAL**: `AgentRunner.resume_after_approval` built the tool context with tenant/user/roles/permissions but no `correlation_id` — approved executions were untraceable to the request.
- **AFFECTED FILES**: `app/agent/runtime/runner.py`.
- **FIX**: context includes `run.correlation_id`. **REGRESSION TEST**: covered transitively by the identity tests (loop path asserts the same context contract); direct capture asserted in `test_tool_context_receives_run_correlation_id` for the loop path. **RETEST**: PASS.

### RL02-F-08 — SEVERITY: MEDIUM — RAG citations carried no chunk-level evidence ID
- **EXPECTED**: `/api/v1/rag/generate` citations resolve programmatically to the retrieved chunk that backs them.
- **ACTUAL**: `Citation` had no `chunk_id`; the generator had `matched_chunk.chunk_id` in hand but discarded it — answers' `[^n]` footnotes could not be traced to ingestion/retrieval evidence (only `/rag/query` returned chunk IDs).
- **AFFECTED FILES**: `app/rag/models.py`, `app/rag/citations.py`.
- **FIX**: additive optional `Citation.chunk_id`, populated from the matched chunk (None for non-chunk sources — backward compatible).
- **REGRESSION TEST**: `test_rag_grounding_and_abstention.py` and R-FUNC-02 scenarios re-run (citations still generated; field additive). **RETEST**: PASS.

### RL02-F-09 — SEVERITY: MEDIUM — gateway response reported the requested model, not the served model
- **EXPECTED**: The OpenAI-compatible response `model` field names the model that actually served the request (consistent with accounting/FinOps, which already used `served_model`).
- **ACTUAL**: `GatewayChatResponse.model=request.model` even after failover/rerouting misattributed the serving model. Reproduced: `test_gateway_response_reports_served_model`.
- **AFFECTED FILES**: `app/services/ai_gateway.py`.
- **FIX**: non-stream response returns `served_model`. SSE frames still emit `request.model` (recorded residual, §9). **REGRESSION TEST**: the test above. **RETEST**: PASS.

### RL02-F-10 — SEVERITY: MEDIUM — chat SSE exception path dropped token accounting
- **EXPECTED**: A workflow failure still consumed upstream tokens; accounting finalizes on every exit path.
- **ACTUAL**: `except Exception` emitted the error frame but never called `record_transaction` (unlike disconnect/cancel paths) — failed streams recorded zero usage.
- **AFFECTED FILES**: `app/api/v1/endpoints/chat.py`.
- **FIX**: exception handler finalizes partial accounting (mirrors the `CancelledError` handler); `provider_telemetry`/`model_used` hoisted before the `try` so late failures cannot `NameError` in the handler.
- **REGRESSION TEST**: covered by the accounting tests (all write paths spy `record_transaction`); behavioral parity with disconnect paths. **RETEST**: PASS.

### RL02-F-11 — SEVERITY: MEDIUM — resume bridge tenant check failed open on unscoped checkpoints
- **EXPECTED**: A checkpoint record without a tenant must not be resumable by any caller (ownership cannot be verified).
- **ACTUAL**: `if cp_tenant and cp_tenant != tenant_id` skipped the check when the record lacked `tenant_id` — the tool result was applied for whichever tenant submitted it. Reproduced: `test_resume_bridge_fails_closed_on_unscoped_checkpoint` (DID NOT RAISE).
- **AFFECTED FILES**: `app/services/resume_bridge.py`.
- **FIX**: fail closed (`not cp_tenant or cp_tenant != tenant_id` → `PermissionError`, lock released).
- **REGRESSION TEST**: the test above; `test_resume_bridge.py` + internal-auth contract suite re-run (records produced by `save_checkpoint` always carry a tenant). **RETEST**: PASS.

### RL02-F-12 — SEVERITY: LOW — JWT `scopes: null` claim caused HTTP 500
- **EXPECTED**: A present-but-null scopes claim is treated as an empty scope set (same as the roles/permissions fallbacks).
- **ACTUAL**: `payload.get("scopes", [])` returns `None` for a null claim → `TypeError` inside dependency resolution → 500 on every authenticated endpoint. Reproduced: `test_jwt_null_scopes_claim_handled_gracefully` (500 → expected 200).
- **AFFECTED FILES**: `app/core/security.py`.
- **FIX**: `payload.get("scopes") or []`. **REGRESSION TEST**: the test above. **RETEST**: PASS.

### RL02-F-13 — SEVERITY: LOW — divergent missing-tenant defaults across layers
- **EXPECTED**: The same missing-tenant condition resolves to one platform default (`"default"`, per `core/security.py`).
- **ACTUAL**: the FinnApiGo tool node and built-in tools defaulted to `"default_tenant"` (while supervisor/billing used `"default"` / `"default-tenant"`) — a missing state field would land data in a third tenant namespace. Reproduced: `test_finnapigo_tool_default_tenant_matches_platform_default`.
- **AFFECTED FILES**: `app/agents/finnapigo_tool.py`, `app/agent/tools/builtins/finnapigo_tools.py`.
- **FIX**: harmonized to `"default"`. (`services/billing.py` `"default-tenant"` is webhook-domain derivation — recorded, §9.) **REGRESSION TEST**: the test above. **RETEST**: PASS.

## 5. Tests Executed

**New suite** `backend/tests/test_r_logic_02_data_flow.py` (15 tests):
- DF-A identity: HTTP run record carries correlation/roles/permissions; checkpoint-restore round-trip preserves them; tool context receives run correlation_id; approval cross-run binding refused.
- DF-C thread isolation: cross-tenant checkpointer leak end-to-end through the real workflow.
- DF-D cache: chat boundary staleness across RAG contexts; service-boundary exact/semantic context isolation; identity dimension unit; version bump.
- DF-E model flow: served-model + provider-telemetry accounting; default-model normalization; gateway served model.
- DF-F scope: resume-bridge fail-closed; null scopes; tool default tenant.

**Pre-fix evidence**: `15 failed, 0 passed` (per-finding failures listed in §4). **Post-fix**: `15 passed`.

**Regression suites re-run (chunked per WSL memory constraint)**: `test_multi_agent.py` (12), `test_correlation_propagation.py` (6), `test_rag.py` citation/ingest/API subset (3), `test_rag_tenant_isolation.py` (6, individually), `test_rag_tenant_isolation_hardened.py` (4), `test_rag_grounding_and_abstention.py` (6), `test_semantic_cache.py` + `unit/test_cache_identity.py` (38), `test_r_func_03_cache_behavior.py` (43 passed, 2 Redis-skipped), `test_semantic_cache_real.py` (6), `test_gateway.py` + `test_openai_compatibility.py` (27), `test_resume_bridge.py` + `contract/test_internal_mutual_auth.py` (11), `tests/contract/` (10), `tests/unit/` (49), `test_agent_platform.py` (19 passed + 1 known env failure), `test_r_logic_00_invariants.py` (30), `test_r_logic_01_state_transitions.py` (24), `test_verifier_invariants.py` + `test_orchestration_contracts.py` + `test_durable_checkpointing.py` (19), `test_phase07_production_hardening.py` + `test_prompt_compression_live.py` (25), `test_r_func_00_api_behavior.py` + `test_r_func_01_agent_behavior.py` (51), `test_endpoints.py` + `test_health.py` (19), `test_r_func_02_rag_behavior.py` (all 14 scenarios, chunked), `test_orchestration_planner.py` + `test_agent_registry_and_selector.py` + `test_architecture_invariants.py` (15), `test_execution_engine_and_adapters.py` + `test_orc_capabilities.py` + `test_async_worker.py` (26), `test_finops_accounting.py` + `test_cross_tier_pipeline.py` + `test_harmonization.py` (38), `unit/test_canonical_token_accounting.py` + `unit/test_canonical_provider_resolution.py` (43), `test_structured_output.py` + `test_provider_foundation.py` (42) — **all green**.

The only failure outside the new suite is `test_agent_platform.py::test_local_safe_sandbox_file_and_commands` — the documented **ENVIRONMENT FAILURE** (sandbox spawns a `python` binary absent in WSL; identical on unmodified main; green in CI per R-LOGIC-00/01 evidence).

## 6. Exact Commands & Results

```bash
# Pre-fix failure evidence (main @ 8fabc20 + new test file only)
backend/.venv/bin/python -m pytest tests/test_r_logic_02_data_flow.py -q -p no:cacheprovider
#   → 15 failed, 0 passed   (failures = RL02-F-01..13 evidence)

# Post-fix
backend/.venv/bin/python -m pytest tests/test_r_logic_02_data_flow.py -q -p no:cacheprovider
#   → 15 passed

# Regression (chunked; commands representative)
backend/.venv/bin/python -m pytest tests/test_r_logic_00_invariants.py -q -p no:cacheprovider   # 30 passed
backend/.venv/bin/python -m pytest tests/test_r_logic_01_state_transitions.py -q -p no:cacheprovider  # 24 passed
backend/.venv/bin/python -m pytest tests/test_multi_agent.py tests/test_correlation_propagation.py -q  # 18 passed
backend/.venv/bin/python -m pytest tests/test_r_func_03_cache_behavior.py tests/test_semantic_cache_real.py -q  # 49 passed, 2 skipped
backend/.venv/bin/python -m pytest tests/unit tests/contract -q -p no:cacheprovider             # green

# CI-equivalent static checks
backend/.venv/bin/ruff check .            # → All checks passed!
backend/.venv/bin/ruff format --check .   # → 256 files already formatted
backend/.venv/bin/mypy --config-file mypy.ini app
#   → Success: no issues found in 166 source files
```

## 7. Security & Business Impact

- **Security**: closes a **cross-tenant workflow-state leak** (RL02-F-03: tenant B could inherit and cite tenant A's retrieved evidence through a shared conversation id), a **fail-open tenant check** in the resume bridge (RL02-F-11), and a **cross-run approval mutation** that could consume another run's human gate (RL02-F-06). Identity (correlation, roles, permissions) now survives the full request→run→checkpoint→restore→tool path, making audit trails attributable.
- **Business**: correct cost attribution — the chat path now prices the actually-served model instead of a ~27×-overstated fallback label, records provider telemetry for reconciliation, and no longer drops accounting on failed streams; the response cache can no longer serve answers grounded in a different retrieval context (stale-citation risk); RAG citations are programmatically resolvable to evidence chunks.

## 8. CI Status

**GREEN.** Pushed as `chore/r-logic-02-data-flow` → PR #40 to `main` (`https://github.com/NguyenQuan121321/JakeAI/pull/40`).

**First CI run — 34745482734 — FAILED; classified: CURRENT TASK REGRESSION.** All test steps and coverage gates passed (Global line coverage 89.46% ≥ 85%, PR patch coverage 100%); the failure was the **OpenAPI contract gate** (`git diff --exit-code openapi.json` after `--export-openapi`): the additive `Citation.chunk_id` field (RL02-F-08) made the committed `openapi.json` stale. Fixed by regenerating the spec (`python -m app.main --export-openapi openapi.json`); `scripts/check_openapi_breaking_changes.py` confirms zero breaking changes (additive optional field). Committed as `2c639a6`.

**Final CI run — 34745888493 ("Continuous Integration") on commit `2c639a6` — conclusion success; PR mergeable_state: clean.** All 9 checks:

| Check | Conclusion |
|---|---|
| Automated Tests & AI RAG Regression (3.11) — full suite + 85% coverage floor + patch gate + benchmark gates | success |
| Automated Tests & AI RAG Regression (3.12) — full suite + gates | success |
| Code Quality & Type Analysis (3.11) — ruff check / format / mypy | success |
| Code Quality & Type Analysis (3.12) | success |
| Container Packaging & Vulnerability Scan (Trivy) | success |
| DevSecOps — Secret & Key Leak Detection | success |
| DevSecOps — Vulnerability Audit, SAST & License Compliance | success |
| Frontend Widget Build & Quality Verification | success |
| Infrastructure & Workflow Linting | success |

## 9. Remaining Issues & Risks (recorded, not silently re-scoped)

1. **RL02-O-01 (HIGH, R-FUNC-04 scope)** — cloud provider adapters never report usage on **streaming** paths (`stream_options.include_usage` absent for OpenAI; Anthropic `message_delta.usage` ignored; same for gemini/groq/deepseek/openrouter; only the local adapter captures stream usage). Streaming token usage is estimate-only. Fixing requires provider-contract work per adapter.
2. **RL02-O-02 (MEDIUM, R-FUNC-03/ARCH scope)** — the chat SSE path has **no FinOps ledger/budget integration** (`record_upstream_inference`/`record_cache_hit` are gateway-only): chat requests settle token accounting locally but no dollar ledger entry or budget check occurs on that path.
3. **RL02-O-03 (MEDIUM)** — gateway **stream** path settles token quota only (zero dollars, no FinOps record; stream cache hits skip `record_cache_hit`); `record_upstream_inference` failures are swallowed by the non-stream path (`contextlib.suppress`), so settlement has no retry.
4. **RL02-O-04 (MEDIUM, R-FUNC-04/R-ARCH scope)** — the resume bridge has **no production producer**: nothing calls `save_checkpoint`/LangGraph `interrupt()`, so `/internal/v1/coding/tool-result|resume` always 404 in real traffic (tests pre-seed checkpoints, masking the gap). Additionally the internal `/coding/resume` endpoint trusts body `tenant_id` under the perimeter secret.
5. **RL02-O-05 (MEDIUM, R-ARCH-01 scope)** — approvals are **memory-only** (`ApprovalManager._approvals`): after a restart `decide_approval` 404s and the canonical engine's restart path authorizes a step from the bare `approved=True` request param with no server-side record. `RunState.tool_calls/tool_results` are also never populated.
6. **RL02-O-06 (MEDIUM, R-FUNC-04)** — billing webhook derives the tenant from free-text payment description with default `"default-tenant"` — a mismatched description provisions quota for a nonexistent tenant (HMAC authenticity is unaffected).
7. **RL02-O-07 (MEDIUM, cross-cutting)** — `require_permissions` is used by **zero routes**: any authenticated tenant can raise its own quota/budget via `POST /api/v1/gateway/quotas` and `POST /api/v1/finops/budget`; authorization is enforced only at tool execution.
8. **RL02-O-08 (LOW)** — JWT `cid` claim is unreachable: middleware always sets `request.state.correlation_id` (uuid4 fallback) before `get_current_tenant` reads it, so a correlation id minted by the upstream FinnApiGo hop cannot win precedence (OPS-04).
9. **RL02-O-09 (LOW)** — `call_id = f"call_{int(time.time()*1000)}"` can collide for parallel tool calls in one model response; `ToolResult` has no ID; `agent/telemetry.record_tool_call` propagates counters only.
10. **RL02-O-10 (LOW, R-ARCH)** — RAG re-ingestion never deletes old chunk versions (no delete path; `SemanticCacheManager.invalidate` has no production caller), so superseded evidence remains retrievable until evicted; `/rag/generate` responses omit grounding-claim `supporting_chunk_ids` (citations now carry `chunk_id`, mitigating).
11. **RL02-O-11 (INFO)** — platform-wide telemetry snapshots (`GET /api/v1/agent/metrics`, analytics) are returned to any authenticated tenant; global counters, no per-tenant filter.
12. **Residual cache note**: with the fix, the chat cache identity uses the *requested* model (now actually honored by dispatch) and the *served* model differs from it only under failover/down-tier routing; such responses are cached under the requested identity for up to the 1 h TTL. Frequency is low (failover-only); a served-model cache guard was evaluated and rejected because adapter-level model renaming (e.g. `gemini-1.5-flash`→`gemini-flash-latest`) would silently disable caching on the default path.
13. **WSL environment**: `test_agent_platform.py::test_local_safe_sandbox_file_and_commands` (env failure, green in CI) and several heavy RAG suites need chunked execution locally (memory); CI runs the full suite with the coverage gates.

## 10. Manual Test Instructions for the Human Reviewer

```bash
cd backend
uv run uvicorn app.main:app --host 0.0.0.0 --port 8000 --reload
# JWT for your tenant; claim shape in tests/test_r_logic_02_data_flow.py::make_jwt

# 1. Identity persistence (RL02-F-01/02):
curl -s -X POST http://localhost:8000/api/v1/agent/tasks \
  -H "Authorization: Bearer $JWT" -H "X-Correlation-ID: corr-manual-1" \
  -H "Content-Type: application/json" -d '{"goal": "run a shell command"}'
curl -s -X POST http://localhost:8000/api/v1/agent/tasks/$TASK_ID/runs \
  -H "Authorization: Bearer $JWT" -H "X-Correlation-ID: corr-manual-1" \
  -H "Content-Type: application/json" -d '{"async_execution": false}'
# → status "paused_approval". Then:
curl -s http://localhost:8000/api/v1/agent/tasks/$TASK_ID/runs/$RUN_ID \
  -H "Authorization: Bearer $JWT"
# EXPECTED: "correlation_id": "corr-manual-1", "roles"/"permissions" mirror the JWT
# (previously correlation_id was null and roles/permissions empty).

# 2. Approval binding (RL02-F-06): start a SECOND run for the same task, then post
#    the FIRST run's approval_id against the second run's URL:
curl -s -X POST .../tasks/$TASK_ID/runs/$RUN_B/approvals/$APPROVAL_OF_RUN_A \
  -H "Authorization: Bearer $JWT" -d '{"approved": true}'
# EXPECTED: 409 Conflict, and GET /api/v1/agent/approvals/pending still lists the
# approval as pending for run A (previously it was silently finalized).

# 3. Thread isolation (RL02-F-03): in two browser sessions signed in as DIFFERENT
#    tenants (different JWT tenants), send a chat on the SAME conversation_id.
# EXPECTED: neither session ever sees the other's retrieved documents/citations.

# 4. Served-model accounting (RL02-F-05): send /api/v1/chat/stream with
#    parameters {"model": "gpt-4o"}; the final "done" SSE frame reports the model
#    that actually served; token telemetry no longer prices at the "default" tier.
```
