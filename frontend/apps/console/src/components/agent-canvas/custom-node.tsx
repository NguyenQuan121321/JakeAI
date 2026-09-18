import * as React from "react";
import { Handle, Position, type NodeProps } from "@xyflow/react";
import {
  Bot,
  Cpu,
  Database,
  Wrench,
  ShieldCheck,
  AlertTriangle,
  CheckCircle2,
  Target,
  Clock,
  RotateCw,
  AlertCircle,
} from "lucide-react";
import { cn } from "@/lib/utils";
import type { CanvasNodeData, CanvasNodeType, CanvasNodeStatus } from "@/types/agent-graph";

const CATEGORY_ICONS: Record<CanvasNodeType, React.ElementType> = {
  task: Target,
  agent: Bot,
  model: Cpu,
  rag: Database,
  tool: Wrench,
  verification: ShieldCheck,
  approval: AlertTriangle,
  result: CheckCircle2,
};

const CATEGORY_COLORS: Record<CanvasNodeType, { border: string; bg: string; text: string }> = {
  task: { border: "border-sky-500/40", bg: "bg-sky-500/10", text: "text-sky-600 dark:text-sky-400" },
  agent: { border: "border-indigo-500/40", bg: "bg-indigo-500/10", text: "text-indigo-600 dark:text-indigo-400" },
  model: { border: "border-purple-500/40", bg: "bg-purple-500/10", text: "text-purple-600 dark:text-purple-400" },
  rag: { border: "border-teal-500/40", bg: "bg-teal-500/10", text: "text-teal-600 dark:text-teal-400" },
  tool: { border: "border-amber-500/40", bg: "bg-amber-500/10", text: "text-amber-600 dark:text-amber-400" },
  verification: { border: "border-emerald-500/40", bg: "bg-emerald-500/10", text: "text-emerald-600 dark:text-emerald-400" },
  approval: { border: "border-rose-500/40", bg: "bg-rose-500/10", text: "text-rose-600 dark:text-rose-400" },
  result: { border: "border-blue-500/40", bg: "bg-blue-500/10", text: "text-blue-600 dark:text-blue-400" },
};

const STATUS_STYLES: Record<CanvasNodeStatus, { badge: string; ring: string; label: string }> = {
  idle: {
    badge: "bg-muted text-muted-foreground border-border",
    ring: "border-border",
    label: "Idle",
  },
  queued: {
    badge: "bg-amber-500/10 text-amber-600 dark:text-amber-400 border-amber-500/30",
    ring: "border-amber-500/40",
    label: "Queued",
  },
  running: {
    badge: "bg-primary/20 text-primary border-primary/50 animate-pulse",
    ring: "border-primary ring-2 ring-primary/40 shadow-lg shadow-primary/20",
    label: "Running",
  },
  waiting_approval: {
    badge: "bg-rose-500/20 text-rose-600 dark:text-rose-400 border-rose-500/50 animate-bounce",
    ring: "border-rose-500 ring-2 ring-rose-500/40 shadow-lg shadow-rose-500/20",
    label: "Awaiting Approval",
  },
  completed: {
    badge: "bg-emerald-500/10 text-emerald-600 dark:text-emerald-400 border-emerald-500/30",
    ring: "border-emerald-500/50",
    label: "Completed",
  },
  failed: {
    badge: "bg-destructive/15 text-destructive border-destructive/30",
    ring: "border-destructive/60",
    label: "Failed",
  },
  cancelled: {
    badge: "bg-zinc-500/15 text-zinc-500 border-zinc-500/30",
    ring: "border-zinc-500/40",
    label: "Cancelled",
  },
};

