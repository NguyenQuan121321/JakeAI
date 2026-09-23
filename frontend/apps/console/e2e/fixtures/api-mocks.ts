import type { Page, Route } from "@playwright/test";
import type { User } from "../../src/types/auth";
import { ADMIN_USER, createDeterministicTestJwt } from "./auth";

/**
 * Configure Authentication & Identity HTTP Mocks
 */
export async function setupAuthMocks(page: Page, user: User = ADMIN_USER) {
  // 1. Login endpoint
  await page.route("**/api/v1/auth/login", async (route: Route) => {
    const postData = route.request().postDataJSON();
    if (postData?.email === "denied@jakeai.com") {
      return route.fulfill({
        status: 401,
        contentType: "application/json",
        body: JSON.stringify({ code: 401, message: "Invalid credentials", data: null }),
      });
    }

    const testToken = createDeterministicTestJwt(user);

    return route.fulfill({
      status: 200,
      contentType: "application/json",
      body: JSON.stringify({
        code: 200,
        message: "OK",
        data: {
          accessToken: testToken,
          refreshToken: `refresh-${user.id}`,
          expiresAt: new Date(Date.now() + 86400 * 1000).toISOString(),
          profile: {
            id: user.id,
            email: user.email,
            fullName: user.name,
            username: user.email.split("@")[0],
            role: user.roles[0] || "member",
            isActive: true,
            isEmailVerified: true,
          },
        },
      }),
    });
  });

  // 2. Current User Profile endpoint
  await page.route("**/api/v1/auth/me", async (route: Route) => {
    return route.fulfill({
      status: 200,
      contentType: "application/json",
      body: JSON.stringify({
        code: 200,
        message: "OK",
        data: {
          id: user.id,
          email: user.email,
          fullName: user.name,
          username: user.email.split("@")[0],
          role: user.roles[0] || "member",
          isActive: true,
          isEmailVerified: true,
          tenantId: user.tenantId,
          roles: user.roles,
          permissions: user.permissions,
        },
      }),
    });
  });

  // 3. Refresh Token endpoint
  await page.route("**/api/v1/auth/refresh-token", async (route: Route) => {
    const testToken = createDeterministicTestJwt(user);
    return route.fulfill({
      status: 200,
      contentType: "application/json",
      body: JSON.stringify({
        code: 200,
        message: "OK",
        data: {
          accessToken: testToken,
          refreshToken: `refresh-${user.id}`,
          expiresAt: new Date(Date.now() + 86400 * 1000).toISOString(),
        },
      }),
    });
  });

  // 4. Logout endpoint
  await page.route("**/api/v1/auth/logout", async (route: Route) => {
    return route.fulfill({
      status: 200,
      contentType: "application/json",
      body: JSON.stringify({ code: 200, message: "Logged out", data: null }),
    });
  });
}

/**
 * Configure Business Domain API Mocks (Gateway, Agent, RAG, FinOps, Admin)
 */
