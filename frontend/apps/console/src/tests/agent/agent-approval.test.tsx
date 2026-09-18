import { describe, it, expect, vi, beforeEach } from "vitest";
import { render, screen, fireEvent, waitFor } from "@testing-library/react";
import AgentPage from "@/pages/agent";
import { ApprovalBanner } from "@/components/agent-canvas/approval-banner";
import { agentService } from "@/api/services/agent.service";

// Mock ResizeObserver
if (typeof window !== "undefined" && !window.ResizeObserver) {
  window.ResizeObserver = class ResizeObserver {
    observe() {}
    unobserve() {}
    disconnect() {}
  };
}

describe("Agent Approval Gate Flow", () => {
  beforeEach(() => {
    vi.clearAllMocks();
  });

  it("renders ApprovalBanner with tool name, reason, and calls decideApproval with approved=true", async () => {
    const decideApprovalSpy = vi
      .spyOn(agentService, "decideApproval")
      .mockResolvedValue({
        approval_id: "appr-101",
        task_id: "task-appr-1",
        run_id: "run-appr-1",
        tenant_id: "tenant_jakeai_core",
        tool_name: "mock_dangerous_shell",
        tool_args: { command: "rm -rf /tmp/test" },
        risk_level: "dangerous",
        reason: "Dangerous shell command requires sign-off",
        status: "approved",
        created_at: Date.now(),
      });

    const onDecided = vi.fn();

    render(
      <ApprovalBanner
        taskId="task-appr-1"
        runId="run-appr-1"
        approvalId="appr-101"
        toolName="mock_dangerous_shell"
        reason="Dangerous shell command requires sign-off"
        stepId="step-dangerous"
        toolArgs={{ command: "rm -rf /tmp/test" }}
        onDecided={onDecided}
      />
    );

    expect(screen.getByText("Human Approval Required")).toBeInTheDocument();
    expect(screen.getByText("mock_dangerous_shell")).toBeInTheDocument();
    expect(screen.getByText("Dangerous shell command requires sign-off")).toBeInTheDocument();

    // Click Approve
    const approveBtn = screen.getByTestId("approve-approval-button");
    fireEvent.click(approveBtn);

    await waitFor(() => {
      expect(decideApprovalSpy).toHaveBeenCalledWith(
        "task-appr-1",
        "run-appr-1",
        "appr-101",
        expect.objectContaining({ approved: true })
      );
      expect(onDecided).toHaveBeenCalledWith(true, "");
    });
  });

  it("calls decideApproval with approved=false when operator rejects action", async () => {
    const decideApprovalSpy = vi
      .spyOn(agentService, "decideApproval")
      .mockResolvedValue({
        approval_id: "appr-102",
        task_id: "task-appr-2",
        run_id: "run-appr-2",
        tenant_id: "tenant_jakeai_core",
        tool_name: "mock_dangerous_shell",
        tool_args: {},
        risk_level: "dangerous",
        reason: "Dangerous command",
        status: "rejected",
        created_at: Date.now(),
      });

    const onDecided = vi.fn();

    render(
      <ApprovalBanner
        taskId="task-appr-2"
        runId="run-appr-2"
        approvalId="appr-102"
        toolName="mock_dangerous_shell"
        reason="Dangerous command"
        onDecided={onDecided}
      />
    );

    // Click Reject
    const rejectBtn = screen.getByTestId("reject-approval-button");
    fireEvent.click(rejectBtn);

    await waitFor(() => {
      expect(decideApprovalSpy).toHaveBeenCalledWith(
        "task-appr-2",
        "run-appr-2",
        "appr-102",
        expect.objectContaining({ approved: false })
      );
      expect(onDecided).toHaveBeenCalledWith(false, "");
    });
  });

  it("displays approval banner when SSE stream emits approval_required event", async () => {
    vi.spyOn(agentService, "createTask").mockResolvedValue({
      task_id: "task-hitl",
      tenant_id: "tenant_jakeai_core",
      user_id: "usr_admin",
      goal: "Test dangerous approval gate",
      status: "pending",
      created_at: Date.now(),
      updated_at: Date.now(),
      metadata: {},
    });

    vi.spyOn(agentService, "startRun").mockResolvedValue({
      run_id: "run-hitl",
      task_id: "task-hitl",
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
      async ({ onEvent }) => {
        onEvent?.({
          event_type: "approval_required",
          task_id: "task-hitl",
          run_id: "run-hitl",
          data: {
            approval_id: "appr-gateway-55",
            tool_name: "mock_dangerous_shell",
            reason: "Requires operator sign-off for safety",
            step_id: "step-shell",
          },
        });
      }
    );

    render(<AgentPage />);
    const startBtn = screen.getByTestId("start-run-button");
    fireEvent.click(startBtn);

    await waitFor(() => {
      const banner = screen.getByTestId("approval-required-banner");
      expect(banner).toBeInTheDocument();
      expect(banner).toHaveTextContent("Human Approval Required");
      expect(banner).toHaveTextContent("mock_dangerous_shell");
    });
  });
});
