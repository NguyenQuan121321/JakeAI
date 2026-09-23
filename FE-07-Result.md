# FE-07 — Playwright E2E Auth Bootstrap & A11y Gate Resolution Report

## Executive Summary

The GitHub Actions CI job **"Frontend Console - Playwright E2E & A11y Gate"** previously failed after ~4 minutes due to systemic authentication and bootstrap mismatches rather than individual page selector defects.

By centralizing the authentication fixture layer, generating deterministic and structurally valid test JWTs, strictly separating auth HTTP mocks from domain/business API mocks, adding explicit canonical role fixtures (`authenticatedPage`, `unauthenticatedPage`, `adminPage`, `memberPage`), and fixing the production build requirement in CI/Playwright webServer, **100% of the Playwright E2E suite and Axe-core WCAG 2.1 AA accessibility audits now pass deterministically** (33/33 tests passing in ~44 seconds).

---

## Root Cause Analysis

Four interrelated root causes caused the systemic failure across multiple routes:

1. **Redirect Loops on `/login` and Protected Routes**:
   - `LoginPage` executes `if (isAuthenticated) navigate(from, { replace: true })`.
   - When tests navigated to `/login` without explicit unauthenticated flags, `AuthProvider` initialized into a default authenticated state, triggering immediate navigation to `/workspace` and causing `/login` selector timeouts.
   - Conversely, when `01-login-session.spec.ts` ran `logout()`, `jakeai_unauthenticated: "true"` was written to `sessionStorage`. Subsequent tests in the worker reused browser contexts with stale storage, locking them out of protected routes (`/workspace`, `/finops`, `/admin`).

2. **Malformed Token Signatures Failing `decodeJwt()`**:
   - Prior init scripts set `jakeai_access_token: "mock-access-token-jwt-valid"`.
   - Production `jwt.ts` (`decodeJwt`) strictly requires a 3-part Base64URL string (`split(".").length === 3`) containing valid JSON payloads.
   - When parsed, `"mock-access-token-jwt-valid"` caused `decodeJwt` to return `null`, dropping the user back to an unauthenticated state and breaking PBAC permissions.

3. **Duplicated & Inconsistent Route Mocking**:
   - Individual test files registered ad-hoc `page.route()` handlers that intercepted subsets of authentication and domain endpoints.
   - Endpoints like `/api/v1/auth/me`, `/api/v1/auth/login`, and `/api/v1/auth/refresh-token` returned payloads misaligned with the updated `AuthProfile` and `User` types (such as `token_type`, `tenant_id`, and `permissions`).

4. **Missing Build Step in CI Runner**:
   - The CI workflow executed `npx playwright test` with `webServer.command = "npm run preview -- --port 4173"`.
   - On clean CI runner VMs, `dist/` did not exist prior to running Playwright, causing Vite preview to fail immediately and stalling until the 2-minute webServer timeout elapsed.

---

## Authentication & Bootstrap Architecture

The frontend authentication system relies on:
- **`TokenStore`**: Strictly in-memory access token storage with auto-refresh mechanism.
- **`AuthProvider`**: Initializes identity from `/api/v1/auth/me` on mount, falling back to cached overrides in `sessionStorage` (`jakeai_access_token`, `jakeai_refresh_token`, `jakeai_user_override`, `jakeai-active-workspace`).
- **`jakeai_unauthenticated` Flag**: Explicitly controls whether the application allows unauthenticated access or forces a redirection to `/login`.

### Bootstrap Resolution Contract

The new fixture setup guarantees:
1. `installAuthenticatedSession`:
   - Purges `jakeai_unauthenticated`.
   - Seeds `jakeai_access_token` and `jakeai_refresh_token` with valid 3-segment test JWTs.
   - Seeds `jakeai_user_override` with the canonical user object.
   - Seeds `jakeai-active-workspace` with `core`.
2. `installUnauthenticatedSession`:
   - Sets `jakeai_unauthenticated: "true"`.
   - Clears all tokens and user overrides from `sessionStorage` and `localStorage`.
3. `createDeterministicTestJwt`:
   - Encodes Header (`{"alg":"HS256","typ":"JWT"}`), Claims (`sub`, `tenant_id`, `roles`, `permissions`, `email`, `name`, `exp`), and Signature into valid Base64URL without weakening production cryptographic verification.

---

## Canonical Test Personas

Three canonical test personas were defined in `frontend/apps/console/e2e/fixtures/auth.ts`:

| Persona | Role | Permissions | Tenant Scope | Purpose |
| :--- | :--- | :--- | :--- | :--- |
| **`ADMIN_USER`** | `admin` | `["*"]` | `org-enterprise-001` (`tenant-root-prod`) | Validates full administrative console access, tenant governance, and security audit logs on `/admin`. |
| **`MEMBER_USER`** | `developer` | `["workspace:read", "workspace:write", "chat:execute"]` | `org-enterprise-001` (`tenant-root-prod`) | Validates RBAC boundary enforcement, permission denial modals, and general workspace operations. |
| **`FINOPS_USER`** | `finops_analyst` | `["finops:read", "finops:write", "budget:configure"]` | `org-enterprise-001` (`tenant-root-prod`) | Validates financial governance, token spend metrics, and budget configuration actions. |

