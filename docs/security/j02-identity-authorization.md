# J02 identity and authorization policy

Jake consumes Finn v1 access credentials using configured HS256 key IDs and canonical base64 signing bytes. Finn is authoritative for tenant, session, account state, credential versions and exact grants. Roles and headers do not add permissions. `default` is an ordinary tenant.

Production requires an authenticated verified-HTTPS `IDENTITY_STATE_URL` with a distinct `IDENTITY_STATE_KEY_ID` / `IDENTITY_STATE_SECRET`. Responses are bounded to 4 KiB, 3 seconds by default (maximum 5), and 16 concurrent requests by default. There is no cross-request positive cache and no local denylist outage fallback. Invalid/inactive access is 401, missing grants 403, unknown/unavailable state 503 and hidden foreign resources 404. Request-local checks are at most 10 seconds apart, with a fresh check before provider dispatch and protected retrieval/indexing/credential use. Capacity is limited by Finn's shared 120/s quota: exceeding it fails closed with 503; no capacity qualification is claimed.

Signing rotation uses `JWT_KEY_ID`, `JWT_PREVIOUS_KEY_ID` and an immutable UTC Unix `JWT_PREVIOUS_LAST_ISSUED_AT`. Previous verification ends at final old issuance +930 seconds, including after restart. No legacy bridge, header-directed key or service-to-user/OBO issuance is enabled.

BYOK retains exact grants plus owner/delegation restrictions and J03 error redaction. Budget mutation additionally requires delegated tenant administration. RAG ingestion overwrites caller owner metadata; retrieval excludes foreign/unowned chunks before reranking, context, generation or citations. Conversation threads include tenant and subject. Cache namespaces additionally bind session, JTI, versions and permissions. Existing unowned documents require authorized re-ingestion; they are hidden rather than assigned an invented owner.

RAM approval/checkpoint state cannot authorize durable execution. A run can explicitly request an assigned second person's approval for a safe calculator action. The dedicated approval authority binds tenant, requester/session/versions, assigned approver, task/run, canonical action hash, tool/policy versions and a maximum 300-second expiry. Only those two users can read its record; only the assigned separate user with `agent:approve` can decide it; only its requester with fresh `agent:execute` can consume it. The strict verifier and actual Finn state recheck both users immediately before publication. A decision's credential is AES-GCM encrypted using a separately provisioned custody key and is removed on consumption/cancellation. Credentials never enter public responses. An expired/revoked approver must issue a new decision on a new request.

`APPROVAL_REDIS_URL` must point to a separate authenticated Redis instance with noeviction, AOF and appendfsync=always. `APPROVAL_CREDENTIAL_KEY` is an independent canonical base64 32-byte key; no cache, vault or RAM fallback exists. An operator provisions canonical JSON at `approval:active-policy` with `epoch` (a positive, monotonically increasing integer), `policy: "approval-calculator-v1"` and `tool: "calculator-v1"`. A policy change, including reverting configuration, uses a new epoch; old generations must never be reactivated. No HTTP route can change this metadata. Lua checks that shared generation atomically with the entire prior record and Redis server time, then publishes the calculator result in the same single write that consumes approval. Thus an old worker also rejects centrally invalidated decisions. Pure arithmetic can repeat under contention; protected publication happens once. An uncertain write reply returns503 and must be reconciled by reading the record; it never restores authority. Record retention/backup policy, restricted store access and store/key/policy provisioning require operational approval before deployment; this change deploys nothing. Rotating custody keys invalidates pending credentials; consumed records retain their denial of replay. Rolling back to code without this adapter disables positive approvals; a store snapshot must never be restored as active authority without invalidating its namespace/generation.

General checkpoint resume, unbound RAM approval listings and queued ingestion remain unavailable. File/shell/payment/general mutation tools remain disabled; this seam authorizes no other tool and does not implement J07's workflow engine. Payment ingress still cannot activate a subscription without a bound service contract. Read-only in-process runs retain route-bound fresh Finn state. Full document ACL lifecycle, provider quality and payment acceptance remain separate obligations.

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
| GET | `/api/v1/agent/tasks/{task_id}/runs/{run_id}/approvals/{approval_id}` | `agent:read`, requester or assigned approver |
| POST | `/api/v1/agent/tasks/{task_id}/runs/{run_id}/approvals/{approval_id}/consume` | `agent:execute`, bound requester, fresh two-party authority |
| POST | `/api/v1/agent/tasks/{task_id}/runs/{run_id}/approvals/{approval_id}/cancel` | `agent:execute`, bound requester |
| GET | `/api/v1/agent/approvals/pending` | `agent:approve` |
| GET | `/api/v1/agent/metrics` | `ops:read` |
| POST | `/v1/chat/completions` | `chat:write` |
| GET | `/v1/models` | `chat:read` |
| GET | `/v1/quotas` | `finops:read` |
| POST | `/v1/quotas` | `finops:write` |
| POST | `/internal/v1/coding/tool-result` | `agent:execute` |
| POST | `/internal/v1/coding/resume` | `agent:execute` |

The middleware rejects registered routes lacking a policy. Resource IDs do not select tenant or subject. Agent task/run reads require the owner and matching parent; foreign resources are hidden. Bound approval routes resolve ownership from the durable store on every worker; RAM checkpoints cannot grant authority. There are54 registered operations, including46 protected user operations.

## Verification and acceptance limits

`backend/tests/security/test_j02_reproductions.py` reproduces the original seven failures. `test_j02_identity.py` tests strict claims, key bytes, retirement, actual route permissions, owner/default-tenant behavior and state-adapter faults. Ordinary pytest suites use an explicitly synthetic state fixture; they do not certify actual Finn.

The guarded `.github/workflows/j02-rehearsal.yml` executes actual Finn b79b0dbea09cbf1464baa4de9ab76573c8b6fd32 and this Jake source on public standard ubuntu-24.04. Only the external model adapter is synthetic. The repair harness adds two Jake processes, actual assigned Finn users, dedicated persistent Redis, cross-worker decisions/consume races and process/store recreation. It preserves exact-image scans, verified TLS, fresh ephemeral keys, the real930-second rotation and owned cleanup. Results apply only when that exact revision passes; source changes alone are not runtime evidence. Same-image recreation is not distinct-version disaster recovery; Qdrant ACL lifecycle remains outside this harness.

Standard public GitHub-hosted runner eligibility: [GitHub billing](https://docs.github.com/en/billing/concepts/product-billing/github-actions). No new artifact/cache/package upload is introduced; existing mandatory artifact controls remain in force. No local Docker/WSL or production deployment is part of J02.

Implementation and PR delivery are separate from acceptance. Human merge and independent exact-main review remain required. Local `.agents/release-readiness/evidence/J02.md` records current execution results and remaining mandatory gaps; this document grants no execution or deployment authority.
