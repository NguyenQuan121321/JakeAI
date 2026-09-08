# JAKEAI REPAIR — REPAIR-00: HANDOFF TO REPAIR-01

> **Originating Task:** REPAIR-00 — Bootstrap  
> **Receiving Task:** REPAIR-01 — Baseline & Audit Verification  
> **Timestamp:** 2026-09-08  
> **Status:** HANDOFF READY  

---

## 1. Task Completed
- Reconstructed complete engineering context, architectural boundaries, and subsystem contracts across `backend/app/` using the smallest sufficient context.
- Inspected and classified all 30 audit findings against the live repository with exact file locations and code snippets (100% verified, 0 false positives).
- Established verified empirical baseline metrics (311 tests passing, 0 Ruff errors, 0 MyPy errors, 0 Bandit issues, 48.74% portfolio token reduction, 84.25% containerless branch coverage).
- Formulated dependency topology, risk map, and progressive execution workstreams (R1 through R5).
- Created durable project state (`docs/ai-engineering/state/repair-state.md`) and prompt archives (`docs/ai-engineering/prompts/`).

---

## 2. Acceptance Criteria Status

| Acceptance Criterion | Status | Evidence |
| :--- | :---: | :--- |
| Read and comply with Universal Worker & Repair Master prompts | **MET** | Archived in `docs/ai-engineering/prompts/` and adhered to across R0 execution |
| Reconstruct system understanding across 11 core domains | **MET** | Documented in `docs/repair/R0/RESULT.md` Section 1 |
| Classify all repair findings against repository evidence | **MET** | All 30 findings inspected and classified in `docs/repair/R0/RESULT.md` Section 2 |
| Build dependency graph and risk map | **MET** | Documented in `docs/repair/R0/RESULT.md` Sections 3 and 4 |
| Propose execution sequence for 5 repair workstreams | **MET** | Documented in `docs/repair/R0/RESULT.md` Section 5 |
| Zero production code modifications during R0 | **MET** | Git status confirms 0 production files or tests modified |
| Produce `RESULT.md` and `HANDOFF.md` under `docs/repair/R0/` | **MET** | Files created with full objective verification data |
| Update project repair state | **MET** | Created `docs/ai-engineering/state/repair-state.md` |

---

## 3. Files Created or Modified

### Files Created:
1. `docs/ai-engineering/prompts/universal-worker.md`
2. `docs/ai-engineering/prompts/repair-master.md`
3. `docs/ai-engineering/state/repair-state.md`
4. `docs/repair/R0/PROMPT.md`
5. `docs/repair/R0/RESULT.md`
6. `docs/repair/R0/HANDOFF.md`

### Files Modified:
- *None (0 production files, 0 test files, 0 CI files modified).*

---

## 4. Objective Verification Evidence & Checks Run

| Check / Tool | Command Executed | Result | Objective Output Summary |
| :--- | :--- | :---: | :--- |
| **Linter** | `uv run --project backend ruff check backend/` | **PASS** | `All checks passed!` across 184 files |
| **Formatter** | `uv run --project backend ruff format --check backend/` | **PASS** | `184 files already formatted` |
| **Type Checker** | `uv run --project backend mypy --config-file backend/mypy.ini backend/app` | **PASS** | `Success: no issues found in 141 source files` |
| **SAST Security** | `uv run --project backend bandit -c pyproject.toml -r app/` | **PASS** | `Total lines of code: 19636. Total issues: 0` |
| **Test Suite** | `uv run --project backend pytest -q` | **PASS** | `311 passed, 1 warning in 98.49s` |
| **Benchmark** | `pytest tests/evals/test_portfolio_benchmark.py` (included in pytest run) | **PASS** | `48.74% Net Token Reduction, Quality: 1.0000, 8/8 Passed` |
| **Branch Coverage** | `uv run --project backend coverage report` | **PASS/WARN** | `84.25%` (Fails 85% floor under containerless local run per `CI-01`) |

---

## 5. Architectural Invariants for Upcoming Repair Work

1. **`CACHE-01` Invariant:** Exact response cache keys MUST be a composite hash of `(tenant_id, provider, model, version, hash(messages), system_prompt, hash(tools), temperature)`.
2. **`PROV-02` Invariant:** `ProviderRequest` MUST accept structured conversation turns (`messages: list[ChatMessage]`), and provider adapters MUST preserve native role designations (`user`, `assistant`, `tool`).
3. **`TOK-02` Invariant:** `raw_prompt_tokens` MUST reflect the full model-visible input envelope (`system_instruction` + all message turns + query), preventing tenant quota evasion.
4. **`DUP-02` Invariant:** Model-to-provider resolution MUST be handled solely by `ProviderRegistry.resolve_provider_name_for_model()`.
5. **`CACHE-03` Invariant:** Agent system instructions MUST remain byte-for-byte static across all iterations of an execution loop to enable upstream provider KV prompt caching.
6. **`DUP-01` / `PROV-01` Invariant:** Redis and HTTP client connections MUST be managed through centralized, application-scoped pools bound to FastAPI lifespan.
7. **`PERF-01` Invariant:** Token quota checks and deductions MUST execute as an atomic reservation (Redis Lua script).

---

## 6. Durable Information for Next Task (REPAIR-01)

### What REPAIR-01 Needs to Do:
- Read `docs/repair/R1/REPAIR-01 — Baseline & Audit Verification.md`.
- Read `docs/ai-engineering/state/repair-state.md`.
- For each finding, perform caller-level inspection, determine downstream effects, identify existing tests covering the behavior, and classify findings into `docs/ai-engineering/state/repair-findings.md`.
- Identify the highest-value unblocked repair candidate.
- **Do not modify production source code during R1.**

### Key Watch Items for R1:
- `CACHE-01` and `PROV-02` are the primary unblockers for inference correctness.
- In `ai_gateway.py`, verify how `request.messages` are processed when `TwoZonePromptCompiler` is active.
- Verify whether existing tests in `backend/tests/services/test_ai_gateway.py` rely on the existing flawed `last_user_msg` cache behavior.

---

## 7. Remaining Risks and Blockers

- **Risk:** Existing tests might assert on legacy cache key formats or mock provider signatures. When updating `ProviderRequest` in R3, existing mocks must be updated consistently.
- **Risk:** Local test runs without Docker Compose cannot achieve 85% branch coverage (currently 84.25%) due to live connection branches in Redis and Qdrant.
- **Blockers:** None for starting REPAIR-01.

---

## 8. Recommended Next Task

**Task:** **`docs/repair/R1/REPAIR-01 — Baseline & Audit Verification.md`**  
**Action:** Execute Baseline & Audit Verification to produce `docs/ai-engineering/state/repair-findings.md`.
