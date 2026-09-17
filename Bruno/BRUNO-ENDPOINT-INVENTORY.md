# BRUNO-ENDPOINT-INVENTORY — JakeAI Authoritative API Endpoint Inventory

**Source of Truth**: Current FastAPI Application (`app.main:app`) + OpenAPI 3.1.0 (`backend/openapi.json`)  
**Total Unique HTTP Paths**: 47  
**Total Unique Operations**: 51  
**Verification Date**: September 17, 2026  

---

## 1. Inventory Summary by Subsystem & Category

| Subsystem / Domain | Route Prefix | Operations | Auth Required | Tenant Scoped | Streaming | Dependencies | Reconciliation Tier |
|---|---|:---:|---|:---:|:---:|---|:---:|
| **Health & Readiness** | `/health`, `/api/v1/health` | 6 | Public (No) | No | No | None (Pure Probe) | `PUBLIC_BRUNO` (6) |
| **Observability** | `/metrics` | 1 | Public (No) | No | No | Prometheus Registry | `PUBLIC_BRUNO` (1) |
| **Chat Stream** | `/api/v1/chat` | 1 | Bearer JWT | Yes | Yes (SSE) | LangGraph, Redis, Qdrant | `PUBLIC_BRUNO` (1) |
| **Agent Platform** | `/api/v1/agent` | 9 | Bearer JWT | Yes | 1 SSE / 8 JSON | ExecutionEngine, Redis, Tools | `PUBLIC_BRUNO` (9) |
| **RAG Pipeline** | `/api/v1/rag` | 4 | Bearer JWT | Yes | No | Qdrant, FastEmbed, BM25 | `PUBLIC_BRUNO` (4) |
| **BYOK Vault** | `/api/v1/byok` | 7 | Bearer JWT | Yes | No | AES-256-GCM, Redis Vault | `PUBLIC_BRUNO` (7) |
| **AI Gateway** | `/api/v1/gateway`, `/v1` | 8 | Bearer JWT | Yes | Yes (JSON/SSE) | Redis, QuotaManager, Upstream | `PUBLIC_BRUNO` (8) |
| **AI FinOps** | `/api/v1/finops` | 5 | Bearer JWT | Yes | No | FinOpsBudgetManager, Ledger | `PUBLIC_BRUNO` (5) |
| **Analytics & Billing** | `/api/v1/analytics`, `/api/v1/billing` | 4 | JWT / Webhook HMAC | Yes / Webhook | No | PayOS Service, Metrics | `PUBLIC_BRUNO` (4) |
| **DevOps Bot** | `/api/v1/devops` | 2 | Bearer JWT | Yes | No | DiffPruner, Git, Scanner | `PUBLIC_BRUNO` (2) |
| **Coding Tool Bridge** | `/api/v1/coding`, `/internal/v1/coding` | 4 | JWT / Perimeter Secret | Yes | No | ResumeBridge, Redis | `PUBLIC_BRUNO` (2) / `PRIVATE_BRUNO` (2) |
| **TOTAL** | | **51** | **41 JWT / 10 Public & Perimeter** | **44 Scoped** | **2 SSE** | | **49 Public / 2 Private / 0 Pytest-Only** |

---

### Reconciliation Tier Breakdown
- **PUBLIC_BRUNO**: 49 operations (100% covered in tracked `Bruno/public/` collection; runnable in clean CI/CD environments)
- **PRIVATE_BRUNO**: 2 operations (`POST /internal/v1/coding/resume`, `POST /internal/v1/coding/tool-result` covered in gitignored `Bruno/private/` and verified in CI via Pytest contract suites)
- **PYTEST_ONLY**: 0 operations
- **Total Operations**: 51 operations (dynamically verified against FastAPI `app.openapi()`)

---

## 2. Complete Authoritative 51-Operation Master Inventory

