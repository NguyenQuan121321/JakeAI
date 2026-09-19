/**
 * AI FinOps & Budget Service
 *
 * Covers token spend reconciliation, real-time ledger records, and budget thresholds.
 */

import { apiClient } from "../client/http-client";
import type {
  FinOpsSummary,
  TenantBudget,
  UpdateBudgetRequest,
  ReconciliationReport,
  FinOpsRecord,
} from "../types/domain";

export class FinOpsService {
  public async getSummary(period?: string): Promise<FinOpsSummary> {
    const res = await apiClient.get<FinOpsSummary>("/api/v1/finops/summary", {
      params: period ? { period } : undefined,
    });
    return res.data;
  }

  public async getBudget(): Promise<TenantBudget> {
    const res = await apiClient.get<TenantBudget>("/api/v1/finops/budget");
    return res.data;
  }

  public async updateBudget(request: UpdateBudgetRequest): Promise<TenantBudget> {
    const res = await apiClient.post<TenantBudget>("/api/v1/finops/budget", request);
    return res.data;
  }

  public async getReconciliation(period?: string): Promise<ReconciliationReport> {
    const res = await apiClient.get<ReconciliationReport>("/api/v1/finops/reconciliation", {
      params: period ? { period } : undefined,
    });
    return res.data;
  }

  public async listTransactions(params?: {
    period?: string;
    limit?: number;
    offset?: number;
  }): Promise<FinOpsRecord[]> {
    const res = await apiClient.get<FinOpsRecord[]>("/api/v1/finops/transactions", {
      params,
    });
    return res.data;
  }
}

export const finopsService = new FinOpsService();
