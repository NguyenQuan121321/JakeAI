# TESTING-INVENTORY — Automated Test System Audit & Technical Inventory
**Audit Phase**: `TEST-01` (Deduplication & Reorganization Completed) | **System**: JakeAI Universal AI Engineering Worker
**Audit Baseline**: Commit `431818a` (`main`, tag `v0.48.0`) | **Branch**: `chore/test-01-deduplication-reorganization`
**Status**: TEST-01 REORGANIZATION & DEDUPLICATION EXECUTED & GREEN (93 Active Test Files, 1,101 Tests Passing)
**Reference Documents**: `00 — Right Master.md`, `RIGHT-00 — System Inventory.md`, 20 RIGHT Result Docs, OpenAPI 3.1.0, GitHub CI Workflows (`ci.yml`, `cd.yml`, `ai-benchmark-scheduled.yml`), Bruno HTTP Collections (`Bruno/`).

---

## Executive Summary
In accordance with `TEST-00`, this document establishes the definitive, empirical truth regarding the CURRENT automated test system in JakeAI prior to any restructuring, deduplication, or test reorganization.
- **Zero Code Modifications**: Production code, test implementations, CI workflows, and Bruno collections remain untouched during this audit.
- **Total Discovered Test Files**: **95 files** (94 test files + `conftest.py`; plus 2 `__init__.py` files = 97 Python files total in `backend/tests/`).
- **Total Discovered Test Functions**: **1,033 unique test functions / methods** in the AST.
- **Total Pytest Collected Test Items**: **1,105 test items** (accounting for parameterized scenario expansions).
- **Test Suite Baseline Comparison**: Increased from 732 tests at the `RIGHT-00` discovery baseline to 1,105 items following the implementation of the 20 canonical RIGHT verification suites (adding 401 targeted verification & regression tests).

---

## 1. Current Directory Structure
The current `backend/tests/` hierarchy is largely flat at the root with three isolated subdirectories (`contract/`, `evals/`, `unit/`):
```
backend/tests/
├── __init__.py                                (Package marker)
├── conftest.py                                (Shared ASGI AsyncClient fixture)
├── contract/                                  (2 files, 10 tests)
│   ├── test_api_contract.py                   (OpenAPI schema & route integrity)
│   └── test_internal_mutual_auth.py           (Perimeter auth & internal header validation)
├── evals/                                     (13 files, 65 tests, 2 golden datasets)
│   ├── __init__.py
│   ├── datasets/
│   │   └── workloads_dataset_v1.json          (Multi-workload token optimization dataset)
│   ├── golden_dataset.json                    (Curated RAG ground-truth benchmark)
│   ├── test_baseline_and_regression_gate.py   (Eval regression gate)
│   ├── test_canary_leakage.py                 (Safety & prompt canary detection)
│   ├── test_coding_intelligence_regression.py (Coding AST & code quality evals)
│   ├── test_llm_judge_and_generation.py       (LLM judge evaluator tests)
│   ├── test_phase03_token_optimization.py     (Empirical 100-request token benchmark)
│   ├── test_phase06_evaluation.py             (End-to-end evaluation runner)
│   ├── test_portfolio_benchmark.py            (8-workload multi-tier evaluation)
│   ├── test_prompt_cache_benchmark.py         (Static/dynamic prompt prefix benchmark)
│   ├── test_rag_context_efficiency.py         (ContextSelector token reduction eval)
│   ├── test_rag_eval.py                       (Golden dataset RAG evaluation)
│   ├── test_rag_metrics.py                    (RAG retrieval & groundedness metrics)
│   ├── test_rag_regression.py                 (Dedicated RAG regression gate)
│   └── test_token_benchmark.py                (Token savings gate)
├── unit/                                      (7 files, 193 tests)
│   ├── test_bpe_tokenizer.py                  (Tiktoken BPE tokenizer unit tests)
│   ├── test_cache_identity.py                 (Cache key hashing & normalization unit tests)
│   ├── test_canonical_provider_resolution.py  (BYOK credential resolution unit tests)
│   ├── test_canonical_token_accounting.py     (FinOps token ledger unit tests)
│   ├── test_direct_provider.py                (Direct LLM client dispatch unit tests)
│   ├── test_state_bridges.py                  (RunState / AgentState bridge converters)
│   └── test_structured_conversation_contract.py (Conversation envelope unit tests)
└── [Root Level Test Files]                     (72 test files, 765 tests)
    ├── test_r_func_00_api_behavior.py ... test_r_func_04_provider_behavior.py (5 RIGHT Func suites)
    ├── test_r_logic_00_invariants.py ... test_r_logic_04_failure_handling.py  (5 RIGHT Logic suites)
    ├── test_r_arch_00_architecture_integrity.py ... test_r_arch_04_...        (5 RIGHT Arch suites)
    ├── test_r_ai_00_agent_correctness.py ... test_r_ai_04_context_correctness (5 RIGHT AI suites)
    └── 52 pre-existing subsystem test files (Agent, RAG, Cache, FinOps, BYOK, Guardrails, DevOps)
```

---

## 2. Total Test Files
- **Total Test Files**: **94 executable test files**
- **Fixture Files**: **1 file** (`conftest.py`)
- **Package Initialization Files**: **2 files** (`backend/tests/__init__.py`, `backend/tests/evals/__init__.py`)
- **Evaluation Datasets**: **2 files** (`evals/golden_dataset.json`, `evals/datasets/workloads_dataset_v1.json`)
- **Total Tracked Files in `backend/tests/`**: **99 files**

---

