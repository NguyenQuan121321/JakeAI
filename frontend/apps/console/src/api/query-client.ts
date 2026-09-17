/**
 * Central TanStack Query Client Configuration
 *
 * Defines explicit staleTime, gcTime, and retry policies per resource type.
 * Ensures non-aggressive polling and predictable cache invalidation.
 */

import { QueryClient } from "@tanstack/react-query";
import { ApiError } from "./client/api-error";

export const queryClient = new QueryClient({
  defaultOptions: {
    queries: {
      // Default: 2 minutes stale, 10 minutes garbage collection
      staleTime: 1000 * 60 * 2,
      gcTime: 1000 * 60 * 10,
      refetchOnWindowFocus: false,
      refetchOnReconnect: true,
      retry: (failureCount, error) => {
        // Never retry client-side errors (4xx)
        if (error instanceof ApiError) {
          if (error.status >= 400 && error.status < 500) {
            return false;
          }
        }
        return failureCount < 2;
      },
    },
    mutations: {
      retry: false,
    },
  },
});

/**
 * Resource-specific cache timing profiles
 */
export const CACHE_POLICIES = {
  health: {
    staleTime: 1000 * 15, // 15 seconds
    gcTime: 1000 * 60,
  },
  metrics: {
    staleTime: 1000 * 30, // 30 seconds
    gcTime: 1000 * 60 * 5,
  },
  finops: {
    staleTime: 1000 * 60, // 1 minute
    gcTime: 1000 * 60 * 15,
  },
  configuration: {
    staleTime: 1000 * 60 * 5, // 5 minutes
    gcTime: 1000 * 60 * 30,
  },
  staticDomain: {
    staleTime: 1000 * 60 * 10, // 10 minutes
    gcTime: 1000 * 60 * 60,
  },
} as const;
