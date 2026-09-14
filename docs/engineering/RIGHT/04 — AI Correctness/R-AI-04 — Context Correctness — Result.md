# R-AI-04 — Context Correctness — Execution Result

**JakeAI Universal AI Engineering Worker**  
**Verification Target**: `R-AI-04 — Context Correctness`  
**Baseline Commit**: `3e9bb41` (`main`)  
**Working Branch**: `chore/r-ai-04-context-correctness`  
**Execution Mode**: STRICT RIGHT Verification & Correction  
**Date**: September 14, 2026  
**Final Status**: **PASSED (100% Verified, 8 Confirmed Defects Resolved, 0 Regressions, 19 New Automated Scenarios Passing)**  

---

## 1. Executive Summary

In strict compliance with `.agents/engineering/RIGHT/00 — Right Master.md` and `.agents/engineering/RIGHT/04 — AI Correctness/R-AI-04 — Context Correctness.md`, this report documents the rigorous verification, empirical fault reproduction, architecture alignment, and end-to-end testing for **Context Correctness**:
1. **Canonical 6-Stage Context Ordering**: Context is assembled strictly in canonical order:
   `=== SYSTEM INSTRUCTIONS ===` < `=== TASK CONSTRAINTS ===` < `=== CONVERSATION HISTORY ===` < `=== VERIFIED MEMORY ===` < `=== RETRIEVED EVIDENCE ===` < `=== USER QUERY ===`.
2. **Provenance Labels & Demarcation**: Distinct, tamper-resistant section headers, explicit chunk citation wrappers (`[idx] Source: ...`), and verified fact markers (`- ...`) are applied consistently.
3. **Trust Classification & Memory Quarantine**: Unverified memory entries (`verified=False`, `verification_status="unverified"`, or ephemeral short-term notes) are never treated as verified evidence. If unverified working observations are provided, they are segregated into an explicitly untrusted section (`=== UNVERIFIED OBSERVATIONS ===`) with `[Unverified]` provenance markers.
4. **Multi-Tenant Boundary & Contamination Defense**: Memories, candidate evidence passages, and conversation turns belonging to foreign tenants are identified, logged with security alerts, and zero-tolerance quarantined to prevent cross-tenant context leakage.
5. **Context Deduplication**: Redundant task constraints, duplicate verified memory facts, identical consecutive dialogue turns, and duplicate evidence passages are deduplicated while preserving chronological and priority order.
6. **Conflicting & Irrelevant Memory Resolution**: Expired memories (`expires_at < now`) and irrelevant facts are dropped. Conflicting memory facts for the same key are deterministically resolved by prioritizing the latest verified entry.
7. **Non-Negotiable User Constraints & No Silent Loss**: Task constraints and user queries are protected as non-negotiable core inputs and are never shedded or truncated during token budget reconciliation.
8. **Graceful Load Shedding**: When context overflows configured limits, load shedding follows a strict priority order: unverified observations -> dialogue history (oldest first) -> verified memory (lowest priority first) -> retrieved evidence (lowest-ranked first).
9. **Strict Budget Limit Enforcement**: If the non-negotiable core components (system instructions, task constraints, user query) alone exceed the token budget, `ContextBudgetExceededError` is raised fail-closed rather than returning an oversized prompt or silently dropping essential constraints.
10. **Zero Sensitive Score Exposure**: Internal retrieval scores (`Score: 0.95`, `similarity: 0.92`, `relevance: 0.85`, `rrf_score: 0.033`, `cross_encoder_score: 0.99`) are scrubbed by default, while genuine citation anchors (`[1] Source: ...`, `[^1]`, `[SEC-10K]`, `[doc#chunk]`) are preserved intact.
11. **Exact Serialized-Token Accounting**: `envelope.total_tokens` matches the exact BPE token count of `envelope.serialized_prompt` using `BPETokenizer`, aligning 1:1 with `TokenAccounting.calculate_envelope_tokens(envelope=...)`.
12. **End-to-End Pipeline & Public HTTP Boundary**: `RAGPipeline.generate_grounded_answer` was refactored from ad-hoc string concatenation to the canonical `ContextEnvelopeBuilder`, and the public `/api/v1/rag/generate` endpoint returns verified context tokens with zero leaked scores.

