/**
 * Frontend Permission & Capability System
 *
 * Provides a declarative capability checking system for UI rendering and navigation.
 *
 * ⚠️ CRITICAL ARCHITECTURAL BOUNDARY:
 * Frontend capability checks are strictly for UX (button disabling, conditional display,
 * route guards). The backend FastAPI and FinnApiGo services remain the authoritative
 * authorization boundary. Never rely on frontend state for application security.
 */

import type { User } from "@/types/auth";

export type StandardPermission =
  | "agent:read"
  | "agent:write"
  | "agent:execute"
  | "agent:approve"
  | "rag:read"
  | "rag:write"
  | "rag:ingest"
  | "chat:read"
  | "chat:write"
  | "gateway:read"
  | "gateway:write"
  | "finops:read"
  | "finops:write"
  | "byok:read"
  | "byok:write"
  | "analytics:read"
  | "admin:read"
  | "admin:write"
  | string;

export class CapabilityManager {
  /**
   * Check if a user possesses a specific permission.
   *
   * Logic:
   * 1. Admin or Tenant Admin roles bypass permission checks (matching backend TenantContext.has_permission).
   * 2. Global wildcard "*" grants all permissions.
   * 3. Exact string match grants permission.
   * 4. Domain wildcard (e.g. "agent:*") grants any sub-action ("agent:write").
   */
  public static can(permission: string, user: User | null): boolean {
    if (!user) return false;

    // Admin role bypass (mirrors backend context.has_permission)
    const roles = user.roles || [];
    if (roles.includes("admin") || roles.includes("tenant_admin")) {
      return true;
    }

    const permissions = user.permissions || [];
    if (permissions.includes("*")) {
      return true;
    }

    if (permissions.includes(permission)) {
      return true;
    }

    // Domain wildcard check (e.g. "agent:*" matches "agent:write")
    const [domain] = permission.split(":");
    if (domain && permissions.includes(`${domain}:*`)) {
      return true;
    }

    return false;
  }

  /**
   * Verify that the user possesses ALL specified permissions.
   */
  public static canAll(permissions: string[], user: User | null): boolean {
    return permissions.every((perm) => this.can(perm, user));
  }

  /**
   * Verify that the user possesses AT LEAST ONE of the specified permissions.
   */
  public static canAny(permissions: string[], user: User | null): boolean {
    return permissions.some((perm) => this.can(perm, user));
  }

  /**
   * Verify that the user has a specific role or any role from a list.
   */
  public static hasRole(role: string | string[], user: User | null): boolean {
    if (!user || !user.roles) return false;
    const required = Array.isArray(role) ? role : [role];
    if (user.roles.includes("admin") || user.roles.includes("tenant_admin")) {
      return true;
    }
    return required.some((r) => user.roles.includes(r));
  }
}

/**
 * Pure function helper
 */
export const can = CapabilityManager.can.bind(CapabilityManager);
export const canAll = CapabilityManager.canAll.bind(CapabilityManager);
export const canAny = CapabilityManager.canAny.bind(CapabilityManager);
export const hasRole = CapabilityManager.hasRole.bind(CapabilityManager);
