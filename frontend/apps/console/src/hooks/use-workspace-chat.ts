/**
 * Workspace Chat & Multi-Agent Orchestration Hook
 *
 * Manages:
 * - Tenant-partitioned conversation threads in localStorage
 * - Active thread message history and selection
 * - Real-time SSE streaming controller with lifecycle cleanup
 * - 6-stage canonical orchestration visibility (Planning, Agent selection, Retrieval, Tool execution, Verification, Final response)
 * - Citations and tool execution metadata
 * - Controlled model selection
 */

import { useState, useEffect, useCallback, useRef, useMemo } from "react";
import { useAuth } from "@/context/auth-context";
import { chatStreamService } from "@/api/services/chat-stream.service";
import type {
  WorkspaceThread,
  WorkspaceMessage,
  OrchestrationStep,
  OrchestrationPhase,
  Citation,
  ToolCallItem,
  TelemetryData,
  SSEStatusPayload,
  SSEToolCallPayload,
  SSETelemetryPayload,
  SSEDonePayload,
} from "@/types/chat";

const INITIAL_STEPS: Array<{ phase: OrchestrationPhase; title: string }> = [
  { phase: "planning", title: "Planning" },
  { phase: "agent_selection", title: "Agent selection" },
  { phase: "retrieval", title: "Retrieval" },
  { phase: "tool_execution", title: "Tool execution" },
  { phase: "verification", title: "Verification" },
  { phase: "final_response", title: "Final response" },
];

function createInitialSteps(): OrchestrationStep[] {
  return INITIAL_STEPS.map((step, idx) => ({
    id: `step-${idx}-${step.phase}`,
    phase: step.phase,
    title: step.title,
    status: "idle",
    timestamp: Date.now(),
  }));
}

