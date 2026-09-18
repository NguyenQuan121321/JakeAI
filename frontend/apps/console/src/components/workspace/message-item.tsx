/**
 * Chat Message Item Component
 *
 * Renders user prompts, streamed assistant responses,
 * orchestration pipeline status, tool executions, and verifiable citations.
 */

import { useState } from "react";
import { User, Bot, Copy, Check, RotateCcw, AlertTriangle } from "lucide-react";
import { Badge } from "@/components/ui/badge";
import { Button } from "@/components/ui/button";
import { OrchestrationPanel } from "./orchestration-panel";
import { ToolActivityCard } from "./tool-activity-card";
import { CitationShelf } from "./citation-shelf";
import { cn } from "@/lib/utils";
import type { WorkspaceMessage } from "@/types/chat";

interface MessageItemProps {
  message: WorkspaceMessage;
  onRetry?: (messageId: string) => void;
  isLastAssistant?: boolean;
}

export function MessageItem({
  message,
  onRetry,
  isLastAssistant = false,
}: MessageItemProps) {
  const [copied, setCopied] = useState<boolean>(false);
  const isUser = message.role === "user";
  const isStreaming = message.status === "streaming";
  const isError = message.status === "error";

  const handleCopy = () => {
    if (!message.content) return;
    navigator.clipboard.writeText(message.content);
    setCopied(true);
    setTimeout(() => setCopied(false), 2000);
  };

  return (
    <div
      className={cn(
        "flex w-full space-x-3 py-4 text-sm transition-colors",
        isUser ? "bg-transparent justify-end" : "bg-card/40 border-y border-border/40"
      )}
    >
      <div
        className={cn(
          "flex w-full space-x-3 max-w-4xl px-4 sm:px-6",
          isUser && "justify-end"
        )}
      >
        {/* Assistant Avatar */}
        {!isUser && (
          <div className="flex h-8 w-8 shrink-0 select-none items-center justify-center rounded-lg bg-primary/10 text-primary border border-primary/20">
            <Bot className="h-4 w-4" />
          </div>
        )}

        {/* Message Content & Shell */}
        <div
          className={cn(
            "flex-1 space-y-2 min-w-0",
            isUser ? "max-w-xl text-right" : "text-left"
          )}
        >
          {/* Header Metadata */}
          <div
            className={cn(
              "flex items-center space-x-2 text-xs text-muted-foreground",
              isUser && "justify-end"
            )}
          >
            <span className="font-semibold text-foreground">
              {isUser ? "You" : "JakeAI Assistant"}
            </span>

            {!isUser && message.model && (
              <Badge variant="outline" className="text-[10px] py-0 px-1.5 font-mono">
                {message.model}
              </Badge>
            )}

            <span className="text-[11px] opacity-60">
              {new Date(message.createdAt).toLocaleTimeString([], {
                hour: "2-digit",
                minute: "2-digit",
              })}
            </span>
          </div>

          {/* User Message Bubble */}
          {isUser ? (
            <div className="inline-block rounded-2xl rounded-tr-sm bg-primary px-4 py-2.5 text-primary-foreground text-left shadow-sm">
              <p className="whitespace-pre-wrap break-words leading-relaxed">
                {message.content}
              </p>
            </div>
          ) : (
            /* Assistant Message Flow */
            <div className="space-y-3">
              {/* Orchestration Panel for Assistant */}
              {message.orchestrationSteps && message.orchestrationSteps.length > 0 && (
                <OrchestrationPanel
                  steps={message.orchestrationSteps}
                  isStreaming={isStreaming}
                  telemetry={message.telemetry}
                  elapsedMs={message.elapsedMs}
                />
              )}

              {/* Tool Execution Cards */}
              {message.toolCalls && message.toolCalls.length > 0 && (
                <div className="space-y-1.5">
                  {message.toolCalls.map((tc, idx) => (
                    <ToolActivityCard key={`${tc.tool_name}-${idx}`} toolCall={tc} />
                  ))}
                </div>
              )}

              {/* Message Content */}
              {message.content && (
                <div className="text-foreground leading-relaxed whitespace-pre-wrap break-words font-normal">
                  {message.content}
                  {/* Blinking streaming cursor */}
                  {isStreaming && (
                    <span
                      className="inline-block w-1.5 h-4 ml-1 bg-primary align-middle animate-pulse"
                      aria-hidden="true"
                    />
                  )}
                </div>
              )}

              {/* Error State Banner */}
              {isError && (
                <div className="rounded-lg border border-destructive/30 bg-destructive/10 p-3 text-xs text-destructive space-y-2">
                  <div className="flex items-center space-x-2 font-semibold">
                    <AlertTriangle className="h-4 w-4 shrink-0" />
                    <span>Generation Encountered an Issue</span>
                  </div>
                  <p className="text-destructive/90">{message.error || "Execution failed."}</p>
                  {onRetry && (
                    <Button
                      size="sm"
                      variant="outline"
                      onClick={() => onRetry(message.id)}
                      className="border-destructive/30 text-destructive hover:bg-destructive/20 h-7 text-xs space-x-1.5"
                    >
                      <RotateCcw className="h-3 w-3" />
                      <span>Retry Request</span>
                    </Button>
                  )}
                </div>
              )}

              {/* Grounded Citations Shelf */}
              {message.citations && message.citations.length > 0 && (
                <CitationShelf citations={message.citations} />
              )}

              {/* Actions Footer */}
              {!isStreaming && !isError && message.content && (
                <div className="flex items-center space-x-2 pt-1 text-xs text-muted-foreground">
                  <button
                    type="button"
                    onClick={handleCopy}
                    className="inline-flex items-center space-x-1 hover:text-foreground py-0.5 px-1.5 rounded transition-colors"
                    title="Copy message"
                    aria-label="Copy message content"
                  >
                    {copied ? (
                      <>
                        <Check className="h-3 w-3 text-emerald-500" />
                        <span className="text-[10px] text-emerald-500">Copied</span>
                      </>
                    ) : (
                      <>
                        <Copy className="h-3 w-3" />
                        <span className="text-[10px]">Copy</span>
                      </>
                    )}
                  </button>

                  {isLastAssistant && onRetry && (
                    <button
                      type="button"
                      onClick={() => onRetry(message.id)}
                      className="inline-flex items-center space-x-1 hover:text-foreground py-0.5 px-1.5 rounded transition-colors"
                      title="Regenerate response"
                      aria-label="Regenerate response"
                    >
                      <RotateCcw className="h-3 w-3" />
                      <span className="text-[10px]">Regenerate</span>
                    </button>
                  )}
                </div>
              )}
            </div>
          )}
        </div>

        {/* User Avatar */}
        {isUser && (
          <div className="flex h-8 w-8 shrink-0 select-none items-center justify-center rounded-lg bg-muted text-muted-foreground border border-border">
            <User className="h-4 w-4" />
          </div>
        )}
      </div>
    </div>
  );
}
