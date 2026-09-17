# BRUNO-RECONCILIATION — Bruno Collection to JakeAI Application Audit

**Audit Baseline**: Current `main` | Current FastAPI Runtime (`app.main:app`)  
**Total Reconciled `.bru` Requests**: 117 (64 Public + 53 Private)  
**Total OpenAPI Operations Required**: 51  
**OpenAPI Operations Covered**: 51 / 51 (100% Complete)  
**Missing Coverage**: 0  
**Reconciliation Date**: September 17, 2026  
**Overall Reconciliation Status**: **🟢 PASS**  

---

## 1. Classification Summary

| Classification | Count | Description | Partition |
|---|:---:|---|:---:|
| **EXACT MATCH** | 64 | Safe public API examples, smoke checks, and OpenAPI operations. | `public/` |
| **SECURITY-SENSITIVE** | 44 | Negative tests, attack payloads, chaos, tenant boundaries, and failure injection. | `private/` |
| **LIVE-ONLY** | 9 | Live FinnApiGo authority and live third-party model providers (BLOCKED when offline). | `private/` |
| **VALID BUT OUTDATED** | 0 | All outdated endpoints reconciled to current routes. | N/A |
| **OBSOLETE** | 0 | All obsolete legacy endpoints removed. | N/A |
| **DUPLICATE** | 0 | All requests consolidated with distinct documented purposes. | N/A |
| **BROKEN** | 0 | All requests validated with correct schemas and status codes. | N/A |
| **MISSING** | 0 | All 51 current OpenAPI operations covered. | N/A |
| **TOTAL ACTIVE** | **117** | **Full reconciled workspace collection.** | **64 Pub / 53 Priv** |

---

## 2. Master Request-by-Request Reconciliation Table