---

## Mock Separation & Route Interception

Route mocking was cleanly decoupled in `frontend/apps/console/e2e/fixtures/api-mocks.ts`:

- **`setupAuthMocks(page, user)`**:
  - `POST **/api/v1/auth/login`: Issues valid session tokens and user profile matching the persona.
  - `POST **/api/v1/auth/refresh-token`: Rotates access and refresh tokens seamlessly.
  - `GET **/api/v1/auth/me`: Delivers authenticated identity and profile.
  - `POST **/api/v1/auth/logout`: Clears session with status `200 OK`.
- **`setupBusinessApiMocks(page, user)`**:
  - Chat streaming (SSE tokens and completion chunks).
  - Agent workflows (`tasks`, `runs`, `approvals`, `events`).
  - BYOK credential vault (validation, rotation, zero raw secret exposure).
  - FinOps governance (budgets, transactions, spend breakdowns).
  - RAG ingestion pipeline (documents, collections, hybrid query).
  - Gateway models, quotas, and subscriptions.
- **`setupDefaultMocks(page, user)`**:
  - Composes auth and business mocks for turnkey page fixtures.

---

## Playwright Custom Fixtures (`fixtures/test.ts`)

Instead of tests configuring `page.addInitScript` manually, tests consume strongly-typed fixtures:

```typescript
import { test, expect } from "../fixtures/test";

test("verified route", async ({ authenticatedPage }) => {
  await authenticatedPage.goto("/workspace");
  // Pre-authenticated with ADMIN_USER and fully mocked APIs
});

test("unauthenticated flow", async ({ unauthenticatedPage }) => {
  await unauthenticatedPage.goto("/login");
  // Clean unauthenticated context, no redirects
});

test("rbac boundary", async ({ memberPage }) => {
  await memberPage.goto("/admin");
  // Non-admin identity, triggers PermissionDeniedState
});
```

---

## Regression Test Suite (`00-auth-bootstrap.spec.ts`)

A 10-point regression suite verifies end-to-end authentication stability:

1. **`authenticatedPage` reaches `/workspace`** without redirection (verifies Orchestrator header).
2. **`authenticatedPage` reaches `/finops`** without redirection (verifies Governance heading).
3. **`authenticatedPage` reaches `/agent`** without redirection (verifies Agent Orchestration Canvas).
4. **`authenticatedPage` reaches `/rag`** without redirection (verifies Knowledge Console).
5. **`memberPage` is denied `/admin`** and sees permission boundary alert + "Return to Workspace" action.
6. **`adminPage` reaches `/admin`** and renders Enterprise Administration & Security console.
7. **`unauthenticatedPage` reaches `/login`** and remains without redirection to `/workspace`.
8. **`unauthenticatedPage` accessing `/workspace`** is cleanly redirected to `/login`.
9. **`authenticatedPage` renders correct tenant context** (`JakeAI Core Platform`).
10. **`authenticatedPage` enables authorized actions** based on PBAC permissions (`Edit Budget`).

---

## E2E Test Suite Results

All 33 Playwright E2E and Axe-core accessibility tests passed across 6 parallel workers:

```
Running 33 tests using 6 workers

  ✓  [chromium] › accessibility.spec.ts › Login route (/login) [Axe-core WCAG 2.1 AA]
  ✓  [chromium] › accessibility.spec.ts › AI Workspace route (/workspace) [Axe-core WCAG 2.1 AA]
  ✓  [chromium] › accessibility.spec.ts › Agent Canvas route (/agent) [Axe-core WCAG 2.1 AA]
  ✓  [chromium] › accessibility.spec.ts › Agent Runs route (/agent/runs) [Axe-core WCAG 2.1 AA]
  ✓  [chromium] › accessibility.spec.ts › Providers & BYOK route (/providers) [Axe-core WCAG 2.1 AA]
  ✓  [chromium] › accessibility.spec.ts › RAG & Knowledge route (/rag) [Axe-core WCAG 2.1 AA]
  ✓  [chromium] › accessibility.spec.ts › FinOps Dashboard route (/finops) [Axe-core WCAG 2.1 AA]
  ✓  [chromium] › accessibility.spec.ts › Settings route (/settings) [Axe-core WCAG 2.1 AA]
  ✓  [chromium] › 00-auth-bootstrap.spec.ts › 1. authenticated fixture reaches /workspace
  ✓  [chromium] › 00-auth-bootstrap.spec.ts › 2. authenticated fixture reaches /finops
  ✓  [chromium] › 00-auth-bootstrap.spec.ts › 3. authenticated fixture reaches /agent
  ✓  [chromium] › 00-auth-bootstrap.spec.ts › 4. authenticated fixture reaches /rag
  ✓  [chromium] › 00-auth-bootstrap.spec.ts › 5. member fixture is denied /admin
  ✓  [chromium] › 00-auth-bootstrap.spec.ts › 6. admin fixture can access /admin
  ✓  [chromium] › 00-auth-bootstrap.spec.ts › 7. unauthenticated fixture reaches /login
  ✓  [chromium] › 00-auth-bootstrap.spec.ts › 8. unauthenticated access redirects to /login
  ✓  [chromium] › 00-auth-bootstrap.spec.ts › 9. authenticated identity renders correct tenant
  ✓  [chromium] › 00-auth-bootstrap.spec.ts › 10. authenticated identity enables authorized actions
  ✓  [chromium] › 01-login-session.spec.ts › authenticates user, sets session, and logs out cleanly
  ✓  [chromium] › 01-login-session.spec.ts › rejects invalid credentials with clear feedback
  ✓  [chromium] › 02-workspace-chat.spec.ts › opens workspace shell, renders header, model selector
  ✓  [chromium] › 02-workspace-chat.spec.ts › submits chat prompt, streams SSE response
  ✓  [chromium] › 02-workspace-chat.spec.ts › stops streaming generation on Stop click
  ✓  [chromium] › 03-agent-orchestration.spec.ts › creates agent task and starts autonomous run
  ✓  [chromium] › 03-agent-orchestration.spec.ts › inspects historical runs and approval gates
  ✓  [chromium] › 04-rag-query.spec.ts › renders RAG console, switches tabs, executes hybrid search
  ✓  [chromium] › 04-rag-query.spec.ts › opens Document Upload dialog and submits ingestion task
  ✓  [chromium] › 05-providers-byok.spec.ts › renders provider catalog and zero-retention banner
  ✓  [chromium] › 05-providers-byok.spec.ts › opens BYOK Key dialog, rotates key, verifies retention
  ✓  [chromium] › 06-finops-dashboard.spec.ts › renders token metrics, spend charts, transactions
  ✓  [chromium] › 06-finops-dashboard.spec.ts › opens Configure Budget Threshold dialog
  ✓  [chromium] › 07-permission-denial.spec.ts › denies non-admin developer user access to /admin
  ✓  [chromium] › 08-error-recovery.spec.ts › handles 503 provider downtime, retries, and recovers

33 passed (43.7s)
```

---

## Verification Summary

| Gate | Command | Result |
| :--- | :--- | :--- |
| **Type Integrity** | `npm run typecheck` | Passed (0 errors) |
| **API Contract & OpenAPI Drift** | `npm run test:contract` | Passed (38 JakeAI + 11 FinnApiGo endpoints) |
| **Unit & Integration Coverage** | `npm run test:coverage` | Passed (all suites green, coverage requirements met) |
| **Production Build** | `npm run build` | Built in 9.81s (0 errors, valid chunks generated) |
| **Playwright E2E & A11y Suite** | `npm run test:e2e` | 33 passed in 43.7s |

---

## Files Created & Modified

### Created Files
- `frontend/apps/console/e2e/fixtures/auth.ts`: Canonical user definitions, Base64URL test JWT generator, session state seeding.
- `frontend/apps/console/e2e/fixtures/test.ts`: Playwright test extension exporting pre-configured page fixtures.
- `frontend/apps/console/e2e/workflows/00-auth-bootstrap.spec.ts`: 10-point regression suite covering bootstrap, RBAC, tenant boundaries, and redirection.
- `FE-07-Result.md`: Comprehensive documentation report.

### Modified Files
- `frontend/apps/console/e2e/fixtures/api-mocks.ts`: Separated auth HTTP mocks from domain mocks; updated response payloads.
- `frontend/apps/console/e2e/workflows/01-login-session.spec.ts`: Refactored to use `unauthenticatedPage`.
- `frontend/apps/console/e2e/workflows/02-workspace-chat.spec.ts`: Refactored to use `authenticatedPage`.
- `frontend/apps/console/e2e/workflows/03-agent-orchestration.spec.ts`: Refactored to use `authenticatedPage`.
- `frontend/apps/console/e2e/workflows/04-rag-query.spec.ts`: Refactored to use `authenticatedPage`.
- `frontend/apps/console/e2e/workflows/05-providers-byok.spec.ts`: Refactored to use `authenticatedPage`.
- `frontend/apps/console/e2e/workflows/06-finops-dashboard.spec.ts`: Refactored to use `authenticatedPage`.
- `frontend/apps/console/e2e/workflows/07-permission-denial.spec.ts`: Refactored to use `memberPage`.
- `frontend/apps/console/e2e/workflows/08-error-recovery.spec.ts`: Refactored to use `authenticatedPage`.
- `frontend/apps/console/e2e/a11y/accessibility.spec.ts`: Clean separation of unauthenticated `/login` and authenticated protected routes.
- `frontend/apps/console/playwright.config.ts`: Updated `webServer.command` to build prior to preview.
- `.github/workflows/ci.yml`: Added build step in `frontend-e2e` job.
- `.github/workflows/nightly.yml`: Added build step in `nightly-frontend-e2e-and-a11y` job.