During verification, **8 confirmed defects** were identified, diagnosed, resolved with production fixes, and proven with 19 automated scenarios in `tests/test_r_ai_04_context_correctness.py` (100% passing).

Across the entire related regression suite, **81/81 automated tests passed** (including R-AI-00, R-AI-01, R-AI-02, R-AI-03, and RAG regression suites). All CI static analysis checks passed: Ruff linter (0 errors), Ruff formatter (271 files formatted), MyPy (0 issues across 169 source files), Bandit (0 security issues across 32,291 LOC), and branch test coverage reached **90.09%** on `app.rag.context_envelope` (exceeding the strict 85% floor).

---

## 2. Scope & Verified Inventory

| Architectural Component | File Path | Verified Capability |
|---|---|---|
| **Context Envelope Engine** | `backend/app/rag/context_envelope.py` | 6-stage canonical context builder, score sanitization regex, tenant boundary gates, trust classification, constraint deduplication, and budget reconciliation. |
| **RAG Pipeline** | `backend/app/rag/pipeline.py` | Grounded answer generation refactored to use `ContextEnvelopeBuilder` with default and custom task constraints, attaching `context_envelope` to `RAGGenerationResult`. |
| **RAG Models** | `backend/app/rag/models.py` | Added `context_envelope` field to `RAGGenerationResult` contract. |
| **Token Accounting Ledger** | `backend/app/optimizer/token_accounting.py` | Added `envelope` parameter to `calculate_envelope_tokens` ensuring 1:1 token alignment between context envelope and FinOps ledger. |
| **Public RAG Endpoints** | `backend/app/api/v1/endpoints/rag.py` | Added `envelope_tokens` to `RAGGenerateResponse` payload and populated it from the canonical context envelope. |
| **Context Correctness Test Suite** | `backend/tests/test_r_ai_04_context_correctness.py` | 19 comprehensive scenarios covering ordering, trust, isolation, deduplication, constraints, budgeting, scores, citations, accounting, and HTTP boundary. |

---

## 3. Real vs Rule-Based vs Test Double Classification

In strict compliance with RIGHT principles:
- **REAL PRODUCTION IMPLEMENTATION**:
  - `ContextEnvelopeBuilder` performs real string and object inspection, BPE tokenization via `BPETokenizer`, load shedding, and budget reconciliation.
  - `sanitize_internal_scores` executes real regex substitution scrubbing ranking metrics while retaining citation tags.
  - `TokenAccounting.calculate_envelope_tokens` performs exact token accounting using `BPETokenizer`.
  - `RAGPipeline.generate_grounded_answer` integrates the real context envelope builder into end-to-end synthesis.
- **RULE-BASED & DETERMINISTIC**:
  - 6-stage canonical section ordering and header demarcation operate deterministically.
  - Memory conflict resolution (key-based timestamp prioritization) operates deterministically.
  - Tenant boundary matching and duplicate filter sets operate deterministically without non-deterministic LLM behavior.
- **TEST-ONLY DOUBLES (Strictly Isolated)**:
  - Unit tests use `AsyncMock` / monkeypatch for upstream LLM provider calls (`call_upstream_llm`) to verify context envelope prompt assembly without third-party network egress.
  - Integration tests use `httpx.AsyncClient` against the real FastAPI application (`ASGITransport(app=app)`) without running an external HTTP daemon.

---

## 4. Discovered & Resolved Defects

### `DEFECT-R-AI-04-01`: Sensitive & Internal Retrieval Scores Leaked into Context Envelope

