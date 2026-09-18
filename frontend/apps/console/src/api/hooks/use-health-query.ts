/**
 * Health React Query Hooks
 */

import { useQuery } from "@tanstack/react-query";
import { healthService } from "../services/health.service";
import { queryKeys } from "./query-keys";
import { CACHE_POLICIES } from "../query-client";

export function useHealthQuery() {
  return useQuery({
    queryKey: queryKeys.health.apiV1(),
    queryFn: () => healthService.getHealth(),
    staleTime: CACHE_POLICIES.health.staleTime,
    gcTime: CACHE_POLICIES.health.gcTime,
  });
}

export function useLivenessQuery() {
  return useQuery({
    queryKey: queryKeys.health.liveness(),
    queryFn: () => healthService.getLiveness(),
    staleTime: CACHE_POLICIES.health.staleTime,
    gcTime: CACHE_POLICIES.health.gcTime,
  });
}

export function useReadinessQuery() {
  return useQuery({
    queryKey: queryKeys.health.readiness(),
    queryFn: () => healthService.getReadiness(),
    staleTime: CACHE_POLICIES.health.staleTime,
    gcTime: CACHE_POLICIES.health.gcTime,
  });
}