## 3. Total Discovered Test Functions
- **AST Parsed Test Functions / Methods**: **1,033 unique test functions**
- **Pytest Collected Test Items**: **1,105 test items**
- **Average Tests per File**: ~11.0 tests/file
- **Largest Test Files by Function Count**:
  1. [`tests/test_r_func_03_cache_behavior.py`](file:///e:/JakeAI/backend/tests/test_r_func_03_cache_behavior.py): 45 tests (50,751 bytes)
  2. [`tests/test_r_func_00_api_behavior.py`](file:///e:/JakeAI/backend/tests/test_r_func_00_api_behavior.py): 39 tests (40,880 bytes)
  3. [`tests/test_r_logic_04_failure_handling.py`](file:///e:/JakeAI/backend/tests/test_r_logic_04_failure_handling.py): 38 tests (38,574 bytes)
  4. [`tests/unit/test_cache_identity.py`](file:///e:/JakeAI/backend/tests/unit/test_cache_identity.py): 34 tests (31,316 bytes)
  5. [`tests/test_r_logic_00_invariants.py`](file:///e:/JakeAI/backend/tests/test_r_logic_00_invariants.py): 30 tests (57,609 bytes)
  6. [`tests/unit/test_structured_conversation_contract.py`](file:///e:/JakeAI/backend/tests/unit/test_structured_conversation_contract.py): 28 tests (30,122 bytes)
  7. [`tests/test_r_func_04_provider_behavior.py`](file:///e:/JakeAI/backend/tests/test_r_func_04_provider_behavior.py): 22 tests (24,800 bytes)
  8. [`tests/test_finops_accounting.py`](file:///e:/JakeAI/backend/tests/test_finops_accounting.py): 21 tests (22,385 bytes)
  9. [`tests/test_gateway.py`](file:///e:/JakeAI/backend/tests/test_gateway.py): 23 tests (20,285 bytes)
  10. [`tests/test_r_logic_03_accounting.py`](file:///e:/JakeAI/backend/tests/test_r_logic_03_accounting.py): 23 tests (29,961 bytes)

---

## 4. Test Distribution by Category
### 4.1 Distribution by Functional Subsystem
| Subsystem | Files | Test Count | % of Suite | Key Production Components Tested |
|---|---|---|---|---|
| **Core / Platform** | 25 | 278 | 29.4% | Covered in catalog |
| **RAG Pipeline** | 31 | 278 | 29.4% | Covered in catalog |
| **Agent Orchestration** | 9 | 94 | 9.9% | Covered in catalog |
| **FinOps & Billing** | 4 | 63 | 6.7% | Covered in catalog |
| **Token Optimization & Caching** | 5 | 53 | 5.6% | Covered in catalog |
| **Contract & Schema** | 3 | 47 | 5.0% | Covered in catalog |
| **Gateway & Routing** | 4 | 44 | 4.7% | Covered in catalog |
| **AI Evaluation & Benchmarking** | 7 | 43 | 4.6% | Covered in catalog |
| **BYOK Security** | 1 | 16 | 1.7% | Covered in catalog |
| **Security & Governance** | 3 | 14 | 1.5% | Covered in catalog |
| **DevOps Bot** | 1 | 5 | 0.5% | Covered in catalog |
| **Health & Diagnostics** | 1 | 5 | 0.5% | Covered in catalog |
| **Observability & Telemetry** | 1 | 5 | 0.5% | Covered in catalog |

### 4.2 Distribution by Test Execution Level
| Test Level | Files | Test Count | % of Suite | Primary Execution Pattern |
|---|---|---|---|---|
| **Unit** | 51 | 411 | 43.5% | In-memory / ASGI Client / Mock doubles |
| **Regression (RIGHT Verification)** | 18 | 312 | 33.0% | In-memory / ASGI Client / Mock doubles |
| **Integration (API / HTTP)** | 6 | 75 | 7.9% | In-memory / ASGI Client / Mock doubles |
| **Contract** | 5 | 63 | 6.7% | In-memory / ASGI Client / Mock doubles |
| **AI Eval / Benchmark** | 13 | 60 | 6.3% | In-memory / ASGI Client / Mock doubles |
| **Integration (Component)** | 2 | 24 | 2.5% | In-memory / ASGI Client / Mock doubles |

---

## 5. Duplicate Candidates

Based on comparative AST analysis of tested behavior, assertions, boundaries, and fixtures, the following test files represent **CONFIRMED** or **LIKELY** duplicates or redundant overlaps:

### 5.1 Duplicate Candidate 1: Exact / Semantic Caching Mocks vs Real Engine
- **Candidates**: [`backend/tests/test_semantic_cache.py`](file:///e:/JakeAI/backend/tests/test_semantic_cache.py) vs [`backend/tests/test_semantic_cache_real.py`](file:///e:/JakeAI/backend/tests/test_semantic_cache_real.py) vs [`backend/tests/test_r_func_03_cache_behavior.py`](file:///e:/JakeAI/backend/tests/test_r_func_03_cache_behavior.py)
- **Status**: **CONFIRMED DUPLICATE & OBSOLETE** (`test_semantic_cache.py`)
- **Evidence**:
  - `test_semantic_cache.py` (lines 40-75) creates a mock embedding vector of length 128 (`len(vec1) == 128`) and tests cosine similarity on synthetic floats.
  - `test_semantic_cache_real.py` (lines 25-60) and `test_r_func_03_cache_behavior.py` (lines 140-200) test the REAL production 384-dimensional FastEmbed ONNX model (`bge-small-en-v1.5`) and real Qdrant payload filters.
  - The mock 128-d tests in `test_semantic_cache.py` provide zero production confidence and actively misled early development (as documented in `R-FUNC-03 Result.md`).
- **Recommendation**: Remove `test_semantic_cache.py` during refactoring; merge `test_semantic_cache_real.py` into `target/integration/cache/`.

### 5.2 Duplicate Candidate 2: BM25 Disk Persistence
- **Candidates**: [`backend/tests/test_rag_bm25_persistence.py`](file:///e:/JakeAI/backend/tests/test_rag_bm25_persistence.py) vs [`backend/tests/test_rag.py`](file:///e:/JakeAI/backend/tests/test_rag.py#L30-L65) vs [`backend/tests/test_r_func_02_rag_behavior.py`](file:///e:/JakeAI/backend/tests/test_r_func_02_rag_behavior.py#L280-L310)
- **Status**: **CONFIRMED PARTIAL OVERLAP**
- **Evidence**:
  - `test_rag_bm25_persistence.py` defines `test_bm25_persistence_lifecycle` which writes `bm25_test_index.json` to the current working directory, checks reload, and calls `os.remove`.
  - `test_r_func_02_rag_behavior.py` contains `test_scenario_12_restart_persistence` which executes the exact same lifecycle with proper isolated temp directory fixtures (`tmp_path`).
- **Recommendation**: Merge `test_rag_bm25_persistence.py` into `test_r_func_02_rag_behavior.py` / target `integration/rag/`.

### 5.3 Duplicate Candidate 3: FinOps Endpoint Wrappers
- **Candidates**: [`backend/tests/test_finops_endpoints.py`](file:///e:/JakeAI/backend/tests/test_finops_endpoints.py) vs [`backend/tests/test_finops_accounting.py`](file:///e:/JakeAI/backend/tests/test_finops_accounting.py) vs [`backend/tests/test_r_func_00_api_behavior.py`](file:///e:/JakeAI/backend/tests/test_r_func_00_api_behavior.py)
- **Status**: **CONFIRMED DUPLICATE / PARTIAL OVERLAP**
- **Evidence**:
  - `test_finops_endpoints.py` contains only 3 test functions calling `/api/v1/finops/summary` and `/api/v1/finops/budget` with mock DB fixtures.
  - The exact same endpoint requests, headers, and payload assertions are executed in `test_finops_accounting.py` (lines 110-180) and `test_r_func_00_api_behavior.py` (lines 240-280).
- **Recommendation**: Merge the 3 endpoint tests into `test_finops_accounting.py`.

### 5.4 Duplicate Candidate 4: Unified Quota Authority vs Gateway
- **Candidates**: [`backend/tests/test_unified_quota_authority.py`](file:///e:/JakeAI/backend/tests/test_unified_quota_authority.py) vs [`backend/tests/test_gateway.py`](file:///e:/JakeAI/backend/tests/test_gateway.py#L180-L240) vs [`backend/tests/test_r_logic_03_accounting.py`](file:///e:/JakeAI/backend/tests/test_r_logic_03_accounting.py)
- **Status**: **CONFIRMED PARTIAL OVERLAP**
- **Evidence**:
  - `test_unified_quota_authority.py` (3 tests) verifies `enforce_quota` checks and error raising for soft/hard caps.
  - `test_gateway.py` tests the same `FinOpsBudgetManager` quota checks through the HTTP gateway, while `test_r_logic_03_accounting.py` tests quota exhaustion invariants.
- **Recommendation**: Merge into `unit/finops/test_budget_authority.py`.

### 5.5 Duplicate Candidate 5: Verifier Loop & Tenant Rejection
- **Candidates**: [`backend/tests/test_verifier_invariants.py`](file:///e:/JakeAI/backend/tests/test_verifier_invariants.py) vs [`backend/tests/test_r_logic_00_invariants.py`](file:///e:/JakeAI/backend/tests/test_r_logic_00_invariants.py#L90-L160)
- **Status**: **CONFIRMED DUPLICATE / PARTIAL OVERLAP**
- **Evidence**:
  - `test_verifier_invariants.py` tests `test_verifier_tenant_mismatch_at_revision_0` and `test_verifier_tenant_mismatch_at_max_revision`.
  - `test_r_logic_00_invariants.py` tests `test_inv_b1_tenant_isolation_fail_stop_at_revision_0` and `test_inv_b2_max_revisions_rejection` with strictly identical assertion logic.
- **Recommendation**: Merge into `unit/agent/test_verifier_invariants.py`.

---

## 6. Legacy Candidates

Tests developed during early prototype phases (WORK-01 / WORK-02) that reflect obsolete design assumptions:

1. [`backend/tests/test_semantic_cache.py`](file:///e:/JakeAI/backend/tests/test_semantic_cache.py): **CONFIRMED LEGACY**. Uses 128-d vector stubs and in-memory mock dictionary, predating FastEmbed and Qdrant integration.
2. [`backend/tests/test_endpoints.py`](file:///e:/JakeAI/backend/tests/test_endpoints.py): **CONFIRMED LEGACY**. Monolithic 14-test file testing a grab-bag of health, chat, and RAG routes with loose status-code assertions. Superseded by `test_r_func_00_api_behavior.py` and OpenAPI contract validation.
3. [`backend/tests/test_harmonization.py`](file:///e:/JakeAI/backend/tests/test_harmonization.py): **LIKELY LEGACY**. 5 tests written as an ad-hoc cross-subsystem check before the formal 20 RIGHT verification suites were codified.
4. [`backend/tests/test_phase07_production_hardening.py`](file:///e:/JakeAI/backend/tests/test_phase07_production_hardening.py): **LIKELY LEGACY**. 18 tests mixing chaos injection, rate limits, PII masking, and token caps in a single file without modular cohesion.

---

## 7. Obsolete Candidates
1. `test_semantic_cache.py::test_embedding_and_cosine_similarity`: **CONFIRMED OBSOLETE**. Tests synthetic 128-float cosine similarity math rather than the production ONNX pipeline.
2. `test_cache_identity.py::test_legacy_compute_hash_still_works`: **LIKELY OBSOLETE**. Verifies backward compatibility with deprecated `_compute_hash` function that should be phased out.
3. `test_rag.py::test_verifier_node_self_rag_groundedness_reject_loop`: **POSSIBLE OBSOLETE**. Tests old LangGraph self-RAG node loop structure superseded by `CanonicalVerifier` in ADR-001.

---

## 8. Missing Test Categories
The current automated test suite has the following **CONFIRMED** architectural gaps:
1. **Live HTTP FinnApiGo Core Banking Integration**: As noted in `RIGHT-00` (`RISK-01`), built-in banking tools (`app/tools/builtin/finn_api_tools.py`) use hardcoded static dictionaries (e.g. `$240,000.00` balance). Zero automated tests make real HTTP calls to the FinnApiGo Go server (`http://localhost:8080`).
2. **Live External Provider Schema & Key Rotation**: Upstream LLM providers (OpenAI, Gemini, Anthropic) are 100% mocked in CI. No automated contract or smoke test validates live outbound payloads against upstream API schema changes.
3. **Multi-Worker Concurrency & File Lock Contention**: Tests run inside a single Python process. Concurrent read/write contention on `data/bm25_index.json` across multiple Uvicorn workers is not tested under load.
4. **Load & Stress / Performance Regression Gates**: While token optimization is empirically benchmarked, there are zero latency (p95/p99), memory leak, or throughput regression tests under concurrent load.
5. **End-to-End Browser UI Widget Tests**: Frontend widget components are tested with Vitest in `frontend/`, but there are no Playwright / Cypress browser E2E tests verifying widget mounting, SSE streaming, and rendering against a live backend.
6. **Dynamic LLM Security Fuzzing & Red-Teaming**: Guardrails are tested with static regex pattern strings; no automated LLM adversarial red-teaming or fuzzing framework (e.g. Garak / Promptfoo) is integrated.

---

## 9. Slow Test Candidates
Empirical measurements from `pytest --durations=30` execution across the entire 1,105-item test suite:

### 9.1 Top 30 Slowest Test Functions (Empirically Measured)
| Rank | Duration | Test File & Function | Bottleneck Category |
|---|---|---|---|
| 1 | **11.07s** | `tests/test_rag_tenant_isolation.py::test_concurrent_multi_tenant_isolation_stress` | FastEmbed ONNX + multi-tenant concurrency |
| 2 | **9.49s** | `tests/test_r_ai_01_rag_grounding.py::test_scenario_01_fully_supported_with_provenance_tracing` | FastEmbed ONNX + CrossEncoder reranking |
| 3 | **8.85s** | `tests/test_r_func_02_rag_behavior.py::test_scenario_11_tenant_isolation_defense_in_depth` | FastEmbed ONNX vector generation + hybrid retrieval |
| 4 | **7.74s** | `tests/test_r_func_02_rag_behavior.py::test_scenario_05_repeated_indexing_and_version_update` | Ingestion & FastEmbed re-indexing |
| 5 | **7.49s** | `tests/test_r_ai_02_hallucination_resistance.py::test_scenario_03_four_way_failure_distinction` | Grounding verifier + CrossEncoder scoring |
| 6 | **7.46s** | `tests/test_r_func_02_rag_behavior.py::test_scenario_14_http_api_endpoints_complete_boundary` | Full ASGI HTTP request + RAG pipeline |
| 7 | **6.70s** | `tests/evals/test_rag_context_efficiency.py::test_rag_pipeline_10_step_lifecycle_efficiency` | 10-step RAG lifecycle execution |
| 8 | **6.64s** | `tests/test_rag_tenant_isolation.py::test_hybrid_retriever_cross_tenant_rejection` | Multi-tenant hybrid retrieval |
| 9 | **6.63s** | `tests/test_rag_tenant_isolation.py::test_rag_pipeline_end_to_end_tenant_isolation` | End-to-end RAG pipeline tenant isolation |
| 10 | **6.53s** | `tests/test_r_ai_02_hallucination_resistance.py::test_scenario_05_conflicting_context_and_antonym_contradictions` | Proposition claim extraction & verification |
| 11 | **6.27s** | `tests/test_rag_tenant_isolation_hardened.py::test_tenant_isolation_in_ingestion_and_hybrid_retrieval` | Hardened multi-tenant ingestion & RRF search |
| 12 | **5.86s** | `tests/test_rag.py::test_hybrid_retriever_pipeline` | Hybrid retriever dense/sparse fusion |
| 13 | **5.80s** | `tests/test_r_ai_02_hallucination_resistance.py::test_scenario_06_prompt_instructions_contradicting_evidence` | Anti-hallucination verification |
| 14 | **5.69s** | `tests/test_r_ai_02_hallucination_resistance.py::test_scenario_01_unknown_entity_impossible_facts` | Unseen entity hallucination suppression |
| 15 | **5.58s** | `tests/test_r_ai_01_rag_grounding.py::test_scenario_09_irrelevant_chunks_suppressed` | Irrelevant chunk filtering & embedding |
| 16 | **5.49s** | `tests/test_r_func_02_rag_behavior.py::test_scenario_07_irrelevant_query_explicit_abstention` | Negative grounding threshold check |
| 17 | **5.49s** | `tests/test_rag_hybrid_retrieval.py::test_hybrid_retrieval_concurrent_success` | Concurrent RRF scoring |
| 18 | **5.42s** | `tests/test_rag.py::test_document_ingestion_pipeline_end_to_end` | Ingestion, chunking, and point generation |
| 19 | **5.39s** | `tests/test_r_ai_02_hallucination_resistance.py::test_scenario_09_pre_output_leakage_safeguards` | Guardrail scrubbing + RAG |
| 20 | **5.33s** | `tests/test_r_func_02_rag_behavior.py::test_scenario_01_txt_document_full_path` | Full ingestion pipeline for TXT |
| 21 | **5.32s** | `tests/evals/test_canary_leakage.py::test_rag_tenant_isolation_canary_leakage` | Canary leakage evaluation across tenants |
| 22 | **5.26s** | `tests/test_r_func_02_rag_behavior.py::test_scenario_03_pdf_document_full_path` | PDF generation, binary extraction & FastEmbed |
| 23 | **5.22s** | `tests/test_r_func_02_rag_behavior.py::test_scenario_13_provider_failure_graceful_abstention` | Provider exception handling & abstention |
| 24 | **5.18s** | `tests/test_r_func_02_rag_behavior.py::test_scenario_02_markdown_document_full_path` | Markdown heading parsing & chunking |
| 25 | **5.06s** | `tests/test_r_func_02_rag_behavior.py::test_scenario_06_relevant_query_and_claim_grounding` | Grounded answer generation + citations |
| 26 | **4.76s** | `tests/test_rag_embedding_and_points.py::test_repeat_indexing_idempotent_no_duplicates` | Qdrant point upsert idempotency |
| 27 | **4.53s** | `tests/test_r_func_00_api_behavior.py::test_rag_pipeline_endpoints` | ASGI HTTP client roundtrip on RAG routes |
| 28 | **3.92s** | `tests/test_rag.py::test_rag_api_endpoints_integration` | RAG API endpoint integration |
| 29 | **3.92s** | `tests/test_r_logic_00_invariants.py::test_inv_e3_rag_answers_never_leak_foreign_tenant_evidence` | Invariant check on foreign tenant leakage |
| 30 | **3.78s** | `tests/test_rag.py::test_cross_encoder_reranker` | CrossEncoder local transformer inference |

### 9.2 Key Findings on Execution Performance
- **Primary Bottleneck**: 28 of the 30 slowest tests belong to the **RAG Pipeline**, driven by CPU execution of FastEmbed ONNX embeddings (`BAAI/bge-small-en-v1.5`) and Cross-Encoder passage scoring (`ms-marco-MiniLM-L-6-v2`).
- **Sleep Call Bottleneck**: Hardcoded `asyncio.sleep` calls in `test_orc_capabilities.py` (10s total), `test_r_logic_03_accounting.py` (5s), and `test_r_func_03_cache_behavior.py` (3.3s) artificially inflate execution times without testing actual computation.


---

## 10. Flaky Candidates
Static analysis identified **27 test files** with environmental or temporal sensitivity:
- **Sleep-Based Timing Hazards (CONFIRMED FLAKY-PRONE)**:
  - `test_orc_capabilities.py`: 2x `asyncio.sleep(5.0)`
  - `test_r_logic_03_accounting.py`: 1x `asyncio.sleep(5.0)`
  - `test_r_func_03_cache_behavior.py`: 3x `asyncio.sleep(1.1)`
  - `test_r_logic_04_failure_handling.py`: `asyncio.sleep(0.6)` and `asyncio.sleep(1.0)`
  - `test_r_ai_03_tool_correctness.py`: `asyncio.sleep(1.0)`
  - `test_async_worker.py`: `asyncio.sleep(0.05)` and `asyncio.sleep(0.02)`
- **Disk State Side-Effects (LIKELY FLAKY IN PARALLEL RUNS)**:
  - `test_rag_bm25_persistence.py`: Hardcoded writes to `bm25_test_index.json` in root working directory.
- **Unscoped Environment Mutations (CONFIRMED FLAKY-PRONE)**:
  - `test_rag_embedding_and_points.py`: Mutates `os.environ['ENVIRONMENT']` directly without `monkeypatch` or `try/finally` cleanup.
- **System Clock Dependencies (POSSIBLE FLAKY)**:
  - Multiple files compare `datetime.now()` or `datetime.utcnow()` directly without frozen clock fixtures (e.g. `freezegun`).

---

## 11. External Dependency Tests
Test files requiring external backing services or local ML model runtimes:
- **Redis Service Required** (Mocked in pure unit tests, live in CI):
  - `test_durable_checkpointing.py`, `test_resume_bridge.py`, `test_async_worker.py`, `test_semantic_cache_real.py`, `test_r_func_03_cache_behavior.py`
- **Qdrant Vector Database Required** (In-memory `:memory:` in unit, live container in CI):
  - `test_semantic_cache_real.py`, `test_r_func_03_cache_behavior.py`, `test_rag.py`, `test_rag_embedding_and_points.py`, `test_rag_tenant_isolation.py`
- **Local FastEmbed ONNX Model Runtime** (Real CPU inference in test process):
  - `test_semantic_cache_real.py`, `test_r_func_03_cache_behavior.py`, `test_rag.py`, `test_rag_parsers.py`, `evals/test_rag_context_efficiency.py`
- **PyPDF Binary PDF Parsing Engine**:
  - `test_rag_parsers.py`, `test_r_func_02_rag_behavior.py`
- **PayOS Cryptographic HMAC-SHA256 Verification**:
  - `test_finops_accounting.py`, `test_finops_endpoints.py`

---

## 12. Tests Already Covered by RIGHT
The 20 RIGHT verification suites (`test_r_*`, 401 tests) provide rigorous coverage of core system contracts:
| RIGHT Area | Test Suite File | Test Count | Defects Verified & Closed in RIGHT |
|---|---|---|---|
| R-FUNC-00 | `test_r_func_00_api_behavior.py` | 39 | Stream termination, 51 route boundaries |
| R-FUNC-01 | `test_r_func_01_agent_behavior.py` | 12 | Agent execution DAG, tool registry, approval bridge |
| R-FUNC-02 | `test_r_func_02_rag_behavior.py` | 14 | Ingestion, UTF-8 normalization, citation grounding |
| R-FUNC-03 | `test_r_func_03_cache_behavior.py` | 45 | Cache identity across 12 dimensions, Tier 1/2 caches |
| R-FUNC-04 | `test_r_func_04_provider_behavior.py` | 22 | Dispatcher delta streaming, BYOK credentials |
| R-LOGIC-00 | `test_r_logic_00_invariants.py` | 30 | Terminal state immutability, tenant isolation fail-stop |
| R-LOGIC-01 | `test_r_logic_01_state_transitions.py` | 24 | Lifecycle DAG transitions, pause/resume loops |
| R-LOGIC-02 | `test_r_logic_02_data_flow.py` | 15 | Two-zone compiler immutability, prompt flow |
| R-LOGIC-03 | `test_r_logic_03_accounting.py` | 23 | FinOps ledger token exactness, soft/hard caps |
| R-LOGIC-04 | `test_r_logic_04_failure_handling.py` | 38 | Circuit breaker trip/reset, bounded retries |
| R-ARCH-00 | `test_r_arch_00_architecture_integrity.py`| 18 | Clean architecture layered imports, no leaks |
| R-ARCH-01 | `test_r_arch_01_canonical_authority.py` | 13 | Single authority for verifier, state, tokens |
| R-ARCH-02 | `test_r_arch_02_dependency_boundaries.py`| 12 | Boundary enforcement: API -> Domain -> Infra |
| R-ARCH-03 | `test_r_arch_03_duplicate_abstractions.py`| 17 | Deduplication of contracts and helper utilities |
| R-ARCH-04 | `test_r_arch_04_contract_consistency.py` | 17 | Pydantic v2 domain models and schema drift |
| R-AI-00 | `test_r_ai_00_agent_correctness.py` | 12 | Intent classification, negative constraint adherence |
| R-AI-01 | `test_r_ai_01_rag_grounding.py` | 12 | Proposition citation validity, abstention threshold |
| R-AI-02 | `test_r_ai_02_hallucination_resistance.py`| 13 | Cross-encoder relevance, conflicting data rejection |
| R-AI-03 | `test_r_ai_03_tool_correctness.py` | 16 | Tool execution safety, sandboxing, shell guards |
| R-AI-04 | `test_r_ai_04_context_correctness.py` | 19 | AST skeletonizer integrity, context window bounds |
| **TOTAL** | **20 Suites** | **401 Tests** | **All 20 RIGHT areas fully verified** |

---

## 13. Tests Already Covered by Bruno
The 85 Bruno requests across 12 collections (`Bruno/`) provide black-box HTTP API verification matching or exceeding many API unit tests:
- `Bruno/00 — Setup & Environment`: Overlaps `test_health.py` and `test_endpoints.py` (probes `/health`, `/live`, `/ready`).
- `Bruno/01 — Authentication & Tenant`: Overlaps `test_r_func_00_api_behavior.py` (validates JWT, 401 Unauthorized, cross-tenant 403).
- `Bruno/02 — Chat & Gateway`: Overlaps `test_gateway.py` and `test_r_func_00_api_behavior.py` (`/v1/chat/completions`, SSE streaming, model catalog).
- `Bruno/03 — Agent`: Overlaps `test_agent_platform.py` and `test_r_func_01_agent_behavior.py` (Task CRUD, Run lifecycle, approvals, resume, metrics).
- `Bruno/04 — RAG`: Overlaps `test_rag.py` and `test_r_func_02_rag_behavior.py` (Document ingest, query, citations, abstention).
- `Bruno/05 — BYOK & Providers`: Overlaps `test_byok.py` and `test_r_func_04_provider_behavior.py` (Key vault registration, rotation, revocation).
- `Bruno/06 — Cache`: Overlaps `test_r_func_03_cache_behavior.py` (Exact cache miss/hit, semantic cache, parameter isolation).
- `Bruno/07 — FinOps & Billing`: Overlaps `test_finops_accounting.py` and `test_finops_endpoints.py` (Costs, budgets, subscription status).
- `Bruno/08 — Security & Negative`: Overlaps `test_guardrails.py` and `contract/test_internal_mutual_auth.py` (Prompt injection, malformed inputs, auth failures).
- `Bruno/09 — Failure & Recovery`: Overlaps `test_circuit_breaker.py` and `test_r_logic_04_failure_handling.py` (Provider timeouts, 429 retries, failover, cancel race).
- `Bruno/10 — Cross System E2E`: Overlaps `test_cross_tier_pipeline.py` (End-to-end multi-tier pipeline workflows).

---

## 14. Tests Duplicated Across Layers
Multiple functionalities are asserted across three distinct layers (Unit, Integration, and API):
1. **Cache Identity Hashing**:
   - Layer 1 (Unit): `backend/tests/unit/test_cache_identity.py` (34 tests on `derive_cache_identity`).
   - Layer 2 (Component): `backend/tests/test_two_zone_compiler.py` (7 tests on Zone 1 hash invalidation).
   - Layer 3 (Integration/HTTP): `backend/tests/test_r_func_03_cache_behavior.py` (45 tests across memory, Redis, and SSE streams).
   - Layer 4 (E2E HTTP): `Bruno/06 — Cache` (6 live HTTP tests).
   - *Status*: **COMPLEMENTARY**. Each layer tests a distinct boundary (pure hash algorithm -> prompt compiler -> cache manager & redis -> live HTTP).
2. **RAG Grounding & Abstention**:
   - Layer 1 (Unit): `backend/tests/test_rag_grounding_and_abstention.py` (6 tests).
   - Layer 2 (Component): `backend/tests/test_rag.py` (16 tests).
   - Layer 3 (AI Eval Gate): `backend/tests/evals/test_rag_regression.py` (1 golden test).
   - Layer 4 (RIGHT Regression): `backend/tests/test_r_ai_01_rag_grounding.py` (12 tests) & `test_r_func_02_rag_behavior.py` (14 tests).
   - *Status*: **PARTIAL OVERLAP**. `test_rag_grounding_and_abstention.py` is redundant with `test_r_ai_01_rag_grounding.py` and should be merged.
3. **FinOps Token Ledger & Budgets**:
   - Layer 1 (Unit): `backend/tests/unit/test_canonical_token_accounting.py` (16 tests).
   - Layer 2 (Integration): `backend/tests/test_finops_accounting.py` (21 tests).
   - Layer 3 (API Wrapper): `backend/tests/test_finops_endpoints.py` (3 tests).
   - Layer 4 (RIGHT Invariants): `backend/tests/test_r_logic_03_accounting.py` (23 tests).
   - *Status*: **PARTIAL OVERLAP**. `test_finops_endpoints.py` is redundant and should be merged into `test_finops_accounting.py`.

---

## 15. Current CI Execution Model
An inspection of `.github/workflows/ci.yml` and `.github/workflows/ai-benchmark-scheduled.yml` reveals the following pipeline architecture:
```
GitHub Actions Workflow: ci.yml
├── secret-scanning              (Gitleaks)
├── dependency-and-sast          (pip-audit, bandit, pip-licenses, CycloneDX SBOM)
├── infra-lint                   (hadolint Dockerfile, actionlint workflows)
├── lint-and-typecheck           (ruff check, ruff format --check, mypy app/)
├── frontend-build-and-test      (npm run typecheck, npm run test:coverage, npm run build)
├── unit-and-ai-tests            (Matrix: Python 3.11, 3.12 | Services: Redis 7, Qdrant 1.12.1)
│   ├── Step 1: pytest --cov=app --cov-branch tests/ --cov-fail-under=85  [RUNS ENTIRE 1,105 TESTS!]
│   ├── Step 2: python scripts/check_coverage_diff.py --min-line 85 --min-patch 80
│   ├── Step 3: pytest tests/evals/test_token_benchmark.py                [RE-EXECUTION #1]
│   ├── Step 4: python scripts/run_ai_evaluation.py && pytest tests/evals/test_portfolio_benchmark.py [RE-EXECUTION #2]
│   ├── Step 5: pytest tests/contract/test_internal_mutual_auth.py       [RE-EXECUTION #3]
│   ├── Step 6: pytest tests/evals/test_rag_regression.py                 [RE-EXECUTION #4]
│   ├── Step 7: pytest tests/evals/test_canary_leakage.py ... (4 files)   [RE-EXECUTION #5]
│   └── Step 8: pytest tests/contract/test_api_contract.py                [RE-EXECUTION #6]
└── container-build-and-scan     (Docker buildx, Trivy vulnerability scan)
```
### Critical CI Inefficiencies Identified:
1. **Monolithic Test Execution**: `pytest tests/` runs all 1,105 tests on every push and PR without filtering.
2. **Duplicate Re-execution**: 10 distinct eval and contract test files are executed twice per CI run (first in Step 1, then again in individual gate steps).
3. **Zero Pytest Markers**: Tests lack markers (`unit`, `integration`, `contract`, `security`, `evals`, `slow`), preventing selective PR execution.

---

## 16. Proposed Future Architecture
In accordance with `TEST-00`, we propose (without modifying existing code or directories) the target test architecture:

```
backend/tests/
├── fixtures/          (Shared pytest fixtures, mock clients, test database factories)
├── unit/              (Fast in-memory unit tests: contracts, tokenizers, crypto, algorithms)
├── integration/       (Component and ASGI HTTP integration tests with mock/local services)
├── contract/          (OpenAPI schema drift, internal perimeter auth, consumer contracts)
├── security/          (Guardrails, BYOK vault encryption, PII masking, tenant isolation)
├── evals/             (AI benchmark datasets, quality gates, RAG faithfulness, prompt evals)
├── performance/       (Token benchmarks, latency measurements, throughput regression)
└── e2e/               (Multi-subsystem workflows, live provider smoke tests, Bruno CLI runner)
```

### 16.1 Target Placement Mapping for All 95 Existing Test Files
| Existing Test File | Target Directory | Rationale |
|---|---|---|
| [`conftest.py`](file:///e:/JakeAI/backend/tests/conftest.py) | `backend/tests/fixtures/` | Root shared ASGI test client fixture. Should be moved to fixtures/. |
| [`test_agent_platform.py`](file:///e:/JakeAI/backend/tests/test_agent_platform.py) | `backend/tests/integration/` | Valuable subsystem test. Needs reclassification into unit/, integration/, or security/. |
| [`test_agent_registry_and_selector.py`](file:///e:/JakeAI/backend/tests/test_agent_registry_and_selector.py) | `backend/tests/unit/` | Valuable subsystem test. Needs reclassification into unit/, integration/, or security/. |
| [`test_architecture_invariants.py`](file:///e:/JakeAI/backend/tests/test_architecture_invariants.py) | `backend/tests/unit/` | Valuable subsystem test. Needs reclassification into unit/, integration/, or security/. |
| [`test_async_worker.py`](file:///e:/JakeAI/backend/tests/test_async_worker.py) | `backend/tests/unit/` | Valuable subsystem test. Needs reclassification into unit/, integration/, or security/. |
| [`test_byok.py`](file:///e:/JakeAI/backend/tests/test_byok.py) | `backend/tests/unit/` | Valuable subsystem test. Needs reclassification into unit/, integration/, or security/. |
| [`test_circuit_breaker.py`](file:///e:/JakeAI/backend/tests/test_circuit_breaker.py) | `backend/tests/unit/` | Valuable subsystem test. Needs reclassification into unit/, integration/, or security/. |
| [`test_commercial_services.py`](file:///e:/JakeAI/backend/tests/test_commercial_services.py) | `backend/tests/unit/` | Valuable subsystem test. Needs reclassification into unit/, integration/, or security/. |
| [`test_correlation_propagation.py`](file:///e:/JakeAI/backend/tests/test_correlation_propagation.py) | `backend/tests/unit/` | Valuable subsystem test. Needs reclassification into unit/, integration/, or security/. |
| [`test_cosign_oidc_signing.py`](file:///e:/JakeAI/backend/tests/test_cosign_oidc_signing.py) | `backend/tests/security/` | Valuable subsystem test. Needs reclassification into unit/, integration/, or security/. |
| [`test_cross_tier_pipeline.py`](file:///e:/JakeAI/backend/tests/test_cross_tier_pipeline.py) | `backend/tests/unit/` | Valuable subsystem test. Needs reclassification into unit/, integration/, or security/. |
| [`test_devops_bot.py`](file:///e:/JakeAI/backend/tests/test_devops_bot.py) | `backend/tests/unit/` | Valuable subsystem test. Needs reclassification into unit/, integration/, or security/. |
| [`test_durable_checkpointing.py`](file:///e:/JakeAI/backend/tests/test_durable_checkpointing.py) | `backend/tests/unit/` | Valuable subsystem test. Needs reclassification into unit/, integration/, or security/. |
| [`test_endpoints.py`](file:///e:/JakeAI/backend/tests/test_endpoints.py) | `backend/tests/integration/` | Valuable subsystem test. Needs reclassification into unit/, integration/, or security/. |
| [`test_execution_engine_and_adapters.py`](file:///e:/JakeAI/backend/tests/test_execution_engine_and_adapters.py) | `backend/tests/unit/` | Valuable subsystem test. Needs reclassification into unit/, integration/, or security/. |
| [`test_finops_accounting.py`](file:///e:/JakeAI/backend/tests/test_finops_accounting.py) | `backend/tests/unit/` | Valuable subsystem test. Needs reclassification into unit/, integration/, or security/. |
| [`test_finops_endpoints.py`](file:///e:/JakeAI/backend/tests/test_finops_endpoints.py) | `backend/tests/integration/` | Only 3 tests; overlaps with test_finops_accounting.py and test_r_func_00_api_behavior.py. Merge into integration/finops/. |
| [`test_gateway.py`](file:///e:/JakeAI/backend/tests/test_gateway.py) | `backend/tests/integration/` | Valuable subsystem test. Needs reclassification into unit/, integration/, or security/. |
| [`test_guardrails.py`](file:///e:/JakeAI/backend/tests/test_guardrails.py) | `backend/tests/security/` | Valuable subsystem test. Needs reclassification into unit/, integration/, or security/. |
| [`test_harmonization.py`](file:///e:/JakeAI/backend/tests/test_harmonization.py) | `backend/tests/unit/` | Valuable subsystem test. Needs reclassification into unit/, integration/, or security/. |
| [`test_health.py`](file:///e:/JakeAI/backend/tests/test_health.py) | `backend/tests/integration/` | Valuable subsystem test. Needs reclassification into unit/, integration/, or security/. |
| [`test_local_provider.py`](file:///e:/JakeAI/backend/tests/test_local_provider.py) | `backend/tests/unit/` | Valuable subsystem test. Needs reclassification into unit/, integration/, or security/. |
| [`test_multi_agent.py`](file:///e:/JakeAI/backend/tests/test_multi_agent.py) | `backend/tests/unit/` | Valuable subsystem test. Needs reclassification into unit/, integration/, or security/. |
| [`test_observability_and_tracing.py`](file:///e:/JakeAI/backend/tests/test_observability_and_tracing.py) | `backend/tests/unit/` | Valuable subsystem test. Needs reclassification into unit/, integration/, or security/. |
| [`test_openai_compatibility.py`](file:///e:/JakeAI/backend/tests/test_openai_compatibility.py) | `backend/tests/unit/` | Valuable subsystem test. Needs reclassification into unit/, integration/, or security/. |
| [`test_orc_capabilities.py`](file:///e:/JakeAI/backend/tests/test_orc_capabilities.py) | `backend/tests/unit/` | Contains asyncio.sleep(5.0). Tests ORC-09/10/11 features that overlap test_agent_platform.py. Eliminate sleeps and merge. |
| [`test_orchestration_contracts.py`](file:///e:/JakeAI/backend/tests/test_orchestration_contracts.py) | `backend/tests/contract/` | API/Internal contract test. Move to contract/. |
| [`test_orchestration_planner.py`](file:///e:/JakeAI/backend/tests/test_orchestration_planner.py) | `backend/tests/unit/` | Valuable subsystem test. Needs reclassification into unit/, integration/, or security/. |
| [`test_phase07_production_hardening.py`](file:///e:/JakeAI/backend/tests/test_phase07_production_hardening.py) | `backend/tests/unit/` | Valuable subsystem test. Needs reclassification into unit/, integration/, or security/. |
| [`test_prompt_compression_live.py`](file:///e:/JakeAI/backend/tests/test_prompt_compression_live.py) | `backend/tests/unit/` | Valuable subsystem test. Needs reclassification into unit/, integration/, or security/. |
| [`test_provider_failover_credentials.py`](file:///e:/JakeAI/backend/tests/test_provider_failover_credentials.py) | `backend/tests/unit/` | Valuable subsystem test. Needs reclassification into unit/, integration/, or security/. |
| [`test_provider_foundation.py`](file:///e:/JakeAI/backend/tests/test_provider_foundation.py) | `backend/tests/unit/` | Valuable subsystem test. Needs reclassification into unit/, integration/, or security/. |
| [`test_provider_prompt_caching.py`](file:///e:/JakeAI/backend/tests/test_provider_prompt_caching.py) | `backend/tests/unit/` | Valuable subsystem test. Needs reclassification into unit/, integration/, or security/. |
| [`test_r_ai_00_agent_correctness.py`](file:///e:/JakeAI/backend/tests/test_r_ai_00_agent_correctness.py) | `backend/tests/unit/` | Authoritative RIGHT verification suite for R-AI-00. Move to dedicated integration/ or regression/ target folder. |
| [`test_r_ai_01_rag_grounding.py`](file:///e:/JakeAI/backend/tests/test_r_ai_01_rag_grounding.py) | `backend/tests/unit/` | Authoritative RIGHT verification suite for R-AI-01. Move to dedicated integration/ or regression/ target folder. |
| [`test_r_ai_02_hallucination_resistance.py`](file:///e:/JakeAI/backend/tests/test_r_ai_02_hallucination_resistance.py) | `backend/tests/unit/` | Authoritative RIGHT verification suite for R-AI-02. Move to dedicated integration/ or regression/ target folder. |
| [`test_r_ai_03_tool_correctness.py`](file:///e:/JakeAI/backend/tests/test_r_ai_03_tool_correctness.py) | `backend/tests/unit/` | Authoritative RIGHT verification suite for R-AI-03. Move to dedicated integration/ or regression/ target folder. |
| [`test_r_ai_04_context_correctness.py`](file:///e:/JakeAI/backend/tests/test_r_ai_04_context_correctness.py) | `backend/tests/unit/` | Authoritative RIGHT verification suite for R-AI-04. Move to dedicated integration/ or regression/ target folder. |
| [`test_r_arch_00_architecture_integrity.py`](file:///e:/JakeAI/backend/tests/test_r_arch_00_architecture_integrity.py) | `backend/tests/unit/` | Authoritative RIGHT verification suite for R-ARCH-00. Move to dedicated integration/ or regression/ target folder. |
| [`test_r_arch_01_canonical_authority.py`](file:///e:/JakeAI/backend/tests/test_r_arch_01_canonical_authority.py) | `backend/tests/unit/` | Authoritative RIGHT verification suite for R-ARCH-01. Move to dedicated integration/ or regression/ target folder. |
| [`test_r_arch_02_dependency_boundaries.py`](file:///e:/JakeAI/backend/tests/test_r_arch_02_dependency_boundaries.py) | `backend/tests/unit/` | Authoritative RIGHT verification suite for R-ARCH-02. Move to dedicated integration/ or regression/ target folder. |
| [`test_r_arch_03_duplicate_abstractions.py`](file:///e:/JakeAI/backend/tests/test_r_arch_03_duplicate_abstractions.py) | `backend/tests/unit/` | Authoritative RIGHT verification suite for R-ARCH-03. Move to dedicated integration/ or regression/ target folder. |
| [`test_r_arch_04_contract_consistency.py`](file:///e:/JakeAI/backend/tests/test_r_arch_04_contract_consistency.py) | `backend/tests/contract/` | Authoritative RIGHT verification suite for R-ARCH-04. Move to dedicated integration/ or regression/ target folder. |
| [`test_r_func_00_api_behavior.py`](file:///e:/JakeAI/backend/tests/test_r_func_00_api_behavior.py) | `backend/tests/integration/` | Authoritative RIGHT verification suite for R-FUNC-00. Move to dedicated integration/ or regression/ target folder. |
| [`test_r_func_01_agent_behavior.py`](file:///e:/JakeAI/backend/tests/test_r_func_01_agent_behavior.py) | `backend/tests/unit/` | Authoritative RIGHT verification suite for R-FUNC-01. Move to dedicated integration/ or regression/ target folder. |
| [`test_r_func_02_rag_behavior.py`](file:///e:/JakeAI/backend/tests/test_r_func_02_rag_behavior.py) | `backend/tests/unit/` | Authoritative RIGHT verification suite for R-FUNC-02. Move to dedicated integration/ or regression/ target folder. |
| [`test_r_func_03_cache_behavior.py`](file:///e:/JakeAI/backend/tests/test_r_func_03_cache_behavior.py) | `backend/tests/unit/` | Authoritative RIGHT verification suite for R-FUNC-03. Move to dedicated integration/ or regression/ target folder. |
| [`test_r_func_04_provider_behavior.py`](file:///e:/JakeAI/backend/tests/test_r_func_04_provider_behavior.py) | `backend/tests/unit/` | Authoritative RIGHT verification suite for R-FUNC-04. Move to dedicated integration/ or regression/ target folder. |
| [`test_r_logic_00_invariants.py`](file:///e:/JakeAI/backend/tests/test_r_logic_00_invariants.py) | `backend/tests/unit/` | Authoritative RIGHT verification suite for R-LOGIC-00. Move to dedicated integration/ or regression/ target folder. |
| [`test_r_logic_01_state_transitions.py`](file:///e:/JakeAI/backend/tests/test_r_logic_01_state_transitions.py) | `backend/tests/unit/` | Authoritative RIGHT verification suite for R-LOGIC-01. Move to dedicated integration/ or regression/ target folder. |
| [`test_r_logic_02_data_flow.py`](file:///e:/JakeAI/backend/tests/test_r_logic_02_data_flow.py) | `backend/tests/unit/` | Authoritative RIGHT verification suite for R-LOGIC-02. Move to dedicated integration/ or regression/ target folder. |
| [`test_r_logic_03_accounting.py`](file:///e:/JakeAI/backend/tests/test_r_logic_03_accounting.py) | `backend/tests/unit/` | Authoritative RIGHT verification suite for R-LOGIC-03. Move to dedicated integration/ or regression/ target folder. |
| [`test_r_logic_04_failure_handling.py`](file:///e:/JakeAI/backend/tests/test_r_logic_04_failure_handling.py) | `backend/tests/unit/` | Authoritative RIGHT verification suite for R-LOGIC-04. Move to dedicated integration/ or regression/ target folder. |
| [`test_rag.py`](file:///e:/JakeAI/backend/tests/test_rag.py) | `backend/tests/unit/` | Valuable subsystem test. Needs reclassification into unit/, integration/, or security/. |
| [`test_rag_bm25_persistence.py`](file:///e:/JakeAI/backend/tests/test_rag_bm25_persistence.py) | `backend/tests/unit/` | Tests BM25 disk persistence; overlaps with test_rag.py and test_r_func_02_rag_behavior.py. Writes bm25_test_index.json to disk. Merge into integration/rag/. |
| [`test_rag_context_budget.py`](file:///e:/JakeAI/backend/tests/test_rag_context_budget.py) | `backend/tests/unit/` | Tests context budget shedding; overlaps with test_rag_unified_envelope.py and test_r_ai_04_context_correctness.py. Merge into unit/rag/. |
| [`test_rag_embedding_and_points.py`](file:///e:/JakeAI/backend/tests/test_rag_embedding_and_points.py) | `backend/tests/unit/` | Tests deterministic UUIDv5 points. Contains unscoped os.environ mutation. Needs fix and move to unit/rag/. |
| [`test_rag_grounding_and_abstention.py`](file:///e:/JakeAI/backend/tests/test_rag_grounding_and_abstention.py) | `backend/tests/unit/` | Groundedness threshold checks; largely replicated and extended in test_r_ai_01_rag_grounding.py and test_r_func_02_rag_behavior.py. Merge. |
| [`test_rag_hybrid_retrieval.py`](file:///e:/JakeAI/backend/tests/test_rag_hybrid_retrieval.py) | `backend/tests/unit/` | RRF hybrid retrieval unit tests; duplicate logic in test_rag.py. Merge into unit/rag/. |
| [`test_rag_normalization.py`](file:///e:/JakeAI/backend/tests/test_rag_normalization.py) | `backend/tests/unit/` | High-value unit tests for NFKC unicode and MIME parsing. Move to unit/rag/. |
| [`test_rag_parsers.py`](file:///e:/JakeAI/backend/tests/test_rag_parsers.py) | `backend/tests/unit/` | Comprehensive document parser unit tests (MD, PDF, TXT). Move to unit/rag/. |
| [`test_rag_reranker.py`](file:///e:/JakeAI/backend/tests/test_rag_reranker.py) | `backend/tests/unit/` | Tests CrossEncoder reranking; overlaps with test_rag.py (lines 130-180) and test_r_func_02_rag_behavior.py. Merge into unit/rag/. |
| [`test_rag_tenant_isolation.py`](file:///e:/JakeAI/backend/tests/test_rag_tenant_isolation.py) | `backend/tests/security/` | Valuable subsystem test. Needs reclassification into unit/, integration/, or security/. |
| [`test_rag_tenant_isolation_hardened.py`](file:///e:/JakeAI/backend/tests/test_rag_tenant_isolation_hardened.py) | `backend/tests/security/` | Defense-in-depth tenant isolation checks. Move to security/ or unit/rag/. |
| [`test_rag_unified_envelope.py`](file:///e:/JakeAI/backend/tests/test_rag_unified_envelope.py) | `backend/tests/unit/` | Valuable subsystem test. Needs reclassification into unit/, integration/, or security/. |
| [`test_resume_bridge.py`](file:///e:/JakeAI/backend/tests/test_resume_bridge.py) | `backend/tests/unit/` | Valuable subsystem test. Needs reclassification into unit/, integration/, or security/. |
| [`test_semantic_cache.py`](file:///e:/JakeAI/backend/tests/test_semantic_cache.py) | `backend/tests/unit/` | Uses obsolete 128-d mock vectors and mock Redis. Completely superseded by test_semantic_cache_real.py (384-d FastEmbed) and test_r_func_03_cache_behavior.py. |
| [`test_semantic_cache_real.py`](file:///e:/JakeAI/backend/tests/test_semantic_cache_real.py) | `backend/tests/unit/` | Exercises real Qdrant/FastEmbed caching. Scenarios overlap with test_r_func_03_cache_behavior.py; should merge into target integration/cache/. |
| [`test_structured_output.py`](file:///e:/JakeAI/backend/tests/test_structured_output.py) | `backend/tests/unit/` | Valuable subsystem test. Needs reclassification into unit/, integration/, or security/. |
| [`test_two_zone_compiler.py`](file:///e:/JakeAI/backend/tests/test_two_zone_compiler.py) | `backend/tests/unit/` | Valuable subsystem test. Needs reclassification into unit/, integration/, or security/. |
| [`test_unified_quota_authority.py`](file:///e:/JakeAI/backend/tests/test_unified_quota_authority.py) | `backend/tests/unit/` | Tests quota enforcement; overlaps with test_gateway.py and test_r_logic_03_accounting.py. Merge into unit/finops/. |
| [`test_verifier_invariants.py`](file:///e:/JakeAI/backend/tests/test_verifier_invariants.py) | `backend/tests/unit/` | Tests verifier loop limits; overlaps with test_r_logic_00_invariants.py and test_orchestration_contracts.py. Merge into unit/agent/. |
| [`test_workload_classification_routing.py`](file:///e:/JakeAI/backend/tests/test_workload_classification_routing.py) | `backend/tests/unit/` | Valuable subsystem test. Needs reclassification into unit/, integration/, or security/. |
| [`test_api_contract.py`](file:///e:/JakeAI/backend/tests/contract/test_api_contract.py) | `backend/tests/contract/` | API/Internal contract test. Move to contract/. |
| [`test_internal_mutual_auth.py`](file:///e:/JakeAI/backend/tests/contract/test_internal_mutual_auth.py) | `backend/tests/contract/` | API/Internal contract test. Move to contract/. |
| [`test_baseline_and_regression_gate.py`](file:///e:/JakeAI/backend/tests/evals/test_baseline_and_regression_gate.py) | `backend/tests/evals/` | AI evaluation or empirical token benchmark suite. Move to evals/. |
| [`test_canary_leakage.py`](file:///e:/JakeAI/backend/tests/evals/test_canary_leakage.py) | `backend/tests/evals/` | AI evaluation or empirical token benchmark suite. Move to evals/. |
| [`test_coding_intelligence_regression.py`](file:///e:/JakeAI/backend/tests/evals/test_coding_intelligence_regression.py) | `backend/tests/evals/` | AI evaluation or empirical token benchmark suite. Move to evals/. |
| [`test_llm_judge_and_generation.py`](file:///e:/JakeAI/backend/tests/evals/test_llm_judge_and_generation.py) | `backend/tests/evals/` | AI evaluation or empirical token benchmark suite. Move to evals/. |
| [`test_phase03_token_optimization.py`](file:///e:/JakeAI/backend/tests/evals/test_phase03_token_optimization.py) | `backend/tests/evals/` | AI evaluation or empirical token benchmark suite. Move to evals/. |
| [`test_phase06_evaluation.py`](file:///e:/JakeAI/backend/tests/evals/test_phase06_evaluation.py) | `backend/tests/evals/` | AI evaluation or empirical token benchmark suite. Move to evals/. |
| [`test_portfolio_benchmark.py`](file:///e:/JakeAI/backend/tests/evals/test_portfolio_benchmark.py) | `backend/tests/evals/` | AI evaluation or empirical token benchmark suite. Move to evals/. |
| [`test_prompt_cache_benchmark.py`](file:///e:/JakeAI/backend/tests/evals/test_prompt_cache_benchmark.py) | `backend/tests/evals/` | AI evaluation or empirical token benchmark suite. Move to evals/. |
| [`test_rag_context_efficiency.py`](file:///e:/JakeAI/backend/tests/evals/test_rag_context_efficiency.py) | `backend/tests/evals/` | AI evaluation or empirical token benchmark suite. Move to evals/. |
| [`test_rag_eval.py`](file:///e:/JakeAI/backend/tests/evals/test_rag_eval.py) | `backend/tests/evals/` | AI evaluation or empirical token benchmark suite. Move to evals/. |
| [`test_rag_metrics.py`](file:///e:/JakeAI/backend/tests/evals/test_rag_metrics.py) | `backend/tests/evals/` | AI evaluation or empirical token benchmark suite. Move to evals/. |
| [`test_rag_regression.py`](file:///e:/JakeAI/backend/tests/evals/test_rag_regression.py) | `backend/tests/evals/` | AI evaluation or empirical token benchmark suite. Move to evals/. |
| [`test_token_benchmark.py`](file:///e:/JakeAI/backend/tests/evals/test_token_benchmark.py) | `backend/tests/evals/` | AI evaluation or empirical token benchmark suite. Move to evals/. |
| [`test_bpe_tokenizer.py`](file:///e:/JakeAI/backend/tests/unit/test_bpe_tokenizer.py) | `backend/tests/unit/` | Already in unit/ directory. High-value isolated unit test. |
| [`test_cache_identity.py`](file:///e:/JakeAI/backend/tests/unit/test_cache_identity.py) | `backend/tests/unit/` | Already in unit/ directory. High-value isolated unit test. |
| [`test_canonical_provider_resolution.py`](file:///e:/JakeAI/backend/tests/unit/test_canonical_provider_resolution.py) | `backend/tests/unit/` | Already in unit/ directory. High-value isolated unit test. |
| [`test_canonical_token_accounting.py`](file:///e:/JakeAI/backend/tests/unit/test_canonical_token_accounting.py) | `backend/tests/unit/` | Already in unit/ directory. High-value isolated unit test. |
| [`test_direct_provider.py`](file:///e:/JakeAI/backend/tests/unit/test_direct_provider.py) | `backend/tests/unit/` | Already in unit/ directory. High-value isolated unit test. |
| [`test_state_bridges.py`](file:///e:/JakeAI/backend/tests/unit/test_state_bridges.py) | `backend/tests/unit/` | Already in unit/ directory. High-value isolated unit test. |
| [`test_structured_conversation_contract.py`](file:///e:/JakeAI/backend/tests/contract/test_structured_conversation_contract.py) | `backend/tests/contract/` | API/Internal contract test. Moved to contract/. |

---

## 17. TEST-01 Execution Record & Migration Results

### 17.1 Reorganization Summary
Under `TEST-01`, the flat test repository was safely reorganized into the target 8-layer architecture with clear ownership:
```
backend/tests/
├── fixtures/     (Shared ASGI client fixture, JWT token creators, test doubles)
├── contract/     (5 files, 67 tests - OpenAPI schema, internal mutual auth, domain contracts)
├── security/     (5 files, 36 tests - Guardrails, BYOK vault, Sigstore Cosign, tenant isolation)
├── performance/  (2 files, 4 tests - Token reduction benchmark, prompt cache benchmark)
├── e2e/          (2 files, 30 tests - Cross-tier pipeline, platform production hardening)
├── evals/        (11 files, 68 tests - Golden datasets, canary leakage, AI judge, RAG metrics)
├── integration/  (16 files, 233 tests - Endpoints, Gateway, Health, Agent Platform, R-FUNC suites)
└── unit/         (52 files, 663 tests - Pure algorithms, tokenizers, models, R-LOGIC, R-ARCH, R-AI suites)
```

- **Active Test Files**: **93 test files** (reduced from 94 by removing 1 proven obsolete stub).
- **Active Fixture Files**: **1 shared fixture module** (`fixtures/auth.py`, `fixtures/client.py`) + root `conftest.py` loader.
- **Total Pytest Collected Test Items**: **1,101 test items** (1,099 passed, 2 skipped in local offline mode for live Redis).
- **Test Suite Pass Rate**: **100%** (0 failures, 0 regressions).

### 17.2 Deduplication & Deletion Record
| Deleted Test File | Functions Deleted | Classification | Behavior Covered In | Rationale & Evidence |
|---|---|---|---|---|
| `tests/test_semantic_cache.py` | 4 (`test_exact_match_cache_hit_and_miss`, `test_semantic_vector_cache_hit_and_tenant_isolation`, `test_cache_invalidation`, `test_embedding_and_cosine_similarity`) | `OBSOLETE` & `DUPLICATE` | `tests/integration/test_semantic_cache_real.py`, `tests/integration/test_r_func_03_cache_behavior.py` | Line 93 tested synthetic 128-float cosine similarity (`len(vec1) == 128`) which actively contradicted production 384-dimensional FastEmbed ONNX embeddings and Qdrant payloads. The real caching behavior, tenant isolation, and cache invalidation are exhaustively covered by 51 tests across `test_semantic_cache_real.py` and `test_r_func_03_cache_behavior.py`. Meaningful coverage was not reduced. |

### 17.3 Preserved Tests Record
All 20 canonical RIGHT verification test suites (`test_r_*`, 401 tests) and all core WORK capabilities (agent orchestration, RAG, FinOps accounting, BYOK security, and token optimization) were preserved without loss of a single regression gate:
- **Preserved in `contract/`**: `test_api_contract.py`, `test_internal_mutual_auth.py`
- **Preserved in `evals/`**: 11 eval suites + `golden_dataset.json` + `workloads_dataset_v1.json`
- **Preserved in `unit/`**: `test_bpe_tokenizer.py`, `test_cache_identity.py`, `test_canonical_provider_resolution.py`, `test_canonical_token_accounting.py`, `test_direct_provider.py`, `test_state_bridges.py`
- **All moved files preserved**: 71 files moved to their authoritative directory layer with exact behavior intact.

### 17.4 Code Coverage Metrics
| Metric | Baseline (TEST-00) | After Migration (TEST-01) | Threshold / Requirement | Status |
|---|---|---|---|---|
| **Branch Coverage** | ~85.0% | **86.97%** | `>= 85.0%` | **PASSED** |
| **Global Line Coverage** | ~87.0% | **89.58%** | `>= 85.0%` | **PASSED** |
| **PR Patch Coverage** | N/A | **91.42%** | `>= 80.0%` | **PASSED** |

### 17.5 Local CI Verification Results
| Verification Gate | Command Executed | Result / Evidence | Status |
|---|---|---|---|
| **Linter Check** | `ruff check .` | All checks passed | **PASSED** |
| **Formatter Check** | `ruff format --check .` | 281 files already formatted | **PASSED** |
| **Type Check** | `mypy --config-file mypy.ini app` | Success: no issues found in 169 source files | **PASSED** |
| **SAST Security** | `bandit -c pyproject.toml -r app/` | No issues identified across 32,291 LOC | **PASSED** |
| **Dependency Audit** | `pip-audit -r requirements.txt` | No known vulnerabilities found | **PASSED** |
| **OpenAPI Contract Gate** | `check_openapi_breaking_changes.py` | 0 breaking changes detected | **PASSED** |
| **Token Benchmark Gate** | `pytest tests/performance/test_token_benchmark.py` | 63.51% net token reduction (>= 40% gate) | **PASSED** |
| **Portfolio Benchmark Gate** | `pytest tests/evals/test_portfolio_benchmark.py` | 48.74% net token reduction (>= 40% gate) | **PASSED** |
| **Internal Mutual Auth Gate**| `pytest tests/contract/test_internal_mutual_auth.py` | 4/4 passed | **PASSED** |
| **RAG Regression Gate** | `pytest tests/evals/test_rag_regression.py` | 7/7 passed | **PASSED** |
| **Canary & LLMOps Gate** | `pytest tests/evals/test_canary_leakage.py ...` | 17/17 passed | **PASSED** |
| **Full Pytest Suite** | `pytest --cov=app --cov-branch tests/` | 1,099 passed, 2 skipped, 0 failed | **PASSED** |

---

## 18. Phase TEST-03 — Integration Test Completeness & CI Regression Resolution

- **Phase**: `TEST-03` (Integration Test Completeness)
- **Branch**: `chore/test-03-integration-completeness`
- **Scope**: Implemented 9 authoritative integration test suites across core dependencies (Redis, Qdrant, Persistence, Agent Runtime, Routing & Providers, RAG Pipeline, Async Ingestion Worker, FinOps Governance, and Telemetry & Context).
- **CI Regressions Identified & Resolved**:
  1. `test_failure_case_1_unavailable_redis` (`test_async_worker_integration.py`): Ensured pure in-memory fallback via patch.object on `_get_redis` to prevent live Redis reconnection.
  2. `test_failure_case_4_connection_failure` (`test_async_worker_integration.py`): Extended connection reset mock across both `_save_task` and `get_task` to verify in-memory task state preservation.
  3. `test_rag_task_manager_redis_queue` (`test_redis_integration.py`): Added `await mgr.clear()` queue isolation before and after test execution to prevent cross-test contamination.
  4. `test_hybrid_retriever_dense_sparse_fusion` (`test_qdrant_integration.py`): Aligned fake embedding dimension with `get_settings().EMBEDDING_DIMENSION` (384) and provisioned isolated unique collection names.
- **Verification Summary**:
  - Full Integration Suites: 32/32 tests passed across modified files.
  - Complete Backend Test Suite: 1,546 passed, 2 skipped, 0 failed.
  - Branch Coverage: 88.37% (Threshold >= 85.0%).
  - Line Coverage: 90.71% (Threshold >= 85.0%).
  - PR Patch Coverage: 100.0%.

---

## 19. Phase TEST-06 — AI Behavior, Agent, RAG & Hallucination Evaluation Automation

- **Phase**: `TEST-06` (AI / Agent / RAG Evaluation Automation)
- **Branch**: `chore/test-06-ai-agent-rag-evaluation-automation`
- **Scope**: Implemented non-brittle, programmatic evaluation layer across 14 Agent dimensions, 10 RAG dimensions, 4 mandatory Hallucination categories, and 3 versioned regression datasets (31 total cases).
- **CI Regressions Identified & Resolved**:
  1. **MyPy Unreachable Code in Hallucination Evaluator**: `HallucinationCategory` is a 4-member `StrEnum`. Replaced unreachable `else: passed = False` with `else: assert_never(expected_category)` to satisfy exhaustiveness while enforcing runtime fail-closed error handling.
  2. **Canonical Metric Normalization Currency Loss**: `METRIC_REGEX` previously required magnitude suffixes when the currency symbol was optional, causing `$100,000,000` to be matched by the plain-number branch without the leading `$`. Fixed by restructuring `METRIC_REGEX` into 4 discrete branches: prefix currency (suffix optional), trailing currency/units, non-monetary magnitude suffixes, and plain numbers.
- **Verification Summary**:
  - Dedicated Evaluation Gate (TEST-06): 63/63 passed in 0.12s.
  - Hallucination Suite (`AI-014`): 14/14 passed in 0.07s.
  - Full Evaluation Suite (`tests/evals/`): 131/131 passed in 100% green.
  - Full Security Suite (`tests/security/`): 141/141 passed.
  - Static Type Check (`mypy`): 0 errors across 171 source files.
  - Linter (`ruff check` & `ruff format`): 0 errors, 310 files formatted.

---

## 20. Phase TEST-07 — JakeAI Python End-to-End Workflow Automation

- **Phase**: `TEST-07` (Python End-to-End Workflow Automation)
- **Branch**: `chore/test-07-e2e-workflow-automation`
- **Scope**: Implemented small, high-value set of full business workflow E2E tests (`E2E-003` / `CAT-124` in `tests/e2e/test_e2e_business_workflows.py`) validating all 7 mandatory workflows:
  1. `AUTH -> CHAT`: Unauthenticated 401 rejection, authenticated 200 response, schema conformance, correlation ID propagation, FinOps ledger accounting, and Tier 1 exact cache hit side-effect.
  2. `AUTH -> AGENT`: Task creation, cross-tenant isolation (403/404), execution, and terminal `completed` state.
  3. `AGENT -> TOOL -> VERIFY`: Task orchestration, tool selection (`CalculatorTool`), tool execution, mathematical verification (`CanonicalVerifier`), and final answer production.
  4. `RAG`: Document ingestion, hybrid retrieval, 6-stage context construction, grounded generation with citations, epistemic abstention on unevidenced query, and tenant isolation.
  5. `BYOK / PROVIDER`: Key configuration, AES-256-GCM vault storage, key masking, memory decryption, provider resolution dispatch, FinOps ledger attribution, and key deletion.
  6. `FAILURE / RECOVERY`: Primary provider failure transparent failover recovery, plus unrecoverable provider outage fail-closed honest terminal state (HTTP 500/503 with sanitized error details).
  7. `APPROVAL`: Task requiring approval pausing in `PAUSED_APPROVAL`, operator approval, execution resume to terminal `COMPLETED`; plus sub-flow 7b for security rejection to `REJECTED`.
- **Live External Workflow**:
  - `test_e2e_workflow_live_external_provider_call`: Marked `@pytest.mark.live_external` and skipped cleanly in offline CI when `LIVE_EXTERNAL_TESTS` env var is absent.
- **Verification Summary**:
  - Critical End-to-End Business Workflow Gate (`E2E-003`): 8/8 passed, 1 deselected with `-m "not live_external"` (or 8 passed, 1 skipped) in 16.2s.
  - Full E2E Suite (`tests/e2e/`): 38/38 passed, 1 skipped in 23.2s.
  - Total Active Executable Test Files: 122 (124 tracked in catalog).
  - Linter & Formatter (`ruff check` & `ruff format`): 0 errors, 100% clean.


