import type {
  CanvasNode,
  CanvasEdge,
  CanvasNodeStatus,
  CanvasNodeType,
  OrchestrationGraphState,
  TimelineEvent,
} from "@/types/agent-graph";
import type { RunState } from "@/api/types/domain";

export interface PlanStepDTO {
  step_id: string;
  description: string;
  objective?: string;
  dependencies?: string[];
  required_capabilities?: string[];
  candidate_agents?: string[];
  required_tools?: string[];
  status?: string;
  assigned_agent?: string | null;
  selected_model?: string | null;
  selected_provider?: string | null;
  pending_approval_id?: string | null;
  observation?: string | null;
  error?: string | null;
  tool_name?: string | null;
  tool_args?: Record<string, unknown>;
  result?: {
    output?: unknown;
    error?: string | null;
    execution_time_ms?: number;
    tokens_consumed?: number;
    tool_calls?: Array<Record<string, unknown>>;
  } | null;
}

export interface ExecutionPlanDTO {
  plan_id?: string;
  task_id?: string;
  goal?: string;
  planner_mode?: string;
  steps: PlanStepDTO[];
}

export interface BackendRunEvent {
  event_type: string;
  task_id: string;
  run_id: string;
  timestamp?: number;
  data?: Record<string, unknown>;
}

/**
 * Standard Canonical Topologies justified by JakeAI backend orchestration:
 * - supervisor: LangGraph supervisor graph (Supervisor -> Specialists -> Verifier -> Synthesizer)
 * - rag: RAG Retrieval & Financial Analysis topology
 * - react: ReAct tool execution with approval gate
 */
