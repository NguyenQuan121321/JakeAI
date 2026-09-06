# ADR-003: Stateless Zero-Retention BYOK Pipeline and Local OS Keystore Isolation

## Status
Accepted

## Context
In commercial AI coding platforms, persisting customer third-party provider API keys (OpenAI, Anthropic, Gemini, OpenRouter) in a central database introduces a catastrophic "Credential Honeypot" risk. If the backend database is compromised, all customer API keys are exfiltrated, exposing users to unlimited financial drain and credit exhaustion.

Furthermore, selling raw LLM tokens forces the platform into a negative-margin liability trap where high-usage edge cases deplete platform operating cash flow.

## Decision
JakeAI adopts a strict **Bring Your Own Key (BYOK)** model backed by a **Stateless Zero-Retention & Local-First Keystore Architecture**:

1. **Zero Database Persistence**:
   - The JakeAI database contains strictly zero tables or columns for customer API keys (`user_api_keys` does not exist).
   - In the event of a total server intrusion, an attacker captures 0 API keys.

2. **Local-First OS Keystore Vault**:
   - Customer API keys reside strictly on the developer's workstation within OS-native secure hardware enclaves:
     - **Windows**: DPAPI via Windows Credential Manager.
     - **macOS**: Apple Keychain Services.
     - **Linux**: Secret Service API / Libsecret.
     - **VS Code Extension**: `vscode.SecretStorage` API.

3. **Ephemeral In-Flight Transmission**:
   - Keys are transmitted over TLS 1.3 in request headers (`X-Provider-API-Key`).
   - The gateway parses the key into a volatile bytearray buffer, injects it into outbound provider requests, and immediately zeroes/wipes the memory buffer upon request completion.
   - Keys are never written to disk, database, swap space, or crash logs.

4. **Hardened Redaction & Anomaly Detection**:
   - Global regex interceptors sanitize all logging sinks: `sk-[a-zA-Z0-9_\-]{20,}` is replaced with `sk-***[REDACTED]***`.
   - Edge proxy computes non-reversible `HMAC-SHA256(key, server_pepper)` for velocity rate limiting without ever exposing the raw secret.

5. **Terms of Service & Blast Radius Isolation**:
   - Platform operates as a non-custodial prompt optimizer with zero custody of user funds.
   - Users are mandated to configure project-scoped restricted keys with hard $5–$20 monthly spend ceilings on provider consoles.

## Consequences
- **Positive**: 100% elimination of the credential honeypot vulnerability; 0 VND upstream LLM liability for the platform; enterprise compliance with SOC 2 / GDPR data minimization.
- **Negative**: Users must manage their own API keys and provider billing accounts.
