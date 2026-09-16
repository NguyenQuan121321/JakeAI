# TEST-CATALOG — JakeAI Automated Test Suite Catalog
**Audit Baseline**: `main` (`971a340`) | **Status**: TEST-08 BRUNO CLI AUTOMATION COMPLETED
**Scope**: Complete inventory of every test file, test class, and test family under `backend/tests/` and automated Bruno collection under `Bruno/`

---

## 1. Catalog Overview & Summary Statistics
- **Total Tracked Test Files**: 124 tracked in catalog (122 active test files + 1 shared fixture module + 1 deleted obsolete file)
- **Active Executable Test Files**: 122
- **Total Test Functions / Methods**: 1,348 (collected by Pytest as 1,822 test items)
- **Dispositions Summary**:
  - `PRESERVED`: 22 files (in existing directories `evals/`, `unit/`, `contract/`)
  - `MOVED`: 71 files (relocated to authoritative target directories `unit/`, `integration/`, `contract/`, `security/`, `e2e/`, `performance/`)
  - `CREATED`: 29 files (9 unit in TEST-02 + 9 integration in TEST-03 + 2 contract in TEST-04 + 5 runtime security in TEST-05 + 3 AI/RAG/Hallucination evaluation in TEST-06 + 1 E2E business workflows in TEST-07: `CAT-124`)
  - `DELETED`: 1 file (`test_semantic_cache.py` - proven obsolete 128-d synthetic vector stub)
  - `FIXTURES`: 1 module (`tests/fixtures/` with `auth.py`, `client.py` + root `conftest.py` loader)
- **Logical IDs Assigned**:
  - `CONTRACT-*`: 7 files (`CONTRACT-001` through `CONTRACT-007`, 164 tests)
  - `SEC-*`: 10 files (`SEC-001` through `SEC-010`, 141 tests)
  - `PERF-*`: 2 files (`PERF-001` through `PERF-002`, 4 tests)
  - `E2E-*`: 3 files (`E2E-001` through `E2E-003`, 39 tests)
  - `AI-*`: 14 files (`AI-001` through `AI-014`, 131 tests)
  - `INT-*`: 25 files (`INT-001` through `INT-025`, 332 tests)
  - `UNIT-*`: 61 files (`UNIT-001` through `UNIT-061`, 1,011 tests)
- **Duplicate / Overlap Status Breakdown**:
  - `COMPLEMENTARY`: 75 files
  - `UNIQUE`: 33 files
  - `PARTIAL OVERLAP`: 8 files (preserved across distinct testing layers)
  - `OBSOLETE`: 1 file (`test_semantic_cache.py`, successfully deleted)
- **Test Suite Pass Rate**: **100%** (1,714 passed, 3 skipped in offline mode, 0 failed)
- **Code Coverage**: Branch: **87%+** (>=85% gate), Line: **90%+** (>=85% gate), Patch: **95%+** (>=80% gate)

---

## 2. Master Test Catalog Table

This master catalog indexes every test family under `backend/tests/`. All 14 required fields are populated per specification.

| LOGICAL ID | LEGACY ID | FILE | TEST FUNCTION / CLASS | SUBSYSTEM | TEST LEVEL | PURPOSE | DEPENDENCIES | CI JOB | RUN FREQUENCY | DUPLICATE STATUS | RIGHT COVERAGE | BRUNO COVERAGE | DISPOSITION | REASON |
|---|---|---|---|---|---|---|---|---|---|---|---|---|---|---|
| `FIXTURE-001` | `CAT-001` | [`tests/conftest.py`](file:///e:/JakeAI/backend/tests/conftest.py) | Fixtures (`async_client`, `create_test_jwt`, `generate_agent_jwt`) | Core / Platform | Fixture | Pytest fixtures and test environment configuration. | HTTP / ASGI | unit-and-ai-tests (Full Suite Floor) | PR / Push (main) | `UNIQUE` | NONE | NONE | **`FIXTURE`** | Root shared ASGI test client & auth fixture loader registering tests.fixtures. |
| `INT-006` | `CAT-002` | [`tests/integration/test_agent_platform.py`](file:///e:/JakeAI/backend/tests/integration/test_agent_platform.py) | 19 functions (`test_jakeai_backend_text_response` ...) | Agent Orchestration | Integration | Comprehensive integration and contract tests for Phase 08 — JakeAI-Agent Platform. | HTTP / ASGI, Mocks / Monkeypatch | unit-and-ai-tests (Full Suite Floor) | PR / Push (main) | `COMPLEMENTARY` | R-FUNC-01 / R-AI-00 / R-ARCH-00 | Bruno/03 — Agent (01-10) | **`MOVED`** | Moved to integration/. Authoritative agent platform HTTP/service integration test. |
| `UNIT-008` | `CAT-003` | [`tests/unit/test_agent_registry_and_selector.py`](file:///e:/JakeAI/backend/tests/unit/test_agent_registry_and_selector.py) | 5 functions (`TestAgentRegistryAndSelector::test_default_built_in_agents` ...) | Agent Orchestration | Unit | Unit tests for AgentRegistry and AgentSelector. | None (Pure In-Memory) | unit-and-ai-tests (Full Suite Floor) | PR / Push (main) | `COMPLEMENTARY` | R-FUNC-01 / R-AI-00 / R-ARCH-00 | NONE | **`MOVED`** | Moved to unit/. Isolated unit tests for registry & selector. |
| `UNIT-007` | `CAT-004` | [`tests/unit/test_architecture_invariants.py`](file:///e:/JakeAI/backend/tests/unit/test_architecture_invariants.py) | 6 functions (`TestArchitectureInvariants::test_invariant_1_single_task_and_run_contracts` ...) | Core / Platform | Unit | Unit and architecture invariant tests for JakeAI Orchestration Capability (WORK-01). | None (Pure In-Memory) | unit-and-ai-tests (Full Suite Floor) | PR / Push (main) | `COMPLEMENTARY` | R-ARCH-00 / R-LOGIC-00 | NONE | **`MOVED`** | Moved to unit/. Fast in-memory AST and contract invariant tests. |
| `INT-008` | `CAT-005` | [`tests/integration/test_async_worker.py`](file:///e:/JakeAI/backend/tests/integration/test_async_worker.py) | 11 functions (`test_task_manager_enqueue_and_isolation` ...) | RAG Pipeline | Integration | Unit and integration tests for Asynchronous Ingestion Task Queue & Worker. | Redis, HTTP / ASGI, Mocks / Monkeypatch | unit-and-ai-tests (Full Suite Floor) | PR / Push (main) | `COMPLEMENTARY` | NONE | NONE | **`MOVED`** | Moved to integration/. Ingestion background task worker integration tests. |
| `SEC-002` | `CAT-006` | [`tests/security/test_byok.py`](file:///e:/JakeAI/backend/tests/security/test_byok.py) | 16 functions (`test_byok_all_six_providers_lifecycle` ...) | BYOK Security | Security | Unit and integration tests for BYOK (Bring Your Own Key) & AES-256-GCM encryption. | Redis, HTTP / ASGI, Mocks / Monkeypatch | unit-and-ai-tests (Full Suite Floor) | PR / Push (main) | `COMPLEMENTARY` | R-FUNC-04 | Bruno/05 — BYOK & Providers (01-07) | **`MOVED`** | Moved to security/. Vault crypto, tenant key isolation, and rotation suite. |
| `UNIT-009` | `CAT-007` | [`tests/unit/test_circuit_breaker.py`](file:///e:/JakeAI/backend/tests/unit/test_circuit_breaker.py) | 5 functions (`test_circuit_breaker_normal_closed_execution` ...) | Core / Platform | Unit | Unit tests for Circuit Breaker and Fallback Routing. | None (Pure In-Memory) | unit-and-ai-tests (Full Suite Floor) | PR / Push (main) | `COMPLEMENTARY` | NONE | NONE | **`MOVED`** | Moved to unit/. Fast state machine unit tests for circuit breaker. |
| `INT-009` | `CAT-008` | [`tests/integration/test_commercial_services.py`](file:///e:/JakeAI/backend/tests/integration/test_commercial_services.py) | 4 functions (`test_quota_manager_lifecycle` ...) | Core / Platform | Integration | Unit and integration tests for AI Gateway, PayOS Billing, and Analytics Dashboard. | HTTP / ASGI, Mocks / Monkeypatch | unit-and-ai-tests (Full Suite Floor) | PR / Push (main) | `COMPLEMENTARY` | NONE | NONE | **`MOVED`** | Moved to integration/. PayOS billing, quota, and commercial gateway integration. |
| `UNIT-010` | `CAT-009` | [`tests/unit/test_correlation_propagation.py`](file:///e:/JakeAI/backend/tests/unit/test_correlation_propagation.py) | 6 functions (`test_tenant_context_and_obo_token_correlation_id` ...) | RAG Pipeline | Unit | Unit tests for end-to-end Correlation ID propagation across JakeAI components (TASK OPS-04). | Mocks / Monkeypatch | unit-and-ai-tests (Full Suite Floor) | PR / Push (main) | `COMPLEMENTARY` | NONE | NONE | **`MOVED`** | Moved to unit/. Header context & correlation ID propagation. |
| `SEC-003` | `CAT-010` | [`tests/security/test_cosign_oidc_signing.py`](file:///e:/JakeAI/backend/tests/security/test_cosign_oidc_signing.py) | 4 functions (`test_missing_oidc_env_vars_fails_immediately` ...) | Security & Governance | Security | Automated verification suite for deterministic Cosign keyless OIDC signing. | None (Pure In-Memory) | unit-and-ai-tests (Full Suite Floor) | PR / Push (main) | `COMPLEMENTARY` | NONE | NONE | **`MOVED`** | Moved to security/. Sigstore Cosign OIDC signing and provenance verification. |
| `E2E-001` | `CAT-011` | [`tests/e2e/test_cross_tier_pipeline.py`](file:///e:/JakeAI/backend/tests/e2e/test_cross_tier_pipeline.py) | 12 functions (`test_dynamic_change_does_not_change_static_prefix` ...) | Core / Platform | E2E | Comprehensive Integration & Verification Tests for Tier 5 -> 6 -> 7 -> 5 Pipeline. | None (Pure In-Memory) | unit-and-ai-tests (Full Suite Floor) | PR / Push (main) | `COMPLEMENTARY` | R-FUNC-03 / R-AI-02 | NONE | **`MOVED`** | Moved to e2e/. End-to-end multi-tier context and token pipeline workflows. |
| `INT-010` | `CAT-012` | [`tests/integration/test_devops_bot.py`](file:///e:/JakeAI/backend/tests/integration/test_devops_bot.py) | 5 functions (`test_diff_pruner_strips_lockfiles` ...) | DevOps Bot | Integration | Unit and integration tests for DevOps & Codebase Audit Bot SaaS. | Redis, HTTP / ASGI | unit-and-ai-tests (Full Suite Floor) | PR / Push (main) | `COMPLEMENTARY` | NONE | NONE | **`MOVED`** | Moved to integration/. DevOps bot endpoint and review pipeline integration. |
| `UNIT-011` | `CAT-013` | [`tests/unit/test_durable_checkpointing.py`](file:///e:/JakeAI/backend/tests/unit/test_durable_checkpointing.py) | 2 functions (`test_durable_checkpointing_lifecycle` ...) | Core / Platform | Unit | Tests for Durable Redis Checkpointing (TASK ORC-05). | Redis, Mocks / Monkeypatch | unit-and-ai-tests (Full Suite Floor) | PR / Push (main) | `COMPLEMENTARY` | NONE | NONE | **`MOVED`** | Moved to unit/. Agent checkpoint serialization and recovery unit tests. |
| `INT-001` | `CAT-014` | [`tests/integration/test_endpoints.py`](file:///e:/JakeAI/backend/tests/integration/test_endpoints.py) | 14 functions (`test_health_endpoint_contract` ...) | Gateway & Routing | Integration | End-to-end Integration and Contract Tests for all JakeAI Platform Endpoints. | HTTP / ASGI, Mocks / Monkeypatch | unit-and-ai-tests (Full Suite Floor) | PR / Push (main) | `COMPLEMENTARY` | R-FUNC-00 | NONE | **`MOVED`** | Moved to integration/. Multi-endpoint HTTP route contract verification. |
| `UNIT-012` | `CAT-015` | [`tests/unit/test_execution_engine_and_adapters.py`](file:///e:/JakeAI/backend/tests/unit/test_execution_engine_and_adapters.py) | 11 functions (`test_scenario_1_simple_question` ...) | Agent Orchestration | Unit | Integration tests for Canonical ExecutionEngine and LangGraphExecutionAdapter. | None (Pure In-Memory) | unit-and-ai-tests (Full Suite Floor) | PR / Push (main) | `COMPLEMENTARY` | R-FUNC-01 / R-AI-00 / R-ARCH-00 | NONE | **`MOVED`** | Moved to unit/. DAG execution engine and adapter conformance unit tests. |
| `UNIT-013` | `CAT-016` | [`tests/unit/test_finops_accounting.py`](file:///e:/JakeAI/backend/tests/unit/test_finops_accounting.py) | 21 functions (`test_finops_pricing_matrix` ...) | FinOps & Billing | Unit | Unit and Integration Tests for Phase 05 AI FinOps & Cost Truth. | None (Pure In-Memory) | unit-and-ai-tests (Full Suite Floor) | PR / Push (main) | `COMPLEMENTARY` | R-LOGIC-03 | Bruno/07 — FinOps & Billing (01-06) | **`MOVED`** | Moved to unit/. Pricing matrix, cost attribution, and ledger unit tests. |
| `INT-005` | `CAT-017` | [`tests/integration/test_finops_endpoints.py`](file:///e:/JakeAI/backend/tests/integration/test_finops_endpoints.py) | 3 functions (`test_finops_endpoints_summary_and_budget` ...) | Gateway & Routing | Integration | REST API Contract and Integration Tests for AI FinOps Endpoints. | HTTP / ASGI | unit-and-ai-tests (Full Suite Floor) | PR / Push (main) | `PARTIAL OVERLAP` | R-FUNC-00 | Bruno/07 — FinOps & Billing (01-06) | **`MOVED`** | Moved to integration/. HTTP endpoints for FinOps budget, summary, and reconciliation. |
| `INT-002` | `CAT-018` | [`tests/integration/test_gateway.py`](file:///e:/JakeAI/backend/tests/integration/test_gateway.py) | 23 functions (`test_verify_valid_jwt` ...) | Gateway & Routing | Integration | Unit and integration tests for Gateway security, PEP, and SSE streaming. | Redis, HTTP / ASGI, Mocks / Monkeypatch | unit-and-ai-tests (Full Suite Floor) | PR / Push (main) | `COMPLEMENTARY` | R-FUNC-00 | Bruno/02 — Chat & Gateway (01-07) | **`MOVED`** | Moved to integration/. Gateway PEP security, auth, and SSE streaming integration. |
| `SEC-001` | `CAT-019` | [`tests/security/test_guardrails.py`](file:///e:/JakeAI/backend/tests/security/test_guardrails.py) | 6 functions (`test_input_guardrail_benign_prompts` ...) | Security & Governance | Security | Unit tests for the Guardrails Layer (Input, RBAC, PII, and Output shields). | None (Pure In-Memory) | unit-and-ai-tests (Full Suite Floor) | PR / Push (main) | `COMPLEMENTARY` | R-AI-02 / R-AI-03 | Bruno/08 — Security & Negative (01-11) | **`MOVED`** | Moved to security/. Guardrails, PII masking, and injection shield tests. |
| `UNIT-014` | `CAT-020` | [`tests/unit/test_harmonization.py`](file:///e:/JakeAI/backend/tests/unit/test_harmonization.py) | 5 functions (`test_singleton_harmonization` ...) | RAG Pipeline | Unit | Tests verifying cross-layer architectural harmonization and synchronization. | Mocks / Monkeypatch | unit-and-ai-tests (Full Suite Floor) | PR / Push (main) | `COMPLEMENTARY` | NONE | NONE | **`MOVED`** | Moved to unit/. Cross-layer singleton and synchronization unit tests. |
| `INT-003` | `CAT-021` | [`tests/integration/test_health.py`](file:///e:/JakeAI/backend/tests/integration/test_health.py) | 5 functions (`test_root_health_endpoint` ...) | Health & Diagnostics | Integration | Unit and integration tests for service health probes and OpenAPI schema. | HTTP / ASGI | unit-and-ai-tests (Full Suite Floor) | PR / Push (main) | `COMPLEMENTARY` | R-FUNC-00 | Bruno/00 — Setup & Environment (01-Health Smoke) | **`MOVED`** | Moved to integration/. Service health probes (`/health`, `/live`, `/ready`). |
| `UNIT-015` | `CAT-022` | [`tests/unit/test_local_provider.py`](file:///e:/JakeAI/backend/tests/unit/test_local_provider.py) | 7 functions (`test_local_model_capabilities_and_pricing` ...) | Core / Platform | Unit | Unit tests for COST-12: Local Model Provider Adapter and Health Probing. | HTTP / ASGI, Mocks / Monkeypatch | unit-and-ai-tests (Full Suite Floor) | PR / Push (main) | `COMPLEMENTARY` | R-FUNC-04 | NONE | **`MOVED`** | Moved to unit/. Local LLM adapter and health probing unit tests. |
| `UNIT-016` | `CAT-023` | [`tests/unit/test_multi_agent.py`](file:///e:/JakeAI/backend/tests/unit/test_multi_agent.py) | 12 functions (`test_supervisor_intent_classification` ...) | Agent Orchestration | Unit | Unit and integration tests for LangGraph multi-agent orchestration. | HTTP / ASGI, Mocks / Monkeypatch | unit-and-ai-tests (Full Suite Floor) | PR / Push (main) | `COMPLEMENTARY` | R-FUNC-01 / R-AI-00 / R-ARCH-00 | NONE | **`MOVED`** | Moved to unit/. Supervisor intent classification & routing unit tests. |
| `UNIT-017` | `CAT-024` | [`tests/unit/test_observability_and_tracing.py`](file:///e:/JakeAI/backend/tests/unit/test_observability_and_tracing.py) | 5 functions (`test_structured_telemetry_event_schema_and_redaction` ...) | Observability & Telemetry | Unit | Unit tests for Structured Telemetry, Prometheus Exposition, and W3C Distributed Tracing (TASK OPS-05, OPS-06, OPS-07, OPS-17). | HTTP / ASGI | unit-and-ai-tests (Full Suite Floor) | PR / Push (main) | `COMPLEMENTARY` | NONE | NONE | **`MOVED`** | Moved to unit/. Structured telemetry schemas and redaction tests. |
| `INT-004` | `CAT-025` | [`tests/integration/test_openai_compatibility.py`](file:///e:/JakeAI/backend/tests/integration/test_openai_compatibility.py) | 4 functions (`test_models_catalog_unauthenticated` ...) | Gateway & Routing | Integration | Tests for OpenAI-compatible API routes (/v1/models and /v1/chat/completions). | Mocks / Monkeypatch | unit-and-ai-tests (Full Suite Floor) | PR / Push (main) | `COMPLEMENTARY` | NONE | NONE | **`MOVED`** | Moved to integration/. OpenAI endpoint compatibility tests. |
| `UNIT-018` | `CAT-026` | [`tests/unit/test_orc_capabilities.py`](file:///e:/JakeAI/backend/tests/unit/test_orc_capabilities.py) | 4 functions (`test_orc_09_planner_memory_recall` ...) | Core / Platform | Unit | Targeted unit tests for AI Orchestration capabilities ORC-09, ORC-10, and ORC-11. | None (Pure In-Memory) | unit-and-ai-tests (Full Suite Floor) | PR / Push (main) | `COMPLEMENTARY` | NONE | NONE | **`MOVED`** | Moved to unit/. Episodic memory recall and dynamic model selection. |
| `CONTRACT-003` | `CAT-027` | [`tests/contract/test_orchestration_contracts.py`](file:///e:/JakeAI/backend/tests/contract/test_orchestration_contracts.py) | 12 functions (`TestTaskSpecContract::test_valid_task_spec` ...) | Agent Orchestration | Contract | Unit tests for canonical orchestration domain contracts and state machine. | None (Pure In-Memory) | unit-and-ai-tests (Full Suite Floor) | PR / Push (main) | `UNIQUE` | R-FUNC-01 / R-AI-00 / R-ARCH-00 | NONE | **`MOVED`** | Moved to contract/. Domain model contracts for TaskSpec, PlanStep, ExecutionPlan. |
| `UNIT-019` | `CAT-028` | [`tests/unit/test_orchestration_planner.py`](file:///e:/JakeAI/backend/tests/unit/test_orchestration_planner.py) | 4 functions (`TestOrchestrationPlanner::test_single_step_direct_question` ...) | Agent Orchestration | Unit | Unit tests for canonical BoundedPlanner, DAG generation, dependency resolution, and replanning. | None (Pure In-Memory) | unit-and-ai-tests (Full Suite Floor) | PR / Push (main) | `COMPLEMENTARY` | R-FUNC-01 / R-AI-00 / R-ARCH-00 | NONE | **`MOVED`** | Moved to unit/. BoundedPlanner DAG generation and replanning unit tests. |
| `E2E-002` | `CAT-029` | [`tests/e2e/test_phase07_production_hardening.py`](file:///e:/JakeAI/backend/tests/e2e/test_phase07_production_hardening.py) | 18 functions (`test_health_endpoints_backward_compatibility` ...) | RAG Pipeline | E2E | Production Hardening, API Contract, Streaming & Resilience Test Suite for Phase 07. | Redis, Qdrant, HTTP / ASGI, Mocks / Monkeypatch | unit-and-ai-tests (Full Suite Floor) | PR / Push (main) | `COMPLEMENTARY` | NONE | NONE | **`MOVED`** | Moved to e2e/. Production hardening, chaos resilience, and streaming E2E. |
| `UNIT-020` | `CAT-030` | [`tests/unit/test_prompt_compression_live.py`](file:///e:/JakeAI/backend/tests/unit/test_prompt_compression_live.py) | 7 functions (`test_context_selector_compress_document_chunks` ...) | RAG Pipeline | Unit | Tests for COST-06 and COST-07: Prompt Compression on Live Paths & Duplicate Compressor Consolidation. | Mocks / Monkeypatch | unit-and-ai-tests (Full Suite Floor) | PR / Push (main) | `COMPLEMENTARY` | NONE | NONE | **`MOVED`** | Moved to unit/. Prompt compression and context selector algorithm tests. |
| `UNIT-021` | `CAT-031` | [`tests/unit/test_provider_failover_credentials.py`](file:///e:/JakeAI/backend/tests/unit/test_provider_failover_credentials.py) | 3 functions (`test_failover_credentials_isolated_and_resolved_for_fallback` ...) | Core / Platform | Unit | Unit tests verifying provider failover credential isolation (COST-01 & COST-11). | HTTP / ASGI | unit-and-ai-tests (Full Suite Floor) | PR / Push (main) | `COMPLEMENTARY` | R-FUNC-04 | NONE | **`MOVED`** | Moved to unit/. Provider failover credential resolution unit tests. |
| `UNIT-022` | `CAT-032` | [`tests/unit/test_provider_foundation.py`](file:///e:/JakeAI/backend/tests/unit/test_provider_foundation.py) | 24 functions (`test_provider_protocol_conformance` ...) | Core / Platform | Unit | Comprehensive Unit and Contract Tests for Phase 01 — Provider Foundation. | HTTP / ASGI, Mocks / Monkeypatch | unit-and-ai-tests (Full Suite Floor) | PR / Push (main) | `COMPLEMENTARY` | R-FUNC-04 | NONE | **`MOVED`** | Moved to unit/. Provider protocol conformance and base client unit tests. |
| `UNIT-023` | `CAT-033` | [`tests/unit/test_provider_prompt_caching.py`](file:///e:/JakeAI/backend/tests/unit/test_provider_prompt_caching.py) | 10 functions (`test_provider_cache_policy_classification` ...) | Core / Platform | Unit | Comprehensive Unit and Contract Tests for Tier 5: Provider Prompt Caching. | Redis, Qdrant, HTTP / ASGI, Mocks / Monkeypatch | unit-and-ai-tests (Full Suite Floor) | PR / Push (main) | `COMPLEMENTARY` | R-FUNC-04 | NONE | **`MOVED`** | Moved to unit/. Provider cache policy classification and parameter checks. |
| `UNIT-048` | `CAT-034` | [`tests/unit/test_r_ai_00_agent_correctness.py`](file:///e:/JakeAI/backend/tests/unit/test_r_ai_00_agent_correctness.py) | 12 functions (`test_planner_paraphrased_financial_and_retrieval_decomposition` ...) | Agent Orchestration | Unit | Regression tests for R-AI-00 — Agent Correctness (AI evaluation and self-healing). | None (Pure In-Memory) | unit-and-ai-tests (Full Suite Floor) | PR / Push (main) | `COMPLEMENTARY` | R-AI-00 | NONE | **`MOVED`** | Moved to unit/. Authoritative RIGHT verification suite for R-AI-00. |
| `UNIT-049` | `CAT-035` | [`tests/unit/test_r_ai_01_rag_grounding.py`](file:///e:/JakeAI/backend/tests/unit/test_r_ai_01_rag_grounding.py) | 12 functions (`test_scenario_01_fully_supported_with_provenance_tracing` ...) | RAG Pipeline | Unit | Comprehensive verification test suite for R-AI-01: RAG Grounding. | Qdrant, HTTP / ASGI, Mocks / Monkeypatch | unit-and-ai-tests (Full Suite Floor) | PR / Push (main) | `COMPLEMENTARY` | R-AI-01 | NONE | **`MOVED`** | Moved to unit/. Authoritative RIGHT verification suite for R-AI-01. |
| `UNIT-050` | `CAT-036` | [`tests/unit/test_r_ai_02_hallucination_resistance.py`](file:///e:/JakeAI/backend/tests/unit/test_r_ai_02_hallucination_resistance.py) | 13 functions (`test_scenario_01_unknown_entity_impossible_facts` ...) | RAG Pipeline | Unit | Comprehensive verification test suite for R-AI-02: Hallucination Resistance. | Qdrant, HTTP / ASGI, Mocks / Monkeypatch | unit-and-ai-tests (Full Suite Floor) | PR / Push (main) | `COMPLEMENTARY` | R-AI-02 | NONE | **`MOVED`** | Moved to unit/. Authoritative RIGHT verification suite for R-AI-02. |
| `UNIT-051` | `CAT-037` | [`tests/unit/test_r_ai_03_tool_correctness.py`](file:///e:/JakeAI/backend/tests/unit/test_r_ai_03_tool_correctness.py) | 16 functions (`test_scenario_01_semantic_paraphrases_and_synonyms_tool_choice` ...) | Core / Platform | Unit | Comprehensive verification test suite for R-AI-03: Tool Correctness. | HTTP / ASGI | unit-and-ai-tests (Full Suite Floor) | PR / Push (main) | `COMPLEMENTARY` | R-AI-03 | NONE | **`MOVED`** | Moved to unit/. Authoritative RIGHT verification suite for R-AI-03. |
| `UNIT-052` | `CAT-038` | [`tests/unit/test_r_ai_04_context_correctness.py`](file:///e:/JakeAI/backend/tests/unit/test_r_ai_04_context_correctness.py) | 19 functions (`test_scenario_01_canonical_6_stage_ordering` ...) | RAG Pipeline | Unit | Comprehensive verification test suite for R-AI-04: Context Correctness. | HTTP / ASGI, Mocks / Monkeypatch | unit-and-ai-tests (Full Suite Floor) | PR / Push (main) | `COMPLEMENTARY` | R-AI-04 | NONE | **`MOVED`** | Moved to unit/. Authoritative RIGHT verification suite for R-AI-04. |
| `UNIT-039` | `CAT-039` | [`tests/unit/test_r_arch_00_architecture_integrity.py`](file:///e:/JakeAI/backend/tests/unit/test_r_arch_00_architecture_integrity.py) | 11 functions (`test_no_module_level_import_cycles_in_app_package` ...) | Core / Platform | Unit | R-ARCH-00 — Architecture Integrity regression suite. | HTTP / ASGI, Mocks / Monkeypatch | unit-and-ai-tests (Full Suite Floor) | PR / Push (main) | `COMPLEMENTARY` | R-ARCH-00 | NONE | **`MOVED`** | Moved to unit/. Authoritative RIGHT verification suite for R-ARCH-00. |
| `UNIT-040` | `CAT-040` | [`tests/unit/test_r_arch_01_canonical_authority.py`](file:///e:/JakeAI/backend/tests/unit/test_r_arch_01_canonical_authority.py) | 13 functions (`test_capability_patterns_defined_exactly_once` ...) | Core / Platform | Unit | R-ARCH-01 — Canonical Authority regression suite. | None (Pure In-Memory) | unit-and-ai-tests (Full Suite Floor) | PR / Push (main) | `COMPLEMENTARY` | R-ARCH-01 | NONE | **`MOVED`** | Moved to unit/. Authoritative RIGHT verification suite for R-ARCH-01. |
| `UNIT-041` | `CAT-041` | [`tests/unit/test_r_arch_02_dependency_boundaries.py`](file:///e:/JakeAI/backend/tests/unit/test_r_arch_02_dependency_boundaries.py) | 12 functions (`test_agent_domain_never_depends_on_langgraph_adapter_or_frameworks` ...) | Core / Platform | Unit | R-ARCH-02 — Dependency Boundaries regression suite. | HTTP / ASGI, Mocks / Monkeypatch | unit-and-ai-tests (Full Suite Floor) | PR / Push (main) | `COMPLEMENTARY` | R-ARCH-02 | NONE | **`MOVED`** | Moved to unit/. Authoritative RIGHT verification suite for R-ARCH-02. |
| `UNIT-042` | `CAT-042` | [`tests/unit/test_r_arch_03_duplicate_abstractions.py`](file:///e:/JakeAI/backend/tests/unit/test_r_arch_03_duplicate_abstractions.py) | 17 functions (`test_workflow_engine_package_removed` ...) | Core / Platform | Unit | R-ARCH-03 — Duplicate Abstractions regression suite. | Redis, Mocks / Monkeypatch | unit-and-ai-tests (Full Suite Floor) | PR / Push (main) | `COMPLEMENTARY` | R-ARCH-03 | NONE | **`MOVED`** | Moved to unit/. Authoritative RIGHT verification suite for R-ARCH-03. |
| `CONTRACT-005` | `CAT-043` | [`tests/contract/test_r_arch_04_contract_consistency.py`](file:///e:/JakeAI/backend/tests/contract/test_r_arch_04_contract_consistency.py) | 13 functions (`test_domain_plan_step_first_class_tool_attributes` ...) | Contract & Schema | Contract | R-ARCH-04 — Contract Consistency Regression Test Suite. | None (Pure In-Memory) | unit-and-ai-tests (Full Suite Floor) | PR / Push (main) | `COMPLEMENTARY` | R-ARCH-04 | NONE | **`MOVED`** | Moved to contract/. Authoritative RIGHT verification suite for R-ARCH-04. |
| `INT-012` | `CAT-044` | [`tests/integration/test_r_func_00_api_behavior.py`](file:///e:/JakeAI/backend/tests/integration/test_r_func_00_api_behavior.py) | 29 functions (`test_all_51_endpoints_accounted_in_openapi` ...) | Core / Platform | Integration | R-FUNC-00 - Comprehensive HTTP API Boundary Verification Test Suite. | Redis, HTTP / ASGI, Mocks / Monkeypatch | unit-and-ai-tests (Full Suite Floor) | PR / Push (main) | `COMPLEMENTARY` | R-FUNC-00 | NONE | **`MOVED`** | Moved to integration/. Authoritative RIGHT verification suite for R-FUNC-00. |
| `INT-013` | `CAT-045` | [`tests/integration/test_r_func_01_agent_behavior.py`](file:///e:/JakeAI/backend/tests/integration/test_r_func_01_agent_behavior.py) | 12 functions (`test_scenario_01_simple_task_lifecycle` ...) | Agent Orchestration | Integration | R-FUNC-01 — Agent Behavior Canonical Verification Test Suite. | HTTP / ASGI | unit-and-ai-tests (Full Suite Floor) | PR / Push (main) | `COMPLEMENTARY` | R-FUNC-01 | Bruno/03 — Agent (01-10) | **`MOVED`** | Moved to integration/. Authoritative RIGHT verification suite for R-FUNC-01. |
| `INT-014` | `CAT-046` | [`tests/integration/test_r_func_02_rag_behavior.py`](file:///e:/JakeAI/backend/tests/integration/test_r_func_02_rag_behavior.py) | 14 functions (`test_scenario_01_txt_document_full_path` ...) | RAG Pipeline | Integration | Comprehensive verification test suite for R-FUNC-02: RAG Behavior. | Qdrant, HTTP / ASGI, Mocks / Monkeypatch | unit-and-ai-tests (Full Suite Floor) | PR / Push (main) | `COMPLEMENTARY` | R-FUNC-02 | Bruno/04 — RAG (01-07) | **`MOVED`** | Moved to integration/. Authoritative RIGHT verification suite for R-FUNC-02. |
| `INT-015` | `CAT-047` | [`tests/integration/test_r_func_03_cache_behavior.py`](file:///e:/JakeAI/backend/tests/integration/test_r_func_03_cache_behavior.py) | 25 functions (`test_scenario_01_exact_cache_miss_set_hit_lifecycle` ...) | RAG Pipeline | Integration | Comprehensive verification test suite for R-FUNC-03: Cache Behavior. | Redis, Qdrant, HTTP / ASGI, Mocks / Monkeypatch | unit-and-ai-tests (Full Suite Floor) | PR / Push (main) | `COMPLEMENTARY` | R-FUNC-03 | Bruno/06 — Cache (01-06) | **`MOVED`** | Moved to integration/. Authoritative RIGHT verification suite for R-FUNC-03. |
| `INT-016` | `CAT-048` | [`tests/integration/test_r_func_04_provider_behavior.py`](file:///e:/JakeAI/backend/tests/integration/test_r_func_04_provider_behavior.py) | 17 functions (`test_dispatch_invokes_selected_provider_and_model_on_the_wire` ...) | Core / Platform | Integration | R-FUNC-04 — Provider Behavior verification suite. | HTTP / ASGI, Mocks / Monkeypatch | unit-and-ai-tests (Full Suite Floor) | PR / Push (main) | `COMPLEMENTARY` | R-FUNC-04 | NONE | **`MOVED`** | Moved to integration/. Authoritative RIGHT verification suite for R-FUNC-04. |
| `UNIT-043` | `CAT-049` | [`tests/unit/test_r_logic_00_invariants.py`](file:///e:/JakeAI/backend/tests/unit/test_r_logic_00_invariants.py) | 30 functions (`test_inv_a1_cancel_of_terminal_run_preserves_terminal_state` ...) | RAG Pipeline | Unit | R-LOGIC-00 — Invariants Verification Test Suite. | Redis, Qdrant, HTTP / ASGI, Mocks / Monkeypatch | unit-and-ai-tests (Full Suite Floor) | PR / Push (main) | `COMPLEMENTARY` | R-LOGIC-00 | NONE | **`MOVED`** | Moved to unit/. Authoritative RIGHT verification suite for R-LOGIC-00. |
| `UNIT-044` | `CAT-050` | [`tests/unit/test_r_logic_01_state_transitions.py`](file:///e:/JakeAI/backend/tests/unit/test_r_logic_01_state_transitions.py) | 24 functions (`test_run_matrix_is_complete_and_closed` ...) | Core / Platform | Unit | R-LOGIC-01 — State Transitions Verification Test Suite. | HTTP / ASGI, Mocks / Monkeypatch | unit-and-ai-tests (Full Suite Floor) | PR / Push (main) | `COMPLEMENTARY` | R-LOGIC-01 | NONE | **`MOVED`** | Moved to unit/. Authoritative RIGHT verification suite for R-LOGIC-01. |
| `UNIT-045` | `CAT-051` | [`tests/unit/test_r_logic_02_data_flow.py`](file:///e:/JakeAI/backend/tests/unit/test_r_logic_02_data_flow.py) | 15 functions (`test_http_run_carries_request_identity` ...) | Core / Platform | Unit | R-LOGIC-02 — Data Flow Verification Test Suite. | HTTP / ASGI, Mocks / Monkeypatch | unit-and-ai-tests (Full Suite Floor) | PR / Push (main) | `COMPLEMENTARY` | R-LOGIC-02 | NONE | **`MOVED`** | Moved to unit/. Authoritative RIGHT verification suite for R-LOGIC-02. |
| `UNIT-046` | `CAT-052` | [`tests/unit/test_r_logic_03_accounting.py`](file:///e:/JakeAI/backend/tests/unit/test_r_logic_03_accounting.py) | 23 functions (`test_zero_token_request_reports_no_false_savings` ...) | FinOps & Billing | Unit | R-LOGIC-03 — Accounting regression tests. | Redis, HTTP / ASGI, Mocks / Monkeypatch | unit-and-ai-tests (Full Suite Floor) | PR / Push (main) | `COMPLEMENTARY` | R-LOGIC-03 | NONE | **`MOVED`** | Moved to unit/. Authoritative RIGHT verification suite for R-LOGIC-03. |
| `UNIT-047` | `CAT-053` | [`tests/unit/test_r_logic_04_failure_handling.py`](file:///e:/JakeAI/backend/tests/unit/test_r_logic_04_failure_handling.py) | 27 functions (`test_status_matrix_retry_vs_failover_at_failover_boundary` ...) | RAG Pipeline | Unit | R-LOGIC-04 — Failure Handling canonical verification test suite. | Redis, Mocks / Monkeypatch | unit-and-ai-tests (Full Suite Floor) | PR / Push (main) | `COMPLEMENTARY` | R-LOGIC-04 | NONE | **`MOVED`** | Moved to unit/. Authoritative RIGHT verification suite for R-LOGIC-04. |
| `UNIT-024` | `CAT-054` | [`tests/unit/test_rag.py`](file:///e:/JakeAI/backend/tests/unit/test_rag.py) | 16 functions (`test_bm25_retriever_search_and_tenant_isolation` ...) | RAG Pipeline | Unit | Unit and integration tests for RAG engine, hybrid retrieval, and Self-RAG loop. | Qdrant, HTTP / ASGI, Mocks / Monkeypatch | unit-and-ai-tests (Full Suite Floor) | PR / Push (main) | `COMPLEMENTARY` | R-FUNC-02 / R-AI-01 | Bruno/04 — RAG (01-07) | **`MOVED`** | Moved to unit/. RAG ingestion, chunking, and self-RAG verification. |
| `UNIT-025` | `CAT-055` | [`tests/unit/test_rag_bm25_persistence.py`](file:///e:/JakeAI/backend/tests/unit/test_rag_bm25_persistence.py) | 2 functions (`test_bm25_reindex_idf_repair` ...) | RAG Pipeline | Unit | Unit tests for TASK RAG-05: BM25 Re-indexing IDF Repair and Disk Persistence. | None (Pure In-Memory) | unit-and-ai-tests (Full Suite Floor) | PR / Push (main) | `PARTIAL OVERLAP` | R-FUNC-02 / R-AI-01 | NONE | **`MOVED`** | Moved to unit/. BM25 re-index IDF repair and disk persistence unit tests. |
| `UNIT-026` | `CAT-056` | [`tests/unit/test_rag_context_budget.py`](file:///e:/JakeAI/backend/tests/unit/test_rag_context_budget.py) | 2 functions (`test_no_score_leakage_in_formatted_context` ...) | RAG Pipeline | Unit | Unit tests for TASK RAG-08: BPETokenizer Full Envelope Budgeting and Score Leakage Elimination. | None (Pure In-Memory) | unit-and-ai-tests (Full Suite Floor) | PR / Push (main) | `PARTIAL OVERLAP` | R-FUNC-02 / R-AI-01 | NONE | **`MOVED`** | Moved to unit/. Tokenizer context budgeting and score leakage elimination. |
| `UNIT-027` | `CAT-057` | [`tests/unit/test_rag_embedding_and_points.py`](file:///e:/JakeAI/backend/tests/unit/test_rag_embedding_and_points.py) | 7 functions (`test_fastembed_provider_dimension_and_norm` ...) | RAG Pipeline | Unit | Unit tests for TASK RAG-03 and RAG-04: Real Embeddings, Dimension Verification, and Deterministic Points. | Qdrant | unit-and-ai-tests (Full Suite Floor) | PR / Push (main) | `COMPLEMENTARY` | R-FUNC-02 / R-AI-01 | NONE | **`MOVED`** | Moved to unit/. FastEmbed dimension verification and deterministic UUIDv5 points. |
| `UNIT-028` | `CAT-058` | [`tests/unit/test_rag_grounding_and_abstention.py`](file:///e:/JakeAI/backend/tests/unit/test_rag_grounding_and_abstention.py) | 6 functions (`test_grounding_verifier_claim_classification` ...) | RAG Pipeline | Unit | Unit tests for TASK RAG-09, 10, 11: Grounding, Verifiable Citations, and Explicit Abstention. | Mocks / Monkeypatch | unit-and-ai-tests (Full Suite Floor) | PR / Push (main) | `COMPLEMENTARY` | R-FUNC-02 / R-AI-01 | NONE | **`MOVED`** | Moved to unit/. Claim classification, citation generator, and abstention unit tests. |
| `UNIT-029` | `CAT-059` | [`tests/unit/test_rag_hybrid_retrieval.py`](file:///e:/JakeAI/backend/tests/unit/test_rag_hybrid_retrieval.py) | 3 functions (`test_hybrid_retrieval_concurrent_success` ...) | RAG Pipeline | Unit | Unit tests for TASK RAG-06: Concurrency, Degraded Mode, 3x Candidate Pool, and Deterministic Tie-Breaking. | Qdrant | unit-and-ai-tests (Full Suite Floor) | PR / Push (main) | `PARTIAL OVERLAP` | R-FUNC-02 / R-AI-01 | NONE | **`MOVED`** | Moved to unit/. Hybrid retrieval degraded mode and tie-breaking unit tests. |
| `UNIT-030` | `CAT-060` | [`tests/unit/test_rag_normalization.py`](file:///e:/JakeAI/backend/tests/unit/test_rag_normalization.py) | 4 functions (`test_unicode_nfkc_normalization` ...) | RAG Pipeline | Unit | Unit tests for TASK RAG-02: Unicode NFKC and text normalization. | None (Pure In-Memory) | unit-and-ai-tests (Full Suite Floor) | PR / Push (main) | `COMPLEMENTARY` | R-FUNC-02 / R-AI-01 | NONE | **`MOVED`** | Moved to unit/. High-value unit tests for NFKC unicode and MIME parsing. |
| `UNIT-031` | `CAT-061` | [`tests/unit/test_rag_parsers.py`](file:///e:/JakeAI/backend/tests/unit/test_rag_parsers.py) | 8 functions (`test_plain_text_parser` ...) | RAG Pipeline | Unit | Unit tests for RAG document parsers (PlainText, Markdown, PDF) and MIME validation. | Qdrant, Mocks / Monkeypatch | unit-and-ai-tests (Full Suite Floor) | PR / Push (main) | `COMPLEMENTARY` | R-FUNC-02 / R-AI-01 | NONE | **`MOVED`** | Moved to unit/. Document parser unit tests (MD, PDF, TXT) and MIME validation. |
| `UNIT-032` | `CAT-062` | [`tests/unit/test_rag_reranker.py`](file:///e:/JakeAI/backend/tests/unit/test_rag_reranker.py) | 3 functions (`test_reranker_telemetry_and_custom_fn` ...) | RAG Pipeline | Unit | Unit tests for TASK RAG-07: Cross-Encoder Reranking, Telemetry, and Heuristic Fallback. | None (Pure In-Memory) | unit-and-ai-tests (Full Suite Floor) | PR / Push (main) | `PARTIAL OVERLAP` | R-FUNC-02 / R-AI-01 | NONE | **`MOVED`** | Moved to unit/. Cross-encoder fallback and telemetry unit tests. |
| `SEC-004` | `CAT-063` | [`tests/security/test_rag_tenant_isolation.py`](file:///e:/JakeAI/backend/tests/security/test_rag_tenant_isolation.py) | 6 functions (`test_bm25_strict_tenant_isolation` ...) | RAG Pipeline | Security | Comprehensive Multi-Tenant Isolation Test Suite for JakeAI RAG Platform. | Qdrant | unit-and-ai-tests (Full Suite Floor) | PR / Push (main) | `COMPLEMENTARY` | R-FUNC-02 / R-AI-01 | NONE | **`MOVED`** | Moved to security/. Multi-tenant RAG isolation tests (dense & sparse). |
| `SEC-005` | `CAT-064` | [`tests/security/test_rag_tenant_isolation_hardened.py`](file:///e:/JakeAI/backend/tests/security/test_rag_tenant_isolation_hardened.py) | 4 functions (`test_tenant_isolation_in_ingestion_and_hybrid_retrieval` ...) | RAG Pipeline | Security | Unit tests for TASK RAG-13: Hardened Multi-Tenant Isolation Defense-in-Depth. | Qdrant | unit-and-ai-tests (Full Suite Floor) | PR / Push (main) | `COMPLEMENTARY` | R-FUNC-02 / R-AI-01 | NONE | **`MOVED`** | Moved to security/. Defense-in-depth tenant isolation checks. |
| `UNIT-033` | `CAT-065` | [`tests/unit/test_rag_unified_envelope.py`](file:///e:/JakeAI/backend/tests/unit/test_rag_unified_envelope.py) | 3 functions (`test_context_envelope_canonical_ordering` ...) | RAG Pipeline | Unit | Unit tests for TASK RAG-12: Unified 6-stage Context Envelope and Token Budgeting. | None (Pure In-Memory) | unit-and-ai-tests (Full Suite Floor) | PR / Push (main) | `COMPLEMENTARY` | R-FUNC-02 / R-AI-01 | NONE | **`MOVED`** | Moved to unit/. 6-stage context envelope canonical ordering unit tests. |
| `INT-007` | `CAT-066` | [`tests/integration/test_resume_bridge.py`](file:///e:/JakeAI/backend/tests/integration/test_resume_bridge.py) | 7 functions (`test_resume_bridge_manager_lifecycle` ...) | Agent Orchestration | Integration | Unit and integration tests for ADR-001 LangGraph interrupt checkpoint and resume bridge. | Redis, Mocks / Monkeypatch | unit-and-ai-tests (Full Suite Floor) | PR / Push (main) | `COMPLEMENTARY` | NONE | NONE | **`MOVED`** | Moved to integration/. ADR-001 interrupt checkpoint and Redis resume bridge. |
| `OBSOLETE-001` | `CAT-067` | `tests/test_semantic_cache.py` | 4 functions (`test_exact_match_cache_hit_and_miss` ...) | Token Optimization & Caching | Unit | Unit tests for Multi-Tier Semantic Cache (Exact & Vector Cosine Similarity). | None (Pure In-Memory) | unit-and-ai-tests (Full Suite Floor) | PR / Push (main) | `OBSOLETE` | R-FUNC-03 / R-AI-02 | NONE | **`DELETED`** | Deleted. Used obsolete 128-d mock vectors and mock Redis. Superseded by test_semantic_cache_real.py and test_r_func_03_cache_behavior.py. |
| `INT-011` | `CAT-068` | [`tests/integration/test_semantic_cache_real.py`](file:///e:/JakeAI/backend/tests/integration/test_semantic_cache_real.py) | 6 functions (`test_real_embedding_dense_semantic_matching` ...) | RAG Pipeline | Integration | Comprehensive unit and integration tests for COST-08: True Vector Semantic Cache. | Qdrant, Mocks / Monkeypatch | unit-and-ai-tests (Full Suite Floor) | PR / Push (main) | `COMPLEMENTARY` | R-FUNC-03 / R-AI-02 | NONE | **`MOVED`** | Moved to integration/. Exercises real Qdrant/FastEmbed caching and tenant boundaries. |
| `UNIT-034` | `CAT-069` | [`tests/unit/test_structured_output.py`](file:///e:/JakeAI/backend/tests/unit/test_structured_output.py) | 18 functions (`test_case_1_raw_json_object` ...) | Core / Platform | Unit | Unit tests for canonical structured output parsing utility (WORK-01-CI-FIX-05). | None (Pure In-Memory) | unit-and-ai-tests (Full Suite Floor) | PR / Push (main) | `COMPLEMENTARY` | NONE | NONE | **`MOVED`** | Moved to unit/. Canonical structured output parsing utility unit tests. |
| `UNIT-035` | `CAT-070` | [`tests/unit/test_two_zone_compiler.py`](file:///e:/JakeAI/backend/tests/unit/test_two_zone_compiler.py) | 7 functions (`test_two_zone_compiler_separation` ...) | Token Optimization & Caching | Unit | Unit tests for TwoZonePromptCompiler (Tier 5: Provider Prompt Caching). | None (Pure In-Memory) | unit-and-ai-tests (Full Suite Floor) | PR / Push (main) | `COMPLEMENTARY` | R-FUNC-03 / R-AI-02 | NONE | **`MOVED`** | Moved to unit/. TwoZonePromptCompiler prefix caching unit tests. |
| `UNIT-036` | `CAT-071` | [`tests/unit/test_unified_quota_authority.py`](file:///e:/JakeAI/backend/tests/unit/test_unified_quota_authority.py) | 3 functions (`test_quota_manager_delegates_to_finops_budget_manager` ...) | FinOps & Billing | Unit | Unit tests for TASK COST-05: Unified Quota & Budget Authority. | None (Pure In-Memory) | unit-and-ai-tests (Full Suite Floor) | PR / Push (main) | `PARTIAL OVERLAP` | NONE | NONE | **`MOVED`** | Moved to unit/. QuotaManager delegation to FinOpsBudgetManager. |
| `UNIT-037` | `CAT-072` | [`tests/unit/test_verifier_invariants.py`](file:///e:/JakeAI/backend/tests/unit/test_verifier_invariants.py) | 5 functions (`test_verifier_tenant_mismatch_at_revision_0` ...) | RAG Pipeline | Unit | Regression tests for Verifier invariant guarantees (TASK ORC-01). | Mocks / Monkeypatch | unit-and-ai-tests (Full Suite Floor) | PR / Push (main) | `PARTIAL OVERLAP` | R-ARCH-00 / R-LOGIC-00 | NONE | **`MOVED`** | Moved to unit/. Verifier_node revision limits and tenant rejection invariants. |
| `UNIT-038` | `CAT-073` | [`tests/unit/test_workload_classification_routing.py`](file:///e:/JakeAI/backend/tests/unit/test_workload_classification_routing.py) | 12 functions (`test_workload_classifier_simple_chat` ...) | Core / Platform | Unit | Comprehensive test suite for COST-09 (Workload Classification), COST-10 (Intelligent Model Routing), and COST-13 (Optimization Telemetry). | None (Pure In-Memory) | unit-and-ai-tests (Full Suite Floor) | PR / Push (main) | `COMPLEMENTARY` | NONE | NONE | **`MOVED`** | Moved to unit/. Workload classification and intelligent model routing unit tests. |
| `CONTRACT-001` | `CAT-074` | [`tests/contract/test_api_contract.py`](file:///e:/JakeAI/backend/tests/contract/test_api_contract.py) | 16 functions (66 items: `test_exact_51_public_operations_accounted`, `test_zero_schema_drift_runtime_vs_committed` ...) | Contract & Schema | Contract | Authoritative API Contract and Zero Schema Drift verification suite auditing all 51 operations across 47 paths against OpenAPI 3.1.0 specification. | None (Pure In-Memory) | API Breaking Change & Schema Drift Gate | PR / Push (main) | `UNIQUE` | R-ARCH-04 / R-FUNC-00 | Bruno Collections (00-08) | **`EXPANDED`** | Expanded in contract/. Exhaustive 51-operation contract, bidirectional zero-drift diff, request body, parameter, auth, and breaking change prevention. |
| `CONTRACT-002` | `CAT-075` | [`tests/contract/test_internal_mutual_auth.py`](file:///e:/JakeAI/backend/tests/contract/test_internal_mutual_auth.py) | 4 functions (`test_perimeter_auth_rejects_missing_or_spoofed_headers` ...) | Security & Governance | Contract | Internal Mutual Auth Contract Test Suite (Invariant 4). | None (Pure In-Memory) | Internal Mutual Auth Contract Gate | PR / Push (main) | `UNIQUE` | R-ARCH-04 | Bruno/08 — Security & Negative (01-11) | **`PRESERVED`** | Preserved in contract/. Perimeter auth and internal mutual auth gate. |
| `AI-001` | `CAT-076` | [`tests/evals/test_baseline_and_regression_gate.py`](file:///e:/JakeAI/backend/tests/evals/test_baseline_and_regression_gate.py) | 4 functions (`test_baseline_store_load_and_save` ...) | AI Evaluation & Benchmarking | AI Eval / Benchmark | Unit tests for Baseline Store and Live Benchmark Regression Gate (TASK OPS-15 & OPS-16). | None (Pure In-Memory) | LLMOps Safety & Canary Data Leakage Gate | PR / Push (main) | `UNIQUE` | NONE | NONE | **`PRESERVED`** | Preserved in evals/. Baseline store and regression gate tests. |
| `AI-002` | `CAT-077` | [`tests/evals/test_canary_leakage.py`](file:///e:/JakeAI/backend/tests/evals/test_canary_leakage.py) | 5 functions (`test_rag_tenant_isolation_canary_leakage` ...) | RAG Pipeline | AI Eval / Benchmark | Comprehensive Canary Data Leakage and Secret Sanitization Tests (TASK OPS-13 & OPS-14). | None (Pure In-Memory) | LLMOps Safety & Canary Data Leakage Gate | PR / Push (main) | `UNIQUE` | NONE | NONE | **`PRESERVED`** | Preserved in evals/. Canary data leakage and secret sanitization tests. |
| `AI-003` | `CAT-078` | [`tests/evals/test_coding_intelligence_regression.py`](file:///e:/JakeAI/backend/tests/evals/test_coding_intelligence_regression.py) | 5 functions (`test_task_a_bug_fix_preserves_implementation` ...) | AI Evaluation & Benchmarking | AI Eval / Benchmark | Golden Dataset Coding Agent Regression & Intelligence Preservation Suite. | None (Pure In-Memory) | unit-and-ai-tests (Full Suite Floor) | PR / Push (main) | `UNIQUE` | NONE | NONE | **`PRESERVED`** | Preserved in evals/. Coding agent regression and intelligence preservation. |
| `AI-004` | `CAT-079` | [`tests/evals/test_llm_judge_and_generation.py`](file:///e:/JakeAI/backend/tests/evals/test_llm_judge_and_generation.py) | 3 functions (`test_llm_judge_heuristic_rubric_fallback` ...) | AI Evaluation & Benchmarking | AI Eval / Benchmark | Unit tests for Real LLM Judge and Actual Model Generation Evaluation (TASK OPS-09 & OPS-10). | Mocks / Monkeypatch | LLMOps Safety & Canary Data Leakage Gate | PR / Push (main) | `UNIQUE` | NONE | NONE | **`PRESERVED`** | Preserved in evals/. LLM judge evaluator and model generation evaluation. |
| `AI-005` | `CAT-080` | [`tests/evals/test_phase03_token_optimization.py`](file:///e:/JakeAI/backend/tests/evals/test_phase03_token_optimization.py) | 13 functions (`test_layer1_exact_cache_metrics_and_accounting` ...) | AI Evaluation & Benchmarking | AI Eval / Benchmark | Phase 03 Token Optimization Comprehensive Verification Suite. | None (Pure In-Memory) | unit-and-ai-tests (Full Suite Floor) | PR / Push (main) | `UNIQUE` | NONE | NONE | **`PRESERVED`** | Preserved in evals/. Multi-layer token optimization verification suite. |
| `AI-006` | `CAT-081` | [`tests/evals/test_phase06_evaluation.py`](file:///e:/JakeAI/backend/tests/evals/test_phase06_evaluation.py) | 13 functions (`test_rubric_evaluator_all_dimensions_positive` ...) | AI Evaluation & Benchmarking | AI Eval / Benchmark | Comprehensive Phase 06 AI Quality Evaluation & Regression Test Suite. | None (Pure In-Memory) | unit-and-ai-tests (Full Suite Floor) | PR / Push (main) | `UNIQUE` | NONE | NONE | **`PRESERVED`** | Preserved in evals/. AI quality evaluation and rubric evaluator tests. |
| `AI-007` | `CAT-082` | [`tests/evals/test_portfolio_benchmark.py`](file:///e:/JakeAI/backend/tests/evals/test_portfolio_benchmark.py) | 2 functions (`test_phase_00_portfolio_benchmark_all_workloads` ...) | AI Evaluation & Benchmarking | AI Eval / Benchmark | Phase 00 Portfolio AI Evaluation Benchmark & Regression Test Suite. | None (Pure In-Memory) | Phase 00 AI Evaluation Benchmark Gate | PR / Push (main) | `UNIQUE` | NONE | NONE | **`PRESERVED`** | Preserved in evals/. Portfolio benchmark CI gate (>= 40% reduction). |
| `PERF-001` | `CAT-083` | [`tests/performance/test_prompt_cache_benchmark.py`](file:///e:/JakeAI/backend/tests/performance/test_prompt_cache_benchmark.py) | 1 functions (`test_empirical_prompt_cache_benchmark` ...) | Token Optimization & Caching | Performance | Empirical Provider Prompt Cache Benchmark Suite (Tier 5). | None (Pure In-Memory) | unit-and-ai-tests (Full Suite Floor) | PR / Push (main) | `UNIQUE` | R-FUNC-03 / R-AI-02 | NONE | **`MOVED`** | Moved to performance/. Provider prompt cache empirical benchmark. |
| `AI-008` | `CAT-084` | [`tests/evals/test_rag_context_efficiency.py`](file:///e:/JakeAI/backend/tests/evals/test_rag_context_efficiency.py) | 4 functions (`test_context_selector_efficiency_and_redundancy_elimination` ...) | RAG Pipeline | AI Eval / Benchmark | RAG Context Efficiency & Quality Evaluation Benchmark Suite. | None (Pure In-Memory) | unit-and-ai-tests (Full Suite Floor) | PR / Push (main) | `UNIQUE` | R-FUNC-02 / R-AI-01 | NONE | **`PRESERVED`** | Preserved in evals/. ContextSelector token reduction and redundancy elimination. |
| `AI-009` | `CAT-085` | [`tests/evals/test_rag_eval.py`](file:///e:/JakeAI/backend/tests/evals/test_rag_eval.py) | 1 functions (`test_rag_golden_dataset_evaluation` ...) | RAG Pipeline | AI Eval / Benchmark | AI RAG Regression and Evaluation Test Suite using Golden Dataset Stub. | None (Pure In-Memory) | unit-and-ai-tests (Full Suite Floor) | PR / Push (main) | `UNIQUE` | R-FUNC-02 / R-AI-01 | NONE | **`PRESERVED`** | Preserved in evals/. Golden dataset RAG evaluation benchmark. |
| `AI-010` | `CAT-086` | [`tests/evals/test_rag_metrics.py`](file:///e:/JakeAI/backend/tests/evals/test_rag_metrics.py) | 5 functions (`test_retrieval_metrics_individual` ...) | RAG Pipeline | AI Eval / Benchmark | Unit tests for RAG Retrieval Metrics and Groundedness Evaluation Engines (TASK OPS-08 & OPS-11). | None (Pure In-Memory) | LLMOps Safety & Canary Data Leakage Gate | PR / Push (main) | `UNIQUE` | R-FUNC-02 / R-AI-01 | NONE | **`PRESERVED`** | Preserved in evals/. RAG retrieval and groundedness evaluation metrics. |
| `AI-011` | `CAT-087` | [`tests/evals/test_rag_regression.py`](file:///e:/JakeAI/backend/tests/evals/test_rag_regression.py) | 1 functions (`test_rag_quality_gate` ...) | RAG Pipeline | AI Eval / Benchmark | Dedicated RAG Regression Testing Gate (Block 5). | None (Pure In-Memory) | RAG Quality Gate & Anti-Hallucination Regression | PR / Push (main) | `UNIQUE` | R-FUNC-02 / R-AI-01 | NONE | **`PRESERVED`** | Preserved in evals/. Dedicated RAG quality regression testing gate. |
| `PERF-002` | `CAT-088` | [`tests/performance/test_token_benchmark.py`](file:///e:/JakeAI/backend/tests/performance/test_token_benchmark.py) | 3 functions (`test_heuristic_token_pruner_compression_and_fact_retention` ...) | AI Evaluation & Benchmarking | Performance | Empirical Benchmark & Token Accounting Verification Suite. | None (Pure In-Memory) | Token Optimization Benchmark Gate | PR / Push (main) | `UNIQUE` | NONE | NONE | **`MOVED`** | Moved to performance/. Empirical token reduction benchmark gate (>= 40%). |
| `UNIT-001` | `CAT-089` | [`tests/unit/test_bpe_tokenizer.py`](file:///e:/JakeAI/backend/tests/unit/test_bpe_tokenizer.py) | 7 functions (`test_bpe_tokenizer_initialization` ...) | Token Optimization & Caching | Unit | Unit tests for Tier 7 BPE Tokenizer Engine and Token Budgeting. | Mocks / Monkeypatch | unit-and-ai-tests (Full Suite Floor) | PR / Push (main) | `COMPLEMENTARY` | NONE | NONE | **`PRESERVED`** | Preserved in unit/. Tiktoken BPE tokenizer engine unit tests. |
| `UNIT-002` | `CAT-090` | [`tests/unit/test_cache_identity.py`](file:///e:/JakeAI/backend/tests/unit/test_cache_identity.py) | 34 functions (`TestComputeCacheIdentity::test_same_request_same_identity` ...) | Token Optimization & Caching | Unit | REPAIR-00 — CACHE-01: Exact Cache Identity Regression Tests. | Mocks / Monkeypatch | unit-and-ai-tests (Full Suite Floor) | PR / Push (main) | `COMPLEMENTARY` | R-FUNC-03 / R-AI-02 | NONE | **`PRESERVED`** | Preserved in unit/. Exact cache identity hashing regression suite. |
| `UNIT-003` | `CAT-091` | [`tests/unit/test_canonical_provider_resolution.py`](file:///e:/JakeAI/backend/tests/unit/test_canonical_provider_resolution.py) | 8 functions (`TestAuthoritativeRegistryResolution::test_registry_resolves_required_providers` ...) | Core / Platform | Unit | REPAIR-03 — DUP-02: Canonical Provider Resolution Regression Tests. | Mocks / Monkeypatch | unit-and-ai-tests (Full Suite Floor) | PR / Push (main) | `COMPLEMENTARY` | R-FUNC-04 | NONE | **`PRESERVED`** | Preserved in unit/. Canonical provider resolution and credential fallback tests. |
| `UNIT-004` | `CAT-092` | [`tests/unit/test_canonical_token_accounting.py`](file:///e:/JakeAI/backend/tests/unit/test_canonical_token_accounting.py) | 16 functions (`test_accounting_envelope_system_history_query` ...) | FinOps & Billing | Unit | Unit and regression tests for REPAIR-02: TOK-02 Canonical Token Accounting. | Redis, Mocks / Monkeypatch | unit-and-ai-tests (Full Suite Floor) | PR / Push (main) | `COMPLEMENTARY` | R-LOGIC-03 | NONE | **`PRESERVED`** | Preserved in unit/. Canonical token accounting envelope tests. |
| `UNIT-005` | `CAT-093` | [`tests/unit/test_direct_provider.py`](file:///e:/JakeAI/backend/tests/unit/test_direct_provider.py) | 7 functions (`test_direct_provider_defaults_and_credentials` ...) | Core / Platform | Unit | Unit tests for DirectProviderBackend adapter and credential hygiene. | HTTP / ASGI, Mocks / Monkeypatch | unit-and-ai-tests (Full Suite Floor) | PR / Push (main) | `COMPLEMENTARY` | R-FUNC-04 | NONE | **`PRESERVED`** | Preserved in unit/. DirectProviderBackend adapter unit tests. |
| `UNIT-006` | `CAT-094` | [`tests/unit/test_state_bridges.py`](file:///e:/JakeAI/backend/tests/unit/test_state_bridges.py) | 2 functions (`test_run_state_bidirectional_conversion` ...) | Core / Platform | Unit | Unit tests for WORK-01 state bridge converters and RunState bidirectional mapping. | None (Pure In-Memory) | unit-and-ai-tests (Full Suite Floor) | PR / Push (main) | `COMPLEMENTARY` | NONE | NONE | **`PRESERVED`** | Preserved in unit/. RunState/AgentState bridge converters unit tests. |
| `CONTRACT-004` | `CAT-095` | [`tests/contract/test_structured_conversation_contract.py`](file:///e:/JakeAI/backend/tests/contract/test_structured_conversation_contract.py) | 28 functions (`TestProviderRequestContract::test_provider_request_with_structured_messages` ...) | Contract & Schema | Contract | Comprehensive Regression and Contract Tests for REPAIR-01 (PROV-02). | Mocks / Monkeypatch | unit-and-ai-tests (Full Suite Floor) | PR / Push (main) | `UNIQUE` | R-ARCH-04 | NONE | **`MOVED`** | Moved to contract/. Structured conversation envelope contracts. |
| `UNIT-053` | `CAT-096` | [`tests/unit/test_state_transitions.py`](file:///e:/JakeAI/backend/tests/unit/test_state_transitions.py) | 142 functions / items (`test_run_status_valid_transitions` ...) | Core / Platform | Unit | Comprehensive deterministic unit tests for RunStatus, TaskStatus, and CircuitBreaker state transitions and idempotency. | None (Pure In-Memory) | unit-and-ai-tests (Full Suite Floor) | PR / Push (main) | `UNIQUE` | R-LOGIC-01 | NONE | **`CREATED`** | New TEST-02 unit test suite for state machines and circuit breaker transitions. |
| `UNIT-054` | `CAT-097` | [`tests/unit/test_agent_memory.py`](file:///e:/JakeAI/backend/tests/unit/test_agent_memory.py) | 15 functions (`TestLongTermMemoryUnit::test_multi_tenant_isolation` ...) | Agent Orchestration | Unit | In-memory unit tests for LongTermMemory, ShortTermMemory, and AgentMemoryManager multi-tenant isolation, TTL pruning, and state snapshotting. | None (Pure In-Memory) | unit-and-ai-tests (Full Suite Floor) | PR / Push (main) | `UNIQUE` | R-ARCH-00 / R-LOGIC-00 | NONE | **`CREATED`** | New TEST-02 unit test suite for isolated agent memory managers. |
| `UNIT-055` | `CAT-098` | [`tests/unit/test_tool_policy_and_validation.py`](file:///e:/JakeAI/backend/tests/unit/test_tool_policy_and_validation.py) | 43 functions (`TestToolPolicyEngineUnit::test_admin_role_bypass` ...) | Core / Platform | Unit | Deterministic unit tests for ToolPolicyEngine path traversal, shell injection, risk gating, and ToolRegistry JSON schema validation. | None (Pure In-Memory) | unit-and-ai-tests (Full Suite Floor) | PR / Push (main) | `UNIQUE` | R-AI-03 | NONE | **`CREATED`** | New TEST-02 unit test suite for tool policy, safety gating, and argument validation. |
| `UNIT-056` | `CAT-099` | [`tests/unit/test_recovery_and_decision_logic.py`](file:///e:/JakeAI/backend/tests/unit/test_recovery_and_decision_logic.py) | 37 functions (`TestRecoveryLimits::test_default_limits_and_aliases` ...) | Agent Orchestration | Unit | Unit tests for agent step failure recovery, verification evaluation, budget ceilings, and alternative model switching. | None (Pure In-Memory) | unit-and-ai-tests (Full Suite Floor) | PR / Push (main) | `UNIQUE` | R-LOGIC-04 | NONE | **`CREATED`** | New TEST-02 unit test suite for deterministic recovery and replanning decision logic. |
| `UNIT-057` | `CAT-100` | [`tests/unit/test_failover_decision_logic.py`](file:///e:/JakeAI/backend/tests/unit/test_failover_decision_logic.py) | 11 functions (`test_failover_config_defaults_and_validation` ...) | Core / Platform | Unit | Unit tests for failover exponential backoff jitter, duplicate candidate pruning, attempt ceilings, credential isolation, and streaming failover. | None (Pure In-Memory) | unit-and-ai-tests (Full Suite Floor) | PR / Push (main) | `UNIQUE` | R-FUNC-04 / R-LOGIC-04 | NONE | **`CREATED`** | New TEST-02 unit test suite for failover decision algorithms and credential isolation. |
| `UNIT-058` | `CAT-101` | [`tests/unit/test_request_normalization.py`](file:///e:/JakeAI/backend/tests/unit/test_request_normalization.py) | 11 functions (`test_provider_request_sync_prompt_and_system` ...) | Core / Platform | Unit | Unit tests for ProviderRequest wire normalization across OpenAI, Anthropic (system extraction, turn alternation), and Gemini (functionResponse). | None (Pure In-Memory) | unit-and-ai-tests (Full Suite Floor) | PR / Push (main) | `UNIQUE` | R-FUNC-04 | NONE | **`CREATED`** | New TEST-02 unit test suite for provider wire request schema normalization. |
| `UNIT-059` | `CAT-102` | [`tests/unit/test_provider_cache_adapters.py`](file:///e:/JakeAI/backend/tests/unit/test_provider_cache_adapters.py) | 21 functions (`test_resolve_provider_cache_policy_defaults` ...) | Token Optimization & Caching | Unit | Unit tests for provider prompt cache adapters, policy resolution, eligibility evaluation, CacheMissReason attribution, and usage parsing. | None (Pure In-Memory) | unit-and-ai-tests (Full Suite Floor) | PR / Push (main) | `UNIQUE` | R-FUNC-03 / R-AI-02 | NONE | **`CREATED`** | New TEST-02 unit test suite for Tier 5 provider cache adapters and telemetry. |
| `UNIT-060` | `CAT-103` | [`tests/unit/test_citations_and_context_sanitization.py`](file:///e:/JakeAI/backend/tests/unit/test_citations_and_context_sanitization.py) | 39 functions (`TestCitationGenerator::test_strip_hallucinated_footnotes_empty_passages` ...) | RAG Pipeline | Unit | Unit tests for CitationGenerator footnote stripping, metric/qualitative matching, score scrubbing, and ContextEnvelopeBuilder assembly. | None (Pure In-Memory) | unit-and-ai-tests (Full Suite Floor) | PR / Push (main) | `UNIQUE` | R-AI-01 / R-AI-04 | NONE | **`CREATED`** | New TEST-02 unit test suite for RAG citations, score sanitization, and envelope budgeting. |
| `UNIT-061` | `CAT-104` | [`tests/unit/test_finops_and_error_classification.py`](file:///e:/JakeAI/backend/tests/unit/test_finops_and_error_classification.py) | 29 functions (`TestFinOpsPricingCalculations::test_get_pricing_known_and_fallback_models` ...) | FinOps & Billing | Unit | Unit tests for FinOps pricing matrices, cache/routing savings calculations, secret redaction, and typed provider error normalization. | None (Pure In-Memory) | unit-and-ai-tests (Full Suite Floor) | PR / Push (main) | `UNIQUE` | R-LOGIC-03 / R-LOGIC-04 | NONE | **`CREATED`** | New TEST-02 unit test suite for FinOps pricing formulas and normalized error taxonomy. |
| `INT-017` | `CAT-105` | [`tests/integration/test_redis_integration.py`](file:///e:/JakeAI/backend/tests/integration/test_redis_integration.py) | 14 functions (`TestRedisIntegration::test_exact_cache_lifecycle_with_redis` ...) | Token Optimization & Caching | Integration | Deep integration suite for Redis Tier 1 exact cache, sliding window rate limiter, distributed locking, and 6 mandatory failure modes. | Redis | unit-and-ai-tests (Full Suite Floor) | PR / Push (main) | `COMPLEMENTARY` | R-FUNC-03 / R-LOGIC-00 | Bruno/06 — Cache (01-06) | **`CREATED`** | New TEST-03 integration test suite for Redis caching, rate limiting, and failover resilience. |
| `INT-018` | `CAT-106` | [`tests/integration/test_qdrant_integration.py`](file:///e:/JakeAI/backend/tests/integration/test_qdrant_integration.py) | 9 functions (`TestQdrantIntegration::test_dense_vector_upsert_and_cosine_similarity` ...) | RAG Pipeline | Integration | Deep integration suite for Qdrant Tier 2 semantic caching, vector collection management, multi-tenant payload isolation, and 6 mandatory failure modes. | Qdrant | unit-and-ai-tests (Full Suite Floor) | PR / Push (main) | `COMPLEMENTARY` | R-FUNC-02 / R-FUNC-03 / R-AI-01 | Bruno/04 — RAG (01-07) | **`CREATED`** | New TEST-03 integration test suite for Qdrant semantic indexing, tenant filtering, and fallback resilience. |
| `INT-019` | `CAT-107` | [`tests/integration/test_persistence_lifecycle.py`](file:///e:/JakeAI/backend/tests/integration/test_persistence_lifecycle.py) | 14 functions (`TestPersistenceLifecycle::test_run_state_roundtrip` ...) | Core / Platform | Integration | End-to-end state and persistence roundtrip suite across all 8 target state entities, disk-backed BM25 index serialization, and 6 mandatory failure modes. | Redis, File System | unit-and-ai-tests (Full Suite Floor) | PR / Push (main) | `COMPLEMENTARY` | R-ARCH-00 / R-LOGIC-00 | NONE | **`CREATED`** | New TEST-03 integration test suite for persistence lifecycle, checkpointing, and storage recovery. |
| `INT-020` | `CAT-108` | [`tests/integration/test_agent_runtime_integration.py`](file:///e:/JakeAI/backend/tests/integration/test_agent_runtime_integration.py) | 10 functions (`TestAgentRuntimeIntegration::test_agent_runtime_manager_task_and_run_lifecycle` ...) | Agent Orchestration | Integration | Comprehensive agent runtime integration suite verifying AgentRuntimeManager, ExecutionEngine DAG, human-in-the-loop approval pause/resume, memory integration, and 6 mandatory failure modes. | None (Pure In-Memory) | unit-and-ai-tests (Full Suite Floor) | PR / Push (main) | `COMPLEMENTARY` | R-FUNC-01 / R-AI-00 / R-ARCH-00 | Bruno/03 — Agent (01-10) | **`CREATED`** | New TEST-03 integration test suite for agent runtime, DAG execution, tool governance, and recovery. |
| `INT-021` | `CAT-109` | [`tests/integration/test_routing_and_provider_integration.py`](file:///e:/JakeAI/backend/tests/integration/test_routing_and_provider_integration.py) | 10 functions (`TestRoutingAndProviderIntegration::test_workload_classification_to_model_routing_flow` ...) | Core / Platform | Integration | Multi-provider adapter integration suite verifying workload classification, model routing, circuit breaker trip/half-open/closed transitions, failover execution, and 6 mandatory failure modes. | HTTP / ASGI, Mocks / Monkeypatch | unit-and-ai-tests (Full Suite Floor) | PR / Push (main) | `COMPLEMENTARY` | R-FUNC-04 / R-LOGIC-04 | Bruno/05 — BYOK & Providers (01-07) | **`CREATED`** | New TEST-03 integration test suite for model routing, circuit breaker, failover, and provider adapter wire contracts. |
| `INT-022` | `CAT-110` | [`tests/integration/test_rag_pipeline_integration.py`](file:///e:/JakeAI/backend/tests/integration/test_rag_pipeline_integration.py) | 10 functions (`TestRAGPipelineIntegration::test_document_ingestion_and_chunking_lifecycle` ...) | RAG Pipeline | Integration | Full-pipeline RAG integration suite verifying ingestion, hybrid retrieval (dense + BM25 sparse), reciprocal rank fusion (RRF), cross-encoder reranking, verifiable citation generation, grounding verification, and 6 mandatory failure modes. | Qdrant, File System | unit-and-ai-tests (Full Suite Floor) | PR / Push (main) | `COMPLEMENTARY` | R-FUNC-02 / R-AI-01 / R-AI-04 | Bruno/04 — RAG (01-07) | **`CREATED`** | New TEST-03 integration test suite for end-to-end RAG ingestion, hybrid search, citation extraction, and grounding. |
| `INT-023` | `CAT-111` | [`tests/integration/test_async_worker_integration.py`](file:///e:/JakeAI/backend/tests/integration/test_async_worker_integration.py) | 9 functions (`TestAsyncWorkerIntegration::test_document_ingestion_task_enqueue_and_execution` ...) | RAG Pipeline | Integration | Asynchronous worker integration suite verifying IngestionTaskManager task queuing, bounded worker pool execution, priority scheduling, progress tracking, and 6 mandatory failure modes. | Redis | unit-and-ai-tests (Full Suite Floor) | PR / Push (main) | `COMPLEMENTARY` | R-FUNC-02 / R-LOGIC-00 | NONE | **`CREATED`** | New TEST-03 integration test suite for async ingestion worker, priority scheduling, and worker fault tolerance. |
| `INT-024` | `CAT-112` | [`tests/integration/test_finops_governance_integration.py`](file:///e:/JakeAI/backend/tests/integration/test_finops_governance_integration.py) | 10 functions (`TestFinOpsGovernanceIntegration::test_dual_budget_governance_preflight_and_reservation` ...) | FinOps & Billing | Integration | FinOps cost truth and budget governance suite verifying pre-flight reservation, soft warning (80%) and hard cap (100%) enforcement, PayOS VietQR webhook verification, ledger sanitization, billing reconciliation, and 6 mandatory failure modes. | Redis | unit-and-ai-tests (Full Suite Floor) | PR / Push (main) | `COMPLEMENTARY` | R-LOGIC-03 | Bruno/07 — FinOps & Billing (01-06) | **`CREATED`** | New TEST-03 integration test suite for FinOps quota reservation, PayOS HMAC billing, ledger sanitization, and reconciliation. |
| `INT-025` | `CAT-113` | [`tests/integration/test_telemetry_and_context_integration.py`](file:///e:/JakeAI/backend/tests/integration/test_telemetry_and_context_integration.py) | 13 functions (`TestTelemetryAndContextIntegration::test_w3c_traceparent_parsing_generation_and_inheritance` ...) | Observability & Telemetry | Integration | Telemetry and context pipeline integration suite verifying W3C distributed tracing contextvars propagation, correlation ID cross-layer flow, 6-stage ContextEnvelope compilation, PII redaction, cardinality normalization, and 6 mandatory failure modes. | HTTP / ASGI | unit-and-ai-tests (Full Suite Floor) | PR / Push (main) | `COMPLEMENTARY` | R-AI-04 / R-ARCH-01 | Bruno/00 — Setup & Environment (01-Health Smoke) | **`CREATED`** | New TEST-03 integration test suite for W3C distributed tracing, correlation propagation, context envelope assembly, and telemetry PII masking. |
| `CONTRACT-006` | `CAT-114` | [`tests/contract/test_api_negative_contracts.py`](file:///e:/JakeAI/backend/tests/contract/test_api_negative_contracts.py) | 27 functions (32 items: `test_negative_400_bad_request_unsupported_byok_provider` ...) | Contract & Schema | Contract | Comprehensive ASGI HTTP boundary negative contracts verifying all 10 legitimate HTTP status codes (400, 401, 403, 404, 409, 413, 422, 429, 500, 503). | HTTP / ASGI, Mocks / Monkeypatch | API Breaking Change & Schema Drift Gate | PR / Push (main) | `UNIQUE` | R-ARCH-04 / R-FUNC-00 | Bruno/08 — Security & Negative (01-11) | **`CREATED`** | New TEST-04 contract test suite for comprehensive negative HTTP boundary status codes. |
| `CONTRACT-007` | `CAT-115` | [`tests/contract/test_api_http_workflows.py`](file:///e:/JakeAI/backend/tests/contract/test_api_http_workflows.py) | 5 functions (`test_workflow_1_agent_task_lifecycle_and_streaming` ...) | Contract & Schema | Contract | End-to-end ASGI HTTP representative workflows verifying Agent, RAG, BYOK, AI Gateway & FinOps, and Human-in-the-Loop resume bridge. | Redis, Qdrant, HTTP / ASGI, Mocks / Monkeypatch | API Breaking Change & Schema Drift Gate | PR / Push (main) | `UNIQUE` | R-FUNC-00 / R-ARCH-04 | Bruno Collections (01-08) | **`CREATED`** | New TEST-04 contract test suite for 5 critical representative end-to-end ASGI HTTP workflows. |
| `SEC-006` | `CAT-116` | [`tests/security/test_security_authentication.py`](file:///e:/JakeAI/backend/tests/security/test_security_authentication.py) | 30 functions (`test_auth_missing_bearer_token` ...) | Security & Governance | Security | Runtime security regression test suite for JWT authentication, expiration, algorithms, JTI revocation, perimeter secrets, and HMAC. | HTTP / ASGI | Dedicated Runtime Security Regression Suite (TEST-05) | PR / Push (main) | `UNIQUE` | R-LOGIC-02 / R-ARCH-04 | Bruno/08 — Security & Negative (01-11) | **`CREATED`** | New TEST-05 dedicated runtime authentication security regression suite. |
| `SEC-007` | `CAT-117` | [`tests/security/test_security_authorization.py`](file:///e:/JakeAI/backend/tests/security/test_security_authorization.py) | 11 functions (`test_authorization_insufficient_permission_for_tool` ...) | Security & Governance | Security | Runtime security regression test suite for RBAC permissions, role isolation, approval hijack/replay/TOCTOU resistance, and unmapped tools. | HTTP / ASGI | Dedicated Runtime Security Regression Suite (TEST-05) | PR / Push (main) | `UNIQUE` | R-LOGIC-02 / R-AI-03 | Bruno/08 — Security & Negative (01-11) | **`CREATED`** | New TEST-05 dedicated runtime authorization security regression suite. |
| `SEC-008` | `CAT-118` | [`tests/security/test_security_tenant_isolation.py`](file:///e:/JakeAI/backend/tests/security/test_security_tenant_isolation.py) | 10 functions (`test_tenant_isolation_agent_tasks_and_runs` ...) | Security & Governance | Security | Multi-tenant boundary regression suite across Agent tasks/runs, LangGraph threads, exact/semantic caches, RAG indexes, BYOK keys, and uniform 404s. | Redis, Qdrant, HTTP / ASGI | Dedicated Runtime Security Regression Suite (TEST-05) | PR / Push (main) | `UNIQUE` | R-AI-04 / R-LOGIC-02 | Bruno/08 — Security & Negative (01-11) | **`CREATED`** | New TEST-05 dedicated runtime tenant isolation regression suite. |
| `SEC-009` | `CAT-119` | [`tests/security/test_security_llm_tool_safety.py`](file:///e:/JakeAI/backend/tests/security/test_security_llm_tool_safety.py) | 12 functions (40 items: `test_direct_prompt_injection_detection` ...) | Security & Governance | Security | LLM & tool security suite for direct/indirect prompt injection, tool output contamination, dangerous shell blocking, path traversal, schema bounds, secret scrubbing, and error sanitization. | None (Pure In-Memory) | Dedicated Runtime Security Regression Suite (TEST-05) | PR / Push (main) | `UNIQUE` | R-AI-02 / R-AI-03 | Bruno/08 — Security & Negative (01-11) | **`CREATED`** | New TEST-05 dedicated runtime LLM & tool security regression suite. |
| `SEC-010` | `CAT-120` | [`tests/security/test_security_fail_closed.py`](file:///e:/JakeAI/backend/tests/security/test_security_fail_closed.py) | 14 functions (`test_fail_closed_verifier_rejects_mathematical_variance` ...) | Security & Governance | Security | Fail-closed invariants suite for verifier variance, foreign tenant breaches, unapproved tools, missing BYOK credentials, budget overflow, and empty auth headers. | HTTP / ASGI | Dedicated Runtime Security Regression Suite (TEST-05) | PR / Push (main) | `UNIQUE` | R-LOGIC-00 / R-LOGIC-02 | Bruno/08 — Security & Negative (01-11) | **`CREATED`** | New TEST-05 dedicated fail-closed invariants regression suite. |
| `AI-012` | `CAT-121` | [`tests/evals/test_eval_agent_automation.py`](file:///e:/JakeAI/backend/tests/evals/test_eval_agent_automation.py) | 15 functions (29 items: `test_eval_agent_01_goal_interpretation_and_constraint_extraction` ...) | Agent Orchestration | AI Eval / Benchmark | Comprehensive automated evaluation for 14 agent orchestration dimensions (goal interpretation, plan structure, agent selection, model selection, tool selection, tool execution, verification, recovery, retry bounds, approval flow, resume integrity, cancellation, terminal state, failure truthfulness) plus versioned regression fixtures. | None (Pure In-Memory) | AI Behavior, Agent, RAG & Hallucination Evaluation Gate (TEST-06) | PR / Push (main) | `UNIQUE` | R-FUNC-01 / R-AI-00 | Bruno/03 — Agent (01-10) | **`CREATED`** | New TEST-06 automated evaluation layer for 14 agent orchestration dimensions and versioned regression fixtures. |
| `AI-013` | `CAT-122` | [`tests/evals/test_eval_rag_automation.py`](file:///e:/JakeAI/backend/tests/evals/test_eval_rag_automation.py) | 11 functions (20 items: `test_eval_rag_01_retrieval_relevance_ranking` ...) | RAG Pipeline | AI Eval / Benchmark | Comprehensive automated evaluation for 10 RAG dimensions (MRR/NDCG retrieval relevance, multi-tenant isolation, 6-stage context construction, grounding entailment, citation integrity, unsupported claim detection, contradiction detection, epistemic abstention, prompt injection resistance, context budget load shedding) plus versioned regression fixtures. | None (Pure In-Memory) | AI Behavior, Agent, RAG & Hallucination Evaluation Gate (TEST-06) | PR / Push (main) | `UNIQUE` | R-FUNC-02 / R-AI-01 / R-AI-04 | Bruno/04 — RAG (01-07) | **`CREATED`** | New TEST-06 automated evaluation layer for 10 RAG pipeline dimensions, retrieval math, and versioned regression fixtures. |
| `AI-014` | `CAT-123` | [`tests/evals/test_eval_hallucination_automation.py`](file:///e:/JakeAI/backend/tests/evals/test_eval_hallucination_automation.py) | 9 functions (14 items: `test_eval_hallucination_01_supported_claims` ...) | AI Evaluation & Benchmarking | AI Eval / Benchmark | Controlled dataset evaluation covering 4 mandatory categories (SUPPORTED, UNSUPPORTED, CONTRADICTORY, INSUFFICIENT EVIDENCE) and edge cases via deterministic assertions (metric canonicalization, antonym polarity matrix, entity divergence, epistemic abstention). | None (Pure In-Memory) | AI Behavior, Agent, RAG & Hallucination Evaluation Gate (TEST-06) | PR / Push (main) | `UNIQUE` | R-AI-01 / R-AI-02 / R-AI-04 | Bruno/08 — Security & Negative (01-11) | **`CREATED`** | New TEST-06 automated evaluation layer for deterministic hallucination categories, metric normalizer, and polarity matrix. |
| `E2E-003` | `CAT-124` | [`tests/e2e/test_e2e_business_workflows.py`](file:///e:/JakeAI/backend/tests/e2e/test_e2e_business_workflows.py) | 9 functions (9 items: `test_e2e_workflow_01_auth_to_chat_lifecycle` ...) | Business Workflows | E2E | High-value full business workflow E2E test suite covering 7 mandatory business lifecycles: AUTH -> CHAT, AUTH -> AGENT, AGENT -> TOOL -> VERIFY, RAG, BYOK / PROVIDER, FAILURE / RECOVERY, and APPROVAL (with rejection and live-external hooks). | HTTP / ASGI, Redis, Qdrant, Mocks / Monkeypatch | Critical End-to-End Business Workflow Gate (TEST-07) | PR / Push (main) | `UNIQUE` | R-FUNC-00 / R-FUNC-01 / R-FUNC-02 / R-FUNC-04 | Bruno Collections (02, 03, 04, 05, 07, 08) | **`CREATED`** | New TEST-07 authoritative business workflow E2E test suite verifying state transitions, telemetry, tenant isolation, and failure recovery. |

---

## 3. Granular Test Family Breakdown by Subsystem

Detailed inventory and test function manifest for each subsystem.

### 3.1 Subsystem: AI Evaluation & Benchmarking (8 Files)
#### `CAT-076`: [`test_baseline_and_regression_gate.py`](file:///e:/JakeAI/backend/tests/evals/test_baseline_and_regression_gate.py)
- **Test File Path**: `backend/tests/evals/test_baseline_and_regression_gate.py` (92 lines)
- **Subsystem**: `AI Evaluation & Benchmarking`
- **Test Level**: `AI Eval / Benchmark`
- **Purpose**: Unit tests for Baseline Store and Live Benchmark Regression Gate (TASK OPS-15 & OPS-16).
- **Dependencies / Fixtures**: None (Pure In-Memory)
- **CI Job Execution**: `LLMOps Safety & Canary Data Leakage Gate`
- **Recommended Run Frequency**: `PR / Push (main)`
- **Duplicate / Overlap Classification**: `UNIQUE`
- **RIGHT Test Suite Coverage**: `NONE`
- **Bruno Collection Coverage**: `NONE`
- **Architectural Disposition**: **`MOVE`** (Target Destination: `backend/tests/evals/`)
- **Disposition Rationale & Evidence**: AI evaluation or empirical token benchmark suite. Move to evals/.
- **Discovered Test Functions (4)**:
  - [`test_baseline_store_load_and_save`](file:///e:/JakeAI/backend/tests/evals/test_baseline_and_regression_gate.py#L1): Direct assertion (4 assertions)
  - [`test_canonical_v1_baseline_exists`](file:///e:/JakeAI/backend/tests/evals/test_baseline_and_regression_gate.py#L1): Direct assertion (4 assertions)
  - [`test_live_benchmark_evaluation_pass`](file:///e:/JakeAI/backend/tests/evals/test_baseline_and_regression_gate.py#L1): Direct assertion (2 assertions)
  - [`test_live_benchmark_evaluation_blocks_on_quality_regression`](file:///e:/JakeAI/backend/tests/evals/test_baseline_and_regression_gate.py#L1): Direct assertion (4 assertions)

#### `CAT-078`: [`test_coding_intelligence_regression.py`](file:///e:/JakeAI/backend/tests/evals/test_coding_intelligence_regression.py)
- **Test File Path**: `backend/tests/evals/test_coding_intelligence_regression.py` (232 lines)
- **Subsystem**: `AI Evaluation & Benchmarking`
- **Test Level**: `AI Eval / Benchmark`
- **Purpose**: Golden Dataset Coding Agent Regression & Intelligence Preservation Suite.
- **Dependencies / Fixtures**: None (Pure In-Memory)
- **CI Job Execution**: `unit-and-ai-tests (Full Suite Floor)`
- **Recommended Run Frequency**: `PR / Push (main)`
- **Duplicate / Overlap Classification**: `UNIQUE`
- **RIGHT Test Suite Coverage**: `NONE`
- **Bruno Collection Coverage**: `NONE`
- **Architectural Disposition**: **`MOVE`** (Target Destination: `backend/tests/evals/`)
- **Disposition Rationale & Evidence**: AI evaluation or empirical token benchmark suite. Move to evals/.
- **Discovered Test Functions (5)**:
  - [`test_task_a_bug_fix_preserves_implementation`](file:///e:/JakeAI/backend/tests/evals/test_coding_intelligence_regression.py#L1): Task A (Bug Fix): Conservative mode preserves full code logic so bug can be fixed. (5 assertions)
  - [`test_task_b_authentication_preserves_security_checks`](file:///e:/JakeAI/backend/tests/evals/test_coding_intelligence_regression.py#L1): Task B (Authentication): Security checks, HMAC comparison, error raises are preserved. (5 assertions)
  - [`test_task_c_cross_file_refactor_preserves_interfaces`](file:///e:/JakeAI/backend/tests/evals/test_coding_intelligence_regression.py#L1): Task C (Cross-File Refactor): Preserves models and type contracts across files. (4 assertions)
  - [`test_task_d_architecture_analysis_aggressive_skeletonization`](file:///e:/JakeAI/backend/tests/evals/test_coding_intelligence_regression.py#L1): Task D (Architecture Query): Aggressive skeletonization safely reduces tokens without losing structure. (8 assertions)
  - [`test_performance_and_finops_benchmark`](file:///e:/JakeAI/backend/tests/evals/test_coding_intelligence_regression.py#L1): Benchmark execution latency, token reduction, and total FinOps cost effectiveness. (3 assertions)

#### `CAT-079`: [`test_llm_judge_and_generation.py`](file:///e:/JakeAI/backend/tests/evals/test_llm_judge_and_generation.py)
- **Test File Path**: `backend/tests/evals/test_llm_judge_and_generation.py` (117 lines)
- **Subsystem**: `AI Evaluation & Benchmarking`
- **Test Level**: `AI Eval / Benchmark`
- **Purpose**: Unit tests for Real LLM Judge and Actual Model Generation Evaluation (TASK OPS-09 & OPS-10).
- **Dependencies / Fixtures**: Mocks / Monkeypatch
- **CI Job Execution**: `LLMOps Safety & Canary Data Leakage Gate`
- **Recommended Run Frequency**: `PR / Push (main)`
- **Duplicate / Overlap Classification**: `UNIQUE`
- **RIGHT Test Suite Coverage**: `NONE`
- **Bruno Collection Coverage**: `NONE`
- **Architectural Disposition**: **`MOVE`** (Target Destination: `backend/tests/evals/`)
- **Disposition Rationale & Evidence**: AI evaluation or empirical token benchmark suite. Move to evals/.
- **Discovered Test Functions (3)**:
  - [`test_llm_judge_heuristic_rubric_fallback`](file:///e:/JakeAI/backend/tests/evals/test_llm_judge_and_generation.py#L1): Direct assertion (5 assertions)
  - [`test_llm_judge_real_model_invocation`](file:///e:/JakeAI/backend/tests/evals/test_llm_judge_and_generation.py#L1): Direct assertion (5 assertions)
  - [`test_benchmark_runner_actual_model_generation`](file:///e:/JakeAI/backend/tests/evals/test_llm_judge_and_generation.py#L1): Direct assertion (3 assertions)

#### `CAT-080`: [`test_phase03_token_optimization.py`](file:///e:/JakeAI/backend/tests/evals/test_phase03_token_optimization.py)
- **Test File Path**: `backend/tests/evals/test_phase03_token_optimization.py` (520 lines)
- **Subsystem**: `AI Evaluation & Benchmarking`
- **Test Level**: `AI Eval / Benchmark`
- **Purpose**: Phase 03 Token Optimization Comprehensive Verification Suite.
- **Dependencies / Fixtures**: None (Pure In-Memory)
- **CI Job Execution**: `unit-and-ai-tests (Full Suite Floor)`
- **Recommended Run Frequency**: `PR / Push (main)`
- **Duplicate / Overlap Classification**: `UNIQUE`
- **RIGHT Test Suite Coverage**: `NONE`
- **Bruno Collection Coverage**: `NONE`
- **Architectural Disposition**: **`MOVE`** (Target Destination: `backend/tests/evals/`)
- **Disposition Rationale & Evidence**: AI evaluation or empirical token benchmark suite. Move to evals/.
- **Discovered Test Functions (13)**:
  - [`test_layer1_exact_cache_metrics_and_accounting`](file:///e:/JakeAI/backend/tests/evals/test_phase03_token_optimization.py#L1): Verify Layer 1 Exact Match Cache hits, telemetry counters, and tokens/cost avoided. (14 assertions)
  - [`test_layer2_semantic_cache_model_and_tenant_isolation`](file:///e:/JakeAI/backend/tests/evals/test_phase03_token_optimization.py#L1): Verify Layer 2 Semantic Cache enforces strict tenant AND model/provider boundaries. (6 assertions)
  - [`test_layer3_boilerplate_pruning_and_entity_protection`](file:///e:/JakeAI/backend/tests/evals/test_phase03_token_optimization.py#L1): Verify Layer 3 prunes corporate boilerplate while protecting 100% of dates, currencies, and citations. (12 assertions)
  - [`test_layer3_structured_json_minification_invariance`](file:///e:/JakeAI/backend/tests/evals/test_phase03_token_optimization.py#L1): Verify Layer 3 never corrupts JSON syntax, schema, or keys (Invariant 4). (5 assertions)
  - [`test_layer3_markdown_code_block_preservation`](file:///e:/JakeAI/backend/tests/evals/test_phase03_token_optimization.py#L1): Verify code blocks within markdown are preserved intact without sentence splitting corruption. (4 assertions)
  - [`test_layer4_retrieval_compressor_pruning_and_citation_retention`](file:///e:/JakeAI/backend/tests/evals/test_phase03_token_optimization.py#L1): Verify Layer 4 prunes distractor chunks while retaining required citations and figures. (8 assertions)
  - [`test_layer5_two_zone_prompt_compilation_and_rule4_invariance`](file:///e:/JakeAI/backend/tests/evals/test_phase03_token_optimization.py#L1): Verify Layer 5 strictly isolates Zone 1 from Zone 2 and enforces byte-determinism. (3 assertions)
  - [`test_layer7_git_diff_pruning`](file:///e:/JakeAI/backend/tests/evals/test_phase03_token_optimization.py#L1): Verify Layer 7 prunes long runs of unchanged lines in git diffs while preserving hunks. (5 assertions)
  - [`test_layer7_generated_file_exclusion`](file:///e:/JakeAI/backend/tests/evals/test_phase03_token_optimization.py#L1): Verify Layer 7 identifies and excludes noisy package lockfiles. (3 assertions)
  - [`test_layer7_chat_workload_guardrail_noop`](file:///e:/JakeAI/backend/tests/evals/test_phase03_token_optimization.py#L1): Verify Layer 7 strictly avoids code pruning on normal chat workloads (Invariant). (3 assertions)
  - [`test_layer8_cost_aware_model_routing`](file:///e:/JakeAI/backend/tests/evals/test_phase03_token_optimization.py#L1): Verify Layer 8 routes simple chat queries to cost-efficient models with positive cost savings. (5 assertions)
  - [`test_workload_aware_optimizer_all_workload_classes`](file:///e:/JakeAI/backend/tests/evals/test_phase03_token_optimization.py#L1): Verify ContextOptimizer correctly tailors optimization across all 7 workload types. (12 assertions)
  - [`test_cross_tier_pipeline_e2e_integration`](file:///e:/JakeAI/backend/tests/evals/test_phase03_token_optimization.py#L1): Verify CrossTierPipeline executes Tier 5 -> 6 -> 7 with workload awareness. (7 assertions)

#### `CAT-081`: [`test_phase06_evaluation.py`](file:///e:/JakeAI/backend/tests/evals/test_phase06_evaluation.py)
- **Test File Path**: `backend/tests/evals/test_phase06_evaluation.py` (577 lines)
- **Subsystem**: `AI Evaluation & Benchmarking`
- **Test Level**: `AI Eval / Benchmark`
- **Purpose**: Comprehensive Phase 06 AI Quality Evaluation & Regression Test Suite.
- **Dependencies / Fixtures**: None (Pure In-Memory)
- **CI Job Execution**: `unit-and-ai-tests (Full Suite Floor)`
- **Recommended Run Frequency**: `PR / Push (main)`
- **Duplicate / Overlap Classification**: `UNIQUE`
- **RIGHT Test Suite Coverage**: `NONE`
- **Bruno Collection Coverage**: `NONE`
- **Architectural Disposition**: **`MOVE`** (Target Destination: `backend/tests/evals/`)
- **Disposition Rationale & Evidence**: AI evaluation or empirical token benchmark suite. Move to evals/.
- **Discovered Test Functions (13)**:
  - [`test_rubric_evaluator_all_dimensions_positive`](file:///e:/JakeAI/backend/tests/evals/test_phase06_evaluation.py#L1): Verify that a high-quality answer scores >= 0.85 across all 7 dimensions. (7 assertions)
  - [`test_rubric_evaluator_detects_individual_dimension_failures`](file:///e:/JakeAI/backend/tests/evals/test_phase06_evaluation.py#L1): Verify each rubric dimension reliably fails when its specific requirement is violated. (6 assertions)
  - [`test_llm_judge_blinded_ordering_and_comparison`](file:///e:/JakeAI/backend/tests/evals/test_phase06_evaluation.py#L1): Verify blinded candidate ordering eliminates presentation bias and produces structured comparison. (7 assertions)
  - [`test_llm_judge_calibration_against_ground_truth`](file:///e:/JakeAI/backend/tests/evals/test_phase06_evaluation.py#L1): Verify judge calibration: ground truth reference answer must defeat corrupted candidate. (1 assertions)
  - [`test_regression_detector_detects_quality_regression`](file:///e:/JakeAI/backend/tests/evals/test_phase06_evaluation.py#L1): Verify detector triggers BLOCK on critical fact loss or score drop. (6 assertions)
  - [`test_regression_detector_detects_token_regression`](file:///e:/JakeAI/backend/tests/evals/test_phase06_evaluation.py#L1): Verify detector triggers BLOCK when optimization increases token count. (5 assertions)
  - [`test_regression_detector_detects_cost_regression`](file:///e:/JakeAI/backend/tests/evals/test_phase06_evaluation.py#L1): Verify detector triggers BLOCK when optimized path is more expensive than baseline. (4 assertions)
  - [`test_regression_detector_passes_clean_optimization`](file:///e:/JakeAI/backend/tests/evals/test_phase06_evaluation.py#L1): Verify detector outputs PASS when quality, tokens, and cost all improve. (3 assertions)
  - [`test_measurement_correctness_twelve_metrics_strictly_independent`](file:///e:/JakeAI/backend/tests/evals/test_phase06_evaluation.py#L1): Confirm that the 12 core metrics are strictly independent and never confused: (9 assertions)
  - [`test_failed_optimization_when_40pct_reduction_has_quality_degradation`](file:///e:/JakeAI/backend/tests/evals/test_phase06_evaluation.py#L1): Prompt Mandate: A result such as '40% token reduction + material quality degradation' (3 assertions)
  - [`test_rubric_evaluator_deep_branch_coverage`](file:///e:/JakeAI/backend/tests/evals/test_phase06_evaluation.py#L1): Exercise all branch conditions in RubricEvaluator. (22 assertions)
  - [`test_llm_judge_branch_coverage`](file:///e:/JakeAI/backend/tests/evals/test_phase06_evaluation.py#L1): Exercise candidate ordering and verdict branches in LLMJudge. (7 assertions)
  - [`test_regression_detector_branch_coverage`](file:///e:/JakeAI/backend/tests/evals/test_phase06_evaluation.py#L1): Exercise WARN severity, citation loss, schema errors, and clean PASS in RegressionDetector. (15 assertions)

#### `CAT-082`: [`test_portfolio_benchmark.py`](file:///e:/JakeAI/backend/tests/evals/test_portfolio_benchmark.py)
- **Test File Path**: `backend/tests/evals/test_portfolio_benchmark.py` (134 lines)
- **Subsystem**: `AI Evaluation & Benchmarking`
- **Test Level**: `AI Eval / Benchmark`
- **Purpose**: Phase 00 Portfolio AI Evaluation Benchmark & Regression Test Suite.
- **Dependencies / Fixtures**: None (Pure In-Memory)
- **CI Job Execution**: `Phase 00 AI Evaluation Benchmark Gate`
- **Recommended Run Frequency**: `PR / Push (main)`
- **Duplicate / Overlap Classification**: `UNIQUE`
- **RIGHT Test Suite Coverage**: `NONE`
- **Bruno Collection Coverage**: `NONE`
- **Architectural Disposition**: **`MOVE`** (Target Destination: `backend/tests/evals/`)
- **Disposition Rationale & Evidence**: AI evaluation or empirical token benchmark suite. Move to evals/.
- **Discovered Test Functions (2)**:
  - [`test_phase_00_portfolio_benchmark_all_workloads`](file:///e:/JakeAI/backend/tests/evals/test_portfolio_benchmark.py#L1): Run full Phase 00 multi-workload benchmark and assert all gates pass. (16 assertions)
  - [`test_quality_oracle_regression_detection`](file:///e:/JakeAI/backend/tests/evals/test_portfolio_benchmark.py#L1): Verify QualityOracle strictly detects fact loss, leakage, and syntax corruption. (7 assertions)

#### `CAT-088`: [`test_token_benchmark.py`](file:///e:/JakeAI/backend/tests/evals/test_token_benchmark.py)
- **Test File Path**: `backend/tests/evals/test_token_benchmark.py` (234 lines)
- **Subsystem**: `AI Evaluation & Benchmarking`
- **Test Level**: `AI Eval / Benchmark`
- **Purpose**: Empirical Benchmark & Token Accounting Verification Suite.
- **Dependencies / Fixtures**: None (Pure In-Memory)
- **CI Job Execution**: `Token Optimization Benchmark Gate`
- **Recommended Run Frequency**: `PR / Push (main)`
- **Duplicate / Overlap Classification**: `UNIQUE`
- **RIGHT Test Suite Coverage**: `NONE`
- **Bruno Collection Coverage**: `NONE`
- **Architectural Disposition**: **`MOVE`** (Target Destination: `backend/tests/evals/`)
- **Disposition Rationale & Evidence**: AI evaluation or empirical token benchmark suite. Move to evals/.
- **Discovered Test Functions (3)**:
  - [`test_heuristic_token_pruner_compression_and_fact_retention`](file:///e:/JakeAI/backend/tests/evals/test_token_benchmark.py#L1): Verify that HeuristicTokenPruner achieves >= 25% compression with 0% fact loss. (5 assertions)
  - [`test_enterprise_workload_token_benchmark_40_percent_gate`](file:///e:/JakeAI/backend/tests/evals/test_token_benchmark.py#L1): Empirically prove that the combined AI Gateway optimization achieves >= 40% Token Reduction. (5 assertions)
  - [`test_token_accounting_mathematical_conservation`](file:///e:/JakeAI/backend/tests/evals/test_token_benchmark.py#L1): Verify that TokenAccounting adheres strictly to the Conservation of Tokens law. (8 assertions)

#### `CAT-123`: [`test_eval_hallucination_automation.py`](file:///e:/JakeAI/backend/tests/evals/test_eval_hallucination_automation.py)
- **Test File Path**: `backend/tests/evals/test_eval_hallucination_automation.py` (245 lines)
- **Subsystem**: `AI Evaluation & Benchmarking`
- **Test Level**: `AI Eval / Benchmark`
- **Purpose**: Controlled dataset evaluation covering 4 mandatory categories (SUPPORTED, UNSUPPORTED, CONTRADICTORY, INSUFFICIENT EVIDENCE) and edge cases via deterministic assertions (metric canonicalization, antonym polarity matrix, entity divergence, epistemic abstention).
- **Dependencies / Fixtures**: None (Pure In-Memory)
- **CI Job Execution**: `AI Behavior, Agent, RAG & Hallucination Evaluation Gate (TEST-06)`
- **Recommended Run Frequency**: `PR / Push (main)`
- **Duplicate / Overlap Classification**: `UNIQUE`
- **RIGHT Test Suite Coverage**: `R-AI-01 / R-AI-02 / R-AI-04`
- **Bruno Collection Coverage**: `Bruno/08 — Security & Negative (01-11)`
- **Architectural Disposition**: **`CREATED`** (Target Destination: `backend/tests/evals/`)
- **Disposition Rationale & Evidence**: New TEST-06 automated evaluation layer for deterministic hallucination categories, metric normalizer, and polarity matrix.
- **Discovered Test Functions (9)**:
  - [`test_eval_hallucination_01_supported_claims`](file:///e:/JakeAI/backend/tests/evals/test_eval_hallucination_automation.py#L1): Evaluate fully supported propositions with metrics (42.5M, 6.2%, 18.4%) pass with 1.0 groundedness.
  - [`test_eval_hallucination_02_unsupported_extrapolations`](file:///e:/JakeAI/backend/tests/evals/test_eval_hallucination_automation.py#L1): Evaluate unevidenced projections ($88.5B by 2030, 45 datacenters) are flagged as ungrounded.
  - [`test_eval_hallucination_03_contradictory_claims`](file:///e:/JakeAI/backend/tests/evals/test_eval_hallucination_automation.py#L1): Evaluate antonym polarity ('lowered' vs 'raised') and metric conflict (4.25% vs 5.75%) detected.
  - [`test_eval_hallucination_04_insufficient_evidence_abstention`](file:///e:/JakeAI/backend/tests/evals/test_eval_hallucination_automation.py#L1): Evaluate explicit epistemic abstention is recognized as grounded behavior and not penalized.
  - [`test_eval_hallucination_05_multi_chunk_compound_metrics`](file:///e:/JakeAI/backend/tests/evals/test_eval_hallucination_automation.py#L1): Evaluate compound metrics across distinct passages are validated ensemble without false conflict.
  - [`test_eval_hallucination_06_entity_divergence_contradiction`](file:///e:/JakeAI/backend/tests/evals/test_eval_hallucination_automation.py#L1): Evaluate named entity collision ('Singapore' vs 'Berlin') flagged despite 80% lexical overlap.
  - [`test_eval_hallucination_07_deterministic_metric_canonicalization`](file:///e:/JakeAI/backend/tests/evals/test_eval_hallucination_automation.py#L1): Evaluate metric normalizer equates formatted variations deterministically.
  - [`test_eval_hallucination_08_deterministic_antonym_polarity`](file:///e:/JakeAI/backend/tests/evals/test_eval_hallucination_automation.py#L1): Evaluate known antonym pairs are recognized in the bidirectional polarity dictionary.
  - [`test_eval_hallucination_versioned_fixtures_pass`](file:///e:/JakeAI/backend/tests/evals/test_eval_hallucination_automation.py#L1): Execute evaluation assertions across all versioned hallucination fixtures (6 items).

### 3.2 Subsystem: Agent Orchestration (10 Files)
#### `CAT-002`: [`test_agent_platform.py`](file:///e:/JakeAI/backend/tests/test_agent_platform.py)
- **Test File Path**: `backend/tests/test_agent_platform.py` (789 lines)
- **Subsystem**: `Agent Orchestration`
- **Test Level**: `Unit`
- **Purpose**: Comprehensive unit, integration, and contract tests for Phase 08 — JakeAI-Agent Platform.
- **Dependencies / Fixtures**: HTTP / ASGI, Mocks / Monkeypatch
- **CI Job Execution**: `unit-and-ai-tests (Full Suite Floor)`
- **Recommended Run Frequency**: `PR / Push (main)`
- **Duplicate / Overlap Classification**: `COMPLEMENTARY`
- **RIGHT Test Suite Coverage**: `R-FUNC-01 / R-AI-00 / R-ARCH-00`
- **Bruno Collection Coverage**: `Bruno/03 — Agent (01-10)`
- **Architectural Disposition**: **`MOVE`** (Target Destination: `backend/tests/integration/`)
- **Disposition Rationale & Evidence**: Valuable subsystem test. Needs reclassification into unit/, integration/, or security/.
- **Discovered Test Functions (19)**:
  - [`test_jakeai_backend_text_response`](file:///e:/JakeAI/backend/tests/test_agent_platform.py#L1): Direct assertion (5 assertions)
  - [`test_jakeai_backend_tool_calls_response`](file:///e:/JakeAI/backend/tests/test_agent_platform.py#L1): Direct assertion (4 assertions)
  - [`test_jakeai_backend_streaming`](file:///e:/JakeAI/backend/tests/test_agent_platform.py#L1): Direct assertion (2 assertions)
  - [`test_direct_provider_backend_openai_compatible`](file:///e:/JakeAI/backend/tests/test_agent_platform.py#L1): Direct assertion (3 assertions)
  - [`test_direct_provider_backend_missing_key`](file:///e:/JakeAI/backend/tests/test_agent_platform.py#L1): Direct assertion (1 assertions)
  - [`test_external_agent_backend_dispatch`](file:///e:/JakeAI/backend/tests/test_agent_platform.py#L1): Direct assertion (2 assertions)
  - [`test_tool_registry_and_policy`](file:///e:/JakeAI/backend/tests/test_agent_platform.py#L1): Direct assertion (9 assertions)
  - [`test_local_safe_sandbox_file_and_commands`](file:///e:/JakeAI/backend/tests/test_agent_platform.py#L1): Direct assertion (8 assertions)
  - [`test_state_and_checkpoint_tenant_isolation`](file:///e:/JakeAI/backend/tests/test_agent_platform.py#L1): Direct assertion (4 assertions)
  - [`test_short_term_memory_sliding_window`](file:///e:/JakeAI/backend/tests/test_agent_platform.py#L1): Direct assertion (4 assertions)
  - [`test_long_term_memory_tenant_isolation`](file:///e:/JakeAI/backend/tests/test_agent_platform.py#L1): Direct assertion (5 assertions)
  - [`test_approval_manager_flow_and_isolation`](file:///e:/JakeAI/backend/tests/test_agent_platform.py#L1): Direct assertion (7 assertions)
  - [`test_bounded_planner_limits`](file:///e:/JakeAI/backend/tests/test_agent_platform.py#L1): Direct assertion (2 assertions)
  - [`test_agent_execution_loop_normal_finish`](file:///e:/JakeAI/backend/tests/test_agent_platform.py#L1): Direct assertion (4 assertions)
  - [`test_agent_execution_loop_approval_gate_and_resume`](file:///e:/JakeAI/backend/tests/test_agent_platform.py#L1): Direct assertion (6 assertions)
  - [`test_agent_execution_loop_cancellation`](file:///e:/JakeAI/backend/tests/test_agent_platform.py#L1): Direct assertion (2 assertions)
  - [`test_api_create_task_and_get_task`](file:///e:/JakeAI/backend/tests/test_agent_platform.py#L1): Direct assertion (6 assertions)
  - [`test_api_create_run_and_cancel`](file:///e:/JakeAI/backend/tests/test_agent_platform.py#L1): Direct assertion (7 assertions)
  - [`test_api_approvals_and_metrics_endpoints`](file:///e:/JakeAI/backend/tests/test_agent_platform.py#L1): Direct assertion (6 assertions)

#### `CAT-003`: [`test_agent_registry_and_selector.py`](file:///e:/JakeAI/backend/tests/test_agent_registry_and_selector.py)
- **Test File Path**: `backend/tests/test_agent_registry_and_selector.py` (119 lines)
- **Subsystem**: `Agent Orchestration`
- **Test Level**: `Unit`
- **Purpose**: Unit tests for AgentRegistry and AgentSelector.
- **Dependencies / Fixtures**: None (Pure In-Memory)
- **CI Job Execution**: `unit-and-ai-tests (Full Suite Floor)`
- **Recommended Run Frequency**: `PR / Push (main)`
- **Duplicate / Overlap Classification**: `COMPLEMENTARY`
- **RIGHT Test Suite Coverage**: `R-FUNC-01 / R-AI-00 / R-ARCH-00`
- **Bruno Collection Coverage**: `NONE`
- **Architectural Disposition**: **`MOVE`** (Target Destination: `backend/tests/unit/`)
- **Disposition Rationale & Evidence**: Valuable subsystem test. Needs reclassification into unit/, integration/, or security/.
- **Discovered Test Functions (5)**:
  - [`TestAgentRegistryAndSelector::test_default_built_in_agents`](file:///e:/JakeAI/backend/tests/test_agent_registry_and_selector.py#L1): Direct assertion (3 assertions)
  - [`TestAgentRegistryAndSelector::test_find_by_capability`](file:///e:/JakeAI/backend/tests/test_agent_registry_and_selector.py#L1): Direct assertion (4 assertions)
  - [`TestAgentRegistryAndSelector::test_selector_matches_financial_step`](file:///e:/JakeAI/backend/tests/test_agent_registry_and_selector.py#L1): Direct assertion (3 assertions)
  - [`TestAgentRegistryAndSelector::test_selector_falls_back_to_general_agent_for_unknown_capability`](file:///e:/JakeAI/backend/tests/test_agent_registry_and_selector.py#L1): Direct assertion (3 assertions)
  - [`TestAgentRegistryAndSelector::test_selector_enforces_tenant_boundary`](file:///e:/JakeAI/backend/tests/test_agent_registry_and_selector.py#L1): Direct assertion (1 assertions)

#### `CAT-015`: [`test_execution_engine_and_adapters.py`](file:///e:/JakeAI/backend/tests/test_execution_engine_and_adapters.py)
- **Test File Path**: `backend/tests/test_execution_engine_and_adapters.py` (584 lines)
- **Subsystem**: `Agent Orchestration`
- **Test Level**: `Unit`
- **Purpose**: Integration tests for Canonical ExecutionEngine and LangGraphExecutionAdapter.
- **Dependencies / Fixtures**: None (Pure In-Memory)
- **CI Job Execution**: `unit-and-ai-tests (Full Suite Floor)`
- **Recommended Run Frequency**: `PR / Push (main)`
- **Duplicate / Overlap Classification**: `COMPLEMENTARY`
- **RIGHT Test Suite Coverage**: `R-FUNC-01 / R-AI-00 / R-ARCH-00`
- **Bruno Collection Coverage**: `NONE`
- **Architectural Disposition**: **`MOVE`** (Target Destination: `backend/tests/unit/`)
- **Disposition Rationale & Evidence**: Valuable subsystem test. Needs reclassification into unit/, integration/, or security/.
- **Discovered Test Functions (11)**:
  - [`test_scenario_1_simple_question`](file:///e:/JakeAI/backend/tests/test_execution_engine_and_adapters.py#L1): Scenario 1: Simple direct question complete lifecycle. (6 assertions)
  - [`test_scenario_2_tool_banking_analysis`](file:///e:/JakeAI/backend/tests/test_execution_engine_and_adapters.py#L1): Scenario 2: Tool-required banking analysis with FinnApiGo. (3 assertions)
  - [`test_scenario_3_parallel_independent_steps`](file:///e:/JakeAI/backend/tests/test_execution_engine_and_adapters.py#L1): Scenario 3: Multi-source independent steps run concurrently via asyncio.gather. (2 assertions)
  - [`test_scenario_4_approval_pause_boundary`](file:///e:/JakeAI/backend/tests/test_execution_engine_and_adapters.py#L1): Scenario 4: Dangerous tool execution triggers approval pause boundary. (4 assertions)
  - [`test_scenario_4_approval_resume_to_completion`](file:///e:/JakeAI/backend/tests/test_execution_engine_and_adapters.py#L1): Scenario 4: Dangerous tool execution pauses, then resumes to completion upon approval. (8 assertions)
  - [`test_scenario_5_model_failure_and_switch`](file:///e:/JakeAI/backend/tests/test_execution_engine_and_adapters.py#L1): Scenario 5: Model provider rate-limit failure triggers model switch and recovery. (3 assertions)
  - [`test_scenario_6_tool_failure_and_retry`](file:///e:/JakeAI/backend/tests/test_execution_engine_and_adapters.py#L1): Scenario 6: Tool execution failure triggers step retry and self-healing recovery. (3 assertions)
  - [`test_scenario_7_verification_failure_and_replan`](file:///e:/JakeAI/backend/tests/test_execution_engine_and_adapters.py#L1): Scenario 7: Verification critique triggers replan loop and self-correction. (3 assertions)
  - [`test_scenario_8_cross_tenant_isolation_rejected`](file:///e:/JakeAI/backend/tests/test_execution_engine_and_adapters.py#L1): Scenario 8: Cross-tenant isolation breach attempt is immediately REJECTED. (3 assertions)
  - [`test_scenario_9_checkpoint_recovery_process_restart`](file:///e:/JakeAI/backend/tests/test_execution_engine_and_adapters.py#L1): Scenario 9: Process restart recovery from durable checkpoint via resume_run. (8 assertions)
  - [`test_langgraph_execution_adapter_parity`](file:///e:/JakeAI/backend/tests/test_execution_engine_and_adapters.py#L1): Test LangGraphExecutionAdapter executes canonical TaskSpec and yields canonical events. (3 assertions)

#### `CAT-023`: [`test_multi_agent.py`](file:///e:/JakeAI/backend/tests/test_multi_agent.py)
- **Test File Path**: `backend/tests/test_multi_agent.py` (342 lines)
- **Subsystem**: `Agent Orchestration`
- **Test Level**: `Integration (Component)`
- **Purpose**: Unit and integration tests for LangGraph multi-agent orchestration.
- **Dependencies / Fixtures**: HTTP / ASGI, Mocks / Monkeypatch
- **CI Job Execution**: `unit-and-ai-tests (Full Suite Floor)`
- **Recommended Run Frequency**: `PR / Push (main)`
- **Duplicate / Overlap Classification**: `COMPLEMENTARY`
- **RIGHT Test Suite Coverage**: `R-FUNC-01 / R-AI-00 / R-ARCH-00`
- **Bruno Collection Coverage**: `NONE`
- **Architectural Disposition**: **`MOVE`** (Target Destination: `backend/tests/unit/`)
- **Disposition Rationale & Evidence**: Valuable subsystem test. Needs reclassification into unit/, integration/, or security/.
- **Discovered Test Functions (12)**:
  - [`test_supervisor_intent_classification`](file:///e:/JakeAI/backend/tests/test_multi_agent.py#L1): Verify intent classifier directs queries to appropriate specialized nodes. (5 assertions)
  - [`test_financial_specialist_node`](file:///e:/JakeAI/backend/tests/test_multi_agent.py#L1): Verify Financial Specialist extracts figures and computes formulas. (6 assertions)
  - [`test_financial_specialist_node_formatted_currencies`](file:///e:/JakeAI/backend/tests/test_multi_agent.py#L1): Verify Financial Specialist extracts comma-separated currency values. (3 assertions)
  - [`test_finnapigo_tool_node`](file:///e:/JakeAI/backend/tests/test_multi_agent.py#L1): Verify FinnApiGo Tool Executor dispatches authenticated upstream calls. (5 assertions)
  - [`test_verifier_critique_and_pass`](file:///e:/JakeAI/backend/tests/test_multi_agent.py#L1): Verify Verifier critiques arithmetic variance and passes grounded data. (5 assertions)
  - [`test_synthesizer_node`](file:///e:/JakeAI/backend/tests/test_multi_agent.py#L1): Verify Synthesizer formats Markdown reports with citations. (5 assertions)
  - [`test_end_to_end_graph_execution`](file:///e:/JakeAI/backend/tests/test_multi_agent.py#L1): Verify complete LangGraph traversal from supervisor through synthesizer. (5 assertions)
  - [`test_stream_multi_agent_workflow`](file:///e:/JakeAI/backend/tests/test_multi_agent.py#L1): Verify async streaming generator yields incremental node events. (3 assertions)
  - [`test_chat_sse_stream_multi_agent`](file:///e:/JakeAI/backend/tests/test_multi_agent.py#L1): Verify /api/v1/chat/stream delivers multi-agent LangGraph SSE frames. (7 assertions)
  - [`test_branch_supervisor_to_finnapigo_tool`](file:///e:/JakeAI/backend/tests/test_multi_agent.py#L1): Verify Branch 2: supervisor -> finnapigo_tool -> verifier -> synthesizer. (6 assertions)
  - [`test_branch_supervisor_to_synthesizer_direct`](file:///e:/JakeAI/backend/tests/test_multi_agent.py#L1): Verify Branch 3: supervisor -> synthesizer (direct general inquiry routing). (5 assertions)
  - [`test_branch_verifier_critique_revision_loop`](file:///e:/JakeAI/backend/tests/test_multi_agent.py#L1): Verify Branch 4: verifier -> supervisor critique/revision loop on variance. (10 assertions)

#### `CAT-027`: [`test_orchestration_contracts.py`](file:///e:/JakeAI/backend/tests/test_orchestration_contracts.py)
- **Test File Path**: `backend/tests/test_orchestration_contracts.py` (286 lines)
- **Subsystem**: `Agent Orchestration`
- **Test Level**: `Contract`
- **Purpose**: Unit tests for canonical orchestration domain contracts and state machine.
- **Dependencies / Fixtures**: None (Pure In-Memory)
- **CI Job Execution**: `unit-and-ai-tests (Full Suite Floor)`
- **Recommended Run Frequency**: `PR / Push (main)`
- **Duplicate / Overlap Classification**: `UNIQUE`
- **RIGHT Test Suite Coverage**: `R-FUNC-01 / R-AI-00 / R-ARCH-00`
- **Bruno Collection Coverage**: `NONE`
- **Architectural Disposition**: **`MOVE`** (Target Destination: `backend/tests/contract/`)
- **Disposition Rationale & Evidence**: API/Internal contract test. Move to contract/.
- **Discovered Test Functions (12)**:
  - [`TestTaskSpecContract::test_valid_task_spec`](file:///e:/JakeAI/backend/tests/test_orchestration_contracts.py#L1): Direct assertion (5 assertions)
  - [`TestTaskSpecContract::test_task_spec_empty_goal_fails`](file:///e:/JakeAI/backend/tests/test_orchestration_contracts.py#L1): Direct assertion (0 assertions)
  - [`TestTaskSpecContract::test_task_spec_empty_tenant_fails`](file:///e:/JakeAI/backend/tests/test_orchestration_contracts.py#L1): Direct assertion (0 assertions)
  - [`TestExecutionPlanContract::test_plan_dependency_and_runnable_steps`](file:///e:/JakeAI/backend/tests/test_orchestration_contracts.py#L1): Direct assertion (10 assertions)
  - [`TestExecutionPlanContract::test_plan_independent_step_tiers`](file:///e:/JakeAI/backend/tests/test_orchestration_contracts.py#L1): Direct assertion (3 assertions)
  - [`TestExecutionContextContract::test_tenant_matching_assertion`](file:///e:/JakeAI/backend/tests/test_orchestration_contracts.py#L1): Direct assertion (1 assertions)
  - [`TestStepResultContract::test_step_result_creation`](file:///e:/JakeAI/backend/tests/test_orchestration_contracts.py#L1): Direct assertion (4 assertions)
  - [`TestVerificationResultContract::test_verification_result_verdicts`](file:///e:/JakeAI/backend/tests/test_orchestration_contracts.py#L1): Direct assertion (3 assertions)
  - [`TestRecoveryDecisionContract::test_recovery_decision_actions`](file:///e:/JakeAI/backend/tests/test_orchestration_contracts.py#L1): Direct assertion (2 assertions)
  - [`TestTerminalRunSemantics::test_terminal_status_flags`](file:///e:/JakeAI/backend/tests/test_orchestration_contracts.py#L1): Terminal-outcome semantics live on the canonical RunStatus machine. (7 assertions)
  - [`TestTerminalRunSemantics::test_non_terminal_statuses_are_not_terminal`](file:///e:/JakeAI/backend/tests/test_orchestration_contracts.py#L1): Terminal-outcome semantics live on the canonical RunStatus machine. (1 assertions)
  - [`TestRunStateTransitions::test_valid_and_invalid_state_transitions`](file:///e:/JakeAI/backend/tests/test_orchestration_contracts.py#L1): Direct assertion (12 assertions)

#### `CAT-028`: [`test_orchestration_planner.py`](file:///e:/JakeAI/backend/tests/test_orchestration_planner.py)
- **Test File Path**: `backend/tests/test_orchestration_planner.py` (124 lines)
- **Subsystem**: `Agent Orchestration`
- **Test Level**: `Unit`
- **Purpose**: Unit tests for canonical BoundedPlanner, DAG generation, dependency resolution, and replanning.
- **Dependencies / Fixtures**: None (Pure In-Memory)
- **CI Job Execution**: `unit-and-ai-tests (Full Suite Floor)`
- **Recommended Run Frequency**: `PR / Push (main)`
- **Duplicate / Overlap Classification**: `COMPLEMENTARY`
- **RIGHT Test Suite Coverage**: `R-FUNC-01 / R-AI-00 / R-ARCH-00`
- **Bruno Collection Coverage**: `NONE`
- **Architectural Disposition**: **`MOVE`** (Target Destination: `backend/tests/unit/`)
- **Disposition Rationale & Evidence**: Valuable subsystem test. Needs reclassification into unit/, integration/, or security/.
- **Discovered Test Functions (4)**:
  - [`TestOrchestrationPlanner::test_single_step_direct_question`](file:///e:/JakeAI/backend/tests/test_orchestration_planner.py#L1): Direct assertion (4 assertions)
  - [`TestOrchestrationPlanner::test_banking_transfer_dag_dependencies`](file:///e:/JakeAI/backend/tests/test_orchestration_planner.py#L1): Direct assertion (4 assertions)
  - [`TestOrchestrationPlanner::test_parallel_multi_source_dag`](file:///e:/JakeAI/backend/tests/test_orchestration_planner.py#L1): Direct assertion (6 assertions)
  - [`TestOrchestrationPlanner::test_replanning_after_verifier_critique`](file:///e:/JakeAI/backend/tests/test_orchestration_planner.py#L1): Direct assertion (4 assertions)

#### `CAT-034`: [`test_r_ai_00_agent_correctness.py`](file:///e:/JakeAI/backend/tests/test_r_ai_00_agent_correctness.py)
- **Test File Path**: `backend/tests/test_r_ai_00_agent_correctness.py` (418 lines)
- **Subsystem**: `Agent Orchestration`
- **Test Level**: `Regression (RIGHT Verification)`
- **Purpose**: Regression tests for R-AI-00 — Agent Correctness (AI evaluation and self-healing).
- **Dependencies / Fixtures**: None (Pure In-Memory)
- **CI Job Execution**: `unit-and-ai-tests (Full Suite Floor)`
- **Recommended Run Frequency**: `PR / Push (main)`
- **Duplicate / Overlap Classification**: `COMPLEMENTARY`
- **RIGHT Test Suite Coverage**: `R-AI-00`
- **Bruno Collection Coverage**: `NONE`
- **Architectural Disposition**: **`MOVE`** (Target Destination: `backend/tests/unit/`)
- **Disposition Rationale & Evidence**: Authoritative RIGHT verification suite for R-AI-00. Move to dedicated integration/ or regression/ target folder.
- **Discovered Test Functions (12)**:
  - [`test_planner_paraphrased_financial_and_retrieval_decomposition`](file:///e:/JakeAI/backend/tests/test_r_ai_00_agent_correctness.py#L1): Paraphrased financial terms (treasury turnover, spending, outlays) trigger multi-step decomposition. (3 assertions)
  - [`test_planner_independent_parallel_steps_with_synthesis_dag`](file:///e:/JakeAI/backend/tests/test_r_ai_00_agent_correctness.py#L1): Multi-source request produces independent parallel steps followed by dependent synthesis. (4 assertions)
  - [`test_negative_constraint_detection`](file:///e:/JakeAI/backend/tests/test_r_ai_00_agent_correctness.py#L1): Verify negative constraint regex correctly detects prohibitions across domains. (9 assertions)
  - [`test_planner_respects_negative_constraints_for_tools`](file:///e:/JakeAI/backend/tests/test_r_ai_00_agent_correctness.py#L1): Planner excludes forbidden tools when user explicitly forbids terminal or banking. (2 assertions)
  - [`test_supervisor_intent_classification_with_negative_constraints`](file:///e:/JakeAI/backend/tests/test_r_ai_00_agent_correctness.py#L1): Supervisor classify_intent respects negative constraints, routing away from prohibited specialists. (4 assertions)
  - [`test_supervisor_model_driven_routing_priority`](file:///e:/JakeAI/backend/tests/test_r_ai_00_agent_correctness.py#L1): Supervisor prioritizes model-driven reasoning over regex patterns when backend is available. (2 assertions)
  - [`test_agent_selector_novel_general_task_falls_back_without_false_confidence`](file:///e:/JakeAI/backend/tests/test_r_ai_00_agent_correctness.py#L1): Novel task with no matching capabilities selects general_agent with fallback_used=True, NOT supervisor. (3 assertions)
  - [`test_agent_selector_respects_negative_constraints`](file:///e:/JakeAI/backend/tests/test_r_ai_00_agent_correctness.py#L1): Agent selector penalizes specialists when prompt contains negative constraints. (1 assertions)
  - [`test_model_router_resolves_default_without_literal_leak`](file:///e:/JakeAI/backend/tests/test_r_ai_00_agent_correctness.py#L1): Model router resolves requested_model='default' to a real candidate model based on workload. (4 assertions)
  - [`test_execution_engine_grounds_user_figures`](file:///e:/JakeAI/backend/tests/test_r_ai_00_agent_correctness.py#L1): Financial specialist in execution engine calculates metrics from user prompt figures, not hardcoded defaults. (5 assertions)
  - [`test_execution_engine_synthesizer_formats_all_accumulated_outputs`](file:///e:/JakeAI/backend/tests/test_r_ai_00_agent_correctness.py#L1): Synthesizer incorporates diverse accumulated outputs (not just revenue) in the final report. (4 assertions)
  - [`test_recovery_engine_classifies_unregistered_tool_as_non_retryable`](file:///e:/JakeAI/backend/tests/test_r_ai_00_agent_correctness.py#L1): Recovery engine does not waste retry budget on unregistered/unknown tools. (2 assertions)

#### `CAT-045`: [`test_r_func_01_agent_behavior.py`](file:///e:/JakeAI/backend/tests/test_r_func_01_agent_behavior.py)
- **Test File Path**: `backend/tests/test_r_func_01_agent_behavior.py` (1038 lines)
- **Subsystem**: `Agent Orchestration`
- **Test Level**: `Regression (RIGHT Verification)`
- **Purpose**: R-FUNC-01 — Agent Behavior Canonical Verification Test Suite.
- **Dependencies / Fixtures**: HTTP / ASGI
- **CI Job Execution**: `unit-and-ai-tests (Full Suite Floor)`
- **Recommended Run Frequency**: `PR / Push (main)`
- **Duplicate / Overlap Classification**: `COMPLEMENTARY`
- **RIGHT Test Suite Coverage**: `R-FUNC-01`
- **Bruno Collection Coverage**: `Bruno/03 — Agent (01-10)`
- **Architectural Disposition**: **`MOVE`** (Target Destination: `backend/tests/unit/`)
- **Disposition Rationale & Evidence**: Authoritative RIGHT verification suite for R-FUNC-01. Move to dedicated integration/ or regression/ target folder.
- **Discovered Test Functions (12)**:
  - [`test_scenario_01_simple_task_lifecycle`](file:///e:/JakeAI/backend/tests/test_r_func_01_agent_behavior.py#L1): SCENARIO 1: Simple task executes through complete canonical lifecycle. (13 assertions)
  - [`test_scenario_02_multistep_dependency_chain`](file:///e:/JakeAI/backend/tests/test_r_func_01_agent_behavior.py#L1): SCENARIO 2: Multi-step pipeline executes strictly in dependency order. (2 assertions)
  - [`test_scenario_03_concurrent_steps_with_synthesis`](file:///e:/JakeAI/backend/tests/test_r_func_01_agent_behavior.py#L1): SCENARIO 3: Two independent steps execute concurrently, followed by synthesis. (5 assertions)
  - [`test_scenario_04_dynamic_agent_selection_from_capabilities_and_model`](file:///e:/JakeAI/backend/tests/test_r_func_01_agent_behavior.py#L1): SCENARIO 4: Agent is selected dynamically by capabilities, not keyword only. (5 assertions)
  - [`test_scenario_05_dynamic_model_routing_and_usage_proof`](file:///e:/JakeAI/backend/tests/test_r_func_01_agent_behavior.py#L1): SCENARIO 5: Model router selects model/provider and StepResult captures real usage. (7 assertions)
  - [`test_scenario_06_tool_selection_validation_and_execution`](file:///e:/JakeAI/backend/tests/test_r_func_01_agent_behavior.py#L1): SCENARIO 6: Tool registry validates schema, evaluates policy, and executes tool. (8 assertions)
  - [`test_scenario_07_approval_pause_resume_via_persisted_state`](file:///e:/JakeAI/backend/tests/test_r_func_01_agent_behavior.py#L1): SCENARIO 7: Dangerous tool triggers approval gate, pauses cleanly, and resumes upon approval. (7 assertions)
  - [`test_scenario_08_verification_failure_replan_and_retry`](file:///e:/JakeAI/backend/tests/test_r_func_01_agent_behavior.py#L1): SCENARIO 8: Verification failure triggers replanning loop and subsequent pass. (5 assertions)
  - [`test_scenario_09_provider_transient_failure_bounded_retry`](file:///e:/JakeAI/backend/tests/test_r_func_01_agent_behavior.py#L1): SCENARIO 9: Provider 429 triggers bounded retry and succeeds on attempt 2. (4 assertions)
  - [`test_scenario_10_process_restart_resume_without_duplication`](file:///e:/JakeAI/backend/tests/test_r_func_01_agent_behavior.py#L1): SCENARIO 10: After process restart, resume skips already completed steps. (3 assertions)
  - [`test_scenario_11_step_timeout_and_cancellation`](file:///e:/JakeAI/backend/tests/test_r_func_01_agent_behavior.py#L1): SCENARIO 11: Cooperative cancellation cleanly terminates execution. (2 assertions)
  - [`test_scenario_12_http_api_endpoints_and_isolation`](file:///e:/JakeAI/backend/tests/test_r_func_01_agent_behavior.py#L1): SCENARIO 12: Public REST endpoints enforce tenant boundary and lifecycle contracts. (9 assertions)

#### `CAT-066`: [`test_resume_bridge.py`](file:///e:/JakeAI/backend/tests/test_resume_bridge.py)
- **Test File Path**: `backend/tests/test_resume_bridge.py` (395 lines)
- **Subsystem**: `Agent Orchestration`
- **Test Level**: `Integration (API / HTTP)`
- **Purpose**: Unit and integration tests for ADR-001 LangGraph interrupt checkpoint and resume bridge.
- **Dependencies / Fixtures**: Redis, Mocks / Monkeypatch
- **CI Job Execution**: `unit-and-ai-tests (Full Suite Floor)`
- **Recommended Run Frequency**: `PR / Push (main)`
- **Duplicate / Overlap Classification**: `COMPLEMENTARY`
- **RIGHT Test Suite Coverage**: `NONE`
- **Bruno Collection Coverage**: `NONE`
- **Architectural Disposition**: **`MOVE`** (Target Destination: `backend/tests/unit/`)
- **Disposition Rationale & Evidence**: Valuable subsystem test. Needs reclassification into unit/, integration/, or security/.
- **Discovered Test Functions (7)**:
  - [`test_resume_bridge_manager_lifecycle`](file:///e:/JakeAI/backend/tests/test_resume_bridge.py#L1): Validate save_checkpoint and resume_checkpoint in manager. (5 assertions)
  - [`test_resume_bridge_cross_tenant_isolation`](file:///e:/JakeAI/backend/tests/test_resume_bridge.py#L1): Validate Invariant 2: attempting to resume another tenant's checkpoint fails. (0 assertions)
  - [`test_resume_bridge_redis_mock_paths`](file:///e:/JakeAI/backend/tests/test_resume_bridge.py#L1): Verify Redis read, write, lock, and delete branches in ResumeBridgeManager. (7 assertions)
  - [`test_api_submit_tool_result_lifecycle`](file:///e:/JakeAI/backend/tests/test_resume_bridge.py#L1): POST /api/v1/coding/tool-result lifecycle with 200, 404, 409, and 403 codes. (7 assertions)
  - [`test_internal_resume_perimeter_security`](file:///e:/JakeAI/backend/tests/test_resume_bridge.py#L1): POST /internal/v1/coding/resume enforces Invariant 4 perimeter credentials and error mapping. (6 assertions)
  - [`test_resume_bridge_redis_lock_cleanup_and_error_branches`](file:///e:/JakeAI/backend/tests/test_resume_bridge.py#L1): Exercise Redis lock release on 404, 403, in-flight locks, and lock acquisition exceptions. (3 assertions)
  - [`test_resume_bridge_event_loop_validation_branches`](file:///e:/JakeAI/backend/tests/test_resume_bridge.py#L1): Verify loop rehydration in _get_redis for closed, active, and invalid client loops. (5 assertions)

#### `CAT-121`: [`test_eval_agent_automation.py`](file:///e:/JakeAI/backend/tests/evals/test_eval_agent_automation.py)
- **Test File Path**: `backend/tests/evals/test_eval_agent_automation.py` (500 lines)
- **Subsystem**: `Agent Orchestration`
- **Test Level**: `AI Eval / Benchmark`
- **Purpose**: Comprehensive automated evaluation for 14 agent orchestration dimensions (goal interpretation, plan structure, agent selection, model selection, tool selection, tool execution, verification, recovery, retry bounds, approval flow, resume integrity, cancellation, terminal state, failure truthfulness) plus versioned regression fixtures.
- **Dependencies / Fixtures**: None (Pure In-Memory)
- **CI Job Execution**: `AI Behavior, Agent, RAG & Hallucination Evaluation Gate (TEST-06)`
- **Recommended Run Frequency**: `PR / Push (main)`
- **Duplicate / Overlap Classification**: `UNIQUE`
- **RIGHT Test Suite Coverage**: `R-FUNC-01 / R-AI-00`
- **Bruno Collection Coverage**: `Bruno/03 — Agent (01-10)`
- **Architectural Disposition**: **`CREATED`** (Target Destination: `backend/tests/evals/`)
- **Disposition Rationale & Evidence**: New TEST-06 automated evaluation layer for 14 agent orchestration dimensions and versioned regression fixtures.
- **Discovered Test Functions (15)**:
  - [`test_eval_agent_01_goal_interpretation_and_constraint_extraction`](file:///e:/JakeAI/backend/tests/evals/test_eval_agent_automation.py#L1): Evaluate goal interpretation extracts objectives and respects negative tool constraints.
  - [`test_eval_agent_02_plan_structure_dag_acyclicity_and_dependencies`](file:///e:/JakeAI/backend/tests/evals/test_eval_agent_automation.py#L1): Evaluate plan DAG acyclicity, dependency validation, and parallel execution tiers.
  - [`test_eval_agent_03_agent_selection_and_fallback`](file:///e:/JakeAI/backend/tests/evals/test_eval_agent_automation.py#L1): Evaluate semantic agent selection chooses specialized agents and provides fallback with confidence.
  - [`test_eval_agent_04_model_selection_and_no_default_leak`](file:///e:/JakeAI/backend/tests/evals/test_eval_agent_automation.py#L1): Evaluate model router matches workload class and never exposes the literal token 'default'.
  - [`test_eval_agent_05_tool_selection_and_synonym_resolution`](file:///e:/JakeAI/backend/tests/evals/test_eval_agent_automation.py#L1): Evaluate semantic tool resolution understands synonyms and excludes forbidden tools.
  - [`test_eval_agent_06_tool_execution_and_schema_validation`](file:///e:/JakeAI/backend/tests/evals/test_eval_agent_automation.py#L1): Evaluate ToolRegistry enforces schema types, boundaries, and rejects unexpected properties fail-closed.
  - [`test_eval_agent_07_verification_mathematical_and_security_gate`](file:///e:/JakeAI/backend/tests/evals/test_eval_agent_automation.py#L1): Evaluate CanonicalVerifier catches discrepancies and mathematical variance.
  - [`test_eval_agent_08_recovery_error_taxonomy_classification`](file:///e:/JakeAI/backend/tests/evals/test_eval_agent_automation.py#L1): Evaluate recovery manager partitions errors into non-retryable vs retryable.
  - [`test_eval_agent_09_retry_bounds_and_budget_exhaustion`](file:///e:/JakeAI/backend/tests/evals/test_eval_agent_automation.py#L1): Evaluate recovery engine halts at max_retries and marks step FAILED without runaway looping.
  - [`test_eval_agent_10_approval_flow_and_toctou_defense`](file:///e:/JakeAI/backend/tests/evals/test_eval_agent_automation.py#L1): Evaluate dangerous tools pause in WAITING_APPROVAL and reject altered arguments upon resume.
  - [`test_eval_agent_11_resume_without_step_duplication`](file:///e:/JakeAI/backend/tests/evals/test_eval_agent_automation.py#L1): Evaluate checkpoint resume executes only pending steps without duplicating completed steps.
  - [`test_eval_agent_12_cancellation_halts_pipeline_immediately`](file:///e:/JakeAI/backend/tests/evals/test_eval_agent_automation.py#L1): Evaluate CANCELLED transitions halt execution and record clean cancellation metadata.
  - [`test_eval_agent_13_terminal_state_immutability`](file:///e:/JakeAI/backend/tests/evals/test_eval_agent_automation.py#L1): Evaluate terminal states are strictly absorbing and reject subsequent status mutations.
  - [`test_eval_agent_14_failure_truthfulness_no_false_success`](file:///e:/JakeAI/backend/tests/evals/test_eval_agent_automation.py#L1): Evaluate failed tasks accurately transition to FAILED and never emit COMPLETED.
  - [`test_eval_agent_versioned_fixtures_pass`](file:///e:/JakeAI/backend/tests/evals/test_eval_agent_automation.py#L1): Parameterized regression suite across all 15 versioned agent fixtures.

### 3.3 Subsystem: BYOK Security (1 Files)
#### `CAT-006`: [`test_byok.py`](file:///e:/JakeAI/backend/tests/test_byok.py)
- **Test File Path**: `backend/tests/test_byok.py` (549 lines)
- **Subsystem**: `BYOK Security`
- **Test Level**: `Unit`
- **Purpose**: Unit and integration tests for BYOK (Bring Your Own Key) & AES-256-GCM encryption.
- **Dependencies / Fixtures**: Redis, HTTP / ASGI, Mocks / Monkeypatch
- **CI Job Execution**: `unit-and-ai-tests (Full Suite Floor)`
- **Recommended Run Frequency**: `PR / Push (main)`
- **Duplicate / Overlap Classification**: `COMPLEMENTARY`
- **RIGHT Test Suite Coverage**: `R-FUNC-04`
- **Bruno Collection Coverage**: `Bruno/05 — BYOK & Providers (01-07)`
- **Architectural Disposition**: **`MOVE`** (Target Destination: `backend/tests/unit/`)
- **Disposition Rationale & Evidence**: Valuable subsystem test. Needs reclassification into unit/, integration/, or security/.
- **Discovered Test Functions (16)**:
  - [`test_byok_all_six_providers_lifecycle`](file:///e:/JakeAI/backend/tests/test_byok.py#L1): Verify full key lifecycle across all 6 supported providers: openai, anthropic, gemini, groq, deepseek, openrouter. (17 assertions)
  - [`test_byok_strict_tenant_isolation`](file:///e:/JakeAI/backend/tests/test_byok.py#L1): Verify strict multi-tenant isolation: Tenant B cannot read, invoke, or mutate Tenant A's keys. (6 assertions)
  - [`test_byok_quota_preserving_probe_and_format_validation`](file:///e:/JakeAI/backend/tests/test_byok.py#L1): Verify validation performs fast format check and lightweight probe without burning quota. (8 assertions)
  - [`test_byok_api_extended_lifecycle`](file:///e:/JakeAI/backend/tests/test_byok.py#L1): Verify extended REST API: validate candidate, store with validation, rotate, revoke, delete. (14 assertions)
  - [`test_byok_aes256_gcm_roundtrip`](file:///e:/JakeAI/backend/tests/test_byok.py#L1): Verify AES-256-GCM encryption and decryption roundtrip. (3 assertions)
  - [`test_byok_cross_tenant_isolation_fails`](file:///e:/JakeAI/backend/tests/test_byok.py#L1): Verify decryption fails when attempted by an unauthorized tenant (AAD mismatch). (0 assertions)
  - [`test_byok_corrupt_payload_fails`](file:///e:/JakeAI/backend/tests/test_byok.py#L1): Verify corrupt or truncated payload fails gracefully. (0 assertions)
  - [`test_byok_key_masking`](file:///e:/JakeAI/backend/tests/test_byok.py#L1): Verify provider key masking preserves privacy. (4 assertions)
  - [`test_byok_store_and_retrieve`](file:///e:/JakeAI/backend/tests/test_byok.py#L1): Verify storing and retrieving provider keys via BYOKManager. (8 assertions)
  - [`test_byok_api_endpoints`](file:///e:/JakeAI/backend/tests/test_byok.py#L1): Verify BYOK REST endpoints: POST, GET, DELETE. (11 assertions)
  - [`test_byok_network_probe_mocked`](file:///e:/JakeAI/backend/tests/test_byok.py#L1): Verify live HTTP probe responses (200, 401, 429, 500, timeout, network error). (12 assertions)
  - [`test_byok_zero_secret_leakage`](file:///e:/JakeAI/backend/tests/test_byok.py#L1): Verify raw API keys are never exposed in list responses or exception messages. (4 assertions)
  - [`test_byok_legacy_plain_ciphertext_backward_compat`](file:///e:/JakeAI/backend/tests/test_byok.py#L1): Verify backward compatibility when storage contains legacy raw base64 ciphertext. (3 assertions)
  - [`test_byok_corrupt_data_in_store_handled_gracefully`](file:///e:/JakeAI/backend/tests/test_byok.py#L1): Verify corrupt ciphertext in storage reports configured=False and status=corrupt without crashing. (3 assertions)
  - [`test_byok_redis_fallback_to_memory_when_redis_empty_or_errors`](file:///e:/JakeAI/backend/tests/test_byok.py#L1): Verify that when Redis is queried and returns None or errors, manager falls back to _memory_store. (3 assertions)
  - [`test_byok_unpack_corrupt_json_structure`](file:///e:/JakeAI/backend/tests/test_byok.py#L1): Verify that corrupt JSON within braces triggers safe fallback and debug logging. (2 assertions)

### 3.4 Subsystem: Contract & Schema (3 Files)
#### `CAT-043`: [`test_r_arch_04_contract_consistency.py`](file:///e:/JakeAI/backend/tests/test_r_arch_04_contract_consistency.py)
- **Test File Path**: `backend/tests/test_r_arch_04_contract_consistency.py` (342 lines)
- **Subsystem**: `Contract & Schema`
- **Test Level**: `Contract`
- **Purpose**: R-ARCH-04 — Contract Consistency Regression Test Suite.
- **Dependencies / Fixtures**: None (Pure In-Memory)
- **CI Job Execution**: `unit-and-ai-tests (Full Suite Floor)`
- **Recommended Run Frequency**: `PR / Push (main)`
- **Duplicate / Overlap Classification**: `COMPLEMENTARY`
- **RIGHT Test Suite Coverage**: `R-ARCH-04`
- **Bruno Collection Coverage**: `NONE`
- **Architectural Disposition**: **`MOVE`** (Target Destination: `backend/tests/contract/`)
- **Disposition Rationale & Evidence**: Authoritative RIGHT verification suite for R-ARCH-04. Move to dedicated integration/ or regression/ target folder.
- **Discovered Test Functions (13)**:
  - [`test_domain_plan_step_first_class_tool_attributes`](file:///e:/JakeAI/backend/tests/test_r_arch_04_contract_consistency.py#L1): PlanStep must have first-class typed tool_name and tool_args attributes. (5 assertions)
  - [`test_execution_plan_default_task_id_factory`](file:///e:/JakeAI/backend/tests/test_r_arch_04_contract_consistency.py#L1): ExecutionPlan and Plan subclasses must both supply default task_id. (4 assertions)
  - [`test_execution_engine_typed_step_tool_attributes`](file:///e:/JakeAI/backend/tests/test_r_arch_04_contract_consistency.py#L1): ExecutionEngine inspects step.tool_name and step.tool_args directly. (4 assertions)
  - [`test_run_state_roundtrip_preserves_tool_results_and_steps`](file:///e:/JakeAI/backend/tests/test_r_arch_04_contract_consistency.py#L1): RunState.to_agent_state and from_agent_state must preserve tool_results and steps. (15 assertions)
  - [`test_task_state_user_id_default_anonymous`](file:///e:/JakeAI/backend/tests/test_r_arch_04_contract_consistency.py#L1): TaskState must default user_id to 'anonymous', aligning with TaskSpec and ExecutionContext. (1 assertions)
  - [`test_checkpoint_record_mutable_defaults_isolated`](file:///e:/JakeAI/backend/tests/test_r_arch_04_contract_consistency.py#L1): StateCheckpointRecord.short_term_memory_snapshot must be an isolated list per instance. (2 assertions)
  - [`test_resume_bridge_mutable_defaults_isolated`](file:///e:/JakeAI/backend/tests/test_r_arch_04_contract_consistency.py#L1): BridgeCheckpointRecord and ResumedExecutionResult mutable dict defaults must be isolated. (2 assertions)
  - [`test_internal_resume_submission_conversation_id`](file:///e:/JakeAI/backend/tests/test_r_arch_04_contract_consistency.py#L1): InternalResumeSubmission contract supports optional conversation_id. (2 assertions)
  - [`test_agent_metrics_endpoint_response_model`](file:///e:/JakeAI/backend/tests/test_r_arch_04_contract_consistency.py#L1): GET /api/v1/agent/metrics specifies response_model=AgentMetricsSnapshot. (2 assertions)
  - [`test_streaming_sse_headers_contract`](file:///e:/JakeAI/backend/tests/test_r_arch_04_contract_consistency.py#L1): streaming_sse_headers produces standard headers with tenant and correlation tracking. (5 assertions)
  - [`test_provider_request_accepts_str_and_dict_response_format`](file:///e:/JakeAI/backend/tests/test_r_arch_04_contract_consistency.py#L1): ProviderRequest.response_format accepts str, dict, and None. (3 assertions)
  - [`test_provider_adapters_normalize_string_response_format`](file:///e:/JakeAI/backend/tests/test_r_arch_04_contract_consistency.py#L1): Provider adapters normalize string response_format='json_object' into dict. (3 assertions)
  - [`test_tool_selection_default_risk_level`](file:///e:/JakeAI/backend/tests/test_r_arch_04_contract_consistency.py#L1): ToolSelection.risk_level must default to 'read_only' within ToolRiskLevel. (2 assertions)

#### `CAT-074`: [`test_api_contract.py`](file:///e:/JakeAI/backend/tests/contract/test_api_contract.py)
- **Test File Path**: `backend/tests/contract/test_api_contract.py` (320 lines)
- **Subsystem**: `Contract & Schema`
- **Test Level**: `Contract`
- **Purpose**: Authoritative API Contract and Zero Schema Drift verification suite auditing all 51 public operations across 47 paths against OpenAPI 3.1.0 specification.
- **Dependencies / Fixtures**: None (Pure In-Memory)
- **CI Job Execution**: `API Breaking Change & Schema Drift Gate`
- **Recommended Run Frequency**: `PR / Push (main)`
- **Duplicate / Overlap Classification**: `UNIQUE`
- **RIGHT Test Suite Coverage**: `R-ARCH-04 / R-FUNC-00`
- **Bruno Collection Coverage**: `Bruno Collections (00-08)`
- **Architectural Disposition**: **`EXPANDED`** (Target Destination: `backend/tests/contract/`)
- **Disposition Rationale & Evidence**: Authoritative API contract gate expanded to systematically verify all 51 operations, parameters, request bodies, response models, auth rules, streaming headers, and breaking changes.
- **Discovered Test Functions (16)**:
  - [`test_openapi_schema_metadata`](file:///e:/JakeAI/backend/tests/contract/test_api_contract.py#L1): Validate OpenAPI document structure and info metadata. (4 assertions)
  - [`test_zero_schema_drift_runtime_vs_committed`](file:///e:/JakeAI/backend/tests/contract/test_api_contract.py#L1): Strict bidirectional zero-drift equality check between app.openapi() and openapi.json. (2 assertions)
  - [`test_security_schemes_registered`](file:///e:/JakeAI/backend/tests/contract/test_api_contract.py#L1): Verify FinnApiGoAuth Bearer security scheme registration in components. (2 assertions)
  - [`test_exact_51_public_operations_accounted`](file:///e:/JakeAI/backend/tests/contract/test_api_contract.py#L1): Verify total public operations count matches exactly 51 across all registered route paths. (2 assertions)
  - [`test_individual_operation_contract`](file:///e:/JakeAI/backend/tests/contract/test_api_contract.py#L1): Parameterized verification of method, path, status codes, and operationId for all 51 operations. (51 parameterized tests)
  - [`test_operation_path_parameter_bindings`](file:///e:/JakeAI/backend/tests/contract/test_api_contract.py#L1): Verify all path template placeholders ({run_id}, {task_id}, {provider}) match documented parameters. (3 assertions)
  - [`test_operation_authentication_contracts`](file:///e:/JakeAI/backend/tests/contract/test_api_contract.py#L1): Verify strict partition between protected (41 ops) and public/perimeter/webhook endpoints (10 ops). (3 assertions)
  - [`test_operation_request_body_contracts`](file:///e:/JakeAI/backend/tests/contract/test_api_contract.py#L1): Verify JSON and multipart/form-data request bodies, required fields, and schema bindings. (3 assertions)
  - [`test_operation_response_schema_contracts`](file:///e:/JakeAI/backend/tests/contract/test_api_contract.py#L1): Verify 200/201/202 responses define valid schema $ref or content representations. (2 assertions)
  - [`test_backward_compatibility_no_deleted_endpoints`](file:///e:/JakeAI/backend/tests/contract/test_api_contract.py#L1): Detect breaking changes: no previously published endpoint path may be deleted. (2 assertions)
  - [`test_backward_compatibility_no_removed_success_responses`](file:///e:/JakeAI/backend/tests/contract/test_api_contract.py#L1): Detect breaking changes: no success HTTP status code may be removed from any operation. (2 assertions)
  - [`test_backward_compatibility_no_new_required_request_fields`](file:///e:/JakeAI/backend/tests/contract/test_api_contract.py#L1): Detect breaking changes: existing request schemas cannot introduce new required fields without deprecation. (2 assertions)
  - [`test_chat_sse_contract`](file:///e:/JakeAI/backend/tests/contract/test_api_contract.py#L1): Verify Server-Sent Events contract for /api/v1/chat/stream. (5 assertions)
  - [`test_agent_run_events_sse_contract`](file:///e:/JakeAI/backend/tests/contract/test_api_contract.py#L1): Verify Server-Sent Events contract for /api/v1/agent/runs/{run_id}/events. (5 assertions)
  - [`test_rag_ingest_contract`](file:///e:/JakeAI/backend/tests/contract/test_api_contract.py#L1): Verify document ingestion contract for /api/v1/rag/ingest. (2 assertions)
  - [`test_metrics_snapshot_contract`](file:///e:/JakeAI/backend/tests/contract/test_api_contract.py#L1): Verify telemetry metrics endpoint contract and MetricsSnapshot schema (COST-13). (13 assertions)

#### `CAT-114`: [`test_api_negative_contracts.py`](file:///e:/JakeAI/backend/tests/contract/test_api_negative_contracts.py)
- **Test File Path**: `backend/tests/contract/test_api_negative_contracts.py` (310 lines)
- **Subsystem**: `Contract & Schema`
- **Test Level**: `Contract`
- **Purpose**: Negative contracts automation for 10 legitimate HTTP status codes (400, 401, 403, 404, 409, 413, 422, 429, 500, 503) at the ASGI application boundary.
- **Dependencies / Fixtures**: HTTP / ASGI, Mocks / Monkeypatch
- **CI Job Execution**: `API Breaking Change & Schema Drift Gate`
- **Recommended Run Frequency**: `PR / Push (main)`
- **Duplicate / Overlap Classification**: `UNIQUE`
- **RIGHT Test Suite Coverage**: `R-ARCH-04 / R-FUNC-00`
- **Bruno Collection Coverage**: `Bruno/08 — Security & Negative (01-11)`
- **Architectural Disposition**: **`CREATED`** (Target Destination: `backend/tests/contract/`)
- **Disposition Rationale & Evidence**: Canonical negative contract test suite. Verifies all 10 supported error status codes at the ASGI boundary with exact error schemas without invented codes.
- **Discovered Test Functions (27)**:
  - [`test_negative_400_bad_request_unsupported_byok_provider`](file:///e:/JakeAI/backend/tests/contract/test_api_negative_contracts.py#L1): 400 Bad Request on invalid BYOK provider. (3 assertions)
  - [`test_negative_400_bad_request_billing_webhook_invalid_hmac`](file:///e:/JakeAI/backend/tests/contract/test_api_negative_contracts.py#L1): 400 Bad Request on billing webhook invalid HMAC signature. (3 assertions)
  - [`test_negative_400_bad_request_provider_context_limit_mapping`](file:///e:/JakeAI/backend/tests/contract/test_api_negative_contracts.py#L1): 400 Bad Request when provider context limit is exceeded. (3 assertions)
  - [`test_negative_401_unauthorized_missing_bearer_token`](file:///e:/JakeAI/backend/tests/contract/test_api_negative_contracts.py#L1): 401 Unauthorized when Bearer token is missing. (3 assertions)
  - [`test_negative_401_unauthorized_malformed_token`](file:///e:/JakeAI/backend/tests/contract/test_api_negative_contracts.py#L1): 401 Unauthorized on garbage token strings. (2 assertions)
  - [`test_negative_401_unauthorized_expired_token`](file:///e:/JakeAI/backend/tests/contract/test_api_negative_contracts.py#L1): 401 Unauthorized on expired JWT tokens. (2 assertions)
  - [`test_negative_401_unauthorized_invalid_signature`](file:///e:/JakeAI/backend/tests/contract/test_api_negative_contracts.py#L1): 401 Unauthorized on forged JWT signatures. (2 assertions)
  - [`test_negative_401_unauthorized_wrong_token_type`](file:///e:/JakeAI/backend/tests/contract/test_api_negative_contracts.py#L1): 401 Unauthorized on non-access token types. (2 assertions)
  - [`test_negative_401_unauthorized_provider_auth_error_mapping`](file:///e:/JakeAI/backend/tests/contract/test_api_negative_contracts.py#L1): 401 Unauthorized on upstream provider authentication failures. (2 assertions)
  - [`test_negative_403_forbidden_missing_internal_perimeter_secret`](file:///e:/JakeAI/backend/tests/contract/test_api_negative_contracts.py#L1): 403 Forbidden when internal perimeter secret is missing. (2 assertions)
  - [`test_negative_403_forbidden_invalid_internal_perimeter_secret`](file:///e:/JakeAI/backend/tests/contract/test_api_negative_contracts.py#L1): 403 Forbidden when internal perimeter secret is invalid. (2 assertions)
  - [`test_negative_403_forbidden_cross_tenant_tool_resumption`](file:///e:/JakeAI/backend/tests/contract/test_api_negative_contracts.py#L1): 403 Forbidden on cross-tenant tool resumption attempts. (3 assertions)
  - [`test_negative_403_forbidden_cross_tenant_agent_task_access`](file:///e:/JakeAI/backend/tests/contract/test_api_negative_contracts.py#L1): 403 Forbidden on cross-tenant agent task inspection. (2 assertions)
  - [`test_negative_404_not_found_nonexistent_agent_task`](file:///e:/JakeAI/backend/tests/contract/test_api_negative_contracts.py#L1): 404 Not Found on nonexistent agent task ID. (2 assertions)
  - [`test_negative_404_not_found_nonexistent_agent_run`](file:///e:/JakeAI/backend/tests/contract/test_api_negative_contracts.py#L1): 404 Not Found on nonexistent agent run ID. (2 assertions)
  - [`test_negative_404_not_found_nonexistent_rag_task`](file:///e:/JakeAI/backend/tests/contract/test_api_negative_contracts.py#L1): 404 Not Found on nonexistent RAG ingestion task ID. (2 assertions)
  - [`test_negative_404_not_found_nonexistent_byok_provider_key`](file:///e:/JakeAI/backend/tests/contract/test_api_negative_contracts.py#L1): 404 Not Found on nonexistent BYOK provider key. (2 assertions)
  - [`test_negative_409_conflict_duplicate_tool_result_submission`](file:///e:/JakeAI/backend/tests/contract/test_api_negative_contracts.py#L1): 409 Conflict when submitting tool result for already resumed execution. (3 assertions)
  - [`test_negative_409_conflict_agent_approval_already_resolved`](file:///e:/JakeAI/backend/tests/contract/test_api_negative_contracts.py#L1): 409 Conflict when submitting decision for already finalized approval. (2 assertions)
  - [`test_negative_413_payload_too_large_exceeding_body_limit`](file:///e:/JakeAI/backend/tests/contract/test_api_negative_contracts.py#L1): 413 Payload Too Large when request body exceeds MAX_REQUEST_BODY_BYTES. (2 assertions)
  - [`test_negative_422_missing_required_fields`](file:///e:/JakeAI/backend/tests/contract/test_api_negative_contracts.py#L1): 422 Unprocessable Entity when required JSON schema fields are omitted. (3 assertions)
  - [`test_negative_422_out_of_bounds_parameters`](file:///e:/JakeAI/backend/tests/contract/test_api_negative_contracts.py#L1): 422 Unprocessable Entity when parameters violate validation constraints. (2 assertions)
  - [`test_negative_422_query_parameter_type_mismatch`](file:///e:/JakeAI/backend/tests/contract/test_api_negative_contracts.py#L1): 422 Unprocessable Entity when query parameter data type is invalid. (2 assertions)
  - [`test_negative_429_too_many_requests_tenant_quota_exceeded`](file:///e:/JakeAI/backend/tests/contract/test_api_negative_contracts.py#L1): 429 Too Many Requests when tenant token/dollar quota is exhausted. (3 assertions)
  - [`test_negative_429_too_many_requests_provider_rate_limit_with_retry_after`](file:///e:/JakeAI/backend/tests/contract/test_api_negative_contracts.py#L1): 429 Too Many Requests with Retry-After header propagation. (3 assertions)
  - [`test_negative_500_internal_server_error_preserves_correlation_id`](file:///e:/JakeAI/backend/tests/contract/test_api_negative_contracts.py#L1): 500 Internal Server Error returns standard envelope and preserves correlation ID without leaking stack trace. (4 assertions)
  - [`test_negative_503_service_unavailable_provider_outage`](file:///e:/JakeAI/backend/tests/contract/test_api_negative_contracts.py#L1): 503 Service Unavailable when all upstream providers in fallback chain fail. (3 assertions)

#### `CAT-115`: [`test_api_http_workflows.py`](file:///e:/JakeAI/backend/tests/contract/test_api_http_workflows.py)
- **Test File Path**: `backend/tests/contract/test_api_http_workflows.py` (475 lines)
- **Subsystem**: `Contract & Schema`
- **Test Level**: `Contract`
- **Purpose**: Real ASGI HTTP boundary verification of 5 critical representative workflows across JakeAI capabilities.
- **Dependencies / Fixtures**: Redis, Qdrant, HTTP / ASGI, Mocks / Monkeypatch
- **CI Job Execution**: `API Breaking Change & Schema Drift Gate`
- **Recommended Run Frequency**: `PR / Push (main)`
- **Duplicate / Overlap Classification**: `UNIQUE`
- **RIGHT Test Suite Coverage**: `R-FUNC-00 / R-ARCH-04`
- **Bruno Collection Coverage**: `Bruno Collections (01-08)`
- **Architectural Disposition**: **`CREATED`** (Target Destination: `backend/tests/contract/`)
- **Disposition Rationale & Evidence**: End-to-end multi-request HTTP workflow contracts exercising full ASGI request/response lifecycles, tenant isolation, and async streams.
- **Discovered Test Functions (5)**:
  - [`test_workflow_1_agent_task_lifecycle_and_streaming`](file:///e:/JakeAI/backend/tests/contract/test_api_http_workflows.py#L1): Workflow 1: Create Task -> Inspect Task -> Trigger Execution Run -> Stream SSE Events -> Get Completed Run -> Retrieve Artifacts. (14 assertions)
  - [`test_workflow_2_rag_ingestion_hybrid_retrieval_and_query`](file:///e:/JakeAI/backend/tests/contract/test_api_http_workflows.py#L1): Workflow 2: Synchronous Document Ingest -> Asynchronous Document Ingest -> Task Status Polling -> RAG Search -> Grounded Query. (12 assertions)
  - [`test_workflow_3_byok_credential_lifecycle`](file:///e:/JakeAI/backend/tests/contract/test_api_http_workflows.py#L1): Workflow 3: Probe Candidate Key -> Store AES-256 Key -> List Configured Keys -> Rotate Key -> Revoke Key -> Delete Key. (18 assertions)
  - [`test_workflow_4_gateway_inference_and_finops_accounting`](file:///e:/JakeAI/backend/tests/contract/test_api_http_workflows.py#L1): Workflow 4: Model Discovery -> Query Quotas -> Synchronous Chat Completion -> Streaming Chat Completion -> Update Quota -> Set Budget -> FinOps Summary. (14 assertions)
  - [`test_workflow_5_human_in_the_loop_and_tool_resume_bridge`](file:///e:/JakeAI/backend/tests/contract/test_api_http_workflows.py#L1): Workflow 5: Create Approval Request -> List Approvals -> Submit Decision -> Checkpoint Creation -> Tool Result Submission -> Internal Resume Bridge. (14 assertions)

#### `CAT-095`: [`test_structured_conversation_contract.py`](file:///e:/JakeAI/backend/tests/unit/test_structured_conversation_contract.py)
- **Test File Path**: `backend/tests/unit/test_structured_conversation_contract.py` (759 lines)
- **Subsystem**: `Contract & Schema`
- **Test Level**: `Contract`
- **Purpose**: Comprehensive Regression and Contract Tests for REPAIR-01 (PROV-02).
- **Dependencies / Fixtures**: Mocks / Monkeypatch
- **CI Job Execution**: `unit-and-ai-tests (Full Suite Floor)`
- **Recommended Run Frequency**: `PR / Push (main)`
- **Duplicate / Overlap Classification**: `UNIQUE`
- **RIGHT Test Suite Coverage**: `R-ARCH-04`
- **Bruno Collection Coverage**: `NONE`
- **Architectural Disposition**: **`MOVE`** (Target Destination: `backend/tests/contract/`)
- **Disposition Rationale & Evidence**: API/Internal contract test. Move to contract/.
- **Discovered Test Functions (28)**:
  - [`TestProviderRequestContract::test_provider_request_with_structured_messages`](file:///e:/JakeAI/backend/tests/unit/test_structured_conversation_contract.py#L1): ProviderRequest accepts structured messages and auto-populates prompt from last user turn. (3 assertions)
  - [`TestProviderRequestContract::test_provider_request_backward_compatibility_single_prompt`](file:///e:/JakeAI/backend/tests/unit/test_structured_conversation_contract.py#L1): Single-prompt callers without messages remain fully functional. (3 assertions)
  - [`TestProviderRequestContract::test_provider_request_explicit_prompt_preserved`](file:///e:/JakeAI/backend/tests/unit/test_structured_conversation_contract.py#L1): When prompt is explicitly provided alongside messages, it is not overwritten. (2 assertions)
  - [`TestFiveTurnConversation::test_openai_five_turn`](file:///e:/JakeAI/backend/tests/unit/test_structured_conversation_contract.py#L1): Validate that 5-turn conversations preserve all turns across all 6 provider adapters. (13 assertions)
  - [`TestFiveTurnConversation::test_deepseek_five_turn`](file:///e:/JakeAI/backend/tests/unit/test_structured_conversation_contract.py#L1): Validate that 5-turn conversations preserve all turns across all 6 provider adapters. (3 assertions)
  - [`TestFiveTurnConversation::test_groq_five_turn`](file:///e:/JakeAI/backend/tests/unit/test_structured_conversation_contract.py#L1): Validate that 5-turn conversations preserve all turns across all 6 provider adapters. (3 assertions)
  - [`TestFiveTurnConversation::test_openrouter_five_turn`](file:///e:/JakeAI/backend/tests/unit/test_structured_conversation_contract.py#L1): Validate that 5-turn conversations preserve all turns across all 6 provider adapters. (3 assertions)
  - [`TestFiveTurnConversation::test_anthropic_five_turn`](file:///e:/JakeAI/backend/tests/unit/test_structured_conversation_contract.py#L1): Validate that 5-turn conversations preserve all turns across all 6 provider adapters. (9 assertions)
  - [`TestFiveTurnConversation::test_gemini_five_turn`](file:///e:/JakeAI/backend/tests/unit/test_structured_conversation_contract.py#L1): Validate that 5-turn conversations preserve all turns across all 6 provider adapters. (8 assertions)
  - [`TestAssistantRecallPreservation::test_assistant_recall_openai`](file:///e:/JakeAI/backend/tests/unit/test_structured_conversation_contract.py#L1): Validate that assistant prior responses are faithfully preserved across adapters. (1 assertions)
  - [`TestAssistantRecallPreservation::test_assistant_recall_anthropic`](file:///e:/JakeAI/backend/tests/unit/test_structured_conversation_contract.py#L1): Validate that assistant prior responses are faithfully preserved across adapters. (1 assertions)
  - [`TestAssistantRecallPreservation::test_assistant_recall_gemini`](file:///e:/JakeAI/backend/tests/unit/test_structured_conversation_contract.py#L1): Validate that assistant prior responses are faithfully preserved across adapters. (1 assertions)
  - [`TestSystemInstructionPreservation::test_system_instruction_via_message`](file:///e:/JakeAI/backend/tests/unit/test_structured_conversation_contract.py#L1): Validate system instructions preservation via message history and top-level field. (3 assertions)
  - [`TestSystemInstructionPreservation::test_system_instruction_via_top_level_field`](file:///e:/JakeAI/backend/tests/unit/test_structured_conversation_contract.py#L1): Validate system instructions preservation via message history and top-level field. (2 assertions)
  - [`TestSystemInstructionPreservation::test_system_instruction_anthropic_ephemeral_cache`](file:///e:/JakeAI/backend/tests/unit/test_structured_conversation_contract.py#L1): Validate system instructions preservation via message history and top-level field. (3 assertions)
  - [`TestToolMessagePreservation::test_tool_preservation_openai`](file:///e:/JakeAI/backend/tests/unit/test_structured_conversation_contract.py#L1): Validate that assistant tool_calls and tool messages preserve IDs and arguments. (8 assertions)
  - [`TestToolMessagePreservation::test_tool_preservation_anthropic`](file:///e:/JakeAI/backend/tests/unit/test_structured_conversation_contract.py#L1): Validate that assistant tool_calls and tool messages preserve IDs and arguments. (8 assertions)
  - [`TestToolMessagePreservation::test_tool_preservation_gemini`](file:///e:/JakeAI/backend/tests/unit/test_structured_conversation_contract.py#L1): Validate that assistant tool_calls and tool messages preserve IDs and arguments. (4 assertions)
  - [`TestOrderingPreservation::test_ordering_openai`](file:///e:/JakeAI/backend/tests/unit/test_structured_conversation_contract.py#L1): Validate that message order is strictly preserved without reordering. (2 assertions)
  - [`TestOrderingPreservation::test_ordering_gemini`](file:///e:/JakeAI/backend/tests/unit/test_structured_conversation_contract.py#L1): Validate that message order is strictly preserved without reordering. (2 assertions)
  - [`TestSinglePromptBackwardCompatibility::test_openai_single_prompt`](file:///e:/JakeAI/backend/tests/unit/test_structured_conversation_contract.py#L1): Validate that existing single-prompt callers without messages function identically. (5 assertions)
  - [`TestSinglePromptBackwardCompatibility::test_anthropic_single_prompt`](file:///e:/JakeAI/backend/tests/unit/test_structured_conversation_contract.py#L1): Validate that existing single-prompt callers without messages function identically. (2 assertions)
  - [`TestSinglePromptBackwardCompatibility::test_gemini_single_prompt`](file:///e:/JakeAI/backend/tests/unit/test_structured_conversation_contract.py#L1): Validate that existing single-prompt callers without messages function identically. (2 assertions)
  - [`TestGatewayMultiTurnDispatch::test_gateway_dispatches_full_messages`](file:///e:/JakeAI/backend/tests/unit/test_structured_conversation_contract.py#L1): Validate that GatewayInferenceProxy correctly receives and forwards multi-turn messages. (8 assertions)
  - [`TestAgentBackendStructuredMessages::test_jakeai_backend_dispatches_structured_messages`](file:///e:/JakeAI/backend/tests/unit/test_structured_conversation_contract.py#L1): Validate that JakeAIBackend constructs and passes structured ChatMessage objects. (9 assertions)
  - [`TestDirectFormatterFunctions::test_direct_format_openai_with_and_without_messages`](file:///e:/JakeAI/backend/tests/unit/test_structured_conversation_contract.py#L1): Validate direct invocation of canonical format helper functions. (2 assertions)
  - [`TestDirectFormatterFunctions::test_direct_format_anthropic_with_and_without_messages`](file:///e:/JakeAI/backend/tests/unit/test_structured_conversation_contract.py#L1): Validate direct invocation of canonical format helper functions. (4 assertions)
  - [`TestDirectFormatterFunctions::test_direct_format_gemini_with_and_without_messages`](file:///e:/JakeAI/backend/tests/unit/test_structured_conversation_contract.py#L1): Validate direct invocation of canonical format helper functions. (4 assertions)

### 3.5 Subsystem: Core / Platform (25 Files)
#### `CAT-001`: [`conftest.py`](file:///e:/JakeAI/backend/tests/conftest.py)
- **Test File Path**: `backend/tests/conftest.py` (16 lines)
- **Subsystem**: `Core / Platform`
- **Test Level**: `Unit`
- **Purpose**: Pytest fixtures and test environment configuration.
- **Dependencies / Fixtures**: HTTP / ASGI
- **CI Job Execution**: `unit-and-ai-tests (Full Suite Floor)`
- **Recommended Run Frequency**: `PR / Push (main)`
- **Duplicate / Overlap Classification**: `UNIQUE`
- **RIGHT Test Suite Coverage**: `NONE`
- **Bruno Collection Coverage**: `NONE`
- **Architectural Disposition**: **`MOVE`** (Target Destination: `backend/tests/fixtures/`)
- **Disposition Rationale & Evidence**: Root shared ASGI test client fixture. Should be moved to fixtures/.
- **Discovered Test Functions (0)**:

#### `CAT-004`: [`test_architecture_invariants.py`](file:///e:/JakeAI/backend/tests/test_architecture_invariants.py)
- **Test File Path**: `backend/tests/test_architecture_invariants.py` (209 lines)
- **Subsystem**: `Core / Platform`
- **Test Level**: `Unit`
- **Purpose**: Unit and architecture invariant tests for JakeAI Orchestration Capability (WORK-01).
- **Dependencies / Fixtures**: None (Pure In-Memory)
- **CI Job Execution**: `unit-and-ai-tests (Full Suite Floor)`
- **Recommended Run Frequency**: `PR / Push (main)`
- **Duplicate / Overlap Classification**: `COMPLEMENTARY`
- **RIGHT Test Suite Coverage**: `R-ARCH-00 / R-LOGIC-00`
- **Bruno Collection Coverage**: `NONE`
- **Architectural Disposition**: **`MOVE`** (Target Destination: `backend/tests/unit/`)
- **Disposition Rationale & Evidence**: Valuable subsystem test. Needs reclassification into unit/, integration/, or security/.
- **Discovered Test Functions (6)**:
  - [`TestArchitectureInvariants::test_invariant_1_single_task_and_run_contracts`](file:///e:/JakeAI/backend/tests/test_architecture_invariants.py#L1): Invariant 1: Exactly ONE authoritative TaskSpec and RunState, with lossless translation to AgentState. (9 assertions)
  - [`TestArchitectureInvariants::test_invariant_2_single_model_router_authority`](file:///e:/JakeAI/backend/tests/test_architecture_invariants.py#L1): Invariant 2: ModelRouter is the sole routing authority across all execution paths. (4 assertions)
  - [`TestArchitectureInvariants::test_invariant_3_single_tool_registry_authority`](file:///e:/JakeAI/backend/tests/test_architecture_invariants.py#L1): Invariant 3: ToolRegistry is the sole registry and policy gateway for all tools. (3 assertions)
  - [`TestArchitectureInvariants::test_invariant_4_single_verification_authority`](file:///e:/JakeAI/backend/tests/test_architecture_invariants.py#L1): Invariant 4: CanonicalVerifier is the sole verification authority, used directly by LangGraph. (3 assertions)
  - [`TestArchitectureInvariants::test_invariant_5_non_degradable_multi_tenant_isolation`](file:///e:/JakeAI/backend/tests/test_architecture_invariants.py#L1): Invariant 5: Multi-tenant boundary mismatch is a non-degradable hard PermissionError. (2 assertions)
  - [`TestArchitectureInvariants::test_invariant_6_bounded_execution_ceilings`](file:///e:/JakeAI/backend/tests/test_architecture_invariants.py#L1): Invariant 6: Strict iteration and retry bounds prevent unbounded execution or infinite loops. (4 assertions)

#### `CAT-007`: [`test_circuit_breaker.py`](file:///e:/JakeAI/backend/tests/test_circuit_breaker.py)
- **Test File Path**: `backend/tests/test_circuit_breaker.py` (125 lines)
- **Subsystem**: `Core / Platform`
- **Test Level**: `Unit`
- **Purpose**: Unit tests for Circuit Breaker and Fallback Routing.
- **Dependencies / Fixtures**: None (Pure In-Memory)
- **CI Job Execution**: `unit-and-ai-tests (Full Suite Floor)`
- **Recommended Run Frequency**: `PR / Push (main)`
- **Duplicate / Overlap Classification**: `COMPLEMENTARY`
- **RIGHT Test Suite Coverage**: `NONE`
- **Bruno Collection Coverage**: `NONE`
- **Architectural Disposition**: **`MOVE`** (Target Destination: `backend/tests/unit/`)
- **Disposition Rationale & Evidence**: Valuable subsystem test. Needs reclassification into unit/, integration/, or security/.
- **Discovered Test Functions (5)**:
  - [`test_circuit_breaker_normal_closed_execution`](file:///e:/JakeAI/backend/tests/test_circuit_breaker.py#L1): Verify standard execution through primary provider when circuit is CLOSED. (4 assertions)
  - [`test_circuit_breaker_trips_to_open_and_uses_fallback`](file:///e:/JakeAI/backend/tests/test_circuit_breaker.py#L1): Verify circuit trips to OPEN after threshold failures and triggers secondary fallback. (8 assertions)
  - [`test_deterministic_safe_fallback_when_all_providers_fail`](file:///e:/JakeAI/backend/tests/test_circuit_breaker.py#L1): Verify zero 500 errors by returning deterministic safe fallback. (2 assertions)
  - [`test_circuit_breaker_recovery_to_half_open_and_closed`](file:///e:/JakeAI/backend/tests/test_circuit_breaker.py#L1): Verify recovery from OPEN to HALF_OPEN after timeout and back to CLOSED after success. (6 assertions)
  - [`test_circuit_breaker_raises_when_no_fallback`](file:///e:/JakeAI/backend/tests/test_circuit_breaker.py#L1): Verify CircuitBreakerOpenException or error raised when no fallbacks provided. (0 assertions)

#### `CAT-008`: [`test_commercial_services.py`](file:///e:/JakeAI/backend/tests/test_commercial_services.py)
- **Test File Path**: `backend/tests/test_commercial_services.py` (248 lines)
- **Subsystem**: `Core / Platform`
- **Test Level**: `Unit`
- **Purpose**: Unit and integration tests for AI Gateway, PayOS Billing, and Analytics Dashboard.
- **Dependencies / Fixtures**: HTTP / ASGI, Mocks / Monkeypatch
- **CI Job Execution**: `unit-and-ai-tests (Full Suite Floor)`
- **Recommended Run Frequency**: `PR / Push (main)`
- **Duplicate / Overlap Classification**: `COMPLEMENTARY`
- **RIGHT Test Suite Coverage**: `NONE`
- **Bruno Collection Coverage**: `NONE`
- **Architectural Disposition**: **`MOVE`** (Target Destination: `backend/tests/unit/`)
- **Disposition Rationale & Evidence**: Valuable subsystem test. Needs reclassification into unit/, integration/, or security/.
- **Discovered Test Functions (4)**:
  - [`test_quota_manager_lifecycle`](file:///e:/JakeAI/backend/tests/test_commercial_services.py#L1): Verify quota tracking, soft alerting at 80%, and hard suspension at 100%. (10 assertions)
  - [`test_gateway_inference_proxy_caching`](file:///e:/JakeAI/backend/tests/test_commercial_services.py#L1): Verify inference proxy caches responses via Tier 1 exact match cache. (6 assertions)
  - [`test_payos_signature_and_webhook`](file:///e:/JakeAI/backend/tests/test_commercial_services.py#L1): Verify PayOS HMAC-SHA256 signature verification and automatic subscription provisioning. (9 assertions)
  - [`test_commercial_api_endpoints`](file:///e:/JakeAI/backend/tests/test_commercial_services.py#L1): Verify REST endpoints for Gateway proxy, quotas, billing, and analytics. (16 assertions)

#### `CAT-011`: [`test_cross_tier_pipeline.py`](file:///e:/JakeAI/backend/tests/test_cross_tier_pipeline.py)
- **Test File Path**: `backend/tests/test_cross_tier_pipeline.py` (485 lines)
- **Subsystem**: `Core / Platform`
- **Test Level**: `Integration (Component)`
- **Purpose**: Comprehensive Integration & Verification Tests for Tier 5 -> 6 -> 7 -> 5 Pipeline.
- **Dependencies / Fixtures**: None (Pure In-Memory)
- **CI Job Execution**: `unit-and-ai-tests (Full Suite Floor)`
- **Recommended Run Frequency**: `PR / Push (main)`
- **Duplicate / Overlap Classification**: `COMPLEMENTARY`
- **RIGHT Test Suite Coverage**: `R-FUNC-03 / R-AI-02`
- **Bruno Collection Coverage**: `NONE`
- **Architectural Disposition**: **`MOVE`** (Target Destination: `backend/tests/unit/`)
- **Disposition Rationale & Evidence**: Valuable subsystem test. Needs reclassification into unit/, integration/, or security/.
- **Discovered Test Functions (12)**:
  - [`test_dynamic_change_does_not_change_static_prefix`](file:///e:/JakeAI/backend/tests/test_cross_tier_pipeline.py#L1): Section 5 Mandatory Integration Test: Static prefix remains byte-identical. (2 assertions)
  - [`test_static_change_invalidates_prefix_hash`](file:///e:/JakeAI/backend/tests/test_cross_tier_pipeline.py#L1): Section 16: Changing static information MUST invalidate static prefix hash. (2 assertions)
  - [`test_tier6_output_measured_by_tier7_bpe`](file:///e:/JakeAI/backend/tests/test_cross_tier_pipeline.py#L1): Sections 6 & 7: Every Tier 6 optimization must be measurable by Tier 7 BPE tokenizer. (6 assertions)
  - [`test_context_budget_enforcement_accepts_when_tier6_fits`](file:///e:/JakeAI/backend/tests/test_cross_tier_pipeline.py#L1): Section 9: Raw context exceeds budget, but Tier 6 optimization brings it within budget. (3 assertions)
  - [`test_context_budget_enforcement_fails_safely_when_still_overflowing`](file:///e:/JakeAI/backend/tests/test_cross_tier_pipeline.py#L1): Section 9: When even optimized context exceeds budget, fails safely without truncation. (1 assertions)
  - [`test_fail_closed_fallback_on_malformed_syntax`](file:///e:/JakeAI/backend/tests/test_cross_tier_pipeline.py#L1): Section 13: Tier 6 encounters malformed syntax and falls back closed to original context. (4 assertions)
  - [`test_provider_cache_telemetry_reconciliation_rule1`](file:///e:/JakeAI/backend/tests/test_cross_tier_pipeline.py#L1): Sections 14, 17, 18: Authoritative provider usage telemetry and FinOps cost reconciliation. (6 assertions)
  - [`test_concurrency_and_tenant_isolation`](file:///e:/JakeAI/backend/tests/test_cross_tier_pipeline.py#L1): Section 27 & 31: Concurrent requests across tenants do not leak context or hashes. (3 assertions)
  - [`test_property4_no_corruption_output_valid_ast`](file:///e:/JakeAI/backend/tests/test_cross_tier_pipeline.py#L1): Property 4: Transformed code must remain syntactically valid Python (parseable by ast.parse). (2 assertions)
  - [`test_provider_request_payload_inspection_anthropic_vs_openai`](file:///e:/JakeAI/backend/tests/test_cross_tier_pipeline.py#L1): Section 25: Verify actual provider-specific request payload structure. (3 assertions)
  - [`test_streaming_pipeline_reconciliation`](file:///e:/JakeAI/backend/tests/test_cross_tier_pipeline.py#L1): Section 26: Streaming request token accounting reconciliation. (4 assertions)
  - [`test_chaos_failure_injection_degrades_safely`](file:///e:/JakeAI/backend/tests/test_cross_tier_pipeline.py#L1): Section 30: Chaos / Failure injection degrades safely without crashing. (3 assertions)

#### `CAT-013`: [`test_durable_checkpointing.py`](file:///e:/JakeAI/backend/tests/test_durable_checkpointing.py)
- **Test File Path**: `backend/tests/test_durable_checkpointing.py` (129 lines)
- **Subsystem**: `Core / Platform`
- **Test Level**: `Unit`
- **Purpose**: Tests for Durable Redis Checkpointing (TASK ORC-05).
- **Dependencies / Fixtures**: Redis, Mocks / Monkeypatch
- **CI Job Execution**: `unit-and-ai-tests (Full Suite Floor)`
- **Recommended Run Frequency**: `PR / Push (main)`
- **Duplicate / Overlap Classification**: `COMPLEMENTARY`
- **RIGHT Test Suite Coverage**: `NONE`
- **Bruno Collection Coverage**: `NONE`
- **Architectural Disposition**: **`MOVE`** (Target Destination: `backend/tests/unit/`)
- **Disposition Rationale & Evidence**: Valuable subsystem test. Needs reclassification into unit/, integration/, or security/.
- **Discovered Test Functions (2)**:
  - [`test_durable_checkpointing_lifecycle`](file:///e:/JakeAI/backend/tests/test_durable_checkpointing.py#L1): Validate save, load, delete, and resume in CheckpointManager. (11 assertions)
  - [`test_durable_checkpointing_survives_process_restart_via_redis`](file:///e:/JakeAI/backend/tests/test_durable_checkpointing.py#L1): Simulate complete process memory loss: state is restored from Redis. (9 assertions)

#### `CAT-022`: [`test_local_provider.py`](file:///e:/JakeAI/backend/tests/test_local_provider.py)
- **Test File Path**: `backend/tests/test_local_provider.py` (147 lines)
- **Subsystem**: `Core / Platform`
- **Test Level**: `Unit`
- **Purpose**: Unit tests for COST-12: Local Model Provider Adapter and Health Probing.
- **Dependencies / Fixtures**: HTTP / ASGI, Mocks / Monkeypatch
- **CI Job Execution**: `unit-and-ai-tests (Full Suite Floor)`
- **Recommended Run Frequency**: `PR / Push (main)`
- **Duplicate / Overlap Classification**: `COMPLEMENTARY`
- **RIGHT Test Suite Coverage**: `R-FUNC-04`
- **Bruno Collection Coverage**: `NONE`
- **Architectural Disposition**: **`MOVE`** (Target Destination: `backend/tests/unit/`)
- **Disposition Rationale & Evidence**: Valuable subsystem test. Needs reclassification into unit/, integration/, or security/.
- **Discovered Test Functions (7)**:
  - [`test_local_model_capabilities_and_pricing`](file:///e:/JakeAI/backend/tests/test_local_provider.py#L1): Verify LocalModelAdapter returns valid capabilities with non-zero operational cost. (7 assertions)
  - [`test_local_model_health_check_success`](file:///e:/JakeAI/backend/tests/test_local_provider.py#L1): Verify check_health returns True when endpoint is reachable. (2 assertions)
  - [`test_local_model_health_check_failure`](file:///e:/JakeAI/backend/tests/test_local_provider.py#L1): Verify check_health marks provider unhealthy on connection failure. (2 assertions)
  - [`test_local_model_complete_execution`](file:///e:/JakeAI/backend/tests/test_local_provider.py#L1): Verify complete parses response and computes non-zero operational cost. (5 assertions)
  - [`test_local_model_timeout_raises_provider_timeout_error`](file:///e:/JakeAI/backend/tests/test_local_provider.py#L1): Verify timeout is normalized into typed ProviderTimeoutError. (0 assertions)
  - [`test_local_model_connection_error_raises_unavailable`](file:///e:/JakeAI/backend/tests/test_local_provider.py#L1): Verify connection error raises ProviderUnavailableError and marks provider unhealthy. (1 assertions)
  - [`test_local_model_registry_resolution`](file:///e:/JakeAI/backend/tests/test_local_provider.py#L1): Verify local provider is registered and resolved in ProviderRegistry. (4 assertions)

#### `CAT-026`: [`test_orc_capabilities.py`](file:///e:/JakeAI/backend/tests/test_orc_capabilities.py)
- **Test File Path**: `backend/tests/test_orc_capabilities.py` (221 lines)
- **Subsystem**: `Core / Platform`
- **Test Level**: `Unit`
- **Purpose**: Targeted unit tests for AI Orchestration capabilities ORC-09, ORC-10, and ORC-11.
- **Dependencies / Fixtures**: None (Pure In-Memory)
- **CI Job Execution**: `unit-and-ai-tests (Full Suite Floor)`
- **Recommended Run Frequency**: `PR / Push (main)`
- **Duplicate / Overlap Classification**: `REVIEW`
- **RIGHT Test Suite Coverage**: `NONE`
- **Bruno Collection Coverage**: `NONE`
- **Architectural Disposition**: **`MERGE`** (Target Destination: `backend/tests/unit/`)
- **Disposition Rationale & Evidence**: Contains asyncio.sleep(5.0). Tests ORC-09/10/11 features that overlap test_agent_platform.py. Eliminate sleeps and merge.
- **Discovered Test Functions (4)**:
  - [`test_orc_09_planner_memory_recall`](file:///e:/JakeAI/backend/tests/test_orc_capabilities.py#L1): ORC-09: Planner recalls tenant episodic memories and injects them into system prompt. (5 assertions)
  - [`test_orc_09_loop_remembers_episodic_on_finish`](file:///e:/JakeAI/backend/tests/test_orc_capabilities.py#L1): ORC-09: Execution loop persists completed goal into episodic memory. (6 assertions)
  - [`test_orc_10_runner_active_task_cancellation`](file:///e:/JakeAI/backend/tests/test_orc_capabilities.py#L1): ORC-10: Runner tracks active asyncio task and cancels it cleanly upon cancellation request. (4 assertions)
  - [`test_orc_11_dynamic_model_selection`](file:///e:/JakeAI/backend/tests/test_orc_capabilities.py#L1): ORC-11: Custom default_model in AgentConfig propagates dynamically to backend and planner. (4 assertions)

#### `CAT-031`: [`test_provider_failover_credentials.py`](file:///e:/JakeAI/backend/tests/test_provider_failover_credentials.py)
- **Test File Path**: `backend/tests/test_provider_failover_credentials.py` (229 lines)
- **Subsystem**: `Core / Platform`
- **Test Level**: `Unit`
- **Purpose**: Unit tests verifying provider failover credential isolation (COST-01 & COST-11).
- **Dependencies / Fixtures**: HTTP / ASGI
- **CI Job Execution**: `unit-and-ai-tests (Full Suite Floor)`
- **Recommended Run Frequency**: `PR / Push (main)`
- **Duplicate / Overlap Classification**: `COMPLEMENTARY`
- **RIGHT Test Suite Coverage**: `R-FUNC-04`
- **Bruno Collection Coverage**: `NONE`
- **Architectural Disposition**: **`MOVE`** (Target Destination: `backend/tests/unit/`)
- **Disposition Rationale & Evidence**: Valuable subsystem test. Needs reclassification into unit/, integration/, or security/.
- **Discovered Test Functions (3)**:
  - [`test_failover_credentials_isolated_and_resolved_for_fallback`](file:///e:/JakeAI/backend/tests/test_provider_failover_credentials.py#L1): COST-01: Primary API key is not passed to fallback provider. (7 assertions)
  - [`test_failover_does_not_repeat_failed_candidates`](file:///e:/JakeAI/backend/tests/test_provider_failover_credentials.py#L1): COST-11: Fallback candidate is not repeated even if present twice in fallback_chain. (2 assertions)
  - [`test_failover_credentials_isolated_without_resolver`](file:///e:/JakeAI/backend/tests/test_provider_failover_credentials.py#L1): COST-01: Without resolver, fallback candidate never receives primary API key. (4 assertions)

#### `CAT-032`: [`test_provider_foundation.py`](file:///e:/JakeAI/backend/tests/test_provider_foundation.py)
- **Test File Path**: `backend/tests/test_provider_foundation.py` (1149 lines)
- **Subsystem**: `Core / Platform`
- **Test Level**: `Unit`
- **Purpose**: Comprehensive Unit and Contract Tests for Phase 01 — Provider Foundation.
- **Dependencies / Fixtures**: HTTP / ASGI, Mocks / Monkeypatch
- **CI Job Execution**: `unit-and-ai-tests (Full Suite Floor)`
- **Recommended Run Frequency**: `PR / Push (main)`
- **Duplicate / Overlap Classification**: `COMPLEMENTARY`
- **RIGHT Test Suite Coverage**: `R-FUNC-04`
- **Bruno Collection Coverage**: `NONE`
- **Architectural Disposition**: **`MOVE`** (Target Destination: `backend/tests/unit/`)
- **Disposition Rationale & Evidence**: Valuable subsystem test. Needs reclassification into unit/, integration/, or security/.
- **Discovered Test Functions (24)**:
  - [`test_provider_protocol_conformance`](file:///e:/JakeAI/backend/tests/test_provider_foundation.py#L1): Verify all 6 provider adapters adhere to the LLMProvider protocol. (6 assertions)
  - [`test_provider_registry_resolution`](file:///e:/JakeAI/backend/tests/test_provider_foundation.py#L1): Verify ProviderRegistry correctly resolves models to their respective adapters. (7 assertions)
  - [`test_model_capabilities_explicit_catalog`](file:///e:/JakeAI/backend/tests/test_provider_foundation.py#L1): Verify explicit capabilities are returned without relying on string matching. (23 assertions)
  - [`test_error_normalization_classification`](file:///e:/JakeAI/backend/tests/test_provider_foundation.py#L1): Verify exact categorization across all required error classes. (22 assertions)
  - [`test_zero_credential_leakage_invariant`](file:///e:/JakeAI/backend/tests/test_provider_foundation.py#L1): Verify API keys, tokens, and authorization headers are scrubbed from all errors. (7 assertions)
  - [`test_model_router_observable_decision`](file:///e:/JakeAI/backend/tests/test_provider_foundation.py#L1): Verify ModelRouter generates explicit, observable RoutingDecisions with reasons. (9 assertions)
  - [`test_model_router_reasoning_workload`](file:///e:/JakeAI/backend/tests/test_provider_foundation.py#L1): Verify router selects reasoning model when required capability is specified. (2 assertions)
  - [`test_model_router_budget_enforcement`](file:///e:/JakeAI/backend/tests/test_provider_foundation.py#L1): Verify router automatically down-tiers when input cost exceeds budget. (3 assertions)
  - [`test_model_router_disallowed_provider`](file:///e:/JakeAI/backend/tests/test_provider_foundation.py#L1): Verify router respects disallowed providers and avoids them in primary and fallback. (2 assertions)
  - [`test_failover_non_retryable_aborts_retries`](file:///e:/JakeAI/backend/tests/test_provider_foundation.py#L1): Verify non-retryable error (e.g. 401 Auth) terminates provider attempts immediately. (1 assertions)
  - [`test_failover_retryable_recovers_with_backoff`](file:///e:/JakeAI/backend/tests/test_provider_foundation.py#L1): Verify retryable 503 error retries up to threshold and succeeds on retry. (2 assertions)
  - [`test_failover_cross_provider_fallback_chain`](file:///e:/JakeAI/backend/tests/test_provider_foundation.py#L1): Verify execution falls back to secondary provider candidate when primary fails. (2 assertions)
  - [`test_call_upstream_llm_detailed_backward_compatibility`](file:///e:/JakeAI/backend/tests/test_provider_foundation.py#L1): Verify call_upstream_llm_detailed dispatches through new provider foundation. (7 assertions)
  - [`test_call_upstream_llm_convenience_wrapper`](file:///e:/JakeAI/backend/tests/test_provider_foundation.py#L1): Verify call_upstream_llm string convenience wrapper functions seamlessly. (1 assertions)
  - [`test_anthropic_adapter_complete_and_stream`](file:///e:/JakeAI/backend/tests/test_provider_foundation.py#L1): Test AnthropicAdapter execution, caching metrics, and streaming. (6 assertions)
  - [`test_openai_adapter_complete_and_stream`](file:///e:/JakeAI/backend/tests/test_provider_foundation.py#L1): Test OpenAIAdapter execution, structured tools, and streaming. (5 assertions)
  - [`test_gemini_adapter_complete_and_stream`](file:///e:/JakeAI/backend/tests/test_provider_foundation.py#L1): Test GeminiAdapter execution, cached content telemetry, and streaming. (4 assertions)
  - [`test_groq_adapter_complete_and_stream`](file:///e:/JakeAI/backend/tests/test_provider_foundation.py#L1): Test GroqAdapter LPU inference and streaming. (5 assertions)
  - [`test_deepseek_adapter_complete_and_stream`](file:///e:/JakeAI/backend/tests/test_provider_foundation.py#L1): Test DeepSeekAdapter 64-token prefix cache handling and streaming. (4 assertions)
  - [`test_openrouter_adapter_complete_and_stream`](file:///e:/JakeAI/backend/tests/test_provider_foundation.py#L1): Test OpenRouterAdapter headers, routing, and streaming. (4 assertions)
  - [`test_registry_methods_extended`](file:///e:/JakeAI/backend/tests/test_provider_foundation.py#L1): Verify registry provider listing, capability retrieval, and fallback resolution. (9 assertions)
  - [`test_router_constraints_and_downgrades_extended`](file:///e:/JakeAI/backend/tests/test_provider_foundation.py#L1): Verify router constraint enforcement, reasoning rerouting, and cost downgrading. (10 assertions)
  - [`test_failover_limits_and_unexpected_errors`](file:///e:/JakeAI/backend/tests/test_provider_foundation.py#L1): Test skipping unregistered providers, unexpected crash wrapping, and total fallback exhaustion. (3 assertions)
  - [`test_errors_additional_branches`](file:///e:/JakeAI/backend/tests/test_provider_foundation.py#L1): Test 400 bad syntax, generic network error, and unmapped status fallback. (3 assertions)

#### `CAT-033`: [`test_provider_prompt_caching.py`](file:///e:/JakeAI/backend/tests/test_provider_prompt_caching.py)
- **Test File Path**: `backend/tests/test_provider_prompt_caching.py` (479 lines)
- **Subsystem**: `Core / Platform`
- **Test Level**: `Unit`
- **Purpose**: Comprehensive Unit and Contract Tests for Tier 5: Provider Prompt Caching.
- **Dependencies / Fixtures**: Redis, Qdrant, HTTP / ASGI, Mocks / Monkeypatch
- **CI Job Execution**: `unit-and-ai-tests (Full Suite Floor)`
- **Recommended Run Frequency**: `PR / Push (main)`
- **Duplicate / Overlap Classification**: `COMPLEMENTARY`
- **RIGHT Test Suite Coverage**: `R-FUNC-04`
- **Bruno Collection Coverage**: `NONE`
- **Architectural Disposition**: **`MOVE`** (Target Destination: `backend/tests/unit/`)
- **Disposition Rationale & Evidence**: Valuable subsystem test. Needs reclassification into unit/, integration/, or security/.
- **Discovered Test Functions (10)**:
  - [`test_provider_cache_policy_classification`](file:///e:/JakeAI/backend/tests/test_provider_prompt_caching.py#L1): Verifies that all provider families are correctly categorized per Tier 5 specs. (15 assertions)
  - [`test_cache_miss_reason_attribution`](file:///e:/JakeAI/backend/tests/test_provider_prompt_caching.py#L1): Verifies fine-grained cache miss reason attribution. (8 assertions)
  - [`test_provider_pricing_and_savings_calculation`](file:///e:/JakeAI/backend/tests/test_provider_prompt_caching.py#L1): Verifies accurate FinOps token cost accounting and discount calculations. (7 assertions)
  - [`test_anthropic_cache_control_and_telemetry`](file:///e:/JakeAI/backend/tests/test_provider_prompt_caching.py#L1): Verifies Anthropic adapter sends cache_control and parses read/write usage. (12 assertions)
  - [`test_openai_cached_tokens_telemetry`](file:///e:/JakeAI/backend/tests/test_provider_prompt_caching.py#L1): Verifies OpenAI adapter correctly parses prompt_tokens_details.cached_tokens. (6 assertions)
  - [`test_rule_1_never_fake_cache_hits`](file:///e:/JakeAI/backend/tests/test_provider_prompt_caching.py#L1): RULE 1 TEST: Identical local prefix hashes MUST NEVER be reported as a provider cache HIT (5 assertions)
  - [`test_three_cache_systems_separation`](file:///e:/JakeAI/backend/tests/test_provider_prompt_caching.py#L1): RULE 10 TEST: Strictly separates Layer A (JakeAI Redis/Qdrant) and Layer B (Provider Prompt Cache). (3 assertions)
  - [`test_get_model_pricing_heuristics`](file:///e:/JakeAI/backend/tests/test_provider_prompt_caching.py#L1): Verifies pricing model resolution and fallback heuristics. (6 assertions)
  - [`test_gemini_cached_tokens_telemetry`](file:///e:/JakeAI/backend/tests/test_provider_prompt_caching.py#L1): Verifies Gemini adapter parses usageMetadata and cachedContentTokenCount. (7 assertions)
  - [`test_provider_adapters_interface`](file:///e:/JakeAI/backend/tests/test_provider_prompt_caching.py#L1): Verifies all provider adapters implement the ProviderPromptCacheAdapter contract. (10 assertions)

#### `CAT-037`: [`test_r_ai_03_tool_correctness.py`](file:///e:/JakeAI/backend/tests/test_r_ai_03_tool_correctness.py)
- **Test File Path**: `backend/tests/test_r_ai_03_tool_correctness.py` (803 lines)
- **Subsystem**: `Core / Platform`
- **Test Level**: `Regression (RIGHT Verification)`
- **Purpose**: Comprehensive verification test suite for R-AI-03: Tool Correctness.
- **Dependencies / Fixtures**: HTTP / ASGI
- **CI Job Execution**: `unit-and-ai-tests (Full Suite Floor)`
- **Recommended Run Frequency**: `PR / Push (main)`
- **Duplicate / Overlap Classification**: `COMPLEMENTARY`
- **RIGHT Test Suite Coverage**: `R-AI-03`
- **Bruno Collection Coverage**: `NONE`
- **Architectural Disposition**: **`MOVE`** (Target Destination: `backend/tests/unit/`)
- **Disposition Rationale & Evidence**: Authoritative RIGHT verification suite for R-AI-03. Move to dedicated integration/ or regression/ target folder.
- **Discovered Test Functions (16)**:
  - [`test_scenario_01_semantic_paraphrases_and_synonyms_tool_choice`](file:///e:/JakeAI/backend/tests/test_r_ai_03_tool_correctness.py#L1): FinnApiGo specialist node correctly maps semantic paraphrases to appropriate tools. (2 assertions)
  - [`test_scenario_02_pre_set_state_tool_and_arguments_preservation`](file:///e:/JakeAI/backend/tests/test_r_ai_03_tool_correctness.py#L1): Explicit tool_name and custom arguments in state take precedence over prompt heuristics. (2 assertions)
  - [`test_scenario_03_ambiguous_request_resolution`](file:///e:/JakeAI/backend/tests/test_r_ai_03_tool_correctness.py#L1): Ambiguous or generic queries safely default to primary account balance inspection. (2 assertions)
  - [`test_scenario_04_schema_validation_missing_required_arguments`](file:///e:/JakeAI/backend/tests/test_r_ai_03_tool_correctness.py#L1): ToolRegistry rejects tool invocations missing required parameters with clear errors. (9 assertions)
  - [`test_scenario_05_schema_validation_wrong_argument_types`](file:///e:/JakeAI/backend/tests/test_r_ai_03_tool_correctness.py#L1): ToolRegistry rejects wrong argument types before tool execution occurs. (14 assertions)
  - [`test_scenario_06_schema_validation_boundary_and_numeric_constraints`](file:///e:/JakeAI/backend/tests/test_r_ai_03_tool_correctness.py#L1): ToolRegistry rejects negative or zero numbers when minimum constraints are violated. (8 assertions)
  - [`test_scenario_07_malicious_shell_commands_policy_defense`](file:///e:/JakeAI/backend/tests/test_r_ai_03_tool_correctness.py#L1): ToolPolicyEngine blocks direct and chained destructive shell commands across all tools. (5 assertions)
  - [`test_scenario_08_path_traversal_and_sensitive_file_defense`](file:///e:/JakeAI/backend/tests/test_r_ai_03_tool_correctness.py#L1): ToolPolicyEngine blocks directory traversal and sensitive path inspections. (3 assertions)
  - [`test_scenario_09_unavailable_and_unregistered_tools_fail_safely`](file:///e:/JakeAI/backend/tests/test_r_ai_03_tool_correctness.py#L1): Invoking an unavailable/unregistered tool fails cleanly without unhandled crashes. (4 assertions)
  - [`test_scenario_10_unauthorized_tools_and_rbac_boundaries`](file:///e:/JakeAI/backend/tests/test_r_ai_03_tool_correctness.py#L1): RBAC guardrails and policy engine fail closed when permissions or roles are lacking. (5 assertions)
  - [`test_scenario_11_approval_required_dangerous_tools_lifecycle`](file:///e:/JakeAI/backend/tests/test_r_ai_03_tool_correctness.py#L1): Dangerous tools pause execution for approval, and proceed upon human authorization. (6 assertions)
  - [`test_scenario_12_toctou_argument_tampering_prevention`](file:///e:/JakeAI/backend/tests/test_r_ai_03_tool_correctness.py#L1): Altering arguments after approval was granted triggers TOCTOU security rejection. (3 assertions)
  - [`test_scenario_13_tool_execution_timeout_boundary`](file:///e:/JakeAI/backend/tests/test_r_ai_03_tool_correctness.py#L1): Tool exceeding timeout_seconds triggers clean asyncio.wait_for TimeoutError. (2 assertions)
  - [`test_scenario_14_tool_result_contamination_isolation`](file:///e:/JakeAI/backend/tests/test_r_ai_03_tool_correctness.py#L1): CanonicalVerifier isolates failed tool results and indirect prompt injection from grounding context. (2 assertions)
  - [`test_scenario_15_planner_pure_banking_and_code_inspection_plans`](file:///e:/JakeAI/backend/tests/test_r_ai_03_tool_correctness.py#L1): Planner generates structured tool-equipped DAG plans for pure banking and code exploration. (6 assertions)
  - [`test_scenario_16_public_http_agent_task_and_approval_api_boundary`](file:///e:/JakeAI/backend/tests/test_r_ai_03_tool_correctness.py#L1): Real ASGI HTTP client exercises task creation, run creation, and approval decision endpoints. (6 assertions)

#### `CAT-039`: [`test_r_arch_00_architecture_integrity.py`](file:///e:/JakeAI/backend/tests/test_r_arch_00_architecture_integrity.py)
- **Test File Path**: `backend/tests/test_r_arch_00_architecture_integrity.py` (549 lines)
- **Subsystem**: `Core / Platform`
- **Test Level**: `Regression (RIGHT Verification)`
- **Purpose**: R-ARCH-00 — Architecture Integrity regression suite.
- **Dependencies / Fixtures**: HTTP / ASGI, Mocks / Monkeypatch
- **CI Job Execution**: `unit-and-ai-tests (Full Suite Floor)`
- **Recommended Run Frequency**: `PR / Push (main)`
- **Duplicate / Overlap Classification**: `COMPLEMENTARY`
- **RIGHT Test Suite Coverage**: `R-ARCH-00`
- **Bruno Collection Coverage**: `NONE`
- **Architectural Disposition**: **`MOVE`** (Target Destination: `backend/tests/unit/`)
- **Disposition Rationale & Evidence**: Authoritative RIGHT verification suite for R-ARCH-00. Move to dedicated integration/ or regression/ target folder.
- **Discovered Test Functions (11)**:
  - [`test_no_module_level_import_cycles_in_app_package`](file:///e:/JakeAI/backend/tests/test_r_arch_00_architecture_integrity.py#L1): The orchestration packages must stay acyclic at module level. (1 assertions)
  - [`test_no_web_framework_imports_in_agent_domain`](file:///e:/JakeAI/backend/tests/test_r_arch_00_architecture_integrity.py#L1): Agent domain/orchestration layers must not import the web framework. (1 assertions)
  - [`test_langgraph_imports_confined_to_adapter_boundary`](file:///e:/JakeAI/backend/tests/test_r_arch_00_architecture_integrity.py#L1): LangGraph is an alternate execution *framework* and must stay an adapter. (1 assertions)
  - [`test_single_canonical_semantic_authority`](file:///e:/JakeAI/backend/tests/test_r_arch_00_architecture_integrity.py#L1): Each semantic authority must have exactly one canonical implementation. (1 assertions)
  - [`test_canonical_verifier_singleton_shared_by_all_drivers`](file:///e:/JakeAI/backend/tests/test_r_arch_00_architecture_integrity.py#L1): LangGraph nodes and the ExecutionEngine share one verification authority. (3 assertions)
  - [`test_langgraph_verifier_node_inherits_canonical_verdicts`](file:///e:/JakeAI/backend/tests/test_r_arch_00_architecture_integrity.py#L1): The graph verifier node delegates semantics to CanonicalVerifier verbatim. (6 assertions)
  - [`test_chat_sse_executes_canonical_orchestration_chain`](file:///e:/JakeAI/backend/tests/test_r_arch_00_architecture_integrity.py#L1): The public chat SSE stream runs the canonical chain over real HTTP. (5 assertions)
  - [`test_chat_tool_path_funnels_through_canonical_tool_registry`](file:///e:/JakeAI/backend/tests/test_r_arch_00_architecture_integrity.py#L1): Tool execution in the chat graph must go through ToolRegistry (no bypass). (6 assertions)
  - [`test_agent_backend_funnels_through_canonical_provider_dispatch`](file:///e:/JakeAI/backend/tests/test_r_arch_00_architecture_integrity.py#L1): The native agent runtime must dispatch upstream generation via llm_provider. (2 assertions)
  - [`test_synthesizer_generation_funnels_through_canonical_provider_dispatch`](file:///e:/JakeAI/backend/tests/test_r_arch_00_architecture_integrity.py#L1): The graph synthesizer's free-form generation must use llm_provider too. (4 assertions)
  - [`test_agent_rest_enforces_canonical_state_machine_and_isolation`](file:///e:/JakeAI/backend/tests/test_r_arch_00_architecture_integrity.py#L1): The agent REST platform enforces RunState ownership and tenant isolation. (9 assertions)

#### `CAT-040`: [`test_r_arch_01_canonical_authority.py`](file:///e:/JakeAI/backend/tests/test_r_arch_01_canonical_authority.py)
- **Test File Path**: `backend/tests/test_r_arch_01_canonical_authority.py` (374 lines)
- **Subsystem**: `Core / Platform`
- **Test Level**: `Regression (RIGHT Verification)`
- **Purpose**: R-ARCH-01 — Canonical Authority regression suite.
- **Dependencies / Fixtures**: None (Pure In-Memory)
- **CI Job Execution**: `unit-and-ai-tests (Full Suite Floor)`
- **Recommended Run Frequency**: `PR / Push (main)`
- **Duplicate / Overlap Classification**: `COMPLEMENTARY`
- **RIGHT Test Suite Coverage**: `R-ARCH-01`
- **Bruno Collection Coverage**: `NONE`
- **Architectural Disposition**: **`MOVE`** (Target Destination: `backend/tests/unit/`)
- **Disposition Rationale & Evidence**: Authoritative RIGHT verification suite for R-ARCH-01. Move to dedicated integration/ or regression/ target folder.
- **Discovered Test Functions (13)**:
  - [`test_capability_patterns_defined_exactly_once`](file:///e:/JakeAI/backend/tests/test_r_arch_01_canonical_authority.py#L1): Financial/banking/retrieval keyword regexes must have one definition site. (1 assertions)
  - [`test_former_duplicate_pattern_copies_removed`](file:///e:/JakeAI/backend/tests/test_r_arch_01_canonical_authority.py#L1): Planner, selector and supervisor must not define local keyword copies. (1 assertions)
  - [`test_layers_classify_goals_consistently`](file:///e:/JakeAI/backend/tests/test_r_arch_01_canonical_authority.py#L1): The planner, the AgentSelector and the supervisor fallback must agree. (17 assertions)
  - [`test_no_duplicate_lifecycle_status_authority`](file:///e:/JakeAI/backend/tests/test_r_arch_01_canonical_authority.py#L1): The dead ExecutionStateStatus/TerminalState duplicates stay removed. (4 assertions)
  - [`test_canonical_status_machine_is_the_lifecycle_authority`](file:///e:/JakeAI/backend/tests/test_r_arch_01_canonical_authority.py#L1): RunStatus/TaskStatus expose terminal semantics with enforced transitions. (3 assertions)
  - [`test_provider_credential_map_defined_once`](file:///e:/JakeAI/backend/tests/test_r_arch_01_canonical_authority.py#L1): The platform-key map must exist exactly once (canonical credentials module). (2 assertions)
  - [`test_credential_resolution_byok_first_then_platform`](file:///e:/JakeAI/backend/tests/test_r_arch_01_canonical_authority.py#L1): BYOK tenant key wins; platform key is the fallback for every variant. (4 assertions)
  - [`test_balance_tool_is_single_obo_and_account_authority`](file:///e:/JakeAI/backend/tests/test_r_arch_01_canonical_authority.py#L1): The tool honors provided OBO tokens and owns the tenant account default. (7 assertions)
  - [`test_transactions_tool_honors_provided_obo_token`](file:///e:/JakeAI/backend/tests/test_r_arch_01_canonical_authority.py#L1): Direct assertion (2 assertions)
  - [`test_tenant_account_identity_derived_exactly_once`](file:///e:/JakeAI/backend/tests/test_r_arch_01_canonical_authority.py#L1): The ACC-<tenant>-01 derivation must exist only in the builtin tool. (1 assertions)
  - [`test_managed_runtime_wires_single_canonical_backend`](file:///e:/JakeAI/backend/tests/test_r_arch_01_canonical_authority.py#L1): Even with a non-canonical backend_type, the runtime uses JakeAIBackend. (1 assertions)
  - [`test_non_canonical_backends_documented_as_adapter_boundary`](file:///e:/JakeAI/backend/tests/test_r_arch_01_canonical_authority.py#L1): Standalone backends must declare their non-canonical boundary. (4 assertions)
  - [`test_settings_snapshot_unchanged_by_credential_refactor`](file:///e:/JakeAI/backend/tests/test_r_arch_01_canonical_authority.py#L1): Guard against accidental drift of the platform-key provider set. (2 assertions)

#### `CAT-041`: [`test_r_arch_02_dependency_boundaries.py`](file:///e:/JakeAI/backend/tests/test_r_arch_02_dependency_boundaries.py)
- **Test File Path**: `backend/tests/test_r_arch_02_dependency_boundaries.py` (493 lines)
- **Subsystem**: `Core / Platform`
- **Test Level**: `Regression (RIGHT Verification)`
- **Purpose**: R-ARCH-02 — Dependency Boundaries regression suite.
- **Dependencies / Fixtures**: HTTP / ASGI, Mocks / Monkeypatch
- **CI Job Execution**: `unit-and-ai-tests (Full Suite Floor)`
- **Recommended Run Frequency**: `PR / Push (main)`
- **Duplicate / Overlap Classification**: `COMPLEMENTARY`
- **RIGHT Test Suite Coverage**: `R-ARCH-02`
- **Bruno Collection Coverage**: `NONE`
- **Architectural Disposition**: **`MOVE`** (Target Destination: `backend/tests/unit/`)
- **Disposition Rationale & Evidence**: Authoritative RIGHT verification suite for R-ARCH-02. Move to dedicated integration/ or regression/ target folder.
- **Discovered Test Functions (12)**:
  - [`test_agent_domain_never_depends_on_langgraph_adapter_or_frameworks`](file:///e:/JakeAI/backend/tests/test_r_arch_02_dependency_boundaries.py#L1): Rule 1: ``app/agent/**`` must not import ``app/agents/**`` or frameworks. (1 assertions)
  - [`test_pure_domain_modules_import_no_foreign_app_modules`](file:///e:/JakeAI/backend/tests/test_r_arch_02_dependency_boundaries.py#L1): Rule 2: contracts and lifecycle state models are dependency-free. (1 assertions)
  - [`test_providers_never_import_orchestration_or_api_layers`](file:///e:/JakeAI/backend/tests/test_r_arch_02_dependency_boundaries.py#L1): Rule 3: provider adapters execute requests; they never own workflow. (1 assertions)
  - [`test_provider_adapters_delegate_credentials_to_canonical_byok`](file:///e:/JakeAI/backend/tests/test_r_arch_02_dependency_boundaries.py#L1): Rule 4: credential resolution is delegated to the canonical BYOK vault. (1 assertions)
  - [`test_tool_instance_execute_has_single_production_call_site`](file:///e:/JakeAI/backend/tests/test_r_arch_02_dependency_boundaries.py#L1): Rule 5: the only production call site of ``Tool.execute`` is the registry. (1 assertions)
  - [`test_financial_capability_formulas_defined_exactly_once`](file:///e:/JakeAI/backend/tests/test_r_arch_02_dependency_boundaries.py#L1): Rule 6: financial business semantics live in exactly one module. (1 assertions)
  - [`test_langgraph_financial_node_is_pure_delegation`](file:///e:/JakeAI/backend/tests/test_r_arch_02_dependency_boundaries.py#L1): Rule 7: the adapter's financial node holds no business semantics. (2 assertions)
  - [`test_endpoints_never_expose_internal_storage_records`](file:///e:/JakeAI/backend/tests/test_r_arch_02_dependency_boundaries.py#L1): Rule 8: public API DTOs must not expose internal persistence records. (1 assertions)
  - [`test_all_drivers_match_canonical_capability_arithmetic`](file:///e:/JakeAI/backend/tests/test_r_arch_02_dependency_boundaries.py#L1): Rule 9: adapter node and degraded planner fallback share one arithmetic. (10 assertions)
  - [`test_engine_financial_step_matches_canonical_capability`](file:///e:/JakeAI/backend/tests/test_r_arch_02_dependency_boundaries.py#L1): Rule 9 (engine): the canonical DAG engine's financial step output equals (5 assertions)
  - [`test_chat_http_financial_output_matches_canonical_capability`](file:///e:/JakeAI/backend/tests/test_r_arch_02_dependency_boundaries.py#L1): Rule 10: the public HTTP chat stream returns canonical arithmetic. (4 assertions)
  - [`test_registry_discovers_builtin_tools_through_policy`](file:///e:/JakeAI/backend/tests/test_r_arch_02_dependency_boundaries.py#L1): Rule 5 (runtime): built-ins are reachable only via the registry funnel. (3 assertions)

#### `CAT-042`: [`test_r_arch_03_duplicate_abstractions.py`](file:///e:/JakeAI/backend/tests/test_r_arch_03_duplicate_abstractions.py)
- **Test File Path**: `backend/tests/test_r_arch_03_duplicate_abstractions.py` (381 lines)
- **Subsystem**: `Core / Platform`
- **Test Level**: `Regression (RIGHT Verification)`
- **Purpose**: R-ARCH-03 — Duplicate Abstractions regression suite.
- **Dependencies / Fixtures**: Redis, Mocks / Monkeypatch
- **CI Job Execution**: `unit-and-ai-tests (Full Suite Floor)`
- **Recommended Run Frequency**: `PR / Push (main)`
- **Duplicate / Overlap Classification**: `COMPLEMENTARY`
- **RIGHT Test Suite Coverage**: `R-ARCH-03`
- **Bruno Collection Coverage**: `NONE`
- **Architectural Disposition**: **`MOVE`** (Target Destination: `backend/tests/unit/`)
- **Disposition Rationale & Evidence**: Authoritative RIGHT verification suite for R-ARCH-03. Move to dedicated integration/ or regression/ target folder.
- **Discovered Test Functions (17)**:
  - [`test_workflow_engine_package_removed`](file:///e:/JakeAI/backend/tests/test_r_arch_03_duplicate_abstractions.py#L1): The test-only third workflow engine stays removed (R-ARCH-00 F-02). (4 assertions)
  - [`test_redis_client_construction_has_single_authority`](file:///e:/JakeAI/backend/tests/test_r_arch_03_duplicate_abstractions.py#L1): All cached-helper modules delegate to the shared factory; nobody else (4 assertions)
  - [`test_redis_mock_detection_defined_once`](file:///e:/JakeAI/backend/tests/test_r_arch_03_duplicate_abstractions.py#L1): The Mock/AsyncMock test-double detection lives only in the factory. (1 assertions)
  - [`test_quota_manager_binary_client_stays_private`](file:///e:/JakeAI/backend/tests/test_r_arch_03_duplicate_abstractions.py#L1): QuotaManager must not write its binary-mode client through the (4 assertions)
  - [`test_capability_catalog_pricing_matches_canonical_authority`](file:///e:/JakeAI/backend/tests/test_r_arch_03_duplicate_abstractions.py#L1): Every catalog entry's prices are exactly the canonical pricing entries. (6 assertions)
  - [`test_capability_catalog_has_no_pricing_literals`](file:///e:/JakeAI/backend/tests/test_r_arch_03_duplicate_abstractions.py#L1): The capability catalog must not re-hardcode price numbers. (1 assertions)
  - [`test_llm_provider_reexports_canonical_credentials`](file:///e:/JakeAI/backend/tests/test_r_arch_03_duplicate_abstractions.py#L1): llm_provider keeps its public API by re-exporting the canonical resolver. (2 assertions)
  - [`test_failover_has_no_local_credential_map`](file:///e:/JakeAI/backend/tests/test_r_arch_03_duplicate_abstractions.py#L1): The verbatim map clone in failover._default_resolve_credentials is gone. (2 assertions)
  - [`test_failover_default_resolver_matches_canonical_resolution`](file:///e:/JakeAI/backend/tests/test_r_arch_03_duplicate_abstractions.py#L1): Failover-time resolution is BYOK-first then platform key, like dispatch. (4 assertions)
  - [`test_json_extraction_copies_removed`](file:///e:/JakeAI/backend/tests/test_r_arch_03_duplicate_abstractions.py#L1): The inline fence-strip idiom is gone; each site uses the canonical util. (4 assertions)
  - [`test_planner_extract_json_action_uses_canonical_semantics`](file:///e:/JakeAI/backend/tests/test_r_arch_03_duplicate_abstractions.py#L1): Planner action extraction accepts fenced and embedded JSON via the util. (5 assertions)
  - [`test_jakeai_backend_tool_call_extraction`](file:///e:/JakeAI/backend/tests/test_r_arch_03_duplicate_abstractions.py#L1): Backend tool-call extraction works for fenced and prose-wrapped JSON. (6 assertions)
  - [`test_quality_oracle_schema_layer_uses_canonical_extraction`](file:///e:/JakeAI/backend/tests/test_r_arch_03_duplicate_abstractions.py#L1): Schema scoring: fenced JSON scores fully; garbage reports the failure. (4 assertions)
  - [`test_rubric_format_correctness_uses_canonical_extraction`](file:///e:/JakeAI/backend/tests/test_r_arch_03_duplicate_abstractions.py#L1): Rubric schema-key checking works on fenced JSON and rejects garbage. (3 assertions)
  - [`test_rubric_json_only_check_is_validation_not_extraction`](file:///e:/JakeAI/backend/tests/test_r_arch_03_duplicate_abstractions.py#L1): The 'JSON only' constraint check must stay strict: prose-wrapped JSON (1 assertions)
  - [`test_agent_run_event_sse_matches_canonical_formatter`](file:///e:/JakeAI/backend/tests/test_r_arch_03_duplicate_abstractions.py#L1): Direct assertion (1 assertions)
  - [`test_sse_headers_defined_once`](file:///e:/JakeAI/backend/tests/test_r_arch_03_duplicate_abstractions.py#L1): The streaming header set is defined once and consumed by both endpoints. (3 assertions)

#### `CAT-044`: [`test_r_func_00_api_behavior.py`](file:///e:/JakeAI/backend/tests/test_r_func_00_api_behavior.py)
- **Test File Path**: `backend/tests/test_r_func_00_api_behavior.py` (1144 lines)
- **Subsystem**: `Core / Platform`
- **Test Level**: `Integration (API / HTTP)`
- **Purpose**: R-FUNC-00 - Comprehensive HTTP API Boundary Verification Test Suite.
- **Dependencies / Fixtures**: Redis, HTTP / ASGI, Mocks / Monkeypatch
- **CI Job Execution**: `unit-and-ai-tests (Full Suite Floor)`
- **Recommended Run Frequency**: `PR / Push (main)`
- **Duplicate / Overlap Classification**: `COMPLEMENTARY`
- **RIGHT Test Suite Coverage**: `R-FUNC-00`
- **Bruno Collection Coverage**: `NONE`
- **Architectural Disposition**: **`MOVE`** (Target Destination: `backend/tests/integration/`)
- **Disposition Rationale & Evidence**: Authoritative RIGHT verification suite for R-FUNC-00. Move to dedicated integration/ or regression/ target folder.
- **Discovered Test Functions (29)**:
  - [`test_all_51_endpoints_accounted_in_openapi`](file:///e:/JakeAI/backend/tests/test_r_func_00_api_behavior.py#L1): Verify runtime OpenAPI specification registers exactly 51 endpoints matching contract. (1 assertions)
  - [`test_health_endpoints_http_boundary`](file:///e:/JakeAI/backend/tests/test_r_func_00_api_behavior.py#L1): Verify all 6 health probe endpoints return 200 OK with HealthResponse schema. (6 assertions)
  - [`test_health_readiness_redis_connected`](file:///e:/JakeAI/backend/tests/test_r_func_00_api_behavior.py#L1): Verify readiness probe returns components.redis == connected when redis is healthy. (2 assertions)
  - [`test_prometheus_metrics_endpoint_http_boundary`](file:///e:/JakeAI/backend/tests/test_r_func_00_api_behavior.py#L1): Verify GET /metrics returns Prometheus exposition format. (3 assertions)
  - [`test_gateway_models_endpoint`](file:///e:/JakeAI/backend/tests/test_r_func_00_api_behavior.py#L1): Verify GET /v1/models and GET /api/v1/gateway/models return ModelListResponse. (4 assertions)
  - [`test_gateway_quotas_endpoints`](file:///e:/JakeAI/backend/tests/test_r_func_00_api_behavior.py#L1): Verify GET & POST quotas on both /v1 and /api/v1/gateway. (5 assertions)
  - [`test_gateway_chat_completions_sync_and_stream`](file:///e:/JakeAI/backend/tests/test_r_func_00_api_behavior.py#L1): Verify POST /chat/completions with sync and streaming modes. (6 assertions)
  - [`test_chat_stream_full_event_flow`](file:///e:/JakeAI/backend/tests/test_r_func_00_api_behavior.py#L1): Verify POST /api/v1/chat/stream emits expected SSE event types in proper order. (7 assertions)
  - [`test_chat_stream_guardrail_rejection`](file:///e:/JakeAI/backend/tests/test_r_func_00_api_behavior.py#L1): Verify POST /api/v1/chat/stream halts with guardrail error event on prompt injection. (3 assertions)
  - [`test_rag_pipeline_endpoints`](file:///e:/JakeAI/backend/tests/test_r_func_00_api_behavior.py#L1): Verify synchronous ingest (201), async ingest (202), task poll, query, and generate. (9 assertions)
  - [`test_byok_lifecycle_endpoints`](file:///e:/JakeAI/backend/tests/test_r_func_00_api_behavior.py#L1): Verify store (201), list (200), candidate validate, stored validate, rotate, revoke, delete. (21 assertions)
  - [`test_devops_endpoints`](file:///e:/JakeAI/backend/tests/test_r_func_00_api_behavior.py#L1): Verify POST /api/v1/devops/audit-pr and POST /api/v1/devops/changelog. (6 assertions)
  - [`test_billing_endpoints`](file:///e:/JakeAI/backend/tests/test_r_func_00_api_behavior.py#L1): Verify GET subscription and POST webhook with HMAC-SHA256 verification. (5 assertions)
  - [`test_analytics_endpoints`](file:///e:/JakeAI/backend/tests/test_r_func_00_api_behavior.py#L1): Verify GET /api/v1/analytics/dashboard and GET /api/v1/analytics/metrics. (4 assertions)
  - [`test_finops_endpoints`](file:///e:/JakeAI/backend/tests/test_r_func_00_api_behavior.py#L1): Verify GET summary, GET transactions, GET/POST budget, and GET reconciliation. (10 assertions)
  - [`test_coding_tool_result_endpoints`](file:///e:/JakeAI/backend/tests/test_r_func_00_api_behavior.py#L1): Verify tool-result endpoint returns 404 for unknown call_id under both route mounts. (1 assertions)
  - [`test_coding_resume_perimeter_auth`](file:///e:/JakeAI/backend/tests/test_r_func_00_api_behavior.py#L1): Verify /resume rejects requests lacking Invariant 4 perimeter credentials (403). (2 assertions)
  - [`test_agent_platform_task_lifecycle`](file:///e:/JakeAI/backend/tests/test_r_func_00_api_behavior.py#L1): Verify create_task (201), get_task (200), start_run (201), get_run (200), cancel_run. (14 assertions)
  - [`test_agent_platform_approvals_and_metrics`](file:///e:/JakeAI/backend/tests/test_r_func_00_api_behavior.py#L1): Verify pending approvals list, approval decision on missing gate (404), and agent metrics. (5 assertions)
  - [`test_agent_run_events_stream_terminal_non_blocking_regression`](file:///e:/JakeAI/backend/tests/test_r_func_00_api_behavior.py#L1): Regression test for DEFECT-R-FUNC-00-01: stream_run_events must NOT block indefinitely. (3 assertions)
  - [`test_agent_runner_stream_events_live_and_timeout`](file:///e:/JakeAI/backend/tests/test_r_func_00_api_behavior.py#L1): Verify stream_run_events yields live events, handles TimeoutError, and terminates on terminal event. (3 assertions)
  - [`test_unauthenticated_request_rejected_with_401`](file:///e:/JakeAI/backend/tests/test_r_func_00_api_behavior.py#L1): Protected endpoints reject requests missing Authorization Bearer header. (2 assertions)
  - [`test_expired_and_invalid_token_rejected_with_401`](file:///e:/JakeAI/backend/tests/test_r_func_00_api_behavior.py#L1): Requests carrying expired or forged JWT tokens are rejected with 401. (4 assertions)
  - [`test_tenant_isolation_cross_tenant_access_rejected`](file:///e:/JakeAI/backend/tests/test_r_func_00_api_behavior.py#L1): Strict tenant boundary: Tenant B cannot access or modify Tenant A resources. (4 assertions)
  - [`test_correlation_and_w3c_traceparent_propagation`](file:///e:/JakeAI/backend/tests/test_r_func_00_api_behavior.py#L1): Incoming X-Correlation-ID and W3C traceparent/tracestate are preserved and reflected. (5 assertions)
  - [`test_request_size_ceiling_413`](file:///e:/JakeAI/backend/tests/test_r_func_00_api_behavior.py#L1): Requests exceeding MAX_REQUEST_BODY_BYTES (10MB) return 413 Content Too Large. (2 assertions)
  - [`test_malformed_json_returns_422`](file:///e:/JakeAI/backend/tests/test_r_func_00_api_behavior.py#L1): Syntactically broken JSON bodies return 422 Unprocessable Entity. (1 assertions)
  - [`test_schema_bound_violations_return_422`](file:///e:/JakeAI/backend/tests/test_r_func_00_api_behavior.py#L1): Out-of-bound or empty required fields return 422 Unprocessable Entity. (3 assertions)
  - [`test_provider_error_exception_handler_mapping`](file:///e:/JakeAI/backend/tests/test_r_func_00_api_behavior.py#L1): Normalized ProviderError is mapped to standard HTTP codes with Retry-After header. (5 assertions)

#### `CAT-048`: [`test_r_func_04_provider_behavior.py`](file:///e:/JakeAI/backend/tests/test_r_func_04_provider_behavior.py)
- **Test File Path**: `backend/tests/test_r_func_04_provider_behavior.py` (663 lines)
- **Subsystem**: `Core / Platform`
- **Test Level**: `Regression (RIGHT Verification)`
- **Purpose**: R-FUNC-04 — Provider Behavior verification suite.
- **Dependencies / Fixtures**: HTTP / ASGI, Mocks / Monkeypatch
- **CI Job Execution**: `unit-and-ai-tests (Full Suite Floor)`
- **Recommended Run Frequency**: `PR / Push (main)`
- **Duplicate / Overlap Classification**: `COMPLEMENTARY`
- **RIGHT Test Suite Coverage**: `R-FUNC-04`
- **Bruno Collection Coverage**: `NONE`
- **Architectural Disposition**: **`MOVE`** (Target Destination: `backend/tests/unit/`)
- **Disposition Rationale & Evidence**: Authoritative RIGHT verification suite for R-FUNC-04. Move to dedicated integration/ or regression/ target folder.
- **Discovered Test Functions (17)**:
  - [`test_dispatch_invokes_selected_provider_and_model_on_the_wire`](file:///e:/JakeAI/backend/tests/test_r_func_04_provider_behavior.py#L1): Routing decision (anthropic, claude-3-5-sonnet) must produce a real HTTP (8 assertions)
  - [`test_selected_model_reaches_provider_payload`](file:///e:/JakeAI/backend/tests/test_r_func_04_provider_behavior.py#L1): The adapter payload must carry the routed model, not a silent substitute. (6 assertions)
  - [`test_structured_output_forwarded_to_provider`](file:///e:/JakeAI/backend/tests/test_r_func_04_provider_behavior.py#L1): response_format (structured output / JSON mode) must be forwarded intact. (2 assertions)
  - [`test_provider_reported_usage_reconciles_to_accounting`](file:///e:/JakeAI/backend/tests/test_r_func_04_provider_behavior.py#L1): Usage reported by the provider must flow unmodified into telemetry (8 assertions)
  - [`test_streaming_dispatcher_yields_incremental_deltas`](file:///e:/JakeAI/backend/tests/test_r_func_04_provider_behavior.py#L1): call_upstream_llm_stream must yield provider deltas incrementally as (1 assertions)
  - [`test_cloud_adapter_timeout_normalized_to_typed_error`](file:///e:/JakeAI/backend/tests/test_r_func_04_provider_behavior.py#L1): httpx read timeout must surface as retryable ProviderTimeoutError. (2 assertions)
  - [`test_cloud_adapter_connect_error_normalized_to_unavailable`](file:///e:/JakeAI/backend/tests/test_r_func_04_provider_behavior.py#L1): Connection failure must surface as retryable ProviderUnavailableError. (2 assertions)
  - [`test_cloud_adapter_malformed_response_normalized`](file:///e:/JakeAI/backend/tests/test_r_func_04_provider_behavior.py#L1): HTTP 200 with unparseable body must surface as a typed ProviderError, (2 assertions)
  - [`test_cloud_adapter_stream_timeout_normalized`](file:///e:/JakeAI/backend/tests/test_r_func_04_provider_behavior.py#L1): Mid-stream read timeout must surface as ProviderTimeoutError. (0 assertions)
  - [`test_cloud_adapter_stream_connect_error_normalized`](file:///e:/JakeAI/backend/tests/test_r_func_04_provider_behavior.py#L1): Stream connect failure must surface as ProviderUnavailableError. (0 assertions)
  - [`test_error_status_matrix_classification`](file:///e:/JakeAI/backend/tests/test_r_func_04_provider_behavior.py#L1): Every provider HTTP failure status must be normalized into the correct (3 assertions)
  - [`test_429_with_quota_message_maps_to_quota_error`](file:///e:/JakeAI/backend/tests/test_r_func_04_provider_behavior.py#L1): Direct assertion (2 assertions)
  - [`test_429_respects_retry_after_header`](file:///e:/JakeAI/backend/tests/test_r_func_04_provider_behavior.py#L1): Direct assertion (1 assertions)
  - [`test_failover_reaches_provider_b_under_default_config`](file:///e:/JakeAI/backend/tests/test_r_func_04_provider_behavior.py#L1): With production default config, a primary persistently failing with a (3 assertions)
  - [`test_failover_wire_credentials_are_provider_specific`](file:///e:/JakeAI/backend/tests/test_r_func_04_provider_behavior.py#L1): After provider A fails, provider B's real HTTP request must carry (7 assertions)
  - [`test_failover_fallback_model_reaches_the_wire`](file:///e:/JakeAI/backend/tests/test_r_func_04_provider_behavior.py#L1): The fallback (provider B, model B) decision must be what is invoked. (3 assertions)
  - [`test_failover_timeout_is_retried_then_fails_over`](file:///e:/JakeAI/backend/tests/test_r_func_04_provider_behavior.py#L1): A timeout on the primary (classified retryable after normalization) must (2 assertions)

#### `CAT-050`: [`test_r_logic_01_state_transitions.py`](file:///e:/JakeAI/backend/tests/test_r_logic_01_state_transitions.py)
- **Test File Path**: `backend/tests/test_r_logic_01_state_transitions.py` (1274 lines)
- **Subsystem**: `Core / Platform`
- **Test Level**: `Regression (RIGHT Verification)`
- **Purpose**: R-LOGIC-01 — State Transitions Verification Test Suite.
- **Dependencies / Fixtures**: HTTP / ASGI, Mocks / Monkeypatch
- **CI Job Execution**: `unit-and-ai-tests (Full Suite Floor)`
- **Recommended Run Frequency**: `PR / Push (main)`
- **Duplicate / Overlap Classification**: `COMPLEMENTARY`
- **RIGHT Test Suite Coverage**: `R-LOGIC-01`
- **Bruno Collection Coverage**: `NONE`
- **Architectural Disposition**: **`MOVE`** (Target Destination: `backend/tests/unit/`)
- **Disposition Rationale & Evidence**: Authoritative RIGHT verification suite for R-LOGIC-01. Move to dedicated integration/ or regression/ target folder.
- **Discovered Test Functions (24)**:
  - [`test_run_matrix_is_complete_and_closed`](file:///e:/JakeAI/backend/tests/test_r_logic_01_state_transitions.py#L1): Every non-terminal run state defines its successors; terminals define none. (4 assertions)
  - [`test_every_allowed_run_transition_is_accepted_via_transition_to`](file:///e:/JakeAI/backend/tests/test_r_logic_01_state_transitions.py#L1): Direct assertion (2 assertions)
  - [`test_every_forbidden_run_transition_is_rejected_via_assignment`](file:///e:/JakeAI/backend/tests/test_r_logic_01_state_transitions.py#L1): Raw status writes may not bypass the machine (RL01-F-01). (1 assertions)
  - [`test_every_forbidden_run_transition_is_rejected_via_transition_to`](file:///e:/JakeAI/backend/tests/test_r_logic_01_state_transitions.py#L1): Direct assertion (1 assertions)
  - [`test_named_forbidden_transitions_cannot_silently_succeed`](file:///e:/JakeAI/backend/tests/test_r_logic_01_state_transitions.py#L1): The task specification's explicit forbidden pairs, on both write paths. (2 assertions)
  - [`test_self_assignment_is_idempotent_noop`](file:///e:/JakeAI/backend/tests/test_r_logic_01_state_transitions.py#L1): Direct assertion (1 assertions)
  - [`test_transition_matrix_survives_checkpoint_roundtrip`](file:///e:/JakeAI/backend/tests/test_r_logic_01_state_transitions.py#L1): Direct assertion (2 assertions)
  - [`test_task_matrix_is_enforced_on_assignment`](file:///e:/JakeAI/backend/tests/test_r_logic_01_state_transitions.py#L1): TaskStatus writes are matrix-validated (RL01-F-07). (2 assertions)
  - [`test_task_happy_path_sequence_is_accepted`](file:///e:/JakeAI/backend/tests/test_r_logic_01_state_transitions.py#L1): Direct assertion (2 assertions)
  - [`test_late_cancellation_after_completion_preserves_terminal_state`](file:///e:/JakeAI/backend/tests/test_r_logic_01_state_transitions.py#L1): A cancel delivered after the run reached COMPLETED must not flip it. (3 assertions)
  - [`test_engine_traverses_verifying_and_replanning_states`](file:///e:/JakeAI/backend/tests/test_r_logic_01_state_transitions.py#L1): The documented VERIFYING/REPLANNING states are actually entered. (6 assertions)
  - [`test_engine_rejected_verdict_terminates_from_verifying`](file:///e:/JakeAI/backend/tests/test_r_logic_01_state_transitions.py#L1): A REJECTED verification terminates REJECTED out of VERIFYING state. (2 assertions)
  - [`test_engine_revision_ceiling_terminates_failed`](file:///e:/JakeAI/backend/tests/test_r_logic_01_state_transitions.py#L1): Verification NEEDS_REVISION is bounded: run terminates FAILED. (2 assertions)
  - [`test_step_retry_is_bounded_and_terminates_failed`](file:///e:/JakeAI/backend/tests/test_r_logic_01_state_transitions.py#L1): A permanently failing step with no alternative agent terminates FAILED (3 assertions)
  - [`test_agent_switch_recovery_is_bounded_in_attempt_count`](file:///e:/JakeAI/backend/tests/test_r_logic_01_state_transitions.py#L1): Agent-switching recovery is bounded: a permanently failing step with (3 assertions)
  - [`test_terminal_failed_run_refuses_resume_and_new_run_is_fresh`](file:///e:/JakeAI/backend/tests/test_r_logic_01_state_transitions.py#L1): Direct assertion (3 assertions)
  - [`test_http_approval_gate_rejection_marks_run_rejected`](file:///e:/JakeAI/backend/tests/test_r_logic_01_state_transitions.py#L1): Rejecting an approval via the decisions API terminates the run REJECTED. (9 assertions)
  - [`test_http_approval_approve_resumes_to_completed`](file:///e:/JakeAI/backend/tests/test_r_logic_01_state_transitions.py#L1): Approving the gate resumes execution; the run terminates COMPLETED and (5 assertions)
  - [`test_http_cancel_during_approval_wait_is_terminal_and_final`](file:///e:/JakeAI/backend/tests/test_r_logic_01_state_transitions.py#L1): Cancelling a paused run persists CANCELLED; a later approval decision (7 assertions)
  - [`test_http_cancel_of_completed_run_is_noop`](file:///e:/JakeAI/backend/tests/test_r_logic_01_state_transitions.py#L1): Cancel of an already-terminal run preserves its terminal status. (3 assertions)
  - [`test_resume_from_ready_checkpoint_completes_legally`](file:///e:/JakeAI/backend/tests/test_r_logic_01_state_transitions.py#L1): A run restored from a READY-state checkpoint (crash window between (3 assertions)
  - [`test_resume_from_running_checkpoint_completes_legally`](file:///e:/JakeAI/backend/tests/test_r_logic_01_state_transitions.py#L1): Direct assertion (1 assertions)
  - [`test_manager_cancel_of_created_run_is_legal_and_terminal`](file:///e:/JakeAI/backend/tests/test_r_logic_01_state_transitions.py#L1): Direct assertion (3 assertions)
  - [`test_retry_as_new_run_does_not_corrupt_task_history`](file:///e:/JakeAI/backend/tests/test_r_logic_01_state_transitions.py#L1): A failed attempt is terminal; the retry is a NEW run that legally (5 assertions)

#### `CAT-051`: [`test_r_logic_02_data_flow.py`](file:///e:/JakeAI/backend/tests/test_r_logic_02_data_flow.py)
- **Test File Path**: `backend/tests/test_r_logic_02_data_flow.py` (819 lines)
- **Subsystem**: `Core / Platform`
- **Test Level**: `Regression (RIGHT Verification)`
- **Purpose**: R-LOGIC-02 — Data Flow Verification Test Suite.
- **Dependencies / Fixtures**: HTTP / ASGI, Mocks / Monkeypatch
- **CI Job Execution**: `unit-and-ai-tests (Full Suite Floor)`
- **Recommended Run Frequency**: `PR / Push (main)`
- **Duplicate / Overlap Classification**: `COMPLEMENTARY`
- **RIGHT Test Suite Coverage**: `R-LOGIC-02`
- **Bruno Collection Coverage**: `NONE`
- **Architectural Disposition**: **`MOVE`** (Target Destination: `backend/tests/unit/`)
- **Disposition Rationale & Evidence**: Authoritative RIGHT verification suite for R-LOGIC-02. Move to dedicated integration/ or regression/ target folder.
- **Discovered Test Functions (15)**:
  - [`test_http_run_carries_request_identity`](file:///e:/JakeAI/backend/tests/test_r_logic_02_data_flow.py#L1): The authenticated correlation_id, roles, and permissions must be persisted (6 assertions)
  - [`test_run_identity_survives_checkpoint_restore_roundtrip`](file:///e:/JakeAI/backend/tests/test_r_logic_02_data_flow.py#L1): Identity fields must survive the durable checkpoint round-trip (7 assertions)
  - [`test_tool_context_receives_run_correlation_id`](file:///e:/JakeAI/backend/tests/test_r_logic_02_data_flow.py#L1): Tool execution context must carry the run's correlation_id (3 assertions)
  - [`test_approval_decision_rejects_cross_run_binding`](file:///e:/JakeAI/backend/tests/test_r_logic_02_data_flow.py#L1): An approval decision must be bound to the run in the request path (2 assertions)
  - [`test_langgraph_thread_state_does_not_leak_across_tenants`](file:///e:/JakeAI/backend/tests/test_r_logic_02_data_flow.py#L1): Checkpointer thread state must be tenant-namespaced (RL02-F-03). (2 assertions)
  - [`test_chat_cache_does_not_serve_stale_answer_across_rag_contexts`](file:///e:/JakeAI/backend/tests/test_r_logic_02_data_flow.py#L1): The chat response cache must not serve an answer generated against one (2 assertions)
  - [`test_semantic_cache_context_dimension_at_service_boundary`](file:///e:/JakeAI/backend/tests/test_r_logic_02_data_flow.py#L1): SemanticCacheManager get/set must accept and isolate the retrieval (3 assertions)
  - [`test_cache_identity_includes_retrieval_context_dimension`](file:///e:/JakeAI/backend/tests/test_r_logic_02_data_flow.py#L1): compute_cache_identity must fold rag/dynamic context into the identity. (3 assertions)
  - [`test_chat_stream_records_served_model_and_provider_telemetry`](file:///e:/JakeAI/backend/tests/test_r_logic_02_data_flow.py#L1): The requested model must reach the LLM dispatcher, and accounting must (6 assertions)
  - [`test_chat_stream_normalizes_default_model_for_accounting`](file:///e:/JakeAI/backend/tests/test_r_logic_02_data_flow.py#L1): A request without a model parameter must be accounted under the model (2 assertions)
  - [`test_gateway_response_reports_served_model`](file:///e:/JakeAI/backend/tests/test_r_logic_02_data_flow.py#L1): The OpenAI-compatible gateway response must name the model that actually (2 assertions)
  - [`test_resume_bridge_fails_closed_on_unscoped_checkpoint`](file:///e:/JakeAI/backend/tests/test_r_logic_02_data_flow.py#L1): A checkpoint record without a tenant must not be resumable by any (0 assertions)
  - [`test_jwt_null_scopes_claim_handled_gracefully`](file:///e:/JakeAI/backend/tests/test_r_logic_02_data_flow.py#L1): A JWT whose scopes claim is present but null must not crash request (1 assertions)
  - [`test_finnapigo_tool_default_tenant_matches_platform_default`](file:///e:/JakeAI/backend/tests/test_r_logic_02_data_flow.py#L1): The FinnApiGo tool node's missing-tenant default must match the (2 assertions)
  - [`test_cache_version_bumped_for_context_dimension`](file:///e:/JakeAI/backend/tests/test_r_logic_02_data_flow.py#L1): The identity schema gained the retrieval-context dimension; the version (1 assertions)

#### `CAT-069`: [`test_structured_output.py`](file:///e:/JakeAI/backend/tests/test_structured_output.py)
- **Test File Path**: `backend/tests/test_structured_output.py` (258 lines)
- **Subsystem**: `Core / Platform`
- **Test Level**: `Unit`
- **Purpose**: Unit tests for canonical structured output parsing utility (WORK-01-CI-FIX-05).
- **Dependencies / Fixtures**: None (Pure In-Memory)
- **CI Job Execution**: `unit-and-ai-tests (Full Suite Floor)`
- **Recommended Run Frequency**: `PR / Push (main)`
- **Duplicate / Overlap Classification**: `COMPLEMENTARY`
- **RIGHT Test Suite Coverage**: `NONE`
- **Bruno Collection Coverage**: `NONE`
- **Architectural Disposition**: **`MOVE`** (Target Destination: `backend/tests/unit/`)
- **Disposition Rationale & Evidence**: Valuable subsystem test. Needs reclassification into unit/, integration/, or security/.
- **Discovered Test Functions (18)**:
  - [`test_case_1_raw_json_object`](file:///e:/JakeAI/backend/tests/test_structured_output.py#L1): 1. Raw JSON object is extracted directly. (1 assertions)
  - [`test_case_2_fenced_json_block`](file:///e:/JakeAI/backend/tests/test_structured_output.py#L1): 2. ```json fenced block is parsed correctly. (1 assertions)
  - [`test_case_3_generic_fenced_block`](file:///e:/JakeAI/backend/tests/test_structured_output.py#L1): 3. Generic ``` fenced block is parsed correctly. (1 assertions)
  - [`test_case_4_embedded_json_object`](file:///e:/JakeAI/backend/tests/test_structured_output.py#L1): 4. Embedded JSON object in prose is discovered and parsed. (1 assertions)
  - [`test_case_5_empty_text`](file:///e:/JakeAI/backend/tests/test_structured_output.py#L1): 5. Empty text returns None. (1 assertions)
  - [`test_case_6_whitespace_only_text`](file:///e:/JakeAI/backend/tests/test_structured_output.py#L1): 6. Whitespace-only text returns None. (1 assertions)
  - [`test_case_7_malformed_json`](file:///e:/JakeAI/backend/tests/test_structured_output.py#L1): 7. Malformed JSON returns None. (2 assertions)
  - [`test_case_8_valid_json_array`](file:///e:/JakeAI/backend/tests/test_structured_output.py#L1): 8. Valid JSON array returns None (must be an object dictionary). (2 assertions)
  - [`test_case_9_valid_json_primitives`](file:///e:/JakeAI/backend/tests/test_structured_output.py#L1): 9. Valid JSON primitives return None. (5 assertions)
  - [`test_case_10_missing_closing_fence`](file:///e:/JakeAI/backend/tests/test_structured_output.py#L1): 10. Missing closing fence returns None. (2 assertions)
  - [`test_case_11_multiple_blocks`](file:///e:/JakeAI/backend/tests/test_structured_output.py#L1): 11. Multiple blocks extracts the first valid JSON block without trailing confusion. (1 assertions)
  - [`test_case_12_braces_inside_surrounding_prose`](file:///e:/JakeAI/backend/tests/test_structured_output.py#L1): 12. Braces inside surrounding prose do not break object extraction. (1 assertions)
  - [`test_case_13_malformed_embedded_object`](file:///e:/JakeAI/backend/tests/test_structured_output.py#L1): 13. Malformed embedded object returns None. (1 assertions)
  - [`test_case_14_regression_no_broad_exceptions`](file:///e:/JakeAI/backend/tests/test_structured_output.py#L1): 14. Prove that canonical parser contains no silent 'except Exception:' or 'except BaseException:'. (4 assertions)
  - [`test_planner_integration_valid_structured_output`](file:///e:/JakeAI/backend/tests/test_structured_output.py#L1): Task 11: BoundedPlanner with canonical parser extracts valid DAG plan. (3 assertions)
  - [`test_planner_integration_none_fallback_deterministic`](file:///e:/JakeAI/backend/tests/test_structured_output.py#L1): Task 11: BoundedPlanner with parser returning None gracefully falls back to deterministic DAG. (2 assertions)
  - [`test_agent_selector_integration_valid_selection`](file:///e:/JakeAI/backend/tests/test_structured_output.py#L1): Task 11: AgentSelector with canonical parser selects agent from structured model output. (3 assertions)
  - [`test_agent_selector_integration_none_fallback_deterministic`](file:///e:/JakeAI/backend/tests/test_structured_output.py#L1): Task 11: AgentSelector with parser returning None falls back to deterministic selection. (2 assertions)

#### `CAT-073`: [`test_workload_classification_routing.py`](file:///e:/JakeAI/backend/tests/test_workload_classification_routing.py)
- **Test File Path**: `backend/tests/test_workload_classification_routing.py` (240 lines)
- **Subsystem**: `Core / Platform`
- **Test Level**: `Unit`
- **Purpose**: Comprehensive test suite for COST-09 (Workload Classification), COST-10 (Intelligent Model Routing), and COST-13 (Optimization Telemetry).
- **Dependencies / Fixtures**: None (Pure In-Memory)
- **CI Job Execution**: `unit-and-ai-tests (Full Suite Floor)`
- **Recommended Run Frequency**: `PR / Push (main)`
- **Duplicate / Overlap Classification**: `COMPLEMENTARY`
- **RIGHT Test Suite Coverage**: `NONE`
- **Bruno Collection Coverage**: `NONE`
- **Architectural Disposition**: **`MOVE`** (Target Destination: `backend/tests/unit/`)
- **Disposition Rationale & Evidence**: Valuable subsystem test. Needs reclassification into unit/, integration/, or security/.
- **Discovered Test Functions (12)**:
  - [`test_workload_classifier_simple_chat`](file:///e:/JakeAI/backend/tests/test_workload_classification_routing.py#L1): Verify conversational queries are classified as simple_chat with low quality floor. (4 assertions)
  - [`test_workload_classifier_coding`](file:///e:/JakeAI/backend/tests/test_workload_classification_routing.py#L1): Verify code patterns trigger coding workload and high quality floor. (3 assertions)
  - [`test_workload_classifier_reasoning`](file:///e:/JakeAI/backend/tests/test_workload_classification_routing.py#L1): Verify analytical and reasoning patterns request supports_reasoning. (3 assertions)
  - [`test_workload_classifier_tools_and_json`](file:///e:/JakeAI/backend/tests/test_workload_classification_routing.py#L1): Verify tools and response format add required capabilities. (3 assertions)
  - [`test_workload_classifier_long_context`](file:///e:/JakeAI/backend/tests/test_workload_classification_routing.py#L1): Verify context exceeding threshold is classified as long_context. (2 assertions)
  - [`test_model_router_hard_prefilter_context_window`](file:///e:/JakeAI/backend/tests/test_workload_classification_routing.py#L1): Verify router rejects candidates whose context window is smaller than context_tokens. (2 assertions)
  - [`test_model_router_hard_prefilter_required_capabilities`](file:///e:/JakeAI/backend/tests/test_workload_classification_routing.py#L1): Verify router hard filter rejects candidates lacking required capabilities. (1 assertions)
  - [`test_model_router_quality_guardrail_prevents_downgrade`](file:///e:/JakeAI/backend/tests/test_workload_classification_routing.py#L1): Verify high-intelligence coding task is never downgraded solely to save cost. (2 assertions)
  - [`test_model_router_cost_aware_simple_chat_downgrade`](file:///e:/JakeAI/backend/tests/test_workload_classification_routing.py#L1): Verify simple chat is safely down-tiered to cost-optimized model with positive savings. (3 assertions)
  - [`test_model_router_deterministic_repeatability`](file:///e:/JakeAI/backend/tests/test_workload_classification_routing.py#L1): Verify router produces identical decisions for identical inputs. (3 assertions)
  - [`test_model_router_cross_provider_non_loopback_fallback`](file:///e:/JakeAI/backend/tests/test_workload_classification_routing.py#L1): Verify fallback chain does not contain the primary model and uses distinct providers. (1 assertions)
  - [`test_optimization_telemetry_recording`](file:///e:/JakeAI/backend/tests/test_workload_classification_routing.py#L1): Verify MetricsCollector captures optimization decisions and aggregates cost savings. (6 assertions)

#### `CAT-091`: [`test_canonical_provider_resolution.py`](file:///e:/JakeAI/backend/tests/unit/test_canonical_provider_resolution.py)
- **Test File Path**: `backend/tests/unit/test_canonical_provider_resolution.py` (384 lines)
- **Subsystem**: `Core / Platform`
- **Test Level**: `Unit`
- **Purpose**: REPAIR-03 — DUP-02: Canonical Provider Resolution Regression Tests.
- **Dependencies / Fixtures**: Mocks / Monkeypatch
- **CI Job Execution**: `unit-and-ai-tests (Full Suite Floor)`
- **Recommended Run Frequency**: `PR / Push (main)`
- **Duplicate / Overlap Classification**: `COMPLEMENTARY`
- **RIGHT Test Suite Coverage**: `R-FUNC-04`
- **Bruno Collection Coverage**: `NONE`
- **Architectural Disposition**: **`KEEP`** (Target Destination: `backend/tests/unit/`)
- **Disposition Rationale & Evidence**: Already in unit/ directory. High-value isolated unit test.
- **Discovered Test Functions (8)**:
  - [`TestAuthoritativeRegistryResolution::test_registry_resolves_required_providers`](file:///e:/JakeAI/backend/tests/unit/test_canonical_provider_resolution.py#L1): Pin the authoritative model-to-provider mapping for all 6 providers. (1 assertions)
  - [`TestAuthoritativeRegistryResolution::test_registry_default_fallback_is_gemini`](file:///e:/JakeAI/backend/tests/unit/test_canonical_provider_resolution.py#L1): Unknown models default to gemini, matching routing behavior. (1 assertions)
  - [`TestGatewayChatCompletionsCanonicalResolution::test_cache_identity_uses_authoritative_provider`](file:///e:/JakeAI/backend/tests/unit/test_canonical_provider_resolution.py#L1): Gateway cache identity and BYOK injection must use the canonical provider. (5 assertions)
  - [`TestGatewayChatCompletionsCanonicalResolution::test_byok_injection_targets_authoritative_provider`](file:///e:/JakeAI/backend/tests/unit/test_canonical_provider_resolution.py#L1): Gateway cache identity and BYOK injection must use the canonical provider. (1 assertions)
  - [`TestGatewayChatCompletionsCanonicalResolution::test_gateway_resolution_matches_authoritative_resolver`](file:///e:/JakeAI/backend/tests/unit/test_canonical_provider_resolution.py#L1): Gateway-resolved provider must equal the authoritative resolver output. (2 assertions)
  - [`TestGatewayStreamCanonicalResolution::test_stream_cache_identity_uses_authoritative_provider`](file:///e:/JakeAI/backend/tests/unit/test_canonical_provider_resolution.py#L1): Streaming cache identity must use the canonical provider. (3 assertions)
  - [`TestGatewayStreamCanonicalResolution::test_stream_resolution_matches_authoritative_resolver`](file:///e:/JakeAI/backend/tests/unit/test_canonical_provider_resolution.py#L1): Stream-resolved provider must equal the authoritative resolver output. (2 assertions)
  - [`TestDispatcherByokSelection::test_byok_key_matches_routing_decision_provider`](file:///e:/JakeAI/backend/tests/unit/test_canonical_provider_resolution.py#L1): call_upstream_llm_detailed must select BYOK credentials per the (6 assertions)

#### `CAT-093`: [`test_direct_provider.py`](file:///e:/JakeAI/backend/tests/unit/test_direct_provider.py)
- **Test File Path**: `backend/tests/unit/test_direct_provider.py` (267 lines)
- **Subsystem**: `Core / Platform`
- **Test Level**: `Unit`
- **Purpose**: Unit tests for DirectProviderBackend adapter and credential hygiene.
- **Dependencies / Fixtures**: HTTP / ASGI, Mocks / Monkeypatch
- **CI Job Execution**: `unit-and-ai-tests (Full Suite Floor)`
- **Recommended Run Frequency**: `PR / Push (main)`
- **Duplicate / Overlap Classification**: `COMPLEMENTARY`
- **RIGHT Test Suite Coverage**: `R-FUNC-04`
- **Bruno Collection Coverage**: `NONE`
- **Architectural Disposition**: **`KEEP`** (Target Destination: `backend/tests/unit/`)
- **Disposition Rationale & Evidence**: Already in unit/ directory. High-value isolated unit test.
- **Discovered Test Functions (7)**:
  - [`test_direct_provider_defaults_and_credentials`](file:///e:/JakeAI/backend/tests/unit/test_direct_provider.py#L1): Verify default base URLs, default models, credentials setting, and redaction. (13 assertions)
  - [`test_direct_provider_anthropic_headers_and_call`](file:///e:/JakeAI/backend/tests/unit/test_direct_provider.py#L1): Verify Anthropic provider configuration uses x-api-key and anthropic-version. (6 assertions)
  - [`test_direct_provider_user_api_key_override`](file:///e:/JakeAI/backend/tests/unit/test_direct_provider.py#L1): Verify request metadata user_api_key overrides or supplies missing credentials. (2 assertions)
  - [`test_direct_provider_http_error_response`](file:///e:/JakeAI/backend/tests/unit/test_direct_provider.py#L1): Verify non-200 HTTP response is cleanly reported without crashing or leaking keys. (3 assertions)
  - [`test_direct_provider_tool_calls_parsing`](file:///e:/JakeAI/backend/tests/unit/test_direct_provider.py#L1): Verify tool_calls payload with JSON string and dictionary arguments are parsed properly. (9 assertions)
  - [`test_direct_provider_exception_handling`](file:///e:/JakeAI/backend/tests/unit/test_direct_provider.py#L1): Verify network exception handling returns an error response with redacted error info. (3 assertions)
  - [`test_direct_provider_generate_stream`](file:///e:/JakeAI/backend/tests/unit/test_direct_provider.py#L1): Verify generate_stream yields a BackendStreamChunk from the generated response. (4 assertions)

#### `CAT-094`: [`test_state_bridges.py`](file:///e:/JakeAI/backend/tests/unit/test_state_bridges.py)
- **Test File Path**: `backend/tests/unit/test_state_bridges.py` (110 lines)
- **Subsystem**: `Core / Platform`
- **Test Level**: `Unit`
- **Purpose**: Unit tests for WORK-01 state bridge converters and RunState bidirectional mapping.
- **Dependencies / Fixtures**: None (Pure In-Memory)
- **CI Job Execution**: `unit-and-ai-tests (Full Suite Floor)`
- **Recommended Run Frequency**: `PR / Push (main)`
- **Duplicate / Overlap Classification**: `COMPLEMENTARY`
- **RIGHT Test Suite Coverage**: `NONE`
- **Bruno Collection Coverage**: `NONE`
- **Architectural Disposition**: **`KEEP`** (Target Destination: `backend/tests/unit/`)
- **Disposition Rationale & Evidence**: Already in unit/ directory. High-value isolated unit test.
- **Discovered Test Functions (2)**:
  - [`test_run_state_bidirectional_conversion`](file:///e:/JakeAI/backend/tests/unit/test_state_bridges.py#L1): Verify RunState.to_agent_state() and RunState.from_agent_state(). (15 assertions)
  - [`test_state_bridge_helpers`](file:///e:/JakeAI/backend/tests/unit/test_state_bridges.py#L1): Verify run_state_to_agent_state and agent_state_to_run_state utility functions. (9 assertions)

### 3.6 Subsystem: DevOps Bot (1 Files)
#### `CAT-012`: [`test_devops_bot.py`](file:///e:/JakeAI/backend/tests/test_devops_bot.py)
- **Test File Path**: `backend/tests/test_devops_bot.py` (151 lines)
- **Subsystem**: `DevOps Bot`
- **Test Level**: `Unit`
- **Purpose**: Unit and integration tests for DevOps & Codebase Audit Bot SaaS.
- **Dependencies / Fixtures**: Redis, HTTP / ASGI
- **CI Job Execution**: `unit-and-ai-tests (Full Suite Floor)`
- **Recommended Run Frequency**: `PR / Push (main)`
- **Duplicate / Overlap Classification**: `COMPLEMENTARY`
- **RIGHT Test Suite Coverage**: `NONE`
- **Bruno Collection Coverage**: `NONE`
- **Architectural Disposition**: **`MOVE`** (Target Destination: `backend/tests/unit/`)
- **Disposition Rationale & Evidence**: Valuable subsystem test. Needs reclassification into unit/, integration/, or security/.
- **Discovered Test Functions (5)**:
  - [`test_diff_pruner_strips_lockfiles`](file:///e:/JakeAI/backend/tests/test_devops_bot.py#L1): Verify DiffPruner strips package-lock.json and preserves code diffs. (3 assertions)
  - [`test_audit_bot_approves_or_comments`](file:///e:/JakeAI/backend/tests/test_devops_bot.py#L1): Verify audit bot analyzes PR and detects missing tests. (4 assertions)
  - [`test_audit_bot_flags_security_risks`](file:///e:/JakeAI/backend/tests/test_devops_bot.py#L1): Verify audit bot detects eval execution and requests changes. (3 assertions)
  - [`test_changelog_synthesis`](file:///e:/JakeAI/backend/tests/test_devops_bot.py#L1): Verify changelog synthesizes commits and PRs into grouped markdown sections. (6 assertions)
  - [`test_devops_api_endpoints`](file:///e:/JakeAI/backend/tests/test_devops_bot.py#L1): Verify DevOps REST endpoints: audit-pr and changelog. (7 assertions)

### 3.7 Subsystem: FinOps & Billing (4 Files)
#### `CAT-016`: [`test_finops_accounting.py`](file:///e:/JakeAI/backend/tests/test_finops_accounting.py)
- **Test File Path**: `backend/tests/test_finops_accounting.py` (638 lines)
- **Subsystem**: `FinOps & Billing`
- **Test Level**: `Unit`
- **Purpose**: Unit and Integration Tests for Phase 05 AI FinOps & Cost Truth.
- **Dependencies / Fixtures**: None (Pure In-Memory)
- **CI Job Execution**: `unit-and-ai-tests (Full Suite Floor)`
- **Recommended Run Frequency**: `PR / Push (main)`
- **Duplicate / Overlap Classification**: `COMPLEMENTARY`
- **RIGHT Test Suite Coverage**: `R-LOGIC-03`
- **Bruno Collection Coverage**: `Bruno/07 — FinOps & Billing (01-06)`
- **Architectural Disposition**: **`MOVE`** (Target Destination: `backend/tests/unit/`)
- **Disposition Rationale & Evidence**: Valuable subsystem test. Needs reclassification into unit/, integration/, or security/.
- **Discovered Test Functions (21)**:
  - [`test_finops_pricing_matrix`](file:///e:/JakeAI/backend/tests/test_finops_accounting.py#L1): Verify official pricing definitions across providers. (12 assertions)
  - [`test_baseline_and_billed_cost_calculation`](file:///e:/JakeAI/backend/tests/test_finops_accounting.py#L1): Verify baseline and actual billed cost formulas. (2 assertions)
  - [`test_provider_cache_savings_calculation`](file:///e:/JakeAI/backend/tests/test_finops_accounting.py#L1): Verify provider prompt caching net discount. (2 assertions)
  - [`test_model_routing_savings`](file:///e:/JakeAI/backend/tests/test_finops_accounting.py#L1): Verify intelligent routing cost delta. (1 assertions)
  - [`test_separate_metrics_never_collapsed`](file:///e:/JakeAI/backend/tests/test_finops_accounting.py#L1): Phase 05 Section 1 Mandate: All 8 metrics must be distinct and non-collapsed. (12 assertions)
  - [`test_non_overlapping_savings_attribution_cache_hit`](file:///e:/JakeAI/backend/tests/test_finops_accounting.py#L1): Verify that JakeAI response cache hit attributes 100% to cache_hit_usd with zero double-counting. (6 assertions)
  - [`test_non_overlapping_savings_attribution_cache_miss`](file:///e:/JakeAI/backend/tests/test_finops_accounting.py#L1): Verify cache miss partitions physical reduction, provider prompt cache, and model routing. (5 assertions)
  - [`test_savings_attribution_validator_consistency`](file:///e:/JakeAI/backend/tests/test_finops_accounting.py#L1): Pydantic model validator ensures total_savings_usd is consistent. (1 assertions)
  - [`test_billing_truth_reconciliation_with_provider_usage`](file:///e:/JakeAI/backend/tests/test_finops_accounting.py#L1): Phase 05 Section 3: Provider-reported usage is authoritative reconciliation source. (6 assertions)
  - [`test_billing_truth_reconciliation_anomaly_detection`](file:///e:/JakeAI/backend/tests/test_finops_accounting.py#L1): Detect billing anomaly when provider bills significantly higher than local estimate (>25%). (4 assertions)
  - [`test_billing_truth_reconciliation_offline_fallback`](file:///e:/JakeAI/backend/tests/test_finops_accounting.py#L1): When provider usage is not available, status remains ESTIMATED. (4 assertions)
  - [`test_finops_budget_manager_soft_warning_and_hard_suspension`](file:///e:/JakeAI/backend/tests/test_finops_accounting.py#L1): Phase 05 Section 5: Verify quota warnings (80%) and hard suspension (100%). (10 assertions)
  - [`test_finops_budget_manager_dollar_budget_suspension`](file:///e:/JakeAI/backend/tests/test_finops_accounting.py#L1): Verify hard suspension triggers if dollar budget is exceeded before token quota. (4 assertions)
  - [`test_finops_service_end_to_end_lifecycle`](file:///e:/JakeAI/backend/tests/test_finops_accounting.py#L1): Verify end-to-end recording of cache hit and upstream call with FinOpsService. (18 assertions)
  - [`test_finops_ledger_multi_tenant_isolation`](file:///e:/JakeAI/backend/tests/test_finops_accounting.py#L1): Negative proof test: Multi-tenant boundary isolation ensures cross-tenant data leakage is impossible. (10 assertions)
  - [`test_finops_ledger_zero_secret_leakage`](file:///e:/JakeAI/backend/tests/test_finops_accounting.py#L1): Validate that API keys, auth tokens, and Bearer headers are scrubbed from FinOps records. (7 assertions)
  - [`test_finops_ledger_bounded_ring_buffer_eviction`](file:///e:/JakeAI/backend/tests/test_finops_accounting.py#L1): Verify bounded ring-buffer evicts oldest records when limit is reached. (2 assertions)
  - [`test_finops_ledger_period_filter`](file:///e:/JakeAI/backend/tests/test_finops_accounting.py#L1): Verify get_records correctly filters by period (YYYY-MM). (5 assertions)
  - [`test_model_routing_identical_model_savings_zero`](file:///e:/JakeAI/backend/tests/test_finops_accounting.py#L1): Verify calculate_model_routing_savings returns 0.0 when requested and selected models match. (2 assertions)
  - [`test_finops_service_check_budget_delegation`](file:///e:/JakeAI/backend/tests/test_finops_accounting.py#L1): Verify FinOpsService.check_budget properly delegates to FinOpsBudgetManager. (4 assertions)
  - [`test_finops_budget_status_soft_warning_text`](file:///e:/JakeAI/backend/tests/test_finops_accounting.py#L1): Verify get_budget_status sets actionable warning string when approaching budget limit. (4 assertions)

#### `CAT-052`: [`test_r_logic_03_accounting.py`](file:///e:/JakeAI/backend/tests/test_r_logic_03_accounting.py)
- **Test File Path**: `backend/tests/test_r_logic_03_accounting.py` (808 lines)
- **Subsystem**: `FinOps & Billing`
- **Test Level**: `Regression (RIGHT Verification)`
- **Purpose**: R-LOGIC-03 — Accounting regression tests.
- **Dependencies / Fixtures**: Redis, HTTP / ASGI, Mocks / Monkeypatch
- **CI Job Execution**: `unit-and-ai-tests (Full Suite Floor)`
- **Recommended Run Frequency**: `PR / Push (main)`
- **Duplicate / Overlap Classification**: `COMPLEMENTARY`
- **RIGHT Test Suite Coverage**: `R-LOGIC-03`
- **Bruno Collection Coverage**: `NONE`
- **Architectural Disposition**: **`MOVE`** (Target Destination: `backend/tests/unit/`)
- **Disposition Rationale & Evidence**: Authoritative RIGHT verification suite for R-LOGIC-03. Move to dedicated integration/ or regression/ target folder.
- **Discovered Test Functions (23)**:
  - [`test_zero_token_request_reports_no_false_savings`](file:///e:/JakeAI/backend/tests/test_r_logic_03_accounting.py#L1): A zero-token transaction must not fabricate savings off the max(1,...) (3 assertions)
  - [`test_zero_token_cache_hit_reports_no_false_avoidance`](file:///e:/JakeAI/backend/tests/test_r_logic_03_accounting.py#L1): Direct assertion (3 assertions)
  - [`test_negative_token_values_rejected_everywhere`](file:///e:/JakeAI/backend/tests/test_r_logic_03_accounting.py#L1): Negative inputs previously produced billed=-60 (quota refund fabrication). (0 assertions)
  - [`test_negative_settlement_and_reservation_inputs_rejected`](file:///e:/JakeAI/backend/tests/test_r_logic_03_accounting.py#L1): Direct assertion (1 assertions)
  - [`test_very_large_token_values_settle_and_deny`](file:///e:/JakeAI/backend/tests/test_r_logic_03_accounting.py#L1): 10^9-token transactions round-trip without crash and trip the hard stop. (4 assertions)
  - [`test_rounding_boundaries_reduced_to_declared_precision`](file:///e:/JakeAI/backend/tests/test_r_logic_03_accounting.py#L1): Direct assertion (2 assertions)
  - [`test_provider_explicit_zero_cached_wins_over_local_assumption`](file:///e:/JakeAI/backend/tests/test_r_logic_03_accounting.py#L1): Pre-fix: provider reported cached_tokens=0 but the stale local (2 assertions)
  - [`test_provider_reported_total_settled_exactly_once`](file:///e:/JakeAI/backend/tests/test_r_logic_03_accounting.py#L1): Direct assertion (2 assertions)
  - [`test_reservation_finalize_charges_actual_not_estimate_plus_actual`](file:///e:/JakeAI/backend/tests/test_r_logic_03_accounting.py#L1): Finalizing a reservation replaces the reserved estimate with actual (5 assertions)
  - [`test_reservation_full_refund_restores_balance`](file:///e:/JakeAI/backend/tests/test_r_logic_03_accounting.py#L1): Refunds must restore the exact pre-reservation balance (no negatives). (5 assertions)
  - [`test_concurrent_requests_cannot_oversubscribe_budget`](file:///e:/JakeAI/backend/tests/test_r_logic_03_accounting.py#L1): 10 concurrent gateway requests (each reserving envelope+max_tokens) (5 assertions)
  - [`test_reservation_denial_messages_match_hard_stop_semantics`](file:///e:/JakeAI/backend/tests/test_r_logic_03_accounting.py#L1): Direct assertion (2 assertions)
  - [`test_redis_lua_denial_results_map_to_correct_messages`](file:///e:/JakeAI/backend/tests/test_r_logic_03_accounting.py#L1): Direct assertion (5 assertions)
  - [`test_redis_lua_granted_result_builds_reservation`](file:///e:/JakeAI/backend/tests/test_r_logic_03_accounting.py#L1): Direct assertion (4 assertions)
  - [`test_gateway_cache_hit_refunds_reservation_and_records_ledger`](file:///e:/JakeAI/backend/tests/test_r_logic_03_accounting.py#L1): Direct assertion (5 assertions)
  - [`test_gateway_stream_settles_dollars_and_ledger`](file:///e:/JakeAI/backend/tests/test_r_logic_03_accounting.py#L1): Pre-fix the stream path settled token counts only (zero dollars, no (6 assertions)
  - [`test_gateway_stream_cache_hit_records_ledger_and_refunds`](file:///e:/JakeAI/backend/tests/test_r_logic_03_accounting.py#L1): Direct assertion (3 assertions)
  - [`test_gateway_usage_total_equals_prompt_plus_completion`](file:///e:/JakeAI/backend/tests/test_r_logic_03_accounting.py#L1): Pre-fix: response reported the provider-cache discount equivalent (2 assertions)
  - [`test_chat_stream_http_settles_budget_and_ledger`](file:///e:/JakeAI/backend/tests/test_r_logic_03_accounting.py#L1): HTTP boundary: POST /api/v1/chat/stream must reserve quota up front and (6 assertions)
  - [`test_chat_stream_http_hard_stop_denies_with_429`](file:///e:/JakeAI/backend/tests/test_r_logic_03_accounting.py#L1): HTTP boundary: an exhausted budget must hard-stop the stream endpoint (2 assertions)
  - [`test_chat_stream_timeout_path_settles_accounting`](file:///e:/JakeAI/backend/tests/test_r_logic_03_accounting.py#L1): Regression: the bounded-stream-timeout path previously returned without (3 assertions)
  - [`test_chat_stream_guardrail_block_refunds_reservation`](file:///e:/JakeAI/backend/tests/test_r_logic_03_accounting.py#L1): Pre-inference exit (input guardrail) must release the reservation in (3 assertions)
  - [`test_reservation_boundary_allows_exactly_full_quota`](file:///e:/JakeAI/backend/tests/test_r_logic_03_accounting.py#L1): Mirrors check_budget semantics: used + estimated == limit is allowed, (2 assertions)

#### `CAT-071`: [`test_unified_quota_authority.py`](file:///e:/JakeAI/backend/tests/test_unified_quota_authority.py)
- **Test File Path**: `backend/tests/test_unified_quota_authority.py` (107 lines)
- **Subsystem**: `FinOps & Billing`
- **Test Level**: `Unit`
- **Purpose**: Unit tests for TASK COST-05: Unified Quota & Budget Authority.
- **Dependencies / Fixtures**: None (Pure In-Memory)
- **CI Job Execution**: `unit-and-ai-tests (Full Suite Floor)`
- **Recommended Run Frequency**: `PR / Push (main)`
- **Duplicate / Overlap Classification**: `PARTIAL OVERLAP`
- **RIGHT Test Suite Coverage**: `NONE`
- **Bruno Collection Coverage**: `NONE`
- **Architectural Disposition**: **`MERGE`** (Target Destination: `backend/tests/unit/`)
- **Disposition Rationale & Evidence**: Tests quota enforcement; overlaps with test_gateway.py and test_r_logic_03_accounting.py. Merge into unit/finops/.
- **Discovered Test Functions (3)**:
  - [`test_quota_manager_delegates_to_finops_budget_manager`](file:///e:/JakeAI/backend/tests/test_unified_quota_authority.py#L1): Verify QuotaManager delegates all reads, updates, and checks to FinOpsBudgetManager. (12 assertions)
  - [`test_payos_billing_provisions_unified_budget`](file:///e:/JakeAI/backend/tests/test_unified_quota_authority.py#L1): Verify PayOS billing webhook provisions both QuotaManager and FinOpsBudgetManager synchronously. (5 assertions)
  - [`test_unified_quota_suspension_thresholds`](file:///e:/JakeAI/backend/tests/test_unified_quota_authority.py#L1): Verify soft warning and hard suspension behave identically. (6 assertions)

#### `CAT-092`: [`test_canonical_token_accounting.py`](file:///e:/JakeAI/backend/tests/unit/test_canonical_token_accounting.py)
- **Test File Path**: `backend/tests/unit/test_canonical_token_accounting.py` (647 lines)
- **Subsystem**: `FinOps & Billing`
- **Test Level**: `Unit`
- **Purpose**: Unit and regression tests for REPAIR-02: TOK-02 Canonical Token Accounting.
- **Dependencies / Fixtures**: Redis, Mocks / Monkeypatch
- **CI Job Execution**: `unit-and-ai-tests (Full Suite Floor)`
- **Recommended Run Frequency**: `PR / Push (main)`
- **Duplicate / Overlap Classification**: `COMPLEMENTARY`
- **RIGHT Test Suite Coverage**: `R-LOGIC-03`
- **Bruno Collection Coverage**: `NONE`
- **Architectural Disposition**: **`KEEP`** (Target Destination: `backend/tests/unit/`)
- **Disposition Rationale & Evidence**: Already in unit/ directory. High-value isolated unit test.
- **Discovered Test Functions (16)**:
  - [`test_accounting_envelope_system_history_query`](file:///e:/JakeAI/backend/tests/unit/test_canonical_token_accounting.py#L1): CRITICAL REQUIREMENT: Given system=2000, history=3000, query=50, (6 assertions)
  - [`test_accounting_with_tools`](file:///e:/JakeAI/backend/tests/unit/test_canonical_token_accounting.py#L1): Verifies tool definitions schema participates in model-visible input envelope. (3 assertions)
  - [`test_accounting_with_rag_context`](file:///e:/JakeAI/backend/tests/unit/test_canonical_token_accounting.py#L1): Verifies RAG context passages participate in model-visible input envelope. (3 assertions)
  - [`test_accounting_with_optimized_context`](file:///e:/JakeAI/backend/tests/unit/test_canonical_token_accounting.py#L1): Verifies tracking of raw_input_tokens, optimized_input_tokens, and physical_tokens_pruned. (8 assertions)
  - [`test_accounting_provider_cache_telemetry_reconciliation`](file:///e:/JakeAI/backend/tests/unit/test_canonical_token_accounting.py#L1): Verifies provider KV prompt cache telemetry reconciliation. (10 assertions)
  - [`test_accounting_tier1_response_cache_hit`](file:///e:/JakeAI/backend/tests/unit/test_canonical_token_accounting.py#L1): Verifies Layer A exact response cache hit accounts 100% tokens saved and 0 billed. (6 assertions)
  - [`test_conservation_of_tokens_invariant`](file:///e:/JakeAI/backend/tests/unit/test_canonical_token_accounting.py#L1): Verifies mathematical conservation law across cache miss, provider cache, and response cache hit: (9 assertions)
  - [`test_gateway_chat_completions_multi_turn_accounting`](file:///e:/JakeAI/backend/tests/unit/test_canonical_token_accounting.py#L1): E2E Gateway test: multi-turn input must NOT report raw prompt tokens as last_user_msg. (4 assertions)
  - [`test_gateway_chat_completions_cache_hit_accounting`](file:///e:/JakeAI/backend/tests/unit/test_canonical_token_accounting.py#L1): E2E Gateway test: cache hit must account the entire model-visible envelope for tokens_saved. (4 assertions)
  - [`test_gateway_chat_completions_stream_accounting`](file:///e:/JakeAI/backend/tests/unit/test_canonical_token_accounting.py#L1): E2E Gateway Streaming: verifies streaming usage deduction accounts the full envelope. (4 assertions)
  - [`test_gateway_chat_completions_stream_cache_hit_accounting`](file:///e:/JakeAI/backend/tests/unit/test_canonical_token_accounting.py#L1): E2E Gateway Streaming Cache Hit: verifies tokens_saved accounts the full envelope. (3 assertions)
  - [`test_accounting_with_assistant_tool_calls_and_tool_results`](file:///e:/JakeAI/backend/tests/unit/test_canonical_token_accounting.py#L1): Verifies that assistant turns with tool_calls and role='tool' results are counted in envelope. (2 assertions)
  - [`test_accounting_dict_messages_compatibility`](file:///e:/JakeAI/backend/tests/unit/test_canonical_token_accounting.py#L1): Verifies backward compatibility with plain dictionary message objects. (1 assertions)
  - [`test_token_usage_record_bidirectional_synchronization`](file:///e:/JakeAI/backend/tests/unit/test_canonical_token_accounting.py#L1): Verifies Pydantic model validator ensures legacy and canonical dimensions stay in sync. (8 assertions)
  - [`test_provider_reconciliation_zero_tokens_fallback`](file:///e:/JakeAI/backend/tests/unit/test_canonical_token_accounting.py#L1): Verifies that if provider telemetry reports 0 tokens, local envelope tokens are safely preserved. (5 assertions)
  - [`test_quota_manager_get_tokens_saved_redis_and_memory`](file:///e:/JakeAI/backend/tests/unit/test_canonical_token_accounting.py#L1): Verifies QuotaManager.get_tokens_saved works seamlessly via Redis and fallback memory. (3 assertions)

### 3.8 Subsystem: Gateway & Routing (4 Files)
#### `CAT-014`: [`test_endpoints.py`](file:///e:/JakeAI/backend/tests/test_endpoints.py)
- **Test File Path**: `backend/tests/test_endpoints.py` (390 lines)
- **Subsystem**: `Gateway & Routing`
- **Test Level**: `Integration (API / HTTP)`
- **Purpose**: End-to-end Integration and Contract Tests for all JakeAI Platform Endpoints.
- **Dependencies / Fixtures**: HTTP / ASGI, Mocks / Monkeypatch
- **CI Job Execution**: `unit-and-ai-tests (Full Suite Floor)`
- **Recommended Run Frequency**: `PR / Push (main)`
- **Duplicate / Overlap Classification**: `COMPLEMENTARY`
- **RIGHT Test Suite Coverage**: `R-FUNC-00 (Covered by API Behavior)`
- **Bruno Collection Coverage**: `NONE`
- **Architectural Disposition**: **`MOVE`** (Target Destination: `backend/tests/integration/`)
- **Disposition Rationale & Evidence**: Valuable subsystem test. Needs reclassification into unit/, integration/, or security/.
- **Discovered Test Functions (14)**:
  - [`test_health_endpoint_contract`](file:///e:/JakeAI/backend/tests/test_endpoints.py#L1): Verify GET /health returns standard 200 OK with expected schema. (5 assertions)
  - [`test_openapi_documentation_contract`](file:///e:/JakeAI/backend/tests/test_endpoints.py#L1): Verify GET /openapi.json returns valid OpenAPI 3.0 document with security scheme. (6 assertions)
  - [`test_chat_stream_endpoint_standard_flow`](file:///e:/JakeAI/backend/tests/test_endpoints.py#L1): Verify POST /api/v1/chat/stream streams complete SSE frames with valid JWT. (8 assertions)
  - [`test_chat_stream_endpoint_guardrail_injection_blocking`](file:///e:/JakeAI/backend/tests/test_endpoints.py#L1): Verify POST /api/v1/chat/stream rejects prompt injections at the perimeter. (5 assertions)
  - [`test_chat_stream_endpoint_semantic_cache_hit`](file:///e:/JakeAI/backend/tests/test_endpoints.py#L1): Verify second identical request hits Semantic Cache and fast-returns. (7 assertions)
  - [`test_chat_stream_endpoint_tool_invocation_with_obo`](file:///e:/JakeAI/backend/tests/test_endpoints.py#L1): Verify tool execution emits tool_call events with delegated credentials. (3 assertions)
  - [`test_chat_stream_unauthenticated`](file:///e:/JakeAI/backend/tests/test_endpoints.py#L1): Verify /chat/stream rejects requests without credentials. (1 assertions)
  - [`test_chat_stream_invalid_token`](file:///e:/JakeAI/backend/tests/test_endpoints.py#L1): Verify /chat/stream rejects malformed JWT tokens. (1 assertions)
  - [`test_chat_stream_expired_token`](file:///e:/JakeAI/backend/tests/test_endpoints.py#L1): Verify /chat/stream rejects expired JWT tokens with 401. (1 assertions)
  - [`test_chat_stream_rbac_blocking`](file:///e:/JakeAI/backend/tests/test_endpoints.py#L1): Verify pre-tool RBAC blocks unauthorized callers and flags tool_blocked. (2 assertions)
  - [`test_chat_stream_query_alias_compatibility`](file:///e:/JakeAI/backend/tests/test_endpoints.py#L1): Verify endpoint accepts {query: '...'} payload seamlessly for frontend widget. (2 assertions)
  - [`test_rag_ingest_endpoint`](file:///e:/JakeAI/backend/tests/test_endpoints.py#L1): Verify POST /api/v1/rag/ingest accepts document, chunks it, and returns 201. (7 assertions)
  - [`test_api_v1_health_endpoint`](file:///e:/JakeAI/backend/tests/test_endpoints.py#L1): Verify GET /api/v1/health returns operational metrics matching root probe. (4 assertions)
  - [`test_rag_query_endpoint`](file:///e:/JakeAI/backend/tests/test_endpoints.py#L1): Verify POST /api/v1/rag/query retrieves indexed chunks for tenant. (5 assertions)

#### `CAT-017`: [`test_finops_endpoints.py`](file:///e:/JakeAI/backend/tests/test_finops_endpoints.py)
- **Test File Path**: `backend/tests/test_finops_endpoints.py` (117 lines)
- **Subsystem**: `Gateway & Routing`
- **Test Level**: `Integration (API / HTTP)`
- **Purpose**: REST API Contract and Integration Tests for AI FinOps Endpoints.
- **Dependencies / Fixtures**: HTTP / ASGI
- **CI Job Execution**: `unit-and-ai-tests (Full Suite Floor)`
- **Recommended Run Frequency**: `PR / Push (main)`
- **Duplicate / Overlap Classification**: `PARTIAL OVERLAP`
- **RIGHT Test Suite Coverage**: `R-FUNC-00 (Covered by API Behavior)`
- **Bruno Collection Coverage**: `Bruno/07 — FinOps & Billing (01-06)`
- **Architectural Disposition**: **`MERGE`** (Target Destination: `backend/tests/integration/`)
- **Disposition Rationale & Evidence**: Only 3 tests; overlaps with test_finops_accounting.py and test_r_func_00_api_behavior.py. Merge into integration/finops/.
- **Discovered Test Functions (3)**:
  - [`test_finops_endpoints_summary_and_budget`](file:///e:/JakeAI/backend/tests/test_finops_endpoints.py#L1): Verify GET /api/v1/finops/summary and /budget endpoints. (13 assertions)
  - [`test_finops_endpoints_transactions_and_reconciliation`](file:///e:/JakeAI/backend/tests/test_finops_endpoints.py#L1): Verify GET /api/v1/finops/transactions and /reconciliation. (6 assertions)
  - [`test_finops_unauthorized_access`](file:///e:/JakeAI/backend/tests/test_finops_endpoints.py#L1): Verify 401 Unauthorized when no valid Bearer token is provided. (1 assertions)

#### `CAT-018`: [`test_gateway.py`](file:///e:/JakeAI/backend/tests/test_gateway.py)
- **Test File Path**: `backend/tests/test_gateway.py` (605 lines)
- **Subsystem**: `Gateway & Routing`
- **Test Level**: `Unit`
- **Purpose**: Unit and integration tests for Gateway security, PEP, and SSE streaming.
- **Dependencies / Fixtures**: Redis, HTTP / ASGI, Mocks / Monkeypatch
- **CI Job Execution**: `unit-and-ai-tests (Full Suite Floor)`
- **Recommended Run Frequency**: `PR / Push (main)`
- **Duplicate / Overlap Classification**: `COMPLEMENTARY`
- **RIGHT Test Suite Coverage**: `R-FUNC-00 (Covered by API Behavior)`
- **Bruno Collection Coverage**: `Bruno/02 — Chat & Gateway (01-07)`
- **Architectural Disposition**: **`MOVE`** (Target Destination: `backend/tests/integration/`)
- **Disposition Rationale & Evidence**: Valuable subsystem test. Needs reclassification into unit/, integration/, or security/.
- **Discovered Test Functions (23)**:
  - [`test_verify_valid_jwt`](file:///e:/JakeAI/backend/tests/test_gateway.py#L1): Verify standard valid JWT parses correctly into TenantContext. (5 assertions)
  - [`test_verify_expired_jwt`](file:///e:/JakeAI/backend/tests/test_gateway.py#L1): Verify expired token raises HTTP 401 Unauthorized. (2 assertions)
  - [`test_verify_invalid_signature`](file:///e:/JakeAI/backend/tests/test_gateway.py#L1): Verify forged signature raises HTTP 401 Unauthorized. (2 assertions)
  - [`test_verify_missing_claims`](file:///e:/JakeAI/backend/tests/test_gateway.py#L1): Verify token missing sub or tenant_id raises HTTP 401. (1 assertions)
  - [`test_verify_jwt_key_rotation_previous_secret`](file:///e:/JakeAI/backend/tests/test_gateway.py#L1): Verify that a token signed with JWT_SECRET_PREVIOUS is accepted during rotation. (2 assertions)
  - [`test_verify_jwt_kid_matching`](file:///e:/JakeAI/backend/tests/test_gateway.py#L1): Verify that a token with kid header matching sha256(secret)[:8] resolves accurately. (3 assertions)
  - [`test_require_permissions_dependency`](file:///e:/JakeAI/backend/tests/test_gateway.py#L1): Verify require_permissions validator permits authorized tenants. (3 assertions)
  - [`test_token_bucket_rate_limiter`](file:///e:/JakeAI/backend/tests/test_gateway.py#L1): Verify token bucket rate limiter permits burst and exhausts tokens. (4 assertions)
  - [`test_chat_stream_unauthorized`](file:///e:/JakeAI/backend/tests/test_gateway.py#L1): Verify /chat/stream rejects requests without Bearer token. (1 assertions)
  - [`test_chat_stream_success`](file:///e:/JakeAI/backend/tests/test_gateway.py#L1): Verify /chat/stream validates JWT, injects context, and streams SSE. (7 assertions)
  - [`test_exchange_obo_token`](file:///e:/JakeAI/backend/tests/test_gateway.py#L1): Verify On-Behalf-Of (OBO) token exchange produces valid delegation JWT. (8 assertions)
  - [`test_verify_finnapigo_compact_enterprise_claims`](file:///e:/JakeAI/backend/tests/test_gateway.py#L1): Verify FinnApiGo compact enterprise token (tid, uid, perms, role) parses correctly. (5 assertions)
  - [`test_verify_token_type_isolation`](file:///e:/JakeAI/backend/tests/test_gateway.py#L1): Verify non-access token types (e.g. reset or email verify) are rejected with 401. (2 assertions)
  - [`test_verify_internal_perimeter_secret_validation`](file:///e:/JakeAI/backend/tests/test_gateway.py#L1): Verify Invariant 4 perimeter provenance validation via X-Internal-Secret and HMAC. (5 assertions)
  - [`test_rate_limiter_perimeter_spoofing_defense`](file:///e:/JakeAI/backend/tests/test_gateway.py#L1): Verify rate limiter blocks spoofed X-Forwarded-By and allows authenticated edge requests. (1 assertions)
  - [`test_check_token_denylist_revoked_jti`](file:///e:/JakeAI/backend/tests/test_gateway.py#L1): Verify check_token_denylist blocks revoked JTI tokens. (2 assertions)
  - [`test_check_token_denylist_revoked_sid`](file:///e:/JakeAI/backend/tests/test_gateway.py#L1): Verify check_token_denylist blocks revoked session SID tokens. (2 assertions)
  - [`test_check_token_denylist_malformed_and_resilient`](file:///e:/JakeAI/backend/tests/test_gateway.py#L1): Verify check_token_denylist handles malformed tokens and Redis connection drop. (0 assertions)
  - [`test_verify_internal_perimeter_secret_edge_cases`](file:///e:/JakeAI/backend/tests/test_gateway.py#L1): Verify perimeter secret checks for None request and malformed HMAC signatures. (2 assertions)
  - [`test_verify_malformed_jwt_returns_401`](file:///e:/JakeAI/backend/tests/test_gateway.py#L1): Verify completely malformed JWT returns HTTP 401 instead of unhandled error. (3 assertions)
  - [`test_verify_malformed_jwt_header_does_not_cause_500`](file:///e:/JakeAI/backend/tests/test_gateway.py#L1): Verify malformed base64 header does not cause HTTP 500 and raises HTTP 401. (2 assertions)
  - [`test_verify_header_inspection_failure_does_not_bypass_signature`](file:///e:/JakeAI/backend/tests/test_gateway.py#L1): Verify header inspection failure or header tampering never bypasses signature verification. (2 assertions)
  - [`test_verify_normal_token_validation_path_unchanged`](file:///e:/JakeAI/backend/tests/test_gateway.py#L1): Verify normal token validation path continues to produce complete TenantContext. (5 assertions)

#### `CAT-025`: [`test_openai_compatibility.py`](file:///e:/JakeAI/backend/tests/test_openai_compatibility.py)
- **Test File Path**: `backend/tests/test_openai_compatibility.py` (114 lines)
- **Subsystem**: `Gateway & Routing`
- **Test Level**: `Integration (API / HTTP)`
- **Purpose**: Tests for OpenAI-compatible API routes (/v1/models and /v1/chat/completions).
- **Dependencies / Fixtures**: Mocks / Monkeypatch
- **CI Job Execution**: `unit-and-ai-tests (Full Suite Floor)`
- **Recommended Run Frequency**: `PR / Push (main)`
- **Duplicate / Overlap Classification**: `COMPLEMENTARY`
- **RIGHT Test Suite Coverage**: `NONE`
- **Bruno Collection Coverage**: `NONE`
- **Architectural Disposition**: **`MOVE`** (Target Destination: `backend/tests/unit/`)
- **Disposition Rationale & Evidence**: Valuable subsystem test. Needs reclassification into unit/, integration/, or security/.
- **Discovered Test Functions (4)**:
  - [`test_models_catalog_unauthenticated`](file:///e:/JakeAI/backend/tests/test_openai_compatibility.py#L1): GET /v1/models without JWT returns 401 Unauthorized. (1 assertions)
  - [`test_models_catalog_authenticated`](file:///e:/JakeAI/backend/tests/test_openai_compatibility.py#L1): GET /v1/models returns standard OpenAI list with active model catalog. (6 assertions)
  - [`test_chat_completions_root_proxy`](file:///e:/JakeAI/backend/tests/test_openai_compatibility.py#L1): POST /v1/chat/completions processes completions with OpenAI structure. (7 assertions)
  - [`test_chat_completions_exact_caching`](file:///e:/JakeAI/backend/tests/test_openai_compatibility.py#L1): Repeated prompt to /v1/chat/completions hits Tier 1 cache with 0 prompt tokens. (5 assertions)

### 3.9 Subsystem: Health & Diagnostics (1 Files)
#### `CAT-021`: [`test_health.py`](file:///e:/JakeAI/backend/tests/test_health.py)
- **Test File Path**: `backend/tests/test_health.py` (82 lines)
- **Subsystem**: `Health & Diagnostics`
- **Test Level**: `Unit`
- **Purpose**: Unit and integration tests for service health probes and OpenAPI schema.
- **Dependencies / Fixtures**: HTTP / ASGI
- **CI Job Execution**: `unit-and-ai-tests (Full Suite Floor)`
- **Recommended Run Frequency**: `PR / Push (main)`
- **Duplicate / Overlap Classification**: `COMPLEMENTARY`
- **RIGHT Test Suite Coverage**: `R-FUNC-00 (Covered by API Behavior)`
- **Bruno Collection Coverage**: `Bruno/00 — Setup & Environment (01-Health Smoke)`
- **Architectural Disposition**: **`MOVE`** (Target Destination: `backend/tests/integration/`)
- **Disposition Rationale & Evidence**: Valuable subsystem test. Needs reclassification into unit/, integration/, or security/.
- **Discovered Test Functions (5)**:
  - [`test_root_health_endpoint`](file:///e:/JakeAI/backend/tests/test_health.py#L1): Verify root health probe returns 200 OK and expected diagnostic schema. (7 assertions)
  - [`test_v1_health_endpoint`](file:///e:/JakeAI/backend/tests/test_health.py#L1): Verify versioned API v1 health probe returns 200 OK. (3 assertions)
  - [`test_openapi_schema_generation`](file:///e:/JakeAI/backend/tests/test_health.py#L1): Verify OpenAPI specification complies with OpenAPI 3.0 and FinnApiGoAuth. (9 assertions)
  - [`test_swagger_and_redoc_documentation_pages`](file:///e:/JakeAI/backend/tests/test_health.py#L1): Verify Swagger UI and ReDoc HTML documentation endpoints load successfully. (4 assertions)
  - [`test_export_openapi_cli`](file:///e:/JakeAI/backend/tests/test_health.py#L1): Verify static export of OpenAPI specification to file. (2 assertions)

### 3.10 Subsystem: Observability & Telemetry (1 Files)
#### `CAT-024`: [`test_observability_and_tracing.py`](file:///e:/JakeAI/backend/tests/test_observability_and_tracing.py)
- **Test File Path**: `backend/tests/test_observability_and_tracing.py` (169 lines)
- **Subsystem**: `Observability & Telemetry`
- **Test Level**: `Unit`
- **Purpose**: Unit tests for Structured Telemetry, Prometheus Exposition, and W3C Distributed Tracing (TASK OPS-05, OPS-06, OPS-07, OPS-17).
- **Dependencies / Fixtures**: HTTP / ASGI
- **CI Job Execution**: `unit-and-ai-tests (Full Suite Floor)`
- **Recommended Run Frequency**: `PR / Push (main)`
- **Duplicate / Overlap Classification**: `COMPLEMENTARY`
- **RIGHT Test Suite Coverage**: `NONE`
- **Bruno Collection Coverage**: `NONE`
- **Architectural Disposition**: **`MOVE`** (Target Destination: `backend/tests/unit/`)
- **Disposition Rationale & Evidence**: Valuable subsystem test. Needs reclassification into unit/, integration/, or security/.
- **Discovered Test Functions (5)**:
  - [`test_structured_telemetry_event_schema_and_redaction`](file:///e:/JakeAI/backend/tests/test_observability_and_tracing.py#L1): Direct assertion (7 assertions)
  - [`test_w3c_traceparent_parsing`](file:///e:/JakeAI/backend/tests/test_observability_and_tracing.py#L1): Direct assertion (9 assertions)
  - [`test_trace_context_span_hierarchy`](file:///e:/JakeAI/backend/tests/test_observability_and_tracing.py#L1): Direct assertion (11 assertions)
  - [`test_prometheus_metrics_generation`](file:///e:/JakeAI/backend/tests/test_observability_and_tracing.py#L1): Direct assertion (14 assertions)
  - [`test_get_metrics_endpoint_and_w3c_header`](file:///e:/JakeAI/backend/tests/test_observability_and_tracing.py#L1): Direct assertion (6 assertions)

### 3.11 Subsystem: RAG Pipeline (32 Files)
#### `CAT-005`: [`test_async_worker.py`](file:///e:/JakeAI/backend/tests/test_async_worker.py)
- **Test File Path**: `backend/tests/test_async_worker.py` (467 lines)
- **Subsystem**: `RAG Pipeline`
- **Test Level**: `Unit`
- **Purpose**: Unit and integration tests for Asynchronous Ingestion Task Queue & Worker.
- **Dependencies / Fixtures**: Redis, HTTP / ASGI, Mocks / Monkeypatch
- **CI Job Execution**: `unit-and-ai-tests (Full Suite Floor)`
- **Recommended Run Frequency**: `PR / Push (main)`
- **Duplicate / Overlap Classification**: `COMPLEMENTARY`
- **RIGHT Test Suite Coverage**: `NONE`
- **Bruno Collection Coverage**: `NONE`
- **Architectural Disposition**: **`MOVE`** (Target Destination: `backend/tests/unit/`)
- **Disposition Rationale & Evidence**: Valuable subsystem test. Needs reclassification into unit/, integration/, or security/.
- **Discovered Test Functions (11)**:
  - [`test_task_manager_enqueue_and_isolation`](file:///e:/JakeAI/backend/tests/test_async_worker.py#L1): Verify task enqueuing, retrieval, and multi-tenant isolation. (8 assertions)
  - [`test_task_manager_lifecycle_states`](file:///e:/JakeAI/backend/tests/test_async_worker.py#L1): Verify state transitions: QUEUED -> PROCESSING -> COMPLETED / FAILED. (13 assertions)
  - [`test_worker_process_single_run`](file:///e:/JakeAI/backend/tests/test_async_worker.py#L1): Verify IngestionWorker processes queued tasks end-to-end. (6 assertions)
  - [`test_api_async_ingest_and_polling`](file:///e:/JakeAI/backend/tests/test_async_worker.py#L1): Verify API POST /api/v1/rag/ingest?async_mode=true (202) and GET /tasks/{task_id}. (12 assertions)
  - [`test_api_sync_ingest_backward_compatibility`](file:///e:/JakeAI/backend/tests/test_async_worker.py#L1): Verify synchronous ingestion fallback (async_mode=false) returns 201 Created. (4 assertions)
  - [`test_worker_start_stop_gracefully`](file:///e:/JakeAI/backend/tests/test_async_worker.py#L1): Verify IngestionWorker starts and terminates cleanly upon stop() signal. (2 assertions)
  - [`test_worker_process_task_failure_handling`](file:///e:/JakeAI/backend/tests/test_async_worker.py#L1): Verify IngestionWorker marks task as FAILED when ingestion pipeline raises an error. (4 assertions)
  - [`test_task_manager_redis_branch_coverage`](file:///e:/JakeAI/backend/tests/test_async_worker.py#L1): Verify IngestionTaskManager with Redis backing operations. (9 assertions)
  - [`test_worker_start_loop_cancelled`](file:///e:/JakeAI/backend/tests/test_async_worker.py#L1): Verify IngestionWorker handles asyncio.CancelledError during start loop. (2 assertions)
  - [`test_worker_start_loop_exception_recovery`](file:///e:/JakeAI/backend/tests/test_async_worker.py#L1): Verify IngestionWorker loop catches generic exception, logs it, and continues. (2 assertions)
  - [`test_worker_main_entrypoint_and_interrupt`](file:///e:/JakeAI/backend/tests/test_async_worker.py#L1): Verify worker process main() entrypoint handles signals and graceful shutdown. (1 assertions)

#### `CAT-009`: [`test_correlation_propagation.py`](file:///e:/JakeAI/backend/tests/test_correlation_propagation.py)
- **Test File Path**: `backend/tests/test_correlation_propagation.py` (204 lines)
- **Subsystem**: `RAG Pipeline`
- **Test Level**: `Unit`
- **Purpose**: Unit tests for end-to-end Correlation ID propagation across JakeAI components (TASK OPS-04).
- **Dependencies / Fixtures**: Mocks / Monkeypatch
- **CI Job Execution**: `unit-and-ai-tests (Full Suite Floor)`
- **Recommended Run Frequency**: `PR / Push (main)`
- **Duplicate / Overlap Classification**: `COMPLEMENTARY`
- **RIGHT Test Suite Coverage**: `NONE`
- **Bruno Collection Coverage**: `NONE`
- **Architectural Disposition**: **`MOVE`** (Target Destination: `backend/tests/unit/`)
- **Disposition Rationale & Evidence**: Valuable subsystem test. Needs reclassification into unit/, integration/, or security/.
- **Discovered Test Functions (6)**:
  - [`test_tenant_context_and_obo_token_correlation_id`](file:///e:/JakeAI/backend/tests/test_correlation_propagation.py#L1): Direct assertion (4 assertions)
  - [`test_router_correlation_id_propagation`](file:///e:/JakeAI/backend/tests/test_correlation_propagation.py#L1): Direct assertion (2 assertions)
  - [`test_llm_provider_correlation_id_propagation`](file:///e:/JakeAI/backend/tests/test_correlation_propagation.py#L1): Direct assertion (4 assertions)
  - [`test_rag_pipeline_correlation_id_propagation`](file:///e:/JakeAI/backend/tests/test_correlation_propagation.py#L1): Direct assertion (1 assertions)
  - [`test_agent_execution_loop_correlation_id_propagation`](file:///e:/JakeAI/backend/tests/test_correlation_propagation.py#L1): Direct assertion (3 assertions)
  - [`test_finnapigo_tool_node_correlation_id_propagation`](file:///e:/JakeAI/backend/tests/test_correlation_propagation.py#L1): Direct assertion (2 assertions)

#### `CAT-020`: [`test_harmonization.py`](file:///e:/JakeAI/backend/tests/test_harmonization.py)
- **Test File Path**: `backend/tests/test_harmonization.py` (110 lines)
- **Subsystem**: `RAG Pipeline`
- **Test Level**: `Unit`
- **Purpose**: Tests verifying cross-layer architectural harmonization and synchronization.
- **Dependencies / Fixtures**: Mocks / Monkeypatch
- **CI Job Execution**: `unit-and-ai-tests (Full Suite Floor)`
- **Recommended Run Frequency**: `PR / Push (main)`
- **Duplicate / Overlap Classification**: `COMPLEMENTARY`
- **RIGHT Test Suite Coverage**: `NONE`
- **Bruno Collection Coverage**: `NONE`
- **Architectural Disposition**: **`MOVE`** (Target Destination: `backend/tests/unit/`)
- **Disposition Rationale & Evidence**: Valuable subsystem test. Needs reclassification into unit/, integration/, or security/.
- **Discovered Test Functions (5)**:
  - [`test_singleton_harmonization`](file:///e:/JakeAI/backend/tests/test_harmonization.py#L1): Verify that all components share identical singleton instances. (4 assertions)
  - [`test_call_upstream_llm_gemini_success`](file:///e:/JakeAI/backend/tests/test_harmonization.py#L1): Verify call_upstream_llm dispatches correctly to Google Gemini. (1 assertions)
  - [`test_call_upstream_llm_openai_success`](file:///e:/JakeAI/backend/tests/test_harmonization.py#L1): Verify call_upstream_llm dispatches correctly to OpenAI. (1 assertions)
  - [`test_call_upstream_llm_network_error_graceful_fallback`](file:///e:/JakeAI/backend/tests/test_harmonization.py#L1): Verify call_upstream_llm gracefully returns None on network failures. (1 assertions)
  - [`test_ai_gateway_calls_upstream_llm_when_available`](file:///e:/JakeAI/backend/tests/test_harmonization.py#L1): Verify AI Gateway proxy leverages call_upstream_llm for live model inference. (1 assertions)

#### `CAT-029`: [`test_phase07_production_hardening.py`](file:///e:/JakeAI/backend/tests/test_phase07_production_hardening.py)
- **Test File Path**: `backend/tests/test_phase07_production_hardening.py` (575 lines)
- **Subsystem**: `RAG Pipeline`
- **Test Level**: `Integration (API / HTTP)`
- **Purpose**: Production Hardening, API Contract, Streaming & Resilience Test Suite for Phase 07.
- **Dependencies / Fixtures**: Redis, Qdrant, HTTP / ASGI, Mocks / Monkeypatch
- **CI Job Execution**: `unit-and-ai-tests (Full Suite Floor)`
- **Recommended Run Frequency**: `PR / Push (main)`
- **Duplicate / Overlap Classification**: `COMPLEMENTARY`
- **RIGHT Test Suite Coverage**: `NONE`
- **Bruno Collection Coverage**: `NONE`
- **Architectural Disposition**: **`MOVE`** (Target Destination: `backend/tests/unit/`)
- **Disposition Rationale & Evidence**: Valuable subsystem test. Needs reclassification into unit/, integration/, or security/.
- **Discovered Test Functions (18)**:
  - [`test_health_endpoints_backward_compatibility`](file:///e:/JakeAI/backend/tests/test_phase07_production_hardening.py#L1): Verify /health, /health/live, and /health/ready return 200 with components. (10 assertions)
  - [`test_correlation_id_and_response_time_middleware`](file:///e:/JakeAI/backend/tests/test_phase07_production_hardening.py#L1): Verify incoming correlation ID is propagated to response headers with execution timing. (4 assertions)
  - [`test_request_size_limit_middleware`](file:///e:/JakeAI/backend/tests/test_phase07_production_hardening.py#L1): Verify requests exceeding MAX_REQUEST_BODY_BYTES are rejected with HTTP 413. (2 assertions)
  - [`test_runtime_telemetry_metrics_endpoint`](file:///e:/JakeAI/backend/tests/test_phase07_production_hardening.py#L1): Verify /api/v1/analytics/metrics returns operational snapshot without sensitive data. (6 assertions)
  - [`test_chat_sse_stream_ordering_and_flush`](file:///e:/JakeAI/backend/tests/test_phase07_production_hardening.py#L1): Verify strict SSE event sequence: status -> token -> telemetry -> done. (9 assertions)
  - [`test_chat_sse_stream_cancellation_and_token_accounting`](file:///e:/JakeAI/backend/tests/test_phase07_production_hardening.py#L1): Verify that client cancellation finalizes partial token accounting and updates telemetry. (1 assertions)
  - [`test_chat_sse_stream_timeout`](file:///e:/JakeAI/backend/tests/test_phase07_production_hardening.py#L1): Verify that stream exceeding STREAM_TIMEOUT_SECONDS emits an error frame. (1 assertions)
  - [`test_gateway_chat_completions_streaming`](file:///e:/JakeAI/backend/tests/test_phase07_production_hardening.py#L1): Verify POST /v1/chat/completions with stream=True streams SSE chunks ending with [DONE]. (5 assertions)
  - [`test_gateway_chat_completions_streaming_exact_cache`](file:///e:/JakeAI/backend/tests/test_phase07_production_hardening.py#L1): Verify streaming response for cached prompt streams from cache with 0 billed tokens. (5 assertions)
  - [`test_redis_outage_resilient_cooldown_and_recovery`](file:///e:/JakeAI/backend/tests/test_phase07_production_hardening.py#L1): Verify SemanticCacheManager fails open on Redis outage and recovers after cooldown. (5 assertions)
  - [`test_qdrant_outage_in_memory_fallback`](file:///e:/JakeAI/backend/tests/test_phase07_production_hardening.py#L1): Verify QdrantVectorStore falls back to in-memory cosine search when Qdrant is down. (3 assertions)
  - [`test_quota_exhaustion_suspension`](file:///e:/JakeAI/backend/tests/test_phase07_production_hardening.py#L1): Verify QuotaManager blocks requests with suspended status when budget is exhausted. (3 assertions)
  - [`test_sanitize_error_message_redacts_credentials`](file:///e:/JakeAI/backend/tests/test_phase07_production_hardening.py#L1): Verify sanitize_error_message completely redacts API keys, Bearer tokens, and secrets. (4 assertions)
  - [`test_global_exception_handler_normalizes_provider_error`](file:///e:/JakeAI/backend/tests/test_phase07_production_hardening.py#L1): Verify ProviderError raised during request is normalized to safe JSON without secrets. (6 assertions)
  - [`test_chat_sse_stream_provider_error_mid_stream`](file:///e:/JakeAI/backend/tests/test_phase07_production_hardening.py#L1): Verify provider exception raised mid-stream emits sanitized error event and closes safely. (4 assertions)
  - [`test_global_exception_handler_provider_timeout_and_408`](file:///e:/JakeAI/backend/tests/test_phase07_production_hardening.py#L1): Verify ProviderTimeoutError maps to HTTP 408 Request Timeout. (4 assertions)
  - [`test_byok_invalid_ciphertext_tamper_defense`](file:///e:/JakeAI/backend/tests/test_phase07_production_hardening.py#L1): Verify tampered or invalid BYOK ciphertext fails safely without unhandled crashes. (0 assertions)
  - [`test_chat_sse_stream_slow_provider_bounded`](file:///e:/JakeAI/backend/tests/test_phase07_production_hardening.py#L1): Verify that slow provider stream emits events in order and updates metrics. (3 assertions)

#### `CAT-030`: [`test_prompt_compression_live.py`](file:///e:/JakeAI/backend/tests/test_prompt_compression_live.py)
- **Test File Path**: `backend/tests/test_prompt_compression_live.py` (232 lines)
- **Subsystem**: `RAG Pipeline`
- **Test Level**: `Unit`
- **Purpose**: Tests for COST-06 and COST-07: Prompt Compression on Live Paths & Duplicate Compressor Consolidation.
- **Dependencies / Fixtures**: Mocks / Monkeypatch
- **CI Job Execution**: `unit-and-ai-tests (Full Suite Floor)`
- **Recommended Run Frequency**: `PR / Push (main)`
- **Duplicate / Overlap Classification**: `COMPLEMENTARY`
- **RIGHT Test Suite Coverage**: `NONE`
- **Bruno Collection Coverage**: `NONE`
- **Architectural Disposition**: **`MOVE`** (Target Destination: `backend/tests/unit/`)
- **Disposition Rationale & Evidence**: Valuable subsystem test. Needs reclassification into unit/, integration/, or security/.
- **Discovered Test Functions (7)**:
  - [`test_context_selector_compress_document_chunks`](file:///e:/JakeAI/backend/tests/test_prompt_compression_live.py#L1): Verify ContextSelector.compress_document_chunks filters and packs candidate chunks. (8 assertions)
  - [`test_context_selector_compress_rag_context_string`](file:///e:/JakeAI/backend/tests/test_prompt_compression_live.py#L1): Verify ContextSelector.compress_rag_context_string prunes labeled distractors. (6 assertions)
  - [`test_retrieval_compressor_deprecation_and_delegation`](file:///e:/JakeAI/backend/tests/test_prompt_compression_live.py#L1): Verify RetrievalCompressor emits DeprecationWarning and delegates to ContextSelector. (5 assertions)
  - [`test_context_optimizer_quality_guardrails_empty_fallback`](file:///e:/JakeAI/backend/tests/test_prompt_compression_live.py#L1): Verify ContextOptimizer safely falls back to raw context if reduced to empty. (3 assertions)
  - [`test_context_optimizer_quality_guardrails_citation_loss`](file:///e:/JakeAI/backend/tests/test_prompt_compression_live.py#L1): Verify ContextOptimizer safely falls back to raw context if a citation is dropped. (3 assertions)
  - [`test_live_chat_stream_compression_accounting`](file:///e:/JakeAI/backend/tests/test_prompt_compression_live.py#L1): Verify live chat streaming path optimizes dynamic context and passes reduced tokens to TokenAccounting. (5 assertions)
  - [`test_jakeai_backend_compression_integration`](file:///e:/JakeAI/backend/tests/test_prompt_compression_live.py#L1): Verify JakeAIBackend optimizes combined prompt before invoking upstream LLM. (3 assertions)

#### `CAT-035`: [`test_r_ai_01_rag_grounding.py`](file:///e:/JakeAI/backend/tests/test_r_ai_01_rag_grounding.py)
- **Test File Path**: `backend/tests/test_r_ai_01_rag_grounding.py` (531 lines)
- **Subsystem**: `RAG Pipeline`
- **Test Level**: `Regression (RIGHT Verification)`
- **Purpose**: Comprehensive verification test suite for R-AI-01: RAG Grounding.
- **Dependencies / Fixtures**: Qdrant, HTTP / ASGI, Mocks / Monkeypatch
- **CI Job Execution**: `unit-and-ai-tests (Full Suite Floor)`
- **Recommended Run Frequency**: `PR / Push (main)`
- **Duplicate / Overlap Classification**: `COMPLEMENTARY`
- **RIGHT Test Suite Coverage**: `R-AI-01`
- **Bruno Collection Coverage**: `NONE`
- **Architectural Disposition**: **`MOVE`** (Target Destination: `backend/tests/unit/`)
- **Disposition Rationale & Evidence**: Authoritative RIGHT verification suite for R-AI-01. Move to dedicated integration/ or regression/ target folder.
- **Discovered Test Functions (12)**:
  - [`test_scenario_01_fully_supported_with_provenance_tracing`](file:///e:/JakeAI/backend/tests/test_r_ai_01_rag_grounding.py#L1): Verify supported claims map to evidence, trace claim -> passage -> source metadata, and generate valid citations. (17 assertions)
  - [`test_scenario_02_partially_supported_unsupported_claim_dropped`](file:///e:/JakeAI/backend/tests/test_r_ai_01_rag_grounding.py#L1): Verify that when an answer contains both supported and unsupported claims, the unsupported claim is dropped. (7 assertions)
  - [`test_scenario_03_metric_format_normalization`](file:///e:/JakeAI/backend/tests/test_r_ai_01_rag_grounding.py#L1): Verify metric normalization resolves $100M, $100 million, and $100,000,000 to identical canonical metrics. (8 assertions)
  - [`test_scenario_04_conflicting_numerical_evidence_surfaced`](file:///e:/JakeAI/backend/tests/test_r_ai_01_rag_grounding.py#L1): Verify conflicting numerical records are flagged UNCERTAIN, reasoning surfaces conflict, and citation confidence is adjusted. (8 assertions)
  - [`test_scenario_05_conflicting_qualitative_entities_surfaced`](file:///e:/JakeAI/backend/tests/test_r_ai_01_rag_grounding.py#L1): Verify that qualitative claims with conflicting entities across candidate chunks are flagged UNCERTAIN. (4 assertions)
  - [`test_scenario_06_direct_antonym_contradiction_rejected`](file:///e:/JakeAI/backend/tests/test_r_ai_01_rag_grounding.py#L1): Verify statements asserting antonyms (e.g. cancelled vs launched) are rejected with 0.0 confidence. (4 assertions)
  - [`test_scenario_07_citation_mismatch_prevention_on_partial_numbers`](file:///e:/JakeAI/backend/tests/test_r_ai_01_rag_grounding.py#L1): Verify a passage reporting $100,000,000 in 2026 is NEVER cited for a sentence asserting $999,000,000 in 2026. (2 assertions)
  - [`test_scenario_08_missing_evidence_explicit_abstention`](file:///e:/JakeAI/backend/tests/test_r_ai_01_rag_grounding.py#L1): Verify RAGPipeline returns status='ABSTAINED' and reason='NO_RELEVANT_EVIDENCE' when evidence is absent. (4 assertions)
  - [`test_scenario_09_irrelevant_chunks_suppressed`](file:///e:/JakeAI/backend/tests/test_r_ai_01_rag_grounding.py#L1): Verify irrelevant documents in index are neither echoed nor cited on unrelated queries. (4 assertions)
  - [`test_scenario_10_model_epistemic_abstention_preserved`](file:///e:/JakeAI/backend/tests/test_r_ai_01_rag_grounding.py#L1): Verify model's honest statement of evidence absence is recognized as abstention and not dropped. (3 assertions)
  - [`test_scenario_11_all_claims_contradicted_abstained`](file:///e:/JakeAI/backend/tests/test_r_ai_01_rag_grounding.py#L1): Verify that when generated text completely contradicts retrieved evidence, generation halts with abstention. (4 assertions)
  - [`test_scenario_12_public_http_api_boundary_grounding`](file:///e:/JakeAI/backend/tests/test_r_ai_01_rag_grounding.py#L1): Verify public HTTP endpoint /api/v1/rag/generate executes full 10-step RAG and returns grounding provenance. (13 assertions)

#### `CAT-036`: [`test_r_ai_02_hallucination_resistance.py`](file:///e:/JakeAI/backend/tests/test_r_ai_02_hallucination_resistance.py)
- **Test File Path**: `backend/tests/test_r_ai_02_hallucination_resistance.py` (662 lines)
- **Subsystem**: `RAG Pipeline`
- **Test Level**: `Regression (RIGHT Verification)`
- **Purpose**: Comprehensive verification test suite for R-AI-02: Hallucination Resistance.
- **Dependencies / Fixtures**: Qdrant, HTTP / ASGI, Mocks / Monkeypatch
- **CI Job Execution**: `unit-and-ai-tests (Full Suite Floor)`
- **Recommended Run Frequency**: `PR / Push (main)`
- **Duplicate / Overlap Classification**: `COMPLEMENTARY`
- **RIGHT Test Suite Coverage**: `R-AI-02`
- **Bruno Collection Coverage**: `NONE`
- **Architectural Disposition**: **`MOVE`** (Target Destination: `backend/tests/unit/`)
- **Disposition Rationale & Evidence**: Authoritative RIGHT verification suite for R-AI-02. Move to dedicated integration/ or regression/ target folder.
- **Discovered Test Functions (13)**:
  - [`test_scenario_01_unknown_entity_impossible_facts`](file:///e:/JakeAI/backend/tests/test_r_ai_02_hallucination_resistance.py#L1): Verify that hallucinated claims about an unknown entity are caught, measured, and rejected. (8 assertions)
  - [`test_scenario_02_missing_documents_empty_index`](file:///e:/JakeAI/backend/tests/test_r_ai_02_hallucination_resistance.py#L1): Verify that queries against an empty index cleanly abstain with NO_RELEVANT_EVIDENCE without calling LLM. (4 assertions)
  - [`test_scenario_03_four_way_failure_distinction`](file:///e:/JakeAI/backend/tests/test_r_ai_02_hallucination_resistance.py#L1): Verify explicit distinction among NO_RELEVANT_EVIDENCE, RETRIEVAL_FAILURE, PROVIDER_FAILURE, and GENERATION_FAILURE. (8 assertions)
  - [`test_scenario_04_ambiguous_requests_and_evidence_qualification`](file:///e:/JakeAI/backend/tests/test_r_ai_02_hallucination_resistance.py#L1): Verify that conflicting evidence on ambiguous names yields UNCERTAIN qualification with [unverified] and 0.50 confidence. (9 assertions)
  - [`test_scenario_05_conflicting_context_and_antonym_contradictions`](file:///e:/JakeAI/backend/tests/test_r_ai_02_hallucination_resistance.py#L1): Verify that statements asserting facts contradicting retrieved evidence are flagged with CONTRADICTORY_EVIDENCE. (5 assertions)
  - [`test_scenario_06_prompt_instructions_contradicting_evidence`](file:///e:/JakeAI/backend/tests/test_r_ai_02_hallucination_resistance.py#L1): Verify system resists user prompt instructions that contradict indexed evidence figures. (3 assertions)
  - [`test_scenario_07_compound_multi_metric_claim_ensemble_support`](file:///e:/JakeAI/backend/tests/test_r_ai_02_hallucination_resistance.py#L1): Verify multi-metric claims spanning multiple chunks are verified as SUPPORTED without false contradiction. (6 assertions)
  - [`test_scenario_08_document_embedded_prompt_injection_defense`](file:///e:/JakeAI/backend/tests/test_r_ai_02_hallucination_resistance.py#L1): Verify that prompt injection directives in document chunks are rejected and prohibited from factual grounding. (7 assertions)
  - [`test_scenario_09_pre_output_leakage_safeguards`](file:///e:/JakeAI/backend/tests/test_r_ai_02_hallucination_resistance.py#L1): Verify that system prompt leaks or credentials in generated output are scrubbed before reaching the user. (3 assertions)
  - [`test_scenario_10_adversarial_prompt_injection_http_boundary`](file:///e:/JakeAI/backend/tests/test_r_ai_02_hallucination_resistance.py#L1): Verify POST /api/v1/rag/generate intercepts adversarial prompt injections with GUARDRAIL_VIOLATION. (5 assertions)
  - [`test_scenario_11_public_http_api_grounding_and_unsupported_rate`](file:///e:/JakeAI/backend/tests/test_r_ai_02_hallucination_resistance.py#L1): Verify POST /api/v1/rag/generate returns grounded answer with grounding metrics including unsupported_claim_rate. (8 assertions)
  - [`test_scenario_12_canonical_verifier_data_leakage_and_hallucination_gates`](file:///e:/JakeAI/backend/tests/test_r_ai_02_hallucination_resistance.py#L1): Verify CanonicalVerifier rejects execution on data leakage or ungrounded numerical claims. (6 assertions)
  - [`test_scenario_13_misleading_retrieved_content_zero_relevance`](file:///e:/JakeAI/backend/tests/test_r_ai_02_hallucination_resistance.py#L1): Verify that when retrieved chunks have zero relevance to the query, hallucination is suppressed and pipeline abstains. (3 assertions)

#### `CAT-038`: [`test_r_ai_04_context_correctness.py`](file:///e:/JakeAI/backend/tests/test_r_ai_04_context_correctness.py)
- **Test File Path**: `backend/tests/test_r_ai_04_context_correctness.py` (878 lines)
- **Subsystem**: `RAG Pipeline`
- **Test Level**: `Regression (RIGHT Verification)`
- **Purpose**: Comprehensive verification test suite for R-AI-04: Context Correctness.
- **Dependencies / Fixtures**: HTTP / ASGI, Mocks / Monkeypatch
- **CI Job Execution**: `unit-and-ai-tests (Full Suite Floor)`
- **Recommended Run Frequency**: `PR / Push (main)`
- **Duplicate / Overlap Classification**: `COMPLEMENTARY`
- **RIGHT Test Suite Coverage**: `R-AI-04`
- **Bruno Collection Coverage**: `NONE`
- **Architectural Disposition**: **`MOVE`** (Target Destination: `backend/tests/unit/`)
- **Disposition Rationale & Evidence**: Authoritative RIGHT verification suite for R-AI-04. Move to dedicated integration/ or regression/ target folder.
- **Discovered Test Functions (19)**:
  - [`test_scenario_01_canonical_6_stage_ordering`](file:///e:/JakeAI/backend/tests/test_r_ai_04_context_correctness.py#L1): Verify ContextEnvelopeBuilder assembles stages in strict 6-stage canonical order. (3 assertions)
  - [`test_scenario_02_provenance_labels_and_section_demarcation`](file:///e:/JakeAI/backend/tests/test_r_ai_04_context_correctness.py#L1): Verify distinct section labels, source attribution formatting, and fact markers. (6 assertions)
  - [`test_scenario_03_trust_classification_unverified_memory_quarantine`](file:///e:/JakeAI/backend/tests/test_r_ai_04_context_correctness.py#L1): Verify unverified memories are excluded from verified memory and never treated as verified evidence. (8 assertions)
  - [`test_scenario_04_multi_tenant_boundary_and_contamination_defense`](file:///e:/JakeAI/backend/tests/test_r_ai_04_context_correctness.py#L1): Verify evidence chunks, memories, and messages from foreign tenants are quarantined and rejected. (7 assertions)
  - [`test_scenario_05_task_constraints_deduplication`](file:///e:/JakeAI/backend/tests/test_r_ai_04_context_correctness.py#L1): Verify duplicate task constraints are deduplicated while preserving order. (4 assertions)
  - [`test_scenario_06_verified_memory_deduplication`](file:///e:/JakeAI/backend/tests/test_r_ai_04_context_correctness.py#L1): Verify duplicate verified memory facts are deduplicated preserving order. (3 assertions)
  - [`test_scenario_07_conversation_history_deduplication`](file:///e:/JakeAI/backend/tests/test_r_ai_04_context_correctness.py#L1): Verify consecutive duplicate turns in dialogue history are collapsed. (3 assertions)
  - [`test_scenario_08_conflicting_memory_superseded_by_latest`](file:///e:/JakeAI/backend/tests/test_r_ai_04_context_correctness.py#L1): Verify when contradictory memories exist for the same key, the newer verified fact supersedes. (2 assertions)
  - [`test_scenario_09_expired_and_irrelevant_memory_filtering`](file:///e:/JakeAI/backend/tests/test_r_ai_04_context_correctness.py#L1): Verify expired TTL memory entries and irrelevant memory facts are excluded. (3 assertions)
  - [`test_scenario_10_no_silent_constraint_loss_during_shedding`](file:///e:/JakeAI/backend/tests/test_r_ai_04_context_correctness.py#L1): Verify task constraints and user query are NEVER shed or truncated during load shedding. (6 assertions)
  - [`test_scenario_11_budget_overflow_shedding_order`](file:///e:/JakeAI/backend/tests/test_r_ai_04_context_correctness.py#L1): Verify graceful load shedding sheds unverified -> history oldest -> memory oldest -> evidence last. (4 assertions)
  - [`test_scenario_12_strict_budget_limit_enforcement_raises_error`](file:///e:/JakeAI/backend/tests/test_r_ai_04_context_correctness.py#L1): Verify ContextBudgetExceededError is raised when essential core context exceeds budget. (2 assertions)
  - [`test_scenario_13_sensitive_and_internal_scores_sanitization`](file:///e:/JakeAI/backend/tests/test_r_ai_04_context_correctness.py#L1): Verify internal retrieval scores are sanitized by default and preserved only when requested. (8 assertions)
  - [`test_scenario_14_verifiable_citations_preserved_during_sanitization`](file:///e:/JakeAI/backend/tests/test_r_ai_04_context_correctness.py#L1): Verify citation anchors are preserved and cataloged when internal scores are stripped. (5 assertions)
  - [`test_scenario_15_exact_serialized_token_accounting`](file:///e:/JakeAI/backend/tests/test_r_ai_04_context_correctness.py#L1): Verify envelope.total_tokens precisely matches BPETokenizer count on serialized_prompt. (2 assertions)
  - [`test_scenario_16_token_accounting_ledger_alignment`](file:///e:/JakeAI/backend/tests/test_r_ai_04_context_correctness.py#L1): Verify TokenAccounting.calculate_envelope_tokens aligns 1:1 with ContextEnvelope. (1 assertions)
  - [`test_scenario_17_domain_models_structured_inputs`](file:///e:/JakeAI/backend/tests/test_r_ai_04_context_correctness.py#L1): Verify ContextEnvelopeBuilder accepts DocumentChunk and MemoryEntry objects cleanly. (3 assertions)
  - [`test_scenario_18_rag_pipeline_end_to_end_context_envelope`](file:///e:/JakeAI/backend/tests/test_r_ai_04_context_correctness.py#L1): Verify RAGPipeline.generate_grounded_answer uses ContextEnvelopeBuilder and attaches envelope. (13 assertions)
  - [`test_scenario_19_public_http_rag_generate_endpoint_context_correctness`](file:///e:/JakeAI/backend/tests/test_r_ai_04_context_correctness.py#L1): Verify /api/v1/rag/generate returns envelope_tokens and zero leaked scores over real HTTP boundary. (12 assertions)

#### `CAT-046`: [`test_r_func_02_rag_behavior.py`](file:///e:/JakeAI/backend/tests/test_r_func_02_rag_behavior.py)
- **Test File Path**: `backend/tests/test_r_func_02_rag_behavior.py` (779 lines)
- **Subsystem**: `RAG Pipeline`
- **Test Level**: `Regression (RIGHT Verification)`
- **Purpose**: Comprehensive verification test suite for R-FUNC-02: RAG Behavior.
- **Dependencies / Fixtures**: Qdrant, HTTP / ASGI, Mocks / Monkeypatch
- **CI Job Execution**: `unit-and-ai-tests (Full Suite Floor)`
- **Recommended Run Frequency**: `PR / Push (main)`
- **Duplicate / Overlap Classification**: `COMPLEMENTARY`
- **RIGHT Test Suite Coverage**: `R-FUNC-02`
- **Bruno Collection Coverage**: `Bruno/04 — RAG (01-07)`
- **Architectural Disposition**: **`MOVE`** (Target Destination: `backend/tests/unit/`)
- **Disposition Rationale & Evidence**: Authoritative RIGHT verification suite for R-FUNC-02. Move to dedicated integration/ or regression/ target folder.
- **Discovered Test Functions (14)**:
  - [`test_scenario_01_txt_document_full_path`](file:///e:/JakeAI/backend/tests/test_r_func_02_rag_behavior.py#L1): Verify TXT document passes MIME detection, NFKC normalization, control char stripping, chunking, and retrieval. (10 assertions)
  - [`test_scenario_02_markdown_document_full_path`](file:///e:/JakeAI/backend/tests/test_r_func_02_rag_behavior.py#L1): Verify Markdown parsing extracts section headings, protects fenced code blocks, and preserves indentation. (6 assertions)
  - [`test_scenario_03_pdf_document_full_path`](file:///e:/JakeAI/backend/tests/test_r_func_02_rag_behavior.py#L1): Verify real multi-page PDF generation, binary extraction with page metadata, and base64 parsing. (9 assertions)
  - [`test_scenario_04_empty_malformed_unsupported_documents`](file:///e:/JakeAI/backend/tests/test_r_func_02_rag_behavior.py#L1): Verify empty input returns 0 chunks, corrupted PDF raises ValueError, and unsupported types raise UnsupportedDocumentTypeError. (2 assertions)
  - [`test_scenario_05_repeated_indexing_and_version_update`](file:///e:/JakeAI/backend/tests/test_r_func_02_rag_behavior.py#L1): Verify re-indexing identical content is idempotent (no duplicate points/counts) and version updates are tracked. (9 assertions)
  - [`test_scenario_06_relevant_query_and_claim_grounding`](file:///e:/JakeAI/backend/tests/test_r_func_02_rag_behavior.py#L1): Verify relevant query retrieves top candidates, selects context, generates grounded answer, and produces citations. (8 assertions)
  - [`test_scenario_07_irrelevant_query_explicit_abstention`](file:///e:/JakeAI/backend/tests/test_r_func_02_rag_behavior.py#L1): Verify query with zero relevance to indexed documents explicitly abstains with NO_RELEVANT_EVIDENCE. (4 assertions)
  - [`test_scenario_08_missing_evidence_explicit_abstention`](file:///e:/JakeAI/backend/tests/test_r_func_02_rag_behavior.py#L1): Verify querying an empty tenant workspace with zero documents explicitly returns ABSTAINED with NO_RELEVANT_EVIDENCE. (4 assertions)
  - [`test_scenario_09_conflicting_evidence_resolution`](file:///e:/JakeAI/backend/tests/test_r_func_02_rag_behavior.py#L1): Verify GroundingVerifier detects conflicting metrics across retrieved records and flags UNCERTAIN instead of SUPPORTED. (3 assertions)
  - [`test_scenario_10_citation_mismatch_and_hallucination_stripping`](file:///e:/JakeAI/backend/tests/test_r_func_02_rag_behavior.py#L1): Verify metric coincidence without topic overlap is rejected (score 0.0), and hallucinated footnote markers are stripped. (7 assertions)
  - [`test_scenario_11_tenant_isolation_defense_in_depth`](file:///e:/JakeAI/backend/tests/test_r_func_02_rag_behavior.py#L1): Verify tenant data is strictly quarantined across vector store, BM25, hybrid search, context selector, citations, and pipeline. (9 assertions)
  - [`test_scenario_12_restart_persistence`](file:///e:/JakeAI/backend/tests/test_r_func_02_rag_behavior.py#L1): Verify BM25 sparse index persists to disk and reloads identically across process restart. (8 assertions)
  - [`test_scenario_13_provider_failure_graceful_abstention`](file:///e:/JakeAI/backend/tests/test_r_func_02_rag_behavior.py#L1): Verify upstream model provider exceptions are caught and explicitly return status=ABSTAINED and PROVIDER_FAILURE. (4 assertions)
  - [`test_scenario_14_http_api_endpoints_complete_boundary`](file:///e:/JakeAI/backend/tests/test_r_func_02_rag_behavior.py#L1): Verify HTTP endpoints /api/v1/rag/ingest, /tasks, /query, and /generate via real ASGI HTTP transport. (24 assertions)

#### `CAT-047`: [`test_r_func_03_cache_behavior.py`](file:///e:/JakeAI/backend/tests/test_r_func_03_cache_behavior.py)
- **Test File Path**: `backend/tests/test_r_func_03_cache_behavior.py` (1408 lines)
- **Subsystem**: `RAG Pipeline`
- **Test Level**: `Regression (RIGHT Verification)`
- **Purpose**: Comprehensive verification test suite for R-FUNC-03: Cache Behavior.
- **Dependencies / Fixtures**: Redis, Qdrant, HTTP / ASGI, Mocks / Monkeypatch
- **CI Job Execution**: `unit-and-ai-tests (Full Suite Floor)`
- **Recommended Run Frequency**: `PR / Push (main)`
- **Duplicate / Overlap Classification**: `COMPLEMENTARY`
- **RIGHT Test Suite Coverage**: `R-FUNC-03`
- **Bruno Collection Coverage**: `Bruno/06 — Cache (01-06)`
- **Architectural Disposition**: **`MOVE`** (Target Destination: `backend/tests/unit/`)
- **Disposition Rationale & Evidence**: Authoritative RIGHT verification suite for R-FUNC-03. Move to dedicated integration/ or regression/ target folder.
- **Discovered Test Functions (25)**:
  - [`test_scenario_01_exact_cache_miss_set_hit_lifecycle`](file:///e:/JakeAI/backend/tests/test_r_func_03_cache_behavior.py#L1): First request misses, second identical request hits the exact tier. (8 assertions)
  - [`test_scenario_02_exact_identity_dimension_isolation`](file:///e:/JakeAI/backend/tests/test_r_func_03_cache_behavior.py#L1): Changing any single generation-relevant dimension must miss. (3 assertions)
  - [`test_scenario_03_exact_cache_ttl_expiry`](file:///e:/JakeAI/backend/tests/test_r_func_03_cache_behavior.py#L1): Expired entries must not be served by the exact tier. (2 assertions)
  - [`test_scenario_04_legacy_entries_must_not_hit`](file:///e:/JakeAI/backend/tests/test_r_func_03_cache_behavior.py#L1): Legacy schema-version entries and legacy hash keys must never be served. (5 assertions)
  - [`test_scenario_05_concurrent_set_get_no_cross_contamination`](file:///e:/JakeAI/backend/tests/test_r_func_03_cache_behavior.py#L1): Parallel set/get streams must not cross-contaminate or crash. (2 assertions)
  - [`test_scenario_06_metrics_accounting`](file:///e:/JakeAI/backend/tests/test_r_func_03_cache_behavior.py#L1): Hit/miss accounting must track exact hits, semantic hits and misses. (12 assertions)
  - [`test_scenario_07_semantic_real_embeddings_near_duplicate_vs_unrelated`](file:///e:/JakeAI/backend/tests/test_r_func_03_cache_behavior.py#L1): Real dense embeddings: near duplicate hits, unrelated query misses. (4 assertions)
  - [`test_scenario_08_semantic_tenant_isolation`](file:///e:/JakeAI/backend/tests/test_r_func_03_cache_behavior.py#L1): Semantic tier must never serve entries across tenants. (3 assertions)
  - [`test_scenario_09_semantic_generation_compatibility_guardrails`](file:///e:/JakeAI/backend/tests/test_r_func_03_cache_behavior.py#L1): Semantic hits must be rejected when generation-relevant dims differ. (1 assertions)
  - [`test_scenario_10_semantic_generation_params_guardrail`](file:///e:/JakeAI/backend/tests/test_r_func_03_cache_behavior.py#L1): Different generation parameters must block semantic reuse (R-FUNC-03 fix). (3 assertions)
  - [`test_scenario_11_semantic_strict_model_provider_matching`](file:///e:/JakeAI/backend/tests/test_r_func_03_cache_behavior.py#L1): No wildcard model/provider matching in the semantic tier (R-FUNC-03 fix). (4 assertions)
  - [`test_scenario_12_semantic_similarity_threshold_boundary`](file:///e:/JakeAI/backend/tests/test_r_func_03_cache_behavior.py#L1): Threshold is enforced: above hits, above-threshold-but-configured-higher misses. (4 assertions)
  - [`test_scenario_13_exact_only_bypasses_semantic_tier`](file:///e:/JakeAI/backend/tests/test_r_func_03_cache_behavior.py#L1): exact_only lookups must never return semantic candidates. (3 assertions)
  - [`test_scenario_14_semantic_never_replaces_exact_tier`](file:///e:/JakeAI/backend/tests/test_r_func_03_cache_behavior.py#L1): An identical request must be served by the exact tier, not the semantic tier. (5 assertions)
  - [`test_scenario_15_qdrant_roundtrip_serves_after_restart_simulation`](file:///e:/JakeAI/backend/tests/test_r_func_03_cache_behavior.py#L1): Real Qdrant client roundtrip: semantic hit must survive memory loss. (5 assertions)
  - [`test_scenario_16_qdrant_expired_entry_not_served`](file:///e:/JakeAI/backend/tests/test_r_func_03_cache_behavior.py#L1): Qdrant-backed semantic hits must respect TTL expiry. (1 assertions)
  - [`test_scenario_17_qdrant_tenant_filter_defense_in_depth`](file:///e:/JakeAI/backend/tests/test_r_func_03_cache_behavior.py#L1): Qdrant candidate payloads from another tenant must be rejected. (1 assertions)
  - [`test_scenario_18_stream_endpoint_miss_then_exact_hit`](file:///e:/JakeAI/backend/tests/test_r_func_03_cache_behavior.py#L1): HTTP: identical replay must hit the cache; first request must miss. (11 assertions)
  - [`test_scenario_19_stream_endpoint_cross_tenant_isolation`](file:///e:/JakeAI/backend/tests/test_r_func_03_cache_behavior.py#L1): HTTP: the same prompt from another tenant must not hit the cache. (4 assertions)
  - [`test_scenario_20_stream_endpoint_identity_dimension_isolation`](file:///e:/JakeAI/backend/tests/test_r_func_03_cache_behavior.py#L1): HTTP: changing one generation-relevant parameter must not hit the exact tier. (6 assertions)
  - [`test_scenario_21_gateway_http_exact_hit_and_identity_isolation`](file:///e:/JakeAI/backend/tests/test_r_func_03_cache_behavior.py#L1): HTTP gateway: identical replay hits; changed dims must not hit. (10 assertions)
  - [`test_scenario_22_gateway_http_no_false_hit_on_tool_call_structure`](file:///e:/JakeAI/backend/tests/test_r_func_03_cache_behavior.py#L1): HTTP gateway regression: tool-call message structure must be part of identity. (5 assertions)
  - [`test_scenario_23_exact_entry_persists_across_manager_instances_via_redis`](file:///e:/JakeAI/backend/tests/test_r_func_03_cache_behavior.py#L1): Real Redis roundtrip: an entry set by one manager is hit by another. (4 assertions)
  - [`test_scenario_24_redis_ttl_expiry_is_honored`](file:///e:/JakeAI/backend/tests/test_r_func_03_cache_behavior.py#L1): Real Redis TTL: expired exact entries must not be served cross-instance. (2 assertions)
  - [`test_scenario_25_get_and_set_use_one_identity_function`](file:///e:/JakeAI/backend/tests/test_r_func_03_cache_behavior.py#L1): SET and GET must derive the same key for equivalent request shapes. (3 assertions)

#### `CAT-049`: [`test_r_logic_00_invariants.py`](file:///e:/JakeAI/backend/tests/test_r_logic_00_invariants.py)
- **Test File Path**: `backend/tests/test_r_logic_00_invariants.py` (1563 lines)
- **Subsystem**: `RAG Pipeline`
- **Test Level**: `Regression (RIGHT Verification)`
- **Purpose**: R-LOGIC-00 — Invariants Verification Test Suite.
- **Dependencies / Fixtures**: Redis, Qdrant, HTTP / ASGI, Mocks / Monkeypatch
- **CI Job Execution**: `unit-and-ai-tests (Full Suite Floor)`
- **Recommended Run Frequency**: `PR / Push (main)`
- **Duplicate / Overlap Classification**: `COMPLEMENTARY`
- **RIGHT Test Suite Coverage**: `R-LOGIC-00`
- **Bruno Collection Coverage**: `NONE`
- **Architectural Disposition**: **`MOVE`** (Target Destination: `backend/tests/unit/`)
- **Disposition Rationale & Evidence**: Authoritative RIGHT verification suite for R-LOGIC-00. Move to dedicated integration/ or regression/ target folder.
- **Discovered Test Functions (30)**:
  - [`test_inv_a1_cancel_of_terminal_run_preserves_terminal_state`](file:///e:/JakeAI/backend/tests/test_r_logic_00_invariants.py#L1): Cancelling a run that already reached a terminal state must be a no-op. (2 assertions)
  - [`test_inv_a2_resume_of_completed_run_must_not_reexecute`](file:///e:/JakeAI/backend/tests/test_r_logic_00_invariants.py#L1): Resuming a COMPLETED run must not re-execute steps or re-complete it. (3 assertions)
  - [`test_inv_a3_resume_of_cancelled_run_must_not_complete`](file:///e:/JakeAI/backend/tests/test_r_logic_00_invariants.py#L1): A CANCELLED run with an unfinished plan must never resume into COMPLETED. (2 assertions)
  - [`test_inv_a4_incomplete_plan_never_completes_without_verification`](file:///e:/JakeAI/backend/tests/test_r_logic_00_invariants.py#L1): A run whose plan did not finish (stuck step) must not be COMPLETED. (2 assertions)
  - [`test_inv_a5_execute_run_refuses_terminal_run`](file:///e:/JakeAI/backend/tests/test_r_logic_00_invariants.py#L1): manager.execute_run on a terminal run must not reset it to RUNNING. (2 assertions)
  - [`test_inv_a6_cancel_of_active_run_still_cancels`](file:///e:/JakeAI/backend/tests/test_r_logic_00_invariants.py#L1): Pin accepted behavior: cancelling a genuinely active run works. (2 assertions)
  - [`test_inv_b10_rejection_on_paused_run_terminates_rejected`](file:///e:/JakeAI/backend/tests/test_r_logic_00_invariants.py#L1): Rejecting a gate on a genuinely paused run terminates it REJECTED. (3 assertions)
  - [`test_inv_b1_approving_one_tool_does_not_unlock_sibling_tool`](file:///e:/JakeAI/backend/tests/test_r_logic_00_invariants.py#L1): Each dangerous tool call requires its own approved approval record. (6 assertions)
  - [`test_inv_b2_resume_without_approval_stays_waiting`](file:///e:/JakeAI/backend/tests/test_r_logic_00_invariants.py#L1): Resuming a paused run with no approved approval must not execute tools. (3 assertions)
  - [`test_inv_b3_rejection_via_resume_marks_rejected`](file:///e:/JakeAI/backend/tests/test_r_logic_00_invariants.py#L1): Explicit rejection through resume terminates the run as REJECTED. (3 assertions)
  - [`test_inv_b4_cross_run_approval_rejected_in_resume`](file:///e:/JakeAI/backend/tests/test_r_logic_00_invariants.py#L1): An approval bound to run A must not authorize resuming run B. (1 assertions)
  - [`test_inv_b5_late_approval_decision_preserves_terminal_run`](file:///e:/JakeAI/backend/tests/test_r_logic_00_invariants.py#L1): A late rejection on an already-terminal run must not resurrect it. (1 assertions)
  - [`test_inv_b6_restart_resume_with_lost_approval_records_unlocks_explicitly`](file:///e:/JakeAI/backend/tests/test_r_logic_00_invariants.py#L1): Restart recovery: an isolated ApprovalManager (records lost) can still (5 assertions)
  - [`test_inv_b7_repausing_step_reuses_pending_gate_without_duplicates`](file:///e:/JakeAI/backend/tests/test_r_logic_00_invariants.py#L1): A step re-entering execution with an undecided bound gate must keep (3 assertions)
  - [`test_inv_b8_rejected_gate_fails_step_closed`](file:///e:/JakeAI/backend/tests/test_r_logic_00_invariants.py#L1): A step whose bound approval was rejected must fail closed, never execute. (2 assertions)
  - [`test_inv_b9_legacy_checkpoint_unlocked_only_by_explicit_approval`](file:///e:/JakeAI/backend/tests/test_r_logic_00_invariants.py#L1): Legacy checkpoint (no step-gate binding) with an explicit approved=True (4 assertions)
  - [`test_inv_c1_gateway_miss_settles_quota_exactly_once`](file:///e:/JakeAI/backend/tests/test_r_logic_00_invariants.py#L1): One gateway inference must settle quota once, not twice. (4 assertions)
  - [`test_inv_c2_gateway_cache_hit_settles_zero_quota`](file:///e:/JakeAI/backend/tests/test_r_logic_00_invariants.py#L1): A Tier 1 exact cache hit must not consume quota. (3 assertions)
  - [`test_inv_c3_quota_never_negative_and_hard_stops_at_limit`](file:///e:/JakeAI/backend/tests/test_r_logic_00_invariants.py#L1): Boundary + concurrency: quota counters never lose updates, never go (7 assertions)
  - [`test_inv_d1_semantic_hit_requires_same_conversation_history`](file:///e:/JakeAI/backend/tests/test_r_logic_00_invariants.py#L1): Tier 2 must not serve an entry cached under a different history. (2 assertions)
  - [`test_inv_d2_exact_cache_identity_boundaries`](file:///e:/JakeAI/backend/tests/test_r_logic_00_invariants.py#L1): Exact tier must isolate on tenant, model and message history. (3 assertions)
  - [`test_inv_d3_concurrent_cache_writes_stay_tenant_isolated`](file:///e:/JakeAI/backend/tests/test_r_logic_00_invariants.py#L1): Concurrent set/get across tenants must never cross-contaminate. (2 assertions)
  - [`test_inv_e1_cross_tenant_agent_run_access_forbidden`](file:///e:/JakeAI/backend/tests/test_r_logic_00_invariants.py#L1): HTTP boundary: tenant B cannot read or cancel tenant A's runs. (4 assertions)
  - [`test_inv_e2_byok_credentials_are_tenant_isolated`](file:///e:/JakeAI/backend/tests/test_r_logic_00_invariants.py#L1): Provider credential isolation: tenant B can never resolve tenant A's key. (2 assertions)
  - [`test_inv_e3_rag_answers_never_leak_foreign_tenant_evidence`](file:///e:/JakeAI/backend/tests/test_r_logic_00_invariants.py#L1): RAG pipeline: tenant B's query must not receive tenant A's evidence. (4 assertions)
  - [`test_inv_f1_uncertain_claims_are_explicitly_caveated`](file:///e:/JakeAI/backend/tests/test_r_logic_00_invariants.py#L1): Claims that could not be verified must be visibly marked in the answer. (4 assertions)
  - [`test_inv_f2_unsupported_claims_never_survive_grounding`](file:///e:/JakeAI/backend/tests/test_r_logic_00_invariants.py#L1): Fabricated claims are dropped; an all-fabricated answer yields nothing. (3 assertions)
  - [`test_inv_g1_permission_gated_tools_fail_closed`](file:///e:/JakeAI/backend/tests/test_r_logic_00_invariants.py#L1): ToolRegistry denies tools whose permissions the context lacks. (4 assertions)
  - [`test_inv_g2_path_traversal_arguments_denied`](file:///e:/JakeAI/backend/tests/test_r_logic_00_invariants.py#L1): Argument-level attack patterns are denied by the policy engine. (1 assertions)
  - [`test_inv_h1_ledger_records_actually_served_model`](file:///e:/JakeAI/backend/tests/test_r_logic_00_invariants.py#L1): FinOps ledger must record the model that actually served the request. (3 assertions)

#### `CAT-053`: [`test_r_logic_04_failure_handling.py`](file:///e:/JakeAI/backend/tests/test_r_logic_04_failure_handling.py)
- **Test File Path**: `backend/tests/test_r_logic_04_failure_handling.py` (1091 lines)
- **Subsystem**: `RAG Pipeline`
- **Test Level**: `Regression (RIGHT Verification)`
- **Purpose**: R-LOGIC-04 — Failure Handling canonical verification test suite.
- **Dependencies / Fixtures**: Redis, Mocks / Monkeypatch
- **CI Job Execution**: `unit-and-ai-tests (Full Suite Floor)`
- **Recommended Run Frequency**: `PR / Push (main)`
- **Duplicate / Overlap Classification**: `COMPLEMENTARY`
- **RIGHT Test Suite Coverage**: `R-LOGIC-04`
- **Bruno Collection Coverage**: `NONE`
- **Architectural Disposition**: **`MOVE`** (Target Destination: `backend/tests/unit/`)
- **Disposition Rationale & Evidence**: Authoritative RIGHT verification suite for R-LOGIC-04. Move to dedicated integration/ or regression/ target folder.
- **Discovered Test Functions (27)**:
  - [`test_status_matrix_retry_vs_failover_at_failover_boundary`](file:///e:/JakeAI/backend/tests/test_r_logic_04_failure_handling.py#L1): 401/403/quota-429 never retry; 429/503/timeout retry on the same provider. (2 assertions)
  - [`test_quota_429_is_not_retried_like_rate_limit`](file:///e:/JakeAI/backend/tests/test_r_logic_04_failure_handling.py#L1): A 429 carrying a quota/billing message maps to non-retryable quota. (3 assertions)
  - [`test_backoff_is_bounded_exponential_with_jitter`](file:///e:/JakeAI/backend/tests/test_r_logic_04_failure_handling.py#L1): Backoff grows exponentially, includes jitter, and never exceeds the cap. (3 assertions)
  - [`test_retry_after_respected_and_capped`](file:///e:/JakeAI/backend/tests/test_r_logic_04_failure_handling.py#L1): Direct assertion (2 assertions)
  - [`test_total_attempt_ceiling_prevents_retry_storm`](file:///e:/JakeAI/backend/tests/test_r_logic_04_failure_handling.py#L1): With many fallback candidates, total attempts never exceed the ceiling. (1 assertions)
  - [`test_provider_outage_fails_run_without_fabricated_success`](file:///e:/JakeAI/backend/tests/test_r_logic_04_failure_handling.py#L1): RL04-F-01: outage through the REAL JakeAIBackend fails the run terminally. (5 assertions)
  - [`test_backend_error_finish_reason_fails_step_not_fabricates`](file:///e:/JakeAI/backend/tests/test_r_logic_04_failure_handling.py#L1): A backend response with an error finish_reason fails the step. (2 assertions)
  - [`test_non_retryable_step_failure_terminates_without_retry`](file:///e:/JakeAI/backend/tests/test_r_logic_04_failure_handling.py#L1): RL04-F-02: an auth failure is terminal — no retry/model-switch events. (3 assertions)
  - [`test_transient_failure_retries_within_bounded_budget`](file:///e:/JakeAI/backend/tests/test_r_logic_04_failure_handling.py#L1): Transient 503s retry with backoff, bounded by MAX_STEP_RETRIES=3. (2 assertions)
  - [`test_run_timeout_is_terminal_and_never_resumable`](file:///e:/JakeAI/backend/tests/test_r_logic_04_failure_handling.py#L1): Run-level timeout yields terminal TIMEOUT status; resume is refused. (5 assertions)
  - [`test_recovery_classification_matrix`](file:///e:/JakeAI/backend/tests/test_r_logic_04_failure_handling.py#L1): Direct assertion (1 assertions)
  - [`test_recovery_first_attempt_timeout_does_not_crash`](file:///e:/JakeAI/backend/tests/test_r_logic_04_failure_handling.py#L1): RL04-F-07: first-attempt timeout (retries=0) returns a terminal decision. (1 assertions)
  - [`test_recovery_first_attempt_non_retryable_does_not_crash`](file:///e:/JakeAI/backend/tests/test_r_logic_04_failure_handling.py#L1): Direct assertion (1 assertions)
  - [`test_recovery_verification_rejection_never_replans`](file:///e:/JakeAI/backend/tests/test_r_logic_04_failure_handling.py#L1): REJECTED verdict terminates rejected — security failures never loop. (1 assertions)
  - [`test_gateway_outage_fallback_not_cached_and_breaker_counts`](file:///e:/JakeAI/backend/tests/test_r_logic_04_failure_handling.py#L1): RL04-F-03/F-04: fallback served on outage, not cached; breaker records. (4 assertions)
  - [`test_gateway_breaker_opens_after_consecutive_outages`](file:///e:/JakeAI/backend/tests/test_r_logic_04_failure_handling.py#L1): Three consecutive total outages trip the breaker; calls fast-fall back. (4 assertions)
  - [`test_gateway_stream_outage_fallback_not_cached`](file:///e:/JakeAI/backend/tests/test_r_logic_04_failure_handling.py#L1): Stream path: outage fallback is streamed but never cached. (4 assertions)
  - [`test_midstream_failure_propagates_not_silently_truncates`](file:///e:/JakeAI/backend/tests/test_r_logic_04_failure_handling.py#L1): RL04-F-05: a mid-stream provider failure raises instead of ending quietly. (1 assertions)
  - [`test_backend_stream_signals_error_terminal_chunk`](file:///e:/JakeAI/backend/tests/test_r_logic_04_failure_handling.py#L1): JakeAIBackend.generate_stream yields an error terminal chunk on mid-stream failure. (3 assertions)
  - [`test_rag_total_retrieval_failure_classified_as_retrieval_failure`](file:///e:/JakeAI/backend/tests/test_r_logic_04_failure_handling.py#L1): RL04-F-06: both retrieval legs failing is RETRIEVAL_FAILURE, not empty evidence. (2 assertions)
  - [`test_rag_empty_index_still_no_relevant_evidence`](file:///e:/JakeAI/backend/tests/test_r_logic_04_failure_handling.py#L1): A genuinely empty (but healthy) index stays NO_RELEVANT_EVIDENCE. (2 assertions)
  - [`test_corrupt_checkpoint_fails_closed_no_fabricated_success`](file:///e:/JakeAI/backend/tests/test_r_logic_04_failure_handling.py#L1): A corrupt checkpoint record cannot be resumed into a fake success. (1 assertions)
  - [`test_redis_write_failure_degrades_to_memory_without_crash`](file:///e:/JakeAI/backend/tests/test_r_logic_04_failure_handling.py#L1): Checkpoint writes degrade to in-memory durability when Redis fails. (2 assertions)
  - [`test_tool_timeout_returns_failed_result`](file:///e:/JakeAI/backend/tests/test_r_logic_04_failure_handling.py#L1): Direct assertion (2 assertions)
  - [`test_tool_policy_denial_never_executes`](file:///e:/JakeAI/backend/tests/test_r_logic_04_failure_handling.py#L1): Direct assertion (2 assertions)
  - [`test_engine_permission_denied_step_terminates_without_retry`](file:///e:/JakeAI/backend/tests/test_r_logic_04_failure_handling.py#L1): A policy-denied tool step terminates the run (never retried into success). (3 assertions)
  - [`test_malformed_plan_output_falls_back_deterministically`](file:///e:/JakeAI/backend/tests/test_r_logic_04_failure_handling.py#L1): A model returning garbage instead of plan JSON falls back, bounded. (2 assertions)

#### `CAT-054`: [`test_rag.py`](file:///e:/JakeAI/backend/tests/test_rag.py)
- **Test File Path**: `backend/tests/test_rag.py` (471 lines)
- **Subsystem**: `RAG Pipeline`
- **Test Level**: `Unit`
- **Purpose**: Unit and integration tests for RAG engine, hybrid retrieval, and Self-RAG loop.
- **Dependencies / Fixtures**: Qdrant, HTTP / ASGI, Mocks / Monkeypatch
- **CI Job Execution**: `unit-and-ai-tests (Full Suite Floor)`
- **Recommended Run Frequency**: `PR / Push (main)`
- **Duplicate / Overlap Classification**: `COMPLEMENTARY`
- **RIGHT Test Suite Coverage**: `R-FUNC-02 / R-AI-01`
- **Bruno Collection Coverage**: `Bruno/04 — RAG (01-07)`
- **Architectural Disposition**: **`MOVE`** (Target Destination: `backend/tests/unit/`)
- **Disposition Rationale & Evidence**: Valuable subsystem test. Needs reclassification into unit/, integration/, or security/.
- **Discovered Test Functions (16)**:
  - [`test_bm25_retriever_search_and_tenant_isolation`](file:///e:/JakeAI/backend/tests/test_rag.py#L1): Verify BM25 retrieval finds passages and strictly isolates tenant data. (7 assertions)
  - [`test_qdrant_vector_store_dense_search`](file:///e:/JakeAI/backend/tests/test_rag.py#L1): Verify dense vector store indexes embeddings with tenant filtering. (3 assertions)
  - [`test_cross_encoder_reranker`](file:///e:/JakeAI/backend/tests/test_rag.py#L1): Verify CrossEncoderReranker combines streams and prioritizes exact matches. (3 assertions)
  - [`test_hybrid_retriever_pipeline`](file:///e:/JakeAI/backend/tests/test_rag.py#L1): Verify end-to-end HybridRetriever indexing and parallel querying. (4 assertions)
  - [`test_citation_generator`](file:///e:/JakeAI/backend/tests/test_rag.py#L1): Verify CitationGenerator inserts footnotes and generates markdown cards. (4 assertions)
  - [`test_verifier_node_self_rag_groundedness_pass`](file:///e:/JakeAI/backend/tests/test_rag.py#L1): Verify verifier_node passes when response is grounded in retrieved context. (4 assertions)
  - [`test_verifier_node_self_rag_groundedness_reject_loop`](file:///e:/JakeAI/backend/tests/test_rag.py#L1): Verify verifier_node triggers critique loop when groundedness is low. (4 assertions)
  - [`test_cross_encoder_reranker_with_custom_callable`](file:///e:/JakeAI/backend/tests/test_rag.py#L1): Verify CrossEncoderReranker applies custom ONNX/CrossEncoder callable scores. (3 assertions)
  - [`test_cross_encoder_empty_inputs`](file:///e:/JakeAI/backend/tests/test_rag.py#L1): Verify CrossEncoderReranker gracefully handles empty candidate inputs. (1 assertions)
  - [`test_cross_encoder_reranker_model_initialization_and_fallback`](file:///e:/JakeAI/backend/tests/test_rag.py#L1): Verify CrossEncoderReranker model_name initialization and fallback execution. (4 assertions)
  - [`test_cross_encoder_reranker_with_fastembed_model`](file:///e:/JakeAI/backend/tests/test_rag.py#L1): Verify CrossEncoderReranker execution with active FastEmbed model. (3 assertions)
  - [`test_document_ingestion_pipeline_end_to_end`](file:///e:/JakeAI/backend/tests/test_rag.py#L1): Verify DocumentIngestionPipeline chunks, creates deterministic IDs, and indexes. (9 assertions)
  - [`test_context_selector_deduplication_and_budget`](file:///e:/JakeAI/backend/tests/test_rag.py#L1): Verify ContextSelector drops low-score chunks and formats structured context. (6 assertions)
  - [`test_rag_pipeline_retrieve_and_select`](file:///e:/JakeAI/backend/tests/test_rag.py#L1): Verify RAGPipeline retrieve_and_select_context returns candidate and context result. (4 assertions)
  - [`test_rag_pipeline_generate_grounded_answer`](file:///e:/JakeAI/backend/tests/test_rag.py#L1): Verify RAGPipeline generate_grounded_answer synthesizes answer with citations. (5 assertions)
  - [`test_rag_api_endpoints_integration`](file:///e:/JakeAI/backend/tests/test_rag.py#L1): Verify /api/v1/rag/query and /api/v1/rag/generate endpoints with HTTP client. (11 assertions)

#### `CAT-055`: [`test_rag_bm25_persistence.py`](file:///e:/JakeAI/backend/tests/test_rag_bm25_persistence.py)
- **Test File Path**: `backend/tests/test_rag_bm25_persistence.py` (80 lines)
- **Subsystem**: `RAG Pipeline`
- **Test Level**: `Unit`
- **Purpose**: Unit tests for TASK RAG-05: BM25 Re-indexing IDF Repair and Disk Persistence.
- **Dependencies / Fixtures**: None (Pure In-Memory)
- **CI Job Execution**: `unit-and-ai-tests (Full Suite Floor)`
- **Recommended Run Frequency**: `PR / Push (main)`
- **Duplicate / Overlap Classification**: `PARTIAL OVERLAP`
- **RIGHT Test Suite Coverage**: `R-FUNC-02 / R-AI-01`
- **Bruno Collection Coverage**: `NONE`
- **Architectural Disposition**: **`MERGE`** (Target Destination: `backend/tests/unit/`)
- **Disposition Rationale & Evidence**: Tests BM25 disk persistence; overlaps with test_rag.py and test_r_func_02_rag_behavior.py. Writes bm25_test_index.json to disk. Merge into integration/rag/.
- **Discovered Test Functions (2)**:
  - [`test_bm25_reindex_idf_repair`](file:///e:/JakeAI/backend/tests/test_rag_bm25_persistence.py#L1): Verify re-indexing a chunk does not double-count document frequencies in BM25. (4 assertions)
  - [`test_bm25_disk_persistence`](file:///e:/JakeAI/backend/tests/test_rag_bm25_persistence.py#L1): Verify BM25 index saves to disk and restores state identically. (5 assertions)

#### `CAT-056`: [`test_rag_context_budget.py`](file:///e:/JakeAI/backend/tests/test_rag_context_budget.py)
- **Test File Path**: `backend/tests/test_rag_context_budget.py` (62 lines)
- **Subsystem**: `RAG Pipeline`
- **Test Level**: `Unit`
- **Purpose**: Unit tests for TASK RAG-08: BPETokenizer Full Envelope Budgeting and Score Leakage Elimination.
- **Dependencies / Fixtures**: None (Pure In-Memory)
- **CI Job Execution**: `unit-and-ai-tests (Full Suite Floor)`
- **Recommended Run Frequency**: `PR / Push (main)`
- **Duplicate / Overlap Classification**: `PARTIAL OVERLAP`
- **RIGHT Test Suite Coverage**: `R-FUNC-02 / R-AI-01`
- **Bruno Collection Coverage**: `NONE`
- **Architectural Disposition**: **`MERGE`** (Target Destination: `backend/tests/unit/`)
- **Disposition Rationale & Evidence**: Tests context budget shedding; overlaps with test_rag_unified_envelope.py and test_r_ai_04_context_correctness.py. Merge into unit/rag/.
- **Discovered Test Functions (2)**:
  - [`test_no_score_leakage_in_formatted_context`](file:///e:/JakeAI/backend/tests/test_rag_context_budget.py#L1): Verify formatted context never leaks internal scores like '(Score: 0.95)' into model prompt. (4 assertions)
  - [`test_bpe_tokenizer_full_envelope_budgeting`](file:///e:/JakeAI/backend/tests/test_rag_context_budget.py#L1): Verify context selection measures the full formatted string with BPETokenizer and never exceeds max_tokens. (2 assertions)

#### `CAT-057`: [`test_rag_embedding_and_points.py`](file:///e:/JakeAI/backend/tests/test_rag_embedding_and_points.py)
- **Test File Path**: `backend/tests/test_rag_embedding_and_points.py` (161 lines)
- **Subsystem**: `RAG Pipeline`
- **Test Level**: `Unit`
- **Purpose**: Unit tests for TASK RAG-03 and RAG-04: Real Embeddings, Dimension Verification, and Deterministic Points.
- **Dependencies / Fixtures**: Qdrant
- **CI Job Execution**: `unit-and-ai-tests (Full Suite Floor)`
- **Recommended Run Frequency**: `PR / Push (main)`
- **Duplicate / Overlap Classification**: `REVIEW`
- **RIGHT Test Suite Coverage**: `R-FUNC-02 / R-AI-01`
- **Bruno Collection Coverage**: `NONE`
- **Architectural Disposition**: **`MOVE`** (Target Destination: `backend/tests/unit/`)
- **Disposition Rationale & Evidence**: Tests deterministic UUIDv5 points. Contains unscoped os.environ mutation. Needs fix and move to unit/rag/.
- **Discovered Test Functions (7)**:
  - [`test_fastembed_provider_dimension_and_norm`](file:///e:/JakeAI/backend/tests/test_rag_embedding_and_points.py#L1): Verify FastEmbed generates 384-dimensional unit vectors. (4 assertions)
  - [`test_fastembed_batch_order_preservation`](file:///e:/JakeAI/backend/tests/test_rag_embedding_and_points.py#L1): Verify batch embeddings preserve exact input ordering. (2 assertions)
  - [`test_test_fake_embedding_provider_guard`](file:///e:/JakeAI/backend/tests/test_rag_embedding_and_points.py#L1): Verify TestOnlyFakeEmbeddingProvider cannot be instantiated in production. (0 assertions)
  - [`test_deterministic_qdrant_point_id`](file:///e:/JakeAI/backend/tests/test_rag_embedding_and_points.py#L1): Verify derive_point_id produces stable UUIDv5 across calls and changes on different chunk_ids. (3 assertions)
  - [`test_vector_store_dimension_mismatch_error`](file:///e:/JakeAI/backend/tests/test_rag_embedding_and_points.py#L1): Verify vector store raises DimensionMismatchError when collection dimension != provider dimension. (0 assertions)
  - [`test_repeat_indexing_idempotent_no_duplicates`](file:///e:/JakeAI/backend/tests/test_rag_embedding_and_points.py#L1): Verify updating a chunk in vector store updates existing point rather than creating duplicates. (4 assertions)
  - [`test_vector_store_edge_cases`](file:///e:/JakeAI/backend/tests/test_rag_embedding_and_points.py#L1): Verify empty upserts and cosine similarity boundary conditions. (3 assertions)

#### `CAT-058`: [`test_rag_grounding_and_abstention.py`](file:///e:/JakeAI/backend/tests/test_rag_grounding_and_abstention.py)
- **Test File Path**: `backend/tests/test_rag_grounding_and_abstention.py` (173 lines)
- **Subsystem**: `RAG Pipeline`
- **Test Level**: `Unit`
- **Purpose**: Unit tests for TASK RAG-09, 10, 11: Grounding, Verifiable Citations, and Explicit Abstention.
- **Dependencies / Fixtures**: Mocks / Monkeypatch
- **CI Job Execution**: `unit-and-ai-tests (Full Suite Floor)`
- **Recommended Run Frequency**: `PR / Push (main)`
- **Duplicate / Overlap Classification**: `COMPLEMENTARY`
- **RIGHT Test Suite Coverage**: `R-FUNC-02 / R-AI-01`
- **Bruno Collection Coverage**: `NONE`
- **Architectural Disposition**: **`MERGE`** (Target Destination: `backend/tests/unit/`)
- **Disposition Rationale & Evidence**: Groundedness threshold checks; largely replicated and extended in test_r_ai_01_rag_grounding.py and test_r_func_02_rag_behavior.py. Merge.
- **Discovered Test Functions (6)**:
  - [`test_grounding_verifier_claim_classification`](file:///e:/JakeAI/backend/tests/test_rag_grounding_and_abstention.py#L1): Verify GroundingVerifier classifies SUPPORTED, UNSUPPORTED, and UNCERTAIN claims. (6 assertions)
  - [`test_citation_generator_strips_hallucinated_footnotes`](file:///e:/JakeAI/backend/tests/test_rag_grounding_and_abstention.py#L1): Verify CitationGenerator removes arbitrary LLM hallucinated footnotes like [^99]. (6 assertions)
  - [`test_pipeline_abstention_on_no_evidence`](file:///e:/JakeAI/backend/tests/test_rag_grounding_and_abstention.py#L1): Verify RAGPipeline explicitly returns status='ABSTAINED' and reason='NO_RELEVANT_EVIDENCE' when no chunks match. (4 assertions)
  - [`test_pipeline_abstention_never_echoes_irrelevant_chunks`](file:///e:/JakeAI/backend/tests/test_rag_grounding_and_abstention.py#L1): Verify RAGPipeline never echoes irrelevant chunks when LLM synthesis is offline. (3 assertions)
  - [`test_pipeline_abstention_on_provider_failure`](file:///e:/JakeAI/backend/tests/test_rag_grounding_and_abstention.py#L1): Verify RAGPipeline explicitly returns status='ABSTAINED' and reason='PROVIDER_FAILURE' on upstream error. (3 assertions)
  - [`test_pipeline_abstention_on_generation_failure`](file:///e:/JakeAI/backend/tests/test_rag_grounding_and_abstention.py#L1): Verify RAGPipeline explicitly returns status='ABSTAINED' and reason='GENERATION_FAILURE' on completely ungrounded generation. (4 assertions)

#### `CAT-059`: [`test_rag_hybrid_retrieval.py`](file:///e:/JakeAI/backend/tests/test_rag_hybrid_retrieval.py)
- **Test File Path**: `backend/tests/test_rag_hybrid_retrieval.py` (127 lines)
- **Subsystem**: `RAG Pipeline`
- **Test Level**: `Unit`
- **Purpose**: Unit tests for TASK RAG-06: Concurrency, Degraded Mode, 3x Candidate Pool, and Deterministic Tie-Breaking.
- **Dependencies / Fixtures**: Qdrant
- **CI Job Execution**: `unit-and-ai-tests (Full Suite Floor)`
- **Recommended Run Frequency**: `PR / Push (main)`
- **Duplicate / Overlap Classification**: `PARTIAL OVERLAP`
- **RIGHT Test Suite Coverage**: `R-FUNC-02 / R-AI-01`
- **Bruno Collection Coverage**: `NONE`
- **Architectural Disposition**: **`MERGE`** (Target Destination: `backend/tests/unit/`)
- **Disposition Rationale & Evidence**: RRF hybrid retrieval unit tests; duplicate logic in test_rag.py. Merge into unit/rag/.
- **Discovered Test Functions (3)**:
  - [`test_hybrid_retrieval_concurrent_success`](file:///e:/JakeAI/backend/tests/test_rag_hybrid_retrieval.py#L1): Verify normal concurrent hybrid retrieval returns mode='hybrid' and degraded=False. (5 assertions)
  - [`test_hybrid_retrieval_degraded_mode_on_dense_failure`](file:///e:/JakeAI/backend/tests/test_rag_hybrid_retrieval.py#L1): Verify degraded mode fallback to sparse when vector store fails, without raising exception. (6 assertions)
  - [`test_deterministic_tie_breaking_by_chunk_id`](file:///e:/JakeAI/backend/tests/test_rag_hybrid_retrieval.py#L1): Verify chunks with equal relevance score sort deterministically by chunk_id. (1 assertions)

#### `CAT-060`: [`test_rag_normalization.py`](file:///e:/JakeAI/backend/tests/test_rag_normalization.py)
- **Test File Path**: `backend/tests/test_rag_normalization.py` (65 lines)
- **Subsystem**: `RAG Pipeline`
- **Test Level**: `Unit`
- **Purpose**: Unit tests for TASK RAG-02: Unicode NFKC and text normalization.
- **Dependencies / Fixtures**: None (Pure In-Memory)
- **CI Job Execution**: `unit-and-ai-tests (Full Suite Floor)`
- **Recommended Run Frequency**: `PR / Push (main)`
- **Duplicate / Overlap Classification**: `COMPLEMENTARY`
- **RIGHT Test Suite Coverage**: `R-FUNC-02 / R-AI-01`
- **Bruno Collection Coverage**: `NONE`
- **Architectural Disposition**: **`MOVE`** (Target Destination: `backend/tests/unit/`)
- **Disposition Rationale & Evidence**: High-value unit tests for NFKC unicode and MIME parsing. Move to unit/rag/.
- **Discovered Test Functions (4)**:
  - [`test_unicode_nfkc_normalization`](file:///e:/JakeAI/backend/tests/test_rag_normalization.py#L1): Verify NFKC decomposes ligatures and normalizes full-width forms. (2 assertions)
  - [`test_line_ending_normalization`](file:///e:/JakeAI/backend/tests/test_rag_normalization.py#L1): Verify CRLF (Windows) and CR (old Mac) are normalized to LF. (2 assertions)
  - [`test_control_character_stripping`](file:///e:/JakeAI/backend/tests/test_rag_normalization.py#L1): Verify non-printable control characters are removed while preserving     and  (8 assertions)
  - [`test_code_block_preservation`](file:///e:/JakeAI/backend/tests/test_rag_normalization.py#L1): Verify prose whitespace is collapsed while code block indentation is preserved. (4 assertions)

#### `CAT-061`: [`test_rag_parsers.py`](file:///e:/JakeAI/backend/tests/test_rag_parsers.py)
- **Test File Path**: `backend/tests/test_rag_parsers.py` (170 lines)
- **Subsystem**: `RAG Pipeline`
- **Test Level**: `Unit`
- **Purpose**: Unit tests for RAG document parsers (PlainText, Markdown, PDF) and MIME validation.
- **Dependencies / Fixtures**: Qdrant, Mocks / Monkeypatch
- **CI Job Execution**: `unit-and-ai-tests (Full Suite Floor)`
- **Recommended Run Frequency**: `PR / Push (main)`
- **Duplicate / Overlap Classification**: `COMPLEMENTARY`
- **RIGHT Test Suite Coverage**: `R-FUNC-02 / R-AI-01`
- **Bruno Collection Coverage**: `NONE`
- **Architectural Disposition**: **`MOVE`** (Target Destination: `backend/tests/unit/`)
- **Disposition Rationale & Evidence**: Comprehensive document parser unit tests (MD, PDF, TXT). Move to unit/rag/.
- **Discovered Test Functions (8)**:
  - [`test_plain_text_parser`](file:///e:/JakeAI/backend/tests/test_rag_parsers.py#L1): Verify PlainTextParser handles UTF-8, Latin-1, and null byte removal. (7 assertions)
  - [`test_markdown_parser_headings`](file:///e:/JakeAI/backend/tests/test_rag_parsers.py#L1): Verify MarkdownParser extracts headings and structural text. (7 assertions)
  - [`test_markdown_parser_heading_extraction_import_error`](file:///e:/JakeAI/backend/tests/test_rag_parsers.py#L1): Verify MarkdownParser continues parsing when markdown_it dependency is missing. (7 assertions)
  - [`test_markdown_parser_heading_extraction_parser_error`](file:///e:/JakeAI/backend/tests/test_rag_parsers.py#L1): Verify MarkdownParser handles expected parser errors (ValueError, TypeError) gracefully. (3 assertions)
  - [`test_markdown_parser_unexpected_exception_propagates`](file:///e:/JakeAI/backend/tests/test_rag_parsers.py#L1): Verify unexpected programming errors (RuntimeError, KeyError) are not silently swallowed. (0 assertions)
  - [`test_pdf_parser_text_and_pages`](file:///e:/JakeAI/backend/tests/test_rag_parsers.py#L1): Verify PDFParser extracts text and page metadata using pypdf. (5 assertions)
  - [`test_get_parser_resolution_and_rejection`](file:///e:/JakeAI/backend/tests/test_rag_parsers.py#L1): Verify get_parser resolves valid types and rejects unsupported formats. (7 assertions)
  - [`test_ingest_file_bytes_markdown_and_pdf`](file:///e:/JakeAI/backend/tests/test_rag_parsers.py#L1): Verify DocumentIngestionPipeline.ingest_file_bytes parses markdown and pdf bytes. (3 assertions)

#### `CAT-062`: [`test_rag_reranker.py`](file:///e:/JakeAI/backend/tests/test_rag_reranker.py)
- **Test File Path**: `backend/tests/test_rag_reranker.py` (83 lines)
- **Subsystem**: `RAG Pipeline`
- **Test Level**: `Unit`
- **Purpose**: Unit tests for TASK RAG-07: Cross-Encoder Reranking, Telemetry, and Heuristic Fallback.
- **Dependencies / Fixtures**: None (Pure In-Memory)
- **CI Job Execution**: `unit-and-ai-tests (Full Suite Floor)`
- **Recommended Run Frequency**: `PR / Push (main)`
- **Duplicate / Overlap Classification**: `PARTIAL OVERLAP`
- **RIGHT Test Suite Coverage**: `R-FUNC-02 / R-AI-01`
- **Bruno Collection Coverage**: `NONE`
- **Architectural Disposition**: **`MERGE`** (Target Destination: `backend/tests/unit/`)
- **Disposition Rationale & Evidence**: Tests CrossEncoder reranking; overlaps with test_rag.py (lines 130-180) and test_r_func_02_rag_behavior.py. Merge into unit/rag/.
- **Discovered Test Functions (3)**:
  - [`test_reranker_telemetry_and_custom_fn`](file:///e:/JakeAI/backend/tests/test_rag_reranker.py#L1): Verify custom cross-encoder function records telemetry 'custom_fn' and scores accurately. (4 assertions)
  - [`test_reranker_calibrated_heuristic_fallback`](file:///e:/JakeAI/backend/tests/test_rag_reranker.py#L1): Verify calibrated heuristic fallback operates properly without 10x multiplier. (5 assertions)
  - [`test_reranker_empty_results_telemetry`](file:///e:/JakeAI/backend/tests/test_rag_reranker.py#L1): Verify empty input candidates sets last_reranker_type to 'empty'. (2 assertions)

#### `CAT-063`: [`test_rag_tenant_isolation.py`](file:///e:/JakeAI/backend/tests/test_rag_tenant_isolation.py)
- **Test File Path**: `backend/tests/test_rag_tenant_isolation.py` (260 lines)
- **Subsystem**: `RAG Pipeline`
- **Test Level**: `Unit`
- **Purpose**: Comprehensive Multi-Tenant Isolation Test Suite for JakeAI RAG Platform.
- **Dependencies / Fixtures**: Qdrant
- **CI Job Execution**: `unit-and-ai-tests (Full Suite Floor)`
- **Recommended Run Frequency**: `PR / Push (main)`
- **Duplicate / Overlap Classification**: `COMPLEMENTARY`
- **RIGHT Test Suite Coverage**: `R-FUNC-02 / R-AI-01`
- **Bruno Collection Coverage**: `NONE`
- **Architectural Disposition**: **`MOVE`** (Target Destination: `backend/tests/security/`)
- **Disposition Rationale & Evidence**: Valuable subsystem test. Needs reclassification into unit/, integration/, or security/.
- **Discovered Test Functions (6)**:
  - [`test_bm25_strict_tenant_isolation`](file:///e:/JakeAI/backend/tests/test_rag_tenant_isolation.py#L1): Verify BM25 sparse index never returns Tenant Alpha documents for Tenant Beta queries. (7 assertions)
  - [`test_qdrant_vector_store_strict_tenant_isolation`](file:///e:/JakeAI/backend/tests/test_rag_tenant_isolation.py#L1): Verify dense vector store enforces tenant boundary filtering in memory and live store. (3 assertions)
  - [`test_hybrid_retriever_cross_tenant_rejection`](file:///e:/JakeAI/backend/tests/test_rag_tenant_isolation.py#L1): Verify end-to-end HybridRetriever filters candidate pools to tenant scope. (6 assertions)
  - [`test_context_selector_foreign_tenant_rejection`](file:///e:/JakeAI/backend/tests/test_rag_tenant_isolation.py#L1): Verify ContextSelector detects and purges any foreign tenant chunks in candidates. (5 assertions)
  - [`test_rag_pipeline_end_to_end_tenant_isolation`](file:///e:/JakeAI/backend/tests/test_rag_tenant_isolation.py#L1): Verify the 10-step RAGPipeline guarantees zero cross-tenant evidence leakage. (5 assertions)
  - [`test_concurrent_multi_tenant_isolation_stress`](file:///e:/JakeAI/backend/tests/test_rag_tenant_isolation.py#L1): Stress test 5 concurrent tenants querying their own and peer data simultaneously. (1 assertions)

#### `CAT-064`: [`test_rag_tenant_isolation_hardened.py`](file:///e:/JakeAI/backend/tests/test_rag_tenant_isolation_hardened.py)
- **Test File Path**: `backend/tests/test_rag_tenant_isolation_hardened.py` (116 lines)
- **Subsystem**: `RAG Pipeline`
- **Test Level**: `Unit`
- **Purpose**: Unit tests for TASK RAG-13: Hardened Multi-Tenant Isolation Defense-in-Depth.
- **Dependencies / Fixtures**: Qdrant
- **CI Job Execution**: `unit-and-ai-tests (Full Suite Floor)`
- **Recommended Run Frequency**: `PR / Push (main)`
- **Duplicate / Overlap Classification**: `COMPLEMENTARY`
- **RIGHT Test Suite Coverage**: `R-FUNC-02 / R-AI-01`
- **Bruno Collection Coverage**: `NONE`
- **Architectural Disposition**: **`MOVE`** (Target Destination: `backend/tests/security/`)
- **Disposition Rationale & Evidence**: Defense-in-depth tenant isolation checks. Move to security/ or unit/rag/.
- **Discovered Test Functions (4)**:
  - [`test_tenant_isolation_in_ingestion_and_hybrid_retrieval`](file:///e:/JakeAI/backend/tests/test_rag_tenant_isolation_hardened.py#L1): Verify tenant data indexed under tenant-A is strictly inaccessible to tenant-B in dense, sparse, and hybrid search. (3 assertions)
  - [`test_tenant_isolation_context_selector_guard`](file:///e:/JakeAI/backend/tests/test_rag_tenant_isolation_hardened.py#L1): Verify ContextSelector forcefully drops candidate chunks belonging to foreign tenants. (3 assertions)
  - [`test_tenant_isolation_citations_filter`](file:///e:/JakeAI/backend/tests/test_rag_tenant_isolation_hardened.py#L1): Verify CitationGenerator never links citations containing foreign tenant IDs. (2 assertions)
  - [`test_tenant_isolation_context_envelope_tagging`](file:///e:/JakeAI/backend/tests/test_rag_tenant_isolation_hardened.py#L1): Verify ContextEnvelope retains tenant boundary tag and scopes correctly. (1 assertions)

#### `CAT-065`: [`test_rag_unified_envelope.py`](file:///e:/JakeAI/backend/tests/test_rag_unified_envelope.py)
- **Test File Path**: `backend/tests/test_rag_unified_envelope.py` (112 lines)
- **Subsystem**: `RAG Pipeline`
- **Test Level**: `Unit`
- **Purpose**: Unit tests for TASK RAG-12: Unified 6-stage Context Envelope and Token Budgeting.
- **Dependencies / Fixtures**: None (Pure In-Memory)
- **CI Job Execution**: `unit-and-ai-tests (Full Suite Floor)`
- **Recommended Run Frequency**: `PR / Push (main)`
- **Duplicate / Overlap Classification**: `COMPLEMENTARY`
- **RIGHT Test Suite Coverage**: `R-FUNC-02 / R-AI-01`
- **Bruno Collection Coverage**: `NONE`
- **Architectural Disposition**: **`MOVE`** (Target Destination: `backend/tests/unit/`)
- **Disposition Rationale & Evidence**: Valuable subsystem test. Needs reclassification into unit/, integration/, or security/.
- **Discovered Test Functions (3)**:
  - [`test_context_envelope_canonical_ordering`](file:///e:/JakeAI/backend/tests/test_rag_unified_envelope.py#L1): Verify ContextEnvelopeBuilder outputs sections in exact 6-stage canonical order. (3 assertions)
  - [`test_context_envelope_budget_shedding`](file:///e:/JakeAI/backend/tests/test_rag_unified_envelope.py#L1): Verify ContextEnvelopeBuilder sheds oldest conversation history and memory when exceeding budget. (4 assertions)
  - [`test_context_envelope_string_inputs_and_evidence_shedding`](file:///e:/JakeAI/backend/tests/test_rag_unified_envelope.py#L1): Verify ContextEnvelopeBuilder accepts plain strings and sheds evidence when necessary. (4 assertions)

#### `CAT-068`: [`test_semantic_cache_real.py`](file:///e:/JakeAI/backend/tests/test_semantic_cache_real.py)
- **Test File Path**: `backend/tests/test_semantic_cache_real.py` (300 lines)
- **Subsystem**: `RAG Pipeline`
- **Test Level**: `Unit`
- **Purpose**: Comprehensive unit and integration tests for COST-08: True Vector Semantic Cache.
- **Dependencies / Fixtures**: Qdrant, Mocks / Monkeypatch
- **CI Job Execution**: `unit-and-ai-tests (Full Suite Floor)`
- **Recommended Run Frequency**: `PR / Push (main)`
- **Duplicate / Overlap Classification**: `PARTIAL OVERLAP`
- **RIGHT Test Suite Coverage**: `R-FUNC-03 / R-AI-02`
- **Bruno Collection Coverage**: `NONE`
- **Architectural Disposition**: **`MERGE`** (Target Destination: `backend/tests/unit/`)
- **Disposition Rationale & Evidence**: Exercises real Qdrant/FastEmbed caching. Scenarios overlap with test_r_func_03_cache_behavior.py; should merge into target integration/cache/.
- **Discovered Test Functions (6)**:
  - [`test_real_embedding_dense_semantic_matching`](file:///e:/JakeAI/backend/tests/test_semantic_cache_real.py#L1): Verify real embedding provider computes dense vectors and yields semantic hits. (4 assertions)
  - [`test_qdrant_vector_store_upsert_and_search`](file:///e:/JakeAI/backend/tests/test_semantic_cache_real.py#L1): Verify SemanticCacheManager interacts with Qdrant client for upsert and search. (12 assertions)
  - [`test_qdrant_tenant_isolation_in_search`](file:///e:/JakeAI/backend/tests/test_semantic_cache_real.py#L1): Verify Qdrant search strictly rejects hits that belong to a different tenant. (1 assertions)
  - [`test_qdrant_invalidation`](file:///e:/JakeAI/backend/tests/test_semantic_cache_real.py#L1): Verify cache invalidation deletes points from Qdrant by tenant or globally. (3 assertions)
  - [`test_generation_guardrails_prevent_mismatched_semantic_hit`](file:///e:/JakeAI/backend/tests/test_semantic_cache_real.py#L1): Verify semantic hits are prevented when model, tools, or system prompt mismatch. (3 assertions)
  - [`test_fallback_to_memory_when_qdrant_fails`](file:///e:/JakeAI/backend/tests/test_semantic_cache_real.py#L1): Verify seamless failover to in-memory vector store when Qdrant encounters exceptions. (3 assertions)

#### `CAT-072`: [`test_verifier_invariants.py`](file:///e:/JakeAI/backend/tests/test_verifier_invariants.py)
- **Test File Path**: `backend/tests/test_verifier_invariants.py` (157 lines)
- **Subsystem**: `RAG Pipeline`
- **Test Level**: `Unit`
- **Purpose**: Regression tests for Verifier invariant guarantees (TASK ORC-01).
- **Dependencies / Fixtures**: Mocks / Monkeypatch
- **CI Job Execution**: `unit-and-ai-tests (Full Suite Floor)`
- **Recommended Run Frequency**: `PR / Push (main)`
- **Duplicate / Overlap Classification**: `PARTIAL OVERLAP`
- **RIGHT Test Suite Coverage**: `R-ARCH-00 / R-LOGIC-00`
- **Bruno Collection Coverage**: `NONE`
- **Architectural Disposition**: **`MERGE`** (Target Destination: `backend/tests/unit/`)
- **Disposition Rationale & Evidence**: Tests verifier loop limits; overlaps with test_r_logic_00_invariants.py and test_orchestration_contracts.py. Merge into unit/agent/.
- **Discovered Test Functions (5)**:
  - [`test_verifier_tenant_mismatch_at_revision_0`](file:///e:/JakeAI/backend/tests/test_verifier_invariants.py#L1): Tenant mismatch at revision 0 must immediately return REJECTED without retry loop. (5 assertions)
  - [`test_verifier_tenant_mismatch_at_max_revision`](file:///e:/JakeAI/backend/tests/test_verifier_invariants.py#L1): Tenant mismatch at max revision must return REJECTED, NEVER PASS. (3 assertions)
  - [`test_verifier_math_error_at_max_revision`](file:///e:/JakeAI/backend/tests/test_verifier_invariants.py#L1): Math error at max revision must return FAILED, NEVER PASS. (4 assertions)
  - [`test_verifier_ungrounded_answer_at_max_revision`](file:///e:/JakeAI/backend/tests/test_verifier_invariants.py#L1): Ungrounded answer (low faithfulness / anti-hallucination failed) at max revision returns FAILED. (4 assertions)
  - [`test_verifier_clean_pass`](file:///e:/JakeAI/backend/tests/test_verifier_invariants.py#L1): Clean pass occurs strictly when tenant matches, math is consistent, and grounding passes. (4 assertions)

#### `CAT-077`: [`test_canary_leakage.py`](file:///e:/JakeAI/backend/tests/evals/test_canary_leakage.py)
- **Test File Path**: `backend/tests/evals/test_canary_leakage.py` (158 lines)
- **Subsystem**: `RAG Pipeline`
- **Test Level**: `AI Eval / Benchmark`
- **Purpose**: Comprehensive Canary Data Leakage and Secret Sanitization Tests (TASK OPS-13 & OPS-14).
- **Dependencies / Fixtures**: None (Pure In-Memory)
- **CI Job Execution**: `LLMOps Safety & Canary Data Leakage Gate`
- **Recommended Run Frequency**: `PR / Push (main)`
- **Duplicate / Overlap Classification**: `UNIQUE`
- **RIGHT Test Suite Coverage**: `NONE`
- **Bruno Collection Coverage**: `NONE`
- **Architectural Disposition**: **`MOVE`** (Target Destination: `backend/tests/evals/`)
- **Disposition Rationale & Evidence**: AI evaluation or empirical token benchmark suite. Move to evals/.
- **Discovered Test Functions (5)**:
  - [`test_rag_tenant_isolation_canary_leakage`](file:///e:/JakeAI/backend/tests/evals/test_canary_leakage.py#L1): Verify Tenant B cannot retrieve or synthesize Tenant A canary tokens. (5 assertions)
  - [`test_cache_tenant_isolation_canary`](file:///e:/JakeAI/backend/tests/evals/test_canary_leakage.py#L1): Verify semantic cache partitions entries strictly by tenant_id. (3 assertions)
  - [`test_episodic_memory_tenant_isolation`](file:///e:/JakeAI/backend/tests/evals/test_canary_leakage.py#L1): Verify episodic memory retrieval respects strict tenant partitions. (2 assertions)
  - [`test_error_message_credential_sanitization`](file:///e:/JakeAI/backend/tests/evals/test_canary_leakage.py#L1): Verify DB URIs, cloud keys, internal IPs, and JWTs are redacted from error messages (TASK OPS-14). (9 assertions)
  - [`test_telemetry_prom_zero_canary_leakage`](file:///e:/JakeAI/backend/tests/evals/test_canary_leakage.py#L1): Verify Prometheus text format never emits canary secrets or user prompts. (3 assertions)

#### `CAT-084`: [`test_rag_context_efficiency.py`](file:///e:/JakeAI/backend/tests/evals/test_rag_context_efficiency.py)
- **Test File Path**: `backend/tests/evals/test_rag_context_efficiency.py` (237 lines)
- **Subsystem**: `RAG Pipeline`
- **Test Level**: `AI Eval / Benchmark`
- **Purpose**: RAG Context Efficiency & Quality Evaluation Benchmark Suite.
- **Dependencies / Fixtures**: None (Pure In-Memory)
- **CI Job Execution**: `unit-and-ai-tests (Full Suite Floor)`
- **Recommended Run Frequency**: `PR / Push (main)`
- **Duplicate / Overlap Classification**: `UNIQUE`
- **RIGHT Test Suite Coverage**: `R-FUNC-02 / R-AI-01`
- **Bruno Collection Coverage**: `NONE`
- **Architectural Disposition**: **`MOVE`** (Target Destination: `backend/tests/evals/`)
- **Disposition Rationale & Evidence**: AI evaluation or empirical token benchmark suite. Move to evals/.
- **Discovered Test Functions (4)**:
  - [`test_context_selector_efficiency_and_redundancy_elimination`](file:///e:/JakeAI/backend/tests/evals/test_rag_context_efficiency.py#L1): Verify ContextSelector achieves >= 35% token reduction while preserving all numbers and citations. (14 assertions)
  - [`test_citation_generator_precision_and_groundedness`](file:///e:/JakeAI/backend/tests/evals/test_rag_context_efficiency.py#L1): Verify CitationGenerator correctly maps generated claims to passages with zero hallucinated sources. (6 assertions)
  - [`test_rag_evaluator_context_reduction_and_quality`](file:///e:/JakeAI/backend/tests/evals/test_rag_context_efficiency.py#L1): Verify RAG evaluator verifies context reduction, anti-hallucination, and citation precision. (8 assertions)
  - [`test_rag_pipeline_10_step_lifecycle_efficiency`](file:///e:/JakeAI/backend/tests/evals/test_rag_context_efficiency.py#L1): Verify complete RAGPipeline lifecycle achieves context efficiency and grounded synthesis. (7 assertions)

#### `CAT-085`: [`test_rag_eval.py`](file:///e:/JakeAI/backend/tests/evals/test_rag_eval.py)
- **Test File Path**: `backend/tests/evals/test_rag_eval.py` (56 lines)
- **Subsystem**: `RAG Pipeline`
- **Test Level**: `AI Eval / Benchmark`
- **Purpose**: AI RAG Regression and Evaluation Test Suite using Golden Dataset Stub.
- **Dependencies / Fixtures**: None (Pure In-Memory)
- **CI Job Execution**: `unit-and-ai-tests (Full Suite Floor)`
- **Recommended Run Frequency**: `PR / Push (main)`
- **Duplicate / Overlap Classification**: `UNIQUE`
- **RIGHT Test Suite Coverage**: `R-FUNC-02 / R-AI-01`
- **Bruno Collection Coverage**: `NONE`
- **Architectural Disposition**: **`MOVE`** (Target Destination: `backend/tests/evals/`)
- **Disposition Rationale & Evidence**: AI evaluation or empirical token benchmark suite. Move to evals/.
- **Discovered Test Functions (1)**:
  - [`test_rag_golden_dataset_evaluation`](file:///e:/JakeAI/backend/tests/evals/test_rag_eval.py#L1): Evaluate RAG quality, faithfulness, anti-hallucination, and leakage. (7 assertions)

#### `CAT-086`: [`test_rag_metrics.py`](file:///e:/JakeAI/backend/tests/evals/test_rag_metrics.py)
- **Test File Path**: `backend/tests/evals/test_rag_metrics.py` (103 lines)
- **Subsystem**: `RAG Pipeline`
- **Test Level**: `AI Eval / Benchmark`
- **Purpose**: Unit tests for RAG Retrieval Metrics and Groundedness Evaluation Engines (TASK OPS-08 & OPS-11).
- **Dependencies / Fixtures**: None (Pure In-Memory)
- **CI Job Execution**: `LLMOps Safety & Canary Data Leakage Gate`
- **Recommended Run Frequency**: `PR / Push (main)`
- **Duplicate / Overlap Classification**: `UNIQUE`
- **RIGHT Test Suite Coverage**: `R-FUNC-02 / R-AI-01`
- **Bruno Collection Coverage**: `NONE`
- **Architectural Disposition**: **`MOVE`** (Target Destination: `backend/tests/evals/`)
- **Disposition Rationale & Evidence**: AI evaluation or empirical token benchmark suite. Move to evals/.
- **Discovered Test Functions (5)**:
  - [`test_retrieval_metrics_individual`](file:///e:/JakeAI/backend/tests/evals/test_rag_metrics.py#L1): Direct assertion (8 assertions)
  - [`test_retrieval_batch_evaluation`](file:///e:/JakeAI/backend/tests/evals/test_rag_metrics.py#L1): Direct assertion (4 assertions)
  - [`test_segment_claims`](file:///e:/JakeAI/backend/tests/evals/test_rag_metrics.py#L1): Direct assertion (3 assertions)
  - [`test_groundedness_evaluation_supported`](file:///e:/JakeAI/backend/tests/evals/test_rag_metrics.py#L1): Direct assertion (7 assertions)
  - [`test_groundedness_evaluation_hallucination`](file:///e:/JakeAI/backend/tests/evals/test_rag_metrics.py#L1): Direct assertion (6 assertions)

#### `CAT-087`: [`test_rag_regression.py`](file:///e:/JakeAI/backend/tests/evals/test_rag_regression.py)
- **Test File Path**: `backend/tests/evals/test_rag_regression.py` (62 lines)
- **Subsystem**: `RAG Pipeline`
- **Test Level**: `AI Eval / Benchmark`
- **Purpose**: Dedicated RAG Regression Testing Gate (Block 5).
- **Dependencies / Fixtures**: None (Pure In-Memory)
- **CI Job Execution**: `RAG Quality Gate & Anti-Hallucination Regression`
- **Recommended Run Frequency**: `PR / Push (main)`
- **Duplicate / Overlap Classification**: `UNIQUE`
- **RIGHT Test Suite Coverage**: `R-FUNC-02 / R-AI-01`
- **Bruno Collection Coverage**: `NONE`
- **Architectural Disposition**: **`MOVE`** (Target Destination: `backend/tests/evals/`)
- **Disposition Rationale & Evidence**: AI evaluation or empirical token benchmark suite. Move to evals/.
- **Discovered Test Functions (1)**:
  - [`test_rag_quality_gate`](file:///e:/JakeAI/backend/tests/evals/test_rag_regression.py#L1): Run RAG evaluation gate against golden test cases. (7 assertions)

#### `CAT-122`: [`test_eval_rag_automation.py`](file:///e:/JakeAI/backend/tests/evals/test_eval_rag_automation.py)
- **Test File Path**: `backend/tests/evals/test_eval_rag_automation.py` (420 lines)
- **Subsystem**: `RAG Pipeline`
- **Test Level**: `AI Eval / Benchmark`
- **Purpose**: Comprehensive automated evaluation for 10 RAG dimensions (MRR/NDCG retrieval relevance, multi-tenant isolation, 6-stage context construction, grounding entailment, citation integrity, unsupported claim detection, contradiction detection, epistemic abstention, prompt injection resistance, context budget load shedding) plus versioned regression fixtures.
- **Dependencies / Fixtures**: None (Pure In-Memory)
- **CI Job Execution**: `AI Behavior, Agent, RAG & Hallucination Evaluation Gate (TEST-06)`
- **Recommended Run Frequency**: `PR / Push (main)`
- **Duplicate / Overlap Classification**: `UNIQUE`
- **RIGHT Test Suite Coverage**: `R-FUNC-02 / R-AI-01 / R-AI-04`
- **Bruno Collection Coverage**: `Bruno/04 — RAG (01-07)`
- **Architectural Disposition**: **`CREATED`** (Target Destination: `backend/tests/evals/`)
- **Disposition Rationale & Evidence**: New TEST-06 automated evaluation layer for 10 RAG pipeline dimensions, retrieval math, and versioned regression fixtures.
- **Discovered Test Functions (11)**:
  - [`test_eval_rag_01_retrieval_relevance_ranking`](file:///e:/JakeAI/backend/tests/evals/test_eval_rag_automation.py#L1): Evaluate retrieval relevance ranking satisfies MRR >= 0.80 and NDCG@3 >= 0.85.
  - [`test_eval_rag_02_tenant_isolation_zero_leakage`](file:///e:/JakeAI/backend/tests/evals/test_eval_rag_automation.py#L1): Evaluate cross-tenant chunks are dropped fail-closed and foreign secrets never leak.
  - [`test_eval_rag_03_canonical_context_construction`](file:///e:/JakeAI/backend/tests/evals/test_eval_rag_automation.py#L1): Evaluate 6-stage context envelope strictly follows canonical sequence and strips scores.
  - [`test_eval_rag_04_grounding_and_entailment`](file:///e:/JakeAI/backend/tests/evals/test_eval_rag_automation.py#L1): Evaluate factual claims, metrics, and entities in generated answer are entailed by context.
  - [`test_eval_rag_05_citation_integrity_and_hallucinated_stripping`](file:///e:/JakeAI/backend/tests/evals/test_eval_rag_automation.py#L1): Evaluate citations match evidence passages and hallucinated unbacked footnotes are stripped.
  - [`test_eval_rag_06_unsupported_claim_detection`](file:///e:/JakeAI/backend/tests/evals/test_eval_rag_automation.py#L1): Evaluate identification and segregation of unsupported claims not found in context.
  - [`test_eval_rag_07_contradiction_detection`](file:///e:/JakeAI/backend/tests/evals/test_eval_rag_automation.py#L1): Evaluate antonym polarities (approved vs rejected) are detected as direct contradictions.
  - [`test_eval_rag_08_epistemic_abstention_on_missing_evidence`](file:///e:/JakeAI/backend/tests/evals/test_eval_rag_automation.py#L1): Evaluate safe refusal and epistemic boundary when context lacks relevant evidence.
  - [`test_eval_rag_09_prompt_injection_resistance`](file:///e:/JakeAI/backend/tests/evals/test_eval_rag_automation.py#L1): Evaluate indirect document-embedded prompt injection is neutralized without execution.
  - [`test_eval_rag_10_context_budget_load_shedding`](file:///e:/JakeAI/backend/tests/evals/test_eval_rag_automation.py#L1): Evaluate context builder sheds negotiable stages while strictly preserving core constraints.
  - [`test_eval_rag_versioned_fixtures_pass`](file:///e:/JakeAI/backend/tests/evals/test_eval_rag_automation.py#L1): Execute evaluation assertions for each versioned RAG fixture (10 items).

### 3.12 Subsystem: Security & Governance (8 Files)
#### `CAT-010`: [`test_cosign_oidc_signing.py`](file:///e:/JakeAI/backend/tests/test_cosign_oidc_signing.py)
- **Test File Path**: `backend/tests/test_cosign_oidc_signing.py` (350 lines)
- **Subsystem**: `Security & Governance`
- **Test Level**: `Unit`
- **Purpose**: Automated verification suite for deterministic Cosign keyless OIDC signing.
- **Dependencies / Fixtures**: None (Pure In-Memory)
- **CI Job Execution**: `unit-and-ai-tests (Full Suite Floor)`
- **Recommended Run Frequency**: `PR / Push (main)`
- **Duplicate / Overlap Classification**: `COMPLEMENTARY`
- **RIGHT Test Suite Coverage**: `NONE`
- **Bruno Collection Coverage**: `NONE`
- **Architectural Disposition**: **`MOVE`** (Target Destination: `backend/tests/security/`)
- **Disposition Rationale & Evidence**: Valuable subsystem test. Needs reclassification into unit/, integration/, or security/.
- **Discovered Test Functions (4)**:
  - [`test_missing_oidc_env_vars_fails_immediately`](file:///e:/JakeAI/backend/tests/test_cosign_oidc_signing.py#L1): Verify script fails immediately with diagnostic error if OIDC env vars are missing. (3 assertions)
  - [`test_signing_with_controlled_failures_and_fresh_tokens`](file:///e:/JakeAI/backend/tests/test_cosign_oidc_signing.py#L1): Verify retry logic: attempts 1 and 2 fail, attempt 3 succeeds, requesting a fresh token every time. (20 assertions)
  - [`test_exhausted_retries_aborts_and_fails_job`](file:///e:/JakeAI/backend/tests/test_cosign_oidc_signing.py#L1): Verify that when all 3 attempts fail, the script terminates with exit code 1 (fails the job). (7 assertions)
  - [`test_attestation_with_predicate_and_retries`](file:///e:/JakeAI/backend/tests/test_cosign_oidc_signing.py#L1): Verify attest subcommand passes predicate file, cyclonedx type, and fresh identity token. (9 assertions)

#### `CAT-019`: [`test_guardrails.py`](file:///e:/JakeAI/backend/tests/test_guardrails.py)
- **Test File Path**: `backend/tests/test_guardrails.py` (144 lines)
- **Subsystem**: `Security & Governance`
- **Test Level**: `Unit`
- **Purpose**: Unit tests for the Guardrails Layer (Input, RBAC, PII, and Output shields).
- **Dependencies / Fixtures**: None (Pure In-Memory)
- **CI Job Execution**: `unit-and-ai-tests (Full Suite Floor)`
- **Recommended Run Frequency**: `PR / Push (main)`
- **Duplicate / Overlap Classification**: `COMPLEMENTARY`
- **RIGHT Test Suite Coverage**: `R-AI-02 / R-AI-03`
- **Bruno Collection Coverage**: `Bruno/08 — Security & Negative (01-11)`
- **Architectural Disposition**: **`MOVE`** (Target Destination: `backend/tests/security/`)
- **Disposition Rationale & Evidence**: Valuable subsystem test. Needs reclassification into unit/, integration/, or security/.
- **Discovered Test Functions (6)**:
  - [`test_input_guardrail_benign_prompts`](file:///e:/JakeAI/backend/tests/test_guardrails.py#L1): Verify normal domain prompts pass input safety checks. (2 assertions)
  - [`test_input_guardrail_injection_detection`](file:///e:/JakeAI/backend/tests/test_guardrails.py#L1): Verify prompt injection and jailbreak attempts are blocked. (2 assertions)
  - [`test_rbac_guardrail_authorization`](file:///e:/JakeAI/backend/tests/test_guardrails.py#L1): Verify pre-tool RBAC enforcement allows authorized callers and rejects others. (10 assertions)
  - [`test_pii_masking`](file:///e:/JakeAI/backend/tests/test_guardrails.py#L1): Verify PII entities are masked with appropriate redaction tokens. (7 assertions)
  - [`test_output_guardrail_leakage_scrubbing`](file:///e:/JakeAI/backend/tests/test_guardrails.py#L1): Verify output guardrail scrubs system prompt leakage and foreign tenant data. (5 assertions)
  - [`test_guardrails_engine_facade`](file:///e:/JakeAI/backend/tests/test_guardrails.py#L1): Verify unified GuardrailsEngine methods. (4 assertions)

#### `CAT-075`: [`test_internal_mutual_auth.py`](file:///e:/JakeAI/backend/tests/contract/test_internal_mutual_auth.py)
- **Test File Path**: `backend/tests/contract/test_internal_mutual_auth.py` (291 lines)
- **Subsystem**: `Security & Governance`
- **Test Level**: `Contract`
- **Purpose**: Internal Mutual Auth Contract Test Suite (Invariant 4).
- **Dependencies / Fixtures**: None (Pure In-Memory)
- **CI Job Execution**: `Internal Mutual Auth Contract Gate`
- **Recommended Run Frequency**: `PR / Push (main)`
- **Duplicate / Overlap Classification**: `UNIQUE`
- **RIGHT Test Suite Coverage**: `R-ARCH-04`
- **Bruno Collection Coverage**: `Bruno/08 — Security & Negative (01-11)`
- **Architectural Disposition**: **`MOVE`** (Target Destination: `backend/tests/contract/`)
- **Disposition Rationale & Evidence**: API/Internal contract test. Move to contract/.
- **Discovered Test Functions (4)**:
  - [`test_perimeter_auth_rejects_missing_or_spoofed_headers`](file:///e:/JakeAI/backend/tests/contract/test_internal_mutual_auth.py#L1): Perimeter guard must reject requests missing headers or spoofing provenance. (4 assertions)
  - [`test_perimeter_auth_accepts_valid_static_secret`](file:///e:/JakeAI/backend/tests/contract/test_internal_mutual_auth.py#L1): Perimeter guard accepts X-Forwarded-By + matching X-Internal-Secret. (1 assertions)
  - [`test_perimeter_auth_hmac_replay_and_drift_window`](file:///e:/JakeAI/backend/tests/contract/test_internal_mutual_auth.py#L1): Perimeter guard enforces +/- 60s window and cryptographic verification. (4 assertions)
  - [`test_internal_resume_perimeter_http_contract`](file:///e:/JakeAI/backend/tests/contract/test_internal_mutual_auth.py#L1): HTTP Contract: /internal/v1/coding/resume enforces perimeter auth, idempotency, and error mapping. (14 assertions)

#### `CAT-116`: [`test_security_authentication.py`](file:///e:/JakeAI/backend/tests/security/test_security_authentication.py)
- **Test File Path**: `backend/tests/security/test_security_authentication.py` (320 lines)
- **Subsystem**: `Security & Governance`
- **Test Level**: `Security`
- **Purpose**: Dedicated runtime security regression test suite for JWT authentication, expiration, algorithm restrictions, wrong issuer/audience, JTI revocation, perimeter secrets, and billing HMAC.
- **Dependencies / Fixtures**: HTTP / ASGI, Mocks / Monkeypatch
- **CI Job Execution**: `Dedicated Runtime Security Regression Suite (TEST-05)`
- **Recommended Run Frequency**: `PR / Push (main)`
- **Duplicate / Overlap Classification**: `UNIQUE`
- **RIGHT Test Suite Coverage**: `R-LOGIC-02 / R-ARCH-04`
- **Bruno Collection Coverage**: `Bruno/08 — Security & Negative (01-11)`
- **Architectural Disposition**: **`CREATED`** (Target Destination: `backend/tests/security/`)
- **Disposition Rationale & Evidence**: New TEST-05 dedicated runtime authentication security regression suite.
- **Discovered Test Functions (30)**:
  - [`test_auth_missing_bearer_token`](file:///e:/JakeAI/backend/tests/security/test_security_authentication.py#L1): Missing bearer token returns 401.
  - [`test_auth_malformed_tokens`](file:///e:/JakeAI/backend/tests/security/test_security_authentication.py#L1): Malformed token formats return 401.
  - [`test_auth_expired_token`](file:///e:/JakeAI/backend/tests/security/test_security_authentication.py#L1): Expired token returns 401.
  - [`test_auth_wrong_issuer`](file:///e:/JakeAI/backend/tests/security/test_security_authentication.py#L1): Token from foreign issuer returns 401.
  - [`test_auth_wrong_audience`](file:///e:/JakeAI/backend/tests/security/test_security_authentication.py#L1): Token intended for other audience returns 401.
  - [`test_auth_invalid_signature`](file:///e:/JakeAI/backend/tests/security/test_security_authentication.py#L1): Token signed by attacker key returns 401.
  - [`test_auth_algorithm_none_rejected`](file:///e:/JakeAI/backend/tests/security/test_security_authentication.py#L1): Algorithm none tokens are rejected fail-closed.
  - [`test_auth_revoked_jti_rejected`](file:///e:/JakeAI/backend/tests/security/test_security_authentication.py#L1): Revoked JTI token cannot access endpoints.
  - [`test_auth_perimeter_secret_enforcement`](file:///e:/JakeAI/backend/tests/security/test_security_authentication.py#L1): Perimeter internal header requirements enforced.
  - [`test_auth_payos_billing_webhook_hmac`](file:///e:/JakeAI/backend/tests/security/test_security_authentication.py#L1): PayOS billing webhooks require valid HMAC signatures.

#### `CAT-117`: [`test_security_authorization.py`](file:///e:/JakeAI/backend/tests/security/test_security_authorization.py)
- **Test File Path**: `backend/tests/security/test_security_authorization.py` (300 lines)
- **Subsystem**: `Security & Governance`
- **Test Level**: `Security`
- **Purpose**: Dedicated runtime security regression test suite for RBAC permissions, role isolation, approval hijack/replay/TOCTOU resistance, and unmapped tools.
- **Dependencies / Fixtures**: HTTP / ASGI, Mocks / Monkeypatch
- **CI Job Execution**: `Dedicated Runtime Security Regression Suite (TEST-05)`
- **Recommended Run Frequency**: `PR / Push (main)`
- **Duplicate / Overlap Classification**: `UNIQUE`
- **RIGHT Test Suite Coverage**: `R-LOGIC-02 / R-AI-03`
- **Bruno Collection Coverage**: `Bruno/08 — Security & Negative (01-11)`
- **Architectural Disposition**: **`CREATED`** (Target Destination: `backend/tests/security/`)
- **Disposition Rationale & Evidence**: New TEST-05 dedicated runtime authorization security regression suite.
- **Discovered Test Functions (11)**:
  - [`test_authorization_insufficient_permission_for_tool`](file:///e:/JakeAI/backend/tests/security/test_security_authorization.py#L1): Caller lacking tool permission is rejected with 403.
  - [`test_authorization_role_mismatch`](file:///e:/JakeAI/backend/tests/security/test_security_authorization.py#L1): Caller with mismatched role cannot invoke restricted operations.
  - [`test_authorization_unmapped_tool_fails_closed`](file:///e:/JakeAI/backend/tests/security/test_security_authorization.py#L1): Unmapped tool invocations fail closed.
  - [`test_authorization_approval_cross_run_hijack`](file:///e:/JakeAI/backend/tests/security/test_security_authorization.py#L1): Approvals bound to Run A cannot be applied to Run B.
  - [`test_authorization_approval_replay_attack`](file:///e:/JakeAI/backend/tests/security/test_security_authorization.py#L1): Resolved approvals cannot be replayed.
  - [`test_authorization_approval_toctou_tampering`](file:///e:/JakeAI/backend/tests/security/test_security_authorization.py#L1): Argument tampering between approval and execution is rejected.

#### `CAT-118`: [`test_security_tenant_isolation.py`](file:///e:/JakeAI/backend/tests/security/test_security_tenant_isolation.py)
- **Test File Path**: `backend/tests/security/test_security_tenant_isolation.py` (460 lines)
- **Subsystem**: `Security & Governance`
- **Test Level**: `Security`
- **Purpose**: Multi-tenant boundary regression suite across Agent tasks/runs, LangGraph threads, exact/semantic caches, RAG indexes, BYOK keys, and uniform 404s.
- **Dependencies / Fixtures**: Redis, Qdrant, HTTP / ASGI, Mocks / Monkeypatch
- **CI Job Execution**: `Dedicated Runtime Security Regression Suite (TEST-05)`
- **Recommended Run Frequency**: `PR / Push (main)`
- **Duplicate / Overlap Classification**: `UNIQUE`
- **RIGHT Test Suite Coverage**: `R-AI-04 / R-LOGIC-02`
- **Bruno Collection Coverage**: `Bruno/08 — Security & Negative (01-11)`
- **Architectural Disposition**: **`CREATED`** (Target Destination: `backend/tests/security/`)
- **Disposition Rationale & Evidence**: New TEST-05 dedicated runtime tenant isolation regression suite.
- **Discovered Test Functions (10)**:
  - [`test_tenant_isolation_agent_tasks_and_runs`](file:///e:/JakeAI/backend/tests/security/test_security_tenant_isolation.py#L1): Foreign tenant cannot read, run, or cancel tasks.
  - [`test_tenant_isolation_langgraph_namespaced_threads`](file:///e:/JakeAI/backend/tests/security/test_security_tenant_isolation.py#L1): Workflow thread checkpoints strictly partitioned by tenant ID.
  - [`test_tenant_isolation_exact_and_semantic_cache`](file:///e:/JakeAI/backend/tests/security/test_security_tenant_isolation.py#L1): Tenant A cache responses never returned to Tenant B.
  - [`test_tenant_isolation_bm25_sparse_search`](file:///e:/JakeAI/backend/tests/security/test_security_tenant_isolation.py#L1): BM25 inverted index partitioned strictly per tenant.
  - [`test_tenant_isolation_context_envelope_builder`](file:///e:/JakeAI/backend/tests/security/test_security_tenant_isolation.py#L1): ContextEnvelopeBuilder drops foreign chunks and memory facts.
  - [`test_tenant_isolation_byok_keys_crud_and_masking`](file:///e:/JakeAI/backend/tests/security/test_security_tenant_isolation.py#L1): Foreign tenant cannot read, list, rotate, or delete BYOK keys.
  - [`test_tenant_isolation_resume_bridge_fails_closed`](file:///e:/JakeAI/backend/tests/security/test_security_tenant_isolation.py#L1): ResumeBridgeManager rejects cross-tenant resume calls with PermissionError.
  - [`test_tenant_isolation_uniform_404_timing_and_enumeration`](file:///e:/JakeAI/backend/tests/security/test_security_tenant_isolation.py#L1): Uniform 404 envelopes prevent resource existence enumeration.

#### `CAT-119`: [`test_security_llm_tool_safety.py`](file:///e:/JakeAI/backend/tests/security/test_security_llm_tool_safety.py)
- **Test File Path**: `backend/tests/security/test_security_llm_tool_safety.py` (520 lines)
- **Subsystem**: `Security & Governance`
- **Test Level**: `Security`
- **Purpose**: LLM & tool security suite for direct/indirect prompt injection, tool output contamination, dangerous shell blocking, path traversal, schema bounds, secret scrubbing, and error sanitization.
- **Dependencies / Fixtures**: None (Pure In-Memory)
- **CI Job Execution**: `Dedicated Runtime Security Regression Suite (TEST-05)`
- **Recommended Run Frequency**: `PR / Push (main)`
- **Duplicate / Overlap Classification**: `UNIQUE`
- **RIGHT Test Suite Coverage**: `R-AI-02 / R-AI-03`
- **Bruno Collection Coverage**: `Bruno/08 — Security & Negative (01-11)`
- **Architectural Disposition**: **`CREATED`** (Target Destination: `backend/tests/security/`)
- **Disposition Rationale & Evidence**: New TEST-05 dedicated runtime LLM & tool security regression suite.
- **Discovered Test Functions (12 / 40 items)**:
  - [`test_direct_prompt_injection_detection`](file:///e:/JakeAI/backend/tests/security/test_security_llm_tool_safety.py#L1): Direct prompt injections and jailbreaks intercepted.
  - [`test_obfuscated_base64_prompt_injection`](file:///e:/JakeAI/backend/tests/security/test_security_llm_tool_safety.py#L1): Base64 encoded payload inspection and rejection.
  - [`test_cross_lingual_vietnamese_prompt_injection`](file:///e:/JakeAI/backend/tests/security/test_security_llm_tool_safety.py#L1): Multi-lingual prompt injection vectors intercepted.
  - [`test_indirect_prompt_injection_in_grounding_claim`](file:///e:/JakeAI/backend/tests/security/test_security_llm_tool_safety.py#L1): Document-embedded injection claims marked UNSUPPORTED.
  - [`test_tool_output_injection_isolation`](file:///e:/JakeAI/backend/tests/security/test_security_llm_tool_safety.py#L1): CanonicalVerifier isolates contaminated tool outputs from context.
  - [`test_tool_policy_blocks_dangerous_commands`](file:///e:/JakeAI/backend/tests/security/test_security_llm_tool_safety.py#L1): ToolPolicyEngine blocks destructive/dangerous shell commands.
  - [`test_tool_policy_blocks_path_traversal_and_sensitive_files`](file:///e:/JakeAI/backend/tests/security/test_security_llm_tool_safety.py#L1): Directory traversal and sensitive file access blocked.
  - [`test_tool_policy_blocks_null_byte_injection`](file:///e:/JakeAI/backend/tests/security/test_security_llm_tool_safety.py#L1): Null-byte injection payloads rejected fail-closed.
  - [`test_tool_registry_schema_bounds_validation`](file:///e:/JakeAI/backend/tests/security/test_security_llm_tool_safety.py#L1): Parameter types, required fields, and bounds enforced.
  - [`test_output_scrubber_redacts_credentials_and_system_prompts`](file:///e:/JakeAI/backend/tests/security/test_security_llm_tool_safety.py#L1): Output scrubber redacts system prompts, JWTs, and API keys.
  - [`test_normalize_provider_error_categories`](file:///e:/JakeAI/backend/tests/security/test_security_llm_tool_safety.py#L1): Provider error normalization into typed hierarchies.
  - [`test_provider_error_handler_zero_credential_leakage`](file:///e:/JakeAI/backend/tests/security/test_security_llm_tool_safety.py#L1): Global exception handler outputs safe errors with zero credential leak.

#### `CAT-120`: [`test_security_fail_closed.py`](file:///e:/JakeAI/backend/tests/security/test_security_fail_closed.py)
- **Test File Path**: `backend/tests/security/test_security_fail_closed.py` (430 lines)
- **Subsystem**: `Security & Governance`
- **Test Level**: `Security`
- **Purpose**: Fail-closed invariants suite for verifier variance, foreign tenant breaches, unapproved tools, missing BYOK credentials, budget overflow, and empty auth headers.
- **Dependencies / Fixtures**: HTTP / ASGI, Mocks / Monkeypatch
- **CI Job Execution**: `Dedicated Runtime Security Regression Suite (TEST-05)`
- **Recommended Run Frequency**: `PR / Push (main)`
- **Duplicate / Overlap Classification**: `UNIQUE`
- **RIGHT Test Suite Coverage**: `R-LOGIC-00 / R-LOGIC-02`
- **Bruno Collection Coverage**: `Bruno/08 — Security & Negative (01-11)`
- **Architectural Disposition**: **`CREATED`** (Target Destination: `backend/tests/security/`)
- **Disposition Rationale & Evidence**: New TEST-05 dedicated fail-closed invariants regression suite.
- **Discovered Test Functions (14)**:
  - [`test_fail_closed_verifier_rejects_mathematical_variance`](file:///e:/JakeAI/backend/tests/security/test_security_fail_closed.py#L1): Verifier rejects execution result on financial calculation variance.
  - [`test_fail_closed_verifier_rejects_foreign_tenant_breach`](file:///e:/JakeAI/backend/tests/security/test_security_fail_closed.py#L1): Verifier terminates on cross-tenant tool call or chunk breach.
  - [`test_fail_closed_verifier_rejects_hallucination_without_evidence`](file:///e:/JakeAI/backend/tests/security/test_security_fail_closed.py#L1): Verifier rejects claims when grounding evidence is absent.
  - [`test_fail_closed_context_envelope_drops_foreign_tenant_data`](file:///e:/JakeAI/backend/tests/security/test_security_fail_closed.py#L1): Context envelope purges all foreign tenant data.
  - [`test_fail_closed_resume_bridge_rejects_cross_tenant_state`](file:///e:/JakeAI/backend/tests/security/test_security_fail_closed.py#L1): Cross-tenant resume rejected with PermissionError.
  - [`test_fail_closed_agent_task_manager_rejects_cross_tenant`](file:///e:/JakeAI/backend/tests/security/test_security_fail_closed.py#L1): Task inspection across tenant boundaries rejected.
  - [`test_fail_closed_unmapped_permission_rejects_execution`](file:///e:/JakeAI/backend/tests/security/test_security_fail_closed.py#L1): Unmapped permissions fail closed.
  - [`test_fail_closed_empty_context_rejects_privileged_tool`](file:///e:/JakeAI/backend/tests/security/test_security_fail_closed.py#L1): Empty context rejected for privileged tools.
  - [`test_fail_closed_dangerous_tool_demands_human_approval`](file:///e:/JakeAI/backend/tests/security/test_security_fail_closed.py#L1): Dangerous tools require explicit human approval.
  - [`test_fail_closed_missing_byok_blocks_inference_without_mocking`](file:///e:/JakeAI/backend/tests/security/test_security_fail_closed.py#L1): Missing BYOK keys block inference without mocking.
  - [`test_fail_closed_context_envelope_raises_budget_exceeded`](file:///e:/JakeAI/backend/tests/security/test_security_fail_closed.py#L1): Context envelope budget overflow raises error fail-closed.
  - [`test_fail_closed_bpe_tokenizer_enforce_budget_raises`](file:///e:/JakeAI/backend/tests/security/test_security_fail_closed.py#L1): Tokenizer budget exceed raises error fail-closed.
  - [`test_fail_closed_tool_registry_rejects_unknown_tool`](file:///e:/JakeAI/backend/tests/security/test_security_fail_closed.py#L1): Unregistered tool invocations fail closed.
  - [`test_fail_closed_http_endpoints_reject_empty_authorization`](file:///e:/JakeAI/backend/tests/security/test_security_fail_closed.py#L1): Endpoints reject empty or corrupt auth headers.

### 3.13 Subsystem: Token Optimization & Caching (5 Files)
#### `CAT-067`: [`test_semantic_cache.py`](file:///e:/JakeAI/backend/tests/test_semantic_cache.py)
- **Test File Path**: `backend/tests/test_semantic_cache.py` (109 lines)
- **Subsystem**: `Token Optimization & Caching`
- **Test Level**: `Unit`
- **Purpose**: Unit tests for Multi-Tier Semantic Cache (Exact & Vector Cosine Similarity).
- **Dependencies / Fixtures**: None (Pure In-Memory)
- **CI Job Execution**: `unit-and-ai-tests (Full Suite Floor)`
- **Recommended Run Frequency**: `PR / Push (main)`
- **Duplicate / Overlap Classification**: `LEGACY`
- **RIGHT Test Suite Coverage**: `R-FUNC-03 / R-AI-02`
- **Bruno Collection Coverage**: `NONE`
- **Architectural Disposition**: **`REMOVE`** (Target Destination: `backend/tests/unit/`)
- **Disposition Rationale & Evidence**: Uses obsolete 128-d mock vectors and mock Redis. Completely superseded by test_semantic_cache_real.py (384-d FastEmbed) and test_r_func_03_cache_behavior.py.
- **Discovered Test Functions (4)**:
  - [`test_exact_match_cache_hit_and_miss`](file:///e:/JakeAI/backend/tests/test_semantic_cache.py#L1): Verify exact match caching returns identical payload on hit and None on miss. (9 assertions)
  - [`test_semantic_vector_cache_hit_and_tenant_isolation`](file:///e:/JakeAI/backend/tests/test_semantic_cache.py#L1): Verify semantic similarity matches close queries and enforces tenant boundaries. (5 assertions)
  - [`test_cache_invalidation`](file:///e:/JakeAI/backend/tests/test_semantic_cache.py#L1): Verify cache invalidation by tenant and globally. (4 assertions)
  - [`test_embedding_and_cosine_similarity`](file:///e:/JakeAI/backend/tests/test_semantic_cache.py#L1): Test vector normalization and cosine similarity computation. (6 assertions)

#### `CAT-070`: [`test_two_zone_compiler.py`](file:///e:/JakeAI/backend/tests/test_two_zone_compiler.py)
- **Test File Path**: `backend/tests/test_two_zone_compiler.py` (231 lines)
- **Subsystem**: `Token Optimization & Caching`
- **Test Level**: `Unit`
- **Purpose**: Unit tests for TwoZonePromptCompiler (Tier 5: Provider Prompt Caching).
- **Dependencies / Fixtures**: None (Pure In-Memory)
- **CI Job Execution**: `unit-and-ai-tests (Full Suite Floor)`
- **Recommended Run Frequency**: `PR / Push (main)`
- **Duplicate / Overlap Classification**: `COMPLEMENTARY`
- **RIGHT Test Suite Coverage**: `R-FUNC-03 / R-AI-02`
- **Bruno Collection Coverage**: `NONE`
- **Architectural Disposition**: **`MOVE`** (Target Destination: `backend/tests/unit/`)
- **Disposition Rationale & Evidence**: Valuable subsystem test. Needs reclassification into unit/, integration/, or security/.
- **Discovered Test Functions (7)**:
  - [`test_two_zone_compiler_separation`](file:///e:/JakeAI/backend/tests/test_two_zone_compiler.py#L1): Verifies that static instructions and dynamic queries are cleanly partitioned. (10 assertions)
  - [`test_static_prefix_determinism`](file:///e:/JakeAI/backend/tests/test_two_zone_compiler.py#L1): Verifies byte-identical SHA-256 hash regardless of tool declaration order or dict keys. (2 assertions)
  - [`test_volatile_data_detection_and_isolation`](file:///e:/JakeAI/backend/tests/test_two_zone_compiler.py#L1): Verifies that volatile identifiers (UUIDs, timestamps) in Zone 1 are flagged or rejected. (3 assertions)
  - [`test_prefix_hash_invalidation_on_content_change`](file:///e:/JakeAI/backend/tests/test_two_zone_compiler.py#L1): Verifies that changes in static prompt, tool schema, or version cleanly update the hash. (3 assertions)
  - [`test_partition_messages`](file:///e:/JakeAI/backend/tests/test_two_zone_compiler.py#L1): Verifies partitioning of standard chat messages into static prefix and dynamic suffix. (4 assertions)
  - [`test_cache_eligibility_threshold`](file:///e:/JakeAI/backend/tests/test_two_zone_compiler.py#L1): Verifies cache eligibility threshold based on token count. (2 assertions)
  - [`test_tenant_isolation_prevents_cross_tenant_cache_leak`](file:///e:/JakeAI/backend/tests/test_two_zone_compiler.py#L1): Verifies that static prompts for different tenants produce isolated prefix hashes. (3 assertions)

#### `CAT-083`: [`test_prompt_cache_benchmark.py`](file:///e:/JakeAI/backend/tests/evals/test_prompt_cache_benchmark.py)
- **Test File Path**: `backend/tests/evals/test_prompt_cache_benchmark.py` (236 lines)
- **Subsystem**: `Token Optimization & Caching`
- **Test Level**: `AI Eval / Benchmark`
- **Purpose**: Empirical Provider Prompt Cache Benchmark Suite (Tier 5).
- **Dependencies / Fixtures**: None (Pure In-Memory)
- **CI Job Execution**: `unit-and-ai-tests (Full Suite Floor)`
- **Recommended Run Frequency**: `PR / Push (main)`
- **Duplicate / Overlap Classification**: `UNIQUE`
- **RIGHT Test Suite Coverage**: `R-FUNC-03 / R-AI-02`
- **Bruno Collection Coverage**: `NONE`
- **Architectural Disposition**: **`MOVE`** (Target Destination: `backend/tests/evals/`)
- **Disposition Rationale & Evidence**: AI evaluation or empirical token benchmark suite. Move to evals/.
- **Discovered Test Functions (1)**:
  - [`test_empirical_prompt_cache_benchmark`](file:///e:/JakeAI/backend/tests/evals/test_prompt_cache_benchmark.py#L1): Run empirical comparison between Scenario A (unstable) and Scenario B (Two-Zone). (5 assertions)

#### `CAT-089`: [`test_bpe_tokenizer.py`](file:///e:/JakeAI/backend/tests/unit/test_bpe_tokenizer.py)
- **Test File Path**: `backend/tests/unit/test_bpe_tokenizer.py` (166 lines)
- **Subsystem**: `Token Optimization & Caching`
- **Test Level**: `Unit`
- **Purpose**: Unit tests for Tier 7 BPE Tokenizer Engine and Token Budgeting.
- **Dependencies / Fixtures**: Mocks / Monkeypatch
- **CI Job Execution**: `unit-and-ai-tests (Full Suite Floor)`
- **Recommended Run Frequency**: `PR / Push (main)`
- **Duplicate / Overlap Classification**: `COMPLEMENTARY`
- **RIGHT Test Suite Coverage**: `NONE`
- **Bruno Collection Coverage**: `NONE`
- **Architectural Disposition**: **`KEEP`** (Target Destination: `backend/tests/unit/`)
- **Disposition Rationale & Evidence**: Already in unit/ directory. High-value isolated unit test.
- **Discovered Test Functions (7)**:
  - [`test_bpe_tokenizer_initialization`](file:///e:/JakeAI/backend/tests/unit/test_bpe_tokenizer.py#L1): Verify standard and invalid BPE tokenizer initialization. (4 assertions)
  - [`test_bpe_tokenizer_encode`](file:///e:/JakeAI/backend/tests/unit/test_bpe_tokenizer.py#L1): Verify token encoding for empty string, default model, and specific models. (5 assertions)
  - [`test_bpe_tokenizer_encode_fallback_on_exception`](file:///e:/JakeAI/backend/tests/unit/test_bpe_tokenizer.py#L1): Verify encode gracefully falls back to regex token estimate when an exception occurs. (4 assertions)
  - [`test_bpe_tokenizer_count_tokens`](file:///e:/JakeAI/backend/tests/unit/test_bpe_tokenizer.py#L1): Verify exact and fallback token counting. (5 assertions)
  - [`test_bpe_tokenizer_measure_optimization`](file:///e:/JakeAI/backend/tests/unit/test_bpe_tokenizer.py#L1): Verify Tier 6 context optimization measurement and token metrics generation. (11 assertions)
  - [`test_bpe_tokenizer_enforce_context_budget`](file:///e:/JakeAI/backend/tests/unit/test_bpe_tokenizer.py#L1): Verify Section 9 context budget enforcement with and without exception raising. (4 assertions)
  - [`test_bpe_tokenizer_singleton`](file:///e:/JakeAI/backend/tests/unit/test_bpe_tokenizer.py#L1): Verify get_bpe_tokenizer returns a singleton instance. (2 assertions)

#### `CAT-090`: [`test_cache_identity.py`](file:///e:/JakeAI/backend/tests/unit/test_cache_identity.py)
- **Test File Path**: `backend/tests/unit/test_cache_identity.py` (910 lines)
- **Subsystem**: `Token Optimization & Caching`
- **Test Level**: `Unit`
- **Purpose**: REPAIR-00 — CACHE-01: Exact Cache Identity Regression Tests.
- **Dependencies / Fixtures**: Mocks / Monkeypatch
- **CI Job Execution**: `unit-and-ai-tests (Full Suite Floor)`
- **Recommended Run Frequency**: `PR / Push (main)`
- **Duplicate / Overlap Classification**: `COMPLEMENTARY`
- **RIGHT Test Suite Coverage**: `R-FUNC-03 / R-AI-02`
- **Bruno Collection Coverage**: `NONE`
- **Architectural Disposition**: **`KEEP`** (Target Destination: `backend/tests/unit/`)
- **Disposition Rationale & Evidence**: Already in unit/ directory. High-value isolated unit test.
- **Discovered Test Functions (34)**:
  - [`TestComputeCacheIdentity::test_same_request_same_identity`](file:///e:/JakeAI/backend/tests/unit/test_cache_identity.py#L1): Identical requests MUST produce identical cache identities. (2 assertions)
  - [`TestComputeCacheIdentity::test_different_model_different_identity`](file:///e:/JakeAI/backend/tests/unit/test_cache_identity.py#L1): Different model => different cache identity. (1 assertions)
  - [`TestComputeCacheIdentity::test_different_provider_different_identity`](file:///e:/JakeAI/backend/tests/unit/test_cache_identity.py#L1): Different provider => different cache identity. (1 assertions)
  - [`TestComputeCacheIdentity::test_different_system_prompt_different_identity`](file:///e:/JakeAI/backend/tests/unit/test_cache_identity.py#L1): Different system instructions => different cache identity. (1 assertions)
  - [`TestComputeCacheIdentity::test_different_conversation_history_different_identity`](file:///e:/JakeAI/backend/tests/unit/test_cache_identity.py#L1): Different message history => different cache identity. (1 assertions)
  - [`TestComputeCacheIdentity::test_different_message_order_different_identity`](file:///e:/JakeAI/backend/tests/unit/test_cache_identity.py#L1): Same messages in different order => different cache identity. (1 assertions)
  - [`TestComputeCacheIdentity::test_different_tools_different_identity`](file:///e:/JakeAI/backend/tests/unit/test_cache_identity.py#L1): Different tool definitions => different cache identity. (1 assertions)
  - [`TestComputeCacheIdentity::test_different_response_format_different_identity`](file:///e:/JakeAI/backend/tests/unit/test_cache_identity.py#L1): Different response format => different cache identity. (3 assertions)
  - [`TestComputeCacheIdentity::test_response_format_key_order_invariance`](file:///e:/JakeAI/backend/tests/unit/test_cache_identity.py#L1): Response format dict with different key ordering => same cache identity. (1 assertions)
  - [`TestComputeCacheIdentity::test_different_generation_params_different_identity`](file:///e:/JakeAI/backend/tests/unit/test_cache_identity.py#L1): Different generation parameters => different cache identity. (1 assertions)
  - [`TestComputeCacheIdentity::test_different_max_tokens_different_identity`](file:///e:/JakeAI/backend/tests/unit/test_cache_identity.py#L1): Different max_tokens => different cache identity. (1 assertions)
  - [`TestComputeCacheIdentity::test_different_tenant_different_identity`](file:///e:/JakeAI/backend/tests/unit/test_cache_identity.py#L1): Different tenant => different cache identity. (1 assertions)
  - [`TestComputeCacheIdentity::test_different_version_different_identity`](file:///e:/JakeAI/backend/tests/unit/test_cache_identity.py#L1): Different cache version => different cache identity. (1 assertions)
  - [`TestComputeCacheIdentity::test_whitespace_normalization`](file:///e:/JakeAI/backend/tests/unit/test_cache_identity.py#L1): Whitespace differences should not affect cache identity. (1 assertions)
  - [`TestComputeCacheIdentity::test_tool_key_order_invariance`](file:///e:/JakeAI/backend/tests/unit/test_cache_identity.py#L1): Tool definitions with different key ordering => same cache identity. (1 assertions)
  - [`TestComputeCacheIdentity::test_empty_messages_vs_no_messages`](file:///e:/JakeAI/backend/tests/unit/test_cache_identity.py#L1): Empty messages list vs None => different identity (no ambiguity). (2 assertions)
  - [`TestComputeCacheIdentity::test_same_last_message_different_system_prompt_no_collision`](file:///e:/JakeAI/backend/tests/unit/test_cache_identity.py#L1): Core defect scenario: same user message, different system prompt. (1 assertions)
  - [`TestComputeCacheIdentity::test_same_last_message_different_model_no_collision`](file:///e:/JakeAI/backend/tests/unit/test_cache_identity.py#L1): Core defect scenario: same user message, different model. (1 assertions)
  - [`TestComputeCacheIdentity::test_user_content_casing_preserved`](file:///e:/JakeAI/backend/tests/unit/test_cache_identity.py#L1): COST-02: Do NOT lowercase arbitrary user content. Case differences must not collide. (1 assertions)
  - [`TestComputeCacheIdentity::test_code_indentation_preserved`](file:///e:/JakeAI/backend/tests/unit/test_cache_identity.py#L1): COST-02: Do NOT collapse semantically meaningful whitespace. Code indentation must be preserved. (1 assertions)
  - [`TestComputeCacheIdentity::test_tool_call_fields_in_messages`](file:///e:/JakeAI/backend/tests/unit/test_cache_identity.py#L1): COST-02: Message serialization MUST include name, tool_call_id, and tool_calls. (3 assertions)
  - [`TestComputeCacheIdentity::test_identical_code_exact_match`](file:///e:/JakeAI/backend/tests/unit/test_cache_identity.py#L1): COST-02: Identical requests with formatted code produce identical identity. (1 assertions)
  - [`test_cache_miss_different_model`](file:///e:/JakeAI/backend/tests/unit/test_cache_identity.py#L1): Cache set with model A, get with model B => miss (no collision). (1 assertions)
  - [`test_cache_miss_different_provider`](file:///e:/JakeAI/backend/tests/unit/test_cache_identity.py#L1): Cache set with provider A, get with provider B => miss. (1 assertions)
  - [`test_cache_miss_different_system_prompt`](file:///e:/JakeAI/backend/tests/unit/test_cache_identity.py#L1): Cache set with system prompt A, get with system prompt B => miss. (1 assertions)
  - [`test_cache_miss_different_history`](file:///e:/JakeAI/backend/tests/unit/test_cache_identity.py#L1): Cache set with history A, get with different history => miss. (1 assertions)
  - [`test_cache_miss_different_tools`](file:///e:/JakeAI/backend/tests/unit/test_cache_identity.py#L1): Cache set with tools, get without tools => miss (and vice versa). (5 assertions)
  - [`test_cache_miss_different_response_format`](file:///e:/JakeAI/backend/tests/unit/test_cache_identity.py#L1): Cache set with response_format=json, get without => miss (and vice versa). (5 assertions)
  - [`test_cache_miss_different_generation_params`](file:///e:/JakeAI/backend/tests/unit/test_cache_identity.py#L1): Cache set with temp=0.7, get with temp=0.0 => miss. (1 assertions)
  - [`test_cache_hit_identical_request`](file:///e:/JakeAI/backend/tests/unit/test_cache_identity.py#L1): Identical requests => cache hit. (3 assertions)
  - [`test_cache_backward_compatibility`](file:///e:/JakeAI/backend/tests/unit/test_cache_identity.py#L1): Legacy callers (no messages/system_instructions) still work via synthesis. (2 assertions)
  - [`test_cache_parameters_dict_normalization_tools_and_rf`](file:///e:/JakeAI/backend/tests/unit/test_cache_identity.py#L1): Passing tools and response_format inside parameters dict derives identical cache identity. (7 assertions)
  - [`test_legacy_compute_hash_still_works`](file:///e:/JakeAI/backend/tests/unit/test_cache_identity.py#L1): The legacy _compute_hash function still produces deterministic output. (3 assertions)
  - [`test_gateway_exact_cache_isolation_across_dimensions`](file:///e:/JakeAI/backend/tests/unit/test_cache_identity.py#L1): End-to-end gateway proxy test verifying exact-cache isolation across dimensions. (0 assertions)

### 3.14 Subsystem: End-to-End Business Workflows (CAT-124)

#### `CAT-124`: [`test_e2e_business_workflows.py`](file:///e:/JakeAI/backend/tests/e2e/test_e2e_business_workflows.py)
- **Logical ID**: `E2E-003`
- **Legacy ID**: `CAT-124`
- **Subsystem**: Business Workflows / Platform Integration
- **Test Level**: E2E (Asynchronous ASGI In-Memory & Managed Pipeline)
- **Purpose**: Authoritative end-to-end verification of 7 core JakeAI business workflows spanning multi-tier architecture, security PEP, agent DAG execution, RAG pipeline, BYOK vault, failover resilience, and human-in-the-loop approvals.
- **Dependencies**: HTTP / ASGI, In-Memory Redis, Qdrant Mock/In-Memory, Upstream LLM Doubles
- **CI Job**: `Critical End-to-End Business Workflow Gate (TEST-07 / E2E-003)`
- **Run Frequency**: PR / Push (main)
- **Test Functions / Methods (9 functions / 9 items)**:
  - [`test_e2e_workflow_01_auth_to_chat_lifecycle`](file:///e:/JakeAI/backend/tests/e2e/test_e2e_business_workflows.py#L130): Workflow 1: Authentication -> authenticated request -> chat -> response schema -> telemetry/accounting & exact cache hit side effect.
  - [`test_e2e_workflow_02_auth_to_agent_task_lifecycle`](file:///e:/JakeAI/backend/tests/e2e/test_e2e_business_workflows.py#L235): Workflow 2: Authentication -> create task -> cross-tenant isolation (403/404) -> execution -> terminal state.
  - [`test_e2e_workflow_03_agent_tool_selection_execution_verification`](file:///e:/JakeAI/backend/tests/e2e/test_e2e_business_workflows.py#L305): Workflow 3: Task -> tool selection -> tool execution -> verifier pass -> result.
  - [`test_e2e_workflow_04_rag_ingest_retrieval_grounding_abstention`](file:///e:/JakeAI/backend/tests/e2e/test_e2e_business_workflows.py#L394): Workflow 4: Ingest document -> hybrid retrieval -> context selection -> grounded generation -> citation & epistemic abstention.
  - [`test_e2e_workflow_05_byok_provider_credential_accounting`](file:///e:/JakeAI/backend/tests/e2e/test_e2e_business_workflows.py#L509): Workflow 5: Credential configuration -> AES-256-GCM vault -> provider selection -> request dispatch -> FinOps accounting.
  - [`test_e2e_workflow_06_failure_recovery_failover_truthfulness`](file:///e:/JakeAI/backend/tests/e2e/test_e2e_business_workflows.py#L609): Workflow 6: Request -> dependency failure -> failover recovery -> non-retryable truthful failure state.
  - [`test_e2e_workflow_07_human_in_the_loop_approval_resume_terminal`](file:///e:/JakeAI/backend/tests/e2e/test_e2e_business_workflows.py#L683): Workflow 7: Task -> approval required -> approval decision -> resume -> terminal state.
  - [`test_e2e_workflow_07b_human_in_the_loop_approval_rejection`](file:///e:/JakeAI/backend/tests/e2e/test_e2e_business_workflows.py#L767): Workflow 7b: Task -> approval required -> operator rejection -> terminal state REJECTED.
  - [`test_e2e_workflow_live_external_provider_call`](file:///e:/JakeAI/backend/tests/e2e/test_e2e_business_workflows.py#L838): Optional Live External Integration Workflow (gated by LIVE_EXTERNAL_TESTS=1).

---

## 4. Automated API Contract & Bruno Collection Architecture Relationship

### 4.1 Design Philosophy: Layered Verification Strategy
JakeAI implements a strict two-tier strategy for API verification, clearly partitioning server-side headless regression testing from client-side interactive/staging exploration.

```
┌────────────────────────────────────────────────────────────────────────┐
│                        FastAPI Application (ASGI)                     │
│           (Routes, OpenAPI 3.1.0 Spec, Pydantic Models, PEP)           │
└──────────────────────────────────┬─────────────────────────────────────┘
                                   │
         ┌─────────────────────────┴─────────────────────────┐
         ▼                                                   ▼
┌───────────────────────────────────┐   ┌───────────────────────────────────┐
│     Pytest API Contract Layer     │   │      Bruno Collection Suite       │
│  (`tests/contract/`)              │   │  (`bruno/JakeAI-Platform/`)       │
├───────────────────────────────────┤   ├───────────────────────────────────┤
│ • Headless ASGI in-memory client  │   │ • Live HTTP client (external CLI) │
│ • Runs in CI on every push / PR   │   │ • Manual & staging exploration    │
│ • Deterministic & isolated        │   │ • Stateful operator walkthroughs  │
│ • 0 external network dependencies │   │ • Environment presets (dev/stg)   │
│ • Zero schema drift gate against  │   │ • Real external service latency   │
│   committed `backend/openapi.json`│   │ • Multi-turn human debugging      │
│ • 51 operations & 10 error codes  │   │                                   │
└───────────────────────────────────┘   └───────────────────────────────────┘
```

### 4.2 Pytest Contract & HTTP Suite (`tests/contract/`)
The Pytest contract suite (`test_api_contract.py`, `test_api_negative_contracts.py`, `test_api_http_workflows.py`) acts as the authoritative, automated server-side verification layer:
- **Execution Environment**: In-process ASGI memory transport (`httpx.AsyncClient(transport=ASGITransport(app=app))`).
- **Speed & Isolation**: All 164 contract tests execute in under 15 seconds without binding TCP ports, invoking live upstream LLMs, or requiring live Redis/Qdrant servers.
- **Zero Schema Drift Invariant**: Automatically compares the live FastAPI schema (`app.openapi()`) against the version-controlled `backend/openapi.json`. Fails CI immediately if any field, type, status code, or schema diverges by even one byte.
- **Comprehensive Exhaustive Audit**:
  - Parameterized verification of all 51 operations across 47 paths.
  - Path template parameters matching declared route signatures.
  - Authentication boundary enforcement (41 Bearer JWT protected vs 10 public/perimeter/webhook endpoints).
  - Negative contracts covering all 10 legitimate HTTP status codes (`400`, `401`, `403`, `404`, `409`, `413`, `422`, `429`, `500`, `503`) at the ASGI boundary with exact error envelope assertions.
  - 5 representative end-to-end multi-request workflows verifying asynchronous SSE streams, RAG indexing, BYOK encryption, AI Gateway & FinOps, and Human-in-the-Loop resume bridges.

### 4.3 Bruno Collection & CLI Automation (`Bruno/` — TEST-08)
The Bruno collection serves as the authoritative, automated HTTP and E2E regression testing layer driven by `@usebruno/cli`:
- **Execution Environment**: Automated CLI runner (`python scripts/run_bruno_tests.py`) or Bruno CLI (`bru run`), issuing real HTTP/1.1 and SSE network requests over TCP to a live JakeAI server (`http://localhost:8000`).
- **Profiles Supported**:
  - `smoke`: Fastest confidence check (<10 seconds, PR confidence).
  - `critical-e2e`: Core business workflows across subsystems (PR gate).
  - `full`: Complete 85-request collection across all 12 folders (Main/Release gate).
  - `live-release`: Full collection requiring live FinnApiGo and provider keys.
- **Collection Layout**: 12 structured folders (00-Setup, 01-Authentication & Tenant, 02-Chat & Gateway, 03-Agent, 04-RAG, 05-BYOK & Providers, 06-Cache, 07-FinOps & Billing, 08-Security & Negative, 09-Failure & Recovery, 10-Cross System E2E, 99-Final Smoke).
- **External Dependency Governance**: Explicitly probes FinnApiGo; reports missing dependencies as `BLOCKED (Dependency Governance)` without false PASS, and verifies all 83 self-contained JakeAI requests.
- **Reporting**: Generates machine-readable reports in `backend/reports/bruno/` (`bruno-results.json`, `bruno-junit.xml`, `bruno-summary.md`) and populates GitHub Actions `$GITHUB_STEP_SUMMARY`.

### 4.4 Rationale: Complementary Testing Architecture
JakeAI employs a layered, non-overlapping testing architecture:
1. **Pytest Unit & Integration**: Tests deep Python logic, state machine transitions, math invariants, and mock error injections in in-process memory.
2. **Pytest Contract**: Verifies OpenAPI schema drift and route invariants via ASGI transport.
3. **Pytest AI Evals**: Measures retrieval precision, citation fidelity, and token optimization benchmarks against golden datasets.
4. **Bruno CLI Automation**: Exercises real HTTP network transport, actual serialization/deserialization, live header propagation, SSE streaming frame delivery, and end-to-end multi-tenant workflows.

---

## 5. Bruno CLI Automated Test Master Table (TEST-08)

| FOLDER | NAME | TOTAL REQUESTS | TARGET SUBSYSTEM | AUTOMATION SUITE | DEPENDENCY POLICY |
|---|---|:---:|---|---|---|
| `00` | Setup & Environment | 3 | Health, Readiness & Core Banking | `smoke`, `critical-e2e`, `full` | 01-02 Local / 03 FinnApiGo (BLOCKED if offline) |
| `01` | Authentication & Tenant | 8 | JWT Auth, Claims & Tenant Isolation | `critical-e2e`, `full` | 01 FinnApiGo / 02-08 Local Dev Tokens |
| `02` | Chat & Gateway | 7 | OpenAI Proxy & SSE Streaming | `smoke`, `critical-e2e`, `full` | Pure Local |
| `03` | Agent | 10 | Task DAG, Run Lifecycle & Approvals | `smoke`, `critical-e2e`, `full` | Pure Local |
| `04` | RAG | 7 | Ingestion, Hybrid Search & Grounding | `smoke`, `critical-e2e`, `full` | Pure Local (Qdrant & FastEmbed) |
| `05` | BYOK & Providers | 7 | AES Vault & Key Lifecycle | `critical-e2e`, `full` | Pure Local |
| `06` | Cache | 6 | Tier 1 Redis & Parameter Isolation | `critical-e2e`, `full` | Pure Local (R-LOGIC-04 Fallback preserved) |
| `07` | FinOps & Billing | 6 | Token Ledger, Budget & Reconciliation | `critical-e2e`, `full` | Pure Local |
| `08` | Security & Negative | 11 | Injection, Fuzzing, Bounds & Negative | `full` | Pure Local |
| `09` | Failure & Recovery | 9 | Timeouts, Retries, Failover & Recovery | `full` | Pure Local |
| `10` | Cross System E2E | 8 | Complete Multi-Hop Business Workflows | `critical-e2e`, `full` | Pure Local |
| `99` | Final Smoke | 3 | Production, Security & E2E Smoke | `smoke`, `critical-e2e`, `full` | Pure Local |
| **TOTAL** | **12 Folders** | **85** | **Complete Platform Surface** | **All Suites** | **83 Local PASS / 2 Dependency BLOCKED** |

---

## 6. DevSecOps CI Security Hardening (Gitleaks Least-Privilege Scanner)

### 6.1 Security Audit Baseline
- **Workflow**: `Continuous Integration / DevSecOps - Secret & Key Leak Detection` (`secret-scanning` in `.github/workflows/ci.yml`)
- **Action**: `gitleaks/gitleaks-action@v3`
- **Audit Date**: 2026-09-16
- **Status**: **VERIFIED GREEN & LEAST PRIVILEGE ENFORCED**

### 6.2 Incident & Resolution Summary
- **Current Failure**: Job failed on PR events with `HttpError: Resource not accessible by integration (403)` when `gitleaks-action` attempted to write PR comments using a read-only `GITHUB_TOKEN`.
- **Root Cause**: `gitleaks-action@v3` enables PR comments by default (`GITLEAKS_ENABLE_COMMENTS: true`), which invokes GitHub REST API comment endpoints when leaks are found (`exitCode == 2`). Initial Bruno environment files contained static dev JWTs that triggered detection.
- **Least-Privilege Remediation**:
  1. **Strict Job-Level Permissions**: Configured `permissions: contents: read`. Write permissions (`pull-requests: write`, `contents: write`) were explicitly rejected as PR commenting is purely cosmetic and granting write tokens violates least-privilege security for untrusted PRs and forks.
  2. **Disabled PR Comments**: Set `GITLEAKS_ENABLE_COMMENTS: "false"`.
  3. **Preserved DevSecOps Gate**: Set `GITLEAKS_ENABLE_SUMMARY: "true"` and `GITLEAKS_ENABLE_UPLOAD_ARTIFACT: "true"`. Failures continue to block CI (`exitCode == 1`), write full markdown summaries to `$GITHUB_STEP_SUMMARY`, and upload SARIF reports.
  4. **Sanitized Environment Fixtures**: `Bruno/environments/Local.bru` and `bruno-collection-environments.json` were sanitized to empty placeholders.
  5. **Dynamic Runtime Dev Tokens**: `scripts/run_bruno_tests.py` mints valid HMAC-SHA256 test tokens at execution time using standard library `hmac`/`hashlib`, passing them via Bruno CLI `--env-var` flags without ever writing secrets to disk.
- **Empirical Regression Verification**:
  - **CASE A (Clean Repository)**: `gitleaks detect --log-opts="origin/main..HEAD" --config=.gitleaks.toml -v` -> 0 leaks found, Exit 0 (PASS).
  - **CASE B (Controlled Synthetic Secret)**: Injected `FAKE_API_KEY` into temporary commit -> 1 leak detected (`RuleID: generic-api-key`), Exit 1 (FAIL). Confirmed scanner remains fully operational with comments disabled.


