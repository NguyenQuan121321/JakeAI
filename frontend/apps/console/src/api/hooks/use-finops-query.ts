/**
 * AI FinOps React Query Hooks
 */

import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { finopsService } from "../services/finops.service";
import { queryKeys } from "./query-keys";
import { CACHE_POLICIES } from "../query-client";
import type { UpdateBudgetRequest } from "../types/domain";

export function useFinopsSummaryQuery() {
  return useQuery({
    queryKey: queryKeys.finops.summary(),
    queryFn: () => finopsService.getSummary(),
    staleTime: CACHE_POLICIES.finops.staleTime,
    gcTime: CACHE_POLICIES.finops.gcTime,
  });
}

export function useFinopsBudgetQuery() {
  return useQuery({
    queryKey: queryKeys.finops.budget(),
    queryFn: () => finopsService.getBudget(),
    staleTime: CACHE_POLICIES.finops.staleTime,
    gcTime: CACHE_POLICIES.finops.gcTime,
  });
}

export function useUpdateBudgetMutation() {
  const queryClient = useQueryClient();
  return useMutation({
    mutationFn: (request: UpdateBudgetRequest) => finopsService.updateBudget(request),
    onSuccess: (updatedBudget) => {
      queryClient.setQueryData(queryKeys.finops.budget(), updatedBudget);
      queryClient.invalidateQueries({ queryKey: queryKeys.finops.summary() });
    },
  });
}

export function useFinopsReconciliationQuery() {
  return useQuery({
    queryKey: queryKeys.finops.reconciliation(),
    queryFn: () => finopsService.getReconciliation(),
    staleTime: CACHE_POLICIES.finops.staleTime,
  });
}

export function useFinopsTransactionsQuery() {
  return useQuery({
    queryKey: queryKeys.finops.transactions(),
    queryFn: () => finopsService.listTransactions(),
    staleTime: CACHE_POLICIES.finops.staleTime,
  });
}
