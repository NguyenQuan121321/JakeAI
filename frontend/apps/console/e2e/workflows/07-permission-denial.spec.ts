import { test, expect } from "@playwright/test";
import { setupDefaultMocks } from "../fixtures/api-mocks";

test.describe("Workflow 11: RBAC Route & Action Permission Denial", () => {
  test("denies non-admin developer user access to /admin and presents permission boundary", async ({ page }) => {
    // Setup mocks with developer role (non-admin)
    await setupDefaultMocks(page, { role: "member", email: "dev-nonadmin@jakeai.com", id: 2 });

    await page.addInitScript(() => {
      window.sessionStorage.setItem("jakeai_access_token", "mock-access-token-jwt-valid");
      window.sessionStorage.setItem("jakeai_refresh_token", "mock-refresh-token-valid");
      window.sessionStorage.setItem("jakeai_user_override", JSON.stringify({
        id: "usr_developer_01",
        name: "Dev User",
        email: "dev@jakeai.com",
        tenantId: "tenant_jakeai_core",
        roles: ["member"],
        permissions: ["agent:read", "rag:read", "read:workspace"],
      }));
    });

    await page.goto("/admin");

    // Must display PermissionDeniedState
    await expect(page.getByRole("alert")).toBeVisible();
    await expect(page.getByRole("heading", { name: /Access Restricted/i })).toBeVisible();
    await expect(page.getByText(/Return to Workspace/i)).toBeVisible();

    // Clicking Return to Workspace navigates back safely
    await page.getByRole("button", { name: /Return to Workspace/i }).click();
    await expect(page).toHaveURL(/.*workspace/);
  });
});
