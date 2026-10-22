# BYOK provisioning and recovery

Production API and worker use the same validated settings. Provision independent
32-byte random signing, internal perimeter, Finn service and audit secrets as
64 hex characters; provision AES-256 masters as canonical base64 of exactly 32
random bytes. Use a secret manager or protected environment injection. Generate
each independently with an approved CSPRNG. Format/diversity checks cannot prove
random generation provenance. Do not hash passphrases to satisfy provisioning.
The service/audit settings reserve separate material for their respective work;
this task does not implement Finn introspection or a durable audit system.

`BYOK_MASTER_KEY` is the sole current encryption setting;
`BYOK_ENCRYPTION_MASTER_KEY` does not configure it. Supply an explicit
`BYOK_MASTER_KEY_ID`, optional JSON map `BYOK_PREVIOUS_KEYS`, and JSON inventories
`BYOK_RETIRED_KEY_IDS` / `BYOK_RETIRED_KEY_HASHES` (SHA256 of decoded master bytes).
Key IDs are immutable and never reused for different material. Preserve the
retirement inventories independently of database restoration and old deployment
manifests. Known published signing keys are unconditionally retired, including
development and explicit-key verifier calls. Never restore those fallbacks.

Use a dedicated BYOK Redis URL, protected network/ACL and transport as required
by the selected topology. Production Compose uses its own persistent volume,
noeviction, AOF and always-fsync; the evictable cache remains separate. Startup
needs PING and CONFIG GET for those durability settings; runtime needs GET, SET,
DEL, EVAL and SCAN within the vault namespace. Capacity/ACL/storage failures
return `BYOK_STORAGE_UNAVAILABLE`; they never acknowledge a RAM-only success.
Capacity planning, host/disk loss, replicas, backup encryption and approved
recovery objectives still need operational qualification. The extra vault
container has a 192 MB limit; include it in the actual host resource budget.

Before a versioned rollout, stop old writers, inventory old `byok:*` records and
securely back up ciphertext plus metadata. Separately escrow the matching key
IDs/material and independently protected retirement inventory. Unversioned
records lack authenticated provider/owner attribution and are deliberately
blocked. Plan a reviewed migration or re-enrollment with the data owner. No
automatic legacy purge or use of the published old master is provided.

For an uncompromised synthetic/staging data-key rotation:

1. Back up records and verify access to matching independently escrowed masters.
2. Provision a fresh current ID/material and retain old material only in the
   previous map. Restart every writer with the new ring; stop all old writers.
3. Run `python -m app.core.byok_migrate --count 100`. It reports counts/cursor and
   fixed error codes, never plaintext or ciphertext. Conflicts/errors exit 1.
4. Resume from the reported cursor for interrupted traversal, then repeat from
   cursor 0. SCAN can repeat keys; CAS makes double migration harmless. After any
   fault, repeat full passes until one has zero migrations/conflicts/errors.
5. Verify all current reads, revoked states, owners and provider injection before
   removing previous material. Assess every backup still requiring the old key.
   Retire IDs/digests only after approved recovery/retention disposition. No
   token-drain deadline or automatic purge applies to encrypted data.

Readers holding the current/previous ring can read either generation while
CAS migration runs. Updates always encrypt with the current key; a stale
migrator cannot overwrite them. Concurrent metadata changes, deletion and
validation also compare their observed record. A storage timeout after a write
may mean the write committed; reconcile by reading before retrying. There is no
cross-slot transaction or distributed rollout lock; stop old writers as part of
the procedure. Repeated old writers can prevent migration completion.

Restore requires the matching master bytes and IDs, a compatible versioned
reader, owner/tenant attribution, isolated persistent Redis, and the latest
independently protected retirement inventory. Restore synthetic snapshots into
an isolated store and demonstrate successful reads and wrong/missing-key
failure. Restoring ciphertext without its master is not recovery. If a master
is compromised, incident handling/re-enrollment replaces the ordinary procedure;
rollback must not reactivate it or remove retirement safeguards. An older valid
record replay at the same slot is outside this envelope's freshness protection.

Metadata listing is owner scoped for ordinary authenticated callers: only their
own stored records are returned. Foreign and nonexistent slots are both omitted;
an omitted slot is not a statement that no credential exists. The console labels
those slots "Not Visible". An explicitly permitted delegated tenant administrator
can see the full tenant inventory. Direct foreign-record mutations remain denied.
Storage and decryption failures still return truthful errors rather than being
represented as missing or unconfigured credentials.

Public failures distinguish `BYOK_NOT_CONFIGURED` (404), owner/permission denial
(403), conflict/corruption/legacy/version/revocation (409), and unavailable
storage/material or retired/unknown masters (503). Provider validation only
reports valid after an observed HTTP 200; 429, outages and unexpected responses
are unavailable, not successful validation. Tests use controlled transports;
test-named keys have no runtime exemption. Provider bodies and nested diagnostics
are sanitized using request-local exact credential values in addition to the
existing patterns. This is scoped BYOK evidence, not global observability or
zero-exposure certification. Previews never include a raw prefix/suffix.

`scripts/j03_runtime.py` starts a uniquely named synthetic production Compose
project on an existing Docker engine and cleans up only its own containers and
volumes. It checks the built image's default-command negatives, injected API and
worker settings, real HTTP permissions, persistent Redis, process/store restart,
rotation, re-encryption, retirement and outage responses. CI runs it on the same
image subsequently scanned by the unchanged Trivy gate. A missing engine or
failed/skipped rehearsal is BLOCKED/FAILED acceptance, never runtime PASS.
