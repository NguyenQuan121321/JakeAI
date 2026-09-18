/**
 * Auth React Query Hooks
 */

import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { authService, type LoginRequest } from "../services/auth.service";
import { queryKeys } from "./query-keys";
import { CACHE_POLICIES } from "../query-client";

export function useLoginMutation() {
  const queryClient = useQueryClient();
  return useMutation({
    mutationFn: (credentials: LoginRequest) => authService.login(credentials),
    onSuccess: () => {
      queryClient.invalidateQueries({ queryKey: queryKeys.auth.all });
    },
  });
}

export function useLogoutMutation() {
  const queryClient = useQueryClient();
  return useMutation({
    mutationFn: () => authService.logout(),
    onSuccess: () => {
      queryClient.clear();
    },
  });
}

export function useUserProfileQuery(enabled = true) {
  return useQuery({
    queryKey: queryKeys.auth.me(),
    queryFn: () => authService.getMe(),
    enabled,
    staleTime: CACHE_POLICIES.staticDomain.staleTime,
    gcTime: CACHE_POLICIES.staticDomain.gcTime,
  });
}
