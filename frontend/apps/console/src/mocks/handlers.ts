/**
 * MSW (Mock Service Worker) Handlers
 *
 * Provides isolated mock implementations strictly adhering to backend contracts.
 * Used for tests and local development mock modes.
 * Invariant: Clearly separated from production API client code.
 */

import { http, HttpResponse } from "msw";

export const handlers = [
  // Health
  http.get("*/health", () => HttpResponse.json({ status: "healthy", environment: "test", timestamp: "2026-09-17T20:00:00Z" })),
  http.get("/health", () => HttpResponse.json({ status: "healthy", environment: "test", timestamp: "2026-09-17T20:00:00Z" })),
  http.get("*/health/live", () => HttpResponse.json({ status: "alive" })),
  http.get("/health/live", () => HttpResponse.json({ status: "alive" })),
  http.get("*/health/ready", () => HttpResponse.json({ status: "ready" })),
  http.get("/health/ready", () => HttpResponse.json({ status: "ready" })),
  http.get("*/api/v1/health", () => HttpResponse.json({ status: "healthy", environment: "test", version: "0.1.0" })),
  http.get("/api/v1/health", () => HttpResponse.json({ status: "healthy", environment: "test", version: "0.1.0" })),
  http.get("*/api/v1/health/live", () => HttpResponse.json({ status: "alive" })),
  http.get("/api/v1/health/live", () => HttpResponse.json({ status: "alive" })),
  http.get("*/api/v1/health/ready", () => HttpResponse.json({ status: "ready" })),
  http.get("/api/v1/health/ready", () => HttpResponse.json({ status: "ready" })),

  // Chat Streaming
  http.post("*/api/v1/chat/stream", async ({ request }) => handleChatStream(request)),
  http.post("/api/v1/chat/stream", async ({ request }) => handleChatStream(request)),


  // Auth (FinnApiGo)
  http.post("*/api/v1/auth/login", async ({ request }) => handleLogin(request)),
  http.post("/api/v1/auth/login", async ({ request }) => handleLogin(request)),

  http.post("*/api/v1/auth/refresh-token", async ({ request }) => handleRefresh(request)),
  http.post("/api/v1/auth/refresh-token", async ({ request }) => handleRefresh(request)),

  http.post("*/api/v1/auth/logout", () => HttpResponse.json({ code: 200, message: "logged out", data: null })),
  http.post("/api/v1/auth/logout", () => HttpResponse.json({ code: 200, message: "logged out", data: null })),

  http.get("*/api/v1/auth/me", () => handleMe()),
  http.get("/api/v1/auth/me", () => handleMe()),

  // Agent Platform
  http.get("*/api/v1/agent/approvals/pending", () => handleApprovals()),
  http.get("/api/v1/agent/approvals/pending", () => handleApprovals()),

  http.get("*/api/v1/agent/metrics", () => handleAgentMetrics()),
  http.get("/api/v1/agent/metrics", () => handleAgentMetrics()),

  http.post("*/api/v1/agent/tasks", async ({ request }) => handleCreateTask(request)),
  http.post("/api/v1/agent/tasks", async ({ request }) => handleCreateTask(request)),

  http.get("*/api/v1/agent/tasks/:taskId", ({ params }) => handleGetTask(params.taskId as string)),
  http.get("/api/v1/agent/tasks/:taskId", ({ params }) => handleGetTask(params.taskId as string)),

  http.post("*/api/v1/agent/tasks/:taskId/runs", ({ params }) => handleStartRun(params.taskId as string)),
  http.post("/api/v1/agent/tasks/:taskId/runs", ({ params }) => handleStartRun(params.taskId as string)),

  http.get("*/api/v1/agent/tasks/:taskId/runs/:runId", ({ params }) => handleGetRun(params.taskId as string, params.runId as string)),
  http.get("/api/v1/agent/tasks/:taskId/runs/:runId", ({ params }) => handleGetRun(params.taskId as string, params.runId as string)),

  http.get("*/api/v1/agent/tasks/:taskId/runs/:runId/events", ({ params }) => handleAgentRunEvents(params.taskId as string, params.runId as string)),
  http.get("/api/v1/agent/tasks/:taskId/runs/:runId/events", ({ params }) => handleAgentRunEvents(params.taskId as string, params.runId as string)),

  http.post("*/api/v1/agent/tasks/:taskId/runs/:runId/approvals/:approvalId", ({ params }) => handleDecideApproval(params.taskId as string, params.runId as string, params.approvalId as string)),
  http.post("/api/v1/agent/tasks/:taskId/runs/:runId/approvals/:approvalId", ({ params }) => handleDecideApproval(params.taskId as string, params.runId as string, params.approvalId as string)),

  http.post("*/api/v1/agent/tasks/:taskId/runs/:runId/cancel", ({ params }) => handleCancelRun(params.taskId as string, params.runId as string)),
  http.post("/api/v1/agent/tasks/:taskId/runs/:runId/cancel", ({ params }) => handleCancelRun(params.taskId as string, params.runId as string)),

  // Gateway & Models
  http.get("*/api/v1/gateway/models", () => handleModels()),
  http.get("/api/v1/gateway/models", () => handleModels()),

  http.get("*/api/v1/gateway/quotas", () => handleQuotas()),
  http.get("/api/v1/gateway/quotas", () => handleQuotas()),

  http.post("*/api/v1/gateway/quotas", async ({ request }) => handleUpdateQuota(request)),
  http.post("/api/v1/gateway/quotas", async ({ request }) => handleUpdateQuota(request)),

  // BYOK
  http.get("*/api/v1/byok/keys", () => handleByokKeys()),
  http.get("/api/v1/byok/keys", () => handleByokKeys()),

  http.post("*/api/v1/byok/keys", async ({ request }) => handleStoreByokKey(request)),
  http.post("/api/v1/byok/keys", async ({ request }) => handleStoreByokKey(request)),

  http.post("*/api/v1/byok/keys/validate", async ({ request }) => handleValidateCandidateKey(request)),
  http.post("/api/v1/byok/keys/validate", async ({ request }) => handleValidateCandidateKey(request)),

  http.post("*/api/v1/byok/keys/:provider/validate", ({ params }) => handleValidateExistingKey(params.provider as string)),
  http.post("/api/v1/byok/keys/:provider/validate", ({ params }) => handleValidateExistingKey(params.provider as string)),

  http.post("*/api/v1/byok/keys/:provider/rotate", async ({ params, request }) => handleRotateByokKey(params.provider as string, request)),
  http.post("/api/v1/byok/keys/:provider/rotate", async ({ params, request }) => handleRotateByokKey(params.provider as string, request)),

  http.post("*/api/v1/byok/keys/:provider/revoke", ({ params }) => handleRevokeByokKey(params.provider as string)),
  http.post("/api/v1/byok/keys/:provider/revoke", ({ params }) => handleRevokeByokKey(params.provider as string)),

  http.delete("*/api/v1/byok/keys/:provider", ({ params }) => handleDeleteByokKey(params.provider as string)),
  http.delete("/api/v1/byok/keys/:provider", ({ params }) => handleDeleteByokKey(params.provider as string)),

  // FinOps
  http.get("*/api/v1/finops/summary", () => handleFinopsSummary()),
  http.get("/api/v1/finops/summary", () => handleFinopsSummary()),

  http.get("*/api/v1/finops/budget", () => handleFinopsBudget()),
  http.get("/api/v1/finops/budget", () => handleFinopsBudget()),

  http.post("*/api/v1/finops/budget", async ({ request }) => handleUpdateBudget(request)),
  http.post("/api/v1/finops/budget", async ({ request }) => handleUpdateBudget(request)),

  http.get("*/api/v1/finops/transactions", () => handleTransactions()),
  http.get("/api/v1/finops/transactions", () => handleTransactions()),

  http.get("*/api/v1/finops/reconciliation", () => handleReconciliation()),
  http.get("/api/v1/finops/reconciliation", () => handleReconciliation()),

  // RAG Pipeline
  http.post("*/api/v1/rag/query", async ({ request }) => handleRagQuery(request)),
  http.post("/api/v1/rag/query", async ({ request }) => handleRagQuery(request)),

  http.post("*/api/v1/rag/generate", async ({ request }) => handleRagGenerate(request)),
  http.post("/api/v1/rag/generate", async ({ request }) => handleRagGenerate(request)),

  http.post("*/api/v1/rag/ingest", async ({ request }) => handleRagIngest(request)),
  http.post("/api/v1/rag/ingest", async ({ request }) => handleRagIngest(request)),

  http.get("*/api/v1/rag/tasks/:taskId", ({ params }) => handleGetRagTask(params.taskId as string)),
  http.get("/api/v1/rag/tasks/:taskId", ({ params }) => handleGetRagTask(params.taskId as string)),

  // Analytics & Billing
  http.get("*/api/v1/analytics/dashboard", () => HttpResponse.json({
    tenant_id: "tenant_jakeai_core",
    tokens_processed: 48200,
    tokens_saved_cache: 12000,
    cost_savings_usd: 14.5,
    savings_percentage: 24.5,
    prs_audited: 8,
    avg_ttft_ms: 220,
    model_distribution: { "gpt-4o": 40, "claude-3-5-sonnet": 60 },
    subscription_tier: "enterprise",
    tokens_saved_provider_cache: 5000,
    provider_cache_savings_usd: 6.2,
    provider_cache_hit_rate: 0.15,
  })),
  http.get("/api/v1/analytics/dashboard", () => HttpResponse.json({
    tenant_id: "tenant_jakeai_core",
    tokens_processed: 48200,
    tokens_saved_cache: 12000,
    cost_savings_usd: 14.5,
    savings_percentage: 24.5,
    prs_audited: 8,
    avg_ttft_ms: 220,
    model_distribution: { "gpt-4o": 40, "claude-3-5-sonnet": 60 },
    subscription_tier: "enterprise",
    tokens_saved_provider_cache: 5000,
    provider_cache_savings_usd: 6.2,
    provider_cache_hit_rate: 0.15,
  })),

  http.get("*/api/v1/analytics/metrics", () => HttpResponse.json({
    uptime_seconds: 86400,
  })),
  http.get("/api/v1/analytics/metrics", () => HttpResponse.json({
    uptime_seconds: 86400,
  })),

  http.get("*/api/v1/billing/subscription", () => HttpResponse.json({
    tenant_id: "tenant_jakeai_core",
    tier: "enterprise",
    plan_name: "Enterprise Dedicated",
    monthly_quota: 5000000,
    features: ["byok", "rag", "audit"],
    is_active: true,
    expires_at: null,
  })),
  http.get("/api/v1/billing/subscription", () => HttpResponse.json({
    tenant_id: "tenant_jakeai_core",
    tier: "enterprise",
    plan_name: "Enterprise Dedicated",
    monthly_quota: 5000000,
    features: ["byok", "rag", "audit"],
    is_active: true,
    expires_at: null,
  })),

  // Admin & Identity Governance
  http.get("*/api/v1/admin/users", ({ request }) => handleAdminUsers(new URL(request.url))),
  http.get("/api/v1/admin/users", ({ request }) => handleAdminUsers(new URL(request.url))),

  http.post("*/api/v1/admin/users/:id/lock", async ({ params, request }) => handleLockUser(params.id as string, request)),
  http.post("/api/v1/admin/users/:id/lock", async ({ params, request }) => handleLockUser(params.id as string, request)),

  http.post("*/api/v1/admin/users/:id/unlock", ({ params }) => handleUnlockUser(params.id as string)),
  http.post("/api/v1/admin/users/:id/unlock", ({ params }) => handleUnlockUser(params.id as string)),

  http.post("*/api/v1/admin/users/:id/force-logout", ({ params }) => handleForceLogout(params.id as string)),
  http.post("/api/v1/admin/users/:id/force-logout", ({ params }) => handleForceLogout(params.id as string)),

  http.get("*/api/v1/admin/sessions", () => handleAdminSessions()),
  http.get("/api/v1/admin/sessions", () => handleAdminSessions()),

  http.get("*/api/v1/admin/audit-log/export", ({ request }) => handleExportAudit(request)),
  http.get("/api/v1/admin/audit-log/export", ({ request }) => handleExportAudit(request)),

  http.get("*/api/v1/admin/audit-log", ({ request }) => handleAdminAudit(request)),
  http.get("/api/v1/admin/audit-log", ({ request }) => handleAdminAudit(request)),

  http.get("*/api/v1/auth/me/audit-log", ({ request }) => handleAdminAudit(request)),
  http.get("/api/v1/auth/me/audit-log", ({ request }) => handleAdminAudit(request)),
];