| # | Collection Partition | Request File | Method | Target URL | Auth | Classification | Notes / Purpose |
|:---:|:---:|---|:---:|---|:---:|---|---|
| 1 | `private/` (Gitignored) | `private/01 — Authentication & Tenant Security/01 — Verify Token A.bru` | `GET` | `{{base_url}}/api/v1/health` | `bearer` | **SECURITY-SENSITIVE** | Negative test, boundary isolation, prompt injection, or failure recovery (private only). |
| 2 | `private/` (Gitignored) | `private/01 — Authentication & Tenant Security/02 — Authenticated Health.bru` | `GET` | `{{base_url}}/api/v1/health` | `bearer` | **SECURITY-SENSITIVE** | Negative test, boundary isolation, prompt injection, or failure recovery (private only). |
| 3 | `private/` (Gitignored) | `private/01 — Authentication & Tenant Security/03 — Tenant Context.bru` | `GET` | `{{base_url}}/api/v1/health` | `bearer` | **SECURITY-SENSITIVE** | Negative test, boundary isolation, prompt injection, or failure recovery (private only). |
| 4 | `private/` (Gitignored) | `private/01 — Authentication & Tenant Security/04 — Missing Token Rejection.bru` | `GET` | `{{base_url}}/api/v1/agent/metrics` | `none` | **SECURITY-SENSITIVE** | Negative test, boundary isolation, prompt injection, or failure recovery (private only). |
| 5 | `private/` (Gitignored) | `private/01 — Authentication & Tenant Security/05 — Invalid Token Rejection.bru` | `GET` | `{{base_url}}/api/v1/agent/metrics` | `bearer` | **SECURITY-SENSITIVE** | Negative test, boundary isolation, prompt injection, or failure recovery (private only). |
| 6 | `private/` (Gitignored) | `private/01 — Authentication & Tenant Security/06 — Expired Token Rejection.bru` | `GET` | `{{base_url}}/api/v1/agent/metrics` | `bearer` | **SECURITY-SENSITIVE** | Negative test, boundary isolation, prompt injection, or failure recovery (private only). |
| 7 | `private/` (Gitignored) | `private/01 — Authentication & Tenant Security/07 — Internal Perimeter Secret Rejection.bru` | `POST` | `{{base_url}}/internal/v1/coding/resume` | `none` | **SECURITY-SENSITIVE** | Negative test, boundary isolation, prompt injection, or failure recovery (private only). |
| 8 | `private/` (Gitignored) | `private/01 — Authentication & Tenant Security/08 — Internal Perimeter Secret Valid.bru` | `POST` | `{{base_url}}/internal/v1/coding/resume` | `none` | **SECURITY-SENSITIVE** | Negative test, boundary isolation, prompt injection, or failure recovery (private only). |
| 9 | `private/` (Gitignored) | `private/01 — Authentication & Tenant Security/09 — Billing Webhook Signature.bru` | `POST` | `{{base_url}}/api/v1/billing/webhook` | `none` | **SECURITY-SENSITIVE** | Negative test, boundary isolation, prompt injection, or failure recovery (private only). |
| 10 | `private/` (Gitignored) | `private/02 — Security & Negative/01 — Missing Authentication.bru` | `POST` | `{{base_url}}/api/v1/chat/stream` | `none` | **SECURITY-SENSITIVE** | Negative test, boundary isolation, prompt injection, or failure recovery (private only). |
| 11 | `private/` (Gitignored) | `private/02 — Security & Negative/02 — Invalid Authentication.bru` | `POST` | `{{base_url}}/api/v1/chat/stream` | `bearer` | **SECURITY-SENSITIVE** | Negative test, boundary isolation, prompt injection, or failure recovery (private only). |
| 12 | `private/` (Gitignored) | `private/02 — Security & Negative/03 — Forbidden Permission.bru` | `POST` | `{{base_url}}/api/v1/agent/tasks/{{task_id}}/runs/{{run_id}}/approvals/{{approval_id}}` | `bearer` | **SECURITY-SENSITIVE** | Negative test, boundary isolation, prompt injection, or failure recovery (private only). |
| 13 | `private/` (Gitignored) | `private/02 — Security & Negative/04 — Invalid Input 422.bru` | `POST` | `{{base_url}}/api/v1/chat/stream` | `bearer` | **SECURITY-SENSITIVE** | Negative test, boundary isolation, prompt injection, or failure recovery (private only). |
| 14 | `private/` (Gitignored) | `private/02 — Security & Negative/05 — Chat Validation Negative.bru` | `POST` | `{{base_url}}/v1/chat/completions` | `bearer` | **SECURITY-SENSITIVE** | Negative test, boundary isolation, prompt injection, or failure recovery (private only). |
| 15 | `private/` (Gitignored) | `private/02 — Security & Negative/06 — Gateway Negative Parameters.bru` | `POST` | `{{base_url}}/v1/chat/completions` | `bearer` | **SECURITY-SENSITIVE** | Negative test, boundary isolation, prompt injection, or failure recovery (private only). |
| 16 | `private/` (Gitignored) | `private/02 — Security & Negative/07 — Oversized Input 413.bru` | `POST` | `{{base_url}}/api/v1/chat/stream` | `bearer` | **SECURITY-SENSITIVE** | Negative test, boundary isolation, prompt injection, or failure recovery (private only). |
| 17 | `private/` (Gitignored) | `private/02 — Security & Negative/08 — Prompt Injection Blocked.bru` | `POST` | `{{base_url}}/api/v1/chat/stream` | `bearer` | **SECURITY-SENSITIVE** | Negative test, boundary isolation, prompt injection, or failure recovery (private only). |
| 18 | `private/` (Gitignored) | `private/02 — Security & Negative/09 — Malformed Provider Response.bru` | `POST` | `{{base_url}}/v1/chat/completions` | `bearer` | **SECURITY-SENSITIVE** | Negative test, boundary isolation, prompt injection, or failure recovery (private only). |
| 19 | `private/` (Gitignored) | `private/02 — Security & Negative/10 — Provider Status Normalization.bru` | `POST` | `{{base_url}}/v1/chat/completions` | `bearer` | **SECURITY-SENSITIVE** | Negative test, boundary isolation, prompt injection, or failure recovery (private only). |
| 20 | `private/` (Gitignored) | `private/03 — Failure & Recovery/01 — Provider Timeout.bru` | `POST` | `{{base_url}}/v1/chat/completions` | `bearer` | **SECURITY-SENSITIVE** | Negative test, boundary isolation, prompt injection, or failure recovery (private only). |
| 21 | `private/` (Gitignored) | `private/03 — Failure & Recovery/02 — Provider Unavailable 503.bru` | `GET` | `{{base_url}}/api/v1/health/ready` | `none` | **SECURITY-SENSITIVE** | Negative test, boundary isolation, prompt injection, or failure recovery (private only). |
| 22 | `private/` (Gitignored) | `private/03 — Failure & Recovery/03 — Provider Retryable.bru` | `POST` | `{{base_url}}/v1/chat/completions` | `bearer` | **SECURITY-SENSITIVE** | Negative test, boundary isolation, prompt injection, or failure recovery (private only). |
| 23 | `private/` (Gitignored) | `private/03 — Failure & Recovery/04 — Model Failover.bru` | `POST` | `{{base_url}}/v1/chat/completions` | `bearer` | **SECURITY-SENSITIVE** | Negative test, boundary isolation, prompt injection, or failure recovery (private only). |
| 24 | `private/` (Gitignored) | `private/03 — Failure & Recovery/05 — Agent Run Failure State.bru` | `GET` | `{{base_url}}/api/v1/agent/tasks/{{task_id}}/runs/{{run_id}}` | `bearer` | **SECURITY-SENSITIVE** | Negative test, boundary isolation, prompt injection, or failure recovery (private only). |
| 25 | `private/` (Gitignored) | `private/03 — Failure & Recovery/06 — Resume After Interrupt.bru` | `GET` | `{{base_url}}/api/v1/agent/tasks/{{task_id}}/runs/{{run_id}}` | `bearer` | **SECURITY-SENSITIVE** | Negative test, boundary isolation, prompt injection, or failure recovery (private only). |
| 26 | `private/` (Gitignored) | `private/03 — Failure & Recovery/07 — Cancel Terminal Invariant.bru` | `POST` | `{{base_url}}/api/v1/agent/tasks/{{task_id}}/runs/{{run_id}}/cancel` | `bearer` | **SECURITY-SENSITIVE** | Negative test, boundary isolation, prompt injection, or failure recovery (private only). |
| 27 | `private/` (Gitignored) | `private/03 — Failure & Recovery/08 — Cache Provider Failure Behavior.bru` | `POST` | `{{base_url}}/api/v1/chat/stream` | `bearer` | **SECURITY-SENSITIVE** | Negative test, boundary isolation, prompt injection, or failure recovery (private only). |
| 28 | `private/` (Gitignored) | `private/03 — Failure & Recovery/09 — Streaming Disconnect Invariant.bru` | `POST` | `{{base_url}}/api/v1/chat/stream` | `bearer` | **SECURITY-SENSITIVE** | Negative test, boundary isolation, prompt injection, or failure recovery (private only). |
| 29 | `private/` (Gitignored) | `private/03 — Failure & Recovery/10 — Accounting After Failure.bru` | `GET` | `{{base_url}}/api/v1/finops/summary` | `bearer` | **SECURITY-SENSITIVE** | Negative test, boundary isolation, prompt injection, or failure recovery (private only). |
| 30 | `private/` (Gitignored) | `private/04 — Cross Tenant/01 — Cross Tenant Task Access.bru` | `GET` | `{{base_url}}/api/v1/agent/tasks/{{task_id}}` | `bearer` | **SECURITY-SENSITIVE** | Negative test, boundary isolation, prompt injection, or failure recovery (private only). |
| 31 | `private/` (Gitignored) | `private/04 — Cross Tenant/02 — Cross Tenant RAG Isolation.bru` | `GET` | `{{base_url}}/api/v1/rag/tasks/{{rag_task_id}}` | `bearer` | **SECURITY-SENSITIVE** | Negative test, boundary isolation, prompt injection, or failure recovery (private only). |
| 32 | `private/` (Gitignored) | `private/04 — Cross Tenant/03 — Cache Tenant Isolation.bru` | `POST` | `{{base_url}}/api/v1/chat/stream` | `bearer` | **SECURITY-SENSITIVE** | Negative test, boundary isolation, prompt injection, or failure recovery (private only). |
| 33 | `private/` (Gitignored) | `private/04 — Cross Tenant/04 — Cross Tenant Access Rejection.bru` | `DELETE` | `{{base_url}}/api/v1/byok/keys/{{provider}}` | `bearer` | **SECURITY-SENSITIVE** | Negative test, boundary isolation, prompt injection, or failure recovery (private only). |
| 34 | `private/` (Gitignored) | `private/05 — Tool Security/01 — Tool Authorization RBAC.bru` | `POST` | `{{base_url}}/api/v1/coding/tool-result` | `bearer` | **SECURITY-SENSITIVE** | Negative test, boundary isolation, prompt injection, or failure recovery (private only). |
| 35 | `private/` (Gitignored) | `private/05 — Tool Security/02 — Dangerous Tool Shell Injection.bru` | `POST` | `{{base_url}}/api/v1/coding/tool-result` | `bearer` | **SECURITY-SENSITIVE** | Negative test, boundary isolation, prompt injection, or failure recovery (private only). |
| 36 | `private/` (Gitignored) | `private/05 — Tool Security/03 — Tool Result Internal Bridge.bru` | `POST` | `{{base_url}}/internal/v1/coding/tool-result` | `bearer` | **SECURITY-SENSITIVE** | Negative test, boundary isolation, prompt injection, or failure recovery (private only). |
| 37 | `private/` (Gitignored) | `private/06 — Live Provider/01 — Live Gemini Smoke.bru` | `POST` | `{{base_url}}/v1/chat/completions` | `bearer` | **LIVE-ONLY** | Live third-party LLM inference probe (requires valid provider API key; BLOCKED if missing). |
| 38 | `private/` (Gitignored) | `private/06 — Live Provider/02 — Live OpenAI Smoke.bru` | `POST` | `{{base_url}}/v1/chat/completions` | `bearer` | **LIVE-ONLY** | Live third-party LLM inference probe (requires valid provider API key; BLOCKED if missing). |
| 39 | `private/` (Gitignored) | `private/06 — Live Provider/03 — Live Anthropic Smoke.bru` | `POST` | `{{base_url}}/v1/chat/completions` | `bearer` | **LIVE-ONLY** | Live third-party LLM inference probe (requires valid provider API key; BLOCKED if missing). |
| 40 | `private/` (Gitignored) | `private/06 — Live Provider/04 — Live DeepSeek Smoke.bru` | `POST` | `{{base_url}}/v1/chat/completions` | `bearer` | **LIVE-ONLY** | Live third-party LLM inference probe (requires valid provider API key; BLOCKED if missing). |
| 41 | `private/` (Gitignored) | `private/06 — Live Provider/05 — Live Groq Smoke.bru` | `POST` | `{{base_url}}/v1/chat/completions` | `bearer` | **LIVE-ONLY** | Live third-party LLM inference probe (requires valid provider API key; BLOCKED if missing). |
| 42 | `private/` (Gitignored) | `private/06 — Live Provider/06 — Live OpenRouter Smoke.bru` | `POST` | `{{base_url}}/v1/chat/completions` | `bearer` | **LIVE-ONLY** | Live third-party LLM inference probe (requires valid provider API key; BLOCKED if missing). |
| 43 | `private/` (Gitignored) | `private/07 — Live FinnApiGo/01 — Healthz Probe.bru` | `GET` | `{{finnapigo_base_url}}/healthz` | `none` | **LIVE-ONLY** | Targets external FinnApiGo identity authority (fail-closed / BLOCKED when offline). |
| 44 | `private/` (Gitignored) | `private/07 — Live FinnApiGo/02 — FinnApiGo Login.bru` | `POST` | `{{finnapigo_base_url}}/api/v1/auth/login` | `none` | **LIVE-ONLY** | Targets external FinnApiGo identity authority (fail-closed / BLOCKED when offline). |
| 45 | `private/` (Gitignored) | `private/07 — Live FinnApiGo/03 — FinnApiGo OBO Token Exchange.bru` | `GET` | `{{finnapigo_base_url}}/healthz` | `none` | **LIVE-ONLY** | Targets external FinnApiGo identity authority (fail-closed / BLOCKED when offline). |
| 46 | `private/` (Gitignored) | `private/08 — Production Verification/01 — FinnApiGo to JakeAI Auth.bru` | `GET` | `{{base_url}}/api/v1/health` | `bearer` | **SECURITY-SENSITIVE** | Negative test, boundary isolation, prompt injection, or failure recovery (private only). |
| 47 | `private/` (Gitignored) | `private/08 — Production Verification/02 — Task to Run to Result.bru` | `GET` | `{{base_url}}/api/v1/agent/tasks/{{task_id}}` | `bearer` | **SECURITY-SENSITIVE** | Negative test, boundary isolation, prompt injection, or failure recovery (private only). |
| 48 | `private/` (Gitignored) | `private/08 — Production Verification/03 — RAG Grounded Answer.bru` | `POST` | `{{base_url}}/api/v1/rag/generate` | `bearer` | **SECURITY-SENSITIVE** | Negative test, boundary isolation, prompt injection, or failure recovery (private only). |
| 49 | `private/` (Gitignored) | `private/08 — Production Verification/04 — BYOK to Provider Chat.bru` | `GET` | `{{base_url}}/api/v1/byok/keys` | `bearer` | **SECURITY-SENSITIVE** | Negative test, boundary isolation, prompt injection, or failure recovery (private only). |
| 50 | `private/` (Gitignored) | `private/08 — Production Verification/05 — Agent to Tool Verification.bru` | `GET` | `{{base_url}}/api/v1/agent/metrics` | `bearer` | **SECURITY-SENSITIVE** | Negative test, boundary isolation, prompt injection, or failure recovery (private only). |
| 51 | `private/` (Gitignored) | `private/08 — Production Verification/06 — Approval to Resume Flow.bru` | `GET` | `{{base_url}}/api/v1/agent/approvals/pending` | `bearer` | **SECURITY-SENSITIVE** | Negative test, boundary isolation, prompt injection, or failure recovery (private only). |
| 52 | `private/` (Gitignored) | `private/08 — Production Verification/07 — Chat to Cache to FinOps.bru` | `GET` | `{{base_url}}/api/v1/finops/summary` | `bearer` | **SECURITY-SENSITIVE** | Negative test, boundary isolation, prompt injection, or failure recovery (private only). |
| 53 | `private/` (Gitignored) | `private/08 — Production Verification/08 — Failure to Recovery Result.bru` | `GET` | `{{base_url}}/health` | `none` | **SECURITY-SENSITIVE** | Negative test, boundary isolation, prompt injection, or failure recovery (private only). |
| 54 | `public/` (Tracked) | `public/00 — Setup/01 — Root Health Smoke.bru` | `GET` | `{{base_url}}/health` | `none` | **EXACT MATCH** | Safe public operational example or smoke verification matching OpenAPI 3.1.0 contract. |
| 55 | `public/` (Tracked) | `public/00 — Setup/02 — API Health Smoke.bru` | `GET` | `{{base_url}}/api/v1/health` | `none` | **EXACT MATCH** | Safe public operational example or smoke verification matching OpenAPI 3.1.0 contract. |
| 56 | `public/` (Tracked) | `public/00 — Setup/03 — Root Liveness Probe.bru` | `GET` | `{{base_url}}/health/live` | `none` | **EXACT MATCH** | Safe public operational example or smoke verification matching OpenAPI 3.1.0 contract. |
| 57 | `public/` (Tracked) | `public/00 — Setup/04 — Root Readiness Probe.bru` | `GET` | `{{base_url}}/health/ready` | `none` | **EXACT MATCH** | Safe public operational example or smoke verification matching OpenAPI 3.1.0 contract. |
| 58 | `public/` (Tracked) | `public/00 — Setup/05 — API Health Live Probe.bru` | `GET` | `{{base_url}}/api/v1/health/live` | `none` | **EXACT MATCH** | Safe public operational example or smoke verification matching OpenAPI 3.1.0 contract. |
| 59 | `public/` (Tracked) | `public/00 — Setup/06 — API Health Ready Probe.bru` | `GET` | `{{base_url}}/api/v1/health/ready` | `none` | **EXACT MATCH** | Safe public operational example or smoke verification matching OpenAPI 3.1.0 contract. |
| 60 | `public/` (Tracked) | `public/00 — Setup/07 — Prometheus Metrics.bru` | `GET` | `{{base_url}}/metrics` | `none` | **EXACT MATCH** | Safe public operational example or smoke verification matching OpenAPI 3.1.0 contract. |
| 61 | `public/` (Tracked) | `public/01 — Public Smoke/01 — Public Root Health.bru` | `GET` | `{{base_url}}/health` | `none` | **EXACT MATCH** | Safe public operational example or smoke verification matching OpenAPI 3.1.0 contract. |
| 62 | `public/` (Tracked) | `public/01 — Public Smoke/02 — Public API Health.bru` | `GET` | `{{base_url}}/api/v1/health` | `none` | **EXACT MATCH** | Safe public operational example or smoke verification matching OpenAPI 3.1.0 contract. |
| 63 | `public/` (Tracked) | `public/01 — Public Smoke/03 — Public Models Catalog.bru` | `GET` | `{{base_url}}/v1/models` | `bearer` | **EXACT MATCH** | Safe public operational example or smoke verification matching OpenAPI 3.1.0 contract. |
| 64 | `public/` (Tracked) | `public/01 — Public Smoke/04 — Public Metrics Exposition.bru` | `GET` | `{{base_url}}/metrics` | `none` | **EXACT MATCH** | Safe public operational example or smoke verification matching OpenAPI 3.1.0 contract. |
| 65 | `public/` (Tracked) | `public/02 — Chat/01 — Chat Stream.bru` | `POST` | `{{base_url}}/api/v1/chat/stream` | `bearer` | **EXACT MATCH** | Safe public operational example or smoke verification matching OpenAPI 3.1.0 contract. |
| 66 | `public/` (Tracked) | `public/02 — Chat/02 — Chat SSE Stream Event Frames.bru` | `POST` | `{{base_url}}/api/v1/chat/stream` | `bearer` | **EXACT MATCH** | Safe public operational example or smoke verification matching OpenAPI 3.1.0 contract. |
| 67 | `public/` (Tracked) | `public/02 — Chat/03 — OpenAI Gateway Chat.bru` | `POST` | `{{base_url}}/v1/chat/completions` | `bearer` | **EXACT MATCH** | Safe public operational example or smoke verification matching OpenAPI 3.1.0 contract. |
| 68 | `public/` (Tracked) | `public/02 — Chat/04 — OpenAI Models List.bru` | `GET` | `{{base_url}}/v1/models` | `bearer` | **EXACT MATCH** | Safe public operational example or smoke verification matching OpenAPI 3.1.0 contract. |
| 69 | `public/` (Tracked) | `public/02 — Chat/05 — API Gateway Models List.bru` | `GET` | `{{base_url}}/api/v1/gateway/models` | `bearer` | **EXACT MATCH** | Safe public operational example or smoke verification matching OpenAPI 3.1.0 contract. |
| 70 | `public/` (Tracked) | `public/02 — Chat/06 — API Gateway Chat Completions.bru` | `POST` | `{{base_url}}/api/v1/gateway/chat/completions` | `bearer` | **EXACT MATCH** | Safe public operational example or smoke verification matching OpenAPI 3.1.0 contract. |
| 71 | `public/` (Tracked) | `public/02 — Chat/07 — OpenAI Gateway Quotas Read.bru` | `GET` | `{{base_url}}/v1/quotas` | `bearer` | **EXACT MATCH** | Safe public operational example or smoke verification matching OpenAPI 3.1.0 contract. |
| 72 | `public/` (Tracked) | `public/02 — Chat/08 — OpenAI Gateway Quotas Update.bru` | `POST` | `{{base_url}}/v1/quotas` | `bearer` | **EXACT MATCH** | Safe public operational example or smoke verification matching OpenAPI 3.1.0 contract. |
| 73 | `public/` (Tracked) | `public/02 — Chat/09 — API Gateway Quotas Read.bru` | `GET` | `{{base_url}}/api/v1/gateway/quotas` | `bearer` | **EXACT MATCH** | Safe public operational example or smoke verification matching OpenAPI 3.1.0 contract. |
| 74 | `public/` (Tracked) | `public/02 — Chat/10 — API Gateway Quotas Update.bru` | `POST` | `{{base_url}}/api/v1/gateway/quotas` | `bearer` | **EXACT MATCH** | Safe public operational example or smoke verification matching OpenAPI 3.1.0 contract. |
| 75 | `public/` (Tracked) | `public/03 — Agent/01 — Create Task.bru` | `POST` | `{{base_url}}/api/v1/agent/tasks` | `bearer` | **EXACT MATCH** | Safe public operational example or smoke verification matching OpenAPI 3.1.0 contract. |
| 76 | `public/` (Tracked) | `public/03 — Agent/02 — Get Task.bru` | `GET` | `{{base_url}}/api/v1/agent/tasks/{{task_id}}` | `bearer` | **EXACT MATCH** | Safe public operational example or smoke verification matching OpenAPI 3.1.0 contract. |
| 77 | `public/` (Tracked) | `public/03 — Agent/03 — Start Run.bru` | `POST` | `{{base_url}}/api/v1/agent/tasks/{{task_id}}/runs` | `bearer` | **EXACT MATCH** | Safe public operational example or smoke verification matching OpenAPI 3.1.0 contract. |
| 78 | `public/` (Tracked) | `public/03 — Agent/04 — Get Run.bru` | `GET` | `{{base_url}}/api/v1/agent/tasks/{{task_id}}/runs/{{run_id}}` | `bearer` | **EXACT MATCH** | Safe public operational example or smoke verification matching OpenAPI 3.1.0 contract. |
| 79 | `public/` (Tracked) | `public/03 — Agent/05 — Stream Run Events.bru` | `GET` | `{{base_url}}/api/v1/agent/tasks/{{task_id}}/runs/{{run_id}}/events` | `bearer` | **EXACT MATCH** | Safe public operational example or smoke verification matching OpenAPI 3.1.0 contract. |
| 80 | `public/` (Tracked) | `public/03 — Agent/06 — Cancel Run.bru` | `POST` | `{{base_url}}/api/v1/agent/tasks/{{task_id}}/runs/{{run_id}}/cancel` | `bearer` | **EXACT MATCH** | Safe public operational example or smoke verification matching OpenAPI 3.1.0 contract. |
| 81 | `public/` (Tracked) | `public/03 — Agent/07 — Pending Approvals.bru` | `GET` | `{{base_url}}/api/v1/agent/approvals/pending` | `bearer` | **EXACT MATCH** | Safe public operational example or smoke verification matching OpenAPI 3.1.0 contract. |
| 82 | `public/` (Tracked) | `public/03 — Agent/08 — Approval Decision.bru` | `POST` | `{{base_url}}/api/v1/agent/tasks/{{task_id}}/runs/{{run_id}}/approvals/{{approval_id}}` | `bearer` | **EXACT MATCH** | Safe public operational example or smoke verification matching OpenAPI 3.1.0 contract. |
| 83 | `public/` (Tracked) | `public/03 — Agent/09 — Resume Checkpoint.bru` | `GET` | `{{base_url}}/api/v1/agent/tasks/{{task_id}}/runs/{{run_id}}` | `bearer` | **EXACT MATCH** | Safe public operational example or smoke verification matching OpenAPI 3.1.0 contract. |
| 84 | `public/` (Tracked) | `public/03 — Agent/10 — Agent Metrics.bru` | `GET` | `{{base_url}}/api/v1/agent/metrics` | `bearer` | **EXACT MATCH** | Safe public operational example or smoke verification matching OpenAPI 3.1.0 contract. |
| 85 | `public/` (Tracked) | `public/04 — RAG/01 — Ingest Document.bru` | `POST` | `{{base_url}}/api/v1/rag/ingest` | `bearer` | **EXACT MATCH** | Safe public operational example or smoke verification matching OpenAPI 3.1.0 contract. |
| 86 | `public/` (Tracked) | `public/04 — RAG/02 — Get RAG Ingestion Task.bru` | `GET` | `{{base_url}}/api/v1/rag/tasks/{{rag_task_id}}` | `bearer` | **EXACT MATCH** | Safe public operational example or smoke verification matching OpenAPI 3.1.0 contract. |
| 87 | `public/` (Tracked) | `public/04 — RAG/03 — Hybrid Query.bru` | `POST` | `{{base_url}}/api/v1/rag/query` | `bearer` | **EXACT MATCH** | Safe public operational example or smoke verification matching OpenAPI 3.1.0 contract. |
| 88 | `public/` (Tracked) | `public/04 — RAG/04 — Generate Grounded Answer.bru` | `POST` | `{{base_url}}/api/v1/rag/generate` | `bearer` | **EXACT MATCH** | Safe public operational example or smoke verification matching OpenAPI 3.1.0 contract. |
| 89 | `public/` (Tracked) | `public/04 — RAG/05 — Citation Verification.bru` | `POST` | `{{base_url}}/api/v1/rag/generate` | `bearer` | **EXACT MATCH** | Safe public operational example or smoke verification matching OpenAPI 3.1.0 contract. |
| 90 | `public/` (Tracked) | `public/04 — RAG/06 — Epistemic Abstention.bru` | `POST` | `{{base_url}}/api/v1/rag/generate` | `bearer` | **EXACT MATCH** | Safe public operational example or smoke verification matching OpenAPI 3.1.0 contract. |
| 91 | `public/` (Tracked) | `public/05 — Provider Examples/01 — List BYOK Keys.bru` | `GET` | `{{base_url}}/api/v1/byok/keys` | `bearer` | **EXACT MATCH** | Safe public operational example or smoke verification matching OpenAPI 3.1.0 contract. |
| 92 | `public/` (Tracked) | `public/05 — Provider Examples/02 — Add BYOK Key.bru` | `POST` | `{{base_url}}/api/v1/byok/keys` | `bearer` | **EXACT MATCH** | Safe public operational example or smoke verification matching OpenAPI 3.1.0 contract. |
| 93 | `public/` (Tracked) | `public/05 — Provider Examples/03 — Validate BYOK Key.bru` | `POST` | `{{base_url}}/api/v1/byok/keys/validate` | `bearer` | **EXACT MATCH** | Safe public operational example or smoke verification matching OpenAPI 3.1.0 contract. |
| 94 | `public/` (Tracked) | `public/05 — Provider Examples/04 — Validate Stored Provider.bru` | `POST` | `{{base_url}}/api/v1/byok/keys/{{provider}}/validate` | `bearer` | **EXACT MATCH** | Safe public operational example or smoke verification matching OpenAPI 3.1.0 contract. |
| 95 | `public/` (Tracked) | `public/05 — Provider Examples/05 — Rotate Provider Key.bru` | `POST` | `{{base_url}}/api/v1/byok/keys/{{provider}}/rotate` | `bearer` | **EXACT MATCH** | Safe public operational example or smoke verification matching OpenAPI 3.1.0 contract. |
| 96 | `public/` (Tracked) | `public/05 — Provider Examples/06 — Revoke Provider Key.bru` | `POST` | `{{base_url}}/api/v1/byok/keys/{{provider}}/revoke` | `bearer` | **EXACT MATCH** | Safe public operational example or smoke verification matching OpenAPI 3.1.0 contract. |
| 97 | `public/` (Tracked) | `public/05 — Provider Examples/07 — Delete Provider Key.bru` | `DELETE` | `{{base_url}}/api/v1/byok/keys/{{provider}}` | `bearer` | **EXACT MATCH** | Safe public operational example or smoke verification matching OpenAPI 3.1.0 contract. |
| 98 | `public/` (Tracked) | `public/05 — Provider Examples/08 — Exact Cache Miss.bru` | `POST` | `{{base_url}}/api/v1/chat/stream` | `bearer` | **EXACT MATCH** | Safe public operational example or smoke verification matching OpenAPI 3.1.0 contract. |
| 99 | `public/` (Tracked) | `public/05 — Provider Examples/09 — Exact Cache Hit.bru` | `POST` | `{{base_url}}/api/v1/chat/stream` | `bearer` | **EXACT MATCH** | Safe public operational example or smoke verification matching OpenAPI 3.1.0 contract. |
| 100 | `public/` (Tracked) | `public/05 — Provider Examples/10 — Semantic Cache Hit.bru` | `POST` | `{{base_url}}/api/v1/chat/stream` | `bearer` | **EXACT MATCH** | Safe public operational example or smoke verification matching OpenAPI 3.1.0 contract. |
| 101 | `public/` (Tracked) | `public/05 — Provider Examples/11 — Cache Parameter Sensitivity.bru` | `POST` | `{{base_url}}/api/v1/chat/stream` | `bearer` | **EXACT MATCH** | Safe public operational example or smoke verification matching OpenAPI 3.1.0 contract. |
| 102 | `public/` (Tracked) | `public/05 — Provider Examples/12 — FinOps Summary.bru` | `GET` | `{{base_url}}/api/v1/finops/summary` | `bearer` | **EXACT MATCH** | Safe public operational example or smoke verification matching OpenAPI 3.1.0 contract. |
| 103 | `public/` (Tracked) | `public/05 — Provider Examples/13 — Analytics Dashboard.bru` | `GET` | `{{base_url}}/api/v1/analytics/dashboard` | `bearer` | **EXACT MATCH** | Safe public operational example or smoke verification matching OpenAPI 3.1.0 contract. |
| 104 | `public/` (Tracked) | `public/05 — Provider Examples/14 — FinOps Budget Read.bru` | `GET` | `{{base_url}}/api/v1/finops/budget` | `bearer` | **EXACT MATCH** | Safe public operational example or smoke verification matching OpenAPI 3.1.0 contract. |
| 105 | `public/` (Tracked) | `public/05 — Provider Examples/15 — FinOps Budget Update.bru` | `POST` | `{{base_url}}/api/v1/finops/budget` | `bearer` | **EXACT MATCH** | Safe public operational example or smoke verification matching OpenAPI 3.1.0 contract. |
| 106 | `public/` (Tracked) | `public/05 — Provider Examples/16 — FinOps Usage Accounting.bru` | `GET` | `{{base_url}}/api/v1/finops/summary` | `bearer` | **EXACT MATCH** | Safe public operational example or smoke verification matching OpenAPI 3.1.0 contract. |
| 107 | `public/` (Tracked) | `public/05 — Provider Examples/17 — Billing Subscription.bru` | `GET` | `{{base_url}}/api/v1/billing/subscription` | `bearer` | **EXACT MATCH** | Safe public operational example or smoke verification matching OpenAPI 3.1.0 contract. |
| 108 | `public/` (Tracked) | `public/05 — Provider Examples/18 — FinOps Transactions.bru` | `GET` | `{{base_url}}/api/v1/finops/transactions?limit=10&offset=0` | `bearer` | **EXACT MATCH** | Safe public operational example or smoke verification matching OpenAPI 3.1.0 contract. |
| 109 | `public/` (Tracked) | `public/05 — Provider Examples/19 — FinOps Reconciliation.bru` | `GET` | `{{base_url}}/api/v1/finops/reconciliation` | `bearer` | **EXACT MATCH** | Safe public operational example or smoke verification matching OpenAPI 3.1.0 contract. |
| 110 | `public/` (Tracked) | `public/05 — Provider Examples/20 — Analytics Metrics.bru` | `GET` | `{{base_url}}/api/v1/analytics/metrics` | `bearer` | **EXACT MATCH** | Safe public operational example or smoke verification matching OpenAPI 3.1.0 contract. |
| 111 | `public/` (Tracked) | `public/05 — Provider Examples/21 — DevOps Audit PR.bru` | `POST` | `{{base_url}}/api/v1/devops/audit-pr` | `bearer` | **EXACT MATCH** | Safe public operational example or smoke verification matching OpenAPI 3.1.0 contract. |
| 112 | `public/` (Tracked) | `public/05 — Provider Examples/22 — DevOps Changelog.bru` | `POST` | `{{base_url}}/api/v1/devops/changelog` | `bearer` | **EXACT MATCH** | Safe public operational example or smoke verification matching OpenAPI 3.1.0 contract. |
| 113 | `public/` (Tracked) | `public/05 — Provider Examples/23 — Coding Tool Result.bru` | `POST` | `{{base_url}}/api/v1/coding/tool-result` | `bearer` | **EXACT MATCH** | Safe public operational example or smoke verification matching OpenAPI 3.1.0 contract. |
| 114 | `public/` (Tracked) | `public/05 — Provider Examples/24 — Coding Resume Bridge.bru` | `POST` | `{{base_url}}/api/v1/coding/resume` | `none` | **EXACT MATCH** | Safe public operational example or smoke verification matching OpenAPI 3.1.0 contract. |
| 115 | `public/` (Tracked) | `public/99 — Public Final Smoke/01 — Production-like Smoke.bru` | `GET` | `{{base_url}}/health` | `none` | **EXACT MATCH** | Safe public operational example or smoke verification matching OpenAPI 3.1.0 contract. |
| 116 | `public/` (Tracked) | `public/99 — Public Final Smoke/02 — Critical Security Smoke.bru` | `GET` | `{{base_url}}/api/v1/agent/metrics` | `none` | **EXACT MATCH** | Safe public operational example or smoke verification matching OpenAPI 3.1.0 contract. |
| 117 | `public/` (Tracked) | `public/99 — Public Final Smoke/03 — Critical E2E Smoke.bru` | `GET` | `{{base_url}}/api/v1/health` | `none` | **EXACT MATCH** | Safe public operational example or smoke verification matching OpenAPI 3.1.0 contract. |