export function useWorkspaceChat() {
  const { activeWorkspace } = useAuth();
  const tenantId = activeWorkspace?.id || "tenant_jakeai_core";
  const storageKey = `jakeai-threads-${tenantId}`;

  // Model & Provider Selection
  const [selectedModel, setSelectedModel] = useState<string>("gemini-1.5-flash");
  const [selectedProvider, setSelectedProvider] = useState<string>("gemini");

  // Threads State
  const [threads, setThreads] = useState<WorkspaceThread[]>(() => {
    try {
      const stored = localStorage.getItem(storageKey);
      if (stored) {
        const parsed = JSON.parse(stored) as WorkspaceThread[];
        if (Array.isArray(parsed) && parsed.length > 0) {
          return parsed;
        }
      }
    } catch {
      // Storage access blocked or parse error
    }

    const initialThreadId = `thread-${Date.now()}`;
    return [
      {
        id: initialThreadId,
        title: "New Conversation",
        createdAt: Date.now(),
        updatedAt: Date.now(),
        tenantId,
        messages: [],
      },
    ];
  });

  const [activeThreadId, setActiveThreadId] = useState<string>(() => {
    return threads[0]?.id || `thread-${Date.now()}`;
  });

  // Streaming & Execution State
  const [isStreaming, setIsStreaming] = useState<boolean>(false);
  const [mascotState, setMascotState] = useState<string>("idle");
  const [activeSteps, setActiveSteps] = useState<OrchestrationStep[]>(createInitialSteps);
  const [streamError, setStreamError] = useState<string | null>(null);

  // In-flight AbortController reference
  const abortControllerRef = useRef<AbortController | null>(null);

  // Sync threads to localStorage
  useEffect(() => {
    try {
      localStorage.setItem(storageKey, JSON.stringify(threads));
    } catch {
      // Storage quota or blocked
    }
  }, [threads, storageKey]);

  // Clean up streams on unmount or route change
  useEffect(() => {
    return () => {
      if (abortControllerRef.current) {
        abortControllerRef.current.abort();
        abortControllerRef.current = null;
      }
    };
  }, []);

  const activeThread = useMemo(() => {
    return (
      threads.find((t) => t.id === activeThreadId) ||
      threads[0] || {
        id: activeThreadId,
        title: "New Conversation",
        createdAt: Date.now(),
        updatedAt: Date.now(),
        tenantId,
        messages: [],
      }
    );
  }, [threads, activeThreadId, tenantId]);

  const messages = activeThread.messages;

  // Thread Operations
  const createThread = useCallback(
    (title = "New Conversation") => {
      if (abortControllerRef.current) {
        abortControllerRef.current.abort();
        abortControllerRef.current = null;
        setIsStreaming(false);
      }
      const newThread: WorkspaceThread = {
        id: `thread-${Date.now()}`,
        title,
        createdAt: Date.now(),
        updatedAt: Date.now(),
        tenantId,
        messages: [],
        model: selectedModel,
        provider: selectedProvider,
      };
      setThreads((prev) => [newThread, ...prev]);
      setActiveThreadId(newThread.id);
      setActiveSteps(createInitialSteps());
      setStreamError(null);
      setMascotState("idle");
      return newThread.id;
    },
    [tenantId, selectedModel, selectedProvider]
  );

  const selectThread = useCallback(
    (threadId: string) => {
      if (threadId === activeThreadId) return;
      if (abortControllerRef.current) {
        abortControllerRef.current.abort();
        abortControllerRef.current = null;
        setIsStreaming(false);
      }
      setActiveThreadId(threadId);
      setActiveSteps(createInitialSteps());
      setStreamError(null);
      setMascotState("idle");
    },
    [activeThreadId]
  );

  const deleteThread = useCallback(
    (threadId: string) => {
      if (abortControllerRef.current && activeThreadId === threadId) {
        abortControllerRef.current.abort();
        abortControllerRef.current = null;
        setIsStreaming(false);
      }
      setThreads((prev) => {
        const filtered = prev.filter((t) => t.id !== threadId);
        if (filtered.length === 0) {
          const fallback: WorkspaceThread = {
            id: `thread-${Date.now()}`,
            title: "New Conversation",
            createdAt: Date.now(),
            updatedAt: Date.now(),
            tenantId,
            messages: [],
          };
          setActiveThreadId(fallback.id);
          return [fallback];
        }
        if (activeThreadId === threadId) {
          setActiveThreadId(filtered[0].id);
        }
        return filtered;
      });
    },
    [activeThreadId, tenantId]
  );

  const clearThreadMessages = useCallback(
    (threadId?: string) => {
      const targetId = threadId || activeThreadId;
      if (abortControllerRef.current && activeThreadId === targetId) {
        abortControllerRef.current.abort();
        abortControllerRef.current = null;
        setIsStreaming(false);
      }
      setThreads((prev) =>
        prev.map((t) =>
          t.id === targetId ? { ...t, messages: [], updatedAt: Date.now() } : t
        )
      );
      setActiveSteps(createInitialSteps());
      setStreamError(null);
      setMascotState("idle");
    },
    [activeThreadId]
  );

  const renameThread = useCallback((threadId: string, newTitle: string) => {
    setThreads((prev) =>
      prev.map((t) =>
        t.id === threadId ? { ...t, title: newTitle, updatedAt: Date.now() } : t
      )
    );
  }, []);

  // Stop Generation
  const stopGeneration = useCallback(() => {
    if (abortControllerRef.current) {
      abortControllerRef.current.abort();
      abortControllerRef.current = null;
    }
    setIsStreaming(false);
    setMascotState("idle");
    setActiveSteps((prev) =>
      prev.map((s) => (s.status === "running" ? { ...s, status: "idle" } : s))
    );
  }, []);

  // Send Message & Stream Response
  const sendMessage = useCallback(
    async (content: string) => {
      const trimmed = content.trim();
      if (!trimmed || isStreaming) return;

      // Abort previous stream if any
      if (abortControllerRef.current) {
        abortControllerRef.current.abort();
      }
      const controller = new AbortController();
      abortControllerRef.current = controller;

      setStreamError(null);
      setIsStreaming(true);
      setMascotState("thinking");

      // Reset orchestration steps to running initial phase
      const initialSteps = createInitialSteps();
      initialSteps[0].status = "running"; // Planning active
      setActiveSteps(initialSteps);

      const userMsgId = `msg-user-${Date.now()}`;
      const userMessage: WorkspaceMessage = {
        id: userMsgId,
        role: "user",
        content: trimmed,
        createdAt: Date.now(),
        status: "completed",
      };

      const assistantMsgId = `msg-asst-${Date.now() + 1}`;
      const assistantMessage: WorkspaceMessage = {
        id: assistantMsgId,
        role: "assistant",
        content: "",
        createdAt: Date.now() + 1,
        status: "streaming",
        orchestrationSteps: [...initialSteps],
        toolCalls: [],
        citations: [],
        model: selectedModel,
      };

      // Auto-title thread if first message
      setThreads((prev) =>
        prev.map((t) => {
          if (t.id === activeThreadId) {
            const isFirst = t.messages.length === 0;
            const newTitle = isFirst
              ? trimmed.length > 32
                ? `${trimmed.substring(0, 32)}...`
                : trimmed
              : t.title;
            return {
              ...t,
              title: newTitle,
              updatedAt: Date.now(),
              messages: [...t.messages, userMessage, assistantMessage],
            };
          }
          return t;
        })
      );

      let accumulatedContent = "";
      const toolCallsList: ToolCallItem[] = [];
      let gatheredCitations: Citation[] = [];
      let telemetryData: TelemetryData | undefined;
      const currentSteps = [...initialSteps];

      const updateStep = (
        phase: OrchestrationPhase,
        status: "idle" | "running" | "completed" | "failed",
        details?: OrchestrationStep["details"],
        description?: string
      ) => {
        const stepIdx = currentSteps.findIndex((s) => s.phase === phase);
        if (stepIdx !== -1) {
          currentSteps[stepIdx] = {
            ...currentSteps[stepIdx],
            status,
            ...(details ? { details } : {}),
            ...(description ? { description } : {}),
          };
          setActiveSteps([...currentSteps]);
        }
      };

      const completePrecedingSteps = (targetPhase: OrchestrationPhase) => {
        const targetIdx = INITIAL_STEPS.findIndex((s) => s.phase === targetPhase);
        for (let i = 0; i < targetIdx; i++) {
          if (currentSteps[i].status === "running" || currentSteps[i].status === "idle") {
            currentSteps[i] = { ...currentSteps[i], status: "completed" };
          }
        }
        setActiveSteps([...currentSteps]);
      };

      try {
        await chatStreamService.streamChat({
          prompt: trimmed,
          conversationId: activeThreadId,
          model: selectedModel,
          provider: selectedProvider,
          signal: controller.signal,

          onStatus: (statusPayload: SSEStatusPayload) => {
            if (statusPayload.mascot_state) {
              setMascotState(statusPayload.mascot_state);
            }

            // Cache Hit Path
            if (statusPayload.phase === "cache_hit") {
              completePrecedingSteps("retrieval");
              updateStep("retrieval", "completed", undefined, "Retrieved from exact/semantic cache");
              updateStep("final_response", "running");
              return;
            }

            const node = statusPayload.node;
            const phase = statusPayload.phase;

            if (node === "supervisor" || phase === "routing" || phase === "re_routing") {
              updateStep("planning", "completed");
              updateStep("agent_selection", "running");
            } else if (node === "financial_specialist" || phase === "financial_analysis") {
              completePrecedingSteps("agent_selection");
              updateStep("agent_selection", "completed");
              updateStep("retrieval", "completed");
            } else if (node === "finnapigo_tool" || phase === "tool_execution" || phase === "tool_blocked") {
              completePrecedingSteps("tool_execution");
              updateStep("tool_execution", "running");
            } else if (node === "verifier" || phase === "critique" || phase === "verification_passed" || phase === "verification_failed") {
              completePrecedingSteps("verification");
              updateStep(
                "verification",
                phase === "verification_failed" ? "failed" : "running"
              );
            } else if (node === "synthesizer" || phase === "synthesizing") {
              completePrecedingSteps("final_response");
              updateStep("final_response", "running");
            }
          },

          onToolCall: (toolPayload: SSEToolCallPayload) => {
            updateStep("tool_execution", "running");
            if (Array.isArray(toolPayload.tool_calls)) {
              for (const tc of toolPayload.tool_calls) {
                const item: ToolCallItem = {
                  tool_name: tc.tool_name || tc.name || "Enterprise Tool",
                  status: (tc.status as ToolCallItem["status"]) || "SUCCESS",
                  reason: tc.reason,
                  arguments: tc.arguments,
                  result: tc.result,
                  duration_ms: tc.duration_ms,
                  timestamp: Date.now(),
                };
                toolCallsList.push(item);
              }
            } else if (toolPayload.name || toolPayload.tool) {
              toolCallsList.push({
                tool_name: String(toolPayload.name || toolPayload.tool),
                status: "SUCCESS",
                timestamp: Date.now(),
              });
            }

            // Sync tool calls to assistant message
            setThreads((prev) =>
              prev.map((t) => {
                if (t.id === activeThreadId) {
                  return {
                    ...t,
                    messages: t.messages.map((m) =>
                      m.id === assistantMsgId
                        ? { ...m, toolCalls: [...toolCallsList] }
                        : m
                    ),
                  };
                }
                return t;
              })
            );
          },

          onToken: (tokenDelta: string) => {
            accumulatedContent += tokenDelta;
            completePrecedingSteps("final_response");
            updateStep("final_response", "running");

            // Real-time delta update without artificial lag
            setThreads((prev) =>
              prev.map((t) => {
                if (t.id === activeThreadId) {
                  return {
                    ...t,
                    messages: t.messages.map((m) =>
                      m.id === assistantMsgId
                        ? {
                            ...m,
                            content: accumulatedContent,
                            orchestrationSteps: [...currentSteps],
                          }
                        : m
                    ),
                  };
                }
                return t;
              })
            );
          },

          onTelemetry: (telemetry: SSETelemetryPayload) => {
            telemetryData = {
              baseline_tokens: telemetry.baseline_tokens,
              billed_tokens: telemetry.billed_tokens,
              tokens_saved: telemetry.tokens_saved,
              reduction_rate: telemetry.reduction_rate,
              cache_hit: telemetry.cache_hit,
            };
          },

          onDone: (donePayload: SSEDonePayload) => {
            gatheredCitations = donePayload.citations || [];
            const finalMascot = donePayload.mascot_state || "success";
            setMascotState(finalMascot);

            // Mark all steps as completed
            currentSteps.forEach((s) => {
              s.status = "completed";
            });
            setActiveSteps([...currentSteps]);

            setThreads((prev) =>
              prev.map((t) => {
                if (t.id === activeThreadId) {
                  return {
                    ...t,
                    messages: t.messages.map((m) =>
                      m.id === assistantMsgId
                        ? {
                            ...m,
                            status: "completed",
                            content: accumulatedContent,
                            citations: gatheredCitations,
                            toolCalls: [...toolCallsList],
                            telemetry: telemetryData,
                            orchestrationSteps: [...currentSteps],
                            mascotState: finalMascot,
                            elapsedMs: donePayload.elapsed_ms,
                            model: donePayload.model || selectedModel,
                          }
                        : m
                    ),
                  };
                }
                return t;
              })
            );

            // Return mascot to idle after short celebration
            setTimeout(() => {
              setMascotState((curr) => (curr === finalMascot ? "idle" : curr));
            }, 3000);
          },

          onError: (err: Error) => {
            setMascotState("alert");
            setStreamError(err.message);

            // Mark in-flight step as failed
            const runningStep = currentSteps.find((s) => s.status === "running");
            if (runningStep) {
              runningStep.status = "failed";
            }
            setActiveSteps([...currentSteps]);

            setThreads((prev) =>
              prev.map((t) => {
                if (t.id === activeThreadId) {
                  return {
                    ...t,
                    messages: t.messages.map((m) =>
                      m.id === assistantMsgId
                        ? {
                            ...m,
                            status: "error",
                            error: err.message,
                            content: accumulatedContent || "Generation could not be completed.",
                            orchestrationSteps: [...currentSteps],
                            mascotState: "alert",
                          }
                        : m
                    ),
                  };
                }
                return t;
              })
            );
          },
        });
      } catch (execErr: unknown) {
        // Handled via onError
      } finally {
        setIsStreaming(false);
        abortControllerRef.current = null;
      }
    },
    [
      isStreaming,
      activeThreadId,
      selectedModel,
      selectedProvider,
    ]
  );

  // Retry last user message
  const retryMessage = useCallback(
    async (messageId?: string) => {
      const msgs = activeThread.messages;
      if (msgs.length === 0) return;

      let targetPrompt = "";
      if (messageId) {
        const found = msgs.find((m) => m.id === messageId);
        if (found && found.role === "user") {
          targetPrompt = found.content;
        }
      }

      if (!targetPrompt) {
        // Find last user message
        const lastUser = [...msgs].reverse().find((m) => m.role === "user");
        if (lastUser) {
          targetPrompt = lastUser.content;
        }
      }

      if (targetPrompt) {
        await sendMessage(targetPrompt);
      }
    },
    [activeThread.messages, sendMessage]
  );

  // Regenerate last response
  const regenerateResponse = useCallback(async () => {
    const msgs = activeThread.messages;
    const lastUser = [...msgs].reverse().find((m) => m.role === "user");
    if (lastUser) {
      await sendMessage(lastUser.content);
    }
  }, [activeThread.messages, sendMessage]);

  return {
    // State
    threads,
    activeThread,
    activeThreadId,
    messages,
    isStreaming,
    streamError,
    mascotState,
    activeSteps,
    selectedModel,
    selectedProvider,

    // Actions
    sendMessage,
    stopGeneration,
    retryMessage,
    regenerateResponse,
    createThread,
    selectThread,
    deleteThread,
    clearThreadMessages,
    renameThread,
    setSelectedModel: (model: string, provider?: string) => {
      setSelectedModel(model);
      if (provider) {
        setSelectedProvider(provider);
      }
    },
  };
}