async function handleLogin(request: Request) {
  const body = (await request.json()) as { email: string; password?: string };
  const isAdmin = body.email.includes("admin");

  const header = btoa(JSON.stringify({ alg: "HS256", typ: "JWT" }));
  const payload = btoa(
    JSON.stringify({
      sub: `usr_${body.email.split("@")[0]}`,
      tenant_id: "tenant_jakeai_core",
      org_id: "org_enterprise",
      roles: isAdmin ? ["admin", "tenant_admin"] : ["member"],
      permissions: isAdmin ? ["*"] : ["agent:read", "rag:read"],
      scopes: ["openid", "profile"],
      exp: Math.floor(Date.now() / 1000) + 3600,
      email: body.email,
      name: "Alex Mercer",
    })
  );
  const mockAccessToken = `${header}.${payload}.mockSignature`;

  return HttpResponse.json({
    code: 200,
    message: "login successful",
    data: {
      accessToken: mockAccessToken,
      refreshToken: "mock-refresh-token-uuid-12345",
      expiresAt: new Date(Date.now() + 3600000).toISOString(),
      profile: {
        id: 1,
        email: body.email,
        fullName: "Alex Mercer",
        role: isAdmin ? "admin" : "member",
        isActive: true,
      },
    },
  });
}

async function handleRefresh(request: Request) {
  const body = (await request.json()) as { refreshToken?: string };
  if (!body.refreshToken || body.refreshToken === "invalid") {
    return HttpResponse.json(
      { code: 401, message: "invalid or expired refresh token", data: null },
      { status: 401 }
    );
  }

  const header = btoa(JSON.stringify({ alg: "HS256", typ: "JWT" }));
  const payload = btoa(
    JSON.stringify({
      sub: "usr_alex_mercer",
      tenant_id: "tenant_jakeai_core",
      roles: ["admin"],
      permissions: ["*"],
      exp: Math.floor(Date.now() / 1000) + 3600,
    })
  );
  const newAccessToken = `${header}.${payload}.mockRefreshedSignature`;

  return HttpResponse.json({
    code: 200,
    message: "token refreshed",
    data: {
      accessToken: newAccessToken,
      refreshToken: "new-mock-refresh-token-uuid-67890",
      expiresAt: new Date(Date.now() + 3600000).toISOString(),
    },
  });
}

