/**
 * AI Gateway React Query Hooks
 */

import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { gatewayService } from "../services/gateway.service";
import { chatService } from "../services/chat.service";
import { queryKeys } from "./query-keys";
import { CACHE_POLICIES } from "../query-client";
import type { UpdateQuotaRequest, GatewayChatRequest } from "../types/domain";

export function useModelsQuery() {
  return useQuery({
    queryKey: queryKeys.gateway.models(),
    queryFn: () => gatewayService.listModels(),
    staleTime: CACHE_POLICIES.configuration.staleTime,
    gcTime: CACHE_POLICIES.configuration.gcTime,
  });
}

export function useQuotasQuery() {
  return useQuery({
    queryKey: queryKeys.gateway.quotas(),
    queryFn: () => gatewayService.getQuota(),
    staleTime: CACHE_POLICIES.finops.staleTime,
    gcTime: CACHE_POLICIES.finops.gcTime,
  });
}

export function useUpdateQuotaMutation() {
  const queryClient = useQueryClient();
  return useMutation({
    mutationFn: (request: UpdateQuotaRequest) => gatewayService.updateQuota(request),
    onSuccess: (updated) => {
      queryClient.setQueryData(queryKeys.gateway.quotas(), updated);
    },
  });
}

export function useGatewayChatMutation() {
  return useMutation({
    mutationFn: (request: GatewayChatRequest) => chatService.postGatewayChat(request),
  });
}