export function getCanonicalTopology(
  type: "supervisor" | "rag" | "react" = "supervisor"
): { nodes: CanvasNode[]; edges: CanvasEdge[] } {
  if (type === "supervisor") {
    const nodes: CanvasNode[] = [
      {
        id: "node-task",
        type: "task",
        position: { x: 300, y: 30 },
        data: {
          id: "node-task",
          label: "Task Goal",
          sublabel: "Financial Analysis",
          category: "task",
          status: "idle",
          description: "Target enterprise objective and parameters",
          inputs: { goal: "Calculate EBITDA and analyze corporate liquidity" },
        },
      },
      {
        id: "node-supervisor",
        type: "agent",
        position: { x: 300, y: 150 },
        data: {
          id: "node-supervisor",
          label: "Supervisor Agent",
          sublabel: "supervisor",
          category: "agent",
          status: "idle",
          description: "Orchestrates task decomposition and dispatching",
          metadata: { capabilities: ["supervision", "planning"] },
        },
      },
      {
        id: "node-model",
        type: "model",
        position: { x: 550, y: 150 },
        data: {
          id: "node-model",
          label: "Model Router",
          sublabel: "gemini-1.5-flash",
          category: "model",
          status: "idle",
          description: "Canonical model and provider routing engine",
          metadata: { provider: "google", workload_class: "general" },
        },
      },
      {
        id: "node-fin-specialist",
        type: "agent",
        position: { x: 80, y: 280 },
        data: {
          id: "node-fin-specialist",
          label: "Financial Specialist",
          sublabel: "financial_specialist",
          category: "agent",
          status: "idle",
          description: "Computes EBITDA, margins, and liquidity ratios",
          metadata: { capabilities: ["financial_analysis", "general_reasoning"] },
        },
      },
      {
        id: "node-finnapigo-specialist",
        type: "agent",
        position: { x: 300, y: 280 },
        data: {
          id: "node-finnapigo-specialist",
          label: "FinnApiGo Banking Specialist",
          sublabel: "finnapigo_specialist",
          category: "agent",
          status: "idle",
          description: "Queries upstream balances, limits, and transactions",
          metadata: { capabilities: ["banking_api"] },
        },
      },
      {
        id: "node-banking-tool",
        type: "tool",
        position: { x: 300, y: 400 },
        data: {
          id: "node-banking-tool",
          label: "Banking Tool",
          sublabel: "get_account_balance",
          category: "tool",
          status: "idle",
          toolName: "get_account_balance",
          description: "Interacts with authoritative ledger",
        },
      },
      {
        id: "node-approval-gate",
        type: "approval",
        position: { x: 550, y: 400 },
        data: {
          id: "node-approval-gate",
          label: "Approval Gate",
          sublabel: "mock_dangerous_shell",
          category: "approval",
          status: "idle",
          description: "Human sign-off gate for sensitive operations",
        },
      },
      {
        id: "node-verifier",
        type: "verification",
        position: { x: 190, y: 530 },
        data: {
          id: "node-verifier",
          label: "Verification Agent",
          sublabel: "verifier",
          category: "verification",
          status: "idle",
          description: "Evaluates mathematical invariants & tenant boundaries",
        },
      },
      {
        id: "node-synthesizer",
        type: "agent",
        position: { x: 190, y: 650 },
        data: {
          id: "node-synthesizer",
          label: "Synthesizer Agent",
          sublabel: "synthesizer",
          category: "agent",
          status: "idle",
          description: "Consolidates verified outputs with citations",
        },
      },
      {
        id: "node-result",
        type: "result",
        position: { x: 190, y: 770 },
        data: {
          id: "node-result",
          label: "Execution Result",
          sublabel: "Completed",
          category: "result",
          status: "idle",
          description: "Final verified response payload and telemetry",
        },
      },
    ];

    const edges: CanvasEdge[] = [
      { id: "e-task-supervisor", source: "node-task", target: "node-supervisor", animated: false },
      { id: "e-supervisor-model", source: "node-supervisor", target: "node-model", animated: false },
      { id: "e-supervisor-fin", source: "node-supervisor", target: "node-fin-specialist", animated: false },
      { id: "e-supervisor-finnapigo", source: "node-supervisor", target: "node-finnapigo-specialist", animated: false },
      { id: "e-finnapigo-tool", source: "node-finnapigo-specialist", target: "node-banking-tool", animated: false },
      { id: "e-tool-approval", source: "node-banking-tool", target: "node-approval-gate", animated: false },
      { id: "e-fin-verifier", source: "node-fin-specialist", target: "node-verifier", animated: false },
      { id: "e-tool-verifier", source: "node-banking-tool", target: "node-verifier", animated: false },
      { id: "e-approval-verifier", source: "node-approval-gate", target: "node-verifier", animated: false },
      { id: "e-verifier-synthesizer", source: "node-verifier", target: "node-synthesizer", animated: false },
      { id: "e-synthesizer-result", source: "node-synthesizer", target: "node-result", animated: false },
    ];

    return { nodes, edges };
  }

  if (type === "rag") {
    const nodes: CanvasNode[] = [
      {
        id: "rag-task",
        type: "task",
        position: { x: 250, y: 30 },
        data: {
          id: "rag-task",
          label: "Task Goal",
          sublabel: "SEC Document Search",
          category: "task",
          status: "idle",
        },
      },
      {
        id: "rag-retriever",
        type: "rag",
        position: { x: 250, y: 150 },
        data: {
          id: "rag-retriever",
          label: "Hybrid Vector Retriever",
          sublabel: "Qdrant + BM25",
          category: "rag",
          status: "idle",
          description: "Hybrid dense and sparse document retrieval",
        },
      },
      {
        id: "rag-agent",
        type: "agent",
        position: { x: 250, y: 270 },
        data: {
          id: "rag-agent",
          label: "RAG Retrieval Specialist",
          sublabel: "retrieval_specialist",
          category: "agent",
          status: "idle",
        },
      },
      {
        id: "rag-verifier",
        type: "verification",
        position: { x: 250, y: 390 },
        data: {
          id: "rag-verifier",
          label: "Groundedness Verifier",
          sublabel: "Self-RAG Critique",
          category: "verification",
          status: "idle",
        },
      },
      {
        id: "rag-result",
        type: "result",
        position: { x: 250, y: 510 },
        data: {
          id: "rag-result",
          label: "Grounded Output",
          sublabel: "Citations verified",
          category: "result",
          status: "idle",
        },
      },
    ];

    const edges: CanvasEdge[] = [
      { id: "e-rag-1", source: "rag-task", target: "rag-retriever" },
      { id: "e-rag-2", source: "rag-retriever", target: "rag-agent" },
      { id: "e-rag-3", source: "rag-agent", target: "rag-verifier" },
      { id: "e-rag-4", source: "rag-verifier", target: "rag-result" },
    ];

    return { nodes, edges };
  }

  // React tool execution
  const nodes: CanvasNode[] = [
    {
      id: "react-task",
      type: "task",
      position: { x: 250, y: 30 },
      data: {
        id: "react-task",
        label: "Task Goal",
        category: "task",
        status: "idle",
      },
    },
    {
      id: "react-agent",
      type: "agent",
      position: { x: 250, y: 150 },
      data: {
        id: "react-agent",
        label: "General ReAct Agent",
        sublabel: "general_agent",
        category: "agent",
        status: "idle",
      },
    },
    {
      id: "react-tool",
      type: "tool",
      position: { x: 100, y: 280 },
      data: {
        id: "react-tool",
        label: "Tool Registry",
        sublabel: "calculator",
        category: "tool",
        status: "idle",
      },
    },
    {
      id: "react-approval",
      type: "approval",
      position: { x: 400, y: 280 },
      data: {
        id: "react-approval",
        label: "Dangerous Action Gate",
        sublabel: "Operator Sign-off",
        category: "approval",
        status: "idle",
      },
    },
    {
      id: "react-result",
      type: "result",
      position: { x: 250, y: 420 },
      data: {
        id: "react-result",
        label: "Execution Result",
        category: "result",
        status: "idle",
      },
    },
  ];

  const edges: CanvasEdge[] = [
    { id: "e-re-1", source: "react-task", target: "react-agent" },
    { id: "e-re-2", source: "react-agent", target: "react-tool" },
    { id: "e-re-3", source: "react-agent", target: "react-approval" },
    { id: "e-re-4", source: "react-tool", target: "react-result" },
    { id: "e-re-5", source: "react-approval", target: "react-result" },
  ];

  return { nodes, edges };
}