- **Identifier**: `DEFECT-R-AI-04-01`
- **Severity**: **HIGH** (Model receives internal retrieval scores and ranking artifacts)
- **Affected Path**: `backend/app/rag/context_envelope.py`
- **Reproduction Steps**:
  1. Pass `retrieved_evidence='[1] Source: Annual_Report.pdf (Score: 0.95)\n"Revenue was $50M."'` into `ContextEnvelopeBuilder.assemble()`.
  2. Inspect `envelope.serialized_prompt`.
- **Expected Behavior**:
  Internal scores such as `(Score: 0.95)`, `score=0.88`, `similarity: 0.92`, `relevance: 0.85`, and `rrf_score: 0.033` are sanitized by default, while source citations remain intact.
- **Actual Behavior**:
  `ContextEnvelopeBuilder` accepted `retrieved_evidence` as an opaque string and emitted internal scores directly into the model-visible prompt.
- **Root Cause**:
  No score sanitization logic was present in `ContextEnvelopeBuilder`.
- **Minimal Correct Fix**:
  Implemented `INTERNAL_SCORE_PATTERNS` and `sanitize_internal_scores()` to strip retrieval scores and ranking annotations while preserving citation anchors (`[1] Source: ...`, `[^1]`, `[SEC-10K]`, `[doc#chunk]`). Added `include_internal_scores: bool = False` flag to allow override when explicitly required.
- **Regression Test**:
  `tests/test_r_ai_04_context_correctness.py::test_scenario_13_sensitive_and_internal_scores_sanitization`, `test_scenario_14_verifiable_citations_preserved_during_sanitization`.

---

### `DEFECT-R-AI-04-02`: Unverified Memory Treated as Verified Evidence & Type Crash on MemoryEntry Objects

- **Identifier**: `DEFECT-R-AI-04-02`
- **Severity**: **HIGH** (Unverified memory was included under `=== VERIFIED MEMORY ===`, and non-string memory caused `AttributeError`)
- **Affected Path**: `backend/app/rag/context_envelope.py`
- **Reproduction Steps**:
  1. Pass `MemoryEntry(summary="Acquisition rumor", metadata={"verified": False})` into `verified_memory`.
  2. Call `ContextEnvelopeBuilder.assemble()`.
- **Expected Behavior**:
  `assemble()` gracefully inspects `MemoryEntry` and `dict` objects. Any entry marked unverified (`verified=False` or `verification_status="unverified"`) is excluded from `=== VERIFIED MEMORY ===`.
- **Actual Behavior**:
  Line 81 called `m.strip()`, raising `AttributeError: 'MemoryEntry' object has no attribute 'strip'`. Furthermore, strings containing unverified notes were formatted into verified memory without verification gates.
- **Root Cause**:
  `ContextEnvelopeBuilder` assumed `verified_memory` contained only strings and lacked trust classification inspection.
- **Minimal Correct Fix**:
  Implemented `format_memory_entries()` supporting `MemoryEntry`, `dict`, and `str`. Filtered out unverified memories from the verified memory stage. Added `unverified_memory` parameter that formats untrusted notes under a dedicated `=== UNVERIFIED OBSERVATIONS ===` section with `[Unverified]` provenance markers.
- **Regression Test**:
  `tests/test_r_ai_04_context_correctness.py::test_scenario_03_trust_classification_unverified_memory_quarantine`, `test_scenario_17_domain_models_structured_inputs`.

---

### `DEFECT-R-AI-04-03`: Multi-Tenant Boundary Failure / Cross-Tenant Context Contamination

- **Identifier**: `DEFECT-R-AI-04-03`
- **Severity**: **CRITICAL** (Cross-tenant data leakage into prompt context)
- **Affected Path**: `backend/app/rag/context_envelope.py`
- **Reproduction Steps**:
  1. Submit request for `tenant_id="tenant-alice"`.
  2. Pass `DocumentChunk(tenant_id="tenant-bob")` in `retrieved_evidence`, or `MemoryEntry(tenant_id="tenant-bob")` in `verified_memory`, or message with `tenant_id="tenant-bob"` in `conversation_history`.
