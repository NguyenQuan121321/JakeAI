# JakeAI — Final Manual Verification Suite (Bruno)

## 1. Overview
This Bruno collection provides an authoritative, deterministic, end-to-end manual verification suite for the **JakeAI Universal AI Engineering Worker**, designed for the final post-RIGHT verification phase.

The collection enables human reviewers, security auditors, and release engineers to manually verify:
1. What endpoints JakeAI exposes (51 OpenAPI routes).
2. How the system operates and coordinates agents, tools, and RAG.
3. How dependencies (PostgreSQL, Redis, Qdrant, FinnApiGo) integrate.
4. How authentication and multi-tenant isolation are enforced.
5. How Agent workflows operate as a verifiable state machine.
6. How RAG operates (Ingest → Index → Hybrid Retrieve → Ground → Abstain).
7. How BYOK and model providers operate with AES-256-GCM encryption.
8. How Tier 1 (Redis) and Tier 2 (Qdrant) caches operate.
9. How FinOps, token accounting, and budget caps operate.
10. How failures, timeouts, retries, and failovers are normalized.
11. How security boundaries, jailbreaks, and injection attacks are blocked.
12. How all major cross-system workflows connect together.

---

## 2. Directory Structure & Phased Workflow
The workspace is organized into 12 distinct human workflow folders:

```
JakeAI/
├── 00 — Setup & Environment/          (Health, readiness, and upstream dependency checks)
├── 01 — Authentication & Tenant/      (JWT login, claims, token storage, 401/403/expired)
├── 02 — Chat & Gateway/               (OpenAI gateway, validation, SSE streaming, model list)
├── 03 — Agent/                        (Task DAG, Run lifecycle, SSE events, approvals, metrics)
├── 04 — RAG/                          (Ingestion, async polling, hybrid query, grounded answer)
├── 05 — BYOK & Providers/             (AES vault, register, validate, rotate, revoke, delete)
├── 06 — Cache/                        (Tier 1 miss/hit, Tier 2 semantic, identity isolation)
├── 07 — FinOps & Billing/             (Token ledger, costs, budget read/update, PayOS billing)
├── 08 — Security & Negative/          (Jailbreak injection, traversal, 413, 422, negative bounds)
├── 09 — Failure & Recovery/           (Provider 408/503, failover, cancel race, disconnect)
├── 10 — Cross System E2E/             (Complete cross-cutting end-to-end integration flows)
└── 99 — Final Smoke/                  (Production, security, and critical path smoke gates)
```

---

## 3. Prerequisite Services & Port Map
| Service | Host & Port | Purpose | Required For | Local Fallback Behavior |
|---|---|---|---|---|
| **JakeAI Backend** | `http://localhost:8000` | Core API & Agent Engine | All tests | Mandatory (Start with `uv run uvicorn app.main:app`) |
| **FinnApiGo Backend** | `http://localhost:8081` | Identity & Core Banking | `01-01` login probe | Pre-computed dev JWTs in `Local.bru` allow all JakeAI tests to pass |
| **Redis 7** | `localhost:6379` | Exact cache, locks, quota | Tier 1 Cache, locks | `degraded_fallback_active` (in-memory cache & critical sections) |
| **Qdrant** | `localhost:6333` | Dense vectors (384-d) | Tier 2 Semantic Cache | In-memory Qdrant / FastEmbed local ONNX |
| **Commercial LLMs** | Cloud APIs | Live upstream generation | Real inference | Test doubles / offline fallback responses |

---

## 4. Environment Variables & Runtime Strategy
The collection is configured via `environments/Local.bru`:
- `base_url`: `http://localhost:8000`
- `finnapigo_base_url`: `http://localhost:8081`
- `token_a`: Dev JWT for Tenant A (`default`, sub `16`, role `admin`, permissions `["*"]`).
- `token_b`: Dev JWT for Tenant B (`tenant_beta`, sub `user-beta`, role `user`, permissions `["read"]`).
- `token_expired`: Expired JWT with past `exp` timestamp.
- `tenant_a`: `default`
- `tenant_b`: `tenant_beta`
- `task_id`: Captured dynamically by `03 — Agent/01 — Create Task`.
- `run_id`: Captured dynamically by `03 — Agent/03 — Start Run`.
- `rag_task_id`: Captured dynamically by `04 — RAG/01 — Ingest Document`.
- `approval_id`: Captured dynamically by `03 — Agent/07 — Pending Approvals`.
- `correlation_id`: `cid-manual-e2e-001` (propagated across all requests).

---

## 5. Interpreting Test Results
- **PASS**: The request returned expected HTTP status, validated response schema, verified non-empty IDs, and satisfied invariants.
- **FAIL**: Status code mismatch, unexpected error structure, or invariant violation. Document using the Defect Reporting Template below.
- **BLOCKED**: An external dependency (e.g. live FinnApiGo daemon or real credit card webhook) is not available. Check the Local Fallback column above.

---

## 6. Defect Reporting Template
When reporting any defect during manual verification, record:

```
BRUNO TEST:           [Folder / Request Name, e.g. 03 — Agent/06 — Cancel Run]
EXPECTED:             [Expected HTTP status code and response payload structure]
ACTUAL:               [Actual HTTP status code and response payload received]
STATUS CODE:          [e.g. 500 instead of 404]
REQUEST:              [HTTP Method, URL, Headers, and Body]
RESPONSE:             [Exact response headers and JSON body]
CORRELATION ID:       [X-Correlation-ID header value]
TENANT:               [tenant_a / tenant_b]
ROOT CAUSE:           [Identified software defect or invariant breach]
SEVERITY:             [CRITICAL / HIGH / MEDIUM / LOW]
REPRODUCIBLE:         [YES / NO — Steps to reproduce]
RELATED RIGHT TASK:   [e.g. R-FUNC-01, R-LOGIC-00]
RECOMMENDED FIX:      [Suggested code or configuration fix]
```
