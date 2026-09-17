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
  public async getSummary(): Promise<FinOpsSummary> {
    const res = await apiClient.get<FinOpsSummary>("/api/v1/finops/summary");
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

  public async getReconciliation(): Promise<ReconciliationReport> {
    const res = await apiClient.get<ReconciliationReport>("/api/v1/finops/reconciliation");
    return res.data;
  }

  public async listTransactions(): Promise<FinOpsRecord[]> {
    const res = await apiClient.get<FinOpsRecord[]>("/api/v1/finops/transactions");
    return res.data;
  }
}

export const finopsService = new FinOpsService();
