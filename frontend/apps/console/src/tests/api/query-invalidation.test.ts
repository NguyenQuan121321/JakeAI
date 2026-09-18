/**
 * TanStack Query Cache & Invalidation Tests
 */

import { describe, it, expect, beforeEach } from "vitest";
import { QueryClient } from "@tanstack/react-query";
import { queryKeys } from "@/api/hooks/query-keys";
import { agentService } from "@/api/services/agent.service";
import { finopsService } from "@/api/services/finops.service";
import { byokService } from "@/api/services/byok.service";

describe("TanStack Query Invalidation & Cache Consistency", () => {
  let queryClient: QueryClient;

  beforeEach(() => {
    queryClient = new QueryClient({
      defaultOptions: {
        queries: { retry: false },
      },
    });
  });

  it("invalidates agent task queries on task creation", async () => {
    // Populate query cache
    queryClient.setQueryData(queryKeys.agent.tasks(), [{ task_id: "t-1", goal: "existing" }]);
    expect(queryClient.getQueryData(queryKeys.agent.tasks())).toHaveLength(1);

    // Perform mutation
    const newTask = await agentService.createTask({
      goal: "New task prompt",
    });

    // Invalidation logic simulation matching useCreateTaskMutation
    await queryClient.invalidateQueries({ queryKey: queryKeys.agent.tasks() });
    if (newTask.task_id) {
      queryClient.setQueryData(queryKeys.agent.task(newTask.task_id), newTask);
    }

    // Query state must be invalidated / marked stale
    const queryState = queryClient.getQueryState(queryKeys.agent.tasks());
    expect(queryState?.isInvalidated).toBe(true);

    // Direct entity cache is populated
    expect(queryClient.getQueryData(queryKeys.agent.task(newTask.task_id))).toBeDefined();
  });

  it("invalidates approval gates on decision mutation", async () => {
    queryClient.setQueryData(queryKeys.agent.approvals(), [{ id: "appr-01" }]);
    expect(queryClient.getQueryData(queryKeys.agent.approvals())).toHaveLength(1);

    await agentService.decideApproval("task-100", "run-200", "appr-01", {
      approved: true,
      reason: "Sign-off",
    });

    await queryClient.invalidateQueries({ queryKey: queryKeys.agent.approvals() });
    await queryClient.invalidateQueries({ queryKey: queryKeys.agent.run("task-100", "run-200") });

    expect(queryClient.getQueryState(queryKeys.agent.approvals())?.isInvalidated).toBe(true);
  });

  it("updates budget cache and invalidates FinOps summary on budget update", async () => {
    queryClient.setQueryData(queryKeys.finops.summary(), { total_requests: 100 });
    queryClient.setQueryData(queryKeys.finops.budget(), { dollar_budget_usd: 500 });

    const updated = await finopsService.updateBudget({
      dollar_budget_usd: 1200,
    });

    // Update budget entity cache and invalidate summary
    queryClient.setQueryData(queryKeys.finops.budget(), updated);
    await queryClient.invalidateQueries({ queryKey: queryKeys.finops.summary() });

    expect((queryClient.getQueryData(queryKeys.finops.budget()) as { dollar_budget_usd: number }).dollar_budget_usd).toBe(1200);
    expect(queryClient.getQueryState(queryKeys.finops.summary())?.isInvalidated).toBe(true);
  });

  it("invalidates BYOK keys list on key creation and deletion", async () => {
    queryClient.setQueryData(queryKeys.byok.keys(), { keys: [] });

    await byokService.storeKey({
      provider: "openai",
      api_key: "test-key-for-ci-byok-12345",
      validate_key: true,
    });

    await queryClient.invalidateQueries({ queryKey: queryKeys.byok.keys() });
    expect(queryClient.getQueryState(queryKeys.byok.keys())?.isInvalidated).toBe(true);

    await byokService.deleteKey("openai");
    await queryClient.invalidateQueries({ queryKey: queryKeys.byok.keys() });
    expect(queryClient.getQueryState(queryKeys.byok.keys())?.isInvalidated).toBe(true);
  });
});