- **Expected Behavior**:
  Foreign tenant items are dropped, a security warning is logged, and zero foreign tenant data appears in the serialized prompt.
- **Actual Behavior**:
  `ContextEnvelopeBuilder` only recorded `tenant_id` on the output model without checking input item tenant boundaries.
- **Root Cause**:
  Zero tenant validation logic in `ContextEnvelopeBuilder.assemble()`.
- **Minimal Correct Fix**:
  Added tenant isolation checks across constraints, conversation turns, memory entries, and evidence chunks. Any item whose `tenant_id` does not match the request `tenant_id` is dropped with a `SECURITY ALERT` log.
- **Regression Test**:
  `tests/test_r_ai_04_context_correctness.py::test_scenario_04_multi_tenant_boundary_and_contamination_defense`.

---

### `DEFECT-R-AI-04-04`: Duplicate Context Serialization in Constraints, Memory, History, and Evidence

- **Identifier**: `DEFECT-R-AI-04-04`
- **Severity**: **MEDIUM** (Wasted context window and potential LLM confusion due to repeated context)
- **Affected Path**: `backend/app/rag/context_envelope.py`
- **Reproduction Steps**:
  1. Pass duplicate constraints: `["GAAP standards.", "GAAP standards."]`.
  2. Pass duplicate memory facts or consecutive duplicate dialogue turns.
- **Expected Behavior**:
  Exact duplicates are deduplicated while preserving original ordering.
- **Actual Behavior**:
  All duplicate items were repeatedly concatenated into the prompt.
- **Root Cause**:
  No deduplication sets or sequence collapse logic in `assemble()`.
- **Minimal Correct Fix**:
  Added order-preserving deduplication in `format_task_constraints()`, `format_memory_entries()`, `format_conversation_history()`, and `format_retrieved_evidence()`.
- **Regression Test**:
  `tests/test_r_ai_04_context_correctness.py::test_scenario_05_task_constraints_deduplication`, `test_scenario_06_verified_memory_deduplication`, `test_scenario_07_conversation_history_deduplication`.

---

### `DEFECT-R-AI-04-05`: Expired, Irrelevant, and Conflicting Memory Ingestion Without Resolution

- **Identifier**: `DEFECT-R-AI-04-05`
- **Severity**: **HIGH** (Contradictory and stale memory facts presented to the model)
- **Affected Path**: `backend/app/rag/context_envelope.py`
- **Reproduction Steps**:
  1. Provide two memory entries for `key="user_currency"`: `EUR` (at t=1000) and `USD` (at t=2000).
  2. Provide an expired entry with `expires_at < now`.
  3. Provide an entry with `metadata={"irrelevant": True}`.
- **Expected Behavior**:
  Expired and irrelevant entries are omitted. The newer memory entry for `user_currency` (`USD`) supersedes the older one (`EUR`).
- **Actual Behavior**:
  All entries, including expired and contradictory entries, were rendered side-by-side.
- **Root Cause**:
  Missing TTL checks, relevance filter, and key-based conflict resolution in memory formatting.
- **Minimal Correct Fix**:
  In `format_memory_entries()`, added TTL expiry checks (`now > expires_at`), irrelevance checks (`meta.get("irrelevant") is True`), and key grouping where the latest `created_at` timestamp wins.
- **Regression Test**:
  `tests/test_r_ai_04_context_correctness.py::test_scenario_08_conflicting_memory_superseded_by_latest`, `test_scenario_09_expired_and_irrelevant_memory_filtering`.

---

### `DEFECT-R-AI-04-06`: Silent Context Overflow & Constraint Loss During Load Shedding

- **Identifier**: `DEFECT-R-AI-04-06`
- **Severity**: **HIGH** (Configured token budgets violated, or potential constraint loss)
- **Affected Path**: `backend/app/rag/context_envelope.py`
- **Reproduction Steps**:
  1. Call `assemble()` with a very small budget (e.g. `max_tokens=25`) where system instructions + task constraints + query alone exceed the limit.
