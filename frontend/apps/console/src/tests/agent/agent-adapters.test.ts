import { describe, it, expect } from "vitest";
import {
  getCanonicalTopology,
  mapBackendStatusToCanvas,
  planToGraph,
  applyEventToGraph,
  createTimelineEvent,
  type ExecutionPlanDTO,
  type BackendRunEvent,
} from "@/lib/agent-graph-adapter";
import type { OrchestrationGraphState } from "@/types/agent-graph";

describe("Agent Graph Adapters", () => {
  it("generates canonical topologies for supervisor, rag, and react", () => {
    const supervisorTopo = getCanonicalTopology("supervisor");
    expect(supervisorTopo.nodes.length).toBeGreaterThanOrEqual(8);
    expect(supervisorTopo.edges.length).toBeGreaterThanOrEqual(7);

    const categories = supervisorTopo.nodes.map((n) => n.type);
    expect(categories).toContain("task");
    expect(categories).toContain("agent");
    expect(categories).toContain("tool");
    expect(categories).toContain("verification");
    expect(categories).toContain("approval");
    expect(categories).toContain("result");

    const ragTopo = getCanonicalTopology("rag");
    expect(ragTopo.nodes.some((n) => n.type === "rag")).toBe(true);

    const reactTopo = getCanonicalTopology("react");
    expect(reactTopo.nodes.some((n) => n.type === "tool")).toBe(true);
  });

  it("maps backend statuses to canvas statuses correctly according to R-LOGIC-01", () => {
    expect(mapBackendStatusToCanvas("completed")).toBe("completed");
    expect(mapBackendStatusToCanvas("verification_passed")).toBe("completed");
    expect(mapBackendStatusToCanvas("running")).toBe("running");
    expect(mapBackendStatusToCanvas("executing")).toBe("running");
    expect(mapBackendStatusToCanvas("waiting_approval")).toBe("waiting_approval");
    expect(mapBackendStatusToCanvas("paused_approval")).toBe("waiting_approval");
    expect(mapBackendStatusToCanvas("failed")).toBe("failed");
    expect(mapBackendStatusToCanvas("rejected")).toBe("failed");
    expect(mapBackendStatusToCanvas("timeout")).toBe("failed");
    expect(mapBackendStatusToCanvas("cancelled")).toBe("cancelled");
    expect(mapBackendStatusToCanvas("pending")).toBe("queued");
    expect(mapBackendStatusToCanvas("ready")).toBe("queued");
    expect(mapBackendStatusToCanvas("planning")).toBe("queued");
    expect(mapBackendStatusToCanvas("unknown_status")).toBe("idle");
  });

  it("converts an ExecutionPlanDTO into nodes and dependency edges", () => {
    const plan: ExecutionPlanDTO = {
      plan_id: "plan-123",
      goal: "Analyze corporate balance sheet",
      planner_mode: "structured",
      steps: [
        {
          step_id: "step-1",
          description: "Retrieve account statements",
          dependencies: [],
          assigned_agent: "finnapigo_specialist",
          tool_name: "get_account_balance",
          status: "completed",
        },
        {
          step_id: "step-2",
          description: "Calculate liquidity ratios",
          dependencies: ["step-1"],
          assigned_agent: "financial_specialist",
          status: "running",
        },
        {
          step_id: "step-3",
          description: "Verify mathematical invariants",
          dependencies: ["step-2"],
          assigned_agent: "verifier",
          status: "pending",
        },
      ],
    };

    const graph = planToGraph(plan, null);
    expect(graph.nodes.length).toBe(5); // root task + 3 steps + terminal result
    expect(graph.edges.length).toBe(4); // task->step1, step1->step2, step2->step3, step3->result

    const step1Node = graph.nodes.find((n) => n.id === "step-1");
    expect(step1Node).toBeDefined();
    expect(step1Node?.type).toBe("tool");
    expect(step1Node?.data.status).toBe("completed");

    const step2Node = graph.nodes.find((n) => n.id === "step-2");
    expect(step2Node?.type).toBe("agent");
    expect(step2Node?.data.status).toBe("running");

    const step3Node = graph.nodes.find((n) => n.id === "step-3");
    expect(step3Node?.type).toBe("verification");
    expect(step3Node?.data.status).toBe("queued");
  });

  it("applies SSE events to graph deterministically", () => {
    const initial = getCanonicalTopology("supervisor");
    const graphState: OrchestrationGraphState = {
      nodes: initial.nodes,
      edges: initial.edges,
      activeNodeId: null,
      selectedNodeId: null,
    };

    // 1. Task created
    const ev1: BackendRunEvent = {
      event_type: "task_created",
      task_id: "task-1",
      run_id: "run-1",
      data: { goal: "Audit ledger" },
    };
    const s1 = applyEventToGraph(ev1, graphState);
    const taskNode = s1.nodes.find((n) => n.id === "node-task");
    expect(taskNode?.data.status).toBe("running");

    // 2. Step started
    const ev2: BackendRunEvent = {
      event_type: "step_started",
      task_id: "task-1",
      run_id: "run-1",
      data: { step_id: "node-supervisor" },
    };
    const s2 = applyEventToGraph(ev2, s1);
    const supNode = s2.nodes.find((n) => n.id === "node-supervisor");
    expect(supNode?.data.status).toBe("running");
    expect(s2.activeNodeId).toBe("node-supervisor");

    // 3. Tool call
    const ev3: BackendRunEvent = {
      event_type: "tool_call",
      task_id: "task-1",
      run_id: "run-1",
      data: { tool_name: "get_account_balance", arguments: { account_id: "acc-1" } },
    };
    const s3 = applyEventToGraph(ev3, s2);
    const toolNode = s3.nodes.find((n) => n.id === "node-banking-tool");
    expect(toolNode?.data.status).toBe("running");
    expect(toolNode?.data.inputs).toEqual({ account_id: "acc-1" });

    // 4. Observation
    const ev4: BackendRunEvent = {
      event_type: "observation",
      task_id: "task-1",
      run_id: "run-1",
      data: {
        tool_name: "get_account_balance",
        success: true,
        output: { balance: 50000 },
        duration_ms: 45,
      },
    };
    const s4 = applyEventToGraph(ev4, s3);
    const toolNodeDone = s4.nodes.find((n) => n.id === "node-banking-tool");
    expect(toolNodeDone?.data.status).toBe("completed");
    expect(toolNodeDone?.data.outputs).toEqual({ balance: 50000 });
    expect(toolNodeDone?.data.latencyMs).toBe(45);

    // 5. Approval required
    const ev5: BackendRunEvent = {
      event_type: "approval_required",
      task_id: "task-1",
      run_id: "run-1",
      data: {
        approval_id: "appr-99",
        tool_name: "mock_dangerous_shell",
        reason: "Dangerous shell command requires sign-off",
      },
    };
    const s5 = applyEventToGraph(ev5, s4);
    const apprNode = s5.nodes.find((n) => n.id === "node-approval-gate");
    expect(apprNode?.data.status).toBe("waiting_approval");
    expect(apprNode?.data.approvalId).toBe("appr-99");

    // 6. Verification result
    const ev6: BackendRunEvent = {
      event_type: "verification_result",
      task_id: "task-1",
      run_id: "run-1",
      data: { verdict: "PASS", reason: "Tenant boundary valid", groundedness_score: 1.0 },
    };
    const s6 = applyEventToGraph(ev6, s5);
    const verifNode = s6.nodes.find((n) => n.id === "node-verifier");
    expect(verifNode?.data.status).toBe("completed");
    expect(verifNode?.data.verdict).toBe("PASS");

    // 7. Completed terminal
    const ev7: BackendRunEvent = {
      event_type: "completed",
      task_id: "task-1",
      run_id: "run-1",
      data: { output: "Finished successfully" },
    };
    const s7 = applyEventToGraph(ev7, s6);
    const resNode = s7.nodes.find((n) => n.id === "node-result");
    expect(resNode?.data.status).toBe("completed");
    expect(resNode?.data.outputs).toBe("Finished successfully");
    expect(s7.activeNodeId).toBeNull();
  });

  it("creates structured TimelineEvents from SSE frames", () => {
    const ev: BackendRunEvent = {
      event_type: "tool_call",
      task_id: "t-1",
      run_id: "r-1",
      timestamp: 1726600000,
      data: { tool_name: "calculator", thought: "Compute EBITDA" },
    };
    const timeline = createTimelineEvent(ev);
    expect(timeline.eventType).toBe("tool_call");
    expect(timeline.title).toBe("Tool Invocation: calculator");
    expect(timeline.status).toBe("running");
  });
});
