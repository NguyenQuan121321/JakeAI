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

export class AgentService {
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
}

export const agentService = new AgentService();
