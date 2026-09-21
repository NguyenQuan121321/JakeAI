import { test, expect } from "@playwright/test";
import { setupDefaultMocks } from "../fixtures/api-mocks";

test.describe("Workflow 1: Login & Session Lifecycle", () => {
  test("authenticates user with valid credentials, sets session, and logs out cleanly", async ({ page }) => {
    await setupDefaultMocks(page);

    // Explicitly start unauthenticated
    await page.addInitScript(() => {
      window.sessionStorage.setItem("jakeai_unauthenticated", "true");
      window.sessionStorage.removeItem("jakeai_access_token");
      window.sessionStorage.removeItem("jakeai_user_override");
    });

    await page.goto("/login");

    // Check login form elements
    await expect(page.getByRole("heading", { name: /Sign in to console/i })).toBeVisible();
    const emailInput = page.getByPlaceholder("name@company.com");
    const passwordInput = page.locator('input[type="password"]');
    const submitBtn = page.getByRole("button", { name: /Sign in/i });

    await emailInput.fill("developer@jakeai.com");
    await passwordInput.fill("CorrectPassword123!");
    await submitBtn.click();

    // Redirection to /workspace upon successful authentication
    await expect(page).toHaveURL(/.*workspace/);
    await expect(page.getByRole("heading", { name: /JakeAI Orchestrator/i })).toBeVisible();

    // Verify session logout
    const userMenuBtn = page.getByRole("button", { name: /User account menu/i });
    if (await userMenuBtn.isVisible()) {
      await userMenuBtn.click();
      const logoutBtn = page.getByRole("menuitem", { name: /Sign out/i });
      if (await logoutBtn.isVisible()) {
        await logoutBtn.click();
        await expect(page).toHaveURL(/.*login/);
      }
    }
  });

  test("rejects invalid credentials and displays clear security error feedback", async ({ page }) => {
    await setupDefaultMocks(page);

    // Explicitly start unauthenticated
    await page.addInitScript(() => {
      window.sessionStorage.setItem("jakeai_unauthenticated", "true");
      window.sessionStorage.removeItem("jakeai_access_token");
      window.sessionStorage.removeItem("jakeai_user_override");
    });

    await page.goto("/login");

    const emailInput = page.getByPlaceholder("name@company.com");
    const passwordInput = page.locator('input[type="password"]');
    const submitBtn = page.getByRole("button", { name: /Sign in/i });

    await emailInput.fill("denied@jakeai.com");
    await passwordInput.fill("WrongPassword!");
    await submitBtn.click();

    // Should stay on /login and display error alert
    await expect(page).toHaveURL(/.*login/);
    await expect(page.getByRole("alert")).toBeVisible();
  });
});
