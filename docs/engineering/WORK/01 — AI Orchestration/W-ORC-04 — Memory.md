# W-ORC-04 — Memory

## OBJECTIVE

Complete bounded agent memory without allowing unbounded conversation growth.

## REQUIRED MEMORY LAYERS

1. Short-term run memory
2. Long-term memory
3. Checkpoint state

Do not merge these into one unbounded message list.

## SHORT-TERM

Store only information required for the current run.

Preserve chronological order.

## LONG-TERM

Store explicitly selected durable facts only.

Do not automatically persist every model message.

## CHECKPOINT

Persist recoverable execution state:

- run_id;
- task_id;
- current node/step;
- relevant state;
- revision count;
- tool state;
- recovery metadata.

## TOKEN BOUNDARY

Memory retrieval must be budget-aware.

Prioritize:

1. current task requirements;
2. verified facts;
3. unresolved constraints;
4. recent relevant context;
5. older context.

Do not append the entire historical conversation blindly.

## TESTS

- short memory;
- long history;
- irrelevant history;
- memory limit;
- checkpoint resume;
- wrong tenant;
- concurrent runs.

## FORBIDDEN

- infinite memory accumulation;
- storing secrets;
- storing raw provider keys;
- cross-tenant memory retrieval.

## ACCEPTANCE

Agent memory remains bounded, tenant-scoped and sufficient for multi-step execution.