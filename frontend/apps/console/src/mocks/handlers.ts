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

  http.post("*/api/v1/byok/keys/validate", () => HttpResponse.json({ is_valid: true, provider: "cohere", error: null })),
  http.post("/api/v1/byok/keys/validate", () => HttpResponse.json({ is_valid: true, provider: "cohere", error: null })),

  http.delete("*/api/v1/byok/keys/:provider", () => HttpResponse.json({ message: "Key revoked and deleted" })),
  http.delete("/api/v1/byok/keys/:provider", () => HttpResponse.json({ message: "Key revoked and deleted" })),

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

  http.post("*/api/v1/rag/ingest", () => HttpResponse.json({ status: "accepted", indexed_chunks: 1, chunk_ids: ["chunk-1"], source: "policy.pdf", tenant_id: "tenant_jakeai_core" }, { status: 201 })),
  http.post("/api/v1/rag/ingest", () => HttpResponse.json({ status: "accepted", indexed_chunks: 1, chunk_ids: ["chunk-1"], source: "policy.pdf", tenant_id: "tenant_jakeai_core" }, { status: 201 })),

  http.get("*/api/v1/rag/tasks/:taskId", ({ params }) => HttpResponse.json({ task_id: params.taskId, tenant_id: "tenant_jakeai_core", status: "completed", processed_chunks: 42, total_chunks: 42, created_at: "2026-09-17T20:00:00Z" })),
  http.get("/api/v1/rag/tasks/:taskId", ({ params }) => HttpResponse.json({ task_id: params.taskId, tenant_id: "tenant_jakeai_core", status: "completed", processed_chunks: 42, total_chunks: 42, created_at: "2026-09-17T20:00:00Z" })),

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

  // Admin
  http.get("*/api/v1/admin/users", () => handleAdminUsers()),
  http.get("/api/v1/admin/users", () => handleAdminUsers()),

  http.get("*/api/v1/admin/audit-log", () => handleAdminAudit()),
  http.get("/api/v1/admin/audit-log", () => handleAdminAudit()),
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

function handleByokKeys() {
  return HttpResponse.json({
    keys: [
      { provider: "openai", masked_key: "sk-...9a8b", status: "active", tenant_id: "tenant_jakeai_core" },
      { provider: "anthropic", masked_key: "sk-...3c4d", status: "active", tenant_id: "tenant_jakeai_core" },
    ],
  });
}

async function handleStoreByokKey(request: Request) {
  const body = (await request.json()) as { provider: string; api_key: string };
  return HttpResponse.json(
    {
      tenant_id: "tenant_jakeai_core",
      provider: body.provider,
      masked_key: `sk-...${body.api_key.slice(-4)}`,
      status: "active",
      created_at: new Date().toISOString(),
    },
    { status: 201 }
  );
}

function handleFinopsSummary() {
  return HttpResponse.json({
    tenant_id: "tenant_jakeai_core",
    period: "monthly",
    total_requests: 1420,
    reconciled_requests: 1420,
    reconciliation_rate: 1.0,
    total_raw_tokens: 4500000,
    total_optimized_tokens: 4200000,
    total_physical_tokens_removed: 300000,
    budget_status: {
      budget_usd: 500.0,
      dollar_budget_usd: 500.0,
      spent_usd: 142.85,
      dollar_spent_usd: 142.85,
      remaining_usd: 357.15,
      threshold_alert: false,
      hard_cap_exceeded: false,
    },
  });
}

function handleFinopsBudget() {
  return HttpResponse.json({
    tenant_id: "tenant_jakeai_core",
    period: "monthly",
    token_quota: 5000000,
    tokens_used: 1420000,
    tokens_remaining: 3580000,
    percentage_tokens_used: 28.4,
    dollar_budget_usd: 500.0,
    dollar_spent_usd: 142.85,
    dollar_remaining_usd: 357.15,
    percentage_dollar_spent: 28.57,
  });
}

async function handleUpdateBudget(request: Request) {
  const body = (await request.json()) as { dollar_budget_usd?: number; token_quota?: number };
  return HttpResponse.json({
    tenant_id: "tenant_jakeai_core",
    period: "monthly",
    token_quota: body.token_quota || 10000000,
    tokens_used: 1420000,
    tokens_remaining: (body.token_quota || 10000000) - 1420000,
    percentage_tokens_used: 14.2,
    dollar_budget_usd: body.dollar_budget_usd || 1000.0,
    dollar_spent_usd: 142.85,
    dollar_remaining_usd: (body.dollar_budget_usd || 1000.0) - 142.85,
    percentage_dollar_spent: 14.28,
  });
}

function handleTransactions() {
  return HttpResponse.json([
    {
      id: "rec-01",
      request_id: "req-01",
      correlation_id: "corr-01",
      tenant_id: "tenant_jakeai_core",
      user_id: "usr_123",
      model: "gpt-4o",
      provider: "openai",
      prompt_tokens: 450,
      completion_tokens: 120,
      total_tokens: 570,
      estimated_cost_usd: 0.0035,
      actual_cost_usd: 0.0035,
      is_reconciled: true,
      timestamp: 1726600000,
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

async function handleRagQuery(request: Request) {
  const body = (await request.json()) as { query: string };
  return HttpResponse.json({
    query: body.query,
    tenant_id: "tenant_jakeai_core",
    chunks: [
      {
        chunk_id: "chunk-1",
        content: "Enterprise AI Security requires perimeter isolation.",
        score: 0.94,
        source: "security-handbook.pdf",
        tenant_id: "tenant_jakeai_core",
      },
    ],
    latency_ms: 12.5,
    sparse_matches: 1,
    dense_matches: 1,
    reciprocal_rank_fused: true,
    cross_encoder_reranked: true,
  });
}

async function handleRagGenerate(request: Request) {
  const body = (await request.json()) as { query: string };
  return HttpResponse.json({
    answer: `Grounded answer generated for: ${body.query}`,
    citations: [{ source: "security-handbook.pdf", chunk_id: "chunk-1" }],
    tokens_used: 150,
    model: "gpt-4o",
    latency_ms: 450.0,
    retrieval_latency_ms: 15.0,
    generation_latency_ms: 435.0,
  });
}

function handleAdminUsers() {
  return HttpResponse.json({
    code: 200,
    message: "users fetched",
    data: [
      { id: 1, username: "alex.mercer", email: "alex.mercer@jakeai.internal", role: "admin", isActive: true, createdAt: "2026-01-01" },
      { id: 2, username: "sarah.connor", email: "sarah@cyberdyne.io", role: "member", isActive: true, createdAt: "2026-02-15" },
    ],
  });
}

function handleAdminAudit() {
  return HttpResponse.json({
    code: 200,
    message: "audit logs fetched",
    data: [
      { id: 1, action: "USER_LOGIN", resource: "auth", ipAddress: "127.0.0.1", createdAt: "2026-09-17 12:00:00" },
    ],
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
