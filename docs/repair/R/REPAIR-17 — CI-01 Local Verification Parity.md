# REPAIR-17 — CI-01 LOCAL VERIFICATION PARITY

Finding:
CI-01

Objective:
Ensure developers can reproduce the relevant CI verification locally without weakening CI gates.

Current condition:
Coverage is enforced at >=85%.

Required invariant:

Local verification has a documented and reproducible path that matches the essential CI environment and thresholds.

Required work:

- inspect the difference between local and CI test environments;
- identify service dependencies;
- identify why containerless execution can differ;
- improve fixtures/mocks where appropriate;
- preserve >=85% threshold;
- do not disable coverage gates;
- do not weaken CI requirements.

Required validation:

- local verification without live services where intended;
- CI-equivalent verification with services;
- coverage consistency;
- fallback branch coverage.

Forbidden:
Do not lower the 85% threshold.
Do not hide coverage failures.
Do not redesign CI architecture.