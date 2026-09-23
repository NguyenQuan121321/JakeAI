import { test, expect } from "../fixtures/test";

test.describe("Workflows 5, 6, 7: Agent Task, Agent Run & Human-in-the-Loop Approval", () => {
  test("creates an agent task and starts autonomous run on agent canvas", async ({ authenticatedPage }) => {
    await authenticatedPage.goto("/agent");

    await expect(authenticatedPage.getByRole("heading", { name: /Agent Orchestration Canvas/i })).toBeVisible();

    const goalInput = authenticatedPage.getByTestId("canvas-goal-input");
    await expect(goalInput).toBeVisible();
    await goalInput.fill("Automate microservice dependency vulnerability scanner");

    const startBtn = authenticatedPage.getByTestId("start-run-button");
    await expect(startBtn).toBeEnabled();
    await startBtn.click();

    // Verify task creation & run execution triggered
    await expect(authenticatedPage.getByTestId("cancel-run-button")).toBeVisible();
  });

  test("inspects historical runs and pending approval gates on /agent/runs", async ({ authenticatedPage }) => {
    await authenticatedPage.goto("/agent/runs");

    await expect(authenticatedPage.getByRole("heading", { name: /Agent Execution Runs/i })).toBeVisible();

    // Check presence of data table
    await expect(authenticatedPage.getByText("run-882")).toBeVisible();
    await expect(authenticatedPage.getByText("run-884")).toBeVisible();

    // Click on row to view run inspector dialog
    await authenticatedPage.getByText("run-882").click();
    await expect(authenticatedPage.getByRole("dialog")).toBeVisible();
    await expect(authenticatedPage.getByText(/Execution Run:\s*run-882/i)).toBeVisible();

    // Close dialog
    await authenticatedPage.keyboard.press("Escape");
    await expect(authenticatedPage.getByRole("dialog")).not.toBeVisible();
  });
});
