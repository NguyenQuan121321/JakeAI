/**
 * Chat Panel Component
 *
 * Hosts the central conversation messages stream, auto-scrolling container,
 * empty state, and bottom composer.
 */

import { useRef, useEffect } from "react";
import { Menu, AlertCircle } from "lucide-react";
import { MessageItem } from "./message-item";
import { Composer } from "./composer";
import { WorkspaceEmptyState } from "./workspace-empty-state";
import { Button } from "@/components/ui/button";
import type { WorkspaceMessage } from "@/types/chat";

interface ChatPanelProps {
  messages: WorkspaceMessage[];
  isStreaming: boolean;
  streamError?: string | null;
  onSendMessage: (content: string) => void;
  onStopGeneration: () => void;
  onRetryMessage: (messageId: string) => void;
  onToggleMobileSidebar?: () => void;
  activeThreadTitle?: string;
}

export function ChatPanel({
  messages,
  isStreaming,
  streamError,
  onSendMessage,
  onStopGeneration,
  onRetryMessage,
  onToggleMobileSidebar,
  activeThreadTitle,
}: ChatPanelProps) {
  const scrollRef = useRef<HTMLDivElement>(null);

  // Auto-scroll to bottom on new messages or streaming tokens
  useEffect(() => {
    if (scrollRef.current) {
      scrollRef.current.scrollTop = scrollRef.current.scrollHeight;
    }
  }, [messages, isStreaming]);

  const lastAssistantIndex = messages
    .map((m, idx) => ({ role: m.role, idx }))
    .reverse()
    .find((m) => m.role === "assistant")?.idx;

  return (
    <div className="flex flex-1 flex-col h-full overflow-hidden bg-background relative">
      {/* Mobile Thread Drawer Toggle Bar */}
      <div className="flex md:hidden items-center justify-between px-4 py-2 border-b border-border bg-muted/40 text-xs">
        <Button
          variant="ghost"
          size="sm"
          onClick={onToggleMobileSidebar}
          className="h-7 px-2 text-xs space-x-1.5"
        >
          <Menu className="h-3.5 w-3.5" />
          <span>Conversations</span>
        </Button>
        <span className="font-semibold text-foreground truncate max-w-[200px]">
          {activeThreadTitle || "Chat"}
        </span>
      </div>

      {/* Messages Scroll Area */}
      <div
        ref={scrollRef}
        className="flex-1 overflow-y-auto divide-y divide-border/20 scroll-smooth"
        role="log"
        aria-live="polite"
      >
        {messages.length === 0 ? (
          <WorkspaceEmptyState
            onSelectPrompt={onSendMessage}
            isStreaming={isStreaming}
          />
        ) : (
          messages.map((msg, index) => (
            <MessageItem
              key={msg.id}
              message={msg}
              onRetry={onRetryMessage}
              isLastAssistant={index === lastAssistantIndex}
            />
          ))
        )}
      </div>

      {/* Stream Error Alert Banner */}
      {streamError && (
        <div className="mx-4 mb-2 flex items-center justify-between rounded-lg border border-destructive/30 bg-destructive/10 px-3 py-2 text-xs text-destructive">
          <div className="flex items-center space-x-2">
            <AlertCircle className="h-4 w-4 shrink-0" />
            <span>{streamError}</span>
          </div>
          <Button
            size="sm"
            variant="ghost"
            onClick={() => {
              const lastUser = [...messages].reverse().find((m) => m.role === "user");
              if (lastUser) onSendMessage(lastUser.content);
            }}
            className="h-6 text-xs text-destructive hover:bg-destructive/20 hover:text-destructive"
          >
            Retry
          </Button>
        </div>
      )}

      {/* Bottom Composer Container */}
      <div className="p-3 sm:p-4 border-t border-border bg-background/80 backdrop-blur-sm">
        <div className="max-w-4xl mx-auto">
          <Composer
            onSendMessage={onSendMessage}
            onStopGeneration={onStopGeneration}
            isStreaming={isStreaming}
          />
        </div>
      </div>
    </div>
  );
}
