import { describe, it, expect, vi, beforeEach } from "vitest";
import { render, screen, fireEvent, waitFor } from "@testing-library/react";
import AgentPage from "@/pages/agent";
import { agentService } from "@/api/services/agent.service";
import type { BackendRunEvent } from "@/lib/agent-graph-adapter";

// Mock ResizeObserver for happy-dom
if (typeof window !== "undefined" && !window.ResizeObserver) {
  window.ResizeObserver = class ResizeObserver {
    observe() {}
    unobserve() {}
    disconnect() {}
  };
}

describe("Agent Execution SSE Stream Integration", () => {
  beforeEach(() => {
    vi.clearAllMocks();
  });

  it("submits task, starts run, and streams real-time events into canvas & timeline", async () => {
    // Spy on service methods
    const createTaskSpy = vi.spyOn(agentService, "createTask").mockResolvedValue({
      task_id: "task-stream-01",
      tenant_id: "tenant_jakeai_core",
      user_id: "usr_admin",
      goal: "Calculate EBITDA and analyze liquidity",
      status: "pending",
      created_at: Date.now(),
      updated_at: Date.now(),
      metadata: {},
    });

    const startRunSpy = vi.spyOn(agentService, "startRun").mockResolvedValue({
      run_id: "run-stream-01",
      task_id: "task-stream-01",
      tenant_id: "tenant_jakeai_core",
      user_id: "usr_admin",
      status: "running",
      created_at: Date.now(),
      current_iteration: 0,
      current_step: 0,
      max_iterations: 10,
      steps: [],
      roles: [],
      permissions: [],
      messages: [],
      context: {},
      tool_calls: [],
      tool_results: [],
      revision_count: 0,
      tokens_consumed: 0,
      cost_usd: 0,
      metadata: {},
    });

    // Mock stream with deterministic sequence of events
    const streamSpy = vi.spyOn(agentService, "streamRunEvents").mockImplementation(
      async ({ onEvent, onComplete }) => {
        const events: BackendRunEvent[] = [
          {
            event_type: "run_started",
            task_id: "task-stream-01",
            run_id: "run-stream-01",
            data: { goal: "Calculate EBITDA and analyze liquidity", max_iterations: 10 },
          },
          {
            event_type: "step_started",
            task_id: "task-stream-01",
            run_id: "run-stream-01",
            data: { step_id: "node-supervisor", description: "Decompose goals" },
          },
          {
            event_type: "tool_call",
            task_id: "task-stream-01",
            run_id: "run-stream-01",
            data: { tool_name: "get_account_balance", arguments: { account_id: "acc_demo" } },
          },
          {
            event_type: "observation",
            task_id: "task-stream-01",
            run_id: "run-stream-01",
            data: { tool_name: "get_account_balance", success: true, output: { balance: 4500000 }, duration_ms: 50 },
          },
          {
            event_type: "verification_started",
            task_id: "task-stream-01",
            run_id: "run-stream-01",
            data: { tenant_id: "tenant_jakeai_core" },
          },
          {
            event_type: "verification_result",
            task_id: "task-stream-01",
            run_id: "run-stream-01",
            data: { verdict: "PASS", reason: "Mathematical invariants hold", groundedness_score: 1.0 },
          },
          {
            event_type: "completed",
            task_id: "task-stream-01",
            run_id: "run-stream-01",
            data: { output: "EBITDA margin verified at 24.5%", elapsed_ms: 180 },
          },
        ];

        for (const ev of events) {
          onEvent?.(ev);
        }
        onComplete?.();
      }
    );

    render(<AgentPage />);

    // Click Start Run
    const startBtn = screen.getByTestId("start-run-button");
    fireEvent.click(startBtn);

    await waitFor(() => {
      expect(createTaskSpy).toHaveBeenCalledWith(
        expect.objectContaining({ goal: expect.stringContaining("EBITDA") })
      );
      expect(startRunSpy).toHaveBeenCalledWith("task-stream-01", expect.any(Object));
      expect(streamSpy).toHaveBeenCalledWith(
        expect.objectContaining({ taskId: "task-stream-01", runId: "run-stream-01" })
      );
    });

    // Verify events were appended into state
    await waitFor(() => {
      expect(screen.getByText("Run: completed")).toBeInTheDocument();
    });
  });

  it("handles execution failure event and displays error gracefully", async () => {
    vi.spyOn(agentService, "createTask").mockResolvedValue({
      task_id: "task-err-01",
      tenant_id: "tenant_jakeai_core",
      user_id: "usr_admin",
      goal: "Simulate failure",
      status: "pending",
      created_at: Date.now(),
      updated_at: Date.now(),
      metadata: {},
    });

    vi.spyOn(agentService, "startRun").mockResolvedValue({
      run_id: "run-err-01",
      task_id: "task-err-01",
      tenant_id: "tenant_jakeai_core",
      user_id: "usr_admin",
      status: "running",
      created_at: Date.now(),
      current_iteration: 0,
      current_step: 0,
      max_iterations: 10,
      steps: [],
      roles: [],
      permissions: [],
      messages: [],
      context: {},
      tool_calls: [],
      tool_results: [],
      revision_count: 0,
      tokens_consumed: 0,
      cost_usd: 0,
      metadata: {},
    });

    vi.spyOn(agentService, "streamRunEvents").mockImplementation(
      async ({ onEvent, onComplete }) => {
        onEvent?.({
          event_type: "failed",
          task_id: "task-err-01",
          run_id: "run-err-01",
          data: { error: "Exceeded maximum iterations limit (10)" },
        });
        onComplete?.();
      }
    );

    render(<AgentPage />);
    const startBtn = screen.getByTestId("start-run-button");
    fireEvent.click(startBtn);

    await waitFor(() => {
      expect(screen.getByText("Run: failed")).toBeInTheDocument();
    });
  });

  it("handles disconnected stream error without crashing", async () => {
    vi.spyOn(agentService, "createTask").mockResolvedValue({
      task_id: "task-disc-01",
      tenant_id: "tenant_jakeai_core",
      user_id: "usr_admin",
      goal: "Disconnect test",
      status: "pending",
      created_at: Date.now(),
      updated_at: Date.now(),
      metadata: {},
    });

    vi.spyOn(agentService, "startRun").mockResolvedValue({
      run_id: "run-disc-01",
      task_id: "task-disc-01",
      tenant_id: "tenant_jakeai_core",
      user_id: "usr_admin",
      status: "running",
      created_at: Date.now(),
      current_iteration: 0,
      current_step: 0,
      max_iterations: 10,
      steps: [],
      roles: [],
      permissions: [],
      messages: [],
      context: {},
      tool_calls: [],
      tool_results: [],
      revision_count: 0,
      tokens_consumed: 0,
      cost_usd: 0,
      metadata: {},
    });

    vi.spyOn(agentService, "streamRunEvents").mockImplementation(
      async ({ onError }) => {
        onError?.(new Error("Network connection lost (HTTP 503)"));
      }
    );

    render(<AgentPage />);
    const startBtn = screen.getByTestId("start-run-button");
    fireEvent.click(startBtn);

    await waitFor(() => {
      expect(screen.getByText("Network connection lost (HTTP 503)")).toBeInTheDocument();
    });
  });
});
