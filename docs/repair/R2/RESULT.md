# JAKEAI REPAIR — REPAIR-02: REPAIR PLANNING RESULT

> **Execution Date:** 2026-09-08  
> **Phase:** REPAIR-02 — Repair Planning  
> **Status:** COMPLETED  
> **Worker:** Principal AI Platform Engineer (Antigravity Diagnostic & Planning Engine)  
> **Compliance Standard:** JakeAI Universal AI Engineering Worker & Repair Master Prompt  

---

## 1. Executive Summary of Work Completed

During session **REPAIR-02**, the engineering worker constructed the complete, executable, dependency-ordered Repair Plan for the JakeAI platform. 

In strict compliance with the project's foundation prompts and the REPAIR-02 task definition:
1. **Zero production code files were modified.** (`backend/app/` remains 100% untouched).
2. **Zero test files were modified or deleted.** (`backend/tests/` remains 100% untouched).
3. **Zero dependencies were added or altered.** (`pyproject.toml` remains untouched).
4. **All 30 verified audit findings were organized into 21 isolated, test-driven task cards** grouped across the 5 prescribed workstreams:
   - **Workstream R1 — Request / Inference Correctness** (`CACHE-01`, `PROV-02`, `TOK-02`, `DUP-02`, plus `CACHE-02`, `CACHE-04`, `TOK-03`).
   - **Workstream R2 — Infrastructure Correctness** (`PROV-01`, `DUP-01`, `PERF-01`, plus `PERF-02`).
   - **Workstream R3 — Streaming / Agent Correctness** (`PROV-04`, `CACHE-03`, `AGT-01`, `AGT-03`, plus `AGT-02`).
   - **Workstream R4 — RAG Correctness** (`RAG-01`, `RAG-02`, `RAG-04`, plus `RAG-03`, `DUP-05`, `PERF-03`).
   - **Workstream R5 — Structural Repair** (`TYPE-01`, `TYPE-02`, `TYPE-03`, `DUP-03`, `DUP-04` / `TOK-01`, `DUP-06`, plus `BYOK-01`, `CI-01`).
5. **Every task card defines the full 11-field specification:**
   `TASK ID`, `OBJECTIVE`, `WHY NOW`, `DEPENDENCIES`, `AFFECTED FILES`, `INVARIANT`, `REGRESSION TEST`, `SECURITY REQUIREMENTS`, `OBSERVABILITY REQUIREMENTS`, `ACCEPTANCE CRITERIA`, and `FORBIDDEN CHANGES`.
6. **Global dependency graph constructed:** Rendered in both ASCII and Mermaid format, enforcing:
   - Correctness before optimization
   - Architectural prerequisite before dependent repair
   - No parallel work on overlapping contracts
   - Protection against silent invariant mutation
7. **Created authoritative repair plan:** `docs/ai-engineering/repair/repair-plan.md`.
8. **Updated project repair state:** `docs/ai-engineering/state/repair-state.md` transitioning Phase R2 to `COMPLETED` and Phase R3 to `READY`.
9. **Single immediate next task identified:** `TASK-R1-01` (`DUP-02`: Canonical Model-to-Provider Resolution) under Phase `REPAIR-03`.

---

## 2. Objective Verification Evidence & Checks Executed

The following checks and verification suites were run directly on the live repository during this session:

| Subsystem Check | Command Executed | Exit Code | Result | Objective Output Summary |
| :--- | :--- | :---: | :---: | :--- |
| **Linter** | `uv run --project backend ruff check backend/` | `0` | **PASS** | `All checks passed!` across 184 files |
| **Type Checker** | `uv run --project backend mypy --config-file backend/mypy.ini backend/app` | `0` | **PASS** | `Success: no issues found in 141 source files` |
| **Git Working Tree** | `git status` | `0` | **CLEAN** | 0 production or test files modified |

---

## 3. Workstream & Task Card Directory

