import { test, expect } from "@playwright/test";
import { setupDefaultMocks } from "../fixtures/api-mocks";

test.describe("Workflows 5, 6, 7: Agent Task, Agent Run & Human-in-the-Loop Approval", () => {
  test.beforeEach(async ({ page }) => {
    await setupDefaultMocks(page);

    await page.addInitScript(() => {
      window.sessionStorage.setItem("jakeai_access_token", "mock-access-token-jwt-valid");
      window.sessionStorage.setItem("jakeai_refresh_token", "mock-refresh-token-valid");
    });
  });

  test("creates an agent task and starts autonomous run on agent canvas", async ({ page }) => {
    await page.goto("/agent");

    await expect(page.getByRole("heading", { name: /Agent Orchestration Canvas/i })).toBeVisible();

    const goalInput = page.getByTestId("canvas-goal-input");
    await expect(goalInput).toBeVisible();
    await goalInput.fill("Automate microservice dependency vulnerability scanner");

    const startBtn = page.getByTestId("start-run-button");
    await expect(startBtn).toBeEnabled();
    await startBtn.click();

    // Verify task creation & run execution triggered
    await expect(page.getByTestId("cancel-run-button")).toBeVisible();
  });

  test("inspects historical runs and pending approval gates on /agent/runs", async ({ page }) => {
    await page.goto("/agent/runs");

    await expect(page.getByRole("heading", { name: /Agent Execution Runs/i })).toBeVisible();

    // Check presence of data table
    await expect(page.getByText("run-882")).toBeVisible();
    await expect(page.getByText("run-884")).toBeVisible();

    // Click on row to view run inspector dialog
    await page.getByText("run-882").click();
    await expect(page.getByRole("dialog")).toBeVisible();
    await expect(page.getByText(/Execution Run:\s*run-882/i)).toBeVisible();

    // Close dialog
    await page.keyboard.press("Escape");
    await expect(page.getByRole("dialog")).not.toBeVisible();
  });
});
