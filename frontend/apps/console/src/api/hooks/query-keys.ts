/**
 * Hierarchical TanStack Query Key Factories
 *
 * Ensures consistent cache scoping and granular cache invalidations across subsystems.
 */

export const queryKeys = {
  auth: {
    all: ["auth"] as const,
    me: () => [...queryKeys.auth.all, "me"] as const,
    sessions: () => [...queryKeys.auth.all, "sessions"] as const,
  },
  health: {
    all: ["health"] as const,
    root: () => [...queryKeys.health.all, "root"] as const,
    liveness: () => [...queryKeys.health.all, "liveness"] as const,
    readiness: () => [...queryKeys.health.all, "readiness"] as const,
    apiV1: () => [...queryKeys.health.all, "v1"] as const,
  },
  agent: {
    all: ["agent"] as const,
    tasks: (tenantId?: string) => [...queryKeys.agent.all, "tasks", { tenantId }] as const,
    task: (taskId: string) => [...queryKeys.agent.all, "task", taskId] as const,
    runs: (taskId: string) => [...queryKeys.agent.all, "task", taskId, "runs"] as const,
    run: (taskId: string, runId: string) => [...queryKeys.agent.all, "task", taskId, "runs", runId] as const,
    approvals: () => [...queryKeys.agent.all, "approvals"] as const,
    metrics: () => [...queryKeys.agent.all, "metrics"] as const,
  },
  gateway: {
    all: ["gateway"] as const,
    models: () => [...queryKeys.gateway.all, "models"] as const,
    quotas: (tenantId?: string) => [...queryKeys.gateway.all, "quotas", { tenantId }] as const,
  },
  byok: {
    all: ["byok"] as const,
    keys: (tenantId?: string) => [...queryKeys.byok.all, "keys", { tenantId }] as const,
    key: (provider: string) => [...queryKeys.byok.all, "key", provider] as const,
  },
  finops: {
    all: ["finops"] as const,
    summary: (tenantId?: string) => [...queryKeys.finops.all, "summary", { tenantId }] as const,
    budget: (tenantId?: string) => [...queryKeys.finops.all, "budget", { tenantId }] as const,
    transactions: (tenantId?: string) => [...queryKeys.finops.all, "transactions", { tenantId }] as const,
    reconciliation: (tenantId?: string) => [...queryKeys.finops.all, "reconciliation", { tenantId }] as const,
  },
  rag: {
    all: ["rag"] as const,
    tasks: () => [...queryKeys.rag.all, "tasks"] as const,
    task: (taskId: string) => [...queryKeys.rag.all, "task", taskId] as const,
  },
  analytics: {
    all: ["analytics"] as const,
    dashboard: (tenantId?: string) => [...queryKeys.analytics.all, "dashboard", { tenantId }] as const,
    metrics: () => [...queryKeys.analytics.all, "metrics"] as const,
    subscription: () => [...queryKeys.analytics.all, "subscription"] as const,
  },
  admin: {
    all: ["admin"] as const,
    users: () => [...queryKeys.admin.all, "users"] as const,
    auditLogs: () => [...queryKeys.admin.all, "audit-logs"] as const,
  },
};