| Workstream | Phase Mapping | Task ID | Primary Finding | Focus / Core Invariant |
| :--- | :--- | :--- | :--- | :--- |
| **R1 — Request / Inference** | Phase R3 | `TASK-R1-01` | `DUP-02` | Canonical Model-to-Provider Resolution via `ProviderRegistry` |
| | Phase R3 | `TASK-R1-02` | `PROV-02` | Structured Multi-Turn Messages (`list[ChatMessage]`) in `ProviderRequest` |
| | Phase R3 | `TASK-R1-03` | `CACHE-01` | Composite Exact Response Cache Key Isolation |
| | Phase R3 | `TASK-R1-04` | `TOK-02` | Full-Envelope Model-Visible Token Accounting & Ledger Separation |
| **R2 — Infrastructure** | Phase R4 | `TASK-R2-01` | `DUP-01` | Centralized Redis Connection Lifecycle Manager in `core/redis.py` |
| | Phase R4 | `TASK-R2-02` | `PROV-01` | Application-Scoped Pooled HTTP Client in `core/http_client.py` |
| | Phase R4 | `TASK-R2-03` | `PERF-01` | Atomic Concurrency Quota Reservation via Redis Lua Script |
| **R3 — Streaming / Agent** | Phase R5 | `TASK-R3-01` | `CACHE-03` | Static System Instruction Prefix Stability in Agent Planner |
| | Phase R5 | `TASK-R3-02` | `PROV-04` | Native SSE Event-Stream Yielding in AI Gateway |
| | Phase R5 | `TASK-R3-03` | `AGT-01` | Tool Output Token Budgeting ($\le 2,000$ tokens) & Truncation |
| | Phase R5 | `TASK-R3-04` | `AGT-03` | Constraint-Preserving Memory Compaction (Pin User Instructions) |
| **R4 — RAG Correctness** | Phase R5 | `TASK-R4-01` | `RAG-01` | Pluggable `EmbeddingProvider` Abstraction & Dense Retrieval |
| | Phase R5 | `TASK-R4-02` | `RAG-02` | Elimination of Retrieval Score Telemetry from Formatted Prompts |
| | Phase R5 | `TASK-R4-03` | `RAG-04` | Formatted RAG Context Accounting & Min-Heap Optimization |
| **R5 — Structural Repair** | Review/Consolidation | `TASK-R5-01` | `TYPE-01` | Strict Static Typing on Infrastructure Handles (`Redis | None`) |
| | | `TASK-R5-02` | `TYPE-02` | Strongly-Typed Tool Schemas, Arguments, and Choices |
| | | `TASK-R5-03` | `TYPE-03` | Narrow Operational Exception Hygiene on Storage/Crypto Paths |
| | | `TASK-R5-04` | `DUP-03` | Consolidation of FinOps Pricing Catalog into `app.finops.pricing` |
| | | `TASK-R5-05` | `DUP-04` / `TOK-01` | Canonical Token Estimation via `BPETokenizer` on Hot Paths |
| | | `TASK-R5-06` | `DUP-06` | Unified Token Quota Governance under `BudgetManager` |
| | | `TASK-R5-07` | `BYOK-01` / `CI-01` | Cryptographic HKDF Upgrade & In-Memory Fallback CI Coverage |

---

## 4. Status of Acceptance Criteria

| Acceptance Criterion | Status | Objective Evidence |
| :--- | :---: | :--- |
| Read and comply with Universal Worker & Repair Master prompts | **MET** | Referenced in session and strictly adhered to across all deliverables. |
| Group work into R1 (Request), R2 (Infra), R3 (Streaming/Agent), R4 (RAG), R5 (Structural) | **MET** | Organized in `docs/ai-engineering/repair/repair-plan.md` sections 3.1 to 3.5. |
| For each task define all 11 required fields | **MET** | All 21 task cards define `TASK ID`, `OBJECTIVE`, `WHY NOW`, `DEPENDENCIES`, `AFFECTED FILES`, `INVARIANT`, `REGRESSION TEST`, `SECURITY REQUIREMENTS`, `OBSERVABILITY REQUIREMENTS`, `ACCEPTANCE CRITERIA`, and `FORBIDDEN CHANGES`. |
| Build dependency graph adhering to 4 core planning rules | **MET** | Rendered in ASCII and Mermaid in `repair-plan.md` section 2. |
| Zero production code implementation in R2 | **MET** | `git status` verifies 0 source or test files touched. |
| Write `docs/ai-engineering/repair/repair-plan.md` | **MET** | File created and validated. |
| Update `docs/ai-engineering/state/repair-state.md` | **MET** | Updated with Phase R2 COMPLETED, Phase R3 READY, and active plan summary. |
| End with exactly one next task | **MET** | Recommended `TASK-R1-01` under `docs/repair/R3/REPAIR-03 — Correctness Repair Worker.md`. |

---

## 5. Files Created or Modified

### Files Created:
1. `docs/ai-engineering/repair/repair-plan.md`
2. `docs/repair/R2/RESULT.md`
3. `docs/repair/R2/HANDOFF.md`

### Files Modified:
1. `docs/ai-engineering/state/repair-state.md`

### Production / Test Files:
- **0 production code files modified.**
- **0 test files modified.**
- **0 configuration files modified.**

---

## 6. Remaining Risks and Blockers

- **Risk:** `TASK-R1-02` (adding `messages` to `ProviderRequest`) modifies the foundation dataclass used by all 6 provider adapters (`openai`, `anthropic`, `gemini`, `groq`, `deepseek`, `openrouter`). All 6 adapters and existing provider unit tests must be updated atomically to prevent contract breakage.
- **Risk:** In `TASK-R1-03`, exact cache keys will become composite hashes. Any existing unit tests in `test_ai_gateway.py` that manually mocked or checked legacy unkeyed cache keys will need their assertions updated to reflect composite keys.
- **Blockers:** None. REPAIR-03 (Correctness Repair Worker) is fully unblocked and ready for immediate execution.

---

## 7. Next Recommended Task

- **Phase:** **`REPAIR-03 — Correctness Repair Worker`**
- **Specification Document:** `docs/repair/R3/REPAIR-03 — Correctness Repair Worker.md`
- **Initial Task:** **`TASK-R1-01` (`DUP-02`: Canonical Model-to-Provider Resolution)**
