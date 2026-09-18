/**
 * AI Workspace & Real-Time Orchestration Chat Page (/workspace)
 *
 * Primary user-facing AI workspace for JakeAI.
 * Exposes multi-agent orchestration, streaming, tool executions,
 * citations, and thread management.
 */

import { useState } from "react";
import { useWorkspaceChat } from "@/hooks/use-workspace-chat";
import { WorkspaceHeader } from "@/components/workspace/workspace-header";
import { ThreadList } from "@/components/workspace/thread-list";
import { ChatPanel } from "@/components/workspace/chat-panel";
import { Drawer } from "@/components/ui/drawer";

export default function WorkspacePage() {
  const {
    threads,
    activeThread,
    activeThreadId,
    messages,
    isStreaming,
    streamError,
    mascotState,
    selectedModel,
    sendMessage,
    stopGeneration,
    retryMessage,
    createThread,
    selectThread,
    deleteThread,
    clearThreadMessages,
    setSelectedModel,
  } = useWorkspaceChat();

  const [mobileSidebarOpen, setMobileSidebarOpen] = useState(false);

  return (
    <div className="flex flex-col h-[calc(100vh-6.5rem)] min-h-[550px] w-full rounded-xl border border-border bg-card shadow-sm overflow-hidden">
      {/* Top Bar: Workspace / Agent / Model */}
      <WorkspaceHeader
        selectedModel={selectedModel}
        onModelChange={setSelectedModel}
        mascotState={mascotState}
        isStreaming={isStreaming}
      />

      {/* Main Split Body: Conversations Sidebar + Chat / Execution */}
      <div className="flex flex-1 overflow-hidden min-h-0 relative">
        {/* Desktop Left Conversations Sidebar */}
        <div className="hidden md:flex h-full shrink-0">
          <ThreadList
            threads={threads}
            activeThreadId={activeThreadId}
            onSelectThread={selectThread}
            onCreateThread={() => createThread()}
            onDeleteThread={deleteThread}
            onClearThread={clearThreadMessages}
            isStreaming={isStreaming}
          />
        </div>

        {/* Mobile Slide-Out Conversations Drawer */}
        <Drawer
          open={mobileSidebarOpen}
          onOpenChange={setMobileSidebarOpen}
          position="left"
          className="p-0 w-72"
        >
          <div className="h-full flex flex-col pt-4">
            <ThreadList
              threads={threads}
              activeThreadId={activeThreadId}
              onSelectThread={(id) => {
                selectThread(id);
                setMobileSidebarOpen(false);
              }}
              onCreateThread={() => {
                createThread();
                setMobileSidebarOpen(false);
              }}
              onDeleteThread={deleteThread}
              onClearThread={clearThreadMessages}
              isStreaming={isStreaming}
            />
          </div>
        </Drawer>

        {/* Central Chat & Execution Panel */}
        <ChatPanel
          messages={messages}
          isStreaming={isStreaming}
          streamError={streamError}
          onSendMessage={sendMessage}
          onStopGeneration={stopGeneration}
          onRetryMessage={retryMessage}
          onToggleMobileSidebar={() => setMobileSidebarOpen(true)}
          activeThreadTitle={activeThread?.title}
        />
      </div>
    </div>
  );
}
