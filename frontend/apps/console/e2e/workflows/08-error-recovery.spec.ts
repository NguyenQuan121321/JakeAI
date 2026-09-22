import { test, expect } from "../fixtures/test";

test.describe("Workflow 12: Network Degradation & Error Recovery Flow", () => {
  test("displays error banner upon 503 provider downtime, allows retry, and recovers successfully", async ({ authenticatedPage }) => {
    await authenticatedPage.goto("/workspace");

    const composerTextarea = authenticatedPage.locator("textarea");
    await expect(composerTextarea).toBeVisible();

    // Trigger failure by prompting FAIL_503 (handled in mock)
    await composerTextarea.fill("Query test service FAIL_503");
    await authenticatedPage.getByRole("button", { name: /Send/i }).click();

    // Error banner should appear
    await expect(authenticatedPage.getByText(/Generation Encountered an Issue/i)).toBeVisible();
    const retryBtn = authenticatedPage.getByRole("button", { name: /Retry Request/i });
    await expect(retryBtn).toBeVisible();

    // Now update mock route so retry succeeds
    await authenticatedPage.route("**/api/v1/chat/stream", async (route) => {
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
    await expect(authenticatedPage.getByText("Recovered from failure successfully!")).toBeVisible();
  });
});
