# R-ARCH-01 — Canonical Authority — Result

**Task**: Identify and eliminate competing sources of truth for planner, task/run state,
model routing, provider resolution, tool execution, verification, telemetry, cache
identity and orchestration lifecycle. For each pair, prove whether one is canonical and
the others are adapters/fallbacks or duplicates. Eliminate duplicate business authority
only after caller migration and regression tests.

**Branch**: `chore/r-arch-01-canonical-authority` (baseline: `origin/main` @ `b5c1f81`,
after PR #43 / R-ARCH-00 merge)
**Status**: ✅ VERIFIED — all confirmed duplicate-authority defects fixed, regression
suite added, full local test matrix green, GitHub CI GREEN.

---

## 1. Scope Inspected

Full authority map over `backend/app`, with emphasis on `app/agent/**`, `app/agents/**`,
`app/routing/**`, `app/providers/**`, `app/core/llm_provider.py`, `app/agent/workflows/**`,
`app/agent/tools/**`, `app/optimizer/semantic_cache.py`, `app/telemetry/**`, and the
HTTP boundary `app/api/v1/endpoints/**`.

Method: read-only sweep of every candidate module, import/caller analysis (grep + AST),
runtime behavior reproduction at component and HTTP boundaries, then targeted fixes.

---

## 2. Authority Map (canonical vs adapter vs fallback vs duplicate)

| Capability | CANONICAL authority | Other implementations | Classification of others | Verdict |
|---|---|---|---|---|
| **Planner** | `app/agent/planning/planner.py` `BoundedPlanner` (locked by R-ARCH-00 test) | `agents/supervisor.py` builds `BoundedPlanner` per request; `AgentExecutionLoop`, `AgentRuntimeManager`, `ExecutionEngine` all call it | ADAPTER/consumers | ✅ single plan algorithm |
| **Agent/capability selection** | `app/agent/registry/agent_selector.py` `AgentSelector` | (pre-fix) planner `_FINANCIAL_KW`/`_BANKING_KW`/`_RETRIEVAL_KW`; supervisor `FINANCIAL_PATTERNS`/`TOOL_PATTERNS` | **DUPLICATE (fixed, F1)** | ✅ fixed |
| **Task/run state** | `app/agent/state/models.py` `TaskStatus`/`RunStatus`/`TaskState`/`RunState` + enforced transition tables | (pre-fix) `contracts.ExecutionStateStatus` + `contracts.TerminalState` (dead duplicates); `workflows/models.WorkflowExecutionStatus` (workflow-scoped, test-only engine) | **DUPLICATE dead (fixed, F2)** / scoped secondary | ✅ fixed |
| **Model routing** | `app/routing/router.py` `ModelRouter` + `workload_classifier.py` + `failover.py` | planner/engine per-step routing calls; router plans fallback chain, FailoverManager executes it (`decision.fallback_chain`) | consumers + planner/executor split | ✅ no duplicate |
| **Provider resolution** | `app/core/llm_provider.py` (classify → route → resolve credentials → FailoverManager → `ProviderRegistry` adapters); BYOK vault `app/core/byok.py` | (pre-fix) credential map + resolver duplicated verbatim in stream variant; `DirectProviderBackend` raw-httpx path | **DUPLICATE (fixed, F3)** / documented non-canonical adapter (F6) | ✅ fixed |
| **Tool execution** | `app/agent/tools/registry.py` `ToolRegistry.execute` (policy → schema → timeout) | call sites: engine, ReAct loop, runner, finnapigo node, workflow engine — all funnel through registry; (pre-fix) OBO exchange duplicated in finnapigo node; account-id default derived in 4 places | **DUPLICATE (fixed, F4/F5)** | ✅ fixed |
| **Verification** | `app/agent/verification/verifier.py` `CanonicalVerifier` | `app/agents/verifier.py` node delegates via `get_canonical_verifier()` (same singleton, proven by R-ARCH-00 runtime test) | ADAPTER (delegating) | ✅ no duplicate |
| **Telemetry** | `app/telemetry/metrics.py` (+ `tracing.py`, `events.py`) | `app/agent/telemetry.py` `AgentTelemetry` wraps `record_agent_*` and keeps an in-memory snapshot for `GET /api/v1/agent/metrics` | ADAPTER (thin per-subsystem façade) | ✅ documented, no double authority |
| **Cache identity** | `app/optimizer/semantic_cache.py` `compute_cache_identity` (SHA-256 v2.1) | legacy `_compute_hash` retained only as a migration-compat shim with dedicated tests (`tests/unit/test_cache_identity.py`, `tests/test_r_func_03_cache_behavior.py`) | documented legacy fallback | ✅ no competing consumer |
| **Orchestration lifecycle** | One canonical state machine (`state/models.py`) written by 3 drivers: canonical DAG `ExecutionEngine`, ReAct `AgentRunner`/loop (HTTP `/api/v1/agent`), LangGraph adapter (`/api/v1/chat/stream`, coding bridge) | `app/agent/workflows/engine.py` — third mini-engine, **not wired to any HTTP endpoint or production caller** (test-only), still delegates tools/model calls to canonical registries | documented secondary (F7) | ✅ documented boundary |

---

## 3. Findings

### FINDING-1 — Capability/intent keyword classification triplicated with divergence
- **SEVERITY**: HIGH
- **EXPECTED**: one authority decides "which specialist capability does this goal belong
  to"; all layers derive from it.
- **ACTUAL**: three independently-maintained regex keyword sets:
  - `app/agent/planning/planner.py:39-53` (`_FINANCIAL_KW`, `_BANKING_KW`, `_RETRIEVAL_KW`)
  - `app/agent/registry/agent_selector.py:31-45` (`_FINANCIAL_PATTERNS`, `_BANKING_PATTERNS`, `_RETRIEVAL_PATTERNS`)
  - `app/agents/supervisor.py:23-32` (`FINANCIAL_PATTERNS`, `TOOL_PATTERNS`)
  They had drifted: planner recognized `variance|statements?`, selector `tax|ledger|cost`,
  supervisor `balances?|debts?|equity|cash flow|roi`. The same prompt classified
  differently depending on which layer evaluated it (e.g. `tax ledger cost` → financial
  for selector but not for planner; `account balance` → banking for selector but financial
  for supervisor fallback). Planner's `_RETRIEVAL_KW` was dead — never referenced.
- **EVIDENCE**: source inspection (file:line above); reproduction in
  `tests/test_r_arch_01_canonical_authority.py::test_capability_patterns_defined_exactly_once`.
- **ROOT CAUSE**: three heuristic layers copy-pasted at different WORK phases, no shared module.
- **AFFECTED FILES**: `planner.py`, `agent_selector.py`, `agents/supervisor.py`.
- **AFFECTED EXECUTION PATH**: degraded/deterministic planning, agent scoring + degraded
  fallback, LangGraph supervisor intent fallback (`decide_supervisor_route` step 3).
- **FIX**: new canonical module `app/agent/registry/capability_patterns.py` with the
  union of legitimately-required signals (`FINANCIAL_PATTERN`, `BANKING_PATTERN`,
  `RETRIEVAL_PATTERN`; balance lookups classified as BANKING, matching the live
  supervisor/selector behavior and the R-ARCH-00 HTTP contract). All three consumers
  migrated to import it. Layer-specific policy stays local (planner multi-source/approval
  plan-shaping rules; supervisor generic tool-verb vocabulary for its 3-node vocabulary).
  Caller precedence logic preserved so accepted behavior outside the union is unchanged.
- **REGRESSION TEST**: `tests/test_r_arch_01_canonical_authority.py` —
  `test_capability_patterns_defined_exactly_once` (AST proof of single definition site),
  `test_former_duplicate_pattern_copies_removed`,
  `test_layers_classify_goals_consistently` (planner/selector/supervisor agreement over
  financial, banking, banking+financial, retrieval, general goals).
- **RETEST RESULT**: PASS (13/13 in suite; R-ARCH-00 HTTP integrity suite re-run green).

### FINDING-2 — Dead duplicate run-lifecycle authority in domain contracts
- **SEVERITY**: MEDIUM
- **EXPECTED**: run/task lifecycle status defined once (`app/agent/state/models.py`,
  with enforced transitions).
- **ACTUAL**: `app/agent/domain/contracts.py` also defined `ExecutionStateStatus`
  (a lifecycle enum overlapping `RunStatus`/`TaskStatus`) and `TerminalState`
  (a terminal-outcome model). Both had **zero runtime consumers** — only re-exports in
  `app/agent/domain/__init__.py` and a contract test. Real engines write terminal state
  onto `RunState` and never emit `TerminalState`.
- **EVIDENCE**: repo-wide grep (pre-fix): references only in `contracts.py`,
  `domain/__init__.py`, `tests/test_orchestration_contracts.py`.
- **ROOT CAUSE**: contract suite authored ahead of / alongside the state machine and
  never reconciled.
- **AFFECTED FILES**: `app/agent/domain/contracts.py`, `app/agent/domain/__init__.py`,
  `tests/test_orchestration_contracts.py`.
- **AFFECTED EXECUTION PATH**: none at runtime (dead code) — risk was future re-adoption
  of the competing enum.
- **FIX**: removed `ExecutionStateStatus` and `TerminalState`; module docstring now
  states lifecycle status is owned exclusively by `app.agent.state.models`.
  `TestTerminalStateContract` in `tests/test_orchestration_contracts.py` replaced with
  `TestTerminalRunSemantics` asserting the same terminal/non-terminal semantics on the
  canonical `RunStatus`/`TaskStatus` (coverage preserved, re-pointed at the authority).
- **REGRESSION TEST**: `test_no_duplicate_lifecycle_status_authority`,
  `test_canonical_status_machine_is_the_lifecycle_authority`.
- **RETEST RESULT**: PASS.

### FINDING-3 — Provider credential resolution duplicated (non-streaming vs streaming)
- **SEVERITY**: MEDIUM
- **EXPECTED**: one credential-resolution authority: tenant BYOK key first, then
  platform key per provider.
- **ACTUAL**: `app/core/llm_provider.py` duplicated the `provider_settings_keys` map and
  the `resolve_provider_credentials` closure verbatim in `call_upstream_llm_detailed`
  (lines 111-125 pre-fix) and `call_upstream_llm_stream` (lines 288-302 pre-fix). Adding
  a provider to one map and not the other would make streaming and non-streaming
  dispatch resolve different credentials.
- **EVIDENCE**: source diff inspection; regression test asserts the map string appears
  exactly once and BYOK-before-platform precedence behaviorally.
- **ROOT CAUSE**: stream variant copy-pasted from the detailed variant.
- **AFFECTED FILES**: `app/core/llm_provider.py`.
- **AFFECTED EXECUTION PATH**: all upstream dispatch — chat, gateway, agent backends
  (`JakeAIBackend`), SSE streaming.
- **FIX**: module-level `_PROVIDER_SETTINGS_KEYS` + `resolve_provider_credentials(...)`
  shared by both variants; local 2-arg wrappers keep the `credential_resolver` protocol
  of `FailoverManager` unchanged. Behavior identical (BYOK first, platform fallback,
  unknown provider → None).
- **REGRESSION TEST**: `test_provider_credential_map_defined_once`,
  `test_credential_resolution_byok_first_then_platform`,
  `test_settings_snapshot_unchanged_by_credential_refactor`.
- **RETEST RESULT**: PASS.

### FINDING-4 — Duplicate OBO token-exchange authority in the tool-execution path
- **SEVERITY**: MEDIUM
- **EXPECTED**: the executor (builtin tool) owns authentication for the execution;
  one OBO token per execution.
- **ACTUAL**: `app/agents/finnapigo_tool.py` (LangGraph node) exchanged an OBO token and
  passed it via context, but `FinnApiGoBalanceTool`/`FinnApiGoTransactionsTool` ignored
  `context["obo_token"]` and exchanged their own token unconditionally. Two tokens per
  execution; the node's audit entry `authorization_header` recorded a token that was
  never used for the actual execution (telemetry-fidelity defect).
- **EVIDENCE**: `finnapigo_tool.py:55-67` vs `finnapigo_tools.py:51-58/113-119` (pre-fix).
- **ROOT CAUSE**: tool built after the node without consuming the prepared context key.
- **AFFECTED FILES**: `app/agent/tools/builtins/finnapigo_tools.py` (fix site),
  `app/agents/finnapigo_tool.py` (caller).
- **AFFECTED EXECUTION PATH**: LangGraph chat tool path (finnapigo_tool node → ToolRegistry
  → FinnApiGo tools); engine/loop paths unchanged (no token in context → tool self-exchanges).
- **FIX**: tools now honor a caller-provided `context["obo_token"]` and otherwise
  self-exchange — the tool is the single exchange authority; the node's pre-exchanged
  token becomes the actual execution token, so its audit entry is truthful. Exchange
  crypto itself remains single-sourced in `app/core/security.exchange_obo_token`.
- **REGRESSION TEST**: `test_balance_tool_is_single_obo_and_account_authority`,
  `test_transactions_tool_honors_provided_obo_token`.
- **RETEST RESULT**: PASS.

### FINDING-5 — Tenant account-id identity rule quadruplicated
- **SEVERITY**: MEDIUM
- **EXPECTED**: the FinnApiGo account identity `ACC-<tenant[:8].upper()>-01` derived once.
- **ACTUAL**: the same f-string derivation existed in 4 places: the builtin tool's
  default, `planner.py` degraded fallback, `engine.py` tool-argument defaults, and
  `agents/finnapigo_tool.py`.
- **EVIDENCE**: grep `ACC-{` (pre-fix, 4 hits in `app/`).
- **ROOT CAUSE**: callers pre-computed defaults instead of relying on the tool.
- **AFFECTED FILES**: `finnapigo_tools.py` (canonical), `planner.py`, `engine.py`,
  `agents/finnapigo_tool.py` (copies removed).
- **AFFECTED EXECUTION PATH**: engine tool path, ReAct degraded fallback, LangGraph
  finnapigo node.
- **FIX**: callers no longer pre-derive `account_id` (they pass no/empty arguments) and
  the tool applies its canonical default — identical output values, one definition site.
  Explicitly different caller choices (`list_transactions` limit 5, degraded shell
  commands) are parameters, not identity rules, and were left alone.
- **REGRESSION TEST**: `test_tenant_account_identity_derived_exactly_once` (AST/text
  proof), plus tool-default behavioral assertions in the OBO test above.
- **RETEST RESULT**: PASS.

### FINDING-6 — Second provider-execution path (`DirectProviderBackend`) unmarked
- **SEVERITY**: MEDIUM (boundary risk, currently unwired)
- **EXPECTED**: raw provider HTTP execution either removed or explicitly bounded.
- **ACTUAL**: `app/agent/backends/direct_provider.py` performs raw httpx calls with
  user-supplied keys, duplicating provider-adapter knowledge (endpoints, default models,
  auth headers) held by `app/providers/*`, bypassing ModelRouter/FailoverManager/BYOK/
  FinOps. `AgentConfig.backend_type` advertises `direct_provider|external_agent`, but
  the managed runtime never consumes `backend_type` — `AgentRuntimeManager` always
  constructs `JakeAIBackend` (verified). Only tests instantiate the class.
- **ROOT CAUSE**: backend abstraction written ahead of the runtime wiring.
- **AFFECTED FILES**: `direct_provider.py`, `external_agent.py`,
  `app/agent/runtime/models.py`.
- **FIX**: explicit documented adapter boundary (per task acceptance "explicitly
  documented adapter boundary"): non-canonical status, bypass consequences, and the
  requirement that production dispatch go through `app.core.llm_provider` are stated in
  both module docstrings and in the `AgentConfig.backend_type` field description.
  No code path changed (preserving accepted behavior; no silent scope expansion).
- **REGRESSION TEST**: `test_managed_runtime_wires_single_canonical_backend`,
  `test_non_canonical_backends_documented_as_adapter_boundary`.
- **RETEST RESULT**: PASS.

### FINDING-7 — Third mini-engine (`WorkflowEngine`) — dispositioned to R-ARCH-03
- **SEVERITY**: LOW
- **ACTUAL**: `app/agent/workflows/engine.py` is a linear pipeline engine with its own
  workflow-scoped status enum; it has no HTTP/production caller (grep: only
  `workflows/__init__.py` export + `tests/test_agent_platform.py:550`). It already
  delegates tool execution to the canonical ToolRegistry and model calls to the canonical
  backend interface, and its status enum tracks workflow-execution progress, not the run
  lifecycle.
- **DISPOSITION**: R-ARCH-00 recorded this as its F-02 and handed removal to **R-ARCH-03**
  ("when a duplicate is unused, remove only after caller search and regression tests").
  Honoring that handoff, R-ARCH-01 does not delete it; the module docstring now declares
  it a secondary test-scope utility, not a competing lifecycle authority.
- **RETEST RESULT**: suite green.

### FINDING-8 (RECORDED, NOT FIXED — out of task scope) — Deterministic specialist math duplicated across drivers
- **SEVERITY**: MEDIUM
- **ACTUAL**: the rule-based financial analysis simulation (revenue 1,500,000 / expenses
  950,000 defaults, `operating_income = rev − exp`, `ebitda = op_income × 1.12`) is
  implemented independently in `app/agent/execution/engine.py` (`_execute_single_step`
  financial branch, with additional ledger-coupling behavior), `app/agents/financial_specialist.py`
  (LangGraph node, prompt-number extraction) and synthesized again in `planner.py`'s
  degraded fallback report. Outputs differ slightly per driver (rounding, banking coupling).
- **DISPOSITION**: specialist capability logic is not one of the nine authority
  categories mandated by this task, and unifying would change per-driver accepted
  behavior. Recorded per "if a finding belongs to another RIGHT task, record it".
  Recommendation: extract a shared deterministic-financials helper under `app/agent/`
  (adapter side may import it) in a dedicated task.
- **REGRESSION TEST**: n/a (not changed).

### FINDING-9 — Canonical DAG `ExecutionEngine` has no HTTP entrypoint (R-ARCH-00 F-01 handoff) — classified, boundary documented
- **SEVERITY**: MEDIUM (inherited from R-ARCH-00 F-01)
- **ACTUAL**: `AgentRuntimeManager` fronts two orchestration drivers over the same
  canonical semantic authorities: `execute_run` → ReAct `AgentRunner` (wired to
  `/api/v1/agent` REST) and `execute_task_spec` → `ExecutionEngine` (canonical DAG +
  verification stage; component boundary/tests only). The LangGraph chat path is an
  adapter, not a third lifecycle.
- **CLASSIFICATION** (per this task's mandate): `ExecutionEngine` = CANONICAL DAG driver;
  `AgentRunner`/loop = second driver (ReAct strategy) — NOT a duplicate business
  authority, because every business rule it exercises (state machine, planning, tool
  policy, approvals, credentials) is single-sourced; it differs only in orchestration
  strategy and lacks the verification stage.
- **DISPOSITION**: caller migration of the REST surface onto the DAG engine would change
  accepted event/lifecycle behavior verified by R-FUNC-01 (SSE event schemas, approval
  flow, resume semantics) — a product-level behavioral migration, not a minimal correct
  fix. Per the acceptance criterion ("one canonical implementation **or an explicitly
  documented adapter boundary**"), the two-driver topology is now explicitly documented
  at the single facade where both drivers live (`AgentRuntimeManager` class docstring):
  drivers may differ in strategy, never in business semantics. Migration remains a
  recorded follow-up.
- **REGRESSION TEST**: `test_managed_runtime_wires_single_canonical_backend` (single
  wired provider dispatch through the manager).
- **RETEST RESULT**: suite green.

### FINDING-10 — Canonical ↔ LangGraph state bridge unused by production (R-ARCH-00 F-03 handoff)
- **SEVERITY**: LOW
- **ACTUAL**: the declared bridge (`RunState.to_agent_state`/`from_agent_state`,
  `agents/state.py` helpers) is unit-covered but not exercised by the chat path;
  conversations keep state in `AgentState` + MemorySaver.
- **DISPOSITION**: wiring the bridge without the FINDING-9 migration decision would
  create dead code in the other direction (same rationale as R-ARCH-00). Documented as
  the single declared projection in the `RunState.to_agent_state` docstring; chat-path
  RunState materialization remains a recorded follow-up tied to FINDING-9.
- **RETEST RESULT**: suite green.

### FINDING-11 — Dual telemetry authorities (R-ARCH-00 F-04 handoff) — re-verified: adapter relationship exists
- **SEVERITY**: LOW
- **ACTUAL (re-verified this session)**: R-ARCH-00 described the two telemetry modules
  as independent ("neither feeds the other"). Current code shows `AgentTelemetry`
  **forwards every significant event** to the platform registry
  (`app.telemetry.metrics.record_agent_*`) in addition to keeping a bounded in-memory
  snapshot for `GET /api/v1/agent/metrics` (unforwarded residual counters: steps,
  approvals, tokens/cost accumulation — all also derivable platform-side).
- **CLASSIFICATION**: `app/telemetry/metrics.py` = platform authority;
  `app/agent/telemetry.py` = subsystem ADAPTER façade + projection. No duplicate
  business authority (no divergent logic to migrate).
- **FIX**: relationship made explicit in the `AgentTelemetry` module docstring (façade
  over the platform authority; introduces no competing store).
- **RETEST RESULT**: suite green.

---

## 4. Execution Paths & Endpoints Exercised

- **REAL HTTP**: `POST /api/v1/chat/stream` (supervisor→specialist→verifier→synthesizer
  chain + canonical ToolRegistry funnel) via `tests/test_r_arch_00_architecture_integrity.py`
  (re-run after fixes) and `tests/test_r_func_00_api_behavior.py`.
- **Component/integration**: `AgentSelector.select_agent`, `BoundedPlanner.create_initial_plan`,
  `classify_intent`, `FinnApiGo*Tool.execute` (real builtin mock tools — classified
  **MOCK** per RIGHT-00: synthetic FinnApiGo payloads, no real Go backend), `AgentRuntimeManager`
  backend wiring, `resolve_provider_credentials` with fake BYOK/settings doubles
  (**MOCK** doubles for credentials — does not prove real provider connectivity, which
  remains mocked in CI per RIGHT-00 Class D).
- **Static/runtime architecture proofs**: AST import-graph + single-definition-site scans
  executed at test time (**RULE-BASED** proofs), consistent with the R-ARCH-00 approach.

## 5. Tests Executed (local, Python 3.14.4 venv, WSL2, pytest 9.1.1)

**Total collected: 988 tests** (`pytest --collect-only`, summed per chunk).
Execution result: **every test green locally except 2 documented environment
failures, both verified to fail identically on clean `origin/main` and to pass in
GitHub CI** (WSL2 lacks a `python` binary on PATH; WSL2 3.8 GB memory ceiling
OOM-kills the full-app HTTP RAG boundary scenario):

1. `tests/test_agent_platform.py::test_local_safe_sandbox_file_and_commands` —
   sandbox spawns `python` (absent in WSL). Exit 1, sole failure of its chunk.
2. `tests/test_r_func_02_rag_behavior.py::test_scenario_14_http_api_endpoints_complete_boundary` —
   exit 137 (OOM kill) at the 14th of 14 tests; other 13 green. Reproduced on
   `origin/main` via `git stash` re-run.

Chunked execution (memory ceiling): `tests/unit` 193, `tests/evals` 72,
`tests/contract` 10, top-level files in 5 groups (174/120/163/130/126) — all
chunks exit 0 except the two environment failures above. One deliberate
`SKIPPED` (Redis not reachable locally) in `test_r_func_03_cache_behavior.py:1308`.

Branch coverage measured locally across chunks: **86% ≥ 85% floor** — with live
Redis/Qdrant-dependent tests skipped locally; CI (with service containers)
enforces the same floor and passed (see §7).

## 6. Exact Commands & Results

```bash
git checkout -b chore/r-arch-01-canonical-authority origin/main   # baseline b5c1f81
cd backend
.venv/bin/ruff check app tests                                  # "All checks passed!"
.venv/bin/ruff format --check app tests                         # 256 files already formatted
.venv/bin/mypy --config-file mypy.ini app                       # "Success: no issues found in 167 source files"
.venv/bin/pytest tests/test_r_arch_01_canonical_authority.py -q # 13 passed
# full suite in OOM-safe chunks (see §5): 988 collected, 2 pre-existing env failures
.venv/bin/coverage report                                       # TOTAL 86% (floor 85%, CI-enforced)
.venv/bin/pytest tests/evals/test_token_benchmark.py -q         # 2 passed (≥40% gate)
python scripts/run_ai_evaluation.py --output-dir benchmark-results
                                                                # "[SUCCESS] Phase 00 AI Evaluation Benchmark Passed all gates."
.venv/bin/pytest tests/evals/test_portfolio_benchmark.py -q     # passed
.venv/bin/python -m app.main --export-openapi openapi.json
git diff --exit-code openapi.json                               # OPENAPI_NO_DRIFT
python scripts/check_openapi_breaking_changes.py                # "Zero breaking changes detected against baseline revision."
# regression check of pre-existing failures on clean baseline (stash → run → pop):
git stash -u && .venv/bin/pytest tests/test_agent_platform.py::test_local_safe_sandbox_file_and_commands; git stash pop
#   → FAILED on clean origin/main too (env); same for:
git stash -u && .venv/bin/pytest tests/test_r_func_02_rag_behavior.py -q; git stash pop
#   → exit 137 OOM on clean origin/main too (env)
git push -u origin chore/r-arch-01-canonical-authority          # PR opened
```

## 7. CI Result

- **GREEN — 9/9 checks**, run [34786116651](https://github.com/NguyenQuan121321/JakeAI/actions/runs/34786116651)
  on PR [#44](https://github.com/NguyenQuan121321/JakeAI/pull/44), head `bd1942c`,
  `mergeable_state: clean`. Both coverage-floor jobs
  ("Automated Tests & AI RAG Regression" 3.11 and 3.12) passed, confirming the
  two local WSL environment failures are environment-only. No CI modification
  was made or needed.
- Classification: n/a — no CURRENT/SHARED/PREVIOUS regressions introduced; the
  sandbox and RAG-HTTP-OOM failures are environment-local (documented in §5).

## 8. Remaining Issues & Risks

1. **FINDING-8**: specialist simulation math still duplicated across drivers (recommend
   dedicated task).
2. **FINDING-9**: canonical `ExecutionEngine` still HTTP-orphaned; REST surface runs the
   ReAct driver (no CanonicalVerifier pass there — bounded + approval-gated only).
   Migration is documented at the manager facade as the deliberate follow-up.
3. **FINDING-10**: chat conversations do not yet materialize a canonical `RunState`
   (bridge documented, tied to FINDING-9).
4. Legacy `_compute_hash` cache-key shim retained deliberately for migration-compat
   coverage; can be removed once the legacy key layout sunset is decided.
5. `AgentConfig.backend_type` values `direct_provider|external_agent` remain advertised
   but unwired (now explicitly documented); either wire them behind governance or drop
   them in a future cleanup.
6. `WorkflowEngine` removal is owned by R-ARCH-03 (R-ARCH-00 F-02 handoff preserved).

## 9. Manual Test Instructions for Human Reviewer

```bash
cd backend
# 1. Canonical authority regression suite
.venv/bin/pytest tests/test_r_arch_01_canonical_authority.py -v
# 2. Prior architecture invariants still hold
.venv/bin/pytest tests/test_r_arch_00_architecture_integrity.py -v
# 3. Full suite
.venv/bin/pytest tests/ -q
# 4. Optional live check: start server and confirm chat tool path still routes
#    "finnapi fetch account balance ..." to the balance tool via the registry:
uv run uvicorn app.main:app --port 8000 &
curl -N -X POST http://localhost:8000/api/v1/chat/stream \
  -H "Authorization: Bearer <JWT with role=admin, permission=accounts:read>" \
  -H "Content-Type: application/json" \
  -d '{"prompt":"finnapi fetch account balance","conversation_id":"manual-arch-01"}'
#    Expect SSE frames containing event: tool_call with tool_name get_account_balance.
```

## 10. Real / Rule-Based / Mock / Not-Verified Classification

- Capability keyword classification (canonical patterns + layer agreement): **RULE-BASED**, verified.
- Credential resolution order (BYOK → platform): **REAL** logic with **MOCK** credential doubles (provider connectivity itself remains **NOT VERIFIED** live — unchanged from baseline Class D).
- OBO exchange & account identity: **RULE-BASED/REAL** code paths over **MOCK** FinnApiGo payloads (**NOT VERIFIED** against a real FinnApiGo backend — unchanged, see RIGHT-00 RISK-01).
- Lifecycle authority & duplicate removal: **REAL** (code + tests).
- HTTP chat tool funnel: **REAL** (FastAPI TestClient HTTP boundary).