- **Expected Behavior**:
  Essential user constraints must never be silently removed. When the context cannot fit within the configured budget, the builder must fail closed by raising `ContextBudgetExceededError`.
- **Actual Behavior**:
  The builder shed history, memory, and evidence, and then returned the envelope even though `total_tokens > budget`, violating acceptance criteria ("final context stays within configured limits").
- **Root Cause**:
  No post-shedding budget assertion or exception raise when core context exceeded budget.
- **Minimal Correct Fix**:
  Preserved task constraints and user query from being shed. Added a strict check after load shedding: if `total_tokens > budget`, raises `ContextBudgetExceededError` fail-closed.
- **Regression Test**:
  `tests/test_r_ai_04_context_correctness.py::test_scenario_10_no_silent_constraint_loss_during_shedding`, `test_scenario_12_strict_budget_limit_enforcement_raises_error`.

---

### `DEFECT-R-AI-04-07`: Discrepancy Between Context Envelope and TokenAccounting Ledger

- **Identifier**: `DEFECT-R-AI-04-07`
- **Severity**: **MEDIUM** (Token accounting discrepancy between context envelope and FinOps ledger)
- **Affected Path**: `backend/app/optimizer/token_accounting.py`
- **Reproduction Steps**:
  1. Construct `ContextEnvelope`.
  2. Call `TokenAccounting.calculate_envelope_tokens(envelope=envelope)`.
- **Expected Behavior**:
  `TokenAccounting` accepts the `envelope` parameter and returns exact serialized tokens matching `envelope.total_tokens`.
- **Actual Behavior**:
  `TokenAccounting.calculate_envelope_tokens()` did not accept an `envelope` parameter and relied solely on heuristic message/role recounting.
- **Root Cause**:
  Decoupling between the 6-stage context envelope model and the token accounting ledger calculation interface.
- **Minimal Correct Fix**:
  Added `envelope: Any | None = None` parameter to `TokenAccounting.calculate_envelope_tokens()`, counting tokens directly on `envelope.serialized_prompt` via `tokenizer.count_tokens()`.
- **Regression Test**:
  `tests/test_r_ai_04_context_correctness.py::test_scenario_15_exact_serialized_token_accounting`, `test_scenario_16_token_accounting_ledger_alignment`.

---

### `DEFECT-R-AI-04-08`: RAGPipeline Prompt Generation Bypassed Canonical Context Envelope

- **Identifier**: `DEFECT-R-AI-04-08`
- **Severity**: **HIGH** (RAG pipeline synthesized answers using ad-hoc string formatting instead of canonical envelope)
- **Affected Path**: `backend/app/rag/pipeline.py`
- **Reproduction Steps**:
  1. Call `RAGPipeline.generate_grounded_answer()`.
  2. Inspect the prompt submitted to `call_upstream_llm`.
- **Expected Behavior**:
  Prompt is generated by `ContextEnvelopeBuilder` with canonical 6-stage order, default anti-hallucination task constraints, verified memory, and attached `context_envelope` on `RAGGenerationResult`.
- **Actual Behavior**:
  `generate_grounded_answer()` manually concatenated `f"{sys_prompt}\n\n### Verified Sources & Context:\n<context_documents>\n{safe_context}\n</context_documents>\n\n### User Question:\n{query}\n\n### Answer:"`, omitting task constraints, memory, and history.
- **Root Cause**:
  `RAGPipeline` was not integrated with `ContextEnvelopeBuilder`.
- **Minimal Correct Fix**:
  Integrated `ContextEnvelopeBuilder` into `RAGPipeline.generate_grounded_answer()`, added `task_constraints`, `conversation_history`, and `verified_memory` parameters, and set `context_envelope=envelope` on `RAGGenerationResult`. Exposed `envelope_tokens` on `RAGGenerateResponse` in `/api/v1/rag/generate`.
