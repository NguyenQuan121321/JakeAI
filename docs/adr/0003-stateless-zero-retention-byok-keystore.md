# ADR-003: Versioned encrypted server-side BYOK custody

Status: corrected by J03. The original zero-retention/OS-keystore proposal was
not implemented by the HTTP vault. This decision describes actual custody.

The backend persists encrypted tenant/provider credentials in Redis. It decrypts
them in Python memory for provider injection. Operators provision encryption
masters separately through environment injection. There is no implemented OS
keystore, external KMS, guaranteed memory wiping, or protection from an attacker
who controls both the running application and its encryption material.

Records use AES-256-GCM with a fresh 96-bit nonce. A canonical JSON header binds
schema version 1, master key ID, explicit tenant, provider and positive record
revision as authenticated associated data. The ciphertext contains the API key,
owner, lifecycle status, timestamps and validation metadata. Previews are constant
masks derived by the application, never trusted store-supplied text. Header changes
or substitution across tenants/providers/versions fail authentication. The store
remains trusted for availability and freshness: a replay of a complete older
valid envelope at the same slot is not cryptographically detectable.

Production requires a separate persistent, non-evicting BYOK Redis and explicit
provisioned current/previous key material. Startup checks AOF, always-fsync and
noeviction configuration. There is no process-memory fallback after an outage.
Development/tests may explicitly select an in-memory store; that store has no
cross-process or restart durability. Neither configuration proves backup quality,
HA, approved retention, RPO/RTO, or a production deployment.

Each tenant/provider slot belongs to its first authenticated writer. HTTP reads
require exactly `byok:read`; mutations and provider probes require exactly
`byok:write`. Existing records require the owner or an explicitly signed
`tenant_admin` role plus the exact permission, scoped to the verified tenant.
Roles, wildcards, scopes, client tenant headers and `byok:manage` do not replace
these grants. The ordinary `default` tenant has the same rules. This BYOK boundary
does not qualify the existing JWT verifier or Finn introspection; those are J02.

Writes, rotations, validations, revocations, deletion and re-encryption use atomic
compare-and-swap against the complete observed envelope. A race returns a conflict
instead of overwriting a concurrent change. Dependency errors are fixed codes;
they do not disclose secrets or silently become absent/demo credentials. A lost
write reply can leave an unknown outcome, requiring a read to reconcile.

Old unversioned records do not establish authenticated provider or owner. They
are detected at their old storage names and fail with `BYOK_LEGACY_RECORD` rather
than being automatically adopted. Before rollout, inventory and back them up;
use a separately reviewed offline attribution/migration or authorized enrollment
after disposition of the old record. Do not decrypt using a public old master or
erase old data merely to pass startup. Mixed old/new writers are unsupported.

Current writes always use the current master. Previous masters are read-only
migration material. Re-encryption repeats complete scans and CAS updates; faults
and conflicts are reported, and successful updates survive retry/restart. Before
retirement, stop old writers and require a subsequent complete pass with no
migrations, conflicts or errors. Keep the retired-ID and retired-material-digest
inventory outside restored ciphertext backups; supply it to every restart.
Retired material is refused even if renamed. Removing that trusted inventory or
running an old binary defeats retirement and is forbidden rollback practice.

Signing-key retirement and data-key migration have different lifetimes. The
JWT token drain is never a ciphertext deletion deadline. A compromised master
cannot be restored as active for rollback. Retention, backups, physical erasure
and incident recovery require the separate approved policy; no automatic purge
or live rotation is introduced. See [BYOK operations](../security/byok-operations.md).
