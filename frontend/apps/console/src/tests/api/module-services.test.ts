/**
 * Module Services Integration Tests
 *
 * Verifies that each typed service correctly targets the OpenAPI/FinnApiGo endpoint contract
 * and deserializes responses strictly adhering to generated schema types.
 */

import { describe, it, expect } from "vitest";
import { healthService } from "@/api/services/health.service";
import { agentService } from "@/api/services/agent.service";
import { gatewayService } from "@/api/services/gateway.service";
import { ragService } from "@/api/services/rag.service";
import { byokService } from "@/api/services/byok.service";
import { finopsService } from "@/api/services/finops.service";
import { analyticsService } from "@/api/services/analytics.service";
import { providersService } from "@/api/services/providers.service";
import { adminService } from "@/api/services/admin.service";

describe("Typed Module Services Contract Verification", () => {
  it("healthService calls all health probe variants", async () => {
    const health = await healthService.getHealth();
    expect(health.status).toBe("healthy");

    const live = await healthService.getLiveness();
    expect(live.status).toBe("alive");

    const ready = await healthService.getReadiness();
    expect(ready.status).toBe("ready");

    const root = await healthService.getRootHealth();
    expect(root.status).toBe("healthy");
  });

  it("agentService manages tasks, runs, approvals, and metrics", async () => {
    const metrics = await agentService.getMetrics();
    expect(metrics.runs_completed).toBe(12);

    const approvals = await agentService.listPendingApprovals();
    expect(approvals).toHaveLength(1);
    expect(approvals[0].approval_id).toBe("appr-01");

    const task = await agentService.createTask({
      goal: "Execute system audit",
    });
    expect(task.goal).toBe("Execute system audit");

    const fetchedTask = await agentService.getTask("task-123");
    expect(fetchedTask.task_id).toBe("task-123");

    const run = await agentService.startRun("task-123", {
      async_execution: true,
    });
    expect(run.status).toBe("running");

    const fetchedRun = await agentService.getRun("task-123", "run-456");
    expect(fetchedRun.run_id).toBe("run-456");
    expect(fetchedRun.status).toBe("completed");

    const decision = await agentService.decideApproval("task-123", "run-456", "appr-01", {
      approved: true,
      reason: "Operator sign-off granted",
    });
    expect(decision.status).toBe("approved");

    const cancelled = await agentService.cancelRun("task-123", "run-456");
    expect(cancelled.status).toBe("cancelled");
  });

  it("gatewayService lists models and manages quotas", async () => {
    const models = await gatewayService.listModels();
    expect(models.data).toHaveLength(3);
    expect(models.data[0].id).toBe("gpt-4o");

    const quota = await gatewayService.getQuota();
    expect(quota.quota_limit).toBe(1000000);

    const updated = await gatewayService.updateQuota({
      new_limit: 5000000,
    });
    expect(updated.quota_limit).toBe(5000000);
  });

  it("ragService executes query, generation, and ingestion", async () => {
    const queryRes = await ragService.query({
      query: "perimeter security",
      top_k: 5,
      select_context: true,
      max_context_tokens: 2048,
    });
    expect(queryRes.chunks).toHaveLength(1);
    expect(queryRes.chunks[0].chunk_id).toBe("chunk-1");

    const genRes = await ragService.generate({
      query: "summarize policies",
      top_k: 5,
      max_context_tokens: 2048,
    });
    expect(genRes.answer).toContain("summarize policies");
    expect(genRes.citations).toHaveLength(1);

    const ingestRes = await ragService.ingest({
      content: "policy text",
      source: "policy.pdf",
      chunk_size: 512,
      chunk_overlap: 64,
    });
    expect((ingestRes as { status: string }).status).toBe("accepted");

    const taskState = await ragService.getIngestionTask("rag-task-555");
    expect(taskState.status).toBe("completed");
  });

  it("byokService manages provider API keys", async () => {
    const list = await byokService.listKeys();
    expect(list.keys).toHaveLength(2);

    const stored = await byokService.storeKey({
      provider: "cohere",
      api_key: "cohere-secret-key-1234",
      validate_key: true,
    });
    expect(stored.provider).toBe("cohere");
    expect(stored.masked_key).toContain("1234");

    const validated = await byokService.validateCandidateKey({
      provider: "cohere",
      api_key: "cohere-secret-key-1234",
    });
    expect(validated.is_valid).toBe(true);

    const deleted = await byokService.deleteKey("cohere");
    expect(deleted.message).toBe("Key revoked and deleted");
  });

  it("finopsService tracks token spend, budgets, and transactions", async () => {
    const summary = await finopsService.getSummary();
    expect(summary.total_requests).toBe(1420);
    expect(summary.budget_status.dollar_spent_usd).toBe(142.85);

    const budget = await finopsService.getBudget();
    expect(budget.token_quota).toBe(5000000);

    const updatedBudget = await finopsService.updateBudget({
      token_quota: 10000000,
      dollar_budget_usd: 1000.0,
    });
    expect(updatedBudget.token_quota).toBe(10000000);

    const txs = await finopsService.listTransactions();
    expect(txs).toHaveLength(1);
    expect(txs[0].model).toBe("gpt-4o");

    const recon = await finopsService.getReconciliation();
    expect(recon.total_reconciled).toBe(1420);
  });

  it("analyticsService fetches dashboards and telemetry metrics", async () => {
    const dashboard = await analyticsService.getDashboard();
    expect(dashboard.tokens_processed).toBe(48200);

    const metrics = await analyticsService.getMetrics();
    expect(metrics.uptime_seconds).toBe(86400);

    const sub = await analyticsService.getSubscription();
    expect(sub.plan_name).toBe("Enterprise Dedicated");
  });

  it("providersService aggregates model discovery and BYOK state", async () => {
    const providers = await providersService.getProvidersWithStatus();
    expect(providers.length).toBeGreaterThan(0);
    const openai = providers.find((p) => p.provider === "openai");
    expect(openai).toBeDefined();
    expect(openai?.hasByokKey).toBe(true);
    expect(openai?.models.some((m) => m.id === "gpt-4o")).toBe(true);
  });

  it("adminService fetches users and audit logs", async () => {
    const users = await adminService.listUsers();
    expect(users).toHaveLength(2);
    expect(users[0].username).toBe("alex.mercer");

    const auditLogs = await adminService.listAuditLogs();
    expect(auditLogs).toHaveLength(1);
    expect(auditLogs[0].action).toBe("USER_LOGIN");
  });
});
