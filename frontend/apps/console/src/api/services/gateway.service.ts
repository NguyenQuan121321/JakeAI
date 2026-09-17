/**
 * AI Gateway & Model Routing Service
 *
 * Covers model catalog and tenant quota limits.
 */

import { apiClient } from "../client/http-client";
import type {
  ModelListResponse,
  QuotaStatus,
  UpdateQuotaRequest,
} from "../types/domain";

export class GatewayService {
  public async listModels(): Promise<ModelListResponse> {
    const res = await apiClient.get<ModelListResponse>("/api/v1/gateway/models");
    return res.data;
  }

  public async getQuota(): Promise<QuotaStatus> {
    const res = await apiClient.get<QuotaStatus>("/api/v1/gateway/quotas");
    return res.data;
  }

  public async updateQuota(request: UpdateQuotaRequest): Promise<QuotaStatus> {
    const res = await apiClient.post<QuotaStatus>("/api/v1/gateway/quotas", request);
    return res.data;
  }
}

export const gatewayService = new GatewayService();