export async function setupBusinessApiMocks(page: Page, user: User = ADMIN_USER) {
  const isAdmin = user.roles.includes("admin") || user.roles.includes("tenant_admin");

  // 1. Gateway models
  await page.route("**/api/v1/gateway/models", async (route: Route) => {
    return route.fulfill({
      status: 200,
      contentType: "application/json",
      body: JSON.stringify({
        data: [
          { id: "gpt-4o", owned_by: "openai", latency_p95: 120 },
          { id: "claude-3-5-sonnet", owned_by: "anthropic", latency_p95: 145 },
          { id: "gemini-1-5-pro", owned_by: "gemini", latency_p95: 110 },
        ],
      }),
    });
  });

  // 2. Chat stream (SSE)
  await page.route("**/api/v1/chat/stream", async (route: Route) => {
    const postData = route.request().postDataJSON();
    if (postData?.prompt?.includes("FAIL_503")) {
      return route.fulfill({
        status: 503,
        contentType: "application/json",
        body: JSON.stringify({ detail: "AI Provider temporarily unavailable" }),
      });
    }

    const ssePayload = [
      'event: status\ndata: {"stage": "planned", "elapsed_ms": 10}\n\n',
      'event: token\ndata: {"token": "Hello! "}\n\n',
      'event: token\ndata: {"token": "I am JakeAI, "}\n\n',
      'event: token\ndata: {"token": "ready to assist with your engineering tasks."}\n\n',
      'event: telemetry\ndata: {"prompt_tokens": 12, "completion_tokens": 15, "total_cost_usd": 0.0002}\n\n',
      'event: done\ndata: {"status": "completed", "finish_reason": "stop"}\n\n',
    ].join("");

    return route.fulfill({
      status: 200,
      contentType: "text/event-stream",
      headers: {
        "Cache-Control": "no-cache",
        "Connection": "keep-alive",
      },
      body: ssePayload,
    });
  });

  // 3. Agent platform
  await page.route("**/api/v1/agent/metrics", async (route: Route) => {
    return route.fulfill({
      status: 200,
      contentType: "application/json",
      body: JSON.stringify({
        active_runs: 1,
        completed_runs: 42,
        failed_runs: 2,
        pending_approvals: 1,
      }),
    });
  });

  await page.route("**/api/v1/agent/approvals/pending", async (route: Route) => {
    return route.fulfill({
      status: 200,
      contentType: "application/json",
      body: JSON.stringify([
        {
          approval_id: "appr-001",
          task_id: "task-001",
          run_id: "run-001",
          action_type: "deploy_production",
          description: "Deploy security patch to production Kubernetes cluster",
          status: "pending",
          created_at: new Date().toISOString(),
        },
      ]),
    });
  });

  await page.route("**/api/v1/agent/tasks", async (route: Route) => {
    const postData = route.request().postDataJSON();
    return route.fulfill({
      status: 200,
      contentType: "application/json",
      body: JSON.stringify({
        task_id: "task-new-e2e-123",
        tenant_id: user.tenantId,
        user_id: user.id,
        prompt: postData?.prompt || "Autonomous Task",
        status: "pending",
        context: {},
        created_at: new Date().toISOString(),
        updated_at: new Date().toISOString(),
      }),
    });
  });

  await page.route("**/api/v1/agent/tasks/*/runs", async (route: Route) => {
    return route.fulfill({
      status: 200,
      contentType: "application/json",
      body: JSON.stringify({
        run_id: "run-new-e2e-456",
        task_id: "task-new-e2e-123",
        status: "executing",
        created_at: new Date().toISOString(),
      }),
    });
  });

  await page.route("**/api/v1/agent/tasks/*/runs/*/approvals/*", async (route: Route) => {
    return route.fulfill({
      status: 200,
      contentType: "application/json",
      body: JSON.stringify({
        approval_id: "appr-001",
        status: "approved",
        decision: "approved",
      }),
    });
  });

  // 4. BYOK Vault
  await page.route("**/api/v1/byok/keys", async (route: Route) => {
    if (route.request().method() === "POST") {
      const data = route.request().postDataJSON();
      return route.fulfill({
        status: 200,
        contentType: "application/json",
        body: JSON.stringify({
          provider: data?.provider || "openai",
          configured: true,
          masked_key: "sk-...e2e9",
          created_at: new Date().toISOString(),
        }),
      });
    }

    return route.fulfill({
      status: 200,
      contentType: "application/json",
      body: JSON.stringify({
        keys: [
          { provider: "openai", configured: true, masked_key: "sk-...9999", validation_status: "valid" },
          { provider: "anthropic", configured: false, validation_status: "not_configured" },
        ],
      }),
    });
  });

  await page.route("**/api/v1/byok/keys/*/rotate", async (route: Route) => {
    return route.fulfill({
      status: 200,
      contentType: "application/json",
      body: JSON.stringify({
        provider: "openai",
        configured: true,
        masked_key: "sk-...rotated",
        created_at: new Date().toISOString(),
      }),
    });
  });

  // 5. RAG Pipeline
  await page.route("**/api/v1/rag/query", async (route: Route) => {
    return route.fulfill({
      status: 200,
      contentType: "application/json",
      body: JSON.stringify({
        answer: "Here is the grounded document synthesis.",
        citations: [
          { source: "architecture.pdf", score: 0.94, chunk_id: "chk-1" },
        ],
      }),
    });
  });

  await page.route("**/api/v1/rag/ingest*", async (route: Route) => {
    return route.fulfill({
      status: 200,
      contentType: "application/json",
      body: JSON.stringify({
        task_id: "ingest-task-001",
        status: "completed",
        document_id: "doc-new-123",
        chunks_created: 14,
      }),
    });
  });

  // 6. FinOps
  await page.route("**/api/v1/finops/summary*", async (route: Route) => {
    return route.fulfill({
      status: 200,
      contentType: "application/json",
      body: JSON.stringify({
        tenant_id: user.tenantId,
        period: "2026-09",
        total_requests: 1250,
        reconciled_requests: 1250,
        reconciliation_rate: 1.0,
        total_raw_tokens: 1250000,
        total_optimized_tokens: 830000,
        total_physical_tokens_removed: 420000,
        total_cached_tokens: 420000,
        total_uncached_tokens: 830000,
        total_output_tokens: 45000,
        total_baseline_cost_usd: 20.27,
        total_actual_cost_usd: 15.42,
        total_savings_usd: 4.85,
        overall_savings_percentage: 23.9,
        savings_attribution: {
          cache_hit_usd: 3.2,
          physical_reduction_usd: 1.65,
          provider_cache_usd: 0.0,
          model_routing_usd: 0.0,
          avoided_retries_usd: 0.0,
          total_savings_usd: 4.85,
        },
        budget_status: {
          tenant_id: user.tenantId,
          period: "2026-09",
          token_quota: 5000000,
          tokens_used: 1250000,
          tokens_remaining: 3750000,
          percentage_tokens_used: 25.0,
          warning_threshold: 0.8,
          dollar_spent_usd: 15.42,
          is_suspended: false,
        },
      }),
    });
  });

  await page.route("**/api/v1/finops/budget", async (route: Route) => {
    return route.fulfill({
      status: 200,
      contentType: "application/json",
      body: JSON.stringify({
        monthly_budget_usd: 100.0,
        current_spend_usd: 15.42,
        alert_threshold_percent: 80,
      }),
    });
  });

  await page.route("**/api/v1/finops/transactions*", async (route: Route) => {
    return route.fulfill({
      status: 200,
      contentType: "application/json",
      body: JSON.stringify([
        {
          id: "tx-1",
          tenant_id: user.tenantId,
          model: "gpt-4o",
          prompt_tokens: 120,
          completion_tokens: 80,
          cost_usd: 0.002,
          created_at: new Date().toISOString(),
        },
      ]),
    });
  });

  // 7. Analytics
  await page.route("**/api/v1/analytics/dashboard", async (route: Route) => {
    return route.fulfill({
      status: 200,
      contentType: "application/json",
      body: JSON.stringify({
        total_requests: 12450,
        average_latency_ms: 185,
        error_rate_percent: 0.02,
        active_users: 18,
      }),
    });
  });

  // 8. Admin routes
  await page.route("**/api/v1/admin/users*", async (route: Route) => {
    if (!isAdmin) {
      return route.fulfill({
        status: 403,
        contentType: "application/json",
        body: JSON.stringify({ code: 403, message: "Forbidden: Admin privileges required", data: null }),
      });
    }

    return route.fulfill({
      status: 200,
      contentType: "application/json",
      body: JSON.stringify({
        code: 200,
        message: "OK",
        data: {
          items: [
            { id: 1, email: "developer@jakeai.com", role: "developer", isActive: true, createdAt: "2026-09-01T00:00:00Z" },
            { id: 2, email: "admin@jakeai.com", role: "admin", isActive: true, createdAt: "2026-09-01T00:00:00Z" },
          ],
          total: 2,
          page: 1,
          limit: 10,
        },
      }),
    });
  });

  await page.route("**/api/v1/admin/audit-log*", async (route: Route) => {
    return route.fulfill({
      status: 200,
      contentType: "application/json",
      body: JSON.stringify({
        code: 200,
        message: "OK",
        data: {
          items: [
            { id: 1, action: "USER_LOGIN", resource: "auth", ipAddress: "127.0.0.1", success: true, createdAt: new Date().toISOString() },
          ],
          total: 1,
        },
      }),
    });
  });
}

/**
 * Composite default mock setup combining Auth and Business endpoints
 */
export async function setupDefaultMocks(page: Page, user: User = ADMIN_USER) {
  await setupAuthMocks(page, user);
  await setupBusinessApiMocks(page, user);
}
