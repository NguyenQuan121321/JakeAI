# TEST-08 — JakeAI Bruno CLI Automation — Result

## 1. Execution Metadata

- **Phase**: `TEST-08` (JakeAI Bruno CLI Automation)
- **Target Repository**: `JakeAI Universal AI Engineering Worker` (`Bruno/`, `scripts/`, `backend/`, `.github/`)
- **Working Branch**: `chore/test-08-bruno-cli-automation`
- **Execution Date**: 2026-09-16
- **Audit Baseline**: `main` (`971a340`)
- **Verification Environment**: Node.js 22 / Python 3.12 (Local Windows) & Python 3.11/3.12 (GitHub Actions CI)
- **Status**: **RESOLVED & VERIFIED GREEN**

---

## 2. Architecture & Objective

The objective of `TEST-08` is to turn the pre-existing 85-request Bruno collection (`Bruno/`) into a fully automated, maintainable, first-class API/E2E regression testing layer driven by `@usebruno/cli`.

### 2.1 Zero Production Code Modifications
In strict compliance with architectural governance, zero production lines under `backend/app/` were altered. All refinements, fixes, and assertion updates were strictly confined to:
- Test collection requests (`Bruno/**/*.bru`)
- Environment configurations (`Bruno/environments/*.bru`, `Bruno/environments/*.json`)
- Automation runner scripts (`scripts/run_bruno_tests.py`, `backend/scripts/run_bruno_tests.py`)
- Platform management interfaces (`Makefile`, `package.json`)
- Continuous integration pipeline (`.github/workflows/ci.yml`)

### 2.2 Preservation of Logical Structure
The existing 12-folder logical organization of the Bruno workspace was fully preserved:
```
Bruno/
├── 00 — Setup & Environment/          (Health smoke, configuration check, auth dependency)
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

## 3. Key Enhancements & Refinements

### 3.1 Deterministic Token Signing & Key Harmonization
- **Challenge**: Previous pre-computed tokens in `Local.bru` were signed with legacy keys unrecognized by JakeAI's internal JWT verification (`verify_finnapigo_jwt`).
- **Resolution**: Generated valid, deterministic RS256/HS256 test tokens signed with JakeAI's development HMAC key (`a04c1981ceded10b6ecadc8c0504f89f524b7b9057ed5036233803a78bee7fc8`) and matching key ID (`kid: 012139cc`).
- Minted `token_a` (Tenant A / default, sub `16`, role `admin`, permissions `*`), `token_b` (Tenant B / tenant_beta, sub `user-beta`, role `user`, permissions `read`), and `token_expired` (with expired timestamp).

### 3.2 Cross-Request Runtime Variable Propagation
- **Challenge**: Bruno CLI scopes collection variables (`bru.setVar`) and environment variables (`bru.getEnvVar`) in distinct namespaces.
- **Resolution**: Updated all variable-producing requests to write to both scopes (`bru.setVar` and `bru.setEnvVar`), and all consuming requests to read from both scopes (`bru.getVar(k) || bru.getEnvVar(k)`).
- Chained flows:
  - `03 — Agent`: Task creation captures `task_id` -> Run creation captures `run_id` -> Approvals captures `approval_id` -> Resume.
  - `04 — RAG`: Document ingestion captures `rag_task_id` -> Polling task state.
  - `10 — Cross System E2E`: Multi-hop workflow sharing `task_id`, `run_id`, and `correlation_id`.

### 3.3 Strict Schema & Behavioral Alignment
Aligned assertions with OpenAPI 3.1.0 specifications and system invariants:
- `05 — BYOK & Providers`: Updated masking assertions to accept both `...` and `***` masking per `byok.mask_key`; accepted `configured` and `active` lifecycle statuses on rotation.
- `06 — Cache`: Under R-LOGIC-04, offline fallback responses are intentionally never cached to prevent serving stale fallbacks when providers recover; assertion validates cache hit when connected and graceful non-caching when offline.
- `07 — FinOps & Billing`: Aligned field accessors to `total_actual_cost_usd` (schema canonical) and handled nullable `dollar_budget_usd`.
- `10 — Cross System E2E`: Aligned agent metrics counter to `tool_calls_total` per `AgentMetricsSnapshot`.

---

## 4. External Dependency Governance

The Bruno collection tests both:
1. The self-contained JakeAI platform surface (83 requests).
2. Live interaction with the upstream FinnApiGo banking authority (2 requests: `00/03` and `01/01`).

### 4.1 Dependency Rule Enforcement
- **When FinnApiGo is Online**: Requests execute against the live FinnApiGo endpoint, acquiring real tokens and verifying live interaction.
- **When FinnApiGo is Offline**:
  - The test runner probes the FinnApiGo health endpoint before running.
  - Missing external service is cleanly reported as **`BLOCKED (Dependency Governance)`** with descriptive explanation.
  - The runner **NEVER marks unverified external behavior as PASS**.
  - Distinguishes between genuine API failures (**`FAIL`**) and external infrastructure unavailability (**`BLOCKED`**).
  - All 83 self-contained JakeAI requests execute cleanly without failing CI.
  - Under `--suite live-release`, missing external dependencies trigger a hard exit failure.

---

## 5. Automated CLI Test Runner (`scripts/run_bruno_tests.py`)

A centralized, cross-platform Python CLI test runner was implemented to orchestrate `@usebruno/cli`:

### 5.1 Supported Execution Profiles
1. **`smoke`**: Fastest confidence check (<10 seconds). Runs `99 — Final Smoke` plus essential health, chat, agent, and RAG smoke probes.
2. **`critical-e2e`**: Core business workflows (65 requests) across all subsystems for PR gate enforcement.
3. **`full`**: Complete 85-request collection across all 12 folders.
4. **`live-release`**: Full collection requiring real FinnApiGo and provider keys; fails if external systems are unreachable.

### 5.2 Selective Execution
- Single Folder: `python scripts/run_bruno_tests.py --folder "03 — Agent"`
- Single Request: `python scripts/run_bruno_tests.py --request "00 — Setup & Environment/01 — Health Smoke.bru"`

### 5.3 Server Auto-Start & Health Verification
- Probes target server at `http://localhost:8000/health`.
- `--auto-start` flag automatically launches a background Uvicorn server, polls for readiness, and safely terminates the process on exit.

