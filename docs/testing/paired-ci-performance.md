# Paired CI performance comparison — inactive, review required

This implementation adds executable capture and comparison support. No active
workflow invokes it. Legacy v1 remains byte-identical and blocking. This is not
a numerical baseline replacement, a production SLO or J02 acceptance.

## Contract proposed for activation

`paired-ci-review-v1` compares candidate against **pre-J02 main
64f087ca708200a2c81ba646acfa6112876f601c**, the parent of the original J02 merge.
The previous bed2473 control already contains J02 and is not substituted for
this control. Both checkout SHAs and backend tree IDs are recorded; a missing,
moving, self-referential or different control blocks with exit 2. Candidate is
the exact PR head, not an unstated main checkout.

The six full workloads are unchanged: chat 30/10, agent 15/5, RAG 30/10,
SSE 16/8, Redis 50/15, Qdrant 30/10 (requests/concurrency). Both subjects use
one Python 3.12.15 environment, frozen installed dependencies, matching pinned
Redis/Qdrant images/configuration and the same measurement harness. The
pre-J02 requirements file has older pypdf; the shared installed environment
deliberately reconciles it to the candidate constraint without editing source.
Installed distributions, runner image, CPU model/count/quota and job identity
are captured and must match. No historical median is used as a reference.

Each subject has its own job-owned Redis/Qdrant instances. This preserves its
state while the other subject runs. Stores must start empty; no reset occurs
between a subject's initial and confirmation. Endpoints are fixed loopback
ports; container identity, published port and image digest are checked. Redis
effective persistence/eviction configuration is queried live. Qdrant effective
configuration is reconstructed from actual default/production/local files and
startup command/environment; mounts/overrides outside the supported contract
block. Configuration and identities are rechecked before and after each phase.
These are benchmark stores, not the separate durable approval authority store.
The reconstruction order follows the pinned upstream
[Qdrant settings implementation](https://github.com/qdrant/qdrant/blob/v1.12.1/src/settings.rs#L168)
and [production image environment](https://github.com/qdrant/qdrant/blob/v1.12.1/Dockerfile#L147).

Both subjects perform the original six-scenario warmup, then initial samples.
Only initially failed scenarios receive **one matched confirmation on both
subjects**, with no third trial or selecting a better trial. Confirmation
decides timing; any request, correctness, security, real-store fallback,
changed cache mix, missing/invalid measurement or integrity failure in either
phase stays fatal. Invalid control is inconclusive/blocking, never a passing
candidate reference. Reports retain both phases, findings, the exact required
confirmation set and reproducibility annotations. A supplied replay's extra
observed confirmations remain retained and are checked for fatal errors.

Latency uses the existing scenario tolerances: 40% (Redis 50%), 20 ms absolute
significance, and existing rounded latency detector formulas. Throughput keeps
the documented 50% allowed drop. Its proposed significance floor is
`min(25 rps, control_rps * allowed_drop_fraction)`, with unrounded relative
comparison. At high references this retains the old 25-rps filter. At low
references it detects a severe collapse instead of making failure impossible.
For example 23.95 -> 0.1 rps fails; the old 25-rps rule only warns. No reference
or tolerance was selected to pass a candidate. Zero/NaN/inconsistent throughput
is a fatal measurement, not a performance success. A control exceeding the
existing 180-second capture deadline (per phase or scenario) is unusable and
blocks; this liveness bound is not an approved absolute capacity budget.

Exit 0 means within this proposed relative contract, exit 1 is candidate
regression/fatal error, and exit 2 is incompatible/inconclusive capture/control.
Both nonzero outcomes block. Shared environmental slowness can still affect
both subjects; relative success does not certify production capacity or G4.

## Explicit control harness adaptation

The source checkouts remain clean. A long-lived private worker imports the
subject's application modules, core/security, stores and native JWT fixture.
Only `app.performance` is overlaid with the common candidate measurement
harness, including current useful-response checks. Synthetic trust, equivalent
permissions/issuer/audience and 900-second expiry are provisioned before
measurement. Native source-specific key/claim formats remain intact. Synthetic
Finn state is attached where implemented; no JWT verifier, permission dependency
or application effect is patched. Provider effects remain the inherited
deterministic stubs. The overlay and bootstrap have a recorded hash; this is
application overhead with synthetic authorities/models, not a real Finn or
provider integration. Other security/J03/approval tests remain independent.

## Commands and review boundary

Offline evidence audit (no store access):

```sh
cd backend
python -m app.performance.paired --evidence samples.json --output comparison.json
pytest tests/unit/test_paired_performance.py tests/performance/test_confirmation_contract.py
```

Guarded hosted capture, after approval and application of the inactive patch:

```sh
python scripts/j02_paired_benchmark.py --control paired-pre-j02-control --output paired-performance.json
```

The capture command refuses local/fork/private/wrong-branch use, requires
explicit `J02_PAIRED_CONTRACT=review-v1` and four owned service container IDs.
Private worker logs and ephemeral keys are not published; only allowlisted
measurement/provenance data leave the private directory. Workers and private
files are cleaned in finally; GitHub removes the service containers. Missing
configuration or capture failures remain blocking.
Received samples are retained before post-measurement configuration probes;
probe failures, configuration drift or later source/baseline identity failures
produce an inconclusive result without discarding the received measurements.

`scripts/j02_replay_paired.py` accepts the exact frozen five-pair receipt file,
retains all 240 scenario records / 3420 operations and emits diagnostic numeric
comparisons. It exits **2**, because the old control/harness/configuration
provenance cannot qualify the new contract. Replay is not fresh hosted evidence.

## One activation decision and rollback

Review `paired-ci-performance.activation.patch`. Approving and applying that
exact patch adds **one additive paired CI check** on the existing public,
same-repository PR branch, with four isolated pinned store services and USD0
standard GitHub-hosted Ubuntu. It does not remove or downgrade any active v1
check; v1's existing blocking failure remains visible. The first fresh paired
execution and its provenance/compatibility must then be reviewed. Approval does
not guarantee the candidate passes and does not qualify production SLOs.

The patch is deliberately outside `.github/workflows`; it is inactive until
explicitly approved and applied. No new load cohort is authorized by committing
this support. Do not dispatch a calibration to obtain a green result.

Rollback after activation deletes the one added workflow. Existing v1,
thresholds, dependency selection and security gates require no rollback because
the patch does not change them. There is no data/schema migration. Removing the
new support files later is optional; they have no default runtime call path.

**Decision for review:** enable this additive paired CI contract and its first
bounded hosted comparison, or leave it inactive. Replacing/waiving the v1 gate
is a different contract migration and is not included or authorized here.
