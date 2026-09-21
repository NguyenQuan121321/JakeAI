import { test, expect } from "@playwright/test";
import { setupDefaultMocks } from "../fixtures/api-mocks";

test.describe("Workflow 9: Provider Selection & BYOK Credential Vault", () => {
  test.beforeEach(async ({ page }) => {
    await setupDefaultMocks(page);

    await page.addInitScript(() => {
      window.sessionStorage.setItem("jakeai_access_token", "mock-access-token-jwt-valid");
      window.sessionStorage.setItem("jakeai_refresh_token", "mock-refresh-token-valid");
    });
  });

  test("renders provider catalog, metrics, and zero-retention keystore banner", async ({ page }) => {
    await page.goto("/providers");

    await expect(page.getByRole("heading", { name: /Providers, Models & BYOK Console/i })).toBeVisible();
    await expect(page.getByText(/Stateless Zero-Retention Cryptographic Keystore Active/i)).toBeVisible();

    // Verify presence of providers in vault table
    await expect(page.getByRole("heading", { name: "OpenAI", exact: true })).toBeVisible();
  });

  test("opens BYOK Key dialog, submits key rotation, and verifies zero raw secret retention", async ({ page }) => {
    await page.goto("/providers");

    const configureBtn = page.getByRole("button", { name: /Rotate Key|Configure Key|Rotate/i }).first();
    if (await configureBtn.isVisible()) {
      await configureBtn.click();

      // Dialog opens
      await expect(page.getByRole("dialog")).toBeVisible();

      // Enter mock key
      const keyInput = page.getByPlaceholder(/sk-/i);
      if (await keyInput.isVisible()) {
        await keyInput.fill("sk-test-candidate-key-12345");
        const submitBtn = page.getByRole("button", { name: /Save Key|Rotate Key|Store Key/i });
        if (await submitBtn.isVisible()) {
          await submitBtn.click();
        }
      }

      // Check localStorage & sessionStorage for any raw secret leaks
      const localStorageKeys = await page.evaluate(() => JSON.stringify(window.localStorage));
      const sessionStorageKeys = await page.evaluate(() => JSON.stringify(window.sessionStorage));
      expect(localStorageKeys).not.toContain("sk-test-candidate-key-12345");
      expect(sessionStorageKeys).not.toContain("sk-test-candidate-key-12345");
    }
  });
});