function handleMe() {
  return HttpResponse.json({
    code: 200,
    message: "profile fetched",
    data: {
      id: 1,
      email: "alex.mercer@jakeai.internal",
      fullName: "Alex Mercer",
      role: "admin",
      isActive: true,
    },
  });
}

function handleApprovals() {
  return HttpResponse.json([
    {
      id: "appr-01",
      approval_id: "appr-01",
      task_id: "task-100",
      run_id: "run-200",
      action_type: "terminal_exec",
      tool_name: "terminal_exec",
      risk_level: "dangerous",
      status: "pending",
      reason: "Dangerous command execution requested",
      created_at: 1726600000,
    },
  ]);
}

function handleAgentMetrics() {
  return HttpResponse.json({
    active_runs: 4,
    waiting_approvals: 1,
    failed_runs_last_hour: 0,
    completed_runs_last_hour: 12,
    runs_completed: 12,
    p95_step_duration_seconds: 1.85,
    p95_total_run_duration_seconds: 12.4,
    active_agents: 4,
  });
}

async function handleCreateTask(request: Request) {
  const body = (await request.json()) as Record<string, unknown>;
  return HttpResponse.json(
    {
      task_id: `task-${Date.now()}`,
      tenant_id: "tenant_jakeai_core",
      user_id: "usr_platform_admin",
      goal: (body.goal as string) || "Execute system audit",
      status: "created",
      created_at: Date.now(),
    },
    { status: 201 }
  );
}

function handleGetTask(taskId: string) {
  return HttpResponse.json({
    id: taskId,
    task_id: taskId,
    tenant_id: "tenant_jakeai_core",
    user_id: "usr_platform_admin",
    goal: "Execute system audit",
    status: "completed",
    created_at: Date.now(),
  });
}

function handleStartRun(taskId: string) {
  return HttpResponse.json(
    {
      run_id: `run-${Date.now()}`,
      task_id: taskId,
      tenant_id: "tenant_jakeai_core",
      user_id: "usr_platform_admin",
      status: "running",
      created_at: Date.now(),
      execution_duration_ms: 0,
      total_tokens_spent: 0,
    },
    { status: 201 }
  );
}

function handleGetRun(taskId: string, runId: string) {
  return HttpResponse.json({
    run_id: runId,
    task_id: taskId,
    tenant_id: "tenant_jakeai_core",
    user_id: "usr_platform_admin",
    status: "completed",
    execution_duration_ms: 2400,
    total_tokens_spent: 1250,
    created_at: Date.now(),
  });
}

