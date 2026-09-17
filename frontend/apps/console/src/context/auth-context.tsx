import React, { createContext, useContext, useState, useCallback, useMemo } from "react";
import type { User, Workspace, AuthContextValue } from "@/types/auth";

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
      return localStorage.getItem("jakeai-active-workspace") || DEFAULT_WORKSPACES[0].id;
    } catch {
      return DEFAULT_WORKSPACES[0].id;
    }
  });

  const activeWorkspace = useMemo(() => {
    return workspaces.find((w) => w.id === activeWorkspaceId) || workspaces[0] || null;
  }, [workspaces, activeWorkspaceId]);

  const login = useCallback(async (email: string, _password?: string) => {
    setIsLoading(true);
    try {
      // Simulate credential verification without storing tokens in unsafe localStorage
      await new Promise((resolve) => setTimeout(resolve, 300));
      const loggedUser: User = {
        id: `usr_${Math.random().toString(36).substring(2, 9)}`,
        name: email.split("@")[0].replace(".", " ").replace(/^\w/, (c) => c.toUpperCase()),
        email,
        tenantId: activeWorkspaceId,
        roles: email.includes("admin") ? ["admin", "tenant_admin"] : ["member"],
        permissions: email.includes("admin") ? ["*"] : ["read:workspace", "read:agent"],
      };
      setUser(loggedUser);
      setIsAuthenticated(true);
    } finally {
      setIsLoading(false);
    }
  }, [activeWorkspaceId]);

  const logout = useCallback(() => {
    setUser(null);
    setIsAuthenticated(false);
  }, []);

  const switchWorkspace = useCallback((workspaceId: string) => {
    setActiveWorkspaceId(workspaceId);
    try {
      localStorage.setItem("jakeai-active-workspace", workspaceId);
    } catch {
      // Ignore storage errors
    }
  }, []);

  const hasRole = useCallback(
    (requiredRole: string | string[]): boolean => {
      if (!user || !user.roles) return false;
      if (user.roles.includes("admin") || user.roles.includes("tenant_admin")) return true;
      const rolesToCheck = Array.isArray(requiredRole) ? requiredRole : [requiredRole];
      return rolesToCheck.some((r) => user.roles.includes(r));
    },
    [user]
  );

  const hasPermission = useCallback(
    (requiredPermission: string | string[]): boolean => {
      if (!user || !user.permissions) return false;
      if (user.permissions.includes("*")) return true;
      if (user.roles.includes("admin") || user.roles.includes("tenant_admin")) return true;
      const permsToCheck = Array.isArray(requiredPermission) ? requiredPermission : [requiredPermission];
      return permsToCheck.every((p) => user.permissions.includes(p));
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
