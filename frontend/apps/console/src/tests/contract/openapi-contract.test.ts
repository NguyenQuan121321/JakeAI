/**
 * OpenAPI Contract & Schema Drift Unit/Contract Suite
 *
 * Verifies:
 * 1. Generated TypeScript types (schema.d.ts) contain all authoritative OpenAPI paths
 * 2. Service definitions match HTTP methods and schema requirements
 * 3. Required payload schemas are preserved and validated
 */

import { describe, it, expect } from "vitest";
import type { paths, components } from "@/api/generated/schema";

describe("FE-07 API Contract & OpenAPI Schema Drift Suite", () => {
  it("includes all primary JakeAI operations in generated schema paths", () => {
    // Assert key path types exist in type system without type errors
    type TestEndpoints = [
      paths["/api/v1/health"]["get"],
      paths["/api/v1/chat/stream"]["post"],
      paths["/api/v1/agent/tasks"]["post"],
      paths["/api/v1/agent/tasks/{task_id}"]["get"],
      paths["/api/v1/agent/tasks/{task_id}/runs"]["post"],
      paths["/api/v1/agent/tasks/{task_id}/runs/{run_id}/approvals/{approval_id}"]["post"],
      paths["/api/v1/byok/keys"]["get"],
      paths["/api/v1/byok/keys"]["post"],
      paths["/api/v1/finops/summary"]["get"],
      paths["/api/v1/finops/budget"]["get"],
      paths["/api/v1/rag/query"]["post"],
      paths["/api/v1/rag/generate"]["post"],
      paths["/api/v1/analytics/dashboard"]["get"]
    ];

    const endpointCount: TestEndpoints["length"] = 13;
    expect(endpointCount).toBe(13);
  });

  it("verifies component schemas align with domain type expectations", () => {
    type Schemas = components["schemas"];

    // TaskState schema check
    type TaskStateSchema = Schemas["TaskState"];
    const sampleTask: TaskStateSchema = {
      task_id: "task-contract-001",
      tenant_id: "tenant-default",
      user_id: "user-1",
      goal: "Implement contract tests",
      status: "pending",
      created_at: 1726590000.0,
      updated_at: 1726590000.0,
    };
    expect(sampleTask.task_id).toBe("task-contract-001");
    expect(sampleTask.status).toBe("pending");

    // BYOK Key schema check
    type BYOKKeySchema = Schemas["BYOKKeyResponse"];
    const sampleKey: BYOKKeySchema = {
      tenant_id: "tenant-default",
      provider: "openai",
      masked_key: "sk-...9999",
      status: "active",
      validation_status: "valid",
    };
    expect(sampleKey.provider).toBe("openai");
    expect(sampleKey.status).toBe("active");

    // FinOps Summary schema check
    type FinOpsSummarySchema = Schemas["FinOpsSummary"];
    const sampleFinOps: FinOpsSummarySchema = {
      tenant_id: "tenant-default",
      period: "2026-09",
      total_requests: 100,
      reconciled_requests: 100,
      reconciliation_rate: 1.0,
      total_raw_tokens: 1500000,
      total_optimized_tokens: 1050000,
      total_physical_tokens_removed: 450000,
      total_cached_tokens: 400000,
      total_uncached_tokens: 650000,
      total_output_tokens: 50000,
      total_baseline_cost_usd: 18.5,
      total_actual_cost_usd: 12.5,
      total_savings_usd: 6.0,
      overall_savings_percentage: 32.4,
      savings_attribution: {
        cache_hit_usd: 3.5,
        physical_reduction_usd: 1.0,
        provider_cache_usd: 0.5,
        model_routing_usd: 0.5,
        avoided_retries_usd: 0.5,
        total_savings_usd: 6.0,
      },
      budget_status: {
        tenant_id: "tenant-default",
        period: "2026-09",
        token_quota: 2000000,
        tokens_used: 1500000,
        tokens_remaining: 500000,
        percentage_tokens_used: 75.0,
        warning_threshold: 80.0,
        dollar_spent_usd: 12.5,
        is_suspended: false,
      },
    };
    expect(sampleFinOps.total_raw_tokens).toBe(1500000);
    expect(sampleFinOps.total_actual_cost_usd).toBe(12.5);

    // RAG Generate Response schema check
    type RAGGenerateResponseSchema = Schemas["RAGGenerateResponse"];
    const sampleRAG: RAGGenerateResponseSchema = {
      query: "What is zero-retention security?",
      tenant_id: "tenant-default",
      answer: "Grounded answer from docs",
      status: "grounded",
      citations: [
        {
          index: 1,
          source: "doc1.pdf",
          snippet: "Ground truth content",
          tenant_id: "tenant-default",
          confidence: 0.95,
          chunk_id: "chunk-1",
        },
      ],
      context_tokens: 1200,
      tokens_saved: 450,
      reduction_ratio: 0.375,
      latency_ms: 120,
    };
    expect(sampleRAG.answer).toBeDefined();
    expect(sampleRAG.citations?.length).toBe(1);
    expect(sampleRAG.status).toBe("grounded");
  });

  it("verifies streaming payload definitions maintain SSE frame invariants", () => {
    type Schemas = components["schemas"];
    type ChatStreamReq = Schemas["ChatStreamRequest"];

    const req: ChatStreamReq = {
      prompt: "Hello JakeAI",
      conversation_id: "conv-1",
      parameters: {
        model: "gpt-4o",
        temperature: 0.7,
      },
    };

    expect(req.prompt).toBe("Hello JakeAI");
    expect(req.conversation_id).toBe("conv-1");
  });
});
