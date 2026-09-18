/**
 * Tenant Context Resolution & Security Boundary
 *
 * Enforces strict multi-tenant boundary on the client:
 * - Derives authoritative tenant from authenticated JWT claims.
 * - Only permits switching between authorized workspaces.
 * - Disallows arbitrary or spoofed tenant IDs.
 */

import type { User, Workspace } from "@/types/auth";
import type { DecodedJwtClaims } from "./jwt";

export interface AuthorizedTenantInfo {
  tenantId: string;
  orgId?: string;
  name: string;
  slug: string;
  isPrimary: boolean;
}

export class TenantManager {
  /**
   * Derive authorized tenants from the authenticated user and token claims
   */
  public static getAuthorizedTenants(
    user: User | null,
    claims: DecodedJwtClaims | null,
    availableWorkspaces: Workspace[] = []
  ): AuthorizedTenantInfo[] {
    if (!user && !claims) return [];

    const primaryTenantId = claims?.tenant_id || user?.tenantId || "default";
    const orgId = claims?.org_id || user?.orgId;

    const tenantMap = new Map<string, AuthorizedTenantInfo>();

    // 1. Authoritative primary tenant from token
    tenantMap.set(primaryTenantId, {
      tenantId: primaryTenantId,
      orgId,
      name: availableWorkspaces.find((w) => w.id === primaryTenantId)?.name || primaryTenantId,
      slug: availableWorkspaces.find((w) => w.id === primaryTenantId)?.slug || primaryTenantId,
      isPrimary: true,
    });

    // 2. Add any additional verified workspaces belonging to the same user
    for (const ws of availableWorkspaces) {
      if (!tenantMap.has(ws.id)) {
        tenantMap.set(ws.id, {
          tenantId: ws.id,
          orgId,
          name: ws.name,
          slug: ws.slug,
          isPrimary: false,
        });
      }
    }

    return Array.from(tenantMap.values());
  }

  /**
   * Validates if a tenantId is permitted for the authenticated user.
   * If invalid or untrusted, returns the primary authorized tenant.
   */
  public static resolveAuthorizedTenantId(
    candidateTenantId: string | null | undefined,
    authorizedTenants: AuthorizedTenantInfo[]
  ): string {
    if (authorizedTenants.length === 0) {
      return "default";
    }

    if (candidateTenantId) {
      const match = authorizedTenants.find((t) => t.tenantId === candidateTenantId);
      if (match) {
        return match.tenantId;
      }
    }

    // Fall back strictly to the primary authorized tenant
    const primary = authorizedTenants.find((t) => t.isPrimary);
    return primary ? primary.tenantId : authorizedTenants[0].tenantId;
  }
}
