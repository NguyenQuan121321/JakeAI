/**
 * Admin Governance React Query Hooks
 */

import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { adminService } from "../services/admin.service";
import { queryKeys } from "./query-keys";
import { CACHE_POLICIES } from "../query-client";

export function useAdminUsersQuery(enabled = true) {
  return useQuery({
    queryKey: queryKeys.admin.users(),
    queryFn: () => adminService.listUsers(),
    enabled,
    staleTime: CACHE_POLICIES.configuration.staleTime,
  });
}

export function useAdminAuditLogsQuery(enabled = true) {
  return useQuery({
    queryKey: queryKeys.admin.auditLogs(),
    queryFn: () => adminService.listAuditLogs(),
    enabled,
    staleTime: CACHE_POLICIES.finops.staleTime,
  });
}

export function useLockUserMutation() {
  const queryClient = useQueryClient();
  return useMutation({
    mutationFn: (userId: string | number) => adminService.lockUser(userId),
    onSuccess: () => {
      queryClient.invalidateQueries({ queryKey: queryKeys.admin.users() });
    },
  });
}

export function useUnlockUserMutation() {
  const queryClient = useQueryClient();
  return useMutation({
    mutationFn: (userId: string | number) => adminService.unlockUser(userId),
    onSuccess: () => {
      queryClient.invalidateQueries({ queryKey: queryKeys.admin.users() });
    },
  });
}
