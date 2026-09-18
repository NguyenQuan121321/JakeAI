/**
 * Chat and AI Workspace Domain Types
 *
 * Strict models for JakeAI orchestration, streaming, citations,
 * tool executions, and conversation threads.
 */

export type ChatRole = "user" | "assistant" | "system";

export interface Citation {
  index: number;
  source: string;
  snippet: string;
  tenant_id: string;
  confidence: number;
  chunk_id?: string | null;
}

export interface ToolCallItem {
  tool_name: string;
  status: "SUCCESS" | "BLOCKED" | "ERROR" | "RUNNING";
  reason?: string;
  arguments?: Record<string, unknown>;
  result?: unknown;
  duration_ms?: number;
  timestamp?: number;
}

export interface TelemetryData {
  baseline_tokens: number;
  billed_tokens: number;
  tokens_saved: number;
  reduction_rate: number;
  cache_hit?: string;
}

export type OrchestrationPhase =
  | "planning"
  | "agent_selection"
  | "retrieval"
  | "tool_execution"
  | "verification"
  | "final_response";

export interface OrchestrationStep {
  id: string;
  phase: OrchestrationPhase;
  node?: string;
  title: string;
  description?: string;
  status: "idle" | "running" | "completed" | "failed" | "skipped";
  timestamp: number;
  mascot_state?: string;
  details?: {
    target_agent?: string;
    tool_name?: string;
    tool_status?: string;
    verdict?: string;
    chunks_count?: number;
    elapsed_ms?: number;
  };
}

export interface WorkspaceMessage {
  id: string;
  role: ChatRole;
  content: string;
  createdAt: number;
  status?: "idle" | "streaming" | "completed" | "error";
  error?: string;
  citations?: Citation[];
  toolCalls?: ToolCallItem[];
  orchestrationSteps?: OrchestrationStep[];
  telemetry?: TelemetryData;
  mascotState?: string;
  model?: string;
  elapsedMs?: number;
}

export interface WorkspaceThread {
  id: string;
  title: string;
  createdAt: number;
  updatedAt: number;
  tenantId: string;
  messages: WorkspaceMessage[];
  model?: string;
  provider?: string;
}

// Raw Backend SSE Data Contracts
export interface SSEStatusPayload {
  phase?: string;
  node?: string;
  conversation_id?: string;
  tenant_id?: string;
  user_id?: string;
  mascot_state?: string;
  message?: string;
  timestamp?: number;
}

export interface SSETokenPayload {
  delta?: string;
  token?: string;
  content?: string;
  conversation_id?: string;
}

export interface SSEToolCallPayload {
  node?: string;
  tool_calls?: Array<{
    tool_name?: string;
    status?: string;
    reason?: string;
    arguments?: Record<string, unknown>;
    result?: unknown;
    duration_ms?: number;
    name?: string;
  }>;
  name?: string;
  tool?: string;
}

export interface SSETelemetryPayload {
  baseline_tokens: number;
  billed_tokens: number;
  tokens_saved: number;
  reduction_rate: number;
  cache_hit?: string;
}

export interface SSEDonePayload {
  conversation_id: string;
  tenant_id: string;
  elapsed_ms: number;
  mascot_state?: string;
  citations?: Citation[];
  cache_hit?: string;
  model?: string;
}

export interface SSEErrorPayload {
  conversation_id?: string;
  error?: string;
  detail?: string;
  mascot_state?: string;
}

export interface StreamChatRequestOptions {
  prompt: string;
  conversationId: string;
  model?: string;
  provider?: string;
  signal?: AbortSignal;
  onStatus?: (status: SSEStatusPayload) => void;
  onToken?: (tokenDelta: string) => void;
  onToolCall?: (toolPayload: SSEToolCallPayload) => void;
  onTelemetry?: (telemetry: SSETelemetryPayload) => void;
  onDone?: (done: SSEDonePayload) => void;
  onError?: (error: Error) => void;
}
