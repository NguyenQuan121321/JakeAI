/**
 * Tool Execution Activity Card
 *
 * Displays tool execution telemetry, status (SUCCESS, BLOCKED, ERROR),
 * duration, and security guardrail verdicts.
 */

import { Wrench, CheckCircle2, AlertTriangle, XCircle, Loader2 } from "lucide-react";
import { Badge } from "@/components/ui/badge";
import { cn } from "@/lib/utils";
import type { ToolCallItem } from "@/types/chat";

interface ToolActivityCardProps {
  toolCall: ToolCallItem;
  className?: string;
}

export function ToolActivityCard({ toolCall, className }: ToolActivityCardProps) {
  const isBlocked = toolCall.status === "BLOCKED";
  const isSuccess = toolCall.status === "SUCCESS";
  const isError = toolCall.status === "ERROR";
  const isRunning = toolCall.status === "RUNNING";

  return (
    <div
      className={cn(
        "rounded-lg border p-2.5 text-xs transition-colors",
        isBlocked
          ? "border-destructive/30 bg-destructive/5 text-destructive"
          : isSuccess
          ? "border-emerald-500/20 bg-emerald-500/5 text-foreground"
          : isError
          ? "border-amber-500/30 bg-amber-500/5 text-foreground"
          : "border-border bg-card/60 text-foreground",
        className
      )}
    >
      <div className="flex items-center justify-between gap-2">
        <div className="flex items-center space-x-2 truncate">
          {isRunning ? (
            <Loader2 className="h-3.5 w-3.5 animate-spin text-primary shrink-0" />
          ) : isBlocked ? (
            <AlertTriangle className="h-3.5 w-3.5 text-destructive shrink-0" />
          ) : isSuccess ? (
            <CheckCircle2 className="h-3.5 w-3.5 text-emerald-500 shrink-0" />
          ) : isError ? (
            <XCircle className="h-3.5 w-3.5 text-amber-500 shrink-0" />
          ) : (
            <Wrench className="h-3.5 w-3.5 text-muted-foreground shrink-0" />
          )}

          <span className="font-semibold truncate">{toolCall.tool_name}</span>
        </div>

        <div className="flex items-center space-x-1.5 shrink-0">
          {toolCall.duration_ms !== undefined && (
            <span className="text-[10px] text-muted-foreground">
              {Math.round(toolCall.duration_ms)}ms
            </span>
          )}
          <Badge
            variant={isBlocked || isError ? "destructive" : isSuccess ? "default" : "outline"}
            className={cn(
              "text-[10px] px-1.5 py-0 uppercase font-mono tracking-wider",
              isSuccess && "bg-emerald-600 hover:bg-emerald-600 text-white"
            )}
          >
            {toolCall.status}
          </Badge>
        </div>
      </div>

      {/* Blocked or Error details */}
      {isBlocked && toolCall.reason && (
        <p className="mt-1 text-[11px] text-destructive/90 font-medium leading-relaxed">
          Access Denied: {toolCall.reason}
        </p>
      )}

      {isError && toolCall.reason && (
        <p className="mt-1 text-[11px] text-amber-600 dark:text-amber-400 font-medium leading-relaxed">
          Error: {toolCall.reason}
        </p>
      )}
    </div>
  );
}