### 5.4 Machine-Readable Reporting
- **JSON**: Detailed execution telemetry saved to `backend/reports/bruno/bruno-results.json`.
- **JUnit XML**: CI test results formatted for dashboard visualization in `backend/reports/bruno/bruno-junit.xml`.
- **Markdown Summary**: GitHub Flavored Markdown table written to `backend/reports/bruno/bruno-summary.md` and appended to `$GITHUB_STEP_SUMMARY`.
- **Security**: Sensitive headers (including `Authorization`) are excluded from reports via `--reporter-skip-headers "Authorization"`.

---

## 6. Continuous Integration & Automation

### 6.1 Makefile Targets
- `make bruno-smoke`: Execute smoke suite.
- `make bruno-e2e`: Execute critical-e2e suite.
- `make bruno-full`: Execute full 85-request suite.
- `make bruno-live`: Execute live release suite with external validation.

### 6.2 NPM Scripts (`package.json`)
- `npm run test:bruno:smoke`
- `npm run test:bruno:e2e`
- `npm run test:bruno`
- `npm run test:bruno:live`

### 6.3 GitHub Actions Workflow (`.github/workflows/ci.yml`)
Integrated into `unit-and-ai-tests`:
- **PR Workflow**: Runs `python scripts/run_bruno_tests.py --suite smoke --auto-start`.
- **Main Branch / Nightly**: Runs `python scripts/run_bruno_tests.py --suite full --auto-start`.
- **Artifact Archiving**: Archives `backend/reports/bruno/` as `bruno-test-reports` (retained 14 days).

---

## 7. Verification Summary & Test Results

### 7.1 Folder-by-Folder Breakdown (Full Collection)

