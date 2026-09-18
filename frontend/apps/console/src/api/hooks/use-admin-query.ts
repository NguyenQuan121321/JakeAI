/**
 * Admin Governance React Query Hooks
 */

import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { adminService } from "../services/admin.service";
import { queryKeys } from "./query-keys";
import { CACHE_POLICIES } from "../query-client";

export function useAdminUsersQuery(
  params?: { page?: number; limit?: number; search?: string },
  enabled = true
) {
  return useQuery({
    queryKey: queryKeys.admin.users(params),
    queryFn: () => adminService.listUsers(params),
    enabled,
    staleTime: CACHE_POLICIES.configuration.staleTime,
  });
}

export function useAdminAuditLogsQuery(
  params?: { page?: number; limit?: number },
  enabled = true
) {
  return useQuery({
    queryKey: queryKeys.admin.auditLogs(params),
    queryFn: () => adminService.listAuditLogs(params),
    enabled,
    staleTime: CACHE_POLICIES.finops.staleTime,
  });
}

export function useAdminSessionsQuery(enabled = true) {
  return useQuery({
    queryKey: queryKeys.admin.sessions(),
    queryFn: () => adminService.listSessions(),
    enabled,
    staleTime: CACHE_POLICIES.finops.staleTime,
  });
}

export function useLockUserMutation() {
  const queryClient = useQueryClient();
  return useMutation({
    mutationFn: ({ userId, durationSeconds }: { userId: string | number; durationSeconds?: number }) =>
      adminService.lockUser(userId, durationSeconds),
    onSuccess: () => {
      queryClient.invalidateQueries({ queryKey: queryKeys.admin.all });
    },
  });
}

export function useUnlockUserMutation() {
  const queryClient = useQueryClient();
  return useMutation({
    mutationFn: (userId: string | number) => adminService.unlockUser(userId),
    onSuccess: () => {
      queryClient.invalidateQueries({ queryKey: queryKeys.admin.all });
    },
  });
}

export function useForceLogoutMutation() {
  const queryClient = useQueryClient();
  return useMutation({
    mutationFn: (userId: string | number) => adminService.forceLogout(userId),
    onSuccess: () => {
      queryClient.invalidateQueries({ queryKey: queryKeys.admin.all });
    },
  });
}
