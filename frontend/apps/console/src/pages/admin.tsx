import * as React from "react";
import {
  Users,
  Shield,
  FileText,
  Lock,
  Unlock,
  LogOut,
  Download,
  Search,
  Building2,
  CheckCircle2,
  Copy,
  Check,
  Globe,
  Clock,
} from "lucide-react";
import {
  useAdminUsersQuery,
  useLockUserMutation,
  useUnlockUserMutation,
  useForceLogoutMutation,
  useAdminAuditLogsQuery,
  useAdminSessionsQuery,
} from "@/api/hooks/use-admin-query";
import { useSubscriptionQuery } from "@/api/hooks/use-analytics-query";
import { useAuth } from "@/context/auth-context";
import { adminService } from "@/api/services/admin.service";
import { Button } from "@/components/ui/button";
import { Card, CardHeader, CardTitle, CardDescription, CardContent } from "@/components/ui/card";
import { Table, TableHeader, TableBody, TableHead, TableRow, TableCell } from "@/components/ui/table";
import { Badge } from "@/components/ui/badge";
import { MetricCard } from "@/components/ui/metric-card";
import { Input } from "@/components/ui/input";
import { Tabs, TabsList, TabsTrigger, TabsContent } from "@/components/ui/tabs";
import { LoadingState } from "@/components/feedback/loading-state";
import { ErrorState } from "@/components/ui/error-state";
import { PermissionDeniedState } from "@/components/feedback/permission-denied-state";
import { ConfirmDialog } from "@/components/feedback/confirm-dialog";
import { DataGrid, type ColumnDef } from "@/components/ui/data-grid";
import { formatDateTime } from "@/lib/utils";
import type { AdminUserItem, AdminAuditLogItem, AdminSessionItem } from "@/api/services/admin.service";

// Enterprise RBAC & PBAC Role Definitions
const ENTERPRISE_ROLES: {
  role: string;
  label: string;
  description: string;
  permissions: string[];
}[] = [
  {
    role: "admin",
    label: "Platform Admin",
    description: "Unrestricted administrative authority across all tenants and operations.",
    permissions: ["*"],
  },
  {
    role: "tenant_admin",
    label: "Tenant Admin",
    description: "Full control over organization members, role mappings, and audit exports.",
    permissions: ["users:read", "users:write", "sessions:read", "audit:export", "finops:*", "billing:*"],
  },
  {
    role: "finops_analyst",
    label: "FinOps Analyst",
    description: "Governance of token spend, budget thresholds, and cost reconciliation.",
    permissions: ["finops:read", "finops:write", "billing:read", "analytics:read"],
  },
  {
    role: "developer",
    label: "Developer",
    description: "Manage BYOK credentials, orchestrate agent tasks, and query knowledge bases.",
    permissions: ["byok:read", "byok:write", "agent:read", "agent:write", "rag:read", "rag:write"],
  },
  {
    role: "member",
    label: "Standard Member",
    description: "General access to chat streaming, standard RAG retrieval, and agent execution.",
    permissions: ["chat:read", "chat:write", "agent:read", "rag:read"],
  },
  {
    role: "viewer",
    label: "Audit Viewer",
    description: "Read-only inspection of dashboards and personal audit trails.",
    permissions: ["analytics:read", "read:workspace"],
  },
];

