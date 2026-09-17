# JakeAI — Public Bruno API Collection Guide

## 1. Overview & Purpose
The `Bruno/public/` collection is the official, shareable, version-controlled Bruno API test and documentation suite for the **JakeAI Universal AI Engineering Worker**.

- **Git-Tracked & Safe**: All files in `Bruno/public/` are committed to the repository and safe for distribution.
- **Zero Real Secrets**: Contains only synthetic mock dev tokens, placeholder environment variables, and public test schemas. No production API keys, customer PII, live FinnApiGo secrets, or destructive payloads exist in this tree.
- **Authoritative Coverage**: Exercises all public, perimeter, and standard tenant workflows across the 51 authoritative OpenAPI operations in JakeAI.
- **CI/CD Ready**: Serves as the primary PR gate and deployment verification suite.

---

## 2. Directory Structure & Folder Map

```
Bruno/public/
├── 00 — Setup & Environment/          (Public health, liveness, readiness, metrics probes)
├── 01 — Public Smoke/                 (Critical health and unauthenticated perimeter checks)
├── 02 — Chat & Gateway/               (OpenAI gateway completions, SSE streaming, model catalogs)
├── 03 — Agent/                        (Task DAG, Run state machine, SSE events, human approvals)
├── 04 — RAG/                          (Ingestion pipeline, polling, hybrid retrieval, grounded answers)
├── 05 — Provider Examples/            (BYOK masked listing, AES vault registration, validation)
└── 99 — Public Final Smoke/           (Non-destructive release smoke gate)
```

### Folder Breakdown:
1. **`00 — Setup & Environment`**:
   - `01 — Health Smoke.bru`: Verifies root `/health` returns `200 OK` and system status `healthy`.
   - `02 — Readiness Check.bru`: Verifies root `/health/ready` ensures database, redis, and vector stores are reachable.
   - `03 — Configuration & Metrics.bru`: Probes `/metrics` for Prometheus scrapers and telemetry counters.
2. **`01 — Public Smoke`**:
   - Fast sanity checks for all perimeter health endpoints (`/health`, `/health/live`, `/health/ready`, `/metrics`, `/api/v1/health`, `/api/v1/health/live`, `/api/v1/health/ready`).
3. **`02 — Chat & Gateway`**:
   - OpenAI-compatible `/v1/chat/completions` and `/api/v1/chat`.
   - Real-time Server-Sent Events (SSE) streaming via `/api/v1/chat/stream`.
   - Model discovery and provider health via `/v1/models`.
4. **`03 — Agent`**:
   - Task creation and DAG management (`POST /api/v1/agent/tasks`, `GET /api/v1/agent/tasks/{task_id}`).
   - Run lifecycle execution (`POST /api/v1/agent/tasks/{task_id}/runs`).
   - Real-time run telemetry stream (`GET /api/v1/agent/tasks/{task_id}/runs/{run_id}/events`).
   - Human-in-the-loop approval workflows (`GET /api/v1/agent/approvals`, `POST /api/v1/agent/approvals/{approval_id}`).
   - Asynchronous coding engine task resumption (`POST /api/v1/coding/resume`).
5. **`04 — RAG`**:
   - Asynchronous document ingestion and task tracking (`POST /api/v1/rag/ingest`, `GET /api/v1/rag/tasks/{task_id}`).
   - Hybrid dense/sparse vector search (`POST /api/v1/rag/query`).
   - Grounded generation with citation envelopes and verifiable abstention (`POST /api/v1/rag/answer`).
6. **`05 — Provider Examples`**:
   - Vault listing and configuration for BYOK providers (`GET /api/v1/providers/keys`, `POST /api/v1/providers/keys`).
   - Key health validation (`POST /api/v1/providers/keys/validate`).
7. **`99 — Public Final Smoke`**:
   - Comprehensive end-to-end non-destructive smoke verification across chat, agent, and RAG services.

---

## 3. Environment Variables & Setup

The public collection uses the environment file `Bruno/environments/Local.bru`:

| Variable | Default Value | Description |
|---|---|---|
| `base_url` | `http://localhost:8000` | JakeAI FastAPI backend URL |
| `finnapigo_base_url` | `http://localhost:8081` | FinnApiGo backend URL (mock or live) |
| `token_a` | `eyJhbGciOiJIUzI1Ni...` | Synthetic dev JWT for Tenant A (`default`, sub `16`, role `admin`) |
| `tenant_a` | `default` | Primary test tenant identifier |
| `correlation_id` | `cid-public-001` | Tracing correlation header (`X-Correlation-ID`) |
| `task_id` | `task-12345` | Dynamically captured by `03-01 Create Task` |
| `run_id` | `run-12345` | Dynamically captured by `03-03 Start Run` |
| `approval_id` | `appr-12345` | Dynamically captured by `03-07 Pending Approvals` |
| `rag_task_id` | `rag-12345` | Dynamically captured by `04-01 Ingest Document` |

> [!NOTE]
> All tokens in `Local.bru` are synthetic local development tokens signed with standard dev test keys (`dev-jwt-secret-key-change-in-production-1234567890`). They provide zero access to any live cloud or production environment.

---

## 4. Automated Execution Commands

You can execute the public collection using the automated Python CLI runner (`scripts/run_bruno_tests.py`):

```bash
# 1. Fast Public Smoke Suite (<5 seconds, non-destructive perimeter sanity)
python scripts/run_bruno_tests.py --suite public-smoke

# 2. Complete Public Suite (all public, chat, agent, RAG, provider examples)
python scripts/run_bruno_tests.py --suite public-full

# 3. Target a specific public folder
python scripts/run_bruno_tests.py --folder "public/02 — Chat & Gateway"

# 4. Target a specific request file
python scripts/run_bruno_tests.py --request "public/01 — Public Smoke/01 — Health Smoke.bru"
```

### Auto-Starting Backend
If the JakeAI server is not already running, pass `--auto-start` to let the runner automatically launch `uvicorn app.main:app` in the background and terminate it upon test completion:

```bash
python scripts/run_bruno_tests.py --suite public-smoke --auto-start
```

---

## 5. CI/CD Integration

In CI pipelines (GitHub Actions, GitLab CI), the public smoke and full suites run as required status checks:

```yaml
# Example GitHub Actions step
- name: Run Bruno Public Smoke
  run: |
    python scripts/run_bruno_tests.py --suite public-smoke --auto-start --format junit
  env:
    ENVIRONMENT: local

- name: Publish Test Results
  uses: EnricoMi/publish-unit-test-result-action@v2
  if: always()
  with:
    junit_files: backend/reports/bruno/*.xml
```

---

## 6. Security Disclaimer & Invariants

> [!IMPORTANT]
> - **Zero Sensitive Attack Payloads**: Prompt injections, SQLi, traversal strings, and credential tampering requests are strictly isolated in `Bruno/private/` and are NOT present in `Bruno/public/`.
> - **Public Contract**: Public requests must always return valid HTTP status codes (`200 OK`, `201 Created`, or well-defined client validation `422 Unprocessable Entity` for intentional boundary checks).
> - **Zero Secrets Committed**: Verified by continuous automated Gitleaks scans (`gitleaks detect --config .gitleaks.toml`).
