export interface User {
  id: string;
  email: string;
  name: string;
  avatarUrl?: string;
  tenantId: string;
  orgId?: string;
  roles: string[];
  permissions: string[];
}

export interface Workspace {
  id: string;
  name: string;
  slug: string;
  plan: "starter" | "team" | "enterprise";
  environment: "production" | "staging" | "development";
}

export interface AuthState {
  isAuthenticated: boolean;
  isLoading: boolean;
  user: User | null;
  workspaces: Workspace[];
  activeWorkspace: Workspace | null;
}

export interface AuthContextValue extends AuthState {
  login: (email: string, password?: string) => Promise<void>;
  logout: () => void;
  switchWorkspace: (workspaceId: string) => void;
  hasRole: (role: string | string[]) => boolean;
  hasPermission: (permission: string | string[]) => boolean;
}