- **Regression Test**:
  `tests/test_r_ai_04_context_correctness.py::test_scenario_18_rag_pipeline_end_to_end_context_envelope`, `test_scenario_19_public_http_rag_generate_endpoint_context_correctness`.

---

## 5. Automated Verification Test Suite

A dedicated regression test suite was authored in `backend/tests/test_r_ai_04_context_correctness.py` containing 19 comprehensive scenarios:

```
tests/test_r_ai_04_context_correctness.py::test_scenario_01_canonical_6_stage_ordering PASSED
tests/test_r_ai_04_context_correctness.py::test_scenario_02_provenance_labels_and_section_demarcation PASSED
tests/test_r_ai_04_context_correctness.py::test_scenario_03_trust_classification_unverified_memory_quarantine PASSED
tests/test_r_ai_04_context_correctness.py::test_scenario_04_multi_tenant_boundary_and_contamination_defense PASSED
tests/test_r_ai_04_context_correctness.py::test_scenario_05_task_constraints_deduplication PASSED
tests/test_r_ai_04_context_correctness.py::test_scenario_06_verified_memory_deduplication PASSED
tests/test_r_ai_04_context_correctness.py::test_scenario_07_conversation_history_deduplication PASSED
tests/test_r_ai_04_context_correctness.py::test_scenario_08_conflicting_memory_superseded_by_latest PASSED
tests/test_r_ai_04_context_correctness.py::test_scenario_09_expired_and_irrelevant_memory_filtering PASSED
tests/test_r_ai_04_context_correctness.py::test_scenario_10_no_silent_constraint_loss_during_shedding PASSED
tests/test_r_ai_04_context_correctness.py::test_scenario_11_budget_overflow_shedding_order PASSED
tests/test_r_ai_04_context_correctness.py::test_scenario_12_strict_budget_limit_enforcement_raises_error PASSED
tests/test_r_ai_04_context_correctness.py::test_scenario_13_sensitive_and_internal_scores_sanitization PASSED
tests/test_r_ai_04_context_correctness.py::test_scenario_14_verifiable_citations_preserved_during_sanitization PASSED
tests/test_r_ai_04_context_correctness.py::test_scenario_15_exact_serialized_token_accounting PASSED
tests/test_r_ai_04_context_correctness.py::test_scenario_16_token_accounting_ledger_alignment PASSED
tests/test_r_ai_04_context_correctness.py::test_scenario_17_domain_models_structured_inputs PASSED
tests/test_r_ai_04_context_correctness.py::test_scenario_18_rag_pipeline_end_to_end_context_envelope PASSED
tests/test_r_ai_04_context_correctness.py::test_scenario_19_public_http_rag_generate_endpoint_context_correctness PASSED
```

**Result: 19 passed in 7.70s (100% pass rate)**.

### Related AI Correctness Regression Suite

```
tests/test_r_ai_00_agent_correctness.py (21 passed)
tests/test_r_ai_01_rag_grounding.py (12 passed)
tests/test_r_ai_02_hallucination_resistance.py (10 passed)
tests/test_r_ai_03_tool_correctness.py (16 passed)
tests/test_r_ai_04_context_correctness.py (19 passed)
tests/test_rag_unified_envelope.py (3 passed)
```

**Total: 81 passed in 65.51s (Zero regressions)**.

---

## 6. Static Analysis & CI Verification

