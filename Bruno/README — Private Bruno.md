# JakeAI — Private Bruno API Collection Guide

## 1. Overview & Purpose
The `Bruno/private/` collection is the internal, security, resilience, chaos, and live-validation Bruno API suite for the **JakeAI Universal AI Engineering Worker**.

- **Strictly Confidential & Gitignored**: This entire directory is excluded from version control via `.gitignore` (`Bruno/private/`).
- **Security & Adversarial Testing**: Houses offensive attack vectors, prompt injection probes, path traversal attempts, malformed payload fuzzing, and negative authentication tests.
- **Cross-Tenant & Isolation Verification**: Validates strict data isolation across tenant boundaries (Tenant A vs Tenant B).
- **Live Upstream Validation**: Contains tests targeting live external services (FinnApiGo banking, live commercial LLM providers, PayOS payment webhooks).

---

## 2. Git Exclusion Verification

This directory MUST NOT be committed to git under any circumstances.
To verify that Git correctly ignores this directory:

```bash
# Verify ignore rule matches:
git check-ignore -v Bruno/private/

# Verify zero files are tracked:
git ls-files Bruno/private/
```
The second command MUST produce zero output.

---

## 3. Directory Structure & Folder Map

```
Bruno/private/
├── 01 — Auth & Tenant/                (JWT login, expired tokens, tampered signatures, claims)
├── 02 — Security & Negative/          (SQLi, path traversal, oversized bodies, schema fuzzing)
├── 03 — Failure & Recovery/           (Timeouts, circuit breakers, failover, idempotency)
├── 04 — Cross Tenant/                 (Cross-tenant task, run, RAG chunk, and cache isolation)
├── 05 — Tool Security/                (Restricted tool execution, SSRF guards, sandboxing)
├── 06 — Live Provider/                (Live OpenAI, Anthropic, Gemini upstream calls)
├── 07 — Live FinnApiGo/               (Live FinnApiGo identity token issuance & banking sync)
└── 08 — Production Verification/      (Post-deployment critical gates & invariant verification)
```

### Folder Breakdown:
1. **`01 — Auth & Tenant`**:
   - Tests `401 Unauthorized` on missing tokens, invalid signatures, expired timestamps, and untrusted issuers.
   - Tests `403 Forbidden` on role/permission authorization mismatches.
2. **`02 — Security & Negative`**:
   - Tests defense against prompt injections (jailbreak attempts, system prompt exfiltration).
   - Validates boundary limits (max tokens exceeding model limit, negative temperature, malformed JSON).
   - Validates `413 Payload Too Large` and `422 Unprocessable Entity` guards.
3. **`03 — Failure & Recovery`**:
   - Simulates upstream provider errors (`503 Service Unavailable`, `408 Request Timeout`).
   - Verifies automated fallback providers and deterministic retry behaviors.
4. **`04 — Cross Tenant`**:
   - Asserts that Tenant B cannot access Tenant A's tasks (`404 Not Found`).
   - Asserts that Tenant B cannot read or search Tenant A's private RAG chunks in Qdrant.
   - Asserts that Tenant B cannot hit cached completions belonging to Tenant A.
5. **`05 — Tool Security`**:
   - Asserts that unauthorized shell, file system, or network tools are blocked by permission policies.
6. **`06 — Live Provider`**:
   - Probes live commercial LLMs (OpenAI, Gemini, Anthropic) using real BYOK keys.
7. **`07 — Live FinnApiGo`**:
   - Connects to a running FinnApiGo instance on port 8081 for real OAuth/JWT flows.
8. **`08 — Production Verification`**:
   - Read-only and non-destructive post-deployment smoke suite for production environments.

---

## 4. Environment Variables & Live Configuration

Private and live suites require active environment credentials configured in `Bruno/environments/Local.bru` or environment variables:

| Variable | Description | Security Requirement |
|---|---|---|
| `token_a` | Tenant A dev or live JWT | Synthetic in dev; ephemeral in live runs |
| `token_b` | Tenant B dev or live JWT | Used for cross-tenant isolation checks |
| `token_expired` | Deliberately expired JWT | Used for 401 verification |
| `token_invalid` | Tampered signature JWT | Used for 401 verification |
| `OPENAI_API_KEY` | Real OpenAI API key | Optional; required only for `06 — Live Provider` |
| `GEMINI_API_KEY` | Real Gemini API key | Optional; required only for `06 — Live Provider` |
| `ANTHROPIC_API_KEY`| Real Anthropic API key | Optional; required only for `06 — Live Provider` |
| `PAYOS_WEBHOOK_SECRET`| PayOS HMAC signature secret | Used for webhook HMAC verification |

> [!CAUTION]
> NEVER commit real API keys into `Bruno/environments/Local.bru`. Use environment variable substitution (`process.env.OPENAI_API_KEY`) or local untracked `.env` files.

---

## 5. Automated Execution Commands

You can execute private suites via `scripts/run_bruno_tests.py`:

```bash
# 1. Run Security, Negative, and Tenant Isolation Suite
python scripts/run_bruno_tests.py --suite private-security

# 2. Run All Private Tests (including offline failure & recovery)
python scripts/run_bruno_tests.py --suite private-full

# 3. Run Critical End-to-End Business Workflows
python scripts/run_bruno_tests.py --suite critical-e2e

# 4. Run Live Release Verification (Requires live FinnApiGo and LLM keys)
python scripts/run_bruno_tests.py --suite live-release
```

---

## 6. Execution Guidelines: Mock vs. Live Upstream Handling

When executing tests in environments without live third-party accounts:
1. **Offline / Dev Environments**:
   - The test runner and test doubles gracefully bypass or mock external calls.
   - Live suites (`06 — Live Provider`, `07 — Live FinnApiGo`) will report **BLOCKED** or **SKIPPED** rather than crashing with false failures when upstream keys are omitted.
2. **Staging / Pre-Production**:
   - Run `--suite live-release` with actual staging keys to confirm live upstream integrations.
3. **Production Environments**:
   - ONLY execute `--suite public-smoke` or `private/08 — Production Verification`.
   - **NEVER execute `02 — Security & Negative` or `03 — Failure & Recovery` against live production systems**, as aggressive payload fuzzing and chaos simulation could impact real customer traffic or trigger WAF rate limits.
