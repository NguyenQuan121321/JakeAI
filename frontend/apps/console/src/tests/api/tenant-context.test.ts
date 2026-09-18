/**
 * Tenant Context & Isolation Security Boundary Tests
 */

import { describe, it, expect, beforeEach } from "vitest";
import { http, HttpResponse } from "msw";
import { server } from "@/mocks/server";
import { TenantManager } from "@/api/auth/tenant";
import { tokenStore } from "@/api/auth/token-store";
import { ApiClient } from "@/api/client/http-client";
import type { User, Workspace } from "@/types/auth";
import type { DecodedJwtClaims } from "@/api/auth/jwt";

describe("Tenant Context Boundary", () => {
  const mockUser: User = {
    id: "usr_alice",
    name: "Alice",
    email: "alice@acme.com",
    tenantId: "tenant_acme_prod",
    roles: ["member"],
    permissions: [],
  };

  const mockClaims: DecodedJwtClaims = {
    sub: "usr_alice",
    tenant_id: "tenant_acme_prod",
    org_id: "org_acme",
    roles: ["member"],
    permissions: [],
    scopes: [],
    raw: {},
  };

  const availableWorkspaces: Workspace[] = [
    {
      id: "tenant_acme_prod",
      name: "Acme Production",
      slug: "acme-prod",
      plan: "enterprise",
      environment: "production",
    },
    {
      id: "tenant_acme_staging",
      name: "Acme Staging",
      slug: "acme-staging",
      plan: "team",
      environment: "staging",
    },
  ];

  beforeEach(() => {
    tokenStore.clear();
  });

  it("extracts authorized tenants including primary token tenant", () => {
    const authorized = TenantManager.getAuthorizedTenants(mockUser, mockClaims, availableWorkspaces);
    expect(authorized).toHaveLength(2);
    expect(authorized[0].tenantId).toBe("tenant_acme_prod");
    expect(authorized[0].isPrimary).toBe(true);
    expect(authorized[1].tenantId).toBe("tenant_acme_staging");
  });

  it("resolves valid authorized tenant selection", () => {
    const authorized = TenantManager.getAuthorizedTenants(mockUser, mockClaims, availableWorkspaces);
    const resolved = TenantManager.resolveAuthorizedTenantId("tenant_acme_staging", authorized);
    expect(resolved).toBe("tenant_acme_staging");
  });

  it("rejects unauthorized spoofed tenant IDs and falls back strictly to primary", () => {
    const authorized = TenantManager.getAuthorizedTenants(mockUser, mockClaims, availableWorkspaces);
    // Attempting to select a malicious or competitor tenant
    const resolved = TenantManager.resolveAuthorizedTenantId("tenant_evil_corp", authorized);
    expect(resolved).toBe("tenant_acme_prod"); // strictly fell back to authorized primary!
  });

  it("automatically injects active authorized X-Tenant-ID header in outgoing requests", async () => {
    let capturedTenantHeader: string | null = null;
    tokenStore.setActiveTenantId("tenant_acme_prod");

    const client = new ApiClient({ baseUrl: "https://api.jakeai.internal" });

    server.use(
      http.get("https://api.jakeai.internal/tenant-check", ({ request }) => {
        capturedTenantHeader = request.headers.get("X-Tenant-ID");
        return HttpResponse.json({ ok: true });
      })
    );

    await client.get("/tenant-check");
    expect(capturedTenantHeader).toBe("tenant_acme_prod");
  });
});
