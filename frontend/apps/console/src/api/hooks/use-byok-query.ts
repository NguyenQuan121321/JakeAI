/**
 * BYOK Vault React Query Hooks
 */

import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { byokService } from "../services/byok.service";
import { queryKeys } from "./query-keys";
import { CACHE_POLICIES } from "../query-client";
import type {
  BYOKStoreRequest,
  BYOKValidateRequest,
  BYOKRotateRequest,
} from "../types/domain";

export function useByokKeysQuery() {
  return useQuery({
    queryKey: queryKeys.byok.keys(),
    queryFn: () => byokService.listKeys(),
    staleTime: CACHE_POLICIES.configuration.staleTime,
    gcTime: CACHE_POLICIES.configuration.gcTime,
  });
}

export function useStoreByokKeyMutation() {
  const queryClient = useQueryClient();
  return useMutation({
    mutationFn: (request: BYOKStoreRequest) => byokService.storeKey(request),
    onSuccess: () => {
      queryClient.invalidateQueries({ queryKey: queryKeys.byok.keys() });
      queryClient.invalidateQueries({ queryKey: queryKeys.gateway.models() });
    },
  });
}

export function useValidateByokKeyMutation() {
  return useMutation({
    mutationFn: (request: BYOKValidateRequest) => byokService.validateCandidateKey(request),
  });
}

export function useDeleteByokKeyMutation() {
  const queryClient = useQueryClient();
  return useMutation({
    mutationFn: (provider: string) => byokService.deleteKey(provider),
    onSuccess: () => {
      queryClient.invalidateQueries({ queryKey: queryKeys.byok.keys() });
    },
  });
}

export function useRevokeByokKeyMutation() {
  const queryClient = useQueryClient();
  return useMutation({
    mutationFn: (provider: string) => byokService.revokeKey(provider),
    onSuccess: () => {
      queryClient.invalidateQueries({ queryKey: queryKeys.byok.keys() });
    },
  });
}

export function useRotateByokKeyMutation(provider: string) {
  const queryClient = useQueryClient();
  return useMutation({
    mutationFn: (request: BYOKRotateRequest) => byokService.rotateKey(provider, request),
    onSuccess: () => {
      queryClient.invalidateQueries({ queryKey: queryKeys.byok.keys() });
    },
  });
}
