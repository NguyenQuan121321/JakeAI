/**
 * Providers React Query Hooks
 */

import { useQuery } from "@tanstack/react-query";
import { providersService } from "../services/providers.service";
import { CACHE_POLICIES } from "../query-client";

export function useProvidersQuery() {
  return useQuery({
    queryKey: ["providers", "composite-status"],
    queryFn: () => providersService.getProvidersWithStatus(),
    staleTime: CACHE_POLICIES.configuration.staleTime,
    gcTime: CACHE_POLICIES.configuration.gcTime,
  });
}
