import { describe, it, expect, vi, beforeEach } from "vitest";
import { render, screen, fireEvent, waitFor } from "@testing-library/react";
import AgentPage from "@/pages/agent";
import { CustomNode } from "@/components/agent-canvas/custom-node";
import { NodePalette } from "@/components/agent-canvas/node-palette";
import { NodeInspector } from "@/components/agent-canvas/node-inspector";
import { EventTimeline } from "@/components/agent-canvas/event-timeline";
import type { CanvasNodeData } from "@/types/agent-graph";

// Mock ResizeObserver if not defined in test environment
if (typeof window !== "undefined" && !window.ResizeObserver) {
  window.ResizeObserver = class ResizeObserver {
    observe() {}
    unobserve() {}
    disconnect() {}
  };
}

import { ReactFlowProvider } from "@xyflow/react";

describe("Agent Orchestration Canvas Component Suite", () => {
  beforeEach(() => {
    vi.clearAllMocks();
  });

  describe("CustomNode Visualization", () => {
    it("renders custom node with name, category, status, and latency", () => {
      const nodeData: CanvasNodeData = {
        id: "test-agent-node",
        label: "Supervisor Agent",
        sublabel: "supervisor",
        category: "agent",
        status: "running",
        description: "Decomposes goals",
        latencyMs: 150,
        executionCount: 2,
      };

      render(
        <ReactFlowProvider>
          <CustomNode
            id="test-agent-node"
            data={nodeData}
            selected={false}
            type="agent"
            zIndex={1}
            isConnectable={true}
            positionAbsoluteX={0}
            positionAbsoluteY={0}
            dragging={false}
            draggable={false}
            selectable={true}
            deletable={false}
          />
        </ReactFlowProvider>
      );

      expect(screen.getByText("Supervisor Agent")).toBeInTheDocument();
      expect(screen.getByText("agent")).toBeInTheDocument();
      expect(screen.getByText("Running")).toBeInTheDocument();

      expect(screen.getByText(/150\s*ms/)).toBeInTheDocument();
      expect(screen.getByText(/x\s*2/)).toBeInTheDocument();

    });

    it("displays error indicator when error is present", () => {
      const nodeData: CanvasNodeData = {
        id: "err-node",
        label: "Failing Step",
        category: "tool",
        status: "failed",
        error: "Upstream timeout (HTTP 504)",
      };

      render(
        <ReactFlowProvider>
          <CustomNode
            id="err-node"
            data={nodeData}
            selected={false}
            type="tool"
            zIndex={1}
            isConnectable={true}
            positionAbsoluteX={0}
            positionAbsoluteY={0}
            dragging={false}
            draggable={false}
            selectable={true}
            deletable={false}
          />
        </ReactFlowProvider>
      );

      expect(screen.getByText("Failed")).toBeInTheDocument();
      expect(screen.getByText("Error")).toBeInTheDocument();
    });

    it("displays verification verdict badge", () => {
      const nodeData: CanvasNodeData = {
        id: "verif-node",
        label: "Canonical Verifier",
        category: "verification",
        status: "completed",
        verdict: "PASS",
      };

      render(
        <ReactFlowProvider>
          <CustomNode
            id="verif-node"
            data={nodeData}
            selected={false}
            type="verification"
            zIndex={1}
            isConnectable={true}
            positionAbsoluteX={0}
            positionAbsoluteY={0}
            dragging={false}
            draggable={false}
            selectable={true}
            deletable={false}
          />
        </ReactFlowProvider>
      );

      expect(screen.getByText("PASS")).toBeInTheDocument();
    });
  });


  describe("NodePalette", () => {
    it("renders palette categories and switches topologies", () => {
      const onSelectTopology = vi.fn();
      render(
        <NodePalette
          activeTopology="supervisor"
          onSelectTopology={onSelectTopology}
        />
      );

      expect(screen.getByText("Node Palette")).toBeInTheDocument();
      expect(screen.getByText("Supervisor Agent")).toBeInTheDocument();
      expect(screen.getByText("Financial Specialist")).toBeInTheDocument();
      expect(screen.getByText("Precision Calculator")).toBeInTheDocument();

      // Click RAG topology button
      const ragButton = screen.getByRole("button", { name: "RAG" });
      fireEvent.click(ragButton);
      expect(onSelectTopology).toHaveBeenCalledWith("rag");
    });

    it("filters nodes by search query", () => {
      render(
        <NodePalette
          activeTopology="supervisor"
          onSelectTopology={vi.fn()}
        />
      );

      const searchInput = screen.getByPlaceholderText("Filter nodes or tools...");
      fireEvent.change(searchInput, { target: { value: "Calculator" } });

      expect(screen.getByText("Precision Calculator")).toBeInTheDocument();
      expect(screen.queryByText("Financial Specialist")).not.toBeInTheDocument();
    });
  });

  describe("NodeInspector", () => {
    it("renders empty state when no node is selected", () => {
      render(<NodeInspector nodeData={null} onClose={vi.fn()} />);
      expect(screen.getByText("Select a node in the canvas")).toBeInTheDocument();
    });

    it("renders contract-approved fields and safe parameters", () => {
      const onClose = vi.fn();
      const nodeData: CanvasNodeData = {
        id: "insp-1",
        label: "Banking Balance Tool",
        sublabel: "get_account_balance",
        category: "tool",
        status: "completed",
        latencyMs: 85,
        inputs: { account_id: "acc_demo_44" },
        outputs: { balance: 1250000, currency: "USD" },
        citations: [{ source: "FinnApiGo Core Ledger", confidence: 0.99 }],
      };

      render(<NodeInspector nodeData={nodeData} onClose={onClose} />);

      expect(screen.getByText("Banking Balance Tool")).toBeInTheDocument();
      expect(screen.getByText("85ms")).toBeInTheDocument();
      expect(screen.getByText("FinnApiGo Core Ledger")).toBeInTheDocument();
      expect(screen.getByText("Contract Inputs")).toBeInTheDocument();
      expect(screen.getByText("Execution Output")).toBeInTheDocument();

      // Close button
      const closeBtn = screen.getByLabelText("Close Inspector");
      fireEvent.click(closeBtn);
      expect(onClose).toHaveBeenCalled();
    });
  });

  describe("EventTimeline", () => {
    it("renders timeline events and handles expansion toggle", () => {
      const onToggle = vi.fn();
      const events = [
        {
          id: "ev-1",
          eventType: "step_started",
          timestamp: Date.now(),
          taskId: "task-1",
          runId: "run-1",
          title: "Step Started",
          description: "Evaluating balance",
          status: "running" as const,
        },
      ];

      render(
        <EventTimeline
          events={events}
          isExpanded={true}
          onToggleExpand={onToggle}
        />
      );

      expect(screen.getByText("Execution Trace & Event Timeline")).toBeInTheDocument();
      expect(screen.getByText("Step Started")).toBeInTheDocument();
      expect(screen.getByText("Evaluating balance")).toBeInTheDocument();

      const collapseBtn = screen.getByRole("button", { name: "Collapse timeline" });
      fireEvent.click(collapseBtn);
      expect(onToggle).toHaveBeenCalled();
    });
  });

  describe("AgentPage Integration & Mode Toggle", () => {
    it("renders page header and switches between Canvas and Simple views", async () => {
      render(<AgentPage />);

      expect(screen.getByText("Agent Orchestration Canvas")).toBeInTheDocument();
      expect(screen.getByTestId("canvas-goal-input")).toBeInTheDocument();
      expect(screen.getByTestId("start-run-button")).toBeInTheDocument();

      // Canvas view is active by default
      expect(screen.getByTestId("react-flow-canvas")).toBeInTheDocument();

      // Switch to Simple view
      const simpleBtn = screen.getByTestId("toggle-simple-view");
      fireEvent.click(simpleBtn);

      await waitFor(() => {
        expect(screen.getByTestId("simple-execution-view")).toBeInTheDocument();
        expect(screen.queryByTestId("react-flow-canvas")).not.toBeInTheDocument();
      });

      // Switch back to Canvas view
      const canvasBtn = screen.getByTestId("toggle-canvas-view");
      fireEvent.click(canvasBtn);

      await waitFor(() => {
        expect(screen.getByTestId("react-flow-canvas")).toBeInTheDocument();
      });
    });
  });
});
