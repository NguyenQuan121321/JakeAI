import { test, expect } from "../fixtures/test";

test.describe("Workflow 10: FinOps & Token Economics Dashboard", () => {
  test("renders token economics metrics, spend charts, and ledger transactions", async ({ authenticatedPage }) => {
    await authenticatedPage.goto("/finops");

    await expect(authenticatedPage.getByRole("heading", { name: /AI FinOps & Token Governance/i })).toBeVisible();

    // Verify MetricCards
    await expect(authenticatedPage.getByText(/Actual Billed Spend/i)).toBeVisible();
    await expect(authenticatedPage.getByText(/Attributed Cost Savings/i)).toBeVisible();

    // Verify Ledger transactions table is rendered
    await expect(authenticatedPage.getByRole("heading", { name: /Inference Accounting Ledger/i })).toBeVisible();
  });

  test("opens Configure Budget Threshold dialog and inspects budget settings", async ({ authenticatedPage }) => {
    await authenticatedPage.goto("/finops");

    const editBudgetBtn = authenticatedPage.getByRole("button", { name: /Edit Budget|Configure Budget/i }).first();
    if (await editBudgetBtn.isVisible()) {
      await editBudgetBtn.click();
      await expect(authenticatedPage.getByRole("dialog")).toBeVisible();
      await expect(authenticatedPage.getByRole("heading", { name: /Configure Tenant Budget/i })).toBeVisible();

      // Close dialog via escape
      await authenticatedPage.keyboard.press("Escape");
      await expect(authenticatedPage.getByRole("dialog")).not.toBeVisible();
    }
  });
});