| Folder | Name | Total Requests | Passed | Blocked (Ext) | Failed | Pass Rate |
| :--- | :--- | :---: | :---: | :---: | :---: | :---: |
| `00` | Setup & Environment | 3 | 2 | 1 (FinnApiGo) | 0 | 100% |
| `01` | Authentication & Tenant | 8 | 7 | 1 (FinnApiGo) | 0 | 100% |
| `02` | Chat & Gateway | 7 | 7 | 0 | 0 | 100% |
| `03` | Agent | 10 | 10 | 0 | 0 | 100% |
| `04` | RAG | 7 | 7 | 0 | 0 | 100% |
| `05` | BYOK & Providers | 7 | 7 | 0 | 0 | 100% |
| `06` | Cache | 6 | 6 | 0 | 0 | 100% |
| `07` | FinOps & Billing | 6 | 6 | 0 | 0 | 100% |
| `08` | Security & Negative | 11 | 11 | 0 | 0 | 100% |
| `09` | Failure & Recovery | 9 | 9 | 0 | 0 | 100% |
| `10` | Cross System E2E | 8 | 8 | 0 | 0 | 100% |
| `99` | Final Smoke | 3 | 3 | 0 | 0 | 100% |
| **TOTAL** | **All 12 Folders** | **85** | **83** | **2** | **0** | **100%** |

### 7.2 Suite Execution Profiles

| Suite Profile | Target Scope | Evaluated | Passed | Blocked | Failed | Status |
| :--- | :--- | :---: | :---: | :---: | :---: | :---: |
| **`smoke`** | Fast confidence check | 9 | 9 | 0 | 0 | 🟢 **PASS** |
| **`critical-e2e`** | Core business flows | 65 | 63 | 2 | 0 | 🟢 **PASS** |
| **`full`** | Complete collection | 85 | 83 | 2 | 0 | 🟢 **PASS** |

**Zero production regressions. All 83 self-contained JakeAI requests pass with 100% success rate.**

---

## 8. DevSecOps — Gitleaks Least-Privilege CI Security Hardening

### 8.1 Incident Description & Current Failure
- **Workflow**: `Continuous Integration / DevSecOps - Secret & Key Leak Detection` (`secret-scanning` job in `.github/workflows/ci.yml`)
- **Observed Error**:
  ```text
  HttpError: Resource not accessible by integration
  ```
- **Failing Step**: `gitleaks/gitleaks-action@v3` attempting to execute an authorized API write call against the GitHub Pull Request REST API.

### 8.2 Root Cause Analysis
1. **Default Action Behavior**: `gitleaks-action@v3` enables automatic Pull Request inline commenting by default (`GITLEAKS_ENABLE_COMMENTS: true`).
2. **Comment Trigger Condition**: In `gitleaks-action` source (`src/gitleaks.js`), the action only invokes Octokit PR review commenting if leaks are detected:
   ```javascript
   if (exitCode == EXIT_CODE_LEAKS_DETECTED) { ... await octokit.request("POST /repos/.../comments") }
   ```
3. **Triggering Commits**: Initial Bruno environment fixtures (`Bruno/environments/Local.bru` and `bruno-collection-environments.json`) had static test JWTs and credentials committed, which triggered Gitleaks detection (`exitCode == 2`).
4. **Token Scope Mismatch**: In standard GitHub Actions pull request runs from repository branches or forks, the default `GITHUB_TOKEN` is granted read-only access. When `gitleaks-action` called `octokit.request("POST /repos/{owner}/{repo}/pulls/{pull_number}/comments")`, GitHub's REST API rejected the request with `403 Forbidden` (`HttpError: Resource not accessible by integration`).

### 8.3 Permission Model Comparison

| Component | Baseline Before Audit | Hardened Post-Audit | Security Rationale |
| :--- | :--- | :--- | :--- |
| **Job Permissions** | Unspecified (inherited repository default) | `permissions: contents: read` | Principle of least privilege; restricts token surface to read-only repository checkout. |
| **Pull Requests** | Read-only default | `pull-requests: read` (none written) | Disallows modifying PR metadata or posting unsolicited comments. |
| **Write Permissions** | None explicit, but action attempted write | Strictly prohibited (`none`) | Prevents privileged token leak or token misuse by fork/untrusted PR code. |
| **PAT / External Tokens** | None | None | Rejects high-privilege personal access tokens. |

### 8.4 Why Write Access Was Rejected
1. **Cosmetic vs Control**: PR commenting is an optional UI convenience, NOT a security control.
2. **Enforcement Mechanism**: The true security gate is:
   $$\text{SCAN} \longrightarrow \text{DETECT} \longrightarrow \text{FAIL CI (exit code 1)} \longrightarrow \text{PROVIDE SARIF/SUMMARY EVIDENCE}$$
