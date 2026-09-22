/**
 * Centralized Playwright E2E Authentication Fixture & Test Identities
 *
 * Provides:
 * - Canonical typed test users (ADMIN_USER, MEMBER_USER, FINOPS_USER)
 * - Deterministic test-only JWT generation compatible with decodeJwt()
 * - Authoritative session bootstrap helpers:
 *   - installAuthenticatedSession(page, user)
 *   - installUnauthenticatedSession(page)
 *   - installAdminSession(page)
 *   - installMemberSession(page)
 */

import type { Page } from "@playwright/test";
import type { User } from "../../src/types/auth";

export const ADMIN_USER: User = {
  id: "usr_platform_admin_01",
  name: "Alex Mercer",
  email: "alex.mercer@jakeai.internal",
  avatarUrl: "https://images.unsplash.com/photo-1534528741775-53994a69daeb?w=100&h=100&fit=crop&crop=faces",
  tenantId: "tenant_jakeai_core",
  orgId: "org_enterprise",
  roles: ["admin", "tenant_admin"],
  permissions: ["*"],
};

export const MEMBER_USER: User = {
  id: "usr_developer_01",
  name: "Dev User",
  email: "dev@jakeai.com",
  avatarUrl: "https://images.unsplash.com/photo-1534528741775-53994a69daeb?w=100&h=100&fit=crop&crop=faces",
  tenantId: "tenant_jakeai_core",
  orgId: "org_enterprise",
  roles: ["member"],
  permissions: ["agent:read", "rag:read", "read:workspace", "read:agent"],
};

export const FINOPS_USER: User = {
  id: "usr_finops_01",
  name: "FinOps Analyst",
  email: "finops@jakeai.com",
  avatarUrl: "https://images.unsplash.com/photo-1534528741775-53994a69daeb?w=100&h=100&fit=crop&crop=faces",
  tenantId: "tenant_finops_lab",
  orgId: "org_enterprise",
  roles: ["member", "finops_analyst"],
  permissions: ["read:finops", "write:finops", "read:workspace"],
};

/**
 * Generate a deterministic test-only JWT with valid structure (3-segment Base64URL)
 * without mocking or bypassing decodeJwt in production.
 */
export function createDeterministicTestJwt(user: User): string {
  const header = { alg: "HS256", typ: "JWT" };
  const payload = {
    sub: user.id,
    tenant_id: user.tenantId,
    org_id: user.orgId || "org_enterprise",
    roles: user.roles,
    permissions: user.permissions,
    scopes: ["read", "write", "admin"],
    email: user.email,
    name: user.name,
    exp: Math.floor(Date.now() / 1000) + 86400, // 24 hours validity
    iat: Math.floor(Date.now() / 1000) - 60,
  };

  const toBase64Url = (obj: object) =>
    Buffer.from(JSON.stringify(obj))
      .toString("base64")
      .replace(/=/g, "")
      .replace(/\+/g, "-")
      .replace(/\//g, "_");

  return `${toBase64Url(header)}.${toBase64Url(payload)}.deterministic_e2e_signature`;
}

/**
 * Configure an authenticated session for the specified user before page navigation
 */
export async function installAuthenticatedSession(
  page: Page,
  user: User = ADMIN_USER
): Promise<void> {
  const testToken = createDeterministicTestJwt(user);

  await page.addInitScript(
    ({ userObj, token }) => {
      // Clean previous session state
      window.sessionStorage.removeItem("jakeai_unauthenticated");

      // Authoritative user override for AuthProvider initialization
      window.sessionStorage.setItem("jakeai_user_override", JSON.stringify(userObj));

      // Syntactically valid tokens
      window.sessionStorage.setItem("jakeai_access_token", token);
      window.sessionStorage.setItem("jakeai_refresh_token", `refresh-${userObj.id}`);

      // Active tenant workspace selection
      try {
        window.localStorage.setItem("jakeai-active-workspace", userObj.tenantId);
      } catch {
        // Storage access fallback
      }
    },
    { userObj: user, token: testToken }
  );
}

/**
 * Explicitly configure an unauthenticated state for testing login flows
 */
export async function installUnauthenticatedSession(page: Page): Promise<void> {
  await page.addInitScript(() => {
    window.sessionStorage.setItem("jakeai_unauthenticated", "true");
    window.sessionStorage.removeItem("jakeai_user_override");
    window.sessionStorage.removeItem("jakeai_access_token");
    window.sessionStorage.removeItem("jakeai_refresh_token");
  });
}

/**
 * Shortcut for admin session
 */
export async function installAdminSession(page: Page): Promise<void> {
  return installAuthenticatedSession(page, ADMIN_USER);
}

/**
 * Shortcut for member / non-admin session
 */
export async function installMemberSession(page: Page): Promise<void> {
  return installAuthenticatedSession(page, MEMBER_USER);
}
