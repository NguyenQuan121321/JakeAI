# R-LOGIC-01 — State Transitions — Result

**Task**: R-LOGIC-01 — State Transitions (RIGHT Phase 2 — Logic Correctness)
**Baseline**: `main` @ `38b2bc2` (merge of PR #38, R-LOGIC-00)
**Branch**: `chore/r-logic-01-state-transitions`
**Date**: 2026-09-13
**Status**: VERIFIED — 7 confirmed defects found, fixed, regression-tested; CI-equivalent local checks green.

---

## 1. Scope Inspected

The complete orchestration state machine for Task/Run/Plan/Step/Approval/Verification, mapped to every actual status write point:

| Component | State model | Primary code paths |
|---|---|---|
| Run | `RunStatus` (14 states) + `RunState.transition_to` matrix | `app/agent/state/models.py`, `app/agent/execution/engine.py`, `app/agent/runtime/{manager,loop,runner}.py` |
| Task | `TaskStatus` (14 states) — had NO machine at all | `app/agent/state/models.py`, `app/agent/runtime/{manager,loop,runner}.py` |
| Plan/Step | `StepStatus` (10 states) via `ExecutionPlan.mark_step_status` | `app/agent/domain/contracts.py`, `app/agent/execution/engine.py`, `app/agent/recovery/recovery.py` |
| Approval | `ApprovalStatus` (PENDING/APPROVED/REJECTED), single-decision guard | `app/agent/approvals/manager.py`, `app/agent/runtime/manager.py` |
| Verification | `VerificationVerdict` (PASS/NEEDS_REVISION/FAILED/REJECTED) | `app/agent/verification/verifier.py`, `app/agent/execution/engine.py` |
| Checkpoint | `CheckpointRecord(RunState)` persistence + restore | `app/agent/state/checkpoint.py` |

All production status writers were enumerated by grep and individually traced: 19 direct `.status =` write sites in `engine.py`, 3 in `manager.py`, 6 in `loop.py`, 2 in `runner.py`.

**Headline discovery**: the canonical run state machine (`RunState.transition_to` + transition matrix) was **dead code** — its only caller was a unit test. Every production write was a raw attribute assignment, so no invalid transition could ever be rejected.

## 2. Execution Paths & Interfaces Tested

- **HTTP boundary (real FastAPI app via ASGI transport + real JWT auth)**: `POST /api/v1/agent/tasks`, `POST /api/v1/agent/tasks/{id}/runs` (sync execution), `GET .../runs/{id}`, `POST .../runs/{id}/cancel`, `POST .../runs/{id}/approvals/{approval_id}`, `GET /api/v1/agent/approvals/pending`.
- **Service boundary**: `AgentRuntimeManager` (create/execute/cancel/decide_approval), `ExecutionEngine.execute_task` / `resume_run` / `_run_execution_loop` / `_execute_single_step`, `AgentRunner.start_run` (asyncio cancellation race), `AgentExecutionLoop.execute`, `BoundedRecoveryEngine.evaluate_step_failure`, `CheckpointManager.save/resume_run_from_checkpoint`.
- **Upstream model calls**: controlled doubles at the module boundary (`call_upstream_llm_detailed` stubs, `MockControllableBackend`) — they verify state-machine behavior only, not live provider integration.

## 3. Real / Rule-Based / Mock / Not-Verified Classification

| Capability under test | Classification |
|---|---|
| Run/Task state machine + enforcement | REAL (in-process deterministic machine, enforced at every write path) |
| Engine DAG dispatch, verification loop, replan cycle | REAL |
| Checkpoint persistence & restore | REAL (in-process manager; Redis path activates in CI) |
| Approval gates & decisions | REAL (single-decision guard enforced in `ApprovalManager.decide`) |
| Step recovery (retry/agent-switch/model-switch) | REAL (deterministic, now count-bounded) + RULE-BASED error classification |
| Upstream LLM generation in platform/engine tests | MOCK (test doubles) — does not prove live provider integration (R-FUNC-04 scope) |
| Live cloud providers, real Redis locally | NOT VERIFIED locally — CI provides Redis 7 + Qdrant services |
| `WorkflowEngine` (`app/agent/workflows/engine.py`) | Separate simple sequential engine (PENDING→RUNNING→COMPLETED/FAILED); no production callers, no HTTP exposure; its status flow is structurally safe. Noted, out of task scope. |

## 4. Findings

All defect-proving tests **failed on unmodified main first** (pre-fix run: 11 failed / 13 passed of the 24-test suite; exact evidence below), then were fixed and re-verified (24/24 pass). Evidence in `backend/tests/test_r_logic_01_state_transitions.py`.

---

### RL01-F-01 — SEVERITY: HIGH (systemic) — State machine was dead code; every write bypassed it
- **EXPECTED**: No invalid transition can be persisted or executed (task acceptance criterion); all writes flow through the enforced matrix.
- **ACTUAL**: `RunState.transition_to` was called only from a unit test. All ~30 production write sites assigned `.status` directly; an invalid assignment was silently persisted. Demonstrated pre-fix: `test_every_forbidden_run_transition_is_rejected_via_assignment`, `test_named_forbidden_transitions_cannot_silently_succeed` (FAILED→COMPLETED etc. all persisted), `test_transition_matrix_survives_checkpoint_roundtrip` ("DID NOT RAISE ValueError").
- **ROOT CAUSE**: the matrix was implemented (with `transition_to`) but never wired into writers; nothing validated attribute assignment.
- **AFFECTED FILES / PATH**: `app/agent/state/models.py` (enforcement), all writers in `app/agent/execution/engine.py`, `app/agent/runtime/{manager,loop,runner}.py`.
- **FIX**: enforcement moved into the model itself: `RunState.__setattr__` validates every `status` write **before mutation** against the canonical matrix (`RUN_TRANSITIONS` / `assert_run_transition`); terminal states immutable; identical re-assignment is an idempotent no-op; invalid enum values rejected. Same mechanism for `TaskState` with `TASK_TRANSITIONS`. `transition_to` remains the explicit API on top of the same assertion. (Note: pydantic `validate_assignment` + after-validator was tested first and rejected — it mutates the field *before* the validator raises, leaving corrupted state on the failed write.)
- **REGRESSION TEST**: `test_every_forbidden_run_transition_is_rejected_via_assignment` (exhaustive ~117 illegal pairs), `test_named_forbidden_transitions_cannot_silently_succeed`, `test_transition_matrix_survives_checkpoint_roundtrip`, `test_self_assignment_is_idempotent_noop`.
- **RETEST**: PASS.

### RL01-F-02 — SEVERITY: CRITICAL — Late cancellation corrupted terminal state
- **EXPECTED**: A cancellation delivered after a run reached a terminal state must not change the terminal record.
- **ACTUAL**: `AgentRunner.start_run`'s `except asyncio.CancelledError` unconditionally set `run.status = CANCELLED`. A cancel landing during the completion path's final awaits (checkpoint save / SSE broadcast) flipped COMPLETED→CANCELLED. Reproduced deterministically pre-fix: `test_late_cancellation_after_completion_preserves_terminal_state` → "terminal state corrupted to cancelled by late cancellation".
- **ROOT CAUSE**: the CancelledError handler had no terminal-state guard (same defect class as R-LOGIC-00 RL00-F-01, different code path).
- **AFFECTED FILES / PATH**: `app/agent/runtime/runner.py` (`start_run`) ← `manager.execute_run` ← `POST /api/v1/agent/tasks/{id}/runs`.
- **FIX**: terminal guard in the handler — status written only when not `run.status.is_terminal`; event broadcast and re-raise unchanged.
- **REGRESSION TEST**: `test_late_cancellation_after_completion_preserves_terminal_state` (real loop + real runner; cancellation injected inside the FINISH branch's checkpoint await).
- **RETEST**: PASS (run stays COMPLETED, task stays COMPLETED).

### RL01-F-03 — SEVERITY: HIGH — VERIFYING / REPLANNING states unreachable; matrix lacked REPLANNING→EXECUTING
- **EXPECTED**: The documented lifecycle traverses VERIFYING during verification and REPLANNING during replanning; after a replan, revised execution resumes.
- **ACTUAL**: The engine never left EXECUTING — it jumped EXECUTING→COMPLETED/FAILED/REJECTED directly, and the matrix had no REPLANNING→EXECUTING edge. Checkpoint observers and API consumers could never see verification/replan states.
- **EVIDENCE**: `test_engine_traverses_verifying_and_replanning_states` failed pre-fix (verification_started observed at EXECUTING).
- **ROOT CAUSE**: status writes were never added to the verification/replan sections; the matrix was authored for the full lifecycle but the engine used a subset.
- **AFFECTED FILES / PATH**: `app/agent/execution/engine.py` (`_run_execution_loop` verification section), `app/agent/state/models.py` (matrix).
- **FIX**: `EXECUTING→VERIFYING` set before `verification_started`; `VERIFYING→REPLANNING` before `replan_started`; `REPLANNING→EXECUTING` after the replan (new matrix edge) and before the post-replan checkpoint.
- **REGRESSION TEST**: `test_engine_traverses_verifying_and_replanning_states`, `test_engine_rejected_verdict_terminates_from_verifying`, `test_engine_revision_ceiling_terminates_failed`.
- **RETEST**: PASS.

### RL01-F-04 — SEVERITY: HIGH — Restored pre-execution runs drove to terminal states via forbidden transitions
- **EXPECTED**: A run restored from a checkpoint (e.g. READY captured in the crash window between planning and dispatch) re-enters the machine legally.
- **ACTUAL**: `resume_run` passed the restored run straight into the execution loop; the loop drove it READY→COMPLETED (not a matrix edge). Silent pre-enforcement; guaranteed ValueError after RL01-F-01's enforcement — i.e. resume of such runs would have crashed.
- **EVIDENCE**: interplay proven by `test_resume_from_ready_checkpoint_completes_legally` / `test_resume_from_running_checkpoint_completes_legally` (these fail once enforcement lands without normalization).
- **ROOT CAUSE**: no status normalization at execution-loop entry.
- **AFFECTED FILES / PATH**: `app/agent/execution/engine.py` (`_run_execution_loop` entry / `_normalize_to_executing`).
- **FIX**: `_normalize_to_executing` at loop entry — non-terminal, non-approval states are brought to EXECUTING via matrix-legal hops (CREATED/PLANNING/VERIFYING/REPLANNING → RUNNING → EXECUTING; READY/RUNNING → EXECUTING).
- **REGRESSION TEST**: the two resume-from-checkpoint tests above.
- **RETEST**: PASS.

### RL01-F-05 — SEVERITY: MEDIUM — Agent-switch recovery unbounded in attempt count
- **EXPECTED**: Retry creates bounded new attempts (task requirement); recovery terminates deterministically.
- **ACTUAL**: When a step exhausted `MAX_STEP_RETRIES` and an alternative agent existed, the recovery engine switched agents on *every* subsequent failure — with ≥2 eligible agents the step alternated A↔B indefinitely, bounded only by the run wall-clock timeout (60 s default), burning provider calls per switch. `RecoveryLimits.MAX_TOTAL_ITERATIONS` existed but was never enforced in the DAG loop.
- **EVIDENCE**: `test_agent_switch_recovery_is_bounded_in_attempt_count` (pre-fix: switch events only stop at the 2 s test timeout; post-fix: ≤ 2).
- **ROOT CAUSE**: the retry-exhausted branch re-selected an alternative agent with no switch budget; `retries_exhausted` kept incrementing past the cap but never terminated the switch path.
- **AFFECTED FILES / PATH**: `app/agent/recovery/recovery.py` (`evaluate_step_failure`, `RecoveryLimits`), `app/agent/execution/engine.py` (SWITCH_AGENT branch), `app/agent/domain/contracts.py` (`PlanStep.agent_switches`).
- **FIX**: `RecoveryLimits.MAX_AGENT_SWITCHES = 2`; the exhaustion branch terminates FAILED once `step.agent_switches` reaches the cap; the engine grants each alternative agent a fresh retry budget (`retries_exhausted = 0`, `agent_switches += 1`) and selects alternatives round-robin. Single-switch success semantics preserved.
- **REGRESSION TEST**: `test_agent_switch_recovery_is_bounded_in_attempt_count` (bounded switches + bounded executions + terminal FAILED), `test_step_retry_is_bounded_and_terminates_failed`.
- **RETEST**: PASS.

### RL01-F-06 — SEVERITY: HIGH — Approval rejection stranded the run in an immortal zombie RUNNING state
- **EXPECTED**: Rejecting an approval gate terminates the run REJECTED (terminal), consistent with the canonical engine's rejection semantics (`resume_run(approved=False)` → REJECTED) and the matrix (WAITING/PAUSED→REJECTED).
- **ACTUAL**: `AgentRuntimeManager.decide_approval` (reject branch) set the run back to RUNNING with nothing left executing — the run could never progress, complete, or be reported terminal; only cancel worked. This also conflicted with R-LOGIC-00's engine-path rejection semantics (test_inv_b3).
- **EVIDENCE**: `test_http_approval_gate_rejection_marks_run_rejected` failed pre-fix (run left in `running` after rejection via the approvals API).
- **ROOT CAUSE**: the reject branch was written as "release the pause", but no code ever re-entered the loop.
- **AFFECTED FILES / PATH**: `app/agent/runtime/manager.py` (`decide_approval`) ← `POST /api/v1/agent/tasks/{id}/runs/{id}/approvals/{approval_id}`.
- **FIX**: reject → `run.transition_to(REJECTED)` + task REJECTED (guarded by terminal checks); memory message and pending-approval clearing unchanged.
- **REGRESSION TEST**: `test_http_approval_gate_rejection_marks_run_rejected` (HTTP boundary, includes double-decision 409), updated `test_inv_b10_rejection_on_paused_run_terminates_rejected` in the R-LOGIC-00 suite (behavior-change disposition documented in §7).
- **RETEST**: PASS.

### RL01-F-07 — SEVERITY: MEDIUM — TaskStatus had no state machine; task terminal states corruptible
- **EXPECTED**: Task status follows an enforced matrix mirroring the run machine; a terminal task re-opens only via an explicit new attempt (new run start), never mutating history.
- **ACTUAL**: `TaskState.status` was a free enum field. Any writer could set any value (e.g. `manager.cancel_run` would flip a COMPLETED task to CANCELLED when cancelling a fresh, never-started attempt).
- **EVIDENCE**: `test_task_matrix_is_enforced_on_assignment` failed pre-fix.
- **ROOT CAUSE**: enforcement was never designed at task level.
- **AFFECTED FILES / PATH**: `app/agent/state/models.py` (`TaskState`, `TASK_TRANSITIONS`, `TaskStatus.is_terminal`), `app/agent/runtime/manager.py` (`cancel_run`).
- **FIX**: enforced task matrix + terminal→RUNNING re-open edge reserved for new-attempt starts; `cancel_run` mirrors CANCELLED onto the task only when the task is non-terminal (a cancelled never-started attempt leaves a terminal task's history intact). PENDING additionally allows FAILED/REJECTED/CANCELLED (operator decisions before first execution).
- **REGRESSION TEST**: `test_task_matrix_is_enforced_on_assignment`, `test_task_happy_path_sequence_is_accepted`, `test_retry_as_new_run_does_not_corrupt_task_history`, `test_manager_cancel_of_created_run_is_legal_and_terminal`.
- **RETEST**: PASS.

### Observation (no defect, recorded): missing terminal timestamps on two FAILED paths
`engine.py` recovery-terminate and plan-stall FAILED paths did not stamp `completed_at` (direct-assignment drift the machine's `transition_to` would have prevented). Stamped during this task; covered by `test_step_retry_is_bounded_and_terminates_failed` (asserts terminal integrity) and the checkpoint roundtrip test.

### Behavior change disposition (R-LOGIC-00 test updated)
`test_r_logic_00_invariants.py::test_inv_b10_rejection_on_paused_run_resumes_planning_state` pinned the zombie-RUNNING rejection behavior as "accepted". RL01-F-06 supersedes it: the test is renamed to `..._terminates_rejected` and asserts the REJECTED-terminal semantic. Its three sibling fixture updates (inv_a1, inv_b5, inv_e1) only replace illegal fixture shortcuts (CREATED→COMPLETED direct hops) with legal transition chains; the invariants asserted are unchanged.

---

## 5. Tests Executed

**New suite** `backend/tests/test_r_logic_01_state_transitions.py` (24 tests):
- ST-A matrix: completeness/closure, exhaustive allowed-via-`transition_to`, exhaustive forbidden-via-assignment, exhaustive forbidden-via-`transition_to`, named forbidden pairs (both write paths), idempotent self-assignment, checkpoint-roundtrip enforcement, task matrix enforcement, task happy path.
- ST-C race: late-cancellation terminal preservation (real loop/runner, deterministic injection).
- ST-D lifecycle: VERIFYING/REPLANNING traversal, REJECTED-from-VERIFYING, revision ceiling.
- ST-E retry: bounded step retries, bounded agent switches, failed-run-refuses-resume + fresh new run.
- ST-F HTTP: approval rejection → REJECTED + double-decision 409, approval → COMPLETED, cancel during approval wait (terminal, final, no resurrection), cancel of completed run no-op.
- ST-G resume: READY-checkpoint resume completes legally, RUNNING-checkpoint resume completes legally; manager cancel of CREATED run; retry-as-new-run task semantics.

**Pre-fix evidence**: `11 failed, 13 passed` (failures listed per finding above; commands in §6).

**Regression suites re-run (chunked per WSL OOM constraint)**: `test_orchestration_contracts.py`, `test_agent_platform.py`, `test_durable_checkpointing.py`, `test_r_logic_00_invariants.py`, `test_orchestration_planner.py`, `test_agent_registry_and_selector.py`, `test_architecture_invariants.py`, `test_resume_bridge.py`, `test_verifier_invariants.py`, `test_r_func_00_api_behavior.py`, `test_r_func_01_agent_behavior.py`, `test_multi_agent.py`, `test_health.py`, `test_execution_engine_and_adapters.py`, `test_orc_capabilities.py`, `test_endpoints.py`, `test_correlation_propagation.py`, `test_phase07_production_hardening.py`, `test_async_worker.py`, `tests/contract/`, `tests/unit/` — **all green** except `test_agent_platform.py::test_local_safe_sandbox_file_and_commands`, the documented **ENVIRONMENT FAILURE** (sandbox spawns a `python` binary absent in WSL; green in CI per R-LOGIC-00 evidence).

## 6. Exact Commands & Results

```bash
# Pre-fix failure evidence (on main @ 38b2bc2 + new test file only)
backend/.venv/bin/python -m pytest tests/test_r_logic_01_state_transitions.py -q -p no:cacheprovider
#   → 11 failed, 13 passed  (failures = RL01-F-01..07 evidence)

# Post-fix
backend/.venv/bin/python -m pytest tests/test_r_logic_01_state_transitions.py tests/test_r_logic_00_invariants.py \
  tests/test_orchestration_contracts.py tests/test_durable_checkpointing.py -p no:cacheprovider
#   → 68 passed

backend/.venv/bin/python -m pytest tests/test_agent_platform.py tests/test_orchestration_planner.py \
  tests/test_agent_registry_and_selector.py tests/test_architecture_invariants.py tests/test_resume_bridge.py \
  tests/test_verifier_invariants.py tests/test_multi_agent.py tests/test_health.py \
  tests/test_execution_engine_and_adapters.py tests/test_orc_capabilities.py tests/test_endpoints.py \
  tests/test_correlation_propagation.py tests/test_phase07_production_hardening.py tests/test_async_worker.py \
  tests/test_r_func_00_api_behavior.py tests/test_r_func_01_agent_behavior.py \
  tests/contract tests/unit -p no:cacheprovider   # run in chunks
#   → all green; only env-failure: test_local_safe_sandbox_file_and_commands (WSL `python` missing)

# CI-equivalent static checks
backend/.venv/bin/ruff check backend/            # → All checks passed!
backend/.venv/bin/ruff format --check backend/   # → 255 files already formatted
backend/.venv/bin/mypy --config-file backend/mypy.ini backend/app
#   → Success: no issues found in 166 source files
```

## 7. Security & Business Impact

- **Security**: approval bypass was already structurally blocked (R-LOGIC-00); this task closes the *state-level* bypasses (WAITING/PAUSED→COMPLETED writes now rejected) and the zombie-RUNNING rejection state that could hide an unapproved dangerous action behind a run that looks active. Terminal immutability is now enforced at the model layer for every writer, including future ones.
- **Business**: eliminates silent terminal-state corruption (COMPLETED→CANCELLED by late cancellation), unbounded agent-switch provider spend, and unobservable verification lifecycle; makes audit trails (completed_at, terminal reasons) consistent.

## 8. CI Status

Pushed as `chore/r-logic-01-state-transitions` → PR to `main`. Local CI-equivalent checks (ruff check, ruff format, mypy, chunked pytest of all affected suites) are green. GitHub CI run recorded below after push.

## 9. Remaining Issues & Risks

1. **VERIFYING/REPLANNING are transient** in the canonical engine (no checkpoint captured *during* those phases because verification/replanning are synchronous); a crash inside them rolls back to the last EXECUTING checkpoint. Acceptable; noted for R-ARCH-02 (multi-worker durability).
2. **Task-level `terminal→RUNNING` re-open is by-design** (retry = new bounded attempt; the run remains the immutable unit). Reviewers should confirm this semantic is intended product behavior.
3. **`engine.resume_run` has no HTTP route** (the internal coding resume bridge goes through LangGraph/ADR-001, R-LOGIC-04 scope); resume normalization is therefore verified at service boundary only.
4. **WSL environment**: full-suite coverage gate cannot run locally (OOM); CI enforces the 85% floor plus patch-coverage gate. The sandbox test is an environment failure locally.
5. `WorkflowEngine` (workflows subsystem) has its own minimal status flow with no production callers — flagged for R-ARCH review if it ever gains an entry point.

## 10. Manual Test Instructions for the Human Reviewer

```bash
cd backend
uv run uvicorn app.main:app --host 0.0.0.0 --port 8000 --reload
# (JWT for your tenant; see tests/test_r_logic_01_state_transitions.py::make_agent_jwt for the claim shape)

# 1. Create a task and a run that requests a dangerous tool (sync execution pauses):
curl -s -X POST http://localhost:8000/api/v1/agent/tasks \
  -H "Authorization: Bearer $JWT" -H "Content-Type: application/json" \
  -d '{"goal": "run a shell command"}'
# → {"task_id": "..."}
curl -s -X POST http://localhost:8000/api/v1/agent/tasks/$TASK_ID/runs \
  -H "Authorization: Bearer $JWT" -H "Content-Type: application/json" \
  -d '{"async_execution": false}'
# → status "paused_approval" (approval_required event on the SSE stream)

# 2. REJECT the approval:
curl -s -X POST http://localhost:8000/api/v1/agent/tasks/$TASK_ID/runs/$RUN_ID/approvals/$APPROVAL_ID \
  -H "Authorization: Bearer $JWT" -H "Content-Type: application/json" \
  -d '{"approved": false, "reason": "not authorized"}'
# EXPECTED: approval status "rejected" AND the run now shows "rejected" (terminal), not "running".

# 3. Cancel semantics:
#   - Cancel the paused run in another session → run becomes "cancelled" and stays cancelled
#     even if a late approval decision arrives afterwards.
#   - Cancel a run that already completed → response returns the run still "completed".
# 4. GET /api/v1/agent/tasks/{id}/runs/{id} after each step to observe the terminal record
#    (status + completed_at set).
```