/**
 * Maps backend step status to canvas node status
 */
export function mapBackendStatusToCanvas(status?: string | null): CanvasNodeStatus {
  switch (status?.toLowerCase()) {
    case "completed":
    case "verification_passed":
      return "completed";
    case "running":
    case "executing":
      return "running";
    case "waiting_approval":
    case "paused_approval":
      return "waiting_approval";
    case "failed":
    case "verification_failed":
    case "rejected":
    case "timeout":
      return "failed";
    case "cancelled":
      return "cancelled";
    case "pending":
    case "ready":
    case "planning":
      return "queued";
    default:
      return "idle";
  }
}

/**
 * Derives a CanvasNodeType from step metadata
 */
function deriveCategoryFromStep(step: PlanStepDTO): CanvasNodeType {
  if (step.pending_approval_id) return "approval";
  if (step.tool_name) return "tool";
  if (step.assigned_agent === "verifier" || step.description.toLowerCase().includes("verify")) {
    return "verification";
  }
  if (step.description.toLowerCase().includes("retrieve") || step.description.toLowerCase().includes("rag")) {
    return "rag";
  }
  if (step.selected_model && !step.assigned_agent) return "model";
  return "agent";
}

/**
 * Transforms an ExecutionPlanDTO and/or RunState into a Canvas DAG
 */
