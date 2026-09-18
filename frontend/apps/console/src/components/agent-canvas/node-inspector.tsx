import * as React from "react";
import {
  X,
  Clock,
  ShieldCheck,
  AlertTriangle,
  FileText,
  Copy,
  Check,
  RotateCw,
  AlertCircle,
  Database,
} from "lucide-react";
import { Button } from "@/components/ui/button";
import { Badge } from "@/components/ui/badge";
import { cn } from "@/lib/utils";
import type { CanvasNodeData, CanvasNodeStatus } from "@/types/agent-graph";

interface NodeInspectorProps {
  nodeData: CanvasNodeData | null;
  onClose: () => void;
}

const STATUS_VARIANTS: Record<CanvasNodeStatus, { label: string; badge: string }> = {
  idle: { label: "Idle", badge: "bg-muted text-muted-foreground border-border" },
  queued: { label: "Queued", badge: "bg-amber-500/10 text-amber-600 dark:text-amber-400 border-amber-500/30" },
  running: { label: "Executing", badge: "bg-primary/20 text-primary border-primary/50 animate-pulse" },
  waiting_approval: { label: "Waiting Approval", badge: "bg-rose-500/20 text-rose-600 dark:text-rose-400 border-rose-500/50" },
  completed: { label: "Completed", badge: "bg-emerald-500/10 text-emerald-600 dark:text-emerald-400 border-emerald-500/30" },
  failed: { label: "Failed", badge: "bg-destructive/15 text-destructive border-destructive/30" },
  cancelled: { label: "Cancelled", badge: "bg-zinc-500/15 text-zinc-500 border-zinc-500/30" },
};

