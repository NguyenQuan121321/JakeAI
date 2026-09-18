import { describe, it, expect, vi, beforeEach } from "vitest";
import { render, screen, fireEvent, waitFor } from "@testing-library/react";
import AgentPage from "@/pages/agent";
import { agentService } from "@/api/services/agent.service";

// Mock ResizeObserver
if (typeof window !== "undefined" && !window.ResizeObserver) {
  window.ResizeObserver = class ResizeObserver {
    observe() {}
    unobserve() {}
    disconnect() {}
  };
}

describe("Agent Cooperative Cancellation Flow", () => {
  beforeEach(() => {
    vi.clearAllMocks();
  });

  it("has Cancel button disabled initially when no run has started", () => {
    render(<AgentPage />);
    const cancelBtn = screen.getByTestId("cancel-run-button");
    expect(cancelBtn).toBeDisabled();
  });

  it("calls agentService.cancelRun and marks state cancelled when Cancel is clicked", async () => {
    vi.spyOn(agentService, "createTask").mockResolvedValue({
      task_id: "task-cancel-100",
      tenant_id: "tenant_jakeai_core",
      user_id: "usr_admin",
      goal: "Test task cancellation",
      status: "pending",
      created_at: Date.now(),
      updated_at: Date.now(),
      metadata: {},
    });

    vi.spyOn(agentService, "startRun").mockResolvedValue({
      run_id: "run-cancel-200",
      task_id: "task-cancel-100",
      tenant_id: "tenant_jakeai_core",
      user_id: "usr_admin",
      status: "running",
      created_at: Date.now(),
      current_iteration: 1,
      current_step: 1,
      max_iterations: 10,
      steps: [],
      roles: [],
      permissions: [],
      messages: [],
      context: {},
      tool_calls: [],
      tool_results: [],
      revision_count: 0,
      tokens_consumed: 120,
      cost_usd: 0.002,
      metadata: {},
    });

    const cancelSpy = vi.spyOn(agentService, "cancelRun").mockResolvedValue({
      run_id: "run-cancel-200",
      task_id: "task-cancel-100",
      tenant_id: "tenant_jakeai_core",
      user_id: "usr_admin",
      status: "cancelled",
      created_at: Date.now(),
      current_iteration: 1,
      current_step: 1,
      max_iterations: 10,
      steps: [],
      roles: [],
      permissions: [],
      messages: [],
      context: {},
      tool_calls: [],
      tool_results: [],
      revision_count: 0,
      tokens_consumed: 120,
      cost_usd: 0.002,
      metadata: {},
    });

    // Mock stream that stays open
    let abortSignalObserved: AbortSignal | undefined;
    vi.spyOn(agentService, "streamRunEvents").mockImplementation(
      async ({ signal, onEvent }) => {
        abortSignalObserved = signal;
        onEvent?.({
          event_type: "step_started",
          task_id: "task-cancel-100",
          run_id: "run-cancel-200",
          data: { step_id: "node-supervisor" },
        });
      }
    );

    render(<AgentPage />);

    // Start run
    const startBtn = screen.getByTestId("start-run-button");
    fireEvent.click(startBtn);

    // Cancel button should now become enabled
    const cancelBtn = screen.getByTestId("cancel-run-button");
    await waitFor(() => {
      expect(cancelBtn).not.toBeDisabled();
    });

    // Click Cancel
    fireEvent.click(cancelBtn);

    await waitFor(() => {
      expect(cancelSpy).toHaveBeenCalledWith("task-cancel-100", "run-cancel-200");
      expect(screen.getByText("Run: cancelled")).toBeInTheDocument();
      expect(cancelBtn).toBeDisabled();
    });

    // Verify abort signal was triggered
    expect(abortSignalObserved?.aborted).toBe(true);
  });

  it("disables Cancel button when run completes naturally", async () => {
    vi.spyOn(agentService, "createTask").mockResolvedValue({
      task_id: "task-cancel-300",
      tenant_id: "tenant_jakeai_core",
      user_id: "usr_admin",
      goal: "Test task naturally completes",
      status: "pending",
      created_at: Date.now(),
      updated_at: Date.now(),
      metadata: {},
    });

    vi.spyOn(agentService, "startRun").mockResolvedValue({
      run_id: "run-cancel-300",
      task_id: "task-cancel-300",
      tenant_id: "tenant_jakeai_core",
      user_id: "usr_admin",
      status: "running",
      created_at: Date.now(),
      current_iteration: 1,
      current_step: 1,
      max_iterations: 10,
      steps: [],
      roles: [],
      permissions: [],
      messages: [],
      context: {},
      tool_calls: [],
      tool_results: [],
      revision_count: 0,
      tokens_consumed: 50,
      cost_usd: 0.001,
      metadata: {},
    });

    vi.spyOn(agentService, "streamRunEvents").mockImplementation(
      async ({ onEvent }) => {
        onEvent?.({
          event_type: "completed",
          task_id: "task-cancel-300",
          run_id: "run-cancel-300",
          data: { output: "Finished task successfully" },
        });
      }
    );

    render(<AgentPage />);
    const startBtn = screen.getByTestId("start-run-button");
    fireEvent.click(startBtn);

    await waitFor(() => {
      expect(screen.getByText("Run: completed")).toBeInTheDocument();
      expect(screen.getByTestId("cancel-run-button")).toBeDisabled();
    });
  });
});
