# JakeAI — Static Code Analysis: Agent Subsystem & Context Bloat Audit

**Audit Date:** September 2026  
**Status:** Audit Completed  
**Domain:** Agent Execution Loop, Memory Systems, Tool Orchestration, Context Compaction, and Tool Output Budgeting  

---

## 1. Architectural Baseline

The JakeAI Agent Platform (`backend/app/agent/`) was introduced in Phase 08 to support multi-step autonomous planning, tool execution, and server-side human approval gates. Its key components include:
- **`AgentExecutionLoop` (`runtime/loop.py`):** Iterative loop managing lifecycle events, cancellation, and execution steps.
- **`BoundedPlanner` (`planning/planner.py`):** Hard iteration ceilings (`max_iterations = 10`) and timeout guards (`timeout_seconds = 60.0`).
- **`ShortTermMemory` (`memory/short_term.py`):** In-run memory scratchpad bounded by FIFO entry count (`max_entries = 50`).
- **`ApprovalManager` (`approvals/manager.py`):** Intercepts high-risk operations (e.g., shell commands, write operations) for human review.
- **`ToolRegistry` (`tools/registry.py`):** Role-based access control and tool execution.

---

## 2. Agent Subsystem Findings

### Finding AGT-01: Unbounded Tool Output Ingestion into Agent Memory
- **Severity:** `HIGH`
- **Confidence:** `HIGH`
- **File / Symbol / Location:** `backend/app/agent/runtime/loop.py` (Lines 250–263)
- **Current Behavior:**  
  ```python
  obs_text = (
      str(tool_res.output)
      if tool_res.success
      else f"Tool execution error: {tool_res.error}"
  )
  short_term_mem.add_message(
      AgentMessage(
          role="tool",
          name=tool_name,
          content=obs_text,
      )
  )
  ```
- **Problem:**  
  Tool execution results are converted to plain string via `str(tool_res.output)` and added directly to `short_term_mem` without any size verification, token budgeting, field filtering, or truncation.
- **Evidence:**  
  If an agent invokes `file_read` on a 500KB source file, or calls a search tool returning 200 JSON records, the entire 50,000-token text dump is injected into short-term memory. On subsequent iterations, the model must re-read this massive raw payload on every turn.
- **Impact:**  
  1. Catastrophic context bloat: A single tool call can exhaust the model's context window (e.g. 128k tokens) or trigger massive token billing.
  2. Attention degradation: Excessive raw tool output degrades the model's ability to locate critical goal requirements in subsequent steps.
- **Recommended Solution:**  
  Implement a strict **Tool Output Budgeting Policy**:
  1. Set a default per-tool output budget (e.g. 2,000 tokens / ~8KB).
  2. If tool output exceeds budget, automatically apply structured projection (extract only requested fields), head/tail truncation with continuation tokens, or write the full output to an artifact store and return an excerpt with a reference ID.
- **Complexity:** Medium.
- **Risk:** Low.
- **Expected Benefit:** 70–90% reduction in agent context bloat on data-intensive tool runs.

---

### Finding AGT-02: Absence of Deferred Tool Discovery (Static Schema Ingestion)
- **Severity:** `HIGH`
- **Confidence:** `HIGH`
- **File / Symbol / Location:** `backend/app/agent/planning/planner.py` (Lines 100–108)
- **Current Behavior:**  
  ```python
  tool_schemas = [
      {
          "name": t.name,
          "description": t.description,
          "parameters": t.input_schema,
          "risk_level": t.risk_level.value,
      }
      for t in available_tools
  ]
  ```
- **Problem:**  
  All tools permitted by user permissions are serialized into full JSON parameter schemas and injected into the model prompt on **every single step of the agent run**.
- **Evidence:**  
  If the platform grows to 50 enterprise tools (e.g., Jira, Slack, GitHub, SQL, ERP, AWS, Kubernetes), transmitting 50 full JSON schemas consumes 5,000–15,000 tokens on every step. For a 10-step agent run, 50,000–150,000 tokens are spent merely repeating tool definitions.
- **Impact:** Unnecessary provider costs, high prompt token consumption, and reduced effective context space for actual task reasoning.
- **Recommended Solution:**  
  Adopt **Deferred Tool Discovery**:
  1. Pass only a lightweight index (tool name + 1-sentence description, ~15 tokens per tool).
  2. When the planner decides to invoke a tool category, emit a `discover_tools` action that loads full parameter schemas only for the relevant tools needed for that task.
- **Complexity:** Medium.
- **Risk:** Low to Medium.
- **Expected Benefit:** 60–80% reduction in tool definition token overhead across multi-step runs.

---

### Finding AGT-03: Primitive FIFO Memory Eviction without Structured Compaction
- **Severity:** `MEDIUM`
- **Confidence:** `HIGH`
- **File / Symbol / Location:** `backend/app/agent/memory/short_term.py` (Lines 28–36)
- **Current Behavior:**  
  ```python
  def add_message(self, message: AgentMessage) -> None:
      self._messages.append(message)
      if len(self._messages) > self.max_entries:
          if self._messages[0].role == "system" and len(self._messages) > 2:
              self._messages.pop(1)
          else:
              self._messages.pop(0)
  ```
- **Problem:**  
  Short-term memory manages context purely by message count (`len > 50`), using naive FIFO eviction:
  1. A single message with 50,000 tokens counts the same as a message with 5 tokens.
  2. When capacity is exceeded, early user turns and crucial instructions (such as constraints given in turn 2) are dropped unceremoniously, causing "agent amnesia" and goal deviation.
- **Impact:** Agent loops lose sight of constraints or repeat failed actions on long-running tasks ($>10$ turns).
- **Recommended Solution:**  
  Implement **Structured Context Compaction**:
  - Track memory size in actual tokens rather than message count.
  - When token threshold is reached, trigger an automated compaction step that summarizes intermediate conversation history, extracts verified facts and state transitions, and discards stale tool observation logs.
- **Complexity:** Medium.
- **Risk:** Medium.
- **Expected Benefit:** Bounded memory footprint with persistent retention of requirements and decisions.

---

### Finding AGT-04: Lack of Programmatic Tool Calling
- **Severity:** `MEDIUM`
- **Confidence:** `MEDIUM`
- **File / Symbol / Location:** `backend/app/agent/runtime/loop.py` (Lines 175–245)
- **Current Behavior:**  
  Every tool execution requires a complete model round-trip. If an agent needs to list 10 files and inspect 3 of them, it takes 4 complete LLM inference round trips.
- **Problem:**  
  Deterministic tasks like filtering file names, calculating sums, or sorting search results are conducted across multiple sequential model round trips rather than executing code directly in an execution sandbox.
- **Impact:** 3x–5x higher latency and token usage for sequential multi-step data tasks.
- **Recommended Solution:**  
  Expose Python tool stubs and allow the agent to emit executable Python scripts within `SandboxManager` to chain and aggregate tools in a single execution step.
- **Complexity:** High.
- **Risk:** Medium (requires sandbox isolation security).
- **Expected Benefit:** 50% reduction in agent steps and latency on complex workflows.
