/**
 * Compact Orchestration Execution Visibility Panel
 *
 * Visualizes the 6 canonical backend multi-agent pipeline stages:
 * 1. Planning
 * 2. Agent selection
 * 3. Retrieval
 * 4. Tool execution
 * 5. Verification
 * 6. Final response
 *
 * SECURITY INVARIANT:
 * Never displays internal reasoning, private chain-of-thought, or system prompts.
 * Exposes only verified execution metadata and approved events.
 */

import { useState } from "react";
import {
  CheckCircle2,
  Loader2,
  Circle,
  AlertCircle,
  ChevronDown,
  ChevronUp,
  Cpu,
  Zap,
} from "lucide-react";
import { cn } from "@/lib/utils";
import type { OrchestrationStep, TelemetryData } from "@/types/chat";

interface OrchestrationPanelProps {
  steps: OrchestrationStep[];
  isStreaming?: boolean;
  telemetry?: TelemetryData;
  elapsedMs?: number;
  className?: string;
}

export function OrchestrationPanel({
  steps,
  isStreaming = false,
  telemetry,
  elapsedMs,
  className,
}: OrchestrationPanelProps) {
  const [isExpanded, setIsExpanded] = useState<boolean>(false);

  // If no steps, nothing to render
  if (!steps || steps.length === 0) return null;

  const runningStep = steps.find((s) => s.status === "running");
  const failedStep = steps.find((s) => s.status === "failed");
  const completedCount = steps.filter((s) => s.status === "completed").length;

  return (
    <div
      className={cn(
        "rounded-lg border border-border/80 bg-muted/30 p-2.5 text-xs transition-all",
        className
      )}
    >
      {/* Summary Header */}
      <div className="flex items-center justify-between gap-2">
        <div className="flex items-center space-x-2">
          <Cpu className="h-4 w-4 text-primary shrink-0" />
          <span className="font-semibold text-foreground">Multi-Agent Orchestration</span>

          {isStreaming ? (
            <span className="inline-flex items-center space-x-1 text-primary font-medium">
              <Loader2 className="h-3 w-3 animate-spin" />
              <span className="text-[11px] truncate">
                {runningStep ? runningStep.title : "Processing..."}
              </span>
            </span>
          ) : failedStep ? (
            <span className="text-destructive font-medium text-[11px] flex items-center space-x-1">
              <AlertCircle className="h-3 w-3" />
              <span>Failed at {failedStep.title}</span>
            </span>
          ) : (
            <span className="text-muted-foreground text-[11px] flex items-center space-x-1">
              <CheckCircle2 className="h-3 w-3 text-emerald-500" />
              <span>
                {completedCount}/{steps.length} stages verified
              </span>
              {elapsedMs !== undefined && (
                <span className="opacity-75">({(elapsedMs / 1000).toFixed(2)}s)</span>
              )}
            </span>
          )}
        </div>

        <div className="flex items-center space-x-2">
          {telemetry && telemetry.tokens_saved > 0 && (
            <div className="hidden sm:flex items-center space-x-1 text-[11px] text-emerald-600 dark:text-emerald-400 font-medium bg-emerald-500/10 px-2 py-0.5 rounded-full">
              <Zap className="h-3 w-3" />
              <span>{telemetry.tokens_saved} tokens saved</span>
            </div>
          )}

          <button
            type="button"
            onClick={() => setIsExpanded((prev) => !prev)}
            className="text-muted-foreground hover:text-foreground p-1 rounded transition-colors"
            aria-label={isExpanded ? "Collapse orchestration steps" : "Expand orchestration steps"}
          >
            {isExpanded ? <ChevronUp className="h-3.5 w-3.5" /> : <ChevronDown className="h-3.5 w-3.5" />}
          </button>
        </div>
      </div>

      {/* Horizontal Pipeline Steps Summary */}
      <div className="mt-2.5 grid grid-cols-2 sm:grid-cols-3 md:grid-cols-6 gap-1.5">
        {steps.map((step) => {
          const isDone = step.status === "completed";
          const isCurr = step.status === "running";
          const isErr = step.status === "failed";

          return (
            <div
              key={step.id}
              className={cn(
                "flex items-center space-x-1.5 rounded-md px-2 py-1.5 text-[11px] font-medium border transition-colors",
                isCurr
                  ? "border-primary/40 bg-primary/10 text-primary shadow-sm"
                  : isDone
                  ? "border-emerald-500/20 bg-emerald-500/5 text-muted-foreground"
                  : isErr
                  ? "border-destructive/30 bg-destructive/5 text-destructive"
                  : "border-border/40 bg-background/50 text-muted-foreground/60"
              )}
            >
              {isCurr ? (
                <Loader2 className="h-3 w-3 animate-spin text-primary shrink-0" />
              ) : isDone ? (
                <CheckCircle2 className="h-3 w-3 text-emerald-500 shrink-0" />
              ) : isErr ? (
                <AlertCircle className="h-3 w-3 text-destructive shrink-0" />
              ) : (
                <Circle className="h-2.5 w-2.5 opacity-40 shrink-0" />
              )}
              <span className="truncate">{step.title}</span>
            </div>
          );
        })}
      </div>

      {/* Expandable Verification & Execution Metadata */}
      {isExpanded && (
        <div className="mt-3 pt-2.5 border-t border-border/60 space-y-1.5 text-[11px] text-muted-foreground">
          <div className="flex flex-wrap items-center justify-between gap-2">
            <span>Pipeline Architecture:</span>
            <span className="font-mono text-foreground font-medium">
              LangGraph Multi-Agent Kernel (Supervisor &bull; Specialist &bull; Verifier &bull; Synthesizer)
            </span>
          </div>

          {telemetry && (
            <div className="flex flex-wrap items-center justify-between gap-2 pt-1">
              <span>Token Accounting & Cache:</span>
              <span className="font-mono text-foreground">
                Baseline: {telemetry.baseline_tokens} &bull; Billed: {telemetry.billed_tokens} &bull; Savings: {(telemetry.reduction_rate * 100).toFixed(1)}%
              </span>
            </div>
          )}
        </div>
      )}
    </div>
  );
}
