# JakeAI — Bruno Collection Reconciliation Architecture

## 1. Context & Purpose
Prior to the comprehensive test overhaul (`TEST-00` through `TEST-13`), the Bruno collection was maintained manually as a monolithic, unstructured set of exploratory requests. Over time, the JakeAI application evolved:
- Endpoints were standardized according to OpenAPI and REST best practices.
- Security boundaries, multi-tenancy rules, and payload schemas were strictly formalized.
- The monolithic Bruno folder structure diverged from the actual FastAPI route registry.

Under **`BRUNO-RECON-01`**, a complete, authoritative reconciliation was performed to establish a single, verifiable source of truth:

$$\text{FastAPI Routes} + \text{OpenAPI Specification} + \text{Test Catalog} \implies \text{Final Reconciled Bruno Collection}$$

---

## 2. Authoritative Source of Truth

The current JakeAI system defines exactly **51 API operations across 47 paths** in `backend/app/main.py` and `backend/openapi.json`.

Every single operation is accounted for and indexed in [`Bruno/BRUNO-ENDPOINT-INVENTORY.md`](file:///e:/JakeAI/Bruno/BRUNO-ENDPOINT-INVENTORY.md):
- **Perimeter / Public (10 operations)**: Unauthenticated health, liveness, readiness, Prometheus metrics, PayOS billing webhook, and coding engine resumption.
- **Tenant-Scoped / Authenticated (41 operations)**: Requires `Authorization: Bearer <JWT>` containing sub, tenant, and role claims.
- **Server-Sent Events (SSE) (2 operations)**:
  - `POST /api/v1/chat/stream`
  - `GET /api/v1/agent/tasks/{task_id}/runs/{run_id}/events`

### Workspace Architecture
The reconciled collection is split cleanly into two top-level partitions:
- **`Bruno/public/`**: Safe, shareable, tracked in Git, covering non-destructive operations and happy paths across all 51 endpoints.
- **`Bruno/private/`**: Internal, security offensive payloads, chaos, live integration, and cross-tenant tests. Excluded from git tracking via `.gitignore`.

---

## 3. Automated Reconciliation & Drift Detection

Reconciliation is enforced programmatically so that drift is caught immediately during development and CI:

### 1. Reconciliation CLI Script: `scripts/check_bruno_reconciliation.py`
This script dynamically loads the live FastAPI app (`backend/app/main.py`), extracts all route handlers and OpenAPI operation definitions, parses all `.bru` files across `Bruno/public/` and `Bruno/private/`, and performs a bi-directional set audit.

```bash
python scripts/check_bruno_reconciliation.py
```

Output contract:
```text
============================================================
JAKEAI BRUNO RECONCILIATION AUDIT
============================================================
CURRENT API OPERATIONS : 51
BRUNO TOTAL REQUESTS   : 117
BRUNO COVERED OPS      : 51
MISSING FROM BRUNO     : 0
OBSOLETE IN BRUNO      : 0
MISMATCHES             : 0
============================================================
STATUS: PASS (100% Reconciled)
============================================================
```

### 2. Pytest Contract Test Gate: `backend/tests/contract/test_bruno_reconciliation.py`
Runs inside the standard Python test suite:
- `test_all_openapi_operations_covered_in_bruno`: Asserts 0 missing operations.
- `test_no_obsolete_operations_in_bruno`: Asserts 0 obsolete requests referencing non-existent routes.
- `test_no_unsupported_path_variable_mismatches`: Verifies parameter alignment.

---

## 4. Deprecated & Obsolete Request Policy

When an API endpoint is deprecated or changed:
1. **Never Leave Phantom Bruno Files**: Outdated `.bru` files calling removed routes must be deleted or updated immediately. The drift check will fail if obsolete routes are detected.
2. **Path Parameter Standardization**: URLs in Bruno requests MUST use double curly braces for path parameters matching FastAPI route definitions (e.g., `{{task_id}}`, `{{run_id}}`, `{{provider}}`), never hardcoded sample IDs like `/providers/gemini` or `/approvals/appr-12345`.
3. **Zero Secrets in Public Collection**: No `.bru` file in `public/` may contain real credentials or sensitive attack strings. Gitleaks will fail CI if any secret is introduced.

---

## 5. Developer Workflow: Adding a New Endpoint

When adding a new route in JakeAI:

1. **Register Route in FastAPI**: Add the endpoint to the appropriate router in `backend/app/api/...`.
2. **Export / Refresh OpenAPI**: Ensure the route is visible in `backend/openapi.json`.
3. **Create Public `.bru` Request**:
   - Add a `.bru` file in the relevant subfolder in `Bruno/public/` (e.g. `Bruno/public/02 — Chat & Gateway/`).
   - Define expected HTTP headers, body, and Bruno assertions.
4. **Create Private / Security `.bru` Request (if applicable)**:
   - Add unauthorized, cross-tenant, or negative bounds requests in `Bruno/private/`.
5. **Update Endpoint Inventory**:
   - Add the operation entry to `Bruno/BRUNO-ENDPOINT-INVENTORY.md`.
6. **Run Drift Verification**:
   ```bash
   python scripts/check_bruno_reconciliation.py
   pytest backend/tests/contract/test_bruno_reconciliation.py -v
   ```
7. **Regenerate Reconciliation Report**:
   ```bash
   python scripts/check_bruno_reconciliation.py --update-report
   ```
8. **Run Gitleaks Pre-Commit Check**:
   ```bash
   gitleaks detect --config .gitleaks.toml -v
   ```