function handleAgentRunEvents(taskId: string, runId: string) {
  const encoder = new TextEncoder();
  const stream = new ReadableStream({
    start(controller) {
      const emit = (event: string, data: Record<string, unknown>) => {
        controller.enqueue(encoder.encode(`event: ${event}\ndata: ${JSON.stringify(data)}\n\n`));
      };

      emit("run_started", {
        event_type: "run_started",
        task_id: taskId,
        run_id: runId,
        data: { goal: "Calculate EBITDA and analyze liquidity", max_iterations: 10 },
      });

      emit("task_created", {
        event_type: "task_created",
        task_id: taskId,
        run_id: runId,
        data: { goal: "Calculate EBITDA and analyze liquidity", tenant_id: "tenant_jakeai_core" },
      });

      emit("planning_started", {
        event_type: "planning_started",
        task_id: taskId,
        run_id: runId,
        data: { goal: "Calculate EBITDA and analyze liquidity" },
      });

      emit("plan_created", {
        event_type: "plan_created",
        task_id: taskId,
        run_id: runId,
        data: {
          plan_id: "plan-mock-1",
          planner_mode: "canonical_bounded",
          steps_count: 3,
          steps: [
            { step_id: "step-1", description: "Decompose financial goals", dependencies: [] },
            { step_id: "step-2", description: "Query FinnApiGo banking ledger", dependencies: ["step-1"] },
            { step_id: "step-3", description: "Verify financial calculations", dependencies: ["step-2"] },
          ],
        },
      });

      emit("step_started", {
        event_type: "step_started",
        task_id: taskId,
        run_id: runId,
        data: { step_id: "step-1", description: "Decompose financial goals" },
      });

      emit("agent_selected", {
        event_type: "agent_selected",
        task_id: taskId,
        run_id: runId,
        data: { step_id: "step-1", agent_id: "supervisor", confidence: 0.98, selection_mode: "canonical" },
      });

      emit("step_completed", {
        event_type: "step_completed",
        task_id: taskId,
        run_id: runId,
        data: { step_id: "step-1", output: "Financial goals successfully decomposed into sub-tasks." },
      });

      emit("step_started", {
        event_type: "step_started",
        task_id: taskId,
        run_id: runId,
        data: { step_id: "step-2", description: "Query FinnApiGo banking ledger" },
      });

      emit("tool_selected", {
        event_type: "tool_selected",
        task_id: taskId,
        run_id: runId,
        data: { step_id: "step-2", tool_name: "get_account_balance" },
      });

      emit("tool_call", {
        event_type: "tool_call",
        task_id: taskId,
        run_id: runId,
        data: { tool_name: "get_account_balance", arguments: { account_id: "acc_demo_01" } },
      });

      emit("observation", {
        event_type: "observation",
        task_id: taskId,
        run_id: runId,
        data: {
          tool_name: "get_account_balance",
          success: true,
          output: { balance: 4500000.0, currency: "USD", current_ratio: 2.1 },
          duration_ms: 65,
        },
      });

      emit("step_completed", {
        event_type: "step_completed",
        task_id: taskId,
        run_id: runId,
        data: { step_id: "step-2", output: "Account balance retrieved: $4,500,000.00 USD" },
      });

      emit("verification_started", {
        event_type: "verification_started",
        task_id: taskId,
        run_id: runId,
        data: { tenant_id: "tenant_jakeai_core", revision_count: 0 },
      });

      emit("verification_result", {
        event_type: "verification_result",
        task_id: taskId,
        run_id: runId,
        data: {
          verdict: "PASS",
          reason: "Mathematical invariants and tenant boundary verified cleanly.",
          groundedness_score: 0.99,
        },
      });

      emit("completed", {
        event_type: "completed",
        task_id: taskId,
        run_id: runId,
        data: {
          output: "Financial liquidity analysis completed: Operating Margin 24.5%, Current Ratio 2.1, Cash Reserve $4.5M.",
          elapsed_ms: 240,
          steps_completed: 3,
          verdict: "PASS",
        },
      });

      controller.close();
    },
  });

  return new HttpResponse(stream, {
    headers: {
      "Content-Type": "text/event-stream",
      "Cache-Control": "no-cache",
      Connection: "keep-alive",
    },
  });
}


function handleDecideApproval(taskId: string, runId: string, approvalId: string) {
  return HttpResponse.json({
    id: approvalId,
    approval_id: approvalId,
    task_id: taskId,
    run_id: runId,
    action_type: "terminal_exec",
    tool_name: "terminal_exec",
    risk_level: "dangerous",
    status: "approved",
    reason: "Operator sign-off granted",
  });
}

function handleCancelRun(taskId: string, runId: string) {
  return HttpResponse.json({
    run_id: runId,
    task_id: taskId,
    tenant_id: "tenant_jakeai_core",
    user_id: "usr_platform_admin",
    status: "cancelled",
    created_at: Date.now(),
  });
}

function handleModels() {
  return HttpResponse.json({
    object: "list",
    data: [
      { id: "gpt-4o", object: "model", owned_by: "openai", permission: [] },
      { id: "claude-3-5-sonnet", object: "model", owned_by: "anthropic", permission: [] },
      { id: "gemini-1.5-pro", object: "model", owned_by: "google", permission: [] },
    ],
  });
}

function handleQuotas() {
  return HttpResponse.json({
    tenant_id: "tenant_jakeai_core",
    quota_limit: 1000000,
    tokens_used: 250000,
    tokens_remaining: 750000,
    percentage_used: 25.0,
    is_suspended: false,
    warning: null,
  });
}

async function handleUpdateQuota(request: Request) {
  const body = (await request.json()) as { new_limit?: number };
  return HttpResponse.json({
    tenant_id: "tenant_jakeai_core",
    quota_limit: body.new_limit || 2000000,
    tokens_used: 250000,
    tokens_remaining: (body.new_limit || 2000000) - 250000,
    percentage_used: 12.5,
    is_suspended: false,
    warning: null,
  });
}

interface MockByokKey {
  provider: string;
  masked_key: string;
  configured: boolean;
  status: string;
  tenant_id: string;
  last_validated_at?: string;
  validation_status?: string;
  created_at?: string;
  updated_at?: string;
}

const INITIAL_MOCK_BYOK_KEYS: MockByokKey[] = [
  { provider: "openai", masked_key: "sk-...9a8b", configured: true, status: "active", tenant_id: "tenant_jakeai_core", last_validated_at: "2026-09-17T20:00:00Z", validation_status: "valid" },
  { provider: "anthropic", masked_key: "sk-...3c4d", configured: true, status: "active", tenant_id: "tenant_jakeai_core", last_validated_at: "2026-09-17T20:00:00Z", validation_status: "valid" },
];

let mockByokKeys: MockByokKey[] = JSON.parse(JSON.stringify(INITIAL_MOCK_BYOK_KEYS));

export function resetMockByokKeys() {
  mockByokKeys = JSON.parse(JSON.stringify(INITIAL_MOCK_BYOK_KEYS));
}

function handleByokKeys() {
  return HttpResponse.json({
    tenant_id: "tenant_jakeai_core",
    keys: mockByokKeys,
  });
}

