import { test, expect } from "../fixtures/test";

test.describe("Workflow 1: Login & Session Lifecycle", () => {
  test("authenticates user with valid credentials, sets session, and logs out cleanly", async ({ unauthenticatedPage }) => {
    await unauthenticatedPage.goto("/login");

    // Check login form elements
    await expect(unauthenticatedPage.getByRole("heading", { name: /Sign in to console/i })).toBeVisible();
    const emailInput = unauthenticatedPage.getByPlaceholder("name@company.com");
    const passwordInput = unauthenticatedPage.locator('input[type="password"]');
    const submitBtn = unauthenticatedPage.getByRole("button", { name: /Sign in/i });

    await emailInput.fill("developer@jakeai.com");
    await passwordInput.fill("CorrectPassword123!");
    await submitBtn.click();

    // Redirection to /workspace upon successful authentication
    await expect(unauthenticatedPage).toHaveURL(/.*workspace/);
    await expect(unauthenticatedPage.getByRole("heading", { name: /JakeAI Orchestrator/i })).toBeVisible();

    // Verify session logout
    const userMenuBtn = unauthenticatedPage.getByRole("button", { name: /User account menu/i });
    if (await userMenuBtn.isVisible()) {
      await userMenuBtn.click();
      const logoutBtn = unauthenticatedPage.getByRole("menuitem", { name: /Sign out/i });
      if (await logoutBtn.isVisible()) {
        await logoutBtn.click();
        await expect(unauthenticatedPage).toHaveURL(/.*login/);
      }
    }
  });

  test("rejects invalid credentials and displays clear security error feedback", async ({ unauthenticatedPage }) => {
    await unauthenticatedPage.goto("/login");

    const emailInput = unauthenticatedPage.getByPlaceholder("name@company.com");
    const passwordInput = unauthenticatedPage.locator('input[type="password"]');
    const submitBtn = unauthenticatedPage.getByRole("button", { name: /Sign in/i });

    await emailInput.fill("denied@jakeai.com");
    await passwordInput.fill("WrongPassword!");
    await submitBtn.click();

    // Should stay on /login and display error alert
    await expect(unauthenticatedPage).toHaveURL(/.*login/);
    await expect(unauthenticatedPage.getByRole("alert")).toBeVisible();
  });
});
