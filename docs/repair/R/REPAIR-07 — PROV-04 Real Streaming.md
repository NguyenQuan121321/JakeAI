# REPAIR-07 — PROV-04 REAL STREAMING

Finding:
PROV-04

Objective:
Replace fake word-by-word replay with true upstream streaming.

Required invariant:

When streaming is requested, upstream chunks are consumed incrementally and forwarded incrementally to the client.

Required work:

1. Inspect provider stream interfaces.
2. Identify providers that support streaming.
3. Connect gateway streaming path to adapter.stream().
4. Forward chunks incrementally.
5. Handle disconnects.
6. Handle provider errors.
7. Preserve usage/accounting behavior.
8. Preserve final event semantics.

Required tests:

- first chunk arrives before full completion
- multi-chunk response
- provider failure
- client disconnect
- final completion event

Benchmark:

Measure TTFT.

Do not claim latency improvement without real measurement.

Forbidden:
Do not retain fake streaming as the primary implementation.