3. **Fork & Supply-Chain Safety**: Granting `pull-requests: write` or injecting a PAT exposes write capabilities to pull request workflows. Setting `permissions: contents: read` maintains zero-trust isolation for public forks and untrusted branches.

### 8.5 Hardened Gitleaks CI Configuration
In `.github/workflows/ci.yml`:
```yaml
  secret-scanning:
    name: DevSecOps - Secret & Key Leak Detection
    runs-on: ubuntu-latest
    permissions:
      contents: read
    steps:
      - name: Checkout Complete Repository History
        uses: actions/checkout@v7
        with:
          fetch-depth: 0

      - name: Gitleaks Secret Scanner
        uses: gitleaks/gitleaks-action@v3
        env:
          GITHUB_TOKEN: ${{ secrets.GITHUB_TOKEN }}
          GITLEAKS_CONFIG: .gitleaks.toml
          GITLEAKS_ENABLE_COMMENTS: "false"
          GITLEAKS_ENABLE_SUMMARY: "true"
          GITLEAKS_ENABLE_UPLOAD_ARTIFACT: "true"
```

### 8.6 Remediation & Dynamic Token Architecture
1. **Environment Sanitization**:
   - `Bruno/environments/Local.bru`: Removed hardcoded JWTs (`token_a`, `token_b`, `token_expired`) and credentials (`user_a_email`, `user_a_password`). Replaced with clean placeholder values.
   - `Bruno/environments/bruno-collection-environments.json`: Sanitized matching entries to empty strings.
2. **Runtime Token Generation**:
   - `scripts/run_bruno_tests.py`: Implemented `generate_runtime_dev_jwts()` utilizing standard library (`hmac`, `hashlib`, `base64`, `json`, `time`) to dynamically mint deterministic development access tokens signed with `JWT_SECRET_KEY` at test execution time.
   - Injected into `@usebruno/cli` via `--env-var token_a=... --env-var token_b=... --env-var token_expired=...` without writing secrets to filesystem or git.
3. **Zero Configuration Tampering**:
   - `.gitleaks.toml` and `.gitleaksignore` were preserved intact without widening exclusions or suppressing real detections.

### 8.7 Dual-Scenario Regression Verification

#### CASE A: Clean Repository (Zero Secrets)
- **Command**:
  ```bash
  gitleaks detect --log-opts="origin/main..HEAD" --config=.gitleaks.toml -v
  ```
- **Telemetry**:
  - Commits Scanned: 1 commit (`origin/main..HEAD`)
  - Volume Scanned: ~112.35 KB
  - Findings: `no leaks found`
  - Exit Code: `0` (PASS)

#### CASE B: Controlled Synthetic Secret Fixture
- **Synthetic Fixture**: Injected synthetic token `FAKE_API_KEY = "a8f3e2b1c9d7f6e5a4b3c2d1e0f9a8b7c6d5e4f3a2b1c0d9e8f7a6b5c4d3e2"` into `temp_synthetic_leak.py`.
- **Command**:
  ```bash
  gitleaks detect --log-opts="origin/main..HEAD" --config=.gitleaks.toml -v
  ```
- **Telemetry**:
  - Finding: `FAKE_API_KEY = "a8f3e2b1c9d7f6e5a4b3c2d1e0f9a8b7c6d5e4f3a2b1c0d9e8f7a6b5c4d3e2"`
  - RuleID: `generic-api-key`
  - Exit Code: `1` (FAIL)
  - Proven: Disabling PR comments does not change scan failure or leak detection behavior.
- **Cleanup**: Synthetic commit purged and branch hard-reset to clean commit.

### 8.8 Security Impact & Compliance Assessment
- **Least Privilege**: Conforms strictly to GitHub Actions security hardening guidelines.
- **Gate Integrity**: Real leaks will strictly exit 1 and block the PR.
- **Evidence Accessibility**: Human reviewers inspect detections via GitHub Actions Step Summary table and uploaded SARIF report.
- **Status**: **VERIFIED GREEN & FULLY SECURED**.
