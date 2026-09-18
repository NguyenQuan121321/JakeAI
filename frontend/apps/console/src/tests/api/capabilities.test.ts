/**
 * Capabilities & Permission System Tests
 */

import { describe, it, expect } from "vitest";
import { can, canAll, canAny, hasRole } from "@/api/auth/capabilities";
import type { User } from "@/types/auth";

describe("Capability & Permission System (UX Layer)", () => {
  const adminUser: User = {
    id: "usr_admin",
    name: "Admin User",
    email: "admin@jakeai.internal",
    tenantId: "tenant_jakeai_core",
    roles: ["admin"],
    permissions: [],
  };

  const tenantAdminUser: User = {
    id: "usr_tenant_admin",
    name: "Tenant Admin",
    email: "tenant.admin@jakeai.internal",
    tenantId: "tenant_finops_lab",
    roles: ["tenant_admin"],
    permissions: [],
  };

  const standardUser: User = {
    id: "usr_dev",
    name: "Standard Dev",
    email: "dev@jakeai.internal",
    tenantId: "tenant_jakeai_core",
    roles: ["developer"],
    permissions: ["agent:read", "agent:write", "rag:read"],
  };

  const wildcardUser: User = {
    id: "usr_lead",
    name: "Team Lead",
    email: "lead@jakeai.internal",
    tenantId: "tenant_jakeai_core",
    roles: ["team_lead"],
    permissions: ["byok:*", "finops:read"],
  };

  const globalWildcardUser: User = {
    id: "usr_wildcard",
    name: "Wildcard User",
    email: "wildcard@jakeai.internal",
    tenantId: "tenant_jakeai_core",
    roles: ["viewer"],
    permissions: ["*"],
  };

  it("admin role automatically satisfies all capabilities", () => {
    expect(can("agent:write", adminUser)).toBe(true);
    expect(can("rag:write", adminUser)).toBe(true);
    expect(can("finops:write", adminUser)).toBe(true);
    expect(hasRole("admin", adminUser)).toBe(true);
  });

  it("tenant_admin role automatically satisfies all capabilities", () => {
    expect(can("agent:write", tenantAdminUser)).toBe(true);
    expect(can("byok:rotate", tenantAdminUser)).toBe(true);
    expect(hasRole("tenant_admin", tenantAdminUser)).toBe(true);
  });

  it("global wildcard '*' satisfies all capabilities", () => {
    expect(can("agent:execute", globalWildcardUser)).toBe(true);
    expect(can("finops:manage", globalWildcardUser)).toBe(true);
  });

  it("domain wildcard matches sub-permissions", () => {
    expect(can("byok:read", wildcardUser)).toBe(true);
    expect(can("byok:write", wildcardUser)).toBe(true);
    expect(can("byok:rotate", wildcardUser)).toBe(true);
    expect(can("finops:read", wildcardUser)).toBe(true);
    expect(can("finops:write", wildcardUser)).toBe(false); // only read granted
    expect(can("agent:read", wildcardUser)).toBe(false);
  });

  it("evaluates exact granular permissions", () => {
    expect(can("agent:read", standardUser)).toBe(true);
    expect(can("agent:write", standardUser)).toBe(true);
    expect(can("rag:read", standardUser)).toBe(true);
    expect(can("rag:write", standardUser)).toBe(false);
    expect(can("admin:access", standardUser)).toBe(false);
  });

  it("evaluates canAll and canAny correctly", () => {
    expect(canAll(["agent:read", "agent:write"], standardUser)).toBe(true);
    expect(canAll(["agent:read", "rag:write"], standardUser)).toBe(false);

    expect(canAny(["admin:access", "agent:read"], standardUser)).toBe(true);
    expect(canAny(["admin:access", "finops:write"], standardUser)).toBe(false);
  });

  it("denies access if user is null or missing", () => {
    expect(can("agent:read", null)).toBe(false);
    expect(canAll(["agent:read"], null)).toBe(false);
    expect(canAny(["agent:read"], null)).toBe(false);
    expect(hasRole("admin", null)).toBe(false);
  });
});
