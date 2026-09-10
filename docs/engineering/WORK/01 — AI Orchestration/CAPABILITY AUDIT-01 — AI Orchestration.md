# CAPABILITY AUDIT-01 — AI Orchestration

**Auditor**: JakeAI Universal AI Engineering Worker  
**Audit Capability**: AI Orchestration (Capability 01)  
**Assigned Specifications**: `docs/engineering/WORK/01 — AI Orchestration/` (`W-ORC-00` to `W-ORC-05`)  
**Repository Working Baseline**: `E:\JakeAI` (Git Branch: `feat/repair-03-canonical-provider-resolution`)  
**Audit Date**: 2026-09-09  
**Audit Standard**: Exhaustive runtime trace, static analysis, import/caller resolution, and test execution parity. Code modifications, bug repairs, refactoring, and optimizations are strictly forbidden.

---

# 1. Executive Summary

A comprehensive architectural and code-level audit of the **AI Orchestration** capability within JakeAI was conducted. The audit inspected every file, class, entrypoint, caller, data contract, state model, and test suite across both `backend/app/agent/` and `backend/app/agents/`, as well as related API endpoints (`/api/v1/chat`, `/api/v1/agent`, `/api/v1/coding`).

### Core Findings

1. **Two Competing, Disconnected Orchestration Systems**:
   JakeAI does not possess a single coherent orchestration authority. Instead, the repository contains two completely isolated, parallel, and competing implementations:
   - **`backend/app/agents/` (Plural)**: A LangGraph-based pipeline wired to the user-facing chat streaming endpoint (`POST /api/v1/chat/stream`). This system claims to be a multi-agent quantitative and tool execution graph. In reality, **none of its specialist agent nodes execute real LLM reasoning**. Routing is performed via naive regex substring matches; financial calculations are hardcoded arithmetic; tool execution returns static mock dictionaries; and token streaming is simulated by splitting the completed markdown text into words with `asyncio.sleep(0.002)`.
   - **`backend/app/agent/` (Singular)**: An autonomous ReAct-style Agent Platform introduced in Phase 08, wired to REST endpoints (`POST /api/v1/agent/tasks`, `/runs`, `/approvals`). This system contains a genuinely working bounded planning engine (`BoundedPlanner`), real upstream model calls (`JakeAIBackend`), a formal tool registry with risk classification (`ToolRegistry`), and human-in-the-loop approval gating (`ApprovalManager`). However, it is **strictly single-agent**, contains **no LangGraph integration**, and is **100% disconnected from the primary chat streaming API**.
   - There are zero cross-imports between `backend/app/agent/` and `backend/app/agents/`. Neither subsystem is aware of the other.

2. **Absence of Real Multi-Agent Collaboration**:
   Multi-agent capability is classified as **PLACEHOLDER**. While `backend/app/agents/graph.py` defines a LangGraph topology containing 5 nodes (`supervisor`, `financial_specialist`, `finnapigo_tool`, `verifier`, `synthesizer`), there is no dynamic specialist coordination or emergent agent collaboration. The specialist agent does not receive prompts from an LLM planner; it merely applies deterministic regexes over user text. The tool node does not connect to FinnApiGo or the `ToolRegistry`; it returns hardcoded mock dictionaries.

3. **Critical Quality Gate & Security Flaw in Verifier**:
   In `backend/app/agents/verifier.py`, when verification fails (due to arithmetic variance, low groundedness, or **even a multi-tenant boundary breach**), the verifier requests revision if `revision_count < 2`. However, once `revision_count >= 2`, the condition evaluates to `False`, and the function **unconditionally falls through to `# 5. Quality gates passed`**, returning `verification_verdict: "PASS"`. This causes multi-tenant isolation breaches and ungrounded hallucinations to be passed to the synthesizer and output to the client as "Verified by JakeAI".

4. **Ephemeral Memory & Checkpointing (No Recovery Across Restarts)**:
   All state management, checkpointing, and long-term memory across both systems are held in transient Python heap memory (dictionaries). Although `CheckpointManager` docstrings claim "dual memory + Redis caching", zero Redis persistence code exists. If an ASGI worker restarts, all active tasks, runs, pending human approvals, checkpoints, and long-term memories are instantly wiped out. Restart recovery is **BROKEN / UNIMPLEMENTED**.

5. **ADR-001 Resume Bridge is Non-Rehydrating**:
   The `ResumeBridgeManager` (`backend/app/services/resume_bridge.py`) implements Redis state locking for developer workstation tool results (`POST /api/v1/coding/tool-result`), but `resume_checkpoint` does not rehydrate or resume any LangGraph graph or agent execution loop. Furthermore, `save_checkpoint` is never called by any production workflow.

---

# 2. Capability Status Matrix

