/**
 * Health & Probes Service
 *
 * Covers container orchestrator probes (/health, /health/live, /health/ready)
 * and API v1 diagnostic probes (/api/v1/health, /api/v1/health/live, /api/v1/health/ready).
 */

import { apiClient } from "../client/http-client";
import type { HealthResponse } from "../types/domain";

export class HealthService {
  public async getHealth(): Promise<HealthResponse> {
    const res = await apiClient.get<HealthResponse>("/api/v1/health", { skipAuth: true });
    return res.data;
  }

  public async getLiveness(): Promise<HealthResponse> {
    const res = await apiClient.get<HealthResponse>("/api/v1/health/live", { skipAuth: true });
    return res.data;
  }

  public async getReadiness(): Promise<HealthResponse> {
    const res = await apiClient.get<HealthResponse>("/api/v1/health/ready", { skipAuth: true });
    return res.data;
  }

  public async getRootHealth(): Promise<HealthResponse> {
    const res = await apiClient.get<HealthResponse>("/health", { skipAuth: true });
    return res.data;
  }
}

export const healthService = new HealthService();