async function handleStoreByokKey(request: Request) {
  const body = (await request.json()) as { provider: string; api_key: string; validate_key?: boolean };
  const existingIdx = mockByokKeys.findIndex((k) => k.provider === body.provider);
  const newItem = {
    provider: body.provider,
    masked_key: `sk-...${body.api_key.slice(-4)}`,
    configured: true,
    status: "active",
    tenant_id: "tenant_jakeai_core",
    created_at: new Date().toISOString(),
    last_validated_at: new Date().toISOString(),
    validation_status: "valid",
  };
  if (existingIdx >= 0) {
    mockByokKeys[existingIdx] = newItem;
  } else {
    mockByokKeys.push(newItem);
  }
  return HttpResponse.json(newItem, { status: 201 });
}

async function handleValidateCandidateKey(request: Request) {
  const body = (await request.json().catch(() => ({}))) as { provider?: string; api_key?: string };
  if (body.api_key?.includes("invalid")) {
    return HttpResponse.json({ provider: body.provider || "openai", is_valid: false, error: "Authentication failed with upstream provider (Invalid API key)" });
  }
  if (body.api_key?.includes("rate-limited")) {
    return HttpResponse.json({ detail: "Rate limit exceeded on provider endpoint" }, { status: 429 });
  }
  if (body.api_key?.includes("unavailable")) {
    return HttpResponse.json({ detail: "Provider API is temporarily unavailable" }, { status: 503 });
  }
  return HttpResponse.json({
    provider: body.provider || "openai",
    is_valid: true,
    error: null,
  });
}

function handleValidateExistingKey(provider: string) {
  const existing = mockByokKeys.find((k) => k.provider === provider);
  if (!existing || existing.status === "revoked") {
    return HttpResponse.json({
      provider,
      is_valid: false,
      error: "No active key configured for provider",
    });
  }
  return HttpResponse.json({
    provider,
    is_valid: true,
    error: null,
  });
}

async function handleRotateByokKey(provider: string, request: Request) {
  const body = (await request.json()) as { new_api_key: string; validate_key?: boolean };
  const existing = mockByokKeys.find((k) => k.provider === provider);
  const updated = {
    provider,
    masked_key: `sk-...${body.new_api_key.slice(-4)}`,
    configured: true,
    status: "active",
    tenant_id: "tenant_jakeai_core",
    updated_at: new Date().toISOString(),
    last_validated_at: new Date().toISOString(),
    validation_status: "valid",
  };
  if (existing) {
    Object.assign(existing, updated);
  } else {
    mockByokKeys.push(updated);
  }
  return HttpResponse.json(updated, { status: 200 });
}

function handleRevokeByokKey(provider: string) {
  const existing = mockByokKeys.find((k) => k.provider === provider);
  if (existing) {
    existing.status = "revoked";
    existing.configured = false;
  }
  return HttpResponse.json(
    existing || {
      provider,
      masked_key: "sk-...revoked",
      configured: false,
      status: "revoked",
      tenant_id: "tenant_jakeai_core",
    },
    { status: 200 }
  );
}

function handleDeleteByokKey(provider: string) {
  mockByokKeys = mockByokKeys.filter((k) => k.provider !== provider);
  return HttpResponse.json({
    tenant_id: "tenant_jakeai_core",
    provider,
    status: "revoked",
    message: "Key revoked and deleted",
  });
}

let mockBudget = {
  tenant_id: "tenant_jakeai_core",
  period: "2026-09",
  token_quota: 5000000,
  tokens_used: 1420000,
  tokens_remaining: 3580000,
  percentage_tokens_used: 28.4,
  dollar_budget_usd: 500.0 as number | null,
  dollar_spent_usd: 142.85,
  dollar_remaining_usd: 357.15 as number | null,
  percentage_dollars_used: 28.57 as number | null,
  warning_threshold: 0.8,
  is_suspended: false,
  warning: null as string | null,
};

function handleFinopsSummary() {
  return HttpResponse.json({
    tenant_id: "tenant_jakeai_core",
    period: "2026-09",
    total_requests: 1420,
    reconciled_requests: 1420,
    reconciliation_rate: 100.0,
    total_raw_tokens: 4500000,
    total_optimized_tokens: 4200000,
    total_physical_tokens_removed: 300000,
    total_cached_tokens: 1200000,
    total_uncached_tokens: 3000000,
    total_output_tokens: 650000,
    total_baseline_cost_usd: 181.25,
    total_actual_cost_usd: 142.85,
    total_savings_usd: 38.40,
    overall_savings_percentage: 21.19,
    savings_attribution: {
      cache_hit_usd: 24.50,
      physical_reduction_usd: 6.20,
      provider_cache_usd: 4.80,
      model_routing_usd: 2.90,
      avoided_retries_usd: 0.0,
      total_savings_usd: 38.40,
    },
    budget_status: mockBudget,
  });
}

function handleFinopsBudget() {
  return HttpResponse.json(mockBudget);
}

async function handleUpdateBudget(request: Request) {
  const body = (await request.json()) as {
    dollar_budget_usd?: number | null;
    token_quota?: number | null;
    warning_threshold?: number | null;
  };

  const newQuota = body.token_quota ?? mockBudget.token_quota;
  const newDollarBudget = body.dollar_budget_usd !== undefined ? body.dollar_budget_usd : mockBudget.dollar_budget_usd;
  const newThreshold = body.warning_threshold ?? mockBudget.warning_threshold;

  const pctTokens = (mockBudget.tokens_used / newQuota) * 100;
  const pctDollars = newDollarBudget ? (mockBudget.dollar_spent_usd / newDollarBudget) * 100 : null;
  const isSuspended = pctTokens >= 100 || (pctDollars !== null && pctDollars >= 100);

  mockBudget = {
    ...mockBudget,
    token_quota: newQuota,
    tokens_remaining: Math.max(0, newQuota - mockBudget.tokens_used),
    percentage_tokens_used: Number(pctTokens.toFixed(1)),
    dollar_budget_usd: newDollarBudget,
    dollar_remaining_usd: newDollarBudget ? Math.max(0, newDollarBudget - mockBudget.dollar_spent_usd) : null,
    percentage_dollars_used: pctDollars ? Number(pctDollars.toFixed(1)) : null,
    warning_threshold: newThreshold,
    is_suspended: isSuspended,
    warning: isSuspended ? "Tenant has exhausted allocated token quota or dollar spending limit." : null,
  };

  return HttpResponse.json(mockBudget);
}

