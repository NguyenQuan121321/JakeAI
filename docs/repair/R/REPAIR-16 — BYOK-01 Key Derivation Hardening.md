# REPAIR-16 — BYOK-01 KEY DERIVATION HARDENING

Finding:
BYOK-01

Objective:
Replace non-standard tenant key derivation with a formally specified KDF without making existing encrypted BYOK data undecryptable.

Current defect to verify:
Docstring states HMAC-SHA256 while implementation uses SHA-256(master_secret || tenant_id).

Required invariant:

New tenant key derivation uses a formally specified, domain-separated KDF.

Existing ciphertext remains recoverable through a safe migration strategy.

Required work:

1. Inspect current encryption format.
2. Identify how existing ciphertext is stored.
3. Design versioned key derivation.
4. Implement migration compatibility.
5. Add new encryption path.
6. Add decrypt compatibility for legacy data.
7. Test tenant isolation.
8. Test migration/re-encryption.
9. Test failure on wrong tenant identity.

Do NOT simply switch the KDF and invalidate existing ciphertext.

Security requirements:
- no secret logging
- no plaintext persistence
- no cross-tenant key reuse

Definition of done:
New derivation is hardened and existing data has a safe migration path.