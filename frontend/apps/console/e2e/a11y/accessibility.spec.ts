import { test, expect } from "../fixtures/test";
import AxeBuilder from "@axe-core/playwright";

test.describe("Automated WCAG 2.1 AA Accessibility Audit (Axe-core)", () => {
  test("audits Login route (/login) for zero critical WCAG violations", async ({ unauthenticatedPage }) => {
    await unauthenticatedPage.goto("/login");
    await unauthenticatedPage.waitForLoadState("networkidle");

    const accessibilityScanResults = await new AxeBuilder({ page: unauthenticatedPage })
      .withTags(["wcag2a", "wcag2aa", "wcag21a", "wcag21aa"])
      .disableRules(["color-contrast"])
      .analyze();

    expect(accessibilityScanResults.violations.filter((v) => v.impact === "critical")).toEqual([]);
  });

  const protectedRoutes = [
    { path: "/workspace", name: "AI Workspace" },
    { path: "/agent", name: "Agent Canvas" },
    { path: "/agent/runs", name: "Agent Runs" },
    { path: "/rag", name: "RAG & Knowledge" },
    { path: "/providers", name: "Providers & BYOK" },
    { path: "/finops", name: "FinOps Dashboard" },
    { path: "/settings", name: "Settings" },
  ];

  for (const { path, name } of protectedRoutes) {
    test(`audits ${name} route (${path}) for zero critical WCAG violations`, async ({ authenticatedPage }) => {
      await authenticatedPage.goto(path);
      await authenticatedPage.waitForLoadState("networkidle");

      const accessibilityScanResults = await new AxeBuilder({ page: authenticatedPage })
        .withTags(["wcag2a", "wcag2aa", "wcag21a", "wcag21aa"])
        .disableRules(["color-contrast"])
        .analyze();

      expect(accessibilityScanResults.violations.filter((v) => v.impact === "critical")).toEqual([]);
    });
  }
});
