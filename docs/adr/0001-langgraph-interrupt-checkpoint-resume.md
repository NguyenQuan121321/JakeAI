# ADR-001: LangGraph Interrupt Checkpointing and Asynchronous SSE Resume Architecture

## Status
Accepted

## Context
In JakeAI Coding, the agent workflow must perform actions against the user's local workspace (e.g. view files, perform AST-anchored search, apply surgical file patches, and run local unit tests). However, developer workstations sit behind private NAT and local firewall boundaries. 

The naive design assumes LangGraph synchronously blocks Python worker threads waiting for client-side tool execution. In a multi-tenant VPS deployment (2 vCPU / 4GB RAM), blocking server threads on remote client round-trips:
1. Pins Python worker threads and memory allocations indefinitely.
2. Violates the strict `< 300MB` RAM ceiling, leading to worker starvation and OOM crashes.
3. Exposes the system to zombie executions when clients disconnect mid-operation.

## Decision
We decouple LangGraph state execution from physical client-tool execution using LangGraph's `interrupt()` checkpointing primitive combined with an asynchronous SSE/HTTP resume bridge orchestrated by FinnApiGo:

1. **Tool Invocation via `interrupt()`**:
   - When the agent decides to invoke a client tool, LangGraph executes `interrupt()`.
   - Complete graph state is serialized atomically to Redis: `checkpoint:{thread_id}:{checkpoint_id}`.
   - The Python ASGI execution thread terminates and frees process heap memory immediately.
   - An SSE frame is emitted down to the client:
     ```
     event: tool_call
     data: {"call_id": "uuid-v4", "name": "tools/call", "arguments": {"tool": "view_file", ...}}
     ```

2. **Client Execution & NAT-Traversing Resume Bridge**:
   - The local client executes the tool against the local disk in milliseconds.
   - The result is returned via HTTP POST to the edge gateway:
     `POST /api/v1/coding/tool-result` with payload `{"call_id": "uuid-v4", "result": {...}}`.
   - FinnApiGo authenticates the caller, acquires an atomic idempotency lock in Redis (`SET lock:tool_call:{call_id} 1 EX 300 NX`), and forwards the payload internally to JakeAI (`POST /internal/v1/coding/resume`).

3. **State Rehydration**:
   - JakeAI validates `call_id`, fetches the checkpoint from Redis, rehydrates the LangGraph state machine, and resumes inference seamlessly.

4. **Idempotency & Stale Result Protection**:
   - If `call_id` does not match an open interrupt or if the session was aborted, the submission is rejected with `HTTP 409 Conflict`, consuming zero LLM tokens.

## Consequences
- **Positive**: Zero Python thread starvation; 100% idle memory offloaded to Redis; robust NAT traversal without requiring inbound ports on developer machines.
- **Negative**: Requires Redis persistence for active checkpoints and an internal resume endpoint.
