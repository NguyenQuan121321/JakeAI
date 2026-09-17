# JakeAI — Final Manual Verification Suite (Bruno)

## 1. Overview
This Bruno collection provides an authoritative, deterministic, end-to-end manual and automated verification suite for the **JakeAI Universal AI Engineering Worker**, completely reconciled following `BRUNO-RECON-01`.

The suite enables software engineers, security auditors, and release engineers to verify:
1. **Full API Surface**: All 51 authoritative OpenAPI operations across 47 paths.
2. **Safe Public Workflows**: Tracked in git under `Bruno/public/` with zero committed secrets.
3. **Security & Chaos Boundaries**: Confined to gitignored `Bruno/private/` for adversarial, negative, and cross-tenant tests.
4. **Authentication & Multi-Tenant Isolation**: Verified across Tenant A (`default`) and Tenant B (`tenant_beta`).
5. **State Machines**: Task DAG creation, execution runs, cancel idempotency, and human approval gates.
6. **RAG Pipeline**: Ingest → Index → Hybrid Retrieve → Grounded Answers → Abstention.
7. **BYOK Key Management**: Masked listing, AES-256-GCM storage, and key validation.
8. **Resilience & Governance**: Normalized timeouts, circuit breakers, failover, and strict correlation tracing.

---

## 2. Directory Structure & Organization

The collection is partitioned into **Public** (shareable, git-tracked) and **Private** (confidential, gitignored):

```
Bruno/
├── environments/
│   └── Local.bru                       (Local dev variables & synthetic tokens)
├── public/                             [TRACKED IN GIT]
│   ├── 00 — Setup & Environment/       (Public health, liveness, readiness, metrics)
│   ├── 01 — Public Smoke/              (Fast perimeter sanity checks)
│   ├── 02 — Chat & Gateway/            (Completions, SSE streaming, model catalog)
│   ├── 03 — Agent/                     (Tasks, Runs, SSE run events, approvals, resume)
│   ├── 04 — RAG/                       (Ingest, status, hybrid query, grounded answer)
│   ├── 05 — Provider Examples/         (BYOK key listing, registration, validation)
│   └── 99 — Public Final Smoke/        (Non-destructive release smoke gate)
└── private/                            [GITIGNORED — UNTRACKED]
    ├── 01 — Auth & Tenant/             (401/403 negative tests, tampered/expired JWTs)
    ├── 02 — Security & Negative/       (Injections, path traversal, 413, schema fuzzing)
    ├── 03 — Failure & Recovery/        (Upstream 503/408, failovers, race conditions)
    ├── 04 — Cross Tenant/              (Cross-tenant task, run, RAG, and cache isolation)
    ├── 05 — Tool Security/             (Sandboxing, blocked tool execution)
    ├── 06 — Live Provider/             (Live OpenAI, Gemini, Anthropic BYOK testing)
    ├── 07 — Live FinnApiGo/            (Live FinnApiGo banking identity probe)
    └── 08 — Production Verification/   (Read-only post-deployment production gates)
```

---

## 3. Prerequisite Services & Port Map

| Service | Host & Port | Purpose | Local Fallback Behavior |
|---|---|---|---|
| **JakeAI Backend** | `http://localhost:8000` | Core API & Agent Engine | Start via `python scripts/run_bruno_tests.py --auto-start` |
| **FinnApiGo Backend** | `http://localhost:8081` | Identity & Core Banking | Synthetic dev JWTs in `Local.bru` enable complete offline execution |
| **Redis 7** | `localhost:6379` | Exact cache, locks, quota | In-memory cache & lock fallback when offline |
| **Qdrant** | `localhost:6333` | Dense vector store | In-memory Qdrant / FastEmbed fallback when offline |
| **Commercial LLMs** | Cloud APIs | Live upstream generation | Offline mock doubles provide deterministic synthetic completions |

---

## 4. Execution Profiles

The test runner (`scripts/run_bruno_tests.py`) supports 6 standard profiles:

| Profile | Command | Target Folders | Use Case |
|---|---|---|---|
| **`public-smoke`** | `python scripts/run_bruno_tests.py --suite public-smoke` | `public/00`, `public/01` | Fast PR gate (<5s) |
| **`public-full`** | `python scripts/run_bruno_tests.py --suite public-full` | All `public/*` | Pre-merge verification |
| **`private-security`**| `python scripts/run_bruno_tests.py --suite private-security` | `private/01`, `02`, `04`, `05` | Security audit & pentest |
| **`private-full`** | `python scripts/run_bruno_tests.py --suite private-full` | All `private/*` (excl. live) | Internal resilience audit |
| **`critical-e2e`** | `python scripts/run_bruno_tests.py --suite critical-e2e` | Key public & private E2E flows | Major release gate |
| **`live-release`** | `python scripts/run_bruno_tests.py --suite live-release` | `private/06`, `07`, `08` | Staging with live services |

---

## 5. Interpreting Test Results
- **PASS**: Expected HTTP status returned, schema validated, dynamic IDs captured, assertions satisfied.
- **FAIL**: Status code mismatch, schema invalid, or assertion failed. File defect using the template below.
- **BLOCKED**: Live external service unavailable during `--suite live-release`. In dev/offline profiles, dependencies fall back gracefully without blocking.

---

## 6. Defect Reporting Template
When reporting any defect during manual verification, record:

```text
BRUNO TEST:           [Folder / Request Name, e.g. public/03 — Agent/06 — Cancel Run.bru]
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
RECOMMENDED FIX:      [Suggested code or configuration fix]
```
