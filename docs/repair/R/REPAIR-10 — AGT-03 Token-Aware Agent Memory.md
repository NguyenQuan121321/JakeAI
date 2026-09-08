# REPAIR-10 — AGT-03 TOKEN-AWARE AGENT MEMORY

Finding:
AGT-03

Objective:
Replace message-count-only memory management with token-aware context management.

Required invariant:

Agent memory remains within its context budget while preserving:
- user goals
- constraints
- verified facts
- decisions
- current state
- relevant recent turns

Required work:

- introduce token accounting for memory;
- define context budget;
- compact when threshold is reached;
- preserve invariant information;
- discard stale observations safely;
- maintain system/dependency state.

Required tests:

- large message
- many messages
- constraint retention
- fact retention
- compaction behavior
- token budget boundary

Forbidden:
Do not blindly increase max_entries.
Do not use summary output that is not tested for information retention.