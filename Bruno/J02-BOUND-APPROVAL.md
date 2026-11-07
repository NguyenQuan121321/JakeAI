# J02 bound approval requests

The repaired API has54 operations across49 paths. All52 client operations are
represented in public Bruno requests;2 internal operations remain covered by
the existing pytest contract. The strict reconciliation gate has zero missing
or obsolete operations. September17 inventory/reconciliation documents are
historical snapshots; their original results are retained.

For an isolated synthetic authority with the dedicated store/key/active-policy
configuration described in `docs/security/j02-identity-authorization.md`, create
a requester-owned task with the existing01 request, then manually run:

1. `11 — Start Bound Approval Run`: requester `token_a` and a different signed
   subject's numeric `approval_approver_id`; only the existing safe calculator.
2. `12 — Get Bound Approval`: capture the server's immutable action hash.
3. `08 — Approval Decision`: separate `approval_approver_token` with the signed
   `agent:approve` permission; the request binds that exact hash.
4. `13 — Consume Bound Approval`: requester consumes once; a replay is409.

To test cancellation, start a fresh proposal and use14 before consumption.
Use valid short-lived tokens and private environment variables; store no bearer
credentials in tracked files. Unavailable store/state or missing grants must
fail. These requests require positive results and do not accept errors as PASS.

Bruno reconciliation is schema/request coverage, not execution acceptance.
Actual two-worker/Finn/Redis/rotation/fault execution is recorded separately by
the guarded J02 hosted rehearsal. General checkpoint resume, file/shell/payment
and arbitrary mutation tools remain disabled.