export const NodeInspector: React.FC<NodeInspectorProps> = ({ nodeData, onClose }) => {
  const [copied, setCopied] = React.useState(false);

  if (!nodeData) {
    return (
      <div className="flex flex-col h-full bg-card border-l w-80 flex-shrink-0 p-6 items-center justify-center text-center text-muted-foreground">
        <FileText className="h-8 w-8 mb-2 stroke-1 text-muted-foreground/60" />
        <p className="text-xs font-medium">Select a node in the canvas</p>
        <p className="text-[11px] text-muted-foreground/80 mt-1 max-w-[200px]">
          Inspect contract-approved parameters, execution status, verified outputs, and citations.
        </p>
      </div>
    );
  }

  const status = nodeData.status || "idle";
  const statusInfo = STATUS_VARIANTS[status] || STATUS_VARIANTS.idle;

  const handleCopyOutputs = () => {
    if (!nodeData.outputs) return;
    const text =
      typeof nodeData.outputs === "string"
        ? nodeData.outputs
        : JSON.stringify(nodeData.outputs, null, 2);
    navigator.clipboard.writeText(text);
    setCopied(true);
    setTimeout(() => setCopied(false), 2000);
  };

  // Filter sensitive fields from metadata strictly (Perimeter security & invariant)
  const safeMetadata = React.useMemo(() => {
    if (!nodeData.metadata) return null;
    const filtered: Record<string, unknown> = {};
    const forbiddenKeys = [
      "token",
      "obo_token",
      "raw_token",
      "api_key",
      "secret",
      "jwt",
      "authorization",
      "private",
      "chain_of_thought",
      "internal_prompt",
      "system_prompt",
    ];

    Object.entries(nodeData.metadata).forEach(([k, v]) => {
      const lower = k.toLowerCase();
      if (!forbiddenKeys.some((bad) => lower.includes(bad))) {
        filtered[k] = v;
      }
    });

    return Object.keys(filtered).length > 0 ? filtered : null;
  }, [nodeData.metadata]);

  return (
    <div
      className="flex flex-col h-full bg-card border-l w-88 md:w-96 flex-shrink-0 select-none overflow-hidden"
      data-testid="node-inspector-panel"
    >
      {/* Header */}
      <div className="p-4 border-b space-y-2.5">
        <div className="flex items-center justify-between">
          <div className="flex items-center gap-2">
            <span className="text-[10px] uppercase font-bold tracking-wider text-muted-foreground">
              {nodeData.category} Node
            </span>
            <Badge variant="outline" className={cn("text-[10px] px-2 py-0.5", statusInfo.badge)}>
              {statusInfo.label}
            </Badge>
          </div>
          <Button
            variant="ghost"
            size="icon"
            className="h-6 w-6 text-muted-foreground hover:text-foreground"
            onClick={onClose}
            aria-label="Close Inspector"
          >
            <X className="h-4 w-4" />
          </Button>
        </div>

        <div>
          <h2 className="text-sm font-bold truncate leading-tight" title={nodeData.label}>
            {nodeData.label}
          </h2>
          {nodeData.sublabel && (
            <span className="text-xs font-mono text-muted-foreground mt-0.5 block">
              {nodeData.sublabel}
            </span>
          )}
        </div>

        {nodeData.description && (
          <p className="text-xs text-muted-foreground leading-relaxed">
            {nodeData.description}
          </p>
        )}
      </div>

      {/* Content Scroll Area */}
      <div className="flex-1 overflow-y-auto p-4 space-y-4 text-xs">
        {/* Execution Metrics */}
        <div className="grid grid-cols-2 gap-2 p-2.5 rounded-lg bg-muted/40 border">
          <div>
            <span className="text-[10px] uppercase font-semibold text-muted-foreground block">
              Latency
            </span>
            <span className="text-xs font-mono font-medium flex items-center gap-1 mt-0.5">
              <Clock className="h-3 w-3 text-muted-foreground" />
              {typeof nodeData.latencyMs === "number" ? `${nodeData.latencyMs}ms` : "—"}
            </span>
          </div>

          <div>
            <span className="text-[10px] uppercase font-semibold text-muted-foreground block">
              Executions
            </span>
            <span className="text-xs font-mono font-medium flex items-center gap-1 mt-0.5">
              <RotateCw className="h-3 w-3 text-muted-foreground" />
              {nodeData.executionCount ? `x${nodeData.executionCount}` : "1"}
            </span>
          </div>
        </div>

        {/* Verification Verdict */}
        {nodeData.verdict && (
          <div className="p-3 rounded-lg border bg-muted/20 space-y-1.5">
            <div className="flex items-center justify-between">
              <span className="text-[10px] font-bold uppercase tracking-wider text-muted-foreground flex items-center gap-1.5">
                <ShieldCheck className="h-3.5 w-3.5 text-emerald-500" />
                Invariant Verification
              </span>
              <Badge
                variant={nodeData.verdict === "PASS" ? "default" : "destructive"}
                className="text-[10px] font-mono font-bold"
              >
                {nodeData.verdict}
              </Badge>
            </div>
            <p className="text-xs text-muted-foreground">
              Evaluated against mathematical balance invariants and tenant isolation boundary.
            </p>
          </div>
        )}

        {/* Human Approval Required Notice */}
        {nodeData.status === "waiting_approval" && (
          <div className="p-3 rounded-lg border border-rose-500/30 bg-rose-500/10 space-y-1.5">
            <div className="flex items-center gap-2 text-rose-600 dark:text-rose-400 font-semibold text-xs">
              <AlertTriangle className="h-4 w-4" />
              <span>Approval Gate Paused</span>
            </div>
            <p className="text-[11px] text-muted-foreground leading-normal">
              {nodeData.approvalReason || "Awaiting authorized operator approval before executing dangerous action."}
            </p>
            {nodeData.toolName && (
              <div className="text-[10px] font-mono bg-background/80 p-1.5 rounded border">
                Tool: <span className="font-semibold text-foreground">{nodeData.toolName}</span>
              </div>
            )}
          </div>
        )}

        {/* Errors */}
        {nodeData.error && (
          <div className="p-3 rounded-lg border border-destructive/40 bg-destructive/10 space-y-1.5">
            <div className="flex items-center gap-1.5 text-destructive font-semibold text-xs">
              <AlertCircle className="h-3.5 w-3.5" />
              <span>Step Execution Error</span>
            </div>
            <p className="text-xs text-destructive/90 font-mono break-all leading-normal">
              {nodeData.error}
            </p>
          </div>
        )}

        {/* Inputs / Parameters */}
        {nodeData.inputs && Object.keys(nodeData.inputs).length > 0 && (
          <div className="space-y-1.5">
            <span className="text-[10px] uppercase font-bold tracking-wider text-muted-foreground block">
              Contract Inputs
            </span>
            <div className="rounded-lg border bg-muted/30 p-2.5 max-h-48 overflow-y-auto font-mono text-[11px]">
              <pre className="whitespace-pre-wrap break-all">
                {JSON.stringify(nodeData.inputs, null, 2)}
              </pre>
            </div>
          </div>
        )}

        {/* Outputs / Observation */}
        {nodeData.outputs !== undefined && nodeData.outputs !== null && (
          <div className="space-y-1.5">
            <div className="flex items-center justify-between">
              <span className="text-[10px] uppercase font-bold tracking-wider text-muted-foreground">
                Execution Output
              </span>
              <Button
                variant="ghost"
                size="sm"
                className="h-5 px-1.5 text-[10px] text-muted-foreground"
                onClick={handleCopyOutputs}
              >
                {copied ? (
                  <>
                    <Check className="h-3 w-3 mr-1 text-emerald-500" /> Copied
                  </>
                ) : (
                  <>
                    <Copy className="h-3 w-3 mr-1" /> Copy
                  </>
                )}
              </Button>
            </div>
            <div className="rounded-lg border bg-muted/30 p-2.5 max-h-60 overflow-y-auto font-mono text-[11px]">
              <pre className="whitespace-pre-wrap break-all">
                {typeof nodeData.outputs === "string"
                  ? nodeData.outputs
                  : JSON.stringify(nodeData.outputs, null, 2)}
              </pre>
            </div>
          </div>
        )}

        {/* Grounded Citations */}
        {nodeData.citations && nodeData.citations.length > 0 && (
          <div className="space-y-2">
            <div className="flex items-center gap-1.5 text-muted-foreground">
              <Database className="h-3.5 w-3.5 text-teal-500" />
              <span className="text-[10px] uppercase font-bold tracking-wider">
                Grounded Citations ({nodeData.citations.length})
              </span>
            </div>
            <div className="space-y-1.5">
              {nodeData.citations.map((cite, idx) => (
                <div key={idx} className="p-2.5 rounded-lg border bg-muted/20 space-y-1">
                  <div className="flex items-center justify-between text-[11px] font-medium">
                    <span className="truncate text-foreground font-semibold">{cite.source}</span>
                    {typeof cite.confidence === "number" && (
                      <span className="text-[10px] font-mono text-muted-foreground">
                        {Math.round(cite.confidence * 100)}% match
                      </span>
                    )}
                  </div>
                  {cite.snippet && (
                    <p className="text-[11px] text-muted-foreground line-clamp-3 italic">
                      "{cite.snippet}"
                    </p>
                  )}
                </div>
              ))}
            </div>
          </div>
        )}

        {/* Safe Metadata */}
        {safeMetadata && (
          <div className="space-y-1.5 border-t pt-3">
            <span className="text-[10px] uppercase font-bold tracking-wider text-muted-foreground block">
              Node Metadata
            </span>
            <div className="rounded-lg border bg-muted/20 p-2 font-mono text-[10px] space-y-1">
              {Object.entries(safeMetadata).map(([k, v]) => (
                <div key={k} className="flex items-center justify-between">
                  <span className="text-muted-foreground">{k}:</span>
                  <span className="text-foreground truncate max-w-[160px]">
                    {typeof v === "object" ? JSON.stringify(v) : String(v)}
                  </span>
                </div>
              ))}
            </div>
          </div>
        )}
      </div>

      {/* Privacy Guard Notice */}
      <div className="p-3 border-t bg-muted/30 text-[10px] text-muted-foreground flex items-center justify-between">
        <span>Security Boundary: Confidential CoT Redacted</span>
        <ShieldCheck className="h-3.5 w-3.5 text-emerald-500" />
      </div>
    </div>
  );
};
