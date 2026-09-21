/**
 * Workspace Conversations / Thread List Component
 *
 * Provides conversation thread switching, creation, deletion,
 * and clear messages action.
 */

import { useState } from "react";
import { Plus, MessageSquare, Trash2, Eraser, Search } from "lucide-react";
import { Button } from "@/components/ui/button";
import { Input } from "@/components/ui/input";
import { cn } from "@/lib/utils";
import type { WorkspaceThread } from "@/types/chat";

interface ThreadListProps {
  threads: WorkspaceThread[];
  activeThreadId: string;
  onSelectThread: (threadId: string) => void;
  onCreateThread: () => void;
  onDeleteThread: (threadId: string) => void;
  onClearThread: (threadId: string) => void;
  isStreaming?: boolean;
}

export function ThreadList({
  threads,
  activeThreadId,
  onSelectThread,
  onCreateThread,
  onDeleteThread,
  onClearThread,
  isStreaming = false,
}: ThreadListProps) {
  const [searchQuery, setSearchQuery] = useState("");

  const filteredThreads = threads.filter((t) =>
    t.title.toLowerCase().includes(searchQuery.toLowerCase())
  );

  return (
    <div className="flex h-full flex-col bg-muted/20 border-r border-border w-full md:w-64 lg:w-72 shrink-0">
      {/* Header & New Chat Button */}
      <div className="p-3 border-b border-border space-y-2">
        <Button
          onClick={onCreateThread}
          disabled={isStreaming}
          className="w-full justify-start space-x-2"
          size="sm"
        >
          <Plus className="h-4 w-4" />
          <span>New Conversation</span>
        </Button>

        {threads.length > 3 && (
          <div className="relative">
            <Search className="absolute left-2.5 top-2.5 h-3.5 w-3.5 text-muted-foreground" />
            <Input
              type="text"
              placeholder="Search conversations..."
              value={searchQuery}
              onChange={(e) => setSearchQuery(e.target.value)}
              className="pl-8 h-8 text-xs"
            />
          </div>
        )}
      </div>

      {/* Conversations Scroll Area */}
      <div className="flex-1 overflow-y-auto p-2 space-y-1">
        {filteredThreads.length === 0 ? (
          <div className="py-8 text-center text-xs text-muted-foreground">
            No conversations found
          </div>
        ) : (
          filteredThreads.map((thread) => {
            const isActive = thread.id === activeThreadId;
            return (
              <div
                key={thread.id}
                onClick={() => onSelectThread(thread.id)}
                className={cn(
                  "group relative flex items-center justify-between rounded-lg px-3 py-2.5 text-xs font-medium cursor-pointer transition-colors",
                  isActive
                    ? "bg-primary/10 text-primary font-semibold"
                    : "text-foreground hover:bg-muted/60"
                )}
                role="button"
                tabIndex={0}
                aria-pressed={isActive}
                onKeyDown={(e) => {
                  if (e.key === "Enter" || e.key === " ") {
                    onSelectThread(thread.id);
                  }
                }}
              >
                <div className="flex items-center space-x-2.5 min-w-0 flex-1 pr-2">
                  <MessageSquare
                    className={cn(
                      "h-4 w-4 shrink-0",
                      isActive ? "text-primary" : "text-muted-foreground"
                    )}
                  />
                  <div className="truncate">
                    <p className="truncate leading-tight">{thread.title}</p>
                    <span className="text-[10px] text-muted-foreground font-normal">
                      {thread.messages.length} messages
                    </span>
                  </div>
                </div>

                {/* Delete Thread Action */}
                <button
                  type="button"
                  onClick={(e) => {
                    e.stopPropagation();
                    onDeleteThread(thread.id);
                  }}
                  title="Delete conversation"
                  aria-label={`Delete conversation ${thread.title}`}
                  className="opacity-0 group-hover:opacity-100 p-1 hover:text-destructive rounded transition-opacity"
                >
                  <Trash2 className="h-3.5 w-3.5" />
                </button>
              </div>
            );
          })
        )}
      </div>

      {/* Footer Clear Conversation */}
      <div className="p-2 border-t border-border">
        <Button
          variant="ghost"
          size="sm"
          onClick={() => onClearThread(activeThreadId)}
          disabled={isStreaming}
          className="w-full justify-start text-xs text-muted-foreground hover:text-destructive space-x-2 h-8"
        >
          <Eraser className="h-3.5 w-3.5" />
          <span>Clear Active Thread</span>
        </Button>
      </div>
    </div>
  );
}
