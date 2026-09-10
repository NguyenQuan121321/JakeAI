# W-ORC-00 — Core Workflow

## OBJECTIVE

Make JakeAI's core AI workflow execute end-to-end through one clearly defined active execution path.

## CURRENT TARGET

Preserve existing working agent behavior.

Do not replace LangGraph or Agent Runtime unless inspection proves one blocks the target.

## REQUIRED FLOW

Request
→ authenticated context
→ task normalization
→ orchestration decision
→ agent execution
→ optional tool execution
→ result validation
→ final synthesis
→ response/stream

## IMPLEMENTATION

1. Identify the currently active entrypoint.
2. Trace every function from API request to final response.
3. Identify whether `backend/app/agent/` or `backend/app/agents/` is the active execution authority for each path.
4. Do not delete either subsystem merely because both exist.
5. Establish which path owns:
   - task creation;
   - run creation;
   - state;
   - planning;
   - tool execution;
   - final answer.
6. Missing functionality must be added to the active path.
7. If two paths implement the same active responsibility, preserve the existing production path and record the duplicate for RIGHT/FAST unless the duplicate blocks the workflow.

## DATA FLOW

Request
→ TenantContext
→ Agent task/run state
→ Planner
→ Agent backend
→ Tool Registry when required
→ Agent output
→ final response

## REQUIRED TESTS

- simple one-step request;
- multi-step request;
- tool request;
- failed tool;
- cancellation;
- wrong tenant;
- empty output.

## FORBIDDEN

- creating a third orchestration system;
- replacing LangGraph only for architectural preference;
- deleting Agent Runtime;
- moving files without necessity;
- changing authentication.

## ACCEPTANCE

One documented execution path successfully completes an end-to-end task.