export function planToGraph(
  plan?: ExecutionPlanDTO | null,
  runState?: RunState | null
): { nodes: CanvasNode[]; edges: CanvasEdge[] } {
  if (!plan || !plan.steps || plan.steps.length === 0) {
    return getCanonicalTopology("supervisor");
  }

  const nodes: CanvasNode[] = [];
  const edges: CanvasEdge[] = [];

  // Root task node
  const taskNodeId = "step-root-task";
  nodes.push({
    id: taskNodeId,
    type: "task",
    position: { x: 300, y: 40 },
    data: {
      id: taskNodeId,
      label: "Task Goal",
      sublabel: runState?.status || "created",
      category: "task",
      status: mapBackendStatusToCanvas(runState?.status || "created"),
      description: plan.goal || runState?.prompt || "Autonomous agent execution",
      inputs: { goal: plan.goal || runState?.prompt },
    },
  });

  // Calculate topological levels for layout
  const stepLevels = new Map<string, number>();
  const stepMap = new Map<string, PlanStepDTO>();
  plan.steps.forEach((s) => stepMap.set(s.step_id, s));

  function getLevel(stepId: string, visited = new Set<string>()): number {
    if (visited.has(stepId)) return 0;
    visited.add(stepId);
    if (stepLevels.has(stepId)) return stepLevels.get(stepId)!;
    const step = stepMap.get(stepId);
    if (!step || !step.dependencies || step.dependencies.length === 0) {
      stepLevels.set(stepId, 1);
      return 1;
    }
    const maxDepLevel = Math.max(...step.dependencies.map((d) => getLevel(d, new Set(visited))));
    const lvl = maxDepLevel + 1;
    stepLevels.set(stepId, lvl);
    return lvl;
  }

  plan.steps.forEach((s) => getLevel(s.step_id));

  // Group steps by level for horizontal positioning
  const levelGroups = new Map<number, PlanStepDTO[]>();
  plan.steps.forEach((s) => {
    const lvl = stepLevels.get(s.step_id) || 1;
    const list = levelGroups.get(lvl) || [];
    list.push(s);
    levelGroups.set(lvl, list);
  });

  let maxLevel = 1;
  levelGroups.forEach((stepsInLevel, lvl) => {
    if (lvl > maxLevel) maxLevel = lvl;
    const yPos = 80 + lvl * 130;
    const count = stepsInLevel.length;
    const totalWidth = count * 260;
    const startX = 300 - totalWidth / 2 + 130;

    stepsInLevel.forEach((step, idx) => {
      const xPos = startX + idx * 260;
      const category = deriveCategoryFromStep(step);
      const status = mapBackendStatusToCanvas(step.status);

      nodes.push({
        id: step.step_id,
        type: category,
        position: { x: xPos, y: yPos },
        data: {
          id: step.step_id,
          label: step.description,
          sublabel: step.assigned_agent || step.tool_name || step.selected_model || category,
          category,
          status,
          description: step.objective || step.description,
          latencyMs: step.result?.execution_time_ms,
          error: step.error || step.result?.error,
          inputs: step.tool_args || {},
          outputs: step.observation || step.result?.output,
          toolName: step.tool_name || undefined,
          approvalId: step.pending_approval_id || undefined,
          metadata: {
            required_capabilities: step.required_capabilities,
            selected_model: step.selected_model,
            selected_provider: step.selected_provider,
          },
        },
      });

      // Connect dependencies
      if (step.dependencies && step.dependencies.length > 0) {
        step.dependencies.forEach((depId) => {
          edges.push({
            id: `e-${depId}-${step.step_id}`,
            source: depId,
            target: step.step_id,
            animated: status === "running",
            status,
          });
        });
      } else {
        // Connect root task
        edges.push({
          id: `e-task-${step.step_id}`,
          source: taskNodeId,
          target: step.step_id,
          animated: status === "running",
          status,
        });
      }
    });
  });

  // Terminal result node
  const resultNodeId = "step-terminal-result";
  const finalStatus = mapBackendStatusToCanvas(runState?.status);
  const lastLevelSteps = levelGroups.get(maxLevel) || [];

  nodes.push({
    id: resultNodeId,
    type: "result",
    position: { x: 300, y: 120 + (maxLevel + 1) * 130 },
    data: {
      id: resultNodeId,
      label: "Result Synthesis",
      sublabel: runState?.final_output ? "Completed" : (runState?.status || "Pending"),
      category: "result",
      status: finalStatus,
      description: "Final verified response payload",
      outputs: runState?.final_output,
      error: runState?.error,
      citations: (runState?.metadata?.citations as unknown as CanvasNode["data"]["citations"]) || [],
    },
  });

  lastLevelSteps.forEach((s) => {
    edges.push({
      id: `e-${s.step_id}-${resultNodeId}`,
      source: s.step_id,
      target: resultNodeId,
      animated: finalStatus === "running",
      status: finalStatus,
    });
  });

  return { nodes, edges };
}