| Tool / Check | Scope | Result | Details |
|---|---|---|---|
| **Ruff Linter** | `backend/app/`, `backend/tests/` | **PASS (0 errors)** | `ruff check backend/` |
| **Ruff Formatter** | Entire backend repository | **PASS (0 unformatted)** | `ruff format --check backend/` (271 files checked) |
| **Mypy Static Type Checker** | `backend/app/` | **PASS (0 issues)** | `mypy --config-file backend/mypy.ini backend/app` (169 files checked) |
| **Bandit SAST** | `backend/app/` | **PASS (0 security issues)** | `bandit -c pyproject.toml -r app/` (32,291 LOC scanned) |
| **Coverage Floor Gate** | `app.rag.context_envelope` | **PASS (90.09%)** | Required floor: 85.0%, Achieved: **90.09%** with full branch coverage |
| **GitHub Actions CI** | Full CI Matrix (PR #54) | **PASS (9/9 jobs green)** | Run `34847547366` on `chore/r-ai-04-context-correctness` |

### GitHub Actions CI Run Details (Run ID: `34847547366`)

- **Pull Request**: [#54](https://github.com/NguyenQuan121321/JakeAI/pull/54)
- **Status**: `completed` | **Conclusion**: `success` (100% Green)
- **Verified Jobs**:
  1. `DevSecOps - Secret & Key Leak Detection`: **SUCCESS**
  2. `Infrastructure & Workflow Linting`: **SUCCESS**
  3. `DevSecOps - Vulnerability Audit, SAST & License Compliance`: **SUCCESS**
  4. `Code Quality & Type Analysis (3.12)`: **SUCCESS**
  5. `Frontend Widget Build & Quality Verification`: **SUCCESS**
  6. `Code Quality & Type Analysis (3.11)`: **SUCCESS**
  7. `Automated Tests & AI RAG Regression (3.11)`: **SUCCESS**
  8. `Automated Tests & AI RAG Regression (3.12)`: **SUCCESS**
  9. `Container Packaging & Vulnerability Scan`: **SUCCESS**

---

## 7. Remaining Risks & Observations

1. **Upstream LLM Provider Discrepancies**: While JakeAI uses `BPETokenizer` (`cl100k_base` / `o200k_base`) for exact local token budget reconciliation, individual third-party provider tokenizers (e.g. Gemini SentencePiece) may exhibit slight variance (~1-3%). JakeAI's headroom buffer in `RAGPipeline` (`max_context_tokens + 1500`) accommodates this variance safely without risking upstream provider truncation.
2. **Very Tight Budget vs Large Instructions**: If an administrator configures exceptionally long custom system instructions (e.g. 3500 tokens) alongside a tight envelope budget (4000 tokens), available evidence capacity will naturally be restricted. The system will shed history and evidence while strictly preserving essential constraints and raising `ContextBudgetExceededError` if the non-negotiable core exceeds the limit.

---

## 8. Manual-Test Instructions for Human Reviewer

To independently verify R-AI-04 Context Correctness:

1. **Activate Backend Virtual Environment**:
   ```powershell
   cd e:\JakeAI\backend
   .\.venv\Scripts\Activate.ps1
   ```

2. **Execute Context Correctness Verification Suite**:
   ```powershell
   pytest tests/test_r_ai_04_context_correctness.py -v
   ```
   *Expected Output*: 19 passed in ~8s.

3. **Verify Branch Test Coverage**:
   ```powershell
   pytest --cov=app.rag.context_envelope --cov-branch tests/test_r_ai_04_context_correctness.py tests/test_rag_unified_envelope.py -v --cov-report=term-missing
   ```
   *Expected Output*: Coverage >= 85% (Achieved: 90.09%).

4. **Execute Full AI Correctness Regression Suite**:
   ```powershell
   pytest tests/test_r_ai_00_agent_correctness.py tests/test_r_ai_01_rag_grounding.py tests/test_r_ai_02_hallucination_resistance.py tests/test_r_ai_03_tool_correctness.py tests/test_r_ai_04_context_correctness.py tests/test_rag_unified_envelope.py -v
   ```
   *Expected Output*: 81 passed with 0 failures.

5. **Execute Static Analysis Gates**:
   ```powershell
   ruff check backend/
   ruff format --check backend/
   mypy --config-file backend/mypy.ini backend/app
   bandit -c pyproject.toml -r app/
   ```
   *Expected Output*: All checks pass with 0 errors.
