# REPAIR-01 — PROV-02 STRUCTURED CONVERSATION CONTRACT

Finding:
PROV-02

Priority:
CRITICAL

Objective:
Preserve complete multi-turn conversation semantics from gateway to provider adapters.

Current defect to verify:
ProviderRequest does not carry structured messages, while the gateway reduces conversation context to the last user message or flattened text.

Required invariant:

A structured conversation must preserve:

- role
- ordering
- content
- assistant turns
- tool messages
- tool call identity
- system instructions

through the provider boundary without semantic loss.

Required work:

1. Inspect GatewayChatRequest.
2. Inspect ProviderRequest.
3. Inspect all active provider adapters.
4. Identify every point where history is flattened or discarded.
5. Introduce/reuse canonical ChatMessage representation.
6. Extend provider request contract appropriately.
7. Map canonical messages into each provider format.
8. Preserve backward compatibility for valid single-prompt callers.
9. Add contract tests for multi-turn behavior.

Required tests:

- 5-turn conversation
- assistant recall
- system instruction preservation
- tool message preservation
- ordering preservation
- provider adapter translation

Forbidden:

Do not redesign cache identity unless strictly required by the message contract.
Do not repair unrelated token accounting.

Definition of done:

No valid multi-turn conversation loses semantic history at the provider boundary.