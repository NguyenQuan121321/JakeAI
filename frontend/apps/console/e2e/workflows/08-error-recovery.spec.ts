import { test, expect } from "@playwright/test";
import { setupDefaultMocks } from "../fixtures/api-mocks";

test.describe("Workflow 12: Network Degradation & Error Recovery Flow", () => {
  test.beforeEach(async ({ page }) => {
    await setupDefaultMocks(page);

    await page.addInitScript(() => {
      window.sessionStorage.setItem("jakeai_access_token", "mock-access-token-jwt-valid");
      window.sessionStorage.setItem("jakeai_refresh_token", "mock-refresh-token-valid");
    });
  });

  test("displays error banner upon 503 provider downtime, allows retry, and recovers successfully", async ({ page }) => {
    await page.goto("/workspace");

    const composerTextarea = page.locator("textarea");
    await expect(composerTextarea).toBeVisible();

    // Trigger failure by prompting FAIL_503 (handled in mock)
    await composerTextarea.fill("Query test service FAIL_503");
    await page.getByRole("button", { name: /Send/i }).click();

    // Error banner should appear
    await expect(page.getByText(/Generation Encountered an Issue/i)).toBeVisible();
    const retryBtn = page.getByRole("button", { name: /Retry Request/i });
    await expect(retryBtn).toBeVisible();

    // Now update mock route so retry succeeds
    await page.route("**/api/v1/chat/stream", async (route) => {
      const ssePayload = [
        'event: token\ndata: {"token": "Recovered from failure successfully!"}\n\n',
        'event: done\ndata: {"status": "completed"}\n\n',
      ].join("");

      return route.fulfill({
        status: 200,
        contentType: "text/event-stream",
        body: ssePayload,
      });
    });

    // Click retry
    await retryBtn.click();

    // Verify recovery
    await expect(page.getByText("Recovered from failure successfully!")).toBeVisible();
  });
});
