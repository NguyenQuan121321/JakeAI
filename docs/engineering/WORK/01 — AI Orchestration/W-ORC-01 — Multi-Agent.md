# W-ORC-01 — Multi-Agent

## OBJECTIVE

Complete multi-agent execution so JakeAI can divide a complex request into specialized agent work and combine the results deterministically.

## REQUIRED MODEL

Use a supervisor/planner architecture.

Request
→ Supervisor/Planner
→ Agent selection
→ Specialist execution
→ Optional tool execution
→ Verification
→ Synthesis

## RULE

Agents must have explicit responsibilities.

Do not create agents that exist only to rename the same LLM call.

## REQUIRED AGENT TYPES

At minimum:

1. Supervisor/Planner
2. Specialist
3. Tool-capable Agent
4. Verifier
5. Synthesizer

Reuse existing implementations where they already exist.

## STATE

Every agent execution must carry:

- task_id;
- run_id;
- tenant_id;
- user_id;
- permissions;
- current step;
- previous outputs;
- tool calls;
- verification state;
- cancellation state;
- iteration count.

## DECISION RULE

The supervisor must return a typed routing decision.

Do not use ad-hoc string matching in multiple modules.

## REQUIRED BEHAVIOR

Simple task:
→ minimum necessary agents.

Complex task:
→ decompose into specialist work.

Tool task:
→ tool-capable agent.

Untrusted/unsupported result:
→ verifier.

Verified result:
→ synthesizer.

## FAILURE

Agent failure:
→ bounded recovery.

Repeated failure:
→ terminate with explicit failure state.

Never loop indefinitely.

## TESTS

- single-agent task;
- multi-agent task;
- wrong-agent selection;
- verifier rejection;
- revision;
- maximum iteration;
- timeout;
- cancellation.

## FORBIDDEN

- unlimited recursive agent spawning;
- hidden agent calls;
- unbounded loops;
- bypassing authorization;
- letting every agent access every tool.

## ACCEPTANCE

Complex requests can execute through multiple specialized agents with bounded state transitions and a final synthesized result.