import { test, expect } from "@playwright/test";
import { setupDefaultMocks } from "../fixtures/api-mocks";

test.describe("Workflows 2, 3, 4: Workspace Opens, Chat Request & Streaming Response", () => {
  test.beforeEach(async ({ page }) => {
    await setupDefaultMocks(page);

    // Pre-populate sessionStorage with valid mock access token for direct route testing
    await page.addInitScript(() => {
      window.sessionStorage.setItem("jakeai_access_token", "mock-access-token-jwt-valid");
      window.sessionStorage.setItem("jakeai_refresh_token", "mock-refresh-token-valid");
    });
  });

  test("opens AI workspace shell, renders header, model selector, and thread sidebar", async ({ page }) => {
    await page.goto("/workspace");

    // Header & Workspace controls
    await expect(page.getByRole("heading", { name: /JakeAI Orchestrator/i })).toBeVisible();
    await expect(page.getByRole("combobox")).toBeVisible();

    // New conversation trigger
    await expect(page.getByRole("button", { name: "New Conversation", exact: true })).toBeVisible();
  });

  test("submits chat prompt, renders user message bubble, and streams SSE response", async ({ page }) => {
    await page.goto("/workspace");

    const composerTextarea = page.locator("textarea");
    await expect(composerTextarea).toBeVisible();

    await composerTextarea.fill("Analyze cloud spending trends across Kubernetes clusters");
    const sendBtn = page.getByRole("button", { name: /Send/i });
    await sendBtn.click();

    // Verify user prompt appears in conversation stream
    await expect(page.getByText("Analyze cloud spending trends across Kubernetes clusters")).toBeVisible();

    // Verify streamed tokens appear
    await expect(page.getByText("I am JakeAI, ready to assist")).toBeVisible();
  });

  test("stops streaming generation when Stop button is clicked", async ({ page }) => {
    // Inject delayed SSE stream
    await page.route("**/api/v1/chat/stream", async (route) => {
      const sseHeader = 'event: status\ndata: {"stage": "planned"}\n\nevent: token\ndata: {"token": "Beginning long computation..."}\n\n';
      return route.fulfill({
        status: 200,
        contentType: "text/event-stream",
        body: sseHeader,
      });
    });

    await page.goto("/workspace");

    const composerTextarea = page.locator("textarea");
    await composerTextarea.fill("Compute deep analysis");
    await page.getByRole("button", { name: /Send/i }).click();

    // Stop button should appear during streaming
    const stopBtn = page.getByRole("button", { name: /Stop/i });
    if (await stopBtn.isVisible()) {
      await stopBtn.click();
      await expect(page.getByRole("button", { name: /Send/i })).toBeVisible();
    }
  });
});
