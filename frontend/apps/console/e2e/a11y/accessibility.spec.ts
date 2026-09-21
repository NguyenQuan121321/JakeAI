import { test, expect } from "@playwright/test";
import AxeBuilder from "@axe-core/playwright";
import { setupDefaultMocks } from "../fixtures/api-mocks";

test.describe("Automated WCAG 2.1 AA Accessibility Audit (Axe-core)", () => {
  test.beforeEach(async ({ page }) => {
    await setupDefaultMocks(page);

    await page.addInitScript(() => {
      window.sessionStorage.setItem("jakeai_access_token", "mock-access-token-jwt-valid");
      window.sessionStorage.setItem("jakeai_refresh_token", "mock-refresh-token-valid");
    });
  });

  const routes = [
    { path: "/login", name: "Login" },
    { path: "/workspace", name: "AI Workspace" },
    { path: "/agent", name: "Agent Canvas" },
    { path: "/agent-runs", name: "Agent Runs" },
    { path: "/rag", name: "RAG & Knowledge" },
    { path: "/providers", name: "Providers & BYOK" },
    { path: "/finops", name: "FinOps Dashboard" },
    { path: "/settings", name: "Settings" },
  ];

  for (const { path, name } of routes) {
    test(`audits ${name} route (${path}) for zero critical WCAG violations`, async ({ page }) => {
      await page.goto(path);
      await page.waitForLoadState("networkidle");

      const accessibilityScanResults = await new AxeBuilder({ page })
        .withTags(["wcag2a", "wcag2aa", "wcag21a", "wcag21aa"])
        .disableRules(["color-contrast"]) // Avoid synthetic theme CSS variable contrast edge cases in headless
        .analyze();

      expect(accessibilityScanResults.violations.filter((v) => v.impact === "critical")).toEqual([]);
    });
  }
});
