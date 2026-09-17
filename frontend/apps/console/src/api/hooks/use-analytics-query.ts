/**
 * Analytics & Billing React Query Hooks
 */

import { useQuery } from "@tanstack/react-query";
import { analyticsService } from "../services/analytics.service";
import { queryKeys } from "./query-keys";
import { CACHE_POLICIES } from "../query-client";

export function useAnalyticsDashboardQuery() {
  return useQuery({
    queryKey: queryKeys.analytics.dashboard(),
    queryFn: () => analyticsService.getDashboard(),
    staleTime: CACHE_POLICIES.finops.staleTime,
    gcTime: CACHE_POLICIES.finops.gcTime,
  });
}

export function useAnalyticsMetricsQuery() {
  return useQuery({
    queryKey: queryKeys.analytics.metrics(),
    queryFn: () => analyticsService.getMetrics(),
    staleTime: CACHE_POLICIES.metrics.staleTime,
    gcTime: CACHE_POLICIES.metrics.gcTime,
  });
}

export function useSubscriptionQuery() {
  return useQuery({
    queryKey: queryKeys.analytics.subscription(),
    queryFn: () => analyticsService.getSubscription(),
    staleTime: CACHE_POLICIES.configuration.staleTime,
  });
}
