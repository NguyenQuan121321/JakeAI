/**
 * Chat Composer Input Component
 *
 * Provides expandable multiline input, keyboard shortcuts (Enter to send,
 * Shift+Enter for newline, Esc to cancel), send button, and stop generation button.
 */

import React, { useState, useRef, useEffect } from "react";
import { Send, Square } from "lucide-react";
import { Button } from "@/components/ui/button";
import { cn } from "@/lib/utils";

interface ComposerProps {
  onSendMessage: (content: string) => void;
  onStopGeneration: () => void;
  isStreaming: boolean;
  disabled?: boolean;
  placeholder?: string;
}

export function Composer({
  onSendMessage,
  onStopGeneration,
  isStreaming,
  disabled = false,
  placeholder = "Ask JakeAI anything (e.g. analyze EBITDA, query tools, verify RAG)...",
}: ComposerProps) {
  const [content, setContent] = useState<string>("");
  const textareaRef = useRef<HTMLTextAreaElement>(null);

  // Auto-resize textarea height
  useEffect(() => {
    if (textareaRef.current) {
      textareaRef.current.style.height = "auto";
      textareaRef.current.style.height = `${Math.min(
        textareaRef.current.scrollHeight,
        200
      )}px`;
    }
  }, [content]);

  const handleSend = () => {
    const trimmed = content.trim();
    if (!trimmed || isStreaming || disabled) return;
    onSendMessage(trimmed);
    setContent("");
    if (textareaRef.current) {
      textareaRef.current.style.height = "auto";
    }
  };

  const handleKeyDown = (e: React.KeyboardEvent<HTMLTextAreaElement>) => {
    if (e.key === "Enter" && !e.shiftKey) {
      e.preventDefault();
      handleSend();
    } else if (e.key === "Escape" && isStreaming) {
      e.preventDefault();
      onStopGeneration();
    }
  };

  return (
    <div className="relative rounded-2xl border border-border bg-card/80 p-2 shadow-sm backdrop-blur-sm focus-within:border-primary/50 focus-within:ring-2 focus-within:ring-primary/20 transition-all">
      <textarea
        ref={textareaRef}
        value={content}
        onChange={(e) => setContent(e.target.value)}
        onKeyDown={handleKeyDown}
        disabled={disabled}
        placeholder={placeholder}
        rows={1}
        className={cn(
          "w-full resize-none border-0 bg-transparent px-3 py-2 text-sm text-foreground placeholder:text-muted-foreground focus:outline-none disabled:cursor-not-allowed disabled:opacity-50 max-h-48 min-h-[44px]"
        )}
      />

      <div className="flex items-center justify-between pt-1 px-1 border-t border-border/40">
        <div className="flex items-center space-x-2 text-[11px] text-muted-foreground">
          <span className="hidden sm:inline">
            <kbd className="rounded bg-muted px-1.5 py-0.5 text-[10px] font-mono text-muted-foreground border border-border">
              Enter
            </kbd>{" "}
            to send
          </span>
          <span className="hidden sm:inline opacity-40">&bull;</span>
          <span className="hidden sm:inline">
            <kbd className="rounded bg-muted px-1.5 py-0.5 text-[10px] font-mono text-muted-foreground border border-border">
              Shift+Enter
            </kbd>{" "}
            for new line
          </span>
        </div>

        <div className="flex items-center space-x-1.5">
          {isStreaming ? (
            <Button
              type="button"
              variant="destructive"
              size="sm"
              onClick={onStopGeneration}
              className="h-8 px-3 text-xs space-x-1.5 rounded-lg shadow-sm"
              title="Stop generating response (Esc)"
            >
              <Square className="h-3.5 w-3.5 fill-current" />
              <span>Stop</span>
            </Button>
          ) : (
            <Button
              type="button"
              size="sm"
              onClick={handleSend}
              disabled={!content.trim() || disabled}
              className="h-8 px-3 text-xs space-x-1.5 rounded-lg shadow-sm"
              title="Send message"
            >
              <span>Send</span>
              <Send className="h-3.5 w-3.5" />
            </Button>
          )}
        </div>
      </div>
    </div>
  );
}
