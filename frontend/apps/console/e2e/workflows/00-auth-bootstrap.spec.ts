import { test, expect } from "../fixtures/test";

test.describe("Workflow 0: Shared Authentication Bootstrap & Authorization Regression", () => {
  test("1. authenticated fixture reaches /workspace", async ({ authenticatedPage }) => {
    await authenticatedPage.goto("/workspace");
    await expect(authenticatedPage.getByRole("heading", { name: /JakeAI Orchestrator/i })).toBeVisible();
    await expect(authenticatedPage).toHaveURL(/.*workspace/);
  });

  test("2. authenticated fixture reaches /finops", async ({ authenticatedPage }) => {
    await authenticatedPage.goto("/finops");
    await expect(authenticatedPage.getByRole("heading", { name: /AI FinOps & Token Governance/i })).toBeVisible();
    await expect(authenticatedPage).toHaveURL(/.*finops/);
  });

  test("3. authenticated fixture reaches /agent", async ({ authenticatedPage }) => {
    await authenticatedPage.goto("/agent");
    await expect(authenticatedPage.getByRole("heading", { name: /Agent Orchestration Canvas/i })).toBeVisible();
    await expect(authenticatedPage).toHaveURL(/.*agent/);
  });

  test("4. authenticated fixture reaches /rag", async ({ authenticatedPage }) => {
    await authenticatedPage.goto("/rag");
    await expect(authenticatedPage.getByRole("heading", { name: /RAG & Knowledge Console/i })).toBeVisible();
    await expect(authenticatedPage).toHaveURL(/.*rag/);
  });

  test("5. member fixture is denied /admin and sees permission boundary", async ({ memberPage }) => {
    await memberPage.goto("/admin");
    await expect(memberPage.getByRole("alert")).toBeVisible();
    await expect(memberPage.getByRole("heading", { name: /Access Restricted/i })).toBeVisible();
    await expect(memberPage.getByRole("button", { name: /Return to Workspace/i })).toBeVisible();
  });

  test("6. admin fixture can access /admin", async ({ adminPage }) => {
    await adminPage.goto("/admin");
    await expect(adminPage.getByRole("heading", { name: /Enterprise Administration/i })).toBeVisible();
    await expect(adminPage).toHaveURL(/.*admin/);
  });

  test("7. unauthenticated fixture reaches /login and remains without redirection", async ({ unauthenticatedPage }) => {
    await unauthenticatedPage.goto("/login");
    await expect(unauthenticatedPage.getByRole("heading", { name: /Sign in to console/i })).toBeVisible();
    await expect(unauthenticatedPage).toHaveURL(/.*login/);
  });

  test("8. unauthenticated access to protected route redirects to /login", async ({ unauthenticatedPage }) => {
    await unauthenticatedPage.goto("/workspace");
    await expect(unauthenticatedPage).toHaveURL(/.*login/);
    await expect(unauthenticatedPage.getByRole("heading", { name: /Sign in to console/i })).toBeVisible();
  });

  test("9. authenticated identity renders correct tenant boundary context", async ({ authenticatedPage }) => {
    await authenticatedPage.goto("/workspace");
    await expect(authenticatedPage.getByText(/JakeAI Core Platform/i)).toBeVisible();
  });

  test("10. authenticated identity enables authorized actions based on permissions", async ({ authenticatedPage }) => {
    await authenticatedPage.goto("/finops");
    await expect(authenticatedPage.getByRole("button", { name: /Edit Budget/i })).toBeVisible();
  });
});
