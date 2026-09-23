import { test, expect } from "../fixtures/test";

test.describe("Workflow 8: RAG Query & Ingestion Pipeline", () => {
  test("renders RAG console, switches between tabs, and executes hybrid search", async ({ authenticatedPage }) => {
    await authenticatedPage.goto("/rag");

    await expect(authenticatedPage.getByRole("heading", { name: /RAG & Knowledge Console/i })).toBeVisible();

    // Switch to Documents view
    const docsTab = authenticatedPage.getByRole("tab", { name: /Documents/i });
    await docsTab.click();
    await expect(authenticatedPage.getByText("security-handbook.pdf")).toBeVisible();

    // Switch to Search/Test view
    const searchTab = authenticatedPage.getByRole("tab", { name: /Search\/Test/i });
    if (await searchTab.isVisible()) {
      await searchTab.click();
      const searchInput = authenticatedPage.getByPlaceholder(/Enter query to test hybrid/i);
      if (await searchInput.isVisible()) {
        await searchInput.fill("perimeter isolation");
        await authenticatedPage.getByRole("button", { name: /Search Index/i }).click();
      }
    }
  });

  test("opens Document Upload dialog and submits ingestion task", async ({ authenticatedPage }) => {
    await authenticatedPage.goto("/rag");

    const uploadBtn = authenticatedPage.getByRole("button", { name: /Upload Document/i });
    await expect(uploadBtn).toBeVisible();
    await uploadBtn.click();

    // Dialog appears
    await expect(authenticatedPage.getByRole("dialog")).toBeVisible();
    await expect(authenticatedPage.getByRole("heading", { name: /Ingest Document into Knowledge Base/i })).toBeVisible();

    // Fill document details
    const sourceInput = authenticatedPage.locator("#rag-doc-source");
    const contentInput = authenticatedPage.locator("#rag-doc-content");

    await sourceInput.fill("engineering-playbook.md");
    await contentInput.fill("JakeAI platform enforces immutable audit logging and Zero Trust tenant segregation.");

    const submitIngestBtn = authenticatedPage.getByRole("button", { name: /Enqueue Ingestion Job/i });
    await submitIngestBtn.click();

    // Dialog closes upon submission
    await expect(authenticatedPage.getByRole("dialog")).not.toBeVisible();
  });
});