| # | METHOD | PATH | SUMMARY | AUTH REQUIRED | TENANT SCOPED | REQUEST BODY | RESPONSE | STATUS CODES | STREAMING | DEPENDENCIES | SECURITY SENSITIVITY | RECONCILIATION TIER |
|:---:|---|---|---|---|:---:|---|---|---|:---:|---|---|:---:|
| 1 | `GET` | `/api/v1/agent/approvals/pending` | List Pending Approvals | FinnApiGoAuth (JWT) | Yes | `None` | `List[ApprovalRequest]` | 200, 401 | No | AgentRuntime, Redis, ExecutionEngine | Authenticated / High | `PUBLIC_BRUNO` |
| 2 | `GET` | `/api/v1/agent/metrics` | Get Agent Metrics | FinnApiGoAuth (JWT) | Yes | `None` | `AgentMetricsSnapshot` | 200, 401 | No | AgentRuntime, Redis, ExecutionEngine | Authenticated / High | `PUBLIC_BRUNO` |
| 3 | `POST` | `/api/v1/agent/tasks` | Create Task | FinnApiGoAuth (JWT) | Yes | `CreateTaskRequest` | `TaskState` | 201, 422, 401 | No | AgentRuntime, Redis, ExecutionEngine | Authenticated / High | `PUBLIC_BRUNO` |
| 4 | `GET` | `/api/v1/agent/tasks/{task_id}` | Get Task | FinnApiGoAuth (JWT) | Yes | `None` | `TaskState` | 200, 422, 401 | No | AgentRuntime, Redis, ExecutionEngine | Authenticated / High | `PUBLIC_BRUNO` |
| 5 | `POST` | `/api/v1/agent/tasks/{task_id}/runs` | Start Run | FinnApiGoAuth (JWT) | Yes | `CreateRunRequest` | `RunState` | 201, 422, 401 | No | AgentRuntime, Redis, ExecutionEngine | Authenticated / High | `PUBLIC_BRUNO` |
| 6 | `GET` | `/api/v1/agent/tasks/{task_id}/runs/{run_id}` | Get Run | FinnApiGoAuth (JWT) | Yes | `None` | `RunState` | 200, 422, 401 | No | AgentRuntime, Redis, ExecutionEngine | Authenticated / High | `PUBLIC_BRUNO` |
| 7 | `POST` | `/api/v1/agent/tasks/{task_id}/runs/{run_id}/approvals/{approval_id}` | Decide Approval | FinnApiGoAuth (JWT) | Yes | `ApprovalDecision` | `ApprovalRequest` | 200, 422, 401 | No | AgentRuntime, Redis, ExecutionEngine | Authenticated / High | `PUBLIC_BRUNO` |
| 8 | `POST` | `/api/v1/agent/tasks/{task_id}/runs/{run_id}/cancel` | Cancel Run | FinnApiGoAuth (JWT) | Yes | `None` | `RunState` | 200, 422, 401 | No | AgentRuntime, Redis, ExecutionEngine | Authenticated / High | `PUBLIC_BRUNO` |
| 9 | `GET` | `/api/v1/agent/tasks/{task_id}/runs/{run_id}/events` | Stream Run Events | FinnApiGoAuth (JWT) | Yes | `None` | `text/event-stream` | 200, 422, 401 | Yes (SSE) | AgentRuntime, Redis, ExecutionEngine | Authenticated / High | `PUBLIC_BRUNO` |
| 10 | `GET` | `/api/v1/analytics/dashboard` | Get Analytics Dashboard | FinnApiGoAuth (JWT) | Yes | `None` | `AnalyticsDashboard` | 200, 401 | No | Telemetry Metrics | Authenticated / Standard | `PUBLIC_BRUNO` |
| 11 | `GET` | `/api/v1/analytics/metrics` | Get Runtime Metrics | FinnApiGoAuth (JWT) | Yes | `None` | `MetricsSnapshot` | 200, 401 | No | Telemetry Metrics | Authenticated / Standard | `PUBLIC_BRUNO` |
| 12 | `GET` | `/api/v1/billing/subscription` | Get Current Subscription | FinnApiGoAuth (JWT) | Yes | `None` | `SubscriptionInfo` | 200, 401 | No | PayOS / VietQR Service | Authenticated / Standard | `PUBLIC_BRUNO` |
| 13 | `POST` | `/api/v1/billing/webhook` | Handle Payment Webhook | PayOS HMAC | No (Webhook) | `PayOSWebhookRequest` | `JSON Object` | 200, 422 | No | PayOS / VietQR Service | Webhook Verification | `PUBLIC_BRUNO` |
| 14 | `GET` | `/api/v1/byok/keys` | List Provider Keys | FinnApiGoAuth (JWT) | Yes | `None` | `BYOKListResponse` | 200, 401 | No | AES-256-GCM Vault, Redis | Authenticated / High | `PUBLIC_BRUNO` |
| 15 | `POST` | `/api/v1/byok/keys` | Store Provider Key | FinnApiGoAuth (JWT) | Yes | `BYOKStoreRequest` | `BYOKKeyResponse` | 201, 422, 401 | No | AES-256-GCM Vault, Redis | Authenticated / High | `PUBLIC_BRUNO` |
| 16 | `POST` | `/api/v1/byok/keys/validate` | Validate Candidate Key | FinnApiGoAuth (JWT) | Yes | `BYOKValidateRequest` | `BYOKValidationResponse` | 200, 422, 401 | No | AES-256-GCM Vault, Redis | Authenticated / High | `PUBLIC_BRUNO` |
| 17 | `DELETE` | `/api/v1/byok/keys/{provider}` | Delete Provider Key | FinnApiGoAuth (JWT) | Yes | `None` | `JSON Object` | 200, 422, 401 | No | AES-256-GCM Vault, Redis | Authenticated / High | `PUBLIC_BRUNO` |
| 18 | `POST` | `/api/v1/byok/keys/{provider}/revoke` | Revoke Provider Key | FinnApiGoAuth (JWT) | Yes | `None` | `BYOKKeyResponse` | 200, 422, 401 | No | AES-256-GCM Vault, Redis | Authenticated / High | `PUBLIC_BRUNO` |
| 19 | `POST` | `/api/v1/byok/keys/{provider}/rotate` | Rotate Provider Key | FinnApiGoAuth (JWT) | Yes | `BYOKRotateRequest` | `BYOKKeyResponse` | 200, 422, 401 | No | AES-256-GCM Vault, Redis | Authenticated / High | `PUBLIC_BRUNO` |
| 20 | `POST` | `/api/v1/byok/keys/{provider}/validate` | Validate Existing Key | FinnApiGoAuth (JWT) | Yes | `None` | `BYOKValidationResponse` | 200, 422, 401 | No | AES-256-GCM Vault, Redis | Authenticated / High | `PUBLIC_BRUNO` |
| 21 | `POST` | `/api/v1/chat/stream` | Real-time Chat SSE Stream | FinnApiGoAuth (JWT) | Yes | `ChatStreamRequest` | `text/event-stream` | 200, 422, 401 | Yes (SSE) | LangGraph, Redis, Qdrant, LLM Provider | Authenticated / Standard | `PUBLIC_BRUNO` |
| 22 | `POST` | `/api/v1/coding/resume` | Internal Resume Endpoint | Perimeter Secret | Yes | `InternalResumeSubmission` | `ResumedExecutionResult` | 200, 422 | No | ResumeBridge, Redis | Internal Perimeter | `PUBLIC_BRUNO` |
| 23 | `POST` | `/api/v1/coding/tool-result` | Submit Tool Result | FinnApiGoAuth (JWT) | Yes | `ToolResultSubmission` | `ResumedExecutionResult` | 200, 422, 401 | No | ResumeBridge, Redis | Authenticated / Standard | `PUBLIC_BRUNO` |
| 24 | `POST` | `/api/v1/devops/audit-pr` | Audit Pull Request | FinnApiGoAuth (JWT) | Yes | `PRAuditRequest` | `PRAuditResult` | 200, 422, 401 | No | DevOpsBot, DiffPruner | Authenticated / Standard | `PUBLIC_BRUNO` |
| 25 | `POST` | `/api/v1/devops/changelog` | Generate Changelog | FinnApiGoAuth (JWT) | Yes | `ChangelogRequest` | `ChangelogResponse` | 200, 422, 401 | No | DevOpsBot, DiffPruner | Authenticated / Standard | `PUBLIC_BRUNO` |
| 26 | `GET` | `/api/v1/finops/budget` | Get Tenant Budget | FinnApiGoAuth (JWT) | Yes | `None` | `TenantBudget` | 200, 401 | No | FinOpsBudgetManager, Redis Ledger | Authenticated / High | `PUBLIC_BRUNO` |
| 27 | `POST` | `/api/v1/finops/budget` | Configure Tenant Budget | FinnApiGoAuth (JWT) | Yes | `UpdateBudgetRequest` | `TenantBudget` | 200, 422, 401 | No | FinOpsBudgetManager, Redis Ledger | Authenticated / High | `PUBLIC_BRUNO` |
| 28 | `GET` | `/api/v1/finops/reconciliation` | Get Reconciliation Report | FinnApiGoAuth (JWT) | Yes | `None` | `ReconciliationReport` | 200, 422, 401 | No | FinOpsBudgetManager, Redis Ledger | Authenticated / High | `PUBLIC_BRUNO` |
| 29 | `GET` | `/api/v1/finops/summary` | Get Finops Summary | FinnApiGoAuth (JWT) | Yes | `None` | `FinOpsSummary` | 200, 422, 401 | No | FinOpsBudgetManager, Redis Ledger | Authenticated / High | `PUBLIC_BRUNO` |
| 30 | `GET` | `/api/v1/finops/transactions` | List Finops Transactions | FinnApiGoAuth (JWT) | Yes | `None` | `List[FinOpsRecord]` | 200, 422, 401 | No | FinOpsBudgetManager, Redis Ledger | Authenticated / High | `PUBLIC_BRUNO` |
| 31 | `POST` | `/api/v1/gateway/chat/completions` | Proxy Chat Completions | FinnApiGoAuth (JWT) | Yes | `GatewayChatRequest` | `GatewayChatResponse` | 200, 422, 401 | No | LangGraph, Redis, Qdrant, LLM Provider | Authenticated / Standard | `PUBLIC_BRUNO` |
| 32 | `GET` | `/api/v1/gateway/models` | List Available Models | FinnApiGoAuth (JWT) | Yes | `None` | `ModelListResponse` | 200, 401 | No | AI Gateway Proxy, Redis QuotaManager | Authenticated / Standard | `PUBLIC_BRUNO` |
| 33 | `GET` | `/api/v1/gateway/quotas` | Get Tenant Quota | FinnApiGoAuth (JWT) | Yes | `None` | `QuotaStatus` | 200, 401 | No | AI Gateway Proxy, Redis QuotaManager | Authenticated / Standard | `PUBLIC_BRUNO` |
| 34 | `POST` | `/api/v1/gateway/quotas` | Update Tenant Quota | FinnApiGoAuth (JWT) | Yes | `UpdateQuotaRequest` | `QuotaStatus` | 200, 422, 401 | No | AI Gateway Proxy, Redis QuotaManager | Authenticated / Standard | `PUBLIC_BRUNO` |
| 35 | `GET` | `/api/v1/health` | Service Health Probe | Public (None) | No | `None` | `HealthResponse` | 200 | No | Platform System Probes | Public / Low | `PUBLIC_BRUNO` |
| 36 | `GET` | `/api/v1/health/live` | Liveness Probe | Public (None) | No | `None` | `HealthResponse` | 200 | No | Platform System Probes | Public / Low | `PUBLIC_BRUNO` |
| 37 | `GET` | `/api/v1/health/ready` | Readiness Probe | Public (None) | No | `None` | `HealthResponse` | 200 | No | Platform System Probes | Public / Low | `PUBLIC_BRUNO` |
| 38 | `POST` | `/api/v1/rag/generate` | Generate grounded answer via 10-step RAG pipeline | FinnApiGoAuth (JWT) | Yes | `RAGGenerateRequest` | `RAGGenerateResponse` | 200, 422, 401 | No | Qdrant, BM25 Index, FastEmbed | Authenticated / Standard | `PUBLIC_BRUNO` |
| 39 | `POST` | `/api/v1/rag/ingest` | Ingest document into tenant RAG index | FinnApiGoAuth (JWT) | Yes | `DocumentIngestRequest` | `DocumentIngestResponse` | 201, 202, 422, 401 | No | Qdrant, BM25 Index, FastEmbed | Authenticated / Standard | `PUBLIC_BRUNO` |
| 40 | `POST` | `/api/v1/rag/query` | Query tenant-isolated RAG index | FinnApiGoAuth (JWT) | Yes | `RAGQueryRequest` | `RAGQueryResponse` | 200, 422, 401 | No | Qdrant, BM25 Index, FastEmbed | Authenticated / Standard | `PUBLIC_BRUNO` |
| 41 | `GET` | `/api/v1/rag/tasks/{task_id}` | Poll status of asynchronous ingestion task | FinnApiGoAuth (JWT) | Yes | `None` | `IngestionTaskState` | 200, 422, 401 | No | Qdrant, BM25 Index, FastEmbed | Authenticated / Standard | `PUBLIC_BRUNO` |
| 42 | `GET` | `/health` | Root Health Probe | Public (None) | No | `None` | `HealthResponse` | 200 | No | Platform System Probes | Public / Low | `PUBLIC_BRUNO` |
| 43 | `GET` | `/health/live` | Root Liveness Probe | Public (None) | No | `None` | `HealthResponse` | 200 | No | Platform System Probes | Public / Low | `PUBLIC_BRUNO` |
| 44 | `GET` | `/health/ready` | Root Readiness Probe | Public (None) | No | `None` | `HealthResponse` | 200 | No | Platform System Probes | Public / Low | `PUBLIC_BRUNO` |
| 45 | `POST` | `/internal/v1/coding/resume` | Internal Resume Endpoint | Perimeter Secret | Yes | `InternalResumeSubmission` | `ResumedExecutionResult` | 200, 422 | No | ResumeBridge, Redis | Internal Perimeter | `PRIVATE_BRUNO` |
| 46 | `POST` | `/internal/v1/coding/tool-result` | Submit Tool Result | FinnApiGoAuth (JWT) | Yes | `ToolResultSubmission` | `ResumedExecutionResult` | 200, 422, 401 | No | ResumeBridge, Redis | Authenticated / Standard | `PRIVATE_BRUNO` |
| 47 | `GET` | `/metrics` | Prometheus Metrics Exposition | Public (None) | No | `None` | `text/plain` | 200 | No | Platform System Probes | Public / Low | `PUBLIC_BRUNO` |
| 48 | `POST` | `/v1/chat/completions` | Proxy Chat Completions | FinnApiGoAuth (JWT) | Yes | `GatewayChatRequest` | `GatewayChatResponse` | 200, 422, 401 | No | LangGraph, Redis, Qdrant, LLM Provider | Authenticated / Standard | `PUBLIC_BRUNO` |
| 49 | `GET` | `/v1/models` | List Available Models | FinnApiGoAuth (JWT) | Yes | `None` | `ModelListResponse` | 200, 401 | No | AI Gateway Proxy, Redis QuotaManager | Authenticated / Standard | `PUBLIC_BRUNO` |
| 50 | `GET` | `/v1/quotas` | Get Tenant Quota | FinnApiGoAuth (JWT) | Yes | `None` | `QuotaStatus` | 200, 401 | No | AI Gateway Proxy, Redis QuotaManager | Authenticated / Standard | `PUBLIC_BRUNO` |
| 51 | `POST` | `/v1/quotas` | Update Tenant Quota | FinnApiGoAuth (JWT) | Yes | `UpdateQuotaRequest` | `QuotaStatus` | 200, 422, 401 | No | AI Gateway Proxy, Redis QuotaManager | Authenticated / Standard | `PUBLIC_BRUNO` |
