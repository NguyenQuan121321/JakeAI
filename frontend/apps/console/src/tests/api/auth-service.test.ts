/**
 * AuthService & TokenStore Integration Tests
 */

import { describe, it, expect, beforeEach, vi } from "vitest";
import { authService } from "@/api/services/auth.service";
import { tokenStore } from "@/api/auth/token-store";
import { decodeJwt, isTokenExpired } from "@/api/auth/jwt";

describe("AuthService & Token Lifecycle", () => {
  beforeEach(() => {
    tokenStore.clear();
  });

  it("authenticates against FinnApiGo login and populates tokenStore", async () => {
    const res = await authService.login({
      email: "alex.mercer@jakeai.internal",
      password: "password123",
    });

    expect(res.accessToken).toBeDefined();
    expect(res.refreshToken).toBeDefined();
    expect(tokenStore.getAccessToken()).toBe(res.accessToken);
    expect(tokenStore.getRefreshToken()).toBe(res.refreshToken);
  });

  it("decodes FinnApiGo compact and expanded claims correctly", () => {
    const header = btoa(JSON.stringify({ alg: "HS256", typ: "JWT" }));
    const payload = btoa(
      JSON.stringify({
        sub: "usr-4422",
        tenant_id: "tenant-acme",
        roles: ["member"],
        permissions: ["agent:read", "agent:write"],
        scopes: ["api"],
        exp: Math.floor(Date.now() / 1000) + 1800,
      })
    );
    const mockToken = `${header}.${payload}.sig`;

    const claims = decodeJwt(mockToken);
    expect(claims).not.toBeNull();
    expect(claims?.sub).toBe("usr-4422");
    expect(claims?.tenant_id).toBe("tenant-acme");
    expect(claims?.roles).toEqual(["member"]);
    expect(claims?.permissions).toContain("agent:write");
    expect(isTokenExpired(mockToken)).toBe(false);
  });

  it("detects expired tokens via isTokenExpired", () => {
    const header = btoa(JSON.stringify({ alg: "HS256", typ: "JWT" }));
    const payload = btoa(
      JSON.stringify({
        sub: "usr-4422",
        exp: Math.floor(Date.now() / 1000) - 60, // expired 1 minute ago
      })
    );
    const expiredToken = `${header}.${payload}.sig`;

    expect(isTokenExpired(expiredToken)).toBe(true);
  });

  it("refreshes tokens via /api/v1/auth/refresh-token", async () => {
    tokenStore.setTokens({
      accessToken: "old-access",
      refreshToken: "mock-refresh-token-uuid-12345",
    });

    const refreshed = await authService.refreshToken();
    expect(refreshed).toBeDefined();
    expect(tokenStore.getAccessToken()).toBe(refreshed);
    expect(tokenStore.getRefreshToken()).toBe("new-mock-refresh-token-uuid-67890");
  });

  it("fetches authenticated user profile via getMe", async () => {
    tokenStore.setTokens({ accessToken: "valid-token" });
    const profile = await authService.getMe();
    expect(profile.email).toBe("alex.mercer@jakeai.internal");
    expect(profile.role).toBe("admin");
  });

  it("clears tokenStore upon logout", async () => {
    tokenStore.setTokens({ accessToken: "valid-token", refreshToken: "refresh" });
    expect(tokenStore.getAccessToken()).toBe("valid-token");

    await authService.logout();
    expect(tokenStore.getAccessToken()).toBeNull();
    expect(tokenStore.getRefreshToken()).toBeNull();
  });

  it("triggers unauthorized listeners on tokenStore.notifyUnauthorized", () => {
    const listener = vi.fn();
    const unsub = tokenStore.subscribeUnauthorized(listener);

    tokenStore.notifyUnauthorized();
    expect(listener).toHaveBeenCalledTimes(1);

    unsub();
    tokenStore.notifyUnauthorized();
    expect(listener).toHaveBeenCalledTimes(1);
  });
});
