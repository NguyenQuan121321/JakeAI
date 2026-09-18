/**
 * JakeAI Agent Platform Service
 *
 * Covers tasks, autonomous execution runs, approval gates, and runtime telemetry.
 */

import { apiClient } from "../client/http-client";
import type {
  TaskState,
  CreateTaskRequest,
  RunState,
  CreateRunRequest,
  ApprovalRequest,
  ApprovalDecision,
  AgentMetricsSnapshot,
} from "../types/domain";

import { tokenStore } from "../auth/token-store";
import type { BackendRunEvent } from "@/lib/agent-graph-adapter";

export interface StreamRunEventsOptions {
  taskId: string;
  runId: string;
  signal?: AbortSignal;
  onEvent?: (event: BackendRunEvent) => void;
  onError?: (error: Error) => void;
  onComplete?: () => void;
}

export class AgentService {
  private baseUrl: string;

  constructor() {
    this.baseUrl =
      typeof import.meta !== "undefined" && import.meta.env?.VITE_API_BASE_URL
        ? String(import.meta.env.VITE_API_BASE_URL)
        : "";
  }

  public async listPendingApprovals(): Promise<ApprovalRequest[]> {
    const res = await apiClient.get<ApprovalRequest[]>("/api/v1/agent/approvals/pending");
    return res.data;
  }

  public async getMetrics(): Promise<AgentMetricsSnapshot> {
    const res = await apiClient.get<AgentMetricsSnapshot>("/api/v1/agent/metrics");
    return res.data;
  }

  public async createTask(request: CreateTaskRequest): Promise<TaskState> {
    const res = await apiClient.post<TaskState>("/api/v1/agent/tasks", request);
    return res.data;
  }

  public async getTask(taskId: string): Promise<TaskState> {
    const res = await apiClient.get<TaskState>(`/api/v1/agent/tasks/${encodeURIComponent(taskId)}`);
    return res.data;
  }

  public async startRun(taskId: string, request: CreateRunRequest): Promise<RunState> {
    const res = await apiClient.post<RunState>(
      `/api/v1/agent/tasks/${encodeURIComponent(taskId)}/runs`,
      request
    );
    return res.data;
  }

  public async getRun(taskId: string, runId: string): Promise<RunState> {
    const res = await apiClient.get<RunState>(
      `/api/v1/agent/tasks/${encodeURIComponent(taskId)}/runs/${encodeURIComponent(runId)}`
    );
    return res.data;
  }

  public async decideApproval(
    taskId: string,
    runId: string,
    approvalId: string,
    decision: ApprovalDecision
  ): Promise<ApprovalRequest> {
    const res = await apiClient.post<ApprovalRequest>(
      `/api/v1/agent/tasks/${encodeURIComponent(taskId)}/runs/${encodeURIComponent(runId)}/approvals/${encodeURIComponent(approvalId)}`,
      decision
    );
    return res.data;
  }

  public async cancelRun(taskId: string, runId: string): Promise<RunState> {
    const res = await apiClient.post<RunState>(
      `/api/v1/agent/tasks/${encodeURIComponent(taskId)}/runs/${encodeURIComponent(runId)}/cancel`,
      {}
    );
    return res.data;
  }

  /**
   * Connects to GET /api/v1/agent/tasks/:taskId/runs/:runId/events via SSE
   */
  public async streamRunEvents(options: StreamRunEventsOptions): Promise<void> {
    const { taskId, runId, signal, onEvent, onError, onComplete } = options;
    const fallbackOrigin = "http://127.0.0.1:8000";
    const base = this.baseUrl || fallbackOrigin;
    const url = `${base.replace(/\/$/, "")}/api/v1/agent/tasks/${encodeURIComponent(taskId)}/runs/${encodeURIComponent(runId)}/events`;

    const headers: Record<string, string> = {
      Accept: "text/event-stream",
    };

    const token = tokenStore.getAccessToken();
    if (token) {
      headers["Authorization"] = `Bearer ${token}`;
    }
    const tenantId = tokenStore.getActiveTenantId();
    if (tenantId) {
      headers["X-Tenant-ID"] = tenantId;
    }

    let response: Response;
    try {
      response = await fetch(url, {
        method: "GET",
        headers,
        signal,
      });
    } catch (err: unknown) {
      if (signal?.aborted) return;
      const error = err instanceof Error ? err : new Error(String(err));
      onError?.(error);
      throw error;
    }

    if (!response.ok) {
      const errText = await response.text().catch(() => "Stream connection failed");
      const error = new Error(`HTTP ${response.status}: ${errText}`);
      onError?.(error);
      throw error;
    }

    if (!response.body) {
      const error = new Error("Response body is empty or not readable as a stream");
      onError?.(error);
      throw error;
    }

    const reader = response.body.getReader();
    const decoder = new TextDecoder("utf-8");
    let buffer = "";

    try {
      while (true) {
        if (signal?.aborted) break;
        const { value, done } = await reader.read();
        if (done) break;

        buffer += decoder.decode(value, { stream: true });
        const parts = buffer.split("\n\n");
        buffer = parts.pop() || "";

        for (const part of parts) {
          if (!part.trim()) continue;
          let currentEventType = "message";
          let currentData = "";

          const lines = part.split("\n");
          for (const line of lines) {
            if (line.startsWith("event:")) {
              currentEventType = line.slice(6).trim();
            } else if (line.startsWith("data:")) {
              currentData = line.slice(5).trim();
            }
          }

          if (currentData) {
            try {
              const parsed = JSON.parse(currentData) as BackendRunEvent;
              // Normalize event type if embedded
              if (!parsed.event_type && currentEventType) {
                parsed.event_type = currentEventType;
              }
              onEvent?.(parsed);

              if (
                parsed.event_type === "completed" ||
                parsed.event_type === "failed" ||
                parsed.event_type === "cancelled"
              ) {
                onComplete?.();
                return;
              }
            } catch {
              // Ignore non-JSON frames
            }
          }
        }
      }
    } catch (err: unknown) {
      if (!signal?.aborted) {
        const error = err instanceof Error ? err : new Error(String(err));
        onError?.(error);
        throw error;
      }
    } finally {
      reader.cancel().catch(() => {});
      onComplete?.();
    }
  }
}

export const agentService = new AgentService();