/**
 * Pure state updater: applies an incoming backend SSE event to the graph
 */
export function applyEventToGraph(
  event: BackendRunEvent,
  currentGraph: OrchestrationGraphState
): OrchestrationGraphState {
  const { event_type, data = {} } = event;
  let nextActiveNodeId = currentGraph.activeNodeId;

  const updatedNodes = currentGraph.nodes.map((node) => {
    const nodeData = { ...node.data };
    const stepId = (data.step_id as string) || (data.node as string);

    // Match by step ID or node ID
    const isTarget = node.id === stepId || node.data.sublabel === stepId;

    switch (event_type) {
      case "task_created":
      case "planning_started":
        if (node.type === "task") {
          nodeData.status = "running";
        }
        break;

      case "step_started":
        if (isTarget) {
          nodeData.status = "running";
          nodeData.isCurrentStep = true;
          nextActiveNodeId = node.id;
        } else if (node.data.isCurrentStep) {
          nodeData.isCurrentStep = false;
        }
        break;

      case "agent_selected":
        if (isTarget) {
          nodeData.sublabel = (data.agent_id as string) || nodeData.sublabel;
        }
        break;

      case "model_selected":
        if (isTarget || node.type === "model") {
          if (data.model) {
            nodeData.sublabel = data.model as string;
          }
        }
        break;

      case "tool_selected":
      case "tool_call":
        if (isTarget || node.data.toolName === data.tool_name) {
          nodeData.status = "running";
          if (data.arguments) {
            nodeData.inputs = data.arguments as Record<string, unknown>;
          }
          nextActiveNodeId = node.id;
        }
        break;

      case "observation":
      case "tool_result":
        if (isTarget || node.data.toolName === data.tool_name) {
          const success = data.success !== false;
          nodeData.status = success ? "completed" : "failed";
          nodeData.outputs = data.output;
          nodeData.error = (data.error as string) || null;
          if (typeof data.duration_ms === "number") {
            nodeData.latencyMs = Math.round(data.duration_ms);
          }
        }
        break;

      case "step_completed":
        if (isTarget) {
          nodeData.status = "completed";
          nodeData.isCurrentStep = false;
          nodeData.outputs = data.output;
        }
        break;

      case "step_retrying":
        if (isTarget) {
          nodeData.status = "running";
          nodeData.executionCount = ((nodeData.executionCount || 0) + 1);
        }
        break;

      case "approval_required":
      case "waiting_approval":
        if (isTarget || node.type === "approval" || node.data.toolName === data.tool_name) {
          nodeData.status = "waiting_approval";
          nodeData.approvalId = (data.approval_id as string) || nodeData.approvalId;
          nodeData.approvalReason = (data.reason as string) || nodeData.approvalReason;
          nextActiveNodeId = node.id;
        }
        break;

      case "verification_started":
        if (node.type === "verification") {
          nodeData.status = "running";
          nextActiveNodeId = node.id;
        }
        break;

      case "verification_result":
        if (node.type === "verification") {
          const verdict = (data.verdict as "PASS" | "NEEDS_REVISION" | "FAILED" | "REJECTED") || "PASS";
          nodeData.verdict = verdict;
          nodeData.status = verdict === "PASS" ? "completed" : verdict === "NEEDS_REVISION" ? "queued" : "failed";
          nodeData.outputs = data.reason || `Verdict: ${verdict}`;
        }
        break;

      case "completed":
        if (node.type === "result") {
          nodeData.status = "completed";
          nodeData.outputs = data.output;
          nextActiveNodeId = null;
        }
        break;

      case "failed":
        if (isTarget || node.type === "result") {
          nodeData.status = "failed";
          nodeData.error = (data.error as string) || "Execution failed";
          nextActiveNodeId = null;
        }
        break;

      case "cancelled":
        if (node.data.status === "running" || node.data.status === "waiting_approval") {
          nodeData.status = "cancelled";
        }
        if (node.type === "result") {
          nodeData.status = "cancelled";
          nodeData.outputs = "Execution cancelled by operator.";
        }
        nextActiveNodeId = null;
        break;
    }

    return { ...node, data: nodeData };
  });

  // Update edges animation state based on active node
  const updatedEdges = currentGraph.edges.map((edge) => {
    const isEdgeActive = edge.target === nextActiveNodeId || edge.source === nextActiveNodeId;
    return {
      ...edge,
      animated: isEdgeActive,
    };
  });

  return {
    ...currentGraph,
    nodes: updatedNodes,
    edges: updatedEdges,
    activeNodeId: nextActiveNodeId,
  };
}

