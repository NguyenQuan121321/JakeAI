/**
 * RAG Pipeline React Query Hooks
 */

import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { ragService } from "../services/rag.service";
import { queryKeys } from "./query-keys";
import type {
  RAGQueryRequest,
  RAGGenerateRequest,
  DocumentIngestRequest,
} from "../types/domain";

export function useRagQueryMutation() {
  return useMutation({
    mutationFn: (request: RAGQueryRequest) => ragService.query(request),
  });
}

export function useRagGenerateMutation() {
  return useMutation({
    mutationFn: (request: RAGGenerateRequest) => ragService.generate(request),
  });
}

export function useRagIngestMutation() {
  const queryClient = useQueryClient();
  return useMutation({
    mutationFn: ({
      request,
      asyncMode = false,
    }: {
      request: DocumentIngestRequest;
      asyncMode?: boolean;
    }) => ragService.ingest(request, asyncMode),
    onSuccess: (res) => {
      if (res && "task_id" in res && res.task_id) {
        queryClient.invalidateQueries({ queryKey: queryKeys.rag.tasks() });
      }
    },
  });
}

export function useRagTaskQuery(taskId: string, enabled = true) {
  return useQuery({
    queryKey: queryKeys.rag.task(taskId),
    queryFn: () => ragService.getIngestionTask(taskId),
    enabled: enabled && Boolean(taskId),
    staleTime: 0,
    refetchInterval: (query) => {
      const state = query.state.data;
      if (state && (state.status === "completed" || state.status === "failed")) {
        return false;
      }
      return 1500;
    },
  });
}

