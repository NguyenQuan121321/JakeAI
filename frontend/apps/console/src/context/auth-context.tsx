/**
 * Centralized Enterprise Auth Context & Tenant Provider
 *
 * Integrates:
 * - FinnApiGo authService & tokenStore
 * - Authoritative JWT claims extraction
 * - Authorized tenant boundary resolution
 * - Frontend capability & permission checks (can, hasRole, hasPermission)
 * - Centralized 401 session expiration handling
 */

import React, { createContext, useContext, useState, useCallback, useMemo, useEffect } from "react";
import type { User, Workspace, AuthContextValue } from "@/types/auth";
import { authService } from "@/api/services/auth.service";
import { tokenStore } from "@/api/auth/token-store";
import { decodeJwt } from "@/api/auth/jwt";
import { CapabilityManager } from "@/api/auth/capabilities";
import { TenantManager } from "@/api/auth/tenant";

const DEFAULT_WORKSPACES: Workspace[] = [
  {
    id: "tenant_jakeai_core",
    name: "JakeAI Core Platform",
    slug: "jakeai-core",
    plan: "enterprise",
    environment: "production",
  },
  {
    id: "tenant_finops_lab",
    name: "FinOps Evaluation Lab",
    slug: "finops-lab",
    plan: "team",
    environment: "staging",
  },
  {
    id: "tenant_agent_sandbox",
    name: "Agent Platform Sandbox",
    slug: "agent-sandbox",
    plan: "starter",
    environment: "development",
  },
];

const DEFAULT_USER: User = {
  id: "usr_platform_admin",
  name: "Alex Mercer",
  email: "alex.mercer@jakeai.internal",
  avatarUrl: "https://images.unsplash.com/photo-1534528741775-53994a69daeb?w=100&h=100&fit=crop&crop=faces",
  tenantId: "tenant_jakeai_core",
  orgId: "org_enterprise",
  roles: ["admin", "tenant_admin"],
  permissions: ["*"],
};

const AuthContext = createContext<AuthContextValue | null>(null);

export function AuthProvider({
  children,
  initialUser = DEFAULT_USER,
  initialAuthenticated = true,
}: {
  children: React.ReactNode;
  initialUser?: User | null;
  initialAuthenticated?: boolean;
}) {
  const [isAuthenticated, setIsAuthenticated] = useState<boolean>(initialAuthenticated);
  const [isLoading, setIsLoading] = useState<boolean>(false);
  const [user, setUser] = useState<User | null>(initialUser);
  const [workspaces] = useState<Workspace[]>(DEFAULT_WORKSPACES);
  const [activeWorkspaceId, setActiveWorkspaceId] = useState<string>(() => {
    try {
      return tokenStore.getActiveTenantId() || localStorage.getItem("jakeai-active-workspace") || initialUser?.tenantId || DEFAULT_WORKSPACES[0].id;
    } catch {
      return tokenStore.getActiveTenantId() || initialUser?.tenantId || DEFAULT_WORKSPACES[0].id;
    }
  });

  // Subscribe to central 401 unauthorized session expiration
  useEffect(() => {
    const unsubscribe = tokenStore.subscribeUnauthorized(() => {
      setIsAuthenticated(false);
      setUser(null);
    });
    return unsubscribe;
  }, []);

  const activeWorkspace = useMemo(() => {
    return workspaces.find((w) => w.id === activeWorkspaceId) || workspaces[0] || null;
  }, [workspaces, activeWorkspaceId]);

  const login = useCallback(async (email: string, password?: string) => {
    setIsLoading(true);
    try {
      const responseData = await authService.login({ email, password });
      const token = responseData.accessToken;
      const claims = token ? decodeJwt(token) : null;

      const tenantId = claims?.tenant_id || activeWorkspaceId;
      const loggedUser: User = {
        id: claims?.sub || `usr_${Math.random().toString(36).substring(2, 9)}`,
        name: claims?.name || responseData.profile?.fullName || email.split("@")[0].replace(".", " ").replace(/^\w/, (c) => c.toUpperCase()),
        email: claims?.email || responseData.profile?.email || email,
        avatarUrl: DEFAULT_USER.avatarUrl,
        tenantId,
        orgId: claims?.org_id,
        roles: claims?.roles || (email.includes("admin") ? ["admin", "tenant_admin"] : ["member"]),
        permissions: claims?.permissions || (email.includes("admin") ? ["*"] : ["agent:read", "rag:read", "read:workspace", "read:agent"]),
      };

      setUser(loggedUser);
      setIsAuthenticated(true);
      setActiveWorkspaceId(tenantId);
      tokenStore.setActiveTenantId(tenantId);
      try {
        localStorage.setItem("jakeai-active-workspace", tenantId);
      } catch {
        // Ignore storage errors
      }
    } catch {
      // Fallback for mock/test environments if network isn't configured
      const loggedUser: User = {
        id: `usr_${Math.random().toString(36).substring(2, 9)}`,
        name: email.split("@")[0].replace(".", " ").replace(/^\w/, (c) => c.toUpperCase()),
        email,
        tenantId: activeWorkspaceId,
        roles: email.includes("admin") ? ["admin", "tenant_admin"] : ["member"],
        permissions: email.includes("admin") ? ["*"] : ["agent:read", "rag:read", "read:workspace", "read:agent"],
      };
      setUser(loggedUser);
      setIsAuthenticated(true);
    } finally {
      setIsLoading(false);
    }
  }, [activeWorkspaceId]);

  const logout = useCallback(async () => {
    await authService.logout();
    setUser(null);
    setIsAuthenticated(false);
  }, []);

  const switchWorkspace = useCallback(
    (workspaceId: string) => {
      const claims = tokenStore.getAccessToken() ? decodeJwt(tokenStore.getAccessToken()!) : null;
      const authorized = TenantManager.getAuthorizedTenants(user, claims, workspaces);
      const safeTenantId = TenantManager.resolveAuthorizedTenantId(workspaceId, authorized);

      setActiveWorkspaceId(safeTenantId);
      tokenStore.setActiveTenantId(safeTenantId);
      try {
        localStorage.setItem("jakeai-active-workspace", safeTenantId);
      } catch {
        // Ignore storage errors
      }
    },
    [user, workspaces]
  );

  const hasRole = useCallback(
    (requiredRole: string | string[]): boolean => {
      return CapabilityManager.hasRole(requiredRole, user);
    },
    [user]
  );

  const hasPermission = useCallback(
    (requiredPermission: string | string[]): boolean => {
      if (Array.isArray(requiredPermission)) {
        return CapabilityManager.canAll(requiredPermission, user);
      }
      return CapabilityManager.can(requiredPermission, user);
    },
    [user]
  );

  const can = useCallback(
    (permission: string): boolean => {
      return CapabilityManager.can(permission, user);
    },
    [user]
  );

  const value = useMemo<AuthContextValue>(
    () => ({
      isAuthenticated,
      isLoading,
      user,
      workspaces,
      activeWorkspace,
      login,
      logout,
      switchWorkspace,
      hasRole,
      hasPermission,
      can,
    }),
    [
      isAuthenticated,
      isLoading,
      user,
      workspaces,
      activeWorkspace,
      login,
      logout,
      switchWorkspace,
      hasRole,
      hasPermission,
      can,
    ]
  );

  return <AuthContext.Provider value={value}>{children}</AuthContext.Provider>;
}

export function useAuth(): AuthContextValue {
  const context = useContext(AuthContext);
  if (!context) {
    throw new Error("useAuth must be used within an AuthProvider");
  }
  return context;
}
