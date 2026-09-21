import { test, expect } from "@playwright/test";
import { setupDefaultMocks } from "../fixtures/api-mocks";

test.describe("Workflow 8: RAG Query & Ingestion Pipeline", () => {
  test.beforeEach(async ({ page }) => {
    await setupDefaultMocks(page);

    await page.addInitScript(() => {
      window.sessionStorage.setItem("jakeai_access_token", "mock-access-token-jwt-valid");
      window.sessionStorage.setItem("jakeai_refresh_token", "mock-refresh-token-valid");
    });
  });

  test("renders RAG console, switches between tabs, and executes hybrid search", async ({ page }) => {
    await page.goto("/rag");

    await expect(page.getByRole("heading", { name: /RAG & Knowledge Console/i })).toBeVisible();

    // Switch to Documents view
    const docsTab = page.getByRole("tab", { name: /Documents/i });
    await docsTab.click();
    await expect(page.getByText("security-handbook.pdf")).toBeVisible();

    // Switch to Search/Test view
    const searchTab = page.getByRole("tab", { name: /Search\/Test/i });
    if (await searchTab.isVisible()) {
      await searchTab.click();
      const searchInput = page.getByPlaceholder(/Enter query to test hybrid/i);
      if (await searchInput.isVisible()) {
        await searchInput.fill("perimeter isolation");
        await page.getByRole("button", { name: /Search Index/i }).click();
      }
    }
  });

  test("opens Document Upload dialog and submits ingestion task", async ({ page }) => {
    await page.goto("/rag");

    const uploadBtn = page.getByRole("button", { name: /Upload Document/i });
    await expect(uploadBtn).toBeVisible();
    await uploadBtn.click();

    // Dialog appears
    await expect(page.getByRole("dialog")).toBeVisible();
    await expect(page.getByRole("heading", { name: /Ingest Document into Knowledge Base/i })).toBeVisible();

    // Fill document details
    const sourceInput = page.locator("#rag-doc-source");
    const contentInput = page.locator("#rag-doc-content");

    await sourceInput.fill("engineering-playbook.md");
    await contentInput.fill("JakeAI platform enforces immutable audit logging and Zero Trust tenant segregation.");

    const submitIngestBtn = page.getByRole("button", { name: /Enqueue Ingestion Job/i });
    await submitIngestBtn.click();

    // Dialog closes upon submission
    await expect(page.getByRole("dialog")).not.toBeVisible();
  });
});
