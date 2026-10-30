# J02 identity and authorization policy

Jake consumes Finn v1 access credentials using configured HS256 key IDs and canonical base64 signing bytes. Finn is authoritative for tenant, session, account state, credential versions and exact grants. Roles and headers do not add permissions. `default` is an ordinary tenant.

Production requires an authenticated verified-HTTPS `IDENTITY_STATE_URL` with a distinct `IDENTITY_STATE_KEY_ID` / `IDENTITY_STATE_SECRET`. Responses are bounded to 4 KiB, 3 seconds by default (maximum 5), and 16 concurrent requests by default. There is no cross-request positive cache and no local denylist outage fallback. Invalid/inactive access is 401, missing grants 403, unknown/unavailable state 503 and hidden foreign resources 404. Request-local checks are at most 10 seconds apart, with a fresh check before provider dispatch and protected retrieval/indexing/credential use. Capacity is limited by Finn's shared 120/s quota: exceeding it fails closed with 503; no capacity qualification is claimed.

Signing rotation uses `JWT_KEY_ID`, `JWT_PREVIOUS_KEY_ID` and an immutable UTC Unix `JWT_PREVIOUS_LAST_ISSUED_AT`. Previous verification ends at final old issuance +930 seconds, including after restart. No legacy bridge, header-directed key or service-to-user/OBO issuance is enabled.

BYOK retains exact grants plus owner/delegation restrictions and J03 error redaction. Budget mutation additionally requires delegated tenant administration. RAG ingestion overwrites caller owner metadata; retrieval excludes foreign/unowned chunks before reranking, context, generation or citations. Conversation threads include tenant and subject. Cache namespaces additionally bind session, JTI, versions and permissions. Existing unowned documents require authorized re-ingestion; they are hidden rather than assigned an invented owner.

RAM approval/checkpoint state cannot authorize durable execution. Approval/resume and queued ingestion return explicit unavailable errors until their durable authority adapters exist (J07/J08). File/shell/business mutation and webhook effects remain unsupported. Payment ingress verifies its existing HMAC but cannot activate a tenant subscription without a bound service contract. Read-only in-process runs remain bound to the verified route operation and fresh Finn state throughout their lifetime. Persisted permission snapshots cannot authorize a resumed effect. These disabled capabilities do not establish approval binding, atomic multi-worker consume, durable workflow, full document ACL lifecycle, provider quality or payment acceptance.

`/metrics` and readiness require the separate optional private `X-Operator-Secret`; absent provisioning hides them. User-facing process telemetry aliases are unavailable. No WebSocket user protocol is registered; attempted connections close with policy code 1008. Static documentation and liveness remain public.

## Complete registered HTTP policy inventory