| Capability | Status | Implementation | Entry Point | Evidence | Tests | Problems |
| :--- | :--- | :--- | :--- | :--- | :--- | :--- |
| **Agent Runtime** | `DUPLICATED` | `app/agent/runtime/manager.py`, `runner.py`, `loop.py` | `get_agent_manager()`, `/api/v1/agent/tasks` | [manager.py:33](file:///e:/JakeAI/backend/app/agent/runtime/manager.py#L33) | `test_agent_platform.py` (39 tests) | Disconnected from `/api/v1/chat/stream`; completely separate from `app/agents`. |
| **Multi-Agent Execution** | `PLACEHOLDER` | `app/agents/graph.py`, `supervisor.py`, `financial_specialist.py` | `stream_multi_agent_workflow()` | [graph.py:35](file:///e:/JakeAI/backend/app/agents/graph.py#L35) | `test_multi_agent.py` | Nodes use regex heuristics and static mock data; no real LLM multi-agent reasoning. |
| **LangGraph Execution** | `PARTIAL` | `app/agents/graph.py` | `create_agent_graph()`, `agent_graph.astream()` | [graph.py:35-81](file:///e:/JakeAI/backend/app/agents/graph.py#L35-L81) | `test_multi_agent.py` | Compiled without checkpointer; no `interrupt()`; static hardcoded graph; lacks dynamic edge routing. |
| **Agent State Management** | `DUPLICATED` | `app/agents/state.py` vs `app/agent/state/models.py` | `AgentState` vs `TaskState`/`RunState` | [state.py:8](file:///e:/JakeAI/backend/app/agents/state.py#L8), [models.py:50](file:///e:/JakeAI/backend/app/agent/state/models.py#L50) | Tested in respective test suites | 3 conflicting state models (`AgentState`, `TaskState`/`RunState`, `WorkflowExecution`); zero interop. |
| **Planning & Supervision** | `DUPLICATED` | `app/agent/planning/planner.py` vs `app/agents/supervisor.py` | `BoundedPlanner.determine_next_action` vs `classify_intent` | [planner.py:29](file:///e:/JakeAI/backend/app/agent/planning/planner.py#L29), [supervisor.py:22](file:///e:/JakeAI/backend/app/agents/supervisor.py#L22) | `test_agent_platform.py`, `test_harmonization.py` | BoundedPlanner is single-agent JSON planner; supervisor is crude regex keyword classifier. |
| **Agent Backends** | `PARTIAL` | `app/agent/backends/jakeai.py`, `direct_provider.py`, `external_agent.py` | `JakeAIBackend.generate()` | [jakeai.py:31](file:///e:/JakeAI/backend/app/agent/backends/jakeai.py#L31) | `test_agent_platform.py` | Working provider adapter in `app/agent`, but completely ignored by `app/agents/` and synthesizer. |
| **Tool Execution Layer** | `PARTIAL` | `app/agent/tools/registry.py` | `ToolRegistry.execute()` | [registry.py:71](file:///e:/JakeAI/backend/app/agent/tools/registry.py#L71) | `test_agent_platform.py` | Fully functional in `app/agent`, but `app/agents/finnapigo_tool.py` and `coding.py` completely bypass it. |
| **Tool Registry & Discovery** | `PARTIAL` | `app/agent/tools/registry.py` | `ToolRegistry.discover()`, `get_tool_registry()` | [registry.py:37](file:///e:/JakeAI/backend/app/agent/tools/registry.py#L37) | `test_agent_platform.py` | Only 5 basic built-in tools (`read_file`, `calculator`, etc.); zero enterprise/FinnApiGo/DB/Git tools. |
| **Memory (Short-Term)** | `PARTIAL` | `app/agent/memory/short_term.py` | `ShortTermMemory.add_message()` | [short_term.py:19](file:///e:/JakeAI/backend/app/agent/memory/short_term.py#L19) | `test_agent_platform.py` | Bounded FIFO (50 messages), but based on entry count instead of token budgets; ephemeral. |
| **Memory (Long-Term)** | `PLACEHOLDER` | `app/agent/memory/long_term.py`, `manager.py` | `AgentMemoryManager.remember_episodic()` | [long_term.py:15](file:///e:/JakeAI/backend/app/agent/memory/long_term.py#L15) | `test_agent_platform.py` (isolated test only) | In-memory only; completely unconnected to `AgentExecutionLoop` and `BoundedPlanner` (dead code). |
| **Checkpointing** | `BROKEN` | `app/agent/state/checkpoint.py` | `CheckpointManager.save_checkpoint()` | [checkpoint.py:22](file:///e:/JakeAI/backend/app/agent/state/checkpoint.py#L22) | `test_agent_platform.py` | Memory-only dictionary; claims Redis support in docstrings but has 0 lines of Redis code; lost on restart. |
| **ADR-001 Resume Bridge** | `BROKEN` | `app/services/resume_bridge.py`, `endpoints/coding.py` | `ResumeBridgeManager.resume_checkpoint()` | [resume_bridge.py:148](file:///e:/JakeAI/backend/app/services/resume_bridge.py#L148) | `test_resume_bridge.py` | Stores metadata in Redis, but `resume_checkpoint` never rehydrates LangGraph; `save_checkpoint` is never called in production. |
| **Human Approval** | `WORKING` | `app/agent/approvals/manager.py`, `policy.py` | `ApprovalManager.decide()`, `/api/v1/agent/.../approvals` | [manager.py:19](file:///e:/JakeAI/backend/app/agent/approvals/manager.py#L19), [policy.py:25](file:///e:/JakeAI/backend/app/agent/approvals/policy.py#L25) | `test_agent_platform.py` | Verified flow: pauses run, awaits human decision, resumes safely. Flaw: in-memory state lost on restart. |
| **Cancellation** | `PARTIAL` | `app/agent/runtime/runner.py`, `chat.py` | `AgentRunner.request_cancellation()`, `/cancel` | [runner.py:80](file:///e:/JakeAI/backend/app/agent/runtime/runner.py#L80), [chat.py:230](file:///e:/JakeAI/backend/app/api/v1/endpoints/chat.py#L230) | `test_agent_platform.py` | Cooperative flag checked between loop iterations. Does not cancel in-flight HTTP or tool executions. |
| **Timeout Handling** | `PARTIAL` | `app/agent/planning/planner.py`, `chat.py` | `BoundedPlanner.determine_next_action()`, `chat.py:214` | [planner.py:86](file:///e:/JakeAI/backend/app/agent/planning/planner.py#L86) | `test_agent_platform.py` | Evaluated at step boundaries only. `ToolRegistry.execute()` has no `asyncio.wait_for` timeout guard. |
| **Retry & Recovery** | `PARTIAL` | `app/core/circuit_breaker.py` | `CircuitBreaker.call_with_fallback()` | [financial_specialist.py:9](file:///e:/JakeAI/backend/app/agents/financial_specialist.py#L9) | `test_circuit_breaker.py` | Circuit breaker exists with static fallback; zero transient exponential retry with jitter; no restart recovery. |
| **Execution Streaming** | `PARTIAL` | `app/agent/runtime/runner.py` vs `app/api/v1/endpoints/chat.py` | `stream_run_events()` vs `generate_chat_stream()` | [runner.py:161](file:///e:/JakeAI/backend/app/agent/runtime/runner.py#L161), [chat.py:82](file:///e:/JakeAI/backend/app/api/v1/endpoints/chat.py#L82) | `test_multi_agent.py`, `test_agent_platform.py` | `app/agent` streams real step events. In `chat.py`, token streaming is simulated post-hoc via `split(" ")`. |
| **Agent Telemetry** | `PARTIAL` | `app/agent/telemetry.py` | `AgentTelemetry`, `/api/v1/agent/metrics` | [telemetry.py:33](file:///e:/JakeAI/backend/app/agent/telemetry.py#L33) | `test_agent_platform.py` | Thread-safe in-memory counters; disconnected from system Prometheus metrics in `app/telemetry/metrics.py`. |
| **Model Selection / Routing** | `MISSING` | `app/agent/runtime/models.py` | `AgentConfig.default_model` | [models.py:21](file:///e:/JakeAI/backend/app/agent/runtime/models.py#L21) | Untested | Static model string (`gemini-1.5-flash`); no dynamic capability-aware or cost-aware model routing in orchestration. |
| **Tenant & Permission Context** | `PARTIAL` | `app/agent/runtime/manager.py`, `tools/policy.py` | `Depends(get_current_tenant)` | [manager.py:99](file:///e:/JakeAI/backend/app/agent/runtime/manager.py#L99) | `test_agent_platform.py` | Tenant ownership checked in `app/agent`. Critical flaw in `app/agents/verifier.py` where tenant breach passes on revision >= 2. |
| **Subsystem Integration** | `BROKEN` | None | None | None | None | `backend/app/agent/` and `backend/app/agents/` have zero code linkages or shared abstractions. |

---

# 3. Actual Execution Paths

Trace analysis identified four separate, disjoint execution paths in the repository:

```
[Path 1: Main Chat SSE Stream]
Client Request: POST /api/v1/chat/stream
  → Depends(get_current_tenant)
  → GuardrailsEngine.inspect_input(prompt)
  → GuardrailsEngine.redact_pii(prompt)
  → SemanticCache.get(sanitized_prompt)
  → [if cache miss] stream_multi_agent_workflow(sanitized_prompt, context)  [backend/app/agents/graph.py]
      → agent_graph.astream(initial_state)
          → Node 1: supervisor_node [app/agents/supervisor.py]
              → classify_intent(prompt)  (REGEX MATCHING: FINANCIAL_PATTERNS / TOOL_PATTERNS)
              → hybrid_retriever.retrieve() + context_selector.select_context()
          → [Branch A]: financial_specialist_node [app/agents/financial_specialist.py]
              → _extract_numbers(prompt) (REGEX)
              → _compute_deterministic_financials() (NO LLM CALL)
          → [Branch B]: finnapigo_tool_node [app/agents/finnapigo_tool.py]
              → check_tool_rbac_guardrail()
              → returns HARDCODED MOCK DICTIONARY (NO ToolRegistry, NO HTTP call)
          → Node 3: verifier_node [app/agents/verifier.py]
              → Checks math, tenant_id, Self-RAG evaluate_rag_case()
              → [If fails & revision < 2]: routes back to supervisor_node
              → [If fails & revision >= 2]: UNCONDITIONALLY RETURNS PASS (CRITICAL FLAW)
          → Node 4: synthesizer_node [app/agents/synthesizer.py]
              → Formats markdown table from financial_data or tool_calls
              → [Only if neither exists]: call_upstream_llm(prompt)
          → END
      → chat.py receives final_response
      → FAKE TOKEN STREAM: words = final_response.split(" "); for word in words: yield token; sleep(0.002)
      → TokenAccounting.record_transaction()
      → yield done event
```

```
[Path 2: Agent Platform REST & Event Stream]
Client Request: POST /api/v1/agent/tasks
  → Depends(get_current_tenant)
  → AgentRuntimeManager.create_task(goal, tenant_id, user_id)
      → Stores TaskState in memory (_tasks dict)
Client Request: POST /api/v1/agent/tasks/{id}/runs
  → AgentRuntimeManager.create_run()
      → Stores RunState in memory (_runs dict)
  → BackgroundTasks / direct: AgentRuntimeManager.execute_run()
      → AgentRunner.start_run()
          → AgentExecutionLoop.execute() [backend/app/agent/runtime/loop.py]
              → short_term_mem.add_message(AgentMessage(role="user", content=goal))
              → tool_registry.discover(user_roles, user_permissions)
              → planner.create_initial_plan()
              → WHILE current_iteration < max_iterations:
                  → Check cooperative cancellation flag
                  → BoundedPlanner.determine_next_action() [app/agent/planning/planner.py]
                      → Checks max_iterations & elapsed_time
                      → Prompts model via JakeAIBackend.generate() -> call_upstream_llm_detailed()
                      → Extracts JSON action: tool_call | finish | fail
                  → [If finish]: run.status = COMPLETED; checkpoint_manager.save_checkpoint(); emit completed event; return
                  → [If tool_call]:
                      → ApprovalPolicy.requires_approval(tool, tool_name, tool_args)
                      → [If dangerous & approval required]:
                          → approval_manager.create_request()
                          → run.status = PAUSED_APPROVAL; checkpoint_manager.save_checkpoint()
                          → emit approval_required event; return (HALT LOOP)
                      → [If safe or pre-approved]:
                          → tool_registry.execute(tool_name, tool_args, context)
                          → short_term_mem.add_message(role="tool", content=obs)
                          → run.steps.append(StepExecutionRecord)
                          → checkpoint_manager.save_checkpoint()
                          → current_iteration += 1
Client Request: GET /api/v1/agent/tasks/{id}/runs/{run_id}/events
  → AgentRunner.stream_run_events(run_id)
      → Subscribes to asyncio.Queue[AgentRunEvent]
      → Yields SSE frames (step, tool_call, observation, approval_required, completed, failed)
```

```
[Path 3: Coding Workstation Resume Bridge]
Client Request: POST /api/v1/coding/tool-result (or internal /resume)
  → Depends(get_current_tenant)
  → ResumeBridgeManager.resume_checkpoint(call_id, result_payload, tenant_id)
      → Redis lock: SET lock:tool_call:{call_id} 1 EX 300 NX
      → Redis get: checkpoint:{call_id} (or in-memory fallback)
      → Verifies tenant_id ownership
      → Deletes Redis checkpoint key
      → Returns ResumedExecutionResult(status="resumed", tool_acknowledged=True)
      → DEAD END: DOES NOT REHYDRATE ANY GRAPH OR EXECUTION LOOP
```

```
[Path 4: Standalone Workflow Engine]
Not connected to any API route. Only instantiated in tests/test_agent_platform.py:
WorkflowEngine(tool_registry).run(workflow_def, execution)
  → Sequentially iterates WorkflowStepDefinition
  → Dispatches StepType.TOOL_CALL -> tool_registry.execute()
  → Dispatches StepType.MODEL_CALL -> backend.generate()
  → Returns WorkflowExecution record
```

---

# 4. Implemented Capabilities

The following capabilities are verified to exist, execute real code, and enforce expected invariants:

1. **Autonomous ReAct Execution Loop (`backend/app/agent/runtime/loop.py`)**:
   - Manages an iterative problem-solving loop with bounded ceilings (`max_iterations`, default 10).
   - Coordinates planning decisions, tool execution, memory recording, step history, and checkpoint snapshots.
   - Verified by test: `test_agent_execution_loop_normal_finish`.

2. **Real Upstream Model Generation with Context (`backend/app/agent/backends/jakeai.py`)**:
   - `JakeAIBackend` correctly formats conversation history into `ChatMessage` objects, bundles JSON tool schemas, extracts system instructions, and calls `call_upstream_llm_detailed`.
   - Propagates tenant context, token usage, and cost accounting.

3. **Tool Registry with Schema & RBAC Enforcement (`backend/app/agent/tools/registry.py`)**:
   - Maintains registered tool instances.
   - Evaluates caller permissions (`user_roles`, `user_permissions`) via `ToolPolicyEngine.evaluate()`.
   - Validates incoming parameter payloads against JSON Schema definitions (`validate()`).
   - Normalizes execution outcomes into `ToolResult` dataclasses with error capture and millisecond timing.

4. **Human-in-the-Loop Approval Gating (`backend/app/agent/approvals/`)**:
   - Server-side inspection via `ApprovalPolicy.requires_approval()` based on risk classification (`DANGEROUS`), sensitive action names (`terminal_exec`, `git_push`, `shell`), and destructive parameter flags.
   - Pauses execution loop in `RunStatus.PAUSED_APPROVAL`, records pending approval in `ApprovalManager`, and emits `approval_required` event over SSE.
   - Resumes execution via `AgentRunner.resume_after_approval()` once approved, executing the authorized tool and continuing the loop.
   - Rejection handling: injects operator denial reason into short-term memory so the planner can adapt.

5. **Multi-Tenant Scope Enforcement in Agent Platform API (`backend/app/agent/runtime/manager.py`)**:
   - All operations on tasks, runs, and approvals enforce strict `tenant_id` validation.
   - Unauthorized cross-tenant access triggers `PermissionError` (HTTP 403) with proven test coverage.

6. **LangGraph Graph Compilation & Execution (`backend/app/agents/graph.py`)**:
   - Compiles a valid LangGraph `StateGraph(AgentState)` with 5 nodes, conditional edges, and explicit `END` termination.
   - Successfully executes via `agent_graph.astream()` and yields incremental step payloads.

---

# 5. Partially Implemented Capabilities

1. **LangGraph Implementation (`backend/app/agents/graph.py`)**:
   - **Missing**: Compiled without any checkpointer (`workflow.compile()` lacks checkpointer parameter).
   - **Missing**: No LangGraph `interrupt()` calls exist. Graph cannot pause for client tools or human approval.
   - **Missing**: No dynamic node registration or parameterized subgraphs.

2. **Multi-Agent Specialist Reasoning (`backend/app/agents/`)**:
   - **Missing**: Specialist agents do not use LLMs. `financial_specialist_node` extracts regex numbers and computes static formulas. `finnapigo_tool_node` returns hardcoded mock dictionaries.
   - **Missing**: State passing between agents is rigid and fixed to specific keys (`financial_analysis`, `tool_calls`).

3. **Short-Term Memory (`backend/app/agent/memory/short_term.py`)**:
   - **Missing**: Eviction policy is based solely on message count (`max_entries=50`), completely ignorant of token consumption. A single massive message will blow prompt budgets.
   - **Missing**: Not integrated with `backend/app/agents/`.

4. **Cooperative Cancellation (`backend/app/agent/runtime/runner.py`)**:
   - **Missing**: Cancellation is checked only at the start of each iteration in `loop.py`. If an upstream LLM call or tool execution hangs, cancellation has no mechanism to abort the in-flight network request.

5. **Timeout Handling (`backend/app/agent/planning/planner.py`)**:
   - **Missing**: Timeout is evaluated only at the beginning of `determine_next_action()`.
   - **Missing**: `ToolRegistry.execute()` does not wrap tool execution with `asyncio.wait_for()`, allowing unconstrained tool hangs.

6. **Real-Time Token Streaming (`backend/app/api/v1/endpoints/chat.py`)**:
   - **Missing**: Does not stream real LLM completion tokens as generated by upstream providers. Instead, it waits for complete workflow termination and artificially simulates token streaming by splitting the finished string.

---

# 6. Broken Capabilities

### 1. Verifier Critique Bypass Allows Security & Quality Breaches
- **Observed Behavior**: In `backend/app/agents/verifier.py`, line 70, the critique loop is bounded by:
  ```python
  if (math_error or tenant_mismatch or not is_grounded) and revision_count < 2:
      ...
      return {"verification_verdict": "NEEDS_REVISION", ...}

  # 5. Quality gates passed
  return {
      "current_agent": "verifier",
      "workflow_phase": "verification_passed",
      "verification_verdict": "PASS",
      ...
  }
  ```
- **Root Cause**: When `revision_count >= 2`, the condition evaluates to `False`. The function falls through to section `# 5`, unconditionally returning `"PASS"` with message `"All quality gates verified... tenant isolation confirmed"`, **even if `tenant_mismatch` or `math_error` is True**.
- **Consequence**: Critical multi-tenant boundary breaches and hallucinations are marked as passed and returned to the user as verified.

### 2. State Checkpointing & Resume Across Restarts is Non-Existent
- **Observed Behavior**: `CheckpointManager` (`backend/app/agent/state/checkpoint.py`) docstring claims "dual memory + Redis caching".
- **Root Cause**: The implementation only stores data in `self._checkpoints: dict[str, CheckpointRecord] = {}` (in-memory). There is zero Redis connection or serialization logic.
- **Consequence**: Upon process restart, all state is wiped out. There is no restart recovery method in `AgentRuntimeManager`.

### 3. ADR-001 Resume Bridge Rehydration is Dead Code
- **Observed Behavior**: `/api/v1/coding/tool-result` and `/internal/v1/coding/resume` claim to rehydrate LangGraph execution after workstation tool execution.
- **Root Cause**: `ResumeBridgeManager.resume_checkpoint()` in `backend/app/services/resume_bridge.py` verifies Redis locks and deletes the checkpoint key, but **never invokes LangGraph or any agent runner**. It returns a detached `ResumedExecutionResult` DTO. Furthermore, `save_checkpoint` is never called by any active agent workflow.
- **Consequence**: Client workstation tool results submitted to JakeAI are dropped into a black hole; inference never resumes.

### 4. Direct Tool Execution Bypasses in `app.agents` and `coding.py`
- **Observed Behavior**: `W-ORC-03` requires every tool call to route: `Agent -> ToolRegistry -> authorization -> argument validation -> execution -> ToolResult -> Agent`.
- **Root Cause**:
  1. `app/agents/finnapigo_tool.py` executes directly inside the node, bypassing `ToolRegistry` and `ToolPolicyEngine`.
  2. `app/api/v1/endpoints/coding.py` directly handles tool result submissions, bypassing `ToolRegistry`.

---

# 7. Missing Capabilities

The following required orchestration capabilities have **no implementation** in the codebase:

1. **Dynamic Model Selection / Routing in Orchestration**:
   - `W-ORC-01` and `W-COST-05` require intelligent model routing (e.g. routing simple reasoning/classification to light models, and complex synthesis to frontier models).
   - Currently, `BoundedPlanner` uses a fixed `AgentConfig.default_model` (`gemini-1.5-flash`), and `app.agents` uses fixed provider resolution.

2. **Enterprise / Upstream Tool Implementations**:
   - `ToolRegistry` has only 5 built-in tools (`read_file`, `search_symbols`, `calculator`, `system_time`, `terminal_exec` [mock]).
   - There are zero tools registered for upstream FinnApiGo banking APIs, database queries, web scraping, git mutations, or code manipulation.

3. **Persistent Long-Term Memory Integration**:
   - `LongTermMemory` exists as an in-memory dictionary, but is **completely uncalled by `AgentExecutionLoop` and `BoundedPlanner`**.
   - No vector embedding search, semantic recall, or durable storage exists in agent memory.

4. **Bounded Exponential Retry with Jitter**:
   - Neither `BoundedPlanner` nor `AgentExecutionLoop` provides automatic retry with exponential backoff on transient upstream provider errors (HTTP 429, 503).

5. **Subsystem Harmonization**:
   - There is no unified bridge connecting LangGraph graphs with the `ToolRegistry`, `ApprovalManager`, or `AgentRuntimeManager`.

---

# 8. Duplicate / Conflicting Architecture

The codebase exhibits severe architectural schizophrenia across its orchestration components:

```
+---------------------------------------------------------------------------------------------------+
|                                       DUPLICATE ORCHESTRATION AUTHORITIES                         |
+------------------------------------+----------------------------------+---------------------------+
| Dimension                          | backend/app/agents/ (Plural)     | backend/app/agent/ (Singular) |
+------------------------------------+----------------------------------+---------------------------+
| Primary Entrypoint                 | POST /api/v1/chat/stream         | POST /api/v1/agent/tasks  |
| Execution Mechanism                | LangGraph (StateGraph.astream)   | Custom ReAct Loop (Async) |
| Architecture Style                 | Static Topological Workflow      | Autonomous ReAct Loop     |
| Multi-Agent Support                | 5 nodes (mock/regex specialist)  | Single Agent with Planner |
| Planner Implementation             | classify_intent (regex match)    | BoundedPlanner (LLM JSON) |
| State Representation               | AgentState (TypedDict)           | TaskState / RunState (Pydantic) |
| Backend Integration                | call_upstream_llm (direct)       | JakeAIBackend (Adapter)   |
| Tool Execution Authority           | Direct mock in finnapigo_tool    | ToolRegistry + Policies   |
| Approval Gates                     | None                             | ApprovalManager (Working) |
| Checkpoint Storage                 | None (uncheckpointed compile)    | CheckpointManager (Memory)|
| Memory Structure                   | messages: list[str]              | ShortTermMemory (FIFO)    |
| Streaming Event Schema             | status, token, done              | AgentRunEvent (SSE)       |
| Cross-System Imports               | ZERO                             | ZERO                      |
+------------------------------------+----------------------------------+---------------------------+
```

### Additional Duplicate Authorities Discovered:

1. **Third Workflow Engine**: `backend/app/agent/workflows/engine.py` implements a linear step-by-step pipeline runner (`WorkflowEngine`) that operates independently of both LangGraph and `AgentExecutionLoop`. It is only exercised in `test_agent_platform.py` and is exposed to no API routes.
2. **Dual Checkpoint Managers**:
   - `app/agent/state/checkpoint.py`: `CheckpointManager` (in-memory snapshot of `RunState`).
   - `app/services/resume_bridge.py`: `ResumeBridgeManager` (Redis-backed interrupt checkpointing for ADR-001).
   - Neither manager integrates with LangGraph or with each other.
3. **Dual Telemetry Trackers**:
   - `app/agent/telemetry.py`: `AgentTelemetry` tracks agent task/run/tool counts.
   - `app/telemetry/metrics.py`: System-wide Prometheus metrics tracker.
   - Neither system feeds data to the other.

---

# 9. Logic / Functional Risks

1. **Security Risk — Fallthrough Verifier Bypass**:
   In `backend/app/agents/verifier.py:70`, if an agent repeatedly breaches multi-tenant boundaries (accessing another tenant's financial data or documents), after 2 revisions the verifier marks the result as `PASS`. The breach is delivered to the user as authentic verified intelligence.

2. **Process Starvation / Unbounded Tool Hangs**:
   `ToolRegistry.execute()` in `backend/app/agent/tools/registry.py` does not wrap tool execution in `asyncio.wait_for()`. A tool performing network I/O or subprocess execution can hang indefinitely, pinning Python worker tasks and exhausting thread pools.

3. **In-Flight Cancellation Blindspot**:
   `AgentExecutionLoop` only inspects cancellation flags between iterations. If `JakeAIBackend.generate()` or a tool is blocked in an HTTP call, operator cancellation via `/cancel` has zero immediate effect.

4. **Data Loss on Restart for Paused Approvals**:
   Because `ApprovalManager` and `TaskState`/`RunState` are stored purely in Python process heap memory, any deployment, pod restart, or crash while a dangerous operation is in `PAUSED_APPROVAL` will permanently destroy the task state. The run cannot be resumed.

5. **Token Count Desynchronization via Fake Token Streaming**:
   `/api/v1/chat/stream` emits SSE `token` events generated by splitting the final response by whitespace. If the client aborts mid-stream, `TokenAccounting.record_transaction` attempts to estimate consumed completion tokens based on how many words were emitted, leading to drift between actual upstream provider token usage and billed tokens.

---

# 10. Test Coverage Reality

Execution of pytest against the orchestration test suites (`test_multi_agent.py`, `test_agent_platform.py`, `test_resume_bridge.py`) executed **39 tests with 100% pass rate in 12.83 seconds**.

However, inspection of test implementations reveals a significant gap between test passes and actual production behavior:

```
+---------------------------------------------------------------------------------------------------+
|                                      TEST SUITE REALITY AUDIT                                     |
+-----------------------------------+------------+---------------------+----------------------------+
| Component / Behavior              | Test Exists| Test Type           | Reality Behind the Test    |
+-----------------------------------+------------+---------------------+----------------------------+
| Agent Execution Loop              | YES        | Unit (Mocked LLM)   | Uses MockFinishingBackend; no real LLM tested. |
| Tool Approval & Pause/Resume      | YES        | Integration         | Exercises real state transitions & policies. |
| Tool Policy & Discovery           | YES        | Unit (Real Tools)   | Verifies path traversal & permissions on real files.|
| Multi-Agent Graph (Topology)      | YES        | Integration         | Runs LangGraph nodes; verifies hardcoded numbers. |
| Verifier Self-Correction Loop     | YES        | Mocked Node Chaining| MANUALLY calls verifier -> supervisor -> specialist; |
|                                   |            |                     | does NOT test LangGraph loop traversal!   |
| ADR-001 Resume Bridge             | YES        | Mocked Redis        | Tests dict serialization; does NOT test graph rehydration. |
| Cross-Tenant Isolation            | YES        | Negative Unit Tests | Real assertions proving PermissionError on mismatch.|
| Bounded Iteration Limit           | YES        | Unit                | Verifies FAIL action when iteration reaches limit. |
| Real Provider LLM in Loop         | NO         | Untested            | 100% of loop tests mock out backend.generate(). |
| Crash / Restart Recovery          | NO         | Untested            | Zero tests verify state survival across restart. |
| Tool Timeout Enforcement          | NO         | Untested            | Zero tests verify tool hanging or timeout abort. |
+-----------------------------------+------------+---------------------+----------------------------+
```

---

# 11. Four-Core-Capability Alignment

JakeAI's primary mandate is:
> **"JakeAI is developed around four core capabilities: 1. Complex AI Orchestration, 2. Context & Data Management, 3. Cost Optimization, 4. LLMOps & AI Safety. The core objective of Orchestration is the ability to design complex AI processing flows."**

### Current Evaluation Against Mandate:

- **Current State**: JakeAI cannot currently design or execute truly complex AI processing flows end-to-end.
  - The LangGraph implementation (`app.agents`) is a rigid, hardcoded 5-node pipeline with deterministic mock outputs, unable to generalize to new tools or dynamic agent teams.
  - The Agent Platform (`app.agent`) provides the correct primitives (planning, tools, approvals, state), but is confined to a single-agent loop and completely disconnected from the chat interface.
- **Verdict**: The orchestration system currently delivers **foundational ReAct mechanics and topological graph scaffolding**, but falls short of a functioning universal AI engineering worker capable of autonomous multi-agent problem decomposition.

---

# 12. Missing Work (To Reach Functional Completeness)

To make AI Orchestration **functionally complete**, the following non-optimization engineering work is required:

1. **Subsystem Harmonization**:
   - Consolidate `backend/app/agents/` into `backend/app/agent/`.
   - Migrate `/api/v1/chat/stream` to execute through the unified `AgentRuntimeManager`.
   - Deprecate hardcoded regex mock nodes in favor of genuine LLM specialist agent roles.

2. **Durable State Persistence & Checkpointing**:
   - Implement real Redis-backed persistence for `TaskState`, `RunState`, and `CheckpointRecord` in `CheckpointManager`.
   - Implement run restoration on server boot (`resume_run_from_checkpoint`).

3. **LangGraph Production Compilation & Real Interrupts**:
   - Pass an active Redis checkpointer (`AsyncRedisSaver` or similar) to `workflow.compile()`.
   - Implement true LangGraph `interrupt()` calls when waiting for workstation tools or human approval.
   - Connect `ResumeBridgeManager` to rehydrate and resume the interrupted LangGraph graph instance.

4. **Fix Verifier Terminal Failure Invariant**:
   - Repair `backend/app/agents/verifier.py` so that exceeding `max_revisions` results in an explicit `FAILED` state, never an unconditional `PASS`.
   - Abort immediately on `tenant_mismatch` without allowing revision loops.

5. **Tool Execution Hardening**:
   - Wrap `ToolRegistry.execute()` in `asyncio.wait_for()` enforcing tool timeout limits.
   - Register real enterprise tools (FinnApiGo banking client, SQL query, web search).

6. **Connect Long-Term Memory to Planner**:
   - Wire `AgentMemoryManager.recall_relevant()` into `BoundedPlanner.determine_next_action()` prompt construction.
   - Wire `remember_episodic()` into run completion.

7. **Real Token Streaming**:
   - Wire `JakeAIBackend.generate_stream()` directly into `/api/v1/chat/stream` so real provider token deltas are yielded as they arrive.

---

# 13. Recommended Implementation Order

Future WORK implementation tasks should be executed in this strict dependency order:

```
[WORK-01A: Repair Verifier Invariant & Security Isolation]
  Fix critical flaw in verifier.py: terminate with FAILED on exhausted revisions or tenant mismatch.
       │
       ▼
[WORK-01B: Architecture Harmonization & Authority Consolidation]
  Consolidate backend/app/agents/ into backend/app/agent/; establish single state model and single entry point.
       │
       ▼
[WORK-01C: Durable Redis Checkpointing & State Persistence]
  Replace in-memory dicts with Redis persistence in CheckpointManager and ApprovalManager; implement resume.
       │
       ▼
[WORK-01D: Tool Execution Hardening & Real Tool Registration]
  Add per-tool asyncio timeouts to ToolRegistry; eliminate direct execution bypasses; register FinnApiGo tools.
       │
       ▼
[WORK-01E: True LangGraph Rehydration & ADR-001 Bridge]
  Compile LangGraph with checkpointer; implement interrupt() on tool/approval gates; wire resume bridge.
       │
       ▼
[WORK-01F: Multi-Agent Specialist Reasoning & Real Token Streaming]
  Replace regex nodes with LLM specialist personas; stream provider token deltas in real time.
       │
       ▼
[WORK-01G: Long-Term Memory Runtime Integration]
  Connect recall_relevant and remember_episodic into BoundedPlanner and execution lifecycle.
```

---

# 14. Evidence

| Conclusion / Defect | File Path | Code Symbol / Line | Execution Relationship | Test Reference |
| :--- | :--- | :--- | :--- | :--- |
| **Verifier Silently Passes Breaches on Revision >= 2** | `backend/app/agents/verifier.py` | `verifier_node`, lines 70 & 100-104 | Called after specialist/tool; routes to supervisor or synthesizer | `backend/tests/test_multi_agent.py:300` |
| **No Redis Code in CheckpointManager** | `backend/app/agent/state/checkpoint.py` | `CheckpointManager.__init__`, lines 30-31 | Invoked by `AgentExecutionLoop` at every step | `backend/tests/test_agent_platform.py:316` |
| **Resume Bridge Fails to Rehydrate Graph** | `backend/app/services/resume_bridge.py` | `resume_checkpoint`, lines 215-244 | Called by `/api/v1/coding/tool-result` | `backend/tests/test_resume_bridge.py:43` |
| **Save Checkpoint Never Called in Prod** | `backend/app/services/resume_bridge.py` | `save_checkpoint`, line 106 | Only called in tests; 0 callers in `backend/app/` | `backend/tests/test_resume_bridge.py:49` |
| **Fake Token Streaming via Word Split** | `backend/app/api/v1/endpoints/chat.py` | `generate_chat_stream`, lines 301-331 | Main SSE streaming generator | `backend/tests/test_multi_agent.py:206` |
| **Multi-Agent Specialist Uses Hardcoded Math** | `backend/app/agents/financial_specialist.py`| `_compute_deterministic_financials`, lines 45-55 | Invoked by LangGraph supervisor branch | `backend/tests/test_multi_agent.py:40` |
| **Tool Execution Bypasses Registry** | `backend/app/agents/finnapigo_tool.py` | `finnapigo_tool_node`, lines 21-45 | Invoked by LangGraph supervisor branch | `backend/tests/test_multi_agent.py:76` |
| **Long-Term Memory Disconnected from Planner** | `backend/app/agent/memory/manager.py` | `remember_episodic`, line 35 | 0 callers in `loop.py` or `planner.py` | `backend/tests/test_agent_platform.py:369` |
| **Zero Imports Between agent and agents** | `backend/app/agent/` & `app/agents/` | Entire packages | Disconnected modules serving `/agent` and `/chat` | Codebase grep search |
| **Missing Tool Timeout Enforcement** | `backend/app/agent/tools/registry.py` | `execute`, lines 117-128 | Invoked by loop during `TOOL_CALL` dispatch | `backend/tests/test_agent_platform.py:260` |
| **Unchecked Memory Growth in FIFO** | `backend/app/agent/memory/short_term.py`| `add_message`, lines 30-35 | Invoked by loop after each step/observation | `backend/tests/test_agent_platform.py:351` |
