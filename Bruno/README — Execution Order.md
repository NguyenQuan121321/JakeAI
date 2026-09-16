# Recommended Execution Order

The Bruno collection can be executed either automatically via the `@usebruno/cli` runner or sequentially by a human reviewer:

## Automated CLI Execution (TEST-08)

You can execute the entire collection or specific profiles using the automated test runner:

```bash
# Fastest confidence smoke (<10s)
python scripts/run_bruno_tests.py --suite smoke
# or: make bruno-smoke
# or: npm run test:bruno:smoke

# Core business flows & PR gate
python scripts/run_bruno_tests.py --suite critical-e2e
# or: make bruno-e2e
# or: npm run test:bruno:e2e

# Full 85-request collection
python scripts/run_bruno_tests.py --suite full
# or: make bruno-full
# or: npm run test:bruno

# Live release verification (mandates online FinnApiGo and provider keys)
python scripts/run_bruno_tests.py --suite live-release
# or: make bruno-live

# Run a single folder or single request
python scripts/run_bruno_tests.py --folder "03 — Agent"
python scripts/run_bruno_tests.py --request "00 — Setup & Environment/01 — Health Smoke.bru"
```

Reports are automatically generated in `backend/reports/bruno/` as JSON, JUnit XML, and Markdown summary.

---

## Manual Sequential Execution Phases

## PHASE 1: 00 — Setup & Environment
1. Run `01 — Health Smoke` → Verify `200 OK` and `status == "healthy"`.
2. Run `02 — Configuration Check` → Verify version `0.1.0` and API status `healthy`.
3. Run `03 — Authentication Dependency Check` → Probe FinnApiGo status.

## PHASE 2: 01 — Authentication & Tenant
1. Run `01 — FinnApiGo Login` → Capture live `token_a` (or use local dev token).
2. Run `02 — Store Access Token` → Verify token presence.
3. Run `03 — JakeAI Authenticated Health` → Verify correlation ID propagation.
4. Run `04 — Tenant Context` → Verify tenant claim extraction.
5. Run `05 — Unauthorized Request` → Verify `401 Unauthorized` on missing token.
6. Run `06 — Invalid Token` → Verify `401 Unauthorized` on tampered token.
7. Run `07 — Expired Token` → Verify `401 Unauthorized` on expired token.
8. Run `08 — Cross Tenant - Authorization` → Verify `404 Not Found` across tenant boundaries.

## PHASE 3: 02 — Chat & Gateway
1. Run `01 — Basic Chat` → Send standard completions request.
2. Run `02 — Chat Validation` → Verify `422 Unprocessable Entity` on invalid bounds.
3. Run `03 — Chat Streaming` → Connect to SSE stream and observe event frames.
4. Run `04 — Gateway Chat` → Verify root `/v1/chat/completions` OpenAI compatibility.
5. Run `05 — Provider List` → Verify model catalog returns available models.
6. Run `06 — Provider Health` → Verify root `/v1/models` route.
7. Run `07 — Gateway Failure Cases` → Verify negative parameters rejection.

## PHASE 4: 03 — Agent
1. Run `01 — Create Task` → Creates task and captures `{{task_id}}`.
2. Run `02 — Get Task` → Retrieves task details.
3. Run `03 — Start Run` → Instantiates execution run and captures `{{run_id}}`.
4. Run `04 — Get Run` → Retrieves run status.
5. Run `05 — Stream Run Events` → Subscribes to SSE execution stream.
6. Run `06 — Cancel Run` → Cancels run idempotently.
7. Run `07 — Pending Approvals` → Inspects pending approval gates and captures `{{approval_id}}`.
8. Run `08 — Approval Decision` → Submits human approval decision.
9. Run `09 — Resume After Approval` → Verifies resumed progression.
10. Run `10 — Agent Metrics` → Verifies telemetry counters.

## PHASE 5: 04 — RAG
1. Run `01 — Ingest Document` → Submits document and captures `{{rag_task_id}}`.
2. Run `02 — Get RAG Task` → Polls ingestion task status.
3. Run `03 — Query` → Executes hybrid dense+sparse retrieval.
4. Run `04 — Generate Grounded Answer` → Generates answer with citations.
5. Run `05 — Citation Verification` → Verifies citation tags and envelope tokens.
6. Run `06 — No Evidence - Abstention` → Verifies deterministic abstention.
7. Run `07 — Cross Tenant RAG Isolation` → Verifies Tenant B cannot view Tenant A chunks.

## PHASE 6: 05 — BYOK & Providers
1. Run `01 — List BYOK Keys` → Lists masked keys.
2. Run `02 — Add BYOK Key` → Adds encrypted key to AES-256-GCM vault.
3. Run `03 — Validate BYOK Key` → Probes key validity.
4. Run `04 — Validate Stored Provider` → Probes stored provider key.
5. Run `05 — Rotate Provider Key` → Rotates key atomically.
6. Run `06 — Revoke Provider Key` → Transitions key to revoked.
7. Run `07 — Delete Provider Key` → Purges key from vault.

## PHASE 7: 06 — Cache
1. Run `01 — Exact Cache Miss` → First request: `cached == false`.
2. Run `02 — Exact Cache Hit` → Identical request: `cached == true`.
3. Run `03 — Cache Identity Isolation` → Tenant B sends same request: `cached == false`.
4. Run `04 — Semantic Cache` → Semantic paraphrase test.
5. Run `05 — Cache Parameter Isolation` → Temperature difference: `cached == false`.
6. Run `06 — Cache - Provider Failure Behavior` → Verifies failure responses not cached.

## PHASE 8: 07 — FinOps & Billing
1. Run `01 — Costs` → Retrieves baseline and actual cost summary.
2. Run `02 — Recommendations` → Inspects dashboard token efficiency.
3. Run `03 — Budget Read` → Retrieves active token quota.
4. Run `04 — Budget Update` → Configures token quota ceiling.
5. Run `05 — Usage Accounting` → Compares local estimates against provider truth.
6. Run `06 — Billing Subscription` → Verifies subscription tier.

## PHASE 9: 08 — Security & Negative
1. Run `01` to `11` → Proves rejection of missing auth, invalid tokens, injection, and oversized payloads.

## PHASE 10: 09 — Failure & Recovery
1. Run `01` to `09` → Proves timeout normalization, retries, failovers, and cancel state invariants.

## PHASE 11: 10 — Cross System E2E
1. Run `01` to `08` → Executes complete end-to-end integration workflows.

## PHASE 12: 99 — Final Smoke
1. Run `01 — Production-like Smoke` → Production readiness smoke.
2. Run `02 — Critical Security Smoke` → Security perimeter smoke.
3. Run `03 — Critical E2E Smoke` → Critical path smoke.
