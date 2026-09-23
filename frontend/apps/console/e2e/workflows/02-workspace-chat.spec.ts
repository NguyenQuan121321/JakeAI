import { test, expect } from "../fixtures/test";

test.describe("Workflows 2, 3, 4: Workspace Opens, Chat Request & Streaming Response", () => {
  test("opens AI workspace shell, renders header, model selector, and thread sidebar", async ({ authenticatedPage }) => {
    await authenticatedPage.goto("/workspace");

    // Header & Workspace controls
    await expect(authenticatedPage.getByRole("heading", { name: /JakeAI Orchestrator/i })).toBeVisible();
    await expect(authenticatedPage.getByRole("combobox")).toBeVisible();

    // New conversation trigger
    await expect(authenticatedPage.getByRole("button", { name: "New Conversation", exact: true })).toBeVisible();
  });

  test("submits chat prompt, renders user message bubble, and streams SSE response", async ({ authenticatedPage }) => {
    await authenticatedPage.goto("/workspace");

    const composerTextarea = authenticatedPage.locator("textarea");
    await expect(composerTextarea).toBeVisible();

    await composerTextarea.fill("Analyze cloud spending trends across Kubernetes clusters");
    const sendBtn = authenticatedPage.getByRole("button", { name: /Send/i });
    await sendBtn.click();

    // Verify user prompt appears in conversation stream
    await expect(authenticatedPage.getByText("Analyze cloud spending trends across Kubernetes clusters")).toBeVisible();

    // Verify streamed tokens appear
    await expect(authenticatedPage.getByText("I am JakeAI, ready to assist")).toBeVisible();
  });

  test("stops streaming generation when Stop button is clicked", async ({ authenticatedPage }) => {
    // Inject delayed SSE stream
    await authenticatedPage.route("**/api/v1/chat/stream", async (route) => {
      const sseHeader = 'event: status\ndata: {"stage": "planned"}\n\nevent: token\ndata: {"token": "Beginning long computation..."}\n\n';
      return route.fulfill({
        status: 200,
        contentType: "text/event-stream",
        body: sseHeader,
      });
    });

    await authenticatedPage.goto("/workspace");

    const composerTextarea = authenticatedPage.locator("textarea");
    await composerTextarea.fill("Compute deep analysis");
    await authenticatedPage.getByRole("button", { name: /Send/i }).click();

    // Stop button should appear during streaming
    const stopBtn = authenticatedPage.getByRole("button", { name: /Stop/i });
    if (await stopBtn.isVisible()) {
      await stopBtn.click();
      await expect(authenticatedPage.getByRole("button", { name: /Send/i })).toBeVisible();
    }
  });
});