/**
 * Creates a clean TimelineEvent from an incoming SSE frame
 */
export function createTimelineEvent(event: BackendRunEvent): TimelineEvent {
  const ts = event.timestamp ? event.timestamp * 1000 : Date.now();
  const data = event.data || {};
  let title = event.event_type.replace(/_/g, " ").toUpperCase();
  let description = "";
  let status: CanvasNodeStatus = "idle";
  let durationMs: number | undefined;

  switch (event.event_type) {
    case "run_started":
    case "task_created":
      title = "Task Initiated";
      description = (data.goal as string) || "Autonomous execution queued";
      status = "running";
      break;
    case "plan_created":
      title = "DAG Plan Created";
      description = `${data.steps_count || 0} milestones scheduled via ${data.planner_mode || "planner"}`;
      status = "queued";
      break;
    case "step_started":
      title = `Step Started: ${data.step_id || "step"}`;
      description = (data.description as string) || "";
      status = "running";
      break;
    case "agent_selected":
      title = "Agent Dispatched";
      description = `Assigned to ${data.agent_id} (${data.selection_mode || "canonical"})`;
      status = "running";
      break;
    case "model_selected":
      title = "Model Routed";
      description = `${data.model} on ${data.provider} (${data.workload_class || "general"})`;
      status = "running";
      break;
    case "tool_call":
    case "tool_selected":
      title = `Tool Invocation: ${data.tool_name}`;
      description = data.thought ? String(data.thought) : "Executing tool with validated policy";
      status = "running";
      break;
    case "observation":
    case "tool_result":
      title = `Tool Observation: ${data.tool_name}`;
      description = data.success !== false ? "Execution succeeded" : `Error: ${data.error}`;
      status = data.success !== false ? "completed" : "failed";
      durationMs = typeof data.duration_ms === "number" ? Math.round(data.duration_ms) : undefined;
      break;
    case "approval_required":
    case "waiting_approval":
      title = "Human Approval Required";
      description = `Dangerous action: ${data.tool_name}. Reason: ${data.reason}`;
      status = "waiting_approval";
      break;
    case "step_completed":
      title = `Step Completed: ${data.step_id || "step"}`;
      status = "completed";
      break;
    case "step_retrying":
      title = `Step Retrying: ${data.step_id || "step"}`;
      description = `Attempt ${data.retry_attempt}: ${data.reason || "Automatic recovery"}`;
      status = "running";
      break;
    case "verification_started":
      title = "Verification Gate";
      description = "Auditing mathematical invariants and RAG grounding";
      status = "running";
      break;
    case "verification_result":
      title = `Verification Verdict: ${data.verdict}`;
      description = (data.reason as string) || "";
      status = data.verdict === "PASS" ? "completed" : "failed";
      break;
    case "completed":
      title = "Run Completed";
      description = "Execution succeeded with verified outputs";
      status = "completed";
      durationMs = typeof data.elapsed_ms === "number" ? Math.round(data.elapsed_ms) : undefined;
      break;
    case "failed":
      title = "Run Failed";
      description = (data.error as string) || "Execution halted";
      status = "failed";
      break;
    case "cancelled":
      title = "Run Cancelled";
      description = (data.message as string) || "Operator terminated execution";
      status = "cancelled";
      break;
  }

  return {
    id: `ev-${Date.now()}-${Math.random().toString(36).slice(2, 6)}`,
    eventType: event.event_type,
    timestamp: ts,
    taskId: event.task_id,
    runId: event.run_id,
    nodeId: (data.step_id as string) || undefined,
    title,
    description,
    status,
    durationMs,
    data,
  };
}
