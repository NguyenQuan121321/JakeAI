# REPAIR-15 — DUP-03 PRICING AUTHORITY

Finding:
DUP-03

Objective:
Create one authoritative pricing implementation.

Required invariant:

Every system component calculating provider cost uses the same pricing authority and the same formulas.

Required work:

- compare existing pricing implementations;
- define authoritative owner;
- migrate callers;
- remove redundant active formulas;
- preserve pricing versioning;
- update tests.

Required validation:

Equivalent inputs through all supported callers produce identical pricing results.

Forbidden:
Do not change provider pricing values merely as part of consolidation.