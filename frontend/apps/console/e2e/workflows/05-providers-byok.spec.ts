import { test, expect } from "../fixtures/test";

test.describe("Workflow 9: Provider Selection & BYOK Credential Vault", () => {
  test("renders provider catalog, metrics, and zero-retention keystore banner", async ({ authenticatedPage }) => {
    await authenticatedPage.goto("/providers");

    await expect(authenticatedPage.getByRole("heading", { name: /Providers, Models & BYOK Console/i })).toBeVisible();
    await expect(authenticatedPage.getByText(/Stateless Zero-Retention Cryptographic Keystore Active/i)).toBeVisible();

    // Verify presence of providers in vault table
    await expect(authenticatedPage.getByRole("heading", { name: "OpenAI", exact: true })).toBeVisible();
  });

  test("opens BYOK Key dialog, submits key rotation, and verifies zero raw secret retention", async ({ authenticatedPage }) => {
    await authenticatedPage.goto("/providers");

    const configureBtn = authenticatedPage.getByRole("button", { name: /Rotate Key|Configure Key|Rotate/i }).first();
    if (await configureBtn.isVisible()) {
      await configureBtn.click();

      // Dialog opens
      await expect(authenticatedPage.getByRole("dialog")).toBeVisible();

      // Enter mock key
      const keyInput = authenticatedPage.getByPlaceholder(/sk-/i);
      if (await keyInput.isVisible()) {
        await keyInput.fill("sk-test-candidate-key-12345");
        const submitBtn = authenticatedPage.getByRole("button", { name: /Save Key|Rotate Key|Store Key/i });
        if (await submitBtn.isVisible()) {
          await submitBtn.click();
        }
      }

      // Check localStorage & sessionStorage for any raw secret leaks
      const localStorageKeys = await authenticatedPage.evaluate(() => JSON.stringify(window.localStorage));
      const sessionStorageKeys = await authenticatedPage.evaluate(() => JSON.stringify(window.sessionStorage));
      expect(localStorageKeys).not.toContain("sk-test-candidate-key-12345");
      expect(sessionStorageKeys).not.toContain("sk-test-candidate-key-12345");
    }
  });
});
