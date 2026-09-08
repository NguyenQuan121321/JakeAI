# JAKEAI REPAIR — REPAIR-02: HANDOFF TO REPAIR-03

> **Originating Task:** REPAIR-02 — Repair Planning  
> **Receiving Task:** REPAIR-03 — Correctness Repair Worker  
> **Timestamp:** 2026-09-08  
> **Status:** HANDOFF READY  

---

## 1. Task Completed

- Constructed the executable, dependency-sequenced Repair Plan for JakeAI in `docs/ai-engineering/repair/repair-plan.md`.
- Formulated 21 isolated, test-driven Task Cards across the 5 prescribed workstreams:
  - **Workstream R1 — Request / Inference Correctness** (`TASK-R1-01` to `TASK-R1-04`)
  - **Workstream R2 — Infrastructure Correctness** (`TASK-R2-01` to `TASK-R2-03`)
  - **Workstream R3 — Streaming / Agent Correctness** (`TASK-R3-01` to `TASK-R3-04`)
  - **Workstream R4 — RAG Correctness** (`TASK-R4-01` to `TASK-R4-03`)
  - **Workstream R5 — Structural Repair** (`TASK-R5-01` to `TASK-R5-07`)
- Defined all 11 required fields for every task: `TASK ID`, `OBJECTIVE`, `WHY NOW`, `DEPENDENCIES`, `AFFECTED FILES`, `INVARIANT`, `REGRESSION TEST`, `SECURITY REQUIREMENTS`, `OBSERVABILITY REQUIREMENTS`, `ACCEPTANCE CRITERIA`, and `FORBIDDEN CHANGES`.
- Constructed global dependency graph (ASCII and Mermaid) enforcing correctness-first ordering, architectural prerequisites, contract isolation, and invariant preservation.
- Mapped workstreams to the master repair pipeline:
  - Workstream R1 → Phase `REPAIR-03`
  - Workstream R2 → Phase `REPAIR-04`
  - Workstreams R3 & R4 → Phase `REPAIR-05`
  - Workstream R5 & Integration → Phase `REPAIR-06`
- Maintained strict non-destructive compliance: 0 production code files, 0 test files, and 0 configuration files modified.
- Updated `docs/ai-engineering/state/repair-state.md` to transition R2 to `COMPLETED` and R3 to `READY`.

---

## 2. Acceptance Criteria Status

| Acceptance Criterion | Status | Objective Evidence |
| :--- | :---: | :--- |
| Read and comply with Universal Worker & Repair Master prompts | **MET** | Verified and adhered to across all R2 planning outputs. |
| Group work into R1 (Request), R2 (Infra), R3 (Streaming/Agent), R4 (RAG), R5 (Structural) | **MET** | Implemented in `docs/ai-engineering/repair/repair-plan.md`. |
| Define all 11 required fields for every task | **MET** | Fully specified across all 21 task cards. |
| Construct dependency graph following 4 planning rules | **MET** | Detailed in Section 2 of `repair-plan.md`. |
| Zero production code modifications during R2 | **MET** | `git status` verifies 0 source or test files touched. |
| Create `docs/ai-engineering/repair/repair-plan.md` | **MET** | Created with complete specifications. |
| Update project repair state (`repair-state.md`) | **MET** | Updated with Phase R2 COMPLETED, Phase R3 READY, and active plan summary. |
| End with exactly one next task | **MET** | Recommended `TASK-R1-01` under `docs/repair/R3/REPAIR-03 — Correctness Repair Worker.md`. |

---

## 3. Files Created or Modified

### Files Created:
1. `docs/ai-engineering/repair/repair-plan.md`
2. `docs/repair/R2/RESULT.md`
3. `docs/repair/R2/HANDOFF.md`

### Files Modified:
1. `docs/ai-engineering/state/repair-state.md`

### Production / Test Files Modified:
- *None (0 production files, 0 test files, 0 CI configuration files modified).*

---

## 4. Objective Verification Evidence & Checks Run