export const CustomNode = React.memo(({ data, selected }: NodeProps) => {
  const nodeData = data as unknown as CanvasNodeData;
  const category = nodeData.category || "agent";
  const status = nodeData.status || "idle";

  const Icon = CATEGORY_ICONS[category] || Bot;
  const colors = CATEGORY_COLORS[category] || CATEGORY_COLORS.agent;
  const statusStyle = STATUS_STYLES[status] || STATUS_STYLES.idle;

  return (
    <div
      className={cn(
        "relative flex flex-col rounded-xl border bg-card text-card-foreground p-3.5 shadow-sm transition-all duration-200 min-w-[220px] max-w-[280px]",
        statusStyle.ring,
        selected && "ring-2 ring-offset-2 ring-primary ring-offset-background",
        nodeData.isCurrentStep && "ring-2 ring-primary shadow-md"
      )}
      data-testid={`canvas-node-${nodeData.id}`}
      data-status={status}
    >
      {/* Target Handles */}
      <Handle
        type="target"
        position={Position.Top}
        className="w-2.5 h-2.5 !bg-muted-foreground border-2 border-background"
      />
      <Handle
        type="target"
        position={Position.Left}
        className="w-2.5 h-2.5 !bg-muted-foreground border-2 border-background"
      />

      {/* Header Row */}
      <div className="flex items-center justify-between gap-2 mb-2">
        <div className="flex items-center gap-2 overflow-hidden">
          <div className={cn("p-1.5 rounded-lg border flex-shrink-0", colors.bg, colors.border)}>
            <Icon className={cn("h-4 w-4", colors.text)} />
          </div>
          <div className="overflow-hidden">
            <span className="text-[10px] uppercase font-bold tracking-wider text-muted-foreground block truncate">
              {category}
            </span>
            <span className="text-xs font-semibold leading-tight truncate block" title={nodeData.label}>
              {nodeData.label}
            </span>
          </div>
        </div>

        {/* Status Badge */}
        <span
          className={cn(
            "text-[10px] font-medium px-2 py-0.5 rounded-full border whitespace-nowrap flex-shrink-0",
            statusStyle.badge
          )}
        >
          {statusStyle.label}
        </span>
      </div>

      {/* Sublabel / Context */}
      {nodeData.sublabel && (
        <div className="mb-2">
          <span className="inline-block text-[11px] font-mono px-1.5 py-0.5 rounded bg-muted/60 text-muted-foreground truncate max-w-full">
            {nodeData.sublabel}
          </span>
        </div>
      )}

      {/* Description */}
      {nodeData.description && (
        <p className="text-[11px] text-muted-foreground line-clamp-2 mb-2">
          {nodeData.description}
        </p>
      )}

      {/* Footer Metrics Row */}
      <div className="flex items-center justify-between text-[10px] text-muted-foreground border-t pt-2 mt-auto">
        <div className="flex items-center gap-2">
          {typeof nodeData.latencyMs === "number" && nodeData.latencyMs > 0 && (
            <span className="flex items-center gap-1 font-mono">
              <Clock className="h-3 w-3" />
              {nodeData.latencyMs}ms
            </span>
          )}
          {typeof nodeData.executionCount === "number" && nodeData.executionCount > 1 && (
            <span className="flex items-center gap-1 font-mono" title="Recovery attempts">
              <RotateCw className="h-3 w-3" />
              x{nodeData.executionCount}
            </span>
          )}
        </div>

        {/* Error Flag */}
        {nodeData.error && (
          <span
            className="flex items-center gap-1 text-destructive font-medium truncate max-w-[120px]"
            title={nodeData.error}
          >
            <AlertCircle className="h-3 w-3 flex-shrink-0" />
            <span className="truncate">Error</span>
          </span>
        )}

        {/* Verdict Badge for verification */}
        {nodeData.verdict && (
          <span
            className={cn(
              "font-mono font-bold px-1.5 py-0.2 rounded text-[9px]",
              nodeData.verdict === "PASS"
                ? "bg-emerald-500/10 text-emerald-600"
                : "bg-destructive/10 text-destructive"
            )}
          >
            {nodeData.verdict}
          </span>
        )}
      </div>

      {/* Source Handles */}
      <Handle
        type="source"
        position={Position.Bottom}
        className="w-2.5 h-2.5 !bg-muted-foreground border-2 border-background"
      />
      <Handle
        type="source"
        position={Position.Right}
        className="w-2.5 h-2.5 !bg-muted-foreground border-2 border-background"
      />
    </div>
  );
});

CustomNode.displayName = "CustomNode";
