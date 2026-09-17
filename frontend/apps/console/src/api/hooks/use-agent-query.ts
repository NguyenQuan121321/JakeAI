/**
 * Agent Platform React Query Hooks
 */

import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { agentService } from "../services/agent.service";
import { queryKeys } from "./query-keys";
import { CACHE_POLICIES } from "../query-client";
import type { CreateTaskRequest, CreateRunRequest, ApprovalDecision } from "../types/domain";

export function usePendingApprovalsQuery() {
  return useQuery({
    queryKey: queryKeys.agent.approvals(),
    queryFn: () => agentService.listPendingApprovals(),
    staleTime: CACHE_POLICIES.metrics.staleTime,
    gcTime: CACHE_POLICIES.metrics.gcTime,
  });
}

export function useAgentMetricsQuery() {
  return useQuery({
    queryKey: queryKeys.agent.metrics(),
    queryFn: () => agentService.getMetrics(),
    staleTime: CACHE_POLICIES.metrics.staleTime,
    gcTime: CACHE_POLICIES.metrics.gcTime,
  });
}

export function useAgentTaskQuery(taskId: string, enabled = true) {
  return useQuery({
    queryKey: queryKeys.agent.task(taskId),
    queryFn: () => agentService.getTask(taskId),
    enabled: enabled && Boolean(taskId),
    staleTime: CACHE_POLICIES.finops.staleTime,
  });
}

export function useAgentRunQuery(taskId: string, runId: string, enabled = true) {
  return useQuery({
    queryKey: queryKeys.agent.run(taskId, runId),
    queryFn: () => agentService.getRun(taskId, runId),
    enabled: enabled && Boolean(taskId) && Boolean(runId),
    staleTime: CACHE_POLICIES.health.staleTime,
  });
}

export function useCreateTaskMutation() {
  const queryClient = useQueryClient();
  return useMutation({
    mutationFn: (request: CreateTaskRequest) => agentService.createTask(request),
    onSuccess: (newTask) => {
      queryClient.invalidateQueries({ queryKey: queryKeys.agent.tasks() });
      if (newTask.task_id) {
        queryClient.setQueryData(queryKeys.agent.task(newTask.task_id), newTask);
      }
    },
  });
}

export function useStartRunMutation(taskId: string) {
  const queryClient = useQueryClient();
  return useMutation({
    mutationFn: (request: CreateRunRequest) => agentService.startRun(taskId, request),
    onSuccess: (newRun) => {
      queryClient.invalidateQueries({ queryKey: queryKeys.agent.runs(taskId) });
      if (newRun.run_id) {
        queryClient.setQueryData(queryKeys.agent.run(taskId, newRun.run_id), newRun);
      }
    },
  });
}

export function useDecideApprovalMutation(taskId: string, runId: string, approvalId: string) {
  const queryClient = useQueryClient();
  return useMutation({
    mutationFn: (decision: ApprovalDecision) =>
      agentService.decideApproval(taskId, runId, approvalId, decision),
    onSuccess: () => {
      queryClient.invalidateQueries({ queryKey: queryKeys.agent.approvals() });
      queryClient.invalidateQueries({ queryKey: queryKeys.agent.run(taskId, runId) });
    },
  });
}

export function useCancelRunMutation(taskId: string, runId: string) {
  const queryClient = useQueryClient();
  return useMutation({
    mutationFn: () => agentService.cancelRun(taskId, runId),
    onSuccess: () => {
      queryClient.invalidateQueries({ queryKey: queryKeys.agent.run(taskId, runId) });
    },
  });
}
