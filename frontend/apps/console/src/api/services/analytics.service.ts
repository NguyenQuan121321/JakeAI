/**
 * Platform Analytics & Billing Service
 *
 * Covers system telemetry dashboards and subscription status.
 */

import { apiClient } from "../client/http-client";
import type {
  AnalyticsDashboard,
  MetricsSnapshot,
  SubscriptionInfo,
} from "../types/domain";

export class AnalyticsService {
  public async getDashboard(): Promise<AnalyticsDashboard> {
    const res = await apiClient.get<AnalyticsDashboard>("/api/v1/analytics/dashboard");
    return res.data;
  }

  public async getMetrics(): Promise<MetricsSnapshot> {
    const res = await apiClient.get<MetricsSnapshot>("/api/v1/analytics/metrics");
    return res.data;
  }

  public async getSubscription(): Promise<SubscriptionInfo> {
    const res = await apiClient.get<SubscriptionInfo>("/api/v1/billing/subscription");
    return res.data;
  }
}

export const analyticsService = new AnalyticsService();
