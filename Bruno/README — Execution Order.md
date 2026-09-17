# Recommended Execution Order

The reconciled Bruno collection can be executed either automatically via the `@usebruno/cli` Python runner or sequentially by a reviewer:

## 1. Automated CLI Execution Profiles

The Python test runner (`scripts/run_bruno_tests.py`) governs test profiles, external dependency checks, and reporting:

```bash
# 1. Fastest confidence smoke gate (<5s, public perimeter endpoints)
python scripts/run_bruno_tests.py --suite public-smoke
# or with backend auto-start:
python scripts/run_bruno_tests.py --suite public-smoke --auto-start

# 2. Complete public collection (all 51 endpoints non-destructive paths)
python scripts/run_bruno_tests.py --suite public-full

# 3. Security, negative boundary, and tenant isolation suite
python scripts/run_bruno_tests.py --suite private-security

# 4. Full private suite (security, failure & recovery, mock providers)
python scripts/run_bruno_tests.py --suite private-full

# 5. Core business workflows & PR gate (public + private E2E flows)
python scripts/run_bruno_tests.py --suite critical-e2e

# 6. Live release verification (mandates online FinnApiGo and provider keys)
python scripts/run_bruno_tests.py --suite live-release

# 7. Run a single folder or single request
python scripts/run_bruno_tests.py --folder "public/03 — Agent"
python scripts/run_bruno_tests.py --request "public/01 — Public Smoke/01 — Health Smoke.bru"
```

Test reports are automatically produced in `backend/reports/bruno/` as JSON, JUnit XML, and Markdown summary files.

---

## 2. Public Collection Execution Order (`Bruno/public/`)

Execute these phases sequentially for safe, non-destructive public verification:

### PHASE 1: `00 — Setup & Environment` & `01 — Public Smoke`
1. Run `01 — Health Smoke.bru` → Verify `200 OK` and `status == "healthy"`.
2. Run `02 — Readiness Check.bru` → Verify `200 OK` with database, redis, and qdrant readiness.
3. Run `03 — Configuration & Metrics.bru` → Verify Prometheus metric scrape returns text payload.

### PHASE 2: `02 — Chat & Gateway`
1. Run `01 — Basic Chat.bru` → Send standard completions request, verify response choice.
2. Run `02 — Chat Validation.bru` → Verify schema bounds.
3. Run `03 — Chat Streaming.bru` → Connect to SSE stream and observe event frames.
4. Run `04 — Gateway Chat.bru` → Verify OpenAI compatibility `/v1/chat/completions`.
5. Run `05 — Provider List.bru` → Verify `/v1/models` returns model catalog.

### PHASE 3: `03 — Agent`
1. Run `01 — Create Task.bru` → Creates task and captures `{{task_id}}`.
2. Run `02 — Get Task.bru` → Retrieves task status and verifies ID.
3. Run `03 — Start Run.bru` → Instantiates run execution and captures `{{run_id}}`.
4. Run `04 — Get Run.bru` → Retrieves run details and state.
5. Run `05 — Stream Run Events.bru` → Subscribes to SSE event stream.
6. Run `06 — Cancel Run.bru` → Idempotently cancels run.
7. Run `07 — Pending Approvals.bru` → Inspects approvals and captures `{{approval_id}}`.
8. Run `08 — Approval Decision.bru` → Submits approval decision.
9. Run `09 — Coding Resume.bru` → Resumes coding task via perimeter secret.

### PHASE 4: `04 — RAG`
1. Run `01 — Ingest Document.bru` → Submits document and captures `{{rag_task_id}}`.
2. Run `02 — Get RAG Task.bru` → Verifies async ingestion progression.
3. Run `03 — Query.bru` → Executes hybrid dense+sparse retrieval.
4. Run `04 — Generate Grounded Answer.bru` → Verifies citations envelope and abstention contract.

### PHASE 5: `05 — Provider Examples`
1. Run `01 — List BYOK Keys.bru` → Lists masked keys.
2. Run `02 — Add BYOK Key.bru` → Adds encrypted key to AES vault.
3. Run `03 — Validate BYOK Key.bru` → Probes key health validation.

### PHASE 6: `99 — Public Final Smoke`
1. Run `01 — Final Smoke Health.bru` → Final unauthenticated sanity check.
2. Run `02 — Final Smoke Chat.bru` → Final chat gate.
3. Run `03 — Final Smoke Agent.bru` → Final agent gate.
4. Run `04 — Final Smoke RAG.bru` → Final RAG gate.

---

## 3. Private Collection Execution Order (`Bruno/private/`)

Execute these phases in an isolated dev or staging environment:

### PHASE 7: `01 — Auth & Tenant`
1. Run `01 — Missing Token.bru` → Asserts `401 Unauthorized`.
2. Run `02 — Tampered Token.bru` → Asserts `401 Unauthorized`.
3. Run `03 — Expired Token.bru` → Asserts `401 Unauthorized`.
4. Run `04 — Insufficient Role.bru` → Asserts `403 Forbidden`.

### PHASE 8: `02 — Security & Negative`
1. Run `01 — Prompt Injection Probe.bru` → Asserts security guardrail deflection.
2. Run `02 — Path Traversal Attempt.bru` → Asserts input validation blocks traversal.
3. Run `03 — Payload Too Large.bru` → Asserts `413 Payload Too Large`.
4. Run `04 — Negative Parameter Bounds.bru` → Asserts `422 Unprocessable Entity`.

### PHASE 9: `03 — Failure & Recovery`
1. Run `01 — Upstream Provider 503.bru` → Asserts graceful failover or structured error.
2. Run `02 — Upstream Timeout 408.bru` → Asserts client timeout handling.
3. Run `03 — Cancel State Machine Race.bru` → Asserts idempotent state transitions.

### PHASE 10: `04 — Cross Tenant`
1. Run `01 — Cross-Tenant Task Isolation.bru` → Asserts Tenant B cannot access Tenant A's task (`404 Not Found`).
2. Run `02 — Cross-Tenant RAG Isolation.bru` → Asserts Tenant B cannot retrieve Tenant A's private knowledge base.
3. Run `03 — Cross-Tenant Cache Isolation.bru` → Asserts Tenant B cannot read Tenant A's cached prompt responses.

### PHASE 11: `05 — Tool Security`
1. Run `01 — Restricted Tool Blocked.bru` → Asserts forbidden tool invocation is rejected.

### PHASE 12: `06 — Live Provider` & `07 — Live FinnApiGo` (Live Profile Only)
1. Run `01 — Live FinnApiGo Auth Probe.bru` → Validates live token exchange when FinnApiGo daemon is up.
2. Run `01 — Live Provider Completion.bru` → Validates real cloud LLM inference when API keys are configured.
