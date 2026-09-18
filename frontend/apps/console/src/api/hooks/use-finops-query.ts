/**
 * AI FinOps React Query Hooks
 */

import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { finopsService } from "../services/finops.service";
import { queryKeys } from "./query-keys";
import { CACHE_POLICIES } from "../query-client";
import type { UpdateBudgetRequest } from "../types/domain";

export function useFinopsSummaryQuery(period?: string) {
  return useQuery({
    queryKey: queryKeys.finops.summary(undefined, period),
    queryFn: () => finopsService.getSummary(period),
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
      queryClient.invalidateQueries({ queryKey: queryKeys.finops.all });
    },
  });
}

export function useFinopsReconciliationQuery(period?: string) {
  return useQuery({
    queryKey: queryKeys.finops.reconciliation(undefined, period),
    queryFn: () => finopsService.getReconciliation(period),
    staleTime: CACHE_POLICIES.finops.staleTime,
  });
}

export function useFinopsTransactionsQuery(params?: {
  period?: string;
  limit?: number;
  offset?: number;
}) {
  return useQuery({
    queryKey: queryKeys.finops.transactions(undefined, params),
    queryFn: () => finopsService.listTransactions(params),
    staleTime: CACHE_POLICIES.finops.staleTime,
  });
}