| Method | Route | Permission / boundary |
|---|---|---|
| GET | `/health` | public |
| GET | `/health/live` | public |
| GET | `/health/ready` | operator |
| GET | `/metrics` | operator |
| GET | `/api/v1/health` | public |
| GET | `/api/v1/health/live` | public |
| GET | `/api/v1/health/ready` | operator |
| POST | `/api/v1/chat/stream` | `chat:write`, `rag:read` |
| POST | `/api/v1/rag/ingest` | `rag:write` |
| GET | `/api/v1/rag/tasks/{task_id}` | `rag:read` |
| POST | `/api/v1/rag/query` | `rag:read` |
| POST | `/api/v1/rag/generate` | `rag:read`, `chat:write` |
| GET | `/api/v1/byok/keys` | `byok:read` |
| POST | `/api/v1/byok/keys` | `byok:write` |
| POST | `/api/v1/byok/keys/validate` | `byok:write` |
| POST | `/api/v1/byok/keys/{provider}/validate` | `byok:write` |
| POST | `/api/v1/byok/keys/{provider}/rotate` | `byok:write` |
| POST | `/api/v1/byok/keys/{provider}/revoke` | `byok:write` |
| DELETE | `/api/v1/byok/keys/{provider}` | `byok:write` |
| POST | `/api/v1/devops/audit-pr` | `agent:execute` |
| POST | `/api/v1/devops/changelog` | `agent:execute` |
| POST | `/api/v1/gateway/chat/completions` | `chat:write` |
| GET | `/api/v1/gateway/models` | `chat:read` |
| GET | `/api/v1/gateway/quotas` | `finops:read` |
| POST | `/api/v1/gateway/quotas` | `finops:write` |
| POST | `/api/v1/billing/webhook` | payment-signature |
| GET | `/api/v1/billing/subscription` | `finops:read` |
| GET | `/api/v1/analytics/dashboard` | `ops:read` |
| GET | `/api/v1/analytics/metrics` | `ops:read` |
| GET | `/api/v1/finops/summary` | `finops:read` |
| GET | `/api/v1/finops/transactions` | `finops:read` |
| GET | `/api/v1/finops/budget` | `finops:read` |
| POST | `/api/v1/finops/budget` | `finops:write` |
| GET | `/api/v1/finops/reconciliation` | `finops:read` |
| POST | `/api/v1/coding/tool-result` | `agent:execute` |
| POST | `/api/v1/coding/resume` | `agent:execute` |
| POST | `/api/v1/agent/tasks` | `agent:write` |
| GET | `/api/v1/agent/tasks/{task_id}` | `agent:read` |
| POST | `/api/v1/agent/tasks/{task_id}/runs` | `agent:execute` |
| GET | `/api/v1/agent/tasks/{task_id}/runs/{run_id}` | `agent:read` |
| GET | `/api/v1/agent/tasks/{task_id}/runs/{run_id}/events` | `agent:read` |
| POST | `/api/v1/agent/tasks/{task_id}/runs/{run_id}/cancel` | `agent:write` |
| POST | `/api/v1/agent/tasks/{task_id}/runs/{run_id}/approvals/{approval_id}` | `agent:approve` |
| GET | `/api/v1/agent/approvals/pending` | `agent:approve` |
| GET | `/api/v1/agent/metrics` | `ops:read` |
| POST | `/v1/chat/completions` | `chat:write` |
| GET | `/v1/models` | `chat:read` |
| GET | `/v1/quotas` | `finops:read` |
| POST | `/v1/quotas` | `finops:write` |
| POST | `/internal/v1/coding/tool-result` | `agent:execute` |
| POST | `/internal/v1/coding/resume` | `agent:execute` |

The middleware rejects registered routes lacking a policy. Resource IDs do not select tenant or subject. Agent task/run reads require the owner and matching parent; foreign resources are hidden. Approvals are disabled before any effect, including root/internal aliases.

## Verification and acceptance limits

`backend/tests/security/test_j02_reproductions.py` reproduces the original seven failures. `test_j02_identity.py` tests strict claims, key bytes, retirement, actual route permissions, owner/default-tenant behavior and state-adapter faults. Ordinary pytest suites use an explicitly synthetic state fixture; they do not certify actual Finn.

The guarded `.github/workflows/j02-rehearsal.yml` executes actual Finn b79b0dbea09cbf1464baa4de9ab76573c8b6fd32 and this Jake source on public standard ubuntu-24.04. Only the external model adapter is synthetic. It preserves real application middleware/routes/services and actual selected Redis stores. It scans the exact images, uses isolated TLS/MySQL/Redis and fresh ephemeral keys, waits the real 930 seconds and retains failures. Cleanup deletes only owned resources and private runtime files; it does not claim secure erasure. Same-image recreation is not distinct-version disaster recovery. Real approval consume and Qdrant ACL lifecycle are not certified by this harness.

Standard public GitHub-hosted runner eligibility: [GitHub billing](https://docs.github.com/en/billing/concepts/product-billing/github-actions). No new artifact/cache/package upload is introduced; existing mandatory artifact controls remain in force. No local Docker/WSL or production deployment is part of J02.

Implementation and PR delivery are separate from acceptance. Human merge and independent exact-main review remain required. Local `.agents/release-readiness/evidence/J02.md` records current execution results and remaining mandatory gaps; this document grants no execution or deployment authority.
