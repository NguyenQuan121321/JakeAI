import * as React from "react";
import {
  useNodesState,
  useEdgesState,
} from "@xyflow/react";
import {
  Play,
  Square,
  Sparkles,
  Layers,
  LayoutGrid,
  CheckCircle2,
  Zap,
  Bot,
  ShieldCheck,
  AlertCircle,
} from "lucide-react";
import { Button } from "@/components/ui/button";
import { Input } from "@/components/ui/input";
import { Badge } from "@/components/ui/badge";
import { Card, CardContent, CardHeader, CardTitle, CardDescription } from "@/components/ui/card";
import { OrchestrationCanvas } from "@/components/agent-canvas/orchestration-canvas";
import { NodePalette } from "@/components/agent-canvas/node-palette";
import { NodeInspector } from "@/components/agent-canvas/node-inspector";
import { EventTimeline } from "@/components/agent-canvas/event-timeline";
import { ApprovalBanner } from "@/components/agent-canvas/approval-banner";
import { agentService } from "@/api/services/agent.service";
import {
  getCanonicalTopology,
  planToGraph,
  applyEventToGraph,
  createTimelineEvent,
  type ExecutionPlanDTO,
} from "@/lib/agent-graph-adapter";
import type {
  CanvasNode,
  CanvasEdge,
  CanvasNodeData,
  TimelineEvent,
} from "@/types/agent-graph";
import type { TaskState, RunState } from "@/api/types/domain";

const PRESET_GOALS = [
  {
    title: "Corporate Liquidity & EBITDA Analysis",
    goal: "Calculate EBITDA and analyze corporate financial liquidity ratios",
    topology: "supervisor" as const,
  },
  {
    title: "SEC 10-K RAG Retrieval",
    goal: "Query SEC 10-K hybrid index for perimeter debt covenants",
    topology: "rag" as const,
  },
  {
    title: "ReAct System Time & Ledger Audit",
    goal: "Audit account transactions and evaluate ledger balance consistency",
    topology: "react" as const,
  },
];

