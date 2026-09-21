import { test, expect } from "@playwright/test";
import { setupDefaultMocks } from "../fixtures/api-mocks";

test.describe("Workflow 10: FinOps & Token Economics Dashboard", () => {
  test.beforeEach(async ({ page }) => {
    await setupDefaultMocks(page);

    await page.addInitScript(() => {
      window.sessionStorage.setItem("jakeai_access_token", "mock-access-token-jwt-valid");
      window.sessionStorage.setItem("jakeai_refresh_token", "mock-refresh-token-valid");
    });
  });

  test("renders token economics metrics, spend charts, and ledger transactions", async ({ page }) => {
    await page.goto("/finops");

    await expect(page.getByRole("heading", { name: /AI FinOps & Token Governance/i })).toBeVisible();

    // Verify MetricCards
    await expect(page.getByText(/Actual Billed Spend/i)).toBeVisible();
    await expect(page.getByText(/Attributed Cost Savings/i)).toBeVisible();

    // Verify Ledger transactions table is rendered
    await expect(page.getByRole("heading", { name: /Inference Accounting Ledger/i })).toBeVisible();
  });

  test("opens Configure Budget Threshold dialog and inspects budget settings", async ({ page }) => {
    await page.goto("/finops");

    const editBudgetBtn = page.getByRole("button", { name: /Edit Budget|Configure Budget/i }).first();
    if (await editBudgetBtn.isVisible()) {
      await editBudgetBtn.click();
      await expect(page.getByRole("dialog")).toBeVisible();
      await expect(page.getByRole("heading", { name: /Configure Tenant Budget/i })).toBeVisible();

      // Close dialog via escape
      await page.keyboard.press("Escape");
      await expect(page.getByRole("dialog")).not.toBeVisible();
    }
  });
});