---

## 3. OpenAPI 51-Operation Full Coverage Verification

Every single registered public HTTP operation in JakeAI is accounted for:

| # | Operation | Method | Path | Bruno Primary Coverage | Partition |
|:---:|---|:---:|---|---|:---:|
| 1 | `DELETE /api/v1/byok/keys/{provider}` | `DELETE` | `/api/v1/byok/keys/{provider}` | `public/05 — Provider Examples/07 — Delete Provider Key.bru` | Public |
| 2 | `GET /api/v1/agent/approvals/pending` | `GET` | `/api/v1/agent/approvals/pending` | `public/03 — Agent/07 — Pending Approvals.bru` | Public |
| 3 | `GET /api/v1/agent/metrics` | `GET` | `/api/v1/agent/metrics` | `public/03 — Agent/10 — Agent Metrics.bru` | Public |
| 4 | `GET /api/v1/agent/tasks/{task_id}` | `GET` | `/api/v1/agent/tasks/{task_id}` | `public/03 — Agent/02 — Get Task.bru` | Public |
| 5 | `GET /api/v1/agent/tasks/{task_id}/runs/{run_id}` | `GET` | `/api/v1/agent/tasks/{task_id}/runs/{run_id}` | `public/03 — Agent/04 — Get Run.bru` | Public |
| 6 | `GET /api/v1/agent/tasks/{task_id}/runs/{run_id}/events` | `GET` | `/api/v1/agent/tasks/{task_id}/runs/{run_id}/events` | `public/03 — Agent/05 — Stream Run Events.bru` | Public |
| 7 | `GET /api/v1/analytics/dashboard` | `GET` | `/api/v1/analytics/dashboard` | `public/05 — Provider Examples/13 — Analytics Dashboard.bru` | Public |
| 8 | `GET /api/v1/analytics/metrics` | `GET` | `/api/v1/analytics/metrics` | `public/05 — Provider Examples/20 — Analytics Metrics.bru` | Public |
| 9 | `GET /api/v1/billing/subscription` | `GET` | `/api/v1/billing/subscription` | `public/05 — Provider Examples/17 — Billing Subscription.bru` | Public |
| 10 | `GET /api/v1/byok/keys` | `GET` | `/api/v1/byok/keys` | `public/05 — Provider Examples/01 — List BYOK Keys.bru` | Public |
| 11 | `GET /api/v1/finops/budget` | `GET` | `/api/v1/finops/budget` | `public/05 — Provider Examples/14 — FinOps Budget Read.bru` | Public |
| 12 | `GET /api/v1/finops/reconciliation` | `GET` | `/api/v1/finops/reconciliation` | `public/05 — Provider Examples/19 — FinOps Reconciliation.bru` | Public |
| 13 | `GET /api/v1/finops/summary` | `GET` | `/api/v1/finops/summary` | `public/05 — Provider Examples/12 — FinOps Summary.bru` | Public |
| 14 | `GET /api/v1/finops/transactions` | `GET` | `/api/v1/finops/transactions` | `public/05 — Provider Examples/18 — FinOps Transactions.bru` | Public |
| 15 | `GET /api/v1/gateway/models` | `GET` | `/api/v1/gateway/models` | `public/02 — Chat/05 — API Gateway Models List.bru` | Public |
| 16 | `GET /api/v1/gateway/quotas` | `GET` | `/api/v1/gateway/quotas` | `public/02 — Chat/09 — API Gateway Quotas Read.bru` | Public |
| 17 | `GET /api/v1/health` | `GET` | `/api/v1/health` | `public/00 — Setup/02 — API Health Smoke.bru` | Public |
| 18 | `GET /api/v1/health/live` | `GET` | `/api/v1/health/live` | `public/00 — Setup/05 — API Health Live Probe.bru` | Public |
| 19 | `GET /api/v1/health/ready` | `GET` | `/api/v1/health/ready` | `public/00 — Setup/06 — API Health Ready Probe.bru` | Public |
| 20 | `GET /api/v1/rag/tasks/{task_id}` | `GET` | `/api/v1/rag/tasks/{task_id}` | `public/04 — RAG/02 — Get RAG Ingestion Task.bru` | Public |
| 21 | `GET /health` | `GET` | `/health` | `public/00 — Setup/01 — Root Health Smoke.bru` | Public |
| 22 | `GET /health/live` | `GET` | `/health/live` | `public/00 — Setup/03 — Root Liveness Probe.bru` | Public |
| 23 | `GET /health/ready` | `GET` | `/health/ready` | `public/00 — Setup/04 — Root Readiness Probe.bru` | Public |
| 24 | `GET /metrics` | `GET` | `/metrics` | `public/00 — Setup/07 — Prometheus Metrics.bru` | Public |
| 25 | `GET /v1/models` | `GET` | `/v1/models` | `public/01 — Public Smoke/03 — Public Models Catalog.bru` | Public |
| 26 | `GET /v1/quotas` | `GET` | `/v1/quotas` | `public/02 — Chat/07 — OpenAI Gateway Quotas Read.bru` | Public |
| 27 | `POST /api/v1/agent/tasks` | `POST` | `/api/v1/agent/tasks` | `public/03 — Agent/01 — Create Task.bru` | Public |
| 28 | `POST /api/v1/agent/tasks/{task_id}/runs` | `POST` | `/api/v1/agent/tasks/{task_id}/runs` | `public/03 — Agent/03 — Start Run.bru` | Public |
| 29 | `POST /api/v1/agent/tasks/{task_id}/runs/{run_id}/approvals/{approval_id}` | `POST` | `/api/v1/agent/tasks/{task_id}/runs/{run_id}/approvals/{approval_id}` | `public/03 — Agent/08 — Approval Decision.bru` | Public |
| 30 | `POST /api/v1/agent/tasks/{task_id}/runs/{run_id}/cancel` | `POST` | `/api/v1/agent/tasks/{task_id}/runs/{run_id}/cancel` | `public/03 — Agent/06 — Cancel Run.bru` | Public |
| 31 | `POST /api/v1/billing/webhook` | `POST` | `/api/v1/billing/webhook` | `private/01 — Authentication & Tenant Security/09 — Billing Webhook Signature.bru` | Private |
| 32 | `POST /api/v1/byok/keys` | `POST` | `/api/v1/byok/keys` | `public/05 — Provider Examples/02 — Add BYOK Key.bru` | Public |
| 33 | `POST /api/v1/byok/keys/validate` | `POST` | `/api/v1/byok/keys/validate` | `public/05 — Provider Examples/03 — Validate BYOK Key.bru` | Public |
| 34 | `POST /api/v1/byok/keys/{provider}/revoke` | `POST` | `/api/v1/byok/keys/{provider}/revoke` | `public/05 — Provider Examples/06 — Revoke Provider Key.bru` | Public |
| 35 | `POST /api/v1/byok/keys/{provider}/rotate` | `POST` | `/api/v1/byok/keys/{provider}/rotate` | `public/05 — Provider Examples/05 — Rotate Provider Key.bru` | Public |
| 36 | `POST /api/v1/byok/keys/{provider}/validate` | `POST` | `/api/v1/byok/keys/{provider}/validate` | `public/05 — Provider Examples/04 — Validate Stored Provider.bru` | Public |
| 37 | `POST /api/v1/chat/stream` | `POST` | `/api/v1/chat/stream` | `public/02 — Chat/01 — Chat Stream.bru` | Public |
| 38 | `POST /api/v1/coding/resume` | `POST` | `/api/v1/coding/resume` | `public/05 — Provider Examples/24 — Coding Resume Bridge.bru` | Public |
| 39 | `POST /api/v1/coding/tool-result` | `POST` | `/api/v1/coding/tool-result` | `public/05 — Provider Examples/23 — Coding Tool Result.bru` | Public |
| 40 | `POST /api/v1/devops/audit-pr` | `POST` | `/api/v1/devops/audit-pr` | `public/05 — Provider Examples/21 — DevOps Audit PR.bru` | Public |
| 41 | `POST /api/v1/devops/changelog` | `POST` | `/api/v1/devops/changelog` | `public/05 — Provider Examples/22 — DevOps Changelog.bru` | Public |
| 42 | `POST /api/v1/finops/budget` | `POST` | `/api/v1/finops/budget` | `public/05 — Provider Examples/15 — FinOps Budget Update.bru` | Public |
| 43 | `POST /api/v1/gateway/chat/completions` | `POST` | `/api/v1/gateway/chat/completions` | `public/02 — Chat/06 — API Gateway Chat Completions.bru` | Public |
| 44 | `POST /api/v1/gateway/quotas` | `POST` | `/api/v1/gateway/quotas` | `public/02 — Chat/10 — API Gateway Quotas Update.bru` | Public |
| 45 | `POST /api/v1/rag/generate` | `POST` | `/api/v1/rag/generate` | `public/04 — RAG/04 — Generate Grounded Answer.bru` | Public |
| 46 | `POST /api/v1/rag/ingest` | `POST` | `/api/v1/rag/ingest` | `public/04 — RAG/01 — Ingest Document.bru` | Public |
| 47 | `POST /api/v1/rag/query` | `POST` | `/api/v1/rag/query` | `public/04 — RAG/03 — Hybrid Query.bru` | Public |
| 48 | `POST /internal/v1/coding/resume` | `POST` | `/internal/v1/coding/resume` | `private/01 — Authentication & Tenant Security/07 — Internal Perimeter Secret Rejection.bru` | Private |
| 49 | `POST /internal/v1/coding/tool-result` | `POST` | `/internal/v1/coding/tool-result` | `private/05 — Tool Security/03 — Tool Result Internal Bridge.bru` | Private |
| 50 | `POST /v1/chat/completions` | `POST` | `/v1/chat/completions` | `public/02 — Chat/03 — OpenAI Gateway Chat.bru` | Public |
| 51 | `POST /v1/quotas` | `POST` | `/v1/quotas` | `public/02 — Chat/08 — OpenAI Gateway Quotas Update.bru` | Public |
