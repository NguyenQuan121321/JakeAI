/**
 * Admin Service
 *
 * Implements FinnApiGo and JakeAI administrative operations:
 * - User management, status locking, unlocking, and forced logout
 * - System and personal audit logs with CSV/NDJSON export
 * - Active tenant session inspection
 */

import { apiClient } from "../client/http-client";
import type { FinnApiResponse } from "../types/api";

export interface AdminUserItem {
  id: number | string;
  username: string;
  email: string;
  fullName?: string;
  role: string;
  isActive: boolean;
  isLocked?: boolean;
  lockedUntil?: string | null;
  createdAt: string;
}

export type AdminUserList = AdminUserItem[] & {
  items: AdminUserItem[];
  total: number;
  page: number;
  limit: number;
};

export interface AdminAuditLogItem {
  id: number | string;
  tenantId?: string;
  userId?: string | number;
  email?: string;
  action: string;
  resource: string;
  ipAddress: string;
  userAgent?: string;
  success: boolean;
  detail?: string;
  recordHash?: string;
  correlationId?: string;
  createdAt: string;
}

export type AdminAuditLogList = AdminAuditLogItem[] & {
  items: AdminAuditLogItem[];
  total: number;
  page: number;
  limit: number;
};

export interface AdminSessionItem {
  id: string;
  userId: string | number;
  username: string;
  ipAddress: string;
  userAgent: string;
  createdAt: string;
  expiresAt: string;
}

export class AdminService {
  /**
   * List tenant users with pagination and search filter.
   * Defensively handles both paginated envelope ({ items, total }) and direct array payloads.
   * Returns an array with attached pagination properties for complete backward compatibility.
   */
  public async listUsers(params?: {
    page?: number;
    limit?: number;
    search?: string;
  }): Promise<AdminUserList> {
    const res = await apiClient.get<
      FinnApiResponse<AdminUserItem[] | { items: AdminUserItem[]; total: number; page?: number; limit?: number }>
    >("/api/v1/admin/users", { params });

    const payload = res.data.data;
    let items: AdminUserItem[] = [];
    let total = 0;
    let page = params?.page || 1;
    let limit = params?.limit || 20;

    if (Array.isArray(payload)) {
      items = [...payload];
      total = payload.length;
    } else if (payload && "items" in payload && Array.isArray(payload.items)) {
      items = [...payload.items];
      total = payload.total ?? payload.items.length;
      page = payload.page || page;
      limit = payload.limit || limit;
    }

    const result = Object.assign(items, {
      total,
      page,
      limit,
      items,
    });

    return result as AdminUserList;
  }

  /**
   * Lock a user account for a specified duration or indefinitely.
   */
  public async lockUser(
    userId: string | number,
    durationSeconds: number = 3600
  ): Promise<void> {
    await apiClient.post<FinnApiResponse<null>>(
      `/api/v1/admin/users/${encodeURIComponent(userId)}/lock`,
      { durationSeconds }
    );
  }

  /**
   * Unlock a user account and reset failed counter.
   */
  public async unlockUser(userId: string | number): Promise<void> {
    await apiClient.post<FinnApiResponse<null>>(
      `/api/v1/admin/users/${encodeURIComponent(userId)}/unlock`,
      {}
    );
  }

  /**
   * Force logout: Revoke all active sessions and access tokens for a user.
   */
  public async forceLogout(userId: string | number): Promise<void> {
    await apiClient.post<FinnApiResponse<null>>(
      `/api/v1/admin/users/${encodeURIComponent(userId)}/force-logout`,
      {}
    );
  }

  /**
   * List all active user sessions within the tenant.
   */
  public async listSessions(): Promise<AdminSessionItem[]> {
    const res = await apiClient.get<FinnApiResponse<AdminSessionItem[]>>(
      "/api/v1/admin/sessions"
    );
    return res.data.data || [];
  }

  /**
   * List security audit logs with pagination.
   * Normalizes backend event fields (event -> action, detail -> resource).
   * Returns an array with attached pagination properties for complete backward compatibility.
   */
  public async listAuditLogs(params?: {
    page?: number;
    limit?: number;
  }): Promise<AdminAuditLogList> {
    const res = await apiClient.get<
      FinnApiResponse<AdminAuditLogItem[] | { items: Record<string, unknown>[]; total: number; page?: number; limit?: number }>
    >("/api/v1/admin/audit-log", { params });

    const payload = res.data.data;
    const rawItems: Record<string, unknown>[] = Array.isArray(payload)
      ? (payload as unknown as Record<string, unknown>[])
      : payload && typeof payload === "object" && "items" in payload && Array.isArray((payload as { items: unknown[] }).items)
      ? ((payload as { items: unknown[] }).items as unknown as Record<string, unknown>[])
      : [];

    const normalizedItems: AdminAuditLogItem[] = rawItems.map((item, idx) => ({
      id: (item.id as string | number) || idx + 1,
      tenantId: (item.tenantId as string) || (item.tenant_id as string) || undefined,
      userId: (item.userId as string | number) || (item.user_id as string | number) || undefined,
      email: (item.email as string) || undefined,
      action: String(item.action || item.event || "USER_LOGIN"),
      resource: String(item.resource || item.detail || "auth"),
      ipAddress: String(item.ipAddress || item.ip_address || "127.0.0.1"),
      userAgent: (item.userAgent as string) || undefined,
      success: item.success !== false,
      detail: (item.detail as string) || undefined,
      recordHash: (item.recordHash as string) || (item.record_hash as string) || undefined,
      correlationId: (item.correlationId as string) || (item.correlation_id as string) || undefined,
      createdAt: String(item.createdAt || item.created_at || new Date().toISOString()),
    }));

    const total = Array.isArray(payload)
      ? payload.length
      : payload && "total" in payload
      ? Number((payload as { total: number }).total)
      : normalizedItems.length;

    const page = params?.page || 1;
    const limit = params?.limit || 20;

    const result = Object.assign(normalizedItems, {
      total,
      page,
      limit,
      items: normalizedItems,
    });

    return result as AdminAuditLogList;
  }

  /**
   * Export audit logs in CSV or NDJSON format.
   */
  public async exportAuditLogs(format: "csv" | "ndjson" = "csv"): Promise<string> {
    const res = await apiClient.get<string>("/api/v1/admin/audit-log/export", {
      params: { format },
    });
    return typeof res.data === "string" ? res.data : JSON.stringify(res.data);
  }
}

export const adminService = new AdminService();