| Tool / Check | Command Executed | Result | Objective Output Summary |
| :--- | :--- | :---: | :--- |
| **Linter** | `uv run --project backend ruff check backend/` | **PASS** | `All checks passed!` across 184 files |
| **Type Checker** | `uv run --project backend mypy --config-file backend/mypy.ini backend/app` | **PASS** | `Success: no issues found in 141 source files` |
| **Git Working Tree** | `git status` | **CLEAN** | 0 production or test files modified |

---

## 5. Architectural Invariants for Upcoming Repair Work

1. **`TASK-R1-01` Invariant (`DUP-02`):** Model-to-provider resolution MUST have exactly one authoritative implementation: `ProviderRegistry.resolve_provider_name_for_model()`.
2. **`TASK-R1-02` Invariant (`PROV-02`):** `ProviderRequest` MUST accept structured conversation turns (`messages: list[ChatMessage]`), and provider adapters MUST preserve native role designations (`user`, `assistant`, `tool`).
3. **`TASK-R1-03` Invariant (`CACHE-01`):** Exact response cache keys MUST be a composite hash of `(tenant_id, provider, model, version, hash(messages), system_prompt, hash(tools), temperature)`.
4. **`TASK-R1-04` Invariant (`TOK-02`):** `raw_prompt_tokens` MUST reflect all model-visible input tokens (`system_instruction` + message turns + query + tools).
5. **`TASK-R2-01` Invariant (`DUP-01`):** Shared Redis connections MUST have exactly one lifecycle owner (`RedisConnectionManager`) bound to FastAPI `lifespan`.
6. **`TASK-R2-02` Invariant (`PROV-01`):** Outbound HTTP transport MUST reuse an application-scoped, pooled `httpx.AsyncClient`.
7. **`TASK-R2-03` Invariant (`PERF-01`):** Quota verification and token allocation MUST execute as an indivisible atomic reservation (Redis Lua script).

---

## 6. Durable Information for Next Task (REPAIR-03)

### What REPAIR-03 Needs to Do:
- Read `docs/repair/R3/REPAIR-03 — Correctness Repair Worker.md`.
- Read `docs/ai-engineering/repair/repair-plan.md` (Workstream R1).
- Execute the immediate starting task: **`TASK-R1-01` (`DUP-02`: Canonical Model-to-Provider Resolution)**.
  - Delete lines 342–350 in `backend/app/services/ai_gateway.py`.
  - Delegate resolution to `get_provider_registry().resolve_provider_name_for_model(request.model)`.
  - Add regression test `backend/tests/unit/test_ai_gateway_routing.py` proving `deepseek-chat` resolves to `"deepseek"` and `llama-3.3-70b-versatile` resolves to `"groq"`.
- Following `TASK-R1-01`, proceed to `TASK-R1-02` (`PROV-02`), `TASK-R1-03` (`CACHE-01`), and `TASK-R1-04` (`TOK-02`).

### Key Guidance for R3:
- Always follow the repair loop: Understand → Reproduce (failing test) → Minimal Fix → Verify → State Update.
- Preserve backward compatibility on `ProviderRequest`: retain `prompt: str` while adding `messages: list[ChatMessage] | None = None`.
- Run focused tests first (`pytest backend/tests/unit/test_ai_gateway_routing.py`) before running the broader suite.

---

## 7. Remaining Risks and Blockers

- **Risk:** Updating `ProviderRequest` in `TASK-R1-02` will touch all 6 provider adapters (`openai`, `anthropic`, `gemini`, `groq`, `deepseek`, `openrouter`). Ensure mock fixtures in existing provider tests are updated concurrently.
- **Risk:** Composite cache keys in `TASK-R1-03` will change cache key hashes; verify that any existing unit tests expecting specific cache keys are updated to use the composite generator.
- **Blockers:** None. Phase REPAIR-03 is fully unblocked.

---

## 8. Recommended Next Task

- **Phase:** **`REPAIR-03 — Correctness Repair Worker`**
- **Specification Document:** `docs/repair/R3/REPAIR-03 — Correctness Repair Worker.md`
- **Initial Task:** **`TASK-R1-01` (`DUP-02`: Canonical Model-to-Provider Resolution)**