export default function AgentPage() {
  // Mode: Canvas View (Advanced / Admin) vs Simple View (Standard Users)
  const [viewMode, setViewMode] = React.useState<"canvas" | "simple">("canvas");
  const [activeTopology, setActiveTopology] = React.useState<"supervisor" | "rag" | "react">("supervisor");

  // Task & Run State
  const [goalInput, setGoalInput] = React.useState(PRESET_GOALS[0].goal);
  const [currentTask, setCurrentTask] = React.useState<TaskState | null>(null);
  const [currentRun, setCurrentRun] = React.useState<RunState | null>(null);
  const [isExecuting, setIsExecuting] = React.useState(false);
  const [errorText, setErrorText] = React.useState<string | null>(null);

  // Approval State
  const [pendingApproval, setPendingApproval] = React.useState<{
    taskId: string;
    runId: string;
    approvalId: string;
    toolName: string;
    reason?: string;
    stepId?: string;
    toolArgs?: Record<string, unknown>;
  } | null>(null);


  // Graph State (@xyflow/react hooks)
  const initialTopology = React.useMemo(() => getCanonicalTopology("supervisor"), []);
  const [nodes, setNodes, onNodesChange] = useNodesState<CanvasNode>(initialTopology.nodes);
  const [edges, setEdges, onEdgesChange] = useEdgesState<CanvasEdge>(initialTopology.edges);
  const [selectedNodeData, setSelectedNodeData] = React.useState<CanvasNodeData | null>(null);

  const nodesRef = React.useRef(nodes);
  nodesRef.current = nodes;
  const edgesRef = React.useRef(edges);
  edgesRef.current = edges;
  const selectedNodeDataRef = React.useRef(selectedNodeData);
  selectedNodeDataRef.current = selectedNodeData;

  // Timeline & Streaming Trace
  const [timelineEvents, setTimelineEvents] = React.useState<TimelineEvent[]>([]);
  const [isTimelineExpanded, setIsTimelineExpanded] = React.useState(false);
  const abortControllerRef = React.useRef<AbortSignal | null>(null);
  const runAbortController = React.useRef<AbortController | null>(null);

  // Reset or Switch Topology
  const handleSelectTopology = React.useCallback(
    (topology: "supervisor" | "rag" | "react") => {
      setActiveTopology(topology);
      const topo = getCanonicalTopology(topology);
      setNodes(topo.nodes);
      setEdges(topo.edges);
      setSelectedNodeData(null);
    },
    [setNodes, setEdges]
  );

  // Check if current run is terminal
  const isTerminalRun = React.useMemo(() => {
    if (!currentRun) return true;
    return ["completed", "failed", "cancelled", "rejected", "timeout"].includes(currentRun.status);
  }, [currentRun]);

  // Start Autonomous Run
  const handleStartRun = async () => {
    if (!goalInput.trim() || isExecuting) return;

    setErrorText(null);
    setIsExecuting(true);
    setPendingApproval(null);
    setSelectedNodeData(null);

    // Cancel existing stream if any
    if (runAbortController.current) {
      runAbortController.current.abort();
    }
    const abortController = new AbortController();
    runAbortController.current = abortController;
    abortControllerRef.current = abortController.signal;

    try {
      // 1. Create Task
      const task = await agentService.createTask({
        goal: goalInput,
        metadata: { source: "canvas_orchestration", topology: activeTopology },
      });
      setCurrentTask(task);

      // 2. Start Run
      const run = await agentService.startRun(task.task_id, {
        max_iterations: 10,
        async_execution: true,
      });
      setCurrentRun(run);

      // If run already has a structured plan from backend, adapt it to graph
      if (run.plan) {
        const planGraph = planToGraph(run.plan as unknown as ExecutionPlanDTO, run);
        nodesRef.current = planGraph.nodes;
        edgesRef.current = planGraph.edges;
        setNodes(planGraph.nodes);
        setEdges(planGraph.edges);
      }

      // 3. Connect to real-time SSE stream
      await agentService.streamRunEvents({
        taskId: task.task_id,
        runId: run.run_id,
        signal: abortController.signal,
        onEvent: (event) => {
          // Append to Timeline
          const timelineEv = createTimelineEvent(event);
          setTimelineEvents((prev) => [...prev, timelineEv]);

          // Transform Graph state incrementally
          const currentGraph = {
            nodes: nodesRef.current,
            edges: edgesRef.current,
            activeNodeId: null,
            selectedNodeId: selectedNodeDataRef.current?.id || null,
          };
          const updated = applyEventToGraph(event, currentGraph);
          nodesRef.current = updated.nodes;
          edgesRef.current = updated.edges;
          setNodes(updated.nodes);
          setEdges(updated.edges);

          if (selectedNodeDataRef.current) {
            const currentSelected = updated.nodes.find((n) => n.id === selectedNodeDataRef.current?.id);
            if (currentSelected) {
              setSelectedNodeData(currentSelected.data);
            }
          }

          // Handle Approval Required
          if (event.event_type === "approval_required" || event.event_type === "waiting_approval") {
            const data = event.data || {};
            setPendingApproval({
              taskId: task.task_id,
              runId: run.run_id,
              approvalId: (data.approval_id as string) || "appr-pending",
              toolName: (data.tool_name as string) || "dangerous_tool",
              reason: (data.reason as string) || "Action requires operator approval",
              stepId: (data.step_id as string) || undefined,
              toolArgs: (data.arguments as Record<string, unknown>) || undefined,
            });
            setCurrentRun((prev) => ({ ...(prev || run), status: "waiting_approval" }));
          }

          // Handle Terminal Statuses
          if (["completed", "failed", "cancelled"].includes(event.event_type)) {
            setIsExecuting(false);
            setCurrentRun((prev) => ({
              ...(prev || run),
              status: event.event_type as RunState["status"],
              final_output: (event.data?.output as string) || prev?.final_output || run.final_output,
              error: (event.data?.error as string) || prev?.error || run.error,
            }));
          }

        },
        onError: (err) => {
          setErrorText(err.message);
          setIsExecuting(false);
        },
        onComplete: () => {
          setIsExecuting(false);
        },
      });
    } catch (err: unknown) {
      const msg = err instanceof Error ? err.message : "Failed to execute agent run";
      setErrorText(msg);
      setIsExecuting(false);
    }
  };

  // Cancel Run
  const handleCancelRun = async () => {
    if (!currentTask || !currentRun || isTerminalRun) return;

    try {
      const updated = await agentService.cancelRun(currentTask.task_id, currentRun.run_id);
      setCurrentRun(updated);
      setIsExecuting(false);
      setPendingApproval(null);

      if (runAbortController.current) {
        runAbortController.current.abort();
      }

      // Mark running nodes as cancelled
      setNodes((prev) =>
        prev.map((n) =>
          n.data.status === "running" || n.data.status === "waiting_approval"
            ? { ...n, data: { ...n.data, status: "cancelled" } }
            : n
        )
      );

      setTimelineEvents((prev) => [
        ...prev,
        {
          id: `ev-cancel-${Date.now()}`,
          eventType: "cancelled",
          timestamp: Date.now(),
          taskId: currentTask.task_id,
          runId: currentRun.run_id,
          title: "Run Cancelled",
          description: "Operator terminated execution cooperatively",
          status: "cancelled",
        },
      ]);
    } catch (err: unknown) {
      const msg = err instanceof Error ? err.message : "Failed to cancel run";
      setErrorText(msg);
    }
  };

  // Approval Decision Response
  const handleApprovalDecided = (approved: boolean, rationale?: string) => {
    setPendingApproval(null);
    setTimelineEvents((prev) => [
      ...prev,
      {
        id: `ev-appr-${Date.now()}`,
        eventType: approved ? "approval_granted" : "approval_rejected",
        timestamp: Date.now(),
        taskId: currentTask?.task_id || "",
        runId: currentRun?.run_id || "",
        title: approved ? "Approval Granted" : "Approval Rejected",
        description: rationale || (approved ? "Authorized by operator" : "Rejected by operator"),
        status: approved ? "completed" : "failed",
      },
    ]);

    if (!approved) {
      setIsExecuting(false);
      setCurrentRun((prev) => (prev ? { ...prev, status: "rejected" } : null));
    }
  };

  // Clean up stream on unmount
  React.useEffect(() => {
    return () => {
      if (runAbortController.current) {
        runAbortController.current.abort();
      }
    };
  }, []);

  return (
    <div className="flex flex-col h-[calc(100vh-4.25rem)] overflow-hidden bg-background">
      {/* Top Workspace Header */}
      <div className="flex flex-col md:flex-row items-stretch md:items-center justify-between gap-3 px-4 py-2.5 border-b bg-card z-20 flex-shrink-0">
        <div className="flex items-center gap-3">
          <div className="p-2 rounded-lg bg-primary/10 text-primary">
            <Bot className="h-5 w-5" />
          </div>
          <div>
            <div className="flex items-center gap-2">
              <h1 className="text-sm font-bold tracking-tight">Agent Orchestration Canvas</h1>
              <Badge variant="secondary" className="text-[10px] font-mono">
                {currentRun ? `Run: ${currentRun.status}` : "Ready"}
              </Badge>
            </div>
            <p className="text-[11px] text-muted-foreground">
              Deterministic multi-agent DAG execution, model routing, and verification.
            </p>
          </div>
        </div>

        {/* Action Controls & Task Submitter */}
        <div className="flex items-center gap-2 flex-wrap">
          {/* Goal Input Bar */}
          <div className="relative min-w-[240px] md:min-w-[320px]">
            <Input
              placeholder="Enter goal or problem statement..."
              value={goalInput}
              onChange={(e) => setGoalInput(e.target.value)}
              disabled={isExecuting}
              className="h-8 text-xs bg-background pr-8"
              data-testid="canvas-goal-input"
            />
            {goalInput && (
              <button
                onClick={() => setGoalInput("")}
                disabled={isExecuting}
                className="absolute right-2 top-2 text-xs text-muted-foreground hover:text-foreground"
              >
                ✕
              </button>
            )}
          </div>

          {/* Start Run Button */}
          <Button
            size="sm"
            onClick={handleStartRun}
            disabled={isExecuting || !goalInput.trim()}
            className="h-8 text-xs gap-1.5 bg-primary text-primary-foreground font-semibold shadow-sm"
            data-testid="start-run-button"
          >
            <Play className="h-3.5 w-3.5 fill-current" />
            {isExecuting ? "Executing..." : "Start Run"}
          </Button>

          {/* Cancel Run Button */}
          <Button
            size="sm"
            variant="outline"
            onClick={handleCancelRun}
            disabled={!isExecuting && isTerminalRun}
            className="h-8 text-xs gap-1.5 text-destructive border-destructive/30 hover:bg-destructive/10"
            data-testid="cancel-run-button"
          >
            <Square className="h-3 w-3 fill-current" />
            Cancel
          </Button>

          {/* View Mode Toggle: Canvas vs Simple (Product Rule) */}
          <div className="flex items-center border rounded-lg p-0.5 bg-muted/40 text-xs">
            <button
              onClick={() => setViewMode("canvas")}
              className={`flex items-center gap-1 px-2.5 py-1 rounded-md transition-colors ${
                viewMode === "canvas"
                  ? "bg-card text-foreground font-semibold shadow-xs"
                  : "text-muted-foreground hover:text-foreground"
              }`}
              data-testid="toggle-canvas-view"
            >
              <Layers className="h-3.5 w-3.5" />
              Canvas
            </button>
            <button
              onClick={() => setViewMode("simple")}
              className={`flex items-center gap-1 px-2.5 py-1 rounded-md transition-colors ${
                viewMode === "simple"
                  ? "bg-card text-foreground font-semibold shadow-xs"
                  : "text-muted-foreground hover:text-foreground"
              }`}
              data-testid="toggle-simple-view"
            >
              <LayoutGrid className="h-3.5 w-3.5" />
              Simple
            </button>
          </div>
        </div>
      </div>

      {/* Preset Goals Pill Bar */}
      <div className="flex items-center gap-2 px-4 py-1.5 border-b bg-muted/20 text-xs overflow-x-auto select-none flex-shrink-0">
        <span className="text-[10px] uppercase font-bold text-muted-foreground flex items-center gap-1">
          <Sparkles className="h-3 w-3 text-primary" /> Presets:
        </span>
        {PRESET_GOALS.map((preset, idx) => (
          <button
            key={idx}
            disabled={isExecuting}
            onClick={() => {
              setGoalInput(preset.goal);
              handleSelectTopology(preset.topology);
            }}
            className="text-[11px] px-2 py-0.5 rounded-full border border-border bg-card/80 hover:bg-accent text-muted-foreground hover:text-foreground transition-colors whitespace-nowrap"
          >
            {preset.title}
          </button>
        ))}
      </div>

      {/* Error Alert Bar */}
      {errorText && (
        <div className="flex items-center justify-between px-4 py-2 bg-destructive/15 border-b border-destructive/30 text-destructive text-xs">
          <div className="flex items-center gap-2">
            <AlertCircle className="h-4 w-4 flex-shrink-0" />
            <span>{errorText}</span>
          </div>
          <button onClick={() => setErrorText(null)} className="text-xs font-bold">
            Dismiss
          </button>
        </div>
      )}

      {/* Approval Required Banner */}
      {pendingApproval && (
        <ApprovalBanner
          taskId={pendingApproval.taskId}
          runId={pendingApproval.runId}
          approvalId={pendingApproval.approvalId}
          toolName={pendingApproval.toolName}
          reason={pendingApproval.reason}
          stepId={pendingApproval.stepId}
          toolArgs={pendingApproval.toolArgs}
          onDecided={handleApprovalDecided}
        />
      )}


      {/* Main Workspace Body */}
      {viewMode === "canvas" ? (
        // 4-Pane Orchestration Layout
        <div className="flex-1 flex flex-col min-h-0 relative">
          <div className="flex-1 flex min-h-0 relative">
            {/* Left Node Palette */}
            <NodePalette
              activeTopology={activeTopology}
              onSelectTopology={handleSelectTopology}
              onInspectItem={(item) => {
                // Find node or create virtual inspection preview
                const found = nodes.find((n) => n.data.category === item.category);
                if (found) {
                  setSelectedNodeData(found.data);
                } else {
                  setSelectedNodeData({
                    id: item.id,
                    label: item.name,
                    sublabel: item.sublabel,
                    category: item.category,
                    status: "idle",
                    description: item.description,
                  });
                }
              }}
            />

            {/* Center React Flow Canvas */}
            <div className="flex-1 h-full relative overflow-hidden bg-dot-pattern">
              <OrchestrationCanvas
                nodes={nodes}
                edges={edges}
                onNodesChange={onNodesChange}
                onEdgesChange={onEdgesChange}
                selectedNodeId={selectedNodeData?.id || null}
                onSelectNode={(nodeData) => setSelectedNodeData(nodeData)}
              />
            </div>

            {/* Right Node Inspector */}
            <NodeInspector
              nodeData={selectedNodeData}
              onClose={() => setSelectedNodeData(null)}
            />
          </div>

          {/* Bottom Event Timeline */}
          <EventTimeline
            events={timelineEvents}
            isExpanded={isTimelineExpanded}
            onToggleExpand={() => setIsTimelineExpanded((prev) => !prev)}
            onSelectEventNode={(nodeId) => {
              const target = nodes.find((n) => n.id === nodeId || n.data.sublabel === nodeId);
              if (target) setSelectedNodeData(target.data);
            }}
            onClearEvents={() => setTimelineEvents([])}
          />
        </div>
      ) : (
        // Simple User Execution View (Product Rule)
        <div className="flex-1 overflow-y-auto p-6 space-y-6 max-w-4xl mx-auto w-full" data-testid="simple-execution-view">
          {/* Active Run Overview Card */}
          <Card>
            <CardHeader className="pb-3">
              <div className="flex items-center justify-between">
                <CardTitle className="text-base font-bold">Execution Status</CardTitle>
                <Badge
                  variant={
                    currentRun?.status === "completed"
                      ? "default"
                      : currentRun?.status === "failed"
                      ? "destructive"
                      : "secondary"
                  }
                  className="font-mono text-xs capitalize"
                >
                  {currentRun?.status || "Idle"}
                </Badge>
              </div>
              <CardDescription className="text-xs">
                {currentTask?.goal || goalInput}
              </CardDescription>
            </CardHeader>
            <CardContent className="space-y-4">
              {/* Canonical Milestones Stepper */}
              <div className="grid grid-cols-2 sm:grid-cols-4 gap-2 pt-2">
                {[
                  { label: "Planning", icon: Layers, done: Boolean(currentRun) },
                  { label: "Execution", icon: Zap, done: Boolean(currentRun && currentRun.status !== "created") },
                  { label: "Verification", icon: ShieldCheck, done: Boolean(currentRun?.status === "completed") },
                  { label: "Synthesis", icon: CheckCircle2, done: Boolean(currentRun?.final_output) },
                ].map((st, idx) => {
                  const Icon = st.icon;
                  return (
                    <div
                      key={idx}
                      className={`p-3 rounded-lg border flex items-center gap-2.5 ${
                        st.done
                          ? "bg-primary/5 border-primary/30 text-foreground"
                          : "bg-muted/30 text-muted-foreground"
                      }`}
                    >
                      <Icon className={`h-4 w-4 ${st.done ? "text-primary" : "text-muted-foreground"}`} />
                      <span className="text-xs font-semibold">{st.label}</span>
                    </div>
                  );
                })}
              </div>

              {/* Final Output Result Panel */}
              {currentRun?.final_output && (
                <div className="p-4 rounded-xl border bg-card space-y-2 mt-4">
                  <div className="flex items-center justify-between">
                    <span className="text-xs font-bold uppercase tracking-wider text-muted-foreground flex items-center gap-1.5">
                      <CheckCircle2 className="h-4 w-4 text-emerald-500" />
                      Verified Result
                    </span>
                    <span className="text-xs font-mono text-muted-foreground">
                      Tokens: {currentRun.tokens_consumed || 120}
                    </span>
                  </div>
                  <p className="text-xs leading-relaxed text-foreground whitespace-pre-wrap font-sans">
                    {currentRun.final_output}
                  </p>
                </div>
              )}

              {/* Execution Error */}
              {currentRun?.error && (
                <div className="p-4 rounded-xl border border-destructive/40 bg-destructive/10 text-destructive text-xs font-mono">
                  {currentRun.error}
                </div>
              )}
            </CardContent>
          </Card>

          {/* Recent Event Stream Feed */}
          <Card>
            <CardHeader className="pb-2">
              <CardTitle className="text-sm font-bold flex items-center justify-between">
                <span>Recent Milestone Events</span>
                <Badge variant="outline" className="text-[10px] font-mono">
                  {timelineEvents.length} items
                </Badge>
              </CardTitle>
            </CardHeader>
            <CardContent>
              <div className="space-y-2 max-h-80 overflow-y-auto font-mono text-xs">
                {timelineEvents.length === 0 ? (
                  <p className="text-xs text-muted-foreground py-6 text-center font-sans">
                    No run events yet. Submit a task above to start autonomous execution.
                  </p>
                ) : (
                  timelineEvents.map((ev) => (
                    <div
                      key={ev.id}
                      className="p-2.5 rounded-lg border bg-muted/20 flex items-center justify-between gap-2 text-[11px]"
                    >
                      <div className="flex items-center gap-2 truncate">
                        <span className="text-muted-foreground text-[10px]">
                          {new Date(ev.timestamp).toLocaleTimeString()}
                        </span>
                        <span className="font-semibold text-foreground truncate">{ev.title}</span>
                      </div>
                      <Badge variant="outline" className="text-[9px] font-mono capitalize">
                        {ev.status || "idle"}
                      </Badge>
                    </div>
                  ))
                )}
              </div>
            </CardContent>
          </Card>
        </div>
      )}
    </div>
  );
}