function handleTransactions() {
  return HttpResponse.json([
    {
      request_id: "req-fin-001",
      tenant_id: "tenant_jakeai_core",
      provider: "openai",
      model: "gpt-4o",
      requested_model: "gpt-4o",
      timestamp: 1726650000,
      estimated_local_tokens: 580,
      raw_tokens: 550,
      optimized_tokens: 420,
      physical_tokens_removed: 130,
      cached_tokens: 120,
      uncached_tokens: 300,
      output_tokens: 110,
      provider_reported_total: 530,
      baseline_cost_usd: 0.0055,
      estimated_cost_usd: 0.0041,
      actual_billed_cost_usd: 0.0038,
      effective_cost_usd: 0.0038,
      total_savings_usd: 0.0017,
      savings_percentage: 30.9,
      savings_attribution: {
        cache_hit_usd: 0.0,
        physical_reduction_usd: 0.0009,
        provider_cache_usd: 0.0008,
        model_routing_usd: 0.0,
        avoided_retries_usd: 0.0,
        total_savings_usd: 0.0017,
      },
      reconciliation_status: "authoritative",
      is_cache_hit: false,
      cache_type: "none",
      metadata: { workload: "chat", route: "standard" },
    },
  ]);
}

function handleReconciliation() {
  return HttpResponse.json({
    tenant_id: "tenant_jakeai_core",
    period: "monthly",
    total_reconciled: 1420,
    total_estimated_only: 0,
    net_token_variance: 0,
    net_cost_variance_usd: 0.0,
    avg_token_variance_pct: 0.0,
    anomalous_requests_count: 0,
  });
}

const mockRagTasks: Record<string, { count: number; source: string; status: string }> = {};

async function handleRagIngest(request: Request) {
  const url = new URL(request.url);
  const isAsync = url.searchParams.get("async_mode") === "true";
  const body = (await request.json().catch(() => ({}))) as { content?: string; source?: string; fail?: boolean };

  if (body.fail || body.content?.includes("fail-now")) {
    return HttpResponse.json({ detail: "Unsupported document format or corrupted encoding" }, { status: 400 });
  }

  if (isAsync) {
    const taskId = `task-ingest-${Date.now()}`;
    mockRagTasks[taskId] = { count: 0, source: body.source || "document.pdf", status: "queued" };
    return HttpResponse.json(
      {
        task_id: taskId,
        tenant_id: "tenant_jakeai_core",
        status: "queued",
        source: body.source || "document.pdf",
        created_at: Date.now() / 1000,
      },
      { status: 202 }
    );
  }

  return HttpResponse.json(
    {
      status: "accepted",
      indexed_chunks: 3,
      chunk_ids: ["chunk-1", "chunk-2", "chunk-3"],
      source: body.source || "document.pdf",
      tenant_id: "tenant_jakeai_core",
    },
    { status: 201 }
  );
}

function handleGetRagTask(taskId: string) {
  if (taskId === "rag-task-555" || taskId.includes("completed")) {
    return HttpResponse.json({
      task_id: taskId,
      tenant_id: "tenant_jakeai_core",
      status: "completed",
      source: "policy.pdf",
      content: "Enterprise AI Security requires perimeter isolation.",
      chunk_size: 500,
      chunk_overlap: 50,
      created_at: Date.now() / 1000 - 30,
      started_at: Date.now() / 1000 - 25,
      completed_at: Date.now() / 1000,
      error: null,
      result: {
        status: "success",
        indexed_chunks: 3,
        chunk_ids: ["chunk-1", "chunk-2", "chunk-3"],
        source: "policy.pdf",
        tenant_id: "tenant_jakeai_core",
      },
    });
  }

  if (!mockRagTasks[taskId]) {
    mockRagTasks[taskId] = { count: 0, source: "policy.pdf", status: "queued" };
  }
  const task = mockRagTasks[taskId];
  task.count += 1;

  if (taskId.includes("fail") || task.source.includes("fail")) {
    return HttpResponse.json({
      task_id: taskId,
      tenant_id: "tenant_jakeai_core",
      status: "failed",
      source: task.source,
      content: "",
      chunk_size: 500,
      chunk_overlap: 50,
      created_at: Date.now() / 1000 - 15,
      started_at: Date.now() / 1000 - 10,
      completed_at: Date.now() / 1000,
      error: "Document parsing error: malformed PDF header detected",
      result: null,
    });
  }

  // Lifecycle progression: count 1 = queued, count 2 = processing, count 3+ = completed
  const currentStatus = task.count === 1 ? "queued" : task.count === 2 ? "processing" : "completed";
  task.status = currentStatus;

  return HttpResponse.json({
    task_id: taskId,
    tenant_id: "tenant_jakeai_core",
    status: currentStatus,
    source: task.source,
    content: "Enterprise AI Security requires perimeter isolation.",
    chunk_size: 500,
    chunk_overlap: 50,
    created_at: Date.now() / 1000 - 10,
    started_at: Date.now() / 1000 - 5,
    completed_at: currentStatus === "completed" ? Date.now() / 1000 : null,
    error: null,
    result:
      currentStatus === "completed"
        ? {
            status: "success",
            indexed_chunks: 3,
            chunk_ids: ["chunk-1", "chunk-2", "chunk-3"],
            source: task.source,
            tenant_id: "tenant_jakeai_core",
          }
        : null,
  });
}

async function handleRagQuery(request: Request) {
  const body = (await request.json()) as {
    query: string;
    top_k?: number;
    select_context?: boolean;
    max_context_tokens?: number;
  };

  const isSingleMatchQuery = body.query === "perimeter security";

  const allChunks = [
    {
      chunk_id: "chunk-1",
      content: "Enterprise AI Security requires perimeter isolation and HSM tenant key scoping.",
      score: 0.94,
      source: "security-handbook.pdf",
      tenant_id: "tenant_jakeai_core",
      metadata: { department: "SecOps", classification: "Internal" },
    },
    {
      chunk_id: "chunk-2",
      content: "All inference requests enforce zero data retention and AES-256 encrypted vaults.",
      score: 0.88,
      source: "compliance-2026.pdf",
      tenant_id: "tenant_jakeai_core",
      metadata: { department: "Compliance", classification: "Public" },
    },
  ];

  const chunks = isSingleMatchQuery ? [allChunks[0]] : allChunks.slice(0, body.top_k || 5);

  return HttpResponse.json({
    query: body.query,
    tenant_id: "tenant_jakeai_core",
    chunks,
    latency_ms: 18.5,
    total_candidates: 12,
    selected_context: body.select_context
      ? "[1] Enterprise AI Security requires perimeter isolation and HSM tenant key scoping.\n[2] All inference requests enforce zero data retention and AES-256 encrypted vaults."
      : null,
    context_tokens: body.select_context ? 48 : null,
    tokens_saved: body.select_context ? 152 : null,
    reduction_ratio: body.select_context ? 0.76 : null,
  });
}