export default function AdminPage() {
  const { user, workspaces, activeWorkspace, switchWorkspace, can, hasRole } = useAuth();

  // Active Tab
  const [activeTab, setActiveTab] = React.useState("users");

  // Filter & Search states
  const [userSearch, setUserSearch] = React.useState("");
  const [userRoleFilter, setUserRoleFilter] = React.useState<string>("all");
  const [auditFilter, setAuditFilter] = React.useState<string>("all");
  const [copiedHash, setCopiedHash] = React.useState<string | null>(null);

  // Confirmation Dialog States
  const [lockTarget, setLockTarget] = React.useState<AdminUserItem | null>(null);
  const [forceLogoutTarget, setForceLogoutTarget] = React.useState<AdminUserItem | null>(null);
  const [exportingAudit, setExportingAudit] = React.useState(false);

  // Authorization Check
  const canAccessAdmin = hasRole(["admin", "tenant_admin"]) || can("admin:read") || can("users:read");
  const canWriteUsers = can("users:write") || hasRole(["admin", "tenant_admin"]);
  const canExportAudit = can("audit:export") || hasRole(["admin", "tenant_admin"]);

  // Queries
  const {
    data: users = [],
    isLoading: isUsersLoading,
    isError: isUsersError,
    error: usersError,
    refetch: refetchUsers,
  } = useAdminUsersQuery({ search: userSearch }, canAccessAdmin);

  const {
    data: auditLogs = [],
    isLoading: isAuditLoading,
    isError: isAuditError,
    error: auditError,
    refetch: refetchAudit,
  } = useAdminAuditLogsQuery(undefined, canAccessAdmin);

  const {
    data: sessions = [],
    isLoading: isSessionsLoading,
  } = useAdminSessionsQuery(canAccessAdmin);

  const { data: subscription } = useSubscriptionQuery();

  // Mutations
  const lockMutation = useLockUserMutation();
  const unlockMutation = useUnlockUserMutation();
  const forceLogoutMutation = useForceLogoutMutation();

  // Copy helper
  const handleCopy = (text: string) => {
    navigator.clipboard.writeText(text);
    setCopiedHash(text);
    setTimeout(() => setCopiedHash(null), 2000);
  };

  // Export audit handler
  const handleExportAuditLogs = async (format: "csv" | "ndjson") => {
    try {
      setExportingAudit(true);
      const content = await adminService.exportAuditLogs(format);
      const blob = new Blob([content], {
        type: format === "csv" ? "text/csv" : "application/x-ndjson",
      });
      const url = URL.createObjectURL(blob);
      const a = document.createElement("a");
      a.href = url;
      a.download = `audit_logs_${new Date().toISOString().split("T")[0]}.${format}`;
      document.body.appendChild(a);
      a.click();
      document.body.removeChild(a);
      URL.revokeObjectURL(url);
    } catch {
      // Export failed
    } finally {
      setExportingAudit(false);
    }
  };

  // Lock user action
  const handleConfirmLock = async () => {
    if (!lockTarget) return;
    await lockMutation.mutateAsync({ userId: lockTarget.id, durationSeconds: 3600 });
    setLockTarget(null);
  };

  // Force logout action
  const handleConfirmForceLogout = async () => {
    if (!forceLogoutTarget) return;
    await forceLogoutMutation.mutateAsync(forceLogoutTarget.id);
    setForceLogoutTarget(null);
  };

  // Permission Guard
  if (!canAccessAdmin) {
    return (
      <PermissionDeniedState
        title="Admin Console Access Restricted"
        description="Your current role does not have administrative permissions to view tenant administration and security logs."
        requiredRoles={["admin", "tenant_admin"]}
      />
    );
  }

  // Filtered Users
  const userItems = Array.isArray(users) ? users : (users as { items?: AdminUserItem[] }).items || [];
  const filteredUsers = userItems.filter((u) => {
    const matchesSearch =
      !userSearch.trim() ||
      u.username.toLowerCase().includes(userSearch.toLowerCase()) ||
      u.email.toLowerCase().includes(userSearch.toLowerCase()) ||
      (u.fullName && u.fullName.toLowerCase().includes(userSearch.toLowerCase()));
    const matchesRole = userRoleFilter === "all" || u.role === userRoleFilter;
    return matchesSearch && matchesRole;
  });

  // Filtered Audit Logs
  const auditItems = Array.isArray(auditLogs) ? auditLogs : (auditLogs as { items?: AdminAuditLogItem[] }).items || [];
  const filteredAuditLogs = auditItems.filter((log) => {
    if (auditFilter === "all") return true;
    if (auditFilter === "success") return log.success;
    if (auditFilter === "failure") return !log.success;
    return log.action.toLowerCase() === auditFilter.toLowerCase();
  });

  // DataGrid Columns for Audit Logs
  const auditColumns: ColumnDef<AdminAuditLogItem>[] = [
    {
      key: "createdAt",
      header: "Timestamp",
      render: (log) => (
        <span className="font-mono text-xs text-muted-foreground whitespace-nowrap">
          {formatDateTime(log.createdAt)}
        </span>
      ),
      sortable: true,
    },
    {
      key: "action",
      header: "Action / Event",
      render: (log) => (
        <Badge variant="outline" className="font-mono text-[10px] uppercase">
          {log.action}
        </Badge>
      ),
      sortable: true,
    },
    {
      key: "email",
      header: "Actor",
      render: (log) => (
        <span className="font-mono text-xs text-foreground">
          {log.email || (log.userId ? `User #${log.userId}` : "System / Anonymous")}
        </span>
      ),
      sortable: true,
    },
    {
      key: "resource",
      header: "Resource / Detail",
      render: (log) => (
        <span className="text-xs text-muted-foreground truncate max-w-[200px] block" title={log.detail || log.resource}>
          {log.detail || log.resource}
        </span>
      ),
      sortable: true,
    },
    {
      key: "success",
      header: "Result",
      render: (log) => (
        <Badge
          variant={log.success ? "success" : "destructive"}
          className="text-[10px] uppercase font-mono"
        >
          {log.success ? "Success" : "Failed"}
        </Badge>
      ),
      sortable: true,
    },
    {
      key: "ipAddress",
      header: "IP Address",
      render: (log) => (
        <span className="font-mono text-xs text-muted-foreground">
          {log.ipAddress}
        </span>
      ),
    },
    {
      key: "recordHash",
      header: "Integrity Hash / CID",
      render: (log) => {
        const hash = log.recordHash || log.correlationId;
        if (!hash) return <span className="text-muted-foreground text-xs">—</span>;
        const isCopied = copiedHash === hash;
        return (
          <div className="flex items-center space-x-1">
            <code className="font-mono text-[11px] text-muted-foreground">
              {hash.slice(0, 10)}...
            </code>
            <button
              type="button"
              onClick={() => handleCopy(hash)}
              className="text-muted-foreground hover:text-foreground p-1"
              title="Copy integrity hash"
              aria-label="Copy integrity hash"
            >
              {isCopied ? <Check className="h-3 w-3 text-emerald-500" /> : <Copy className="h-3 w-3" />}
            </button>
          </div>
        );
      },
    },
  ];

  return (
    <div className="space-y-8">
      {/* Header */}
      <div className="flex flex-col sm:flex-row sm:items-center sm:justify-between gap-4">
        <div>
          <div className="flex items-center space-x-2">
            <h1 className="text-2xl font-bold tracking-tight">Enterprise Administration & Security</h1>
            <Badge variant="default" className="text-[10px] font-mono uppercase">
              Admin Restricted
            </Badge>
          </div>
          <p className="text-sm text-muted-foreground mt-1">
            Tenant governance, user account access, multi-tenant boundaries, RBAC matrix, and immutable audit trails.
          </p>
        </div>
      </div>

      {/* Overview Metrics Cards */}
      <div className="grid grid-cols-1 sm:grid-cols-2 lg:grid-cols-4 gap-4">
        <MetricCard
          title="Active Tenant Users"
          value={String(userItems.length)}
          change={{ value: `${userItems.filter((u) => u.isLocked).length} locked`, trend: "neutral", label: "status" }}
          icon={Users}
        />
        <MetricCard
          title="Active Tenant Sessions"
          value={String(sessions.length)}
          change={{ value: "live devices", trend: "neutral", label: "authenticated" }}
          icon={Globe}
        />
        <MetricCard
          title="Tenant Workspaces"
          value={String(workspaces.length)}
          change={{ value: activeWorkspace?.slug || "core", trend: "neutral", label: "active scope" }}
          icon={Building2}
        />
        <MetricCard
          title="Audit Trail Logs"
          value={String(auditItems.length)}
          change={{ value: "tamper-evident", trend: "neutral", label: "HMAC verified" }}
          icon={FileText}
        />
      </div>

      {/* Administration Tabs */}
      <Tabs value={activeTab} onValueChange={setActiveTab}>
        <TabsList className="grid grid-cols-2 sm:grid-cols-5 w-full max-w-2xl">
          <TabsTrigger value="users" className="text-xs">
            <Users className="h-3.5 w-3.5 mr-1.5" />
            Users
          </TabsTrigger>
          <TabsTrigger value="tenants" className="text-xs">
            <Building2 className="h-3.5 w-3.5 mr-1.5" />
            Tenants
          </TabsTrigger>
          <TabsTrigger value="roles" className="text-xs">
            <Shield className="h-3.5 w-3.5 mr-1.5" />
            Roles & Matrix
          </TabsTrigger>
          <TabsTrigger value="audit" className="text-xs">
            <FileText className="h-3.5 w-3.5 mr-1.5" />
            Audit Logs
          </TabsTrigger>
          <TabsTrigger value="sessions" className="text-xs">
            <Clock className="h-3.5 w-3.5 mr-1.5" />
            Sessions
          </TabsTrigger>
        </TabsList>

        {/* TAB 1: USERS */}
        <TabsContent value="users" className="mt-6 space-y-4">
          <Card>
            <CardHeader className="pb-4">
              <div className="flex flex-col sm:flex-row sm:items-center sm:justify-between gap-3">
                <div>
                  <CardTitle className="text-base">Tenant User Accounts</CardTitle>
                  <CardDescription>
                    Manage users, account locking, and session invalidation under the current tenant boundary.
                  </CardDescription>
                </div>
                {/* Search & Role Filter */}
                <div className="flex items-center space-x-2">
                  <div className="relative w-48 sm:w-60">
                    <Input
                      type="text"
                      placeholder="Search users..."
                      value={userSearch}
                      onChange={(e) => setUserSearch(e.target.value)}
                      leftAdornment={<Search className="h-4 w-4 text-muted-foreground" />}
                      className="h-8 text-xs"
                    />
                  </div>
                  <select
                    value={userRoleFilter}
                    onChange={(e) => setUserRoleFilter(e.target.value)}
                    className="h-8 rounded-md border border-input bg-background px-2.5 text-xs text-foreground focus:outline-none focus:ring-1 focus:ring-ring"
                    aria-label="Filter users by role"
                  >
                    <option value="all">All Roles</option>
                    <option value="admin">Admin</option>
                    <option value="tenant_admin">Tenant Admin</option>
                    <option value="finops_analyst">FinOps Analyst</option>
                    <option value="developer">Developer</option>
                    <option value="member">Member</option>
                    <option value="viewer">Viewer</option>
                  </select>
                </div>
              </div>
            </CardHeader>
            <CardContent>
              {isUsersLoading ? (
                <LoadingState message="Loading tenant user directory..." />
              ) : isUsersError ? (
                <ErrorState
                  title="Failed to Load Users"
                  message="Could not retrieve organization members."
                  error={usersError}
                  onRetry={refetchUsers}
                />
              ) : filteredUsers.length === 0 ? (
                <div className="py-12 text-center text-xs text-muted-foreground">
                  No matching tenant users found.
                </div>
              ) : (
                <Table>
                  <TableHeader>
                    <TableRow>
                      <TableHead>User</TableHead>
                      <TableHead>Email</TableHead>
                      <TableHead>Role</TableHead>
                      <TableHead>Account Status</TableHead>
                      <TableHead>Registered</TableHead>
                      <TableHead className="text-right">Actions</TableHead>
                    </TableRow>
                  </TableHeader>
                  <TableBody>
                    {filteredUsers.map((u) => {
                      const isCurrentUser = u.id === user?.id || u.email === user?.email;
                      const isLocked = u.isLocked;

                      return (
                        <TableRow key={u.id}>
                          <TableCell>
                            <div>
                              <span className="font-semibold text-xs text-foreground block">
                                {u.fullName || u.username}
                              </span>
                              <span className="text-[11px] text-muted-foreground font-mono">
                                @{u.username}
                              </span>
                            </div>
                          </TableCell>
                          <TableCell className="font-mono text-xs text-muted-foreground">
                            {u.email}
                          </TableCell>
                          <TableCell>
                            <Badge variant="secondary" className="font-mono text-[10px] uppercase">
                              {u.role}
                            </Badge>
                          </TableCell>
                          <TableCell>
                            {isLocked ? (
                              <Badge variant="destructive" className="text-[10px]">
                                Locked
                              </Badge>
                            ) : (
                              <Badge variant="success" className="text-[10px]">
                                Active
                              </Badge>
                            )}
                          </TableCell>
                          <TableCell className="text-xs text-muted-foreground font-mono">
                            {formatDateTime(u.createdAt)}
                          </TableCell>
                          <TableCell className="text-right">
                            {canWriteUsers ? (
                              <div className="flex items-center justify-end space-x-1">
                                {isLocked ? (
                                  <Button
                                    variant="outline"
                                    size="sm"
                                    className="h-7 text-xs"
                                    onClick={() => unlockMutation.mutate(u.id)}
                                    disabled={unlockMutation.isPending}
                                    leftIcon={<Unlock className="h-3 w-3" />}
                                  >
                                    Unlock
                                  </Button>
                                ) : (
                                  <Button
                                    variant="outline"
                                    size="sm"
                                    className="h-7 text-xs text-amber-600 hover:text-amber-700 dark:text-amber-400"
                                    onClick={() => setLockTarget(u)}
                                    disabled={isCurrentUser || lockMutation.isPending}
                                    leftIcon={<Lock className="h-3 w-3" />}
                                  >
                                    Lock
                                  </Button>
                                )}

                                <Button
                                  variant="ghost"
                                  size="sm"
                                  className="h-7 text-xs text-destructive hover:bg-destructive/10"
                                  onClick={() => setForceLogoutTarget(u)}
                                  disabled={isCurrentUser || forceLogoutMutation.isPending}
                                  title="Revoke all active sessions for this user"
                                >
                                  <LogOut className="h-3 w-3" />
                                </Button>
                              </div>
                            ) : (
                              <span className="text-xs text-muted-foreground">Read-only</span>
                            )}
                          </TableCell>
                        </TableRow>
                      );
                    })}
                  </TableBody>
                </Table>
              )}
            </CardContent>
          </Card>
        </TabsContent>

        {/* TAB 2: TENANTS & BOUNDARIES */}
        <TabsContent value="tenants" className="mt-6 space-y-6">
          <Card>
            <CardHeader>
              <CardTitle className="text-base flex items-center space-x-2">
                <Building2 className="h-4 w-4 text-primary" />
                <span>Active Tenant Scope & Isolation</span>
              </CardTitle>
              <CardDescription>
                Cryptographically bound tenant context strictly enforced by FinnApiGo token verification.
              </CardDescription>
            </CardHeader>
            <CardContent className="space-y-6">
              <div className="grid grid-cols-1 sm:grid-cols-2 md:grid-cols-3 gap-4">
                <div className="p-3.5 rounded-lg border bg-muted/30 space-y-1">
                  <span className="text-xs text-muted-foreground block">Active Tenant ID</span>
                  <span className="font-mono text-sm font-bold text-foreground">
                    {user?.tenantId || activeWorkspace?.id || "default"}
                  </span>
                </div>

                <div className="p-3.5 rounded-lg border bg-muted/30 space-y-1">
                  <span className="text-xs text-muted-foreground block">Organization ID</span>
                  <span className="font-mono text-sm font-bold text-foreground">
                    {user?.orgId || "org_enterprise"}
                  </span>
                </div>

                <div className="p-3.5 rounded-lg border bg-muted/30 space-y-1">
                  <span className="text-xs text-muted-foreground block">Subscription Tier</span>
                  <span className="font-mono text-sm font-bold text-primary uppercase">
                    {subscription?.tier || activeWorkspace?.plan || "Enterprise"}
                  </span>
                </div>
              </div>

              {/* Authorized Tenant Workspaces Switcher */}
              <div>
                <h3 className="text-sm font-semibold mb-2">Authorized Tenant Workspaces</h3>
                <p className="text-xs text-muted-foreground mb-3">
                  You are authorized to access the following tenant environments. Switching tenants scopes all API headers to the selected boundary.
                </p>

                <div className="grid grid-cols-1 sm:grid-cols-3 gap-3">
                  {workspaces.map((ws) => {
                    const isActive = ws.id === activeWorkspace?.id;
                    return (
                      <div
                        key={ws.id}
                        onClick={() => !isActive && switchWorkspace(ws.id)}
                        className={`p-3.5 rounded-lg border transition-all cursor-pointer ${
                          isActive
                            ? "border-primary bg-primary/5 shadow-sm"
                            : "hover:border-primary/50 hover:bg-muted/30"
                        }`}
                      >
                        <div className="flex items-center justify-between">
                          <span className="font-semibold text-xs text-foreground">{ws.name}</span>
                          {isActive && <CheckCircle2 className="h-4 w-4 text-primary" />}
                        </div>
                        <span className="font-mono text-[11px] text-muted-foreground block mt-1">
                          {ws.id}
                        </span>
                        <div className="mt-2 flex items-center space-x-2">
                          <Badge variant="outline" className="text-[10px] font-mono">
                            {ws.environment}
                          </Badge>
                          <Badge variant="secondary" className="text-[10px] font-mono">
                            {ws.plan}
                          </Badge>
                        </div>
                      </div>
                    );
                  })}
                </div>
              </div>
            </CardContent>
          </Card>
        </TabsContent>

        {/* TAB 3: ROLES & CAPABILITY MATRIX */}
        <TabsContent value="roles" className="mt-6 space-y-6">
          <Card>
            <CardHeader>
              <CardTitle className="text-base flex items-center space-x-2">
                <Shield className="h-4 w-4 text-primary" />
                <span>Enterprise RBAC / PBAC Permission Matrix</span>
              </CardTitle>
              <CardDescription>
                Authoritative capability matrix governing UI features and upstream FastAPI/FinnApiGo route enforcement.
              </CardDescription>
            </CardHeader>
            <CardContent>
              <Table>
                <TableHeader>
                  <TableRow>
                    <TableHead>Role</TableHead>
                    <TableHead>Description</TableHead>
                    <TableHead>Fine-Grained Permissions</TableHead>
                  </TableRow>
                </TableHeader>
                <TableBody>
                  {ENTERPRISE_ROLES.map((r) => (
                    <TableRow key={r.role}>
                      <TableCell className="font-semibold text-xs">
                        <div>
                          <span>{r.label}</span>
                          <span className="font-mono text-[10px] text-muted-foreground block">
                            {r.role}
                          </span>
                        </div>
                      </TableCell>
                      <TableCell className="text-xs text-muted-foreground max-w-xs">
                        {r.description}
                      </TableCell>
                      <TableCell>
                        <div className="flex flex-wrap gap-1">
                          {r.permissions.map((p) => (
                            <Badge key={p} variant="outline" className="font-mono text-[10px]">
                              {p}
                            </Badge>
                          ))}
                        </div>
                      </TableCell>
                    </TableRow>
                  ))}
                </TableBody>
              </Table>

              {/* Active Caller Claims Inspector */}
              <div className="mt-6 p-4 rounded-lg bg-muted/40 border">
                <h4 className="text-xs font-bold uppercase tracking-wider text-muted-foreground mb-2">
                  My Active Session Claims
                </h4>
                <div className="grid grid-cols-1 sm:grid-cols-2 gap-3 text-xs">
                  <div>
                    <span className="text-muted-foreground block mb-1">Assigned Roles:</span>
                    <div className="flex flex-wrap gap-1">
                      {(user?.roles || []).map((role) => (
                        <Badge key={role} variant="default" className="font-mono text-[10px]">
                          {role}
                        </Badge>
                      ))}
                    </div>
                  </div>
                  <div>
                    <span className="text-muted-foreground block mb-1">Effective Permissions:</span>
                    <div className="flex flex-wrap gap-1">
                      {(user?.permissions || []).map((perm) => (
                        <Badge key={perm} variant="secondary" className="font-mono text-[10px]">
                          {perm}
                        </Badge>
                      ))}
                    </div>
                  </div>
                </div>
              </div>
            </CardContent>
          </Card>
        </TabsContent>

        {/* TAB 4: AUDIT LOGS */}
        <TabsContent value="audit" className="mt-6 space-y-4">
          <Card>
            <CardHeader className="pb-4">
              <div className="flex flex-col sm:flex-row sm:items-center sm:justify-between gap-3">
                <div>
                  <CardTitle className="text-base flex items-center space-x-2">
                    <FileText className="h-4 w-4 text-primary" />
                    <span>Immutable Audit Log Trail</span>
                  </CardTitle>
                  <CardDescription>
                    Tamper-evident security events recorded across authentication, BYOK vault, and FinOps actions.
                  </CardDescription>
                </div>
                <div className="flex items-center space-x-2">
                  <select
                    value={auditFilter}
                    onChange={(e) => setAuditFilter(e.target.value)}
                    className="h-8 rounded-md border border-input bg-background px-2.5 text-xs text-foreground focus:outline-none focus:ring-1 focus:ring-ring"
                    aria-label="Filter audit logs by event status"
                  >
                    <option value="all">All Events</option>
                    <option value="success">Success Only</option>
                    <option value="failure">Failures Only</option>
                    <option value="login">Logins</option>
                    <option value="byok_rotate">BYOK Operations</option>
                    <option value="budget_update">Budget Changes</option>
                  </select>

                  {canExportAudit && (
                    <div className="flex items-center space-x-1">
                      <Button
                        size="sm"
                        variant="outline"
                        onClick={() => handleExportAuditLogs("csv")}
                        disabled={exportingAudit}
                        leftIcon={<Download className="h-3.5 w-3.5" />}
                        className="h-8 text-xs"
                      >
                        CSV
                      </Button>
                      <Button
                        size="sm"
                        variant="outline"
                        onClick={() => handleExportAuditLogs("ndjson")}
                        disabled={exportingAudit}
                        leftIcon={<Download className="h-3.5 w-3.5" />}
                        className="h-8 text-xs"
                      >
                        NDJSON
                      </Button>
                    </div>
                  )}
                </div>
              </div>
            </CardHeader>
            <CardContent>
              {isAuditLoading ? (
                <LoadingState message="Fetching security audit events..." />
              ) : isAuditError ? (
                <ErrorState
                  title="Failed to Load Audit Logs"
                  message="Could not stream security events from backend."
                  error={auditError}
                  onRetry={refetchAudit}
                />
              ) : filteredAuditLogs.length === 0 ? (
                <div className="py-12 text-center text-xs text-muted-foreground">
                  No matching audit records found.
                </div>
              ) : (
                <DataGrid
                  data={filteredAuditLogs}
                  columns={auditColumns}
                  pageSize={10}
                  searchPlaceholder="Filter audit records by actor, action, or resource..."
                />
              )}
            </CardContent>
          </Card>
        </TabsContent>

        {/* TAB 5: ACTIVE SESSIONS */}
        <TabsContent value="sessions" className="mt-6 space-y-4">
          <Card>
            <CardHeader>
              <CardTitle className="text-base flex items-center space-x-2">
                <Clock className="h-4 w-4 text-primary" />
                <span>Active Tenant Sessions</span>
              </CardTitle>
              <CardDescription>
                Live authenticated device sessions within the organization.
              </CardDescription>
            </CardHeader>
            <CardContent>
              {isSessionsLoading ? (
                <LoadingState message="Querying active sessions..." />
              ) : sessions.length === 0 ? (
                <div className="py-8 text-center text-xs text-muted-foreground">
                  No other active device sessions found.
                </div>
              ) : (
                <Table>
                  <TableHeader>
                    <TableRow>
                      <TableHead>Session ID</TableHead>
                      <TableHead>User</TableHead>
                      <TableHead>IP Address</TableHead>
                      <TableHead>User Agent</TableHead>
                      <TableHead>Logged In</TableHead>
                      <TableHead>Expires</TableHead>
                    </TableRow>
                  </TableHeader>
                  <TableBody>
                    {sessions.map((s: AdminSessionItem) => (
                      <TableRow key={s.id}>
                        <TableCell className="font-mono text-xs font-semibold">
                          {s.id}
                        </TableCell>
                        <TableCell className="font-medium text-xs">
                          {s.username} (ID: {s.userId})
                        </TableCell>
                        <TableCell className="font-mono text-xs text-muted-foreground">
                          {s.ipAddress}
                        </TableCell>
                        <TableCell className="text-xs text-muted-foreground max-w-xs truncate" title={s.userAgent}>
                          {s.userAgent}
                        </TableCell>
                        <TableCell className="font-mono text-xs text-muted-foreground">
                          {formatDateTime(s.createdAt)}
                        </TableCell>
                        <TableCell className="font-mono text-xs text-muted-foreground">
                          {formatDateTime(s.expiresAt)}
                        </TableCell>
                      </TableRow>
                    ))}
                  </TableBody>
                </Table>
              )}
            </CardContent>
          </Card>
        </TabsContent>
      </Tabs>

      {/* Lock User Confirmation Dialog */}
      <ConfirmDialog
        open={Boolean(lockTarget)}
        onOpenChange={(open) => !open && setLockTarget(null)}
        title="Lock User Account"
        description={`Are you sure you want to temporarily suspend access for ${lockTarget?.fullName || lockTarget?.username}? They will be unable to log in until unlocked.`}
        confirmLabel="Lock Account"
        variant="warning"
        onConfirm={handleConfirmLock}
        isLoading={lockMutation.isPending}
      />

      {/* Force Logout Destructive Confirmation Dialog */}
      <ConfirmDialog
        open={Boolean(forceLogoutTarget)}
        onOpenChange={(open) => !open && setForceLogoutTarget(null)}
        title="Force Logout User Across All Devices"
        description={`This will immediately revoke all active refresh tokens and denylist access tokens for ${forceLogoutTarget?.fullName || forceLogoutTarget?.username}. The user will be immediately disconnected.`}
        confirmLabel="Revoke All Sessions"
        variant="destructive"
        onConfirm={handleConfirmForceLogout}
        isLoading={forceLogoutMutation.isPending}
      />
    </div>
  );
}
