# REPAIR-11 — AGT-02 DEFERRED TOOL DISCOVERY

Finding:
AGT-02

Objective:
Prevent all full tool schemas from being retransmitted on every agent iteration.

Required invariant:

The agent receives enough tool information to choose actions while detailed schemas are loaded only when necessary.

Required work:

- define lightweight tool index;
- define discovery mechanism;
- load detailed schema on demand;
- preserve authorization and risk metadata;
- preserve tool selection correctness.

Required tests:

- small tool catalog
- large tool catalog
- authorized/unauthorized tool
- correct detailed schema retrieval
- tool selection remains correct

Measure:
token overhead before/after.

Do not claim token savings without benchmark evidence.