async function handleRagGenerate(request: Request) {
  const body = (await request.json()) as { query: string; model?: string; top_k?: number };
  const queryLower = (body.query || "").toLowerCase();

  // Epistemic abstention case
  if (
    queryLower.includes("martian") ||
    queryLower.includes("alien") ||
    queryLower.includes("abstain") ||
    queryLower.includes("classified top-speed")
  ) {
    return HttpResponse.json({
      query: body.query,
      tenant_id: "tenant_jakeai_core",
      answer: "I cannot answer this question as the knowledge base does not contain relevant verifiable evidence.",
      citations: [],
      context_tokens: 0,
      tokens_saved: 0,
      reduction_ratio: 0.0,
      latency_ms: 145.0,
      status: "ABSTAINED",
      abstention_reason: "NO_RELEVANT_EVIDENCE",
      grounding: {
        is_grounded: false,
        groundedness_ratio: 0.0,
        unsupported_claim_rate: 1.0,
        claims: [],
      },
      envelope_tokens: 0,
    });
  }

  return HttpResponse.json({
    query: body.query,
    tenant_id: "tenant_jakeai_core",
    answer: `Grounded synthesis for: ${body.query}. According to enterprise guidelines [1], perimeter isolation and cryptographic key scoping are required.`,
    citations: [
      {
        index: 1,
        source: "security-handbook.pdf",
        snippet: "Enterprise AI Security requires perimeter isolation and HSM tenant key scoping.",
        tenant_id: "tenant_jakeai_core",
        confidence: 0.97,
        chunk_id: "chunk-1",
      },
    ],
    context_tokens: 180,
    tokens_saved: 420,
    reduction_ratio: 0.7,
    latency_ms: 380.0,
    status: "SUCCESS",
    abstention_reason: null,
    grounding: {
      is_grounded: true,
      groundedness_ratio: 1.0,
      unsupported_claim_rate: 0.0,
      claims: [
        {
          claim_text: "Perimeter isolation and cryptographic key scoping are required.",
          entailment: "SUPPORTED",
          confidence: 0.98,
          supporting_chunk_ids: ["chunk-1"],
          reasoning: "Direct factual entailment from security handbook chunk-1.",
        },
      ],
      supported_claims: [
        {
          claim_text: "Perimeter isolation and cryptographic key scoping are required.",
          entailment: "SUPPORTED",
          confidence: 0.98,
          supporting_chunk_ids: ["chunk-1"],
          reasoning: "Direct factual entailment from security handbook chunk-1.",
        },
      ],
      unsupported_claims: [],
      contradicted_claims: [],
      uncertain_claims: [],
      verified_answer: `Grounded synthesis for: ${body.query}. According to enterprise guidelines [1], perimeter isolation and cryptographic key scoping are required.`,
    },
    envelope_tokens: 240,
  });
}

interface MockAdminUser {
  id: number;
  username: string;
  fullName: string;
  email: string;
  role: string;
  isActive: boolean;
  isLocked: boolean;
  lockedUntil?: string | null;
  createdAt: string;
}

interface MockAdminSession {
  id: string;
  userId: number;
  username: string;
  ipAddress: string;
  userAgent: string;
  createdAt: string;
  expiresAt: string;
}

const initialAdminUsers: MockAdminUser[] = [
  { id: 1, username: "alex.mercer", fullName: "Alex Mercer", email: "alex.mercer@jakeai.internal", role: "admin", isActive: true, isLocked: false, lockedUntil: null, createdAt: "2026-01-15T09:00:00Z" },
  { id: 2, username: "sarah.connor", fullName: "Sarah Connor", email: "sarah@cyberdyne.io", role: "member", isActive: true, isLocked: false, lockedUntil: null, createdAt: "2026-02-15T14:30:00Z" },
];

let mockAdminUsers: MockAdminUser[] = JSON.parse(JSON.stringify(initialAdminUsers));

const initialAdminSessions: MockAdminSession[] = [
  { id: "sess_01", userId: 1, username: "alex.mercer", ipAddress: "192.168.1.50", userAgent: "Mozilla/5.0 (Windows NT 10.0; Win64; x64) Chrome/128.0", createdAt: "2026-09-18T08:00:00Z", expiresAt: "2026-09-19T08:00:00Z" },
  { id: "sess_02", userId: 2, username: "sarah.connor", ipAddress: "10.0.0.42", userAgent: "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) Safari/605.1.15", createdAt: "2026-09-18T10:15:00Z", expiresAt: "2026-09-19T10:15:00Z" },
];

let mockAdminSessions: MockAdminSession[] = JSON.parse(JSON.stringify(initialAdminSessions));

export function resetAdminMocks() {
  mockAdminUsers = JSON.parse(JSON.stringify(initialAdminUsers));
  mockAdminSessions = JSON.parse(JSON.stringify(initialAdminSessions));
}

let mockAdminAuditLogs = [
  {
    id: 1,
    tenant_id: "tenant_jakeai_core",
    user_id: 1,
    email: "alex.mercer@jakeai.internal",
    action: "USER_LOGIN",
    resource: "auth",
    status: "success",
    ip_address: "192.168.1.50",
    user_agent: "Mozilla/5.0 Chrome/128.0",
    created_at: "2026-09-18T08:00:00Z",
  },
];

function handleAdminUsers(url: URL) {
  const page = parseInt(url.searchParams.get("page") || "1", 10);
  const limit = parseInt(url.searchParams.get("limit") || "10", 10);
  const search = (url.searchParams.get("search") || "").toLowerCase().trim();

  const filtered = search
    ? mockAdminUsers.filter(
        (u) =>
          u.username.toLowerCase().includes(search) ||
          u.email.toLowerCase().includes(search) ||
          u.fullName.toLowerCase().includes(search)
      )
    : mockAdminUsers;

  const start = (page - 1) * limit;
  const items = filtered.slice(start, start + limit);

  return HttpResponse.json({
    code: 200,
    message: "users retrieved",
    data: {
      items,
      total: filtered.length,
      page,
      limit,
    },
  });
}

async function handleLockUser(id: string, _request: Request) {
  const user = mockAdminUsers.find((u) => String(u.id) === String(id));
  if (user) {
    user.isLocked = true;
    user.lockedUntil = new Date(Date.now() + 3600 * 1000).toISOString();
  }
  return HttpResponse.json({ code: 200, message: "user locked", data: null });
}

function handleUnlockUser(id: string) {
  const user = mockAdminUsers.find((u) => String(u.id) === String(id));
  if (user) {
    user.isLocked = false;
    user.lockedUntil = null;
  }
  return HttpResponse.json({ code: 200, message: "user unlocked", data: null });
}

function handleForceLogout(id: string) {
  mockAdminSessions = mockAdminSessions.filter((s) => String(s.userId) !== String(id));
  return HttpResponse.json({ code: 200, message: "user logged out of all devices", data: null });
}

function handleAdminSessions() {
  return HttpResponse.json({
    code: 200,
    message: "tenant sessions retrieved",
    data: mockAdminSessions,
  });
}

function handleAdminAudit(request: Request) {
  const url = new URL(request.url);
  const page = parseInt(url.searchParams.get("page") || "1", 10);
  const limit = parseInt(url.searchParams.get("limit") || "20", 10);

  const start = (page - 1) * limit;
  const items = mockAdminAuditLogs.slice(start, start + limit);

  return HttpResponse.json({
    code: 200,
    message: "audit logs retrieved",
    data: {
      items,
      total: mockAdminAuditLogs.length,
      page,
      limit,
    },
  });
}

function handleExportAudit(request: Request) {
  const url = new URL(request.url);
  const format = url.searchParams.get("format") || "csv";

  if (format === "ndjson") {
    const ndjson = mockAdminAuditLogs.map((l) => JSON.stringify(l)).join("\n");
    return new HttpResponse(ndjson, {
      headers: {
        "Content-Type": "application/x-ndjson",
        "Content-Disposition": 'attachment; filename="audit_export.ndjson"',
      },
    });
  }

  const csv = [
    "id,timestamp,action,resource,actor,status,ip_address",
    ...mockAdminAuditLogs.map(
      (l) => `${l.id},${l.created_at},${l.action},${l.resource},${l.email},${l.status},${l.ip_address}`
    ),
  ].join("\n");

  return new HttpResponse(csv, {
    headers: {
      "Content-Type": "text/csv",
      "Content-Disposition": 'attachment; filename="audit_export.csv"',
    },
  });
}

async function handleChatStream(request: Request) {
  const body = (await request.json().catch(() => ({}))) as {
    prompt?: string;
    conversation_id?: string;
  };
  const encoder = new TextEncoder();
  const convId = body.conversation_id || "conv-mock-123";
  const prompt = body.prompt || "";

  if (!prompt.trim()) {
    return new HttpResponse(
      JSON.stringify({ detail: "Prompt or query must not be empty." }),
      { status: 422, headers: { "Content-Type": "application/json" } }
    );
  }

  const stream = new ReadableStream({
    start(controller) {
      // 1. Initial status
      controller.enqueue(
        encoder.encode(
          `event: status\ndata: ${JSON.stringify({
            phase: "initialized",
            conversation_id: convId,
            tenant_id: "tenant_jakeai_core",
            mascot_state: "thinking",
          })}\n\n`
        )
      );

      // 2. Supervisor routing status
      controller.enqueue(
        encoder.encode(
          `event: status\ndata: ${JSON.stringify({
            node: "supervisor",
            phase: "routing",
            mascot_state: "thinking",
            message: "Supervisor: Dispatching to financial_specialist.",
          })}\n\n`
        )
      );

      // 3. Specialist status
      controller.enqueue(
        encoder.encode(
          `event: status\ndata: ${JSON.stringify({
            node: "financial_specialist",
            phase: "financial_analysis",
            mascot_state: "thinking",
            message: "Specialist analyzing query.",
          })}\n\n`
        )
      );

      // 4. Verifier status
      controller.enqueue(
        encoder.encode(
          `event: status\ndata: ${JSON.stringify({
            node: "verifier",
            phase: "verification_passed",
            mascot_state: "thinking",
            message: "Verifier: Verified factual consistency.",
          })}\n\n`
        )
      );

      // 5. Synthesizer status
      controller.enqueue(
        encoder.encode(
          `event: status\ndata: ${JSON.stringify({
            node: "synthesizer",
            phase: "synthesizing",
            mascot_state: "thinking",
            message: "Synthesizer: Consolidating verified claims.",
          })}\n\n`
        )
      );

      // 6. Tokens
      const words = ["JakeAI", " analyzes", " your", " request", " with", " multi-agent", " verification."];
      for (const w of words) {
        controller.enqueue(
          encoder.encode(
            `event: token\ndata: ${JSON.stringify({
              delta: w,
              token: w,
              conversation_id: convId,
            })}\n\n`
          )
        );
      }

      // 7. Telemetry
      controller.enqueue(
        encoder.encode(
          `event: telemetry\ndata: ${JSON.stringify({
            baseline_tokens: 150,
            billed_tokens: 120,
            tokens_saved: 30,
            reduction_rate: 0.2,
          })}\n\n`
        )
      );

      // 8. Done
      controller.enqueue(
        encoder.encode(
          `event: done\ndata: ${JSON.stringify({
            conversation_id: convId,
            tenant_id: "tenant_jakeai_core",
            elapsed_ms: 180,
            mascot_state: "success",
            citations: [
              {
                index: 1,
                source: "FinnApiGo Core Ledger",
                snippet: "Authoritative financial statement snapshot for tenant",
                tenant_id: "tenant_jakeai_core",
                confidence: 0.98,
                chunk_id: "chunk-fin-01",
              },
            ],
            model: "gemini-1.5-flash",
          })}\n\n`
        )
      );

      controller.close();
    },
  });

  return new HttpResponse(stream, {
    headers: {
      "Content-Type": "text/event-stream",
      "Cache-Control": "no-cache",
      Connection: "keep-alive",
    },
  });
}
