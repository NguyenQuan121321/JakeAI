/**
 * Admin Service
 *
 * Implements FinnApiGo and JakeAI administrative operations:
 * - User management & status locking
 * - System audit logs
 */

import { apiClient } from "../client/http-client";
import type { FinnApiResponse } from "../types/api";

export interface AdminUserItem {
  id: number | string;
  username: string;
  email: string;
  role: string;
  isActive: boolean;
  isLocked?: boolean;
  createdAt: string;
}

export interface AdminAuditLogItem {
  id: number | string;
  userId?: string | number;
  action: string;
  resource: string;
  ipAddress: string;
  userAgent?: string;
  createdAt: string;
}

export class AdminService {
  public async listUsers(): Promise<AdminUserItem[]> {
    const res = await apiClient.get<FinnApiResponse<AdminUserItem[]>>("/api/v1/admin/users");
    return res.data.data || [];
  }

  public async listAuditLogs(): Promise<AdminAuditLogItem[]> {
    const res = await apiClient.get<FinnApiResponse<AdminAuditLogItem[]>>("/api/v1/admin/audit-log");
    return res.data.data || [];
  }

  public async lockUser(userId: string | number): Promise<void> {
    await apiClient.post<FinnApiResponse<null>>(`/api/v1/admin/users/${encodeURIComponent(userId)}/lock`);
  }

  public async unlockUser(userId: string | number): Promise<void> {
    await apiClient.post<FinnApiResponse<null>>(`/api/v1/admin/users/${encodeURIComponent(userId)}/unlock`);
  }
}

export const adminService = new AdminService();
