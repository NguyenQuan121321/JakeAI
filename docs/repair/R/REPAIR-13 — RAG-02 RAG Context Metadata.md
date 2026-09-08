# REPAIR-13 — RAG-02 MODEL-VISIBLE CONTEXT METADATA

Finding:
RAG-02

Objective:
Prevent internal retrieval scores from unnecessarily entering model-visible context.

Required invariant:

Internal retrieval metadata remains available to telemetry and application logic without polluting the semantic evidence presented to the model.

Required work:

- inspect context formatting;
- remove unnecessary score text from model context;
- preserve source/citation identity;
- retain score in metadata/telemetry;
- update affected tests.

Required tests:

- source labels preserved
- citation anchors preserved
- scores remain available to internal telemetry
- model-visible context excludes irrelevant internal score values

Forbidden:
Do not remove retrieval metadata from application-level observability.