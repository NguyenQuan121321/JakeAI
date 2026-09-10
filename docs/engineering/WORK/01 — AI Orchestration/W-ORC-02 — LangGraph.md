# W-ORC-02 — LangGraph

## OBJECTIVE

Make LangGraph the concrete workflow execution mechanism for the graph-based JakeAI orchestration path.

## REQUIRED GRAPH

START
→ Supervisor
→ conditional specialist/tool branch
→ Verifier
→ either Revision or Synthesizer
→ END

## IMPLEMENTATION

Use `StateGraph`.

Define one explicit state object.

State must contain only workflow data required for execution.

Use typed node outputs.

Use conditional edges for routing.

Use explicit END termination.

## EXISTING REPOSITORY ALIGNMENT

The existing `backend/app/agents/graph.py` already contains:
- supervisor;
- financial specialist;
- FinnApiGo tool;
- verifier;
- synthesizer.

Preserve these working nodes unless the assigned task specifically replaces their behavior.

## ROUTING

Supervisor returns a typed/validated decision.

Verifier returns a typed verdict.

Do not duplicate routing rules inside nodes.

## LOOP CONTROL

Revision loop MUST have:

- maximum revision_count;
- cancellation check;
- timeout;
- terminal failure state.

## TESTS

Test graph topology and behavior separately.

Topology:
- expected nodes;
- expected edges.

Behavior:
- specialist route;
- tool route;
- verification success;
- revision loop;
- terminal failure.

## FORBIDDEN

- free-form graph mutation at runtime;
- hidden recursive graph creation;
- infinite verifier loops;
- duplicate routing heuristics.

## ACCEPTANCE

The LangGraph workflow executes deterministically through the intended nodes with bounded revision behavior.