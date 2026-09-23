import { test, expect } from "../fixtures/test";

test.describe("Workflow 11: RBAC Route & Action Permission Denial", () => {
  test("denies non-admin developer user access to /admin and presents permission boundary", async ({ memberPage }) => {
    await memberPage.goto("/admin");

    // Must display PermissionDeniedState
    await expect(memberPage.getByRole("alert")).toBeVisible();
    await expect(memberPage.getByRole("heading", { name: /Access Restricted/i })).toBeVisible();
    await expect(memberPage.getByRole("button", { name: /Return to Workspace/i })).toBeVisible();

    // Clicking Return to Workspace navigates back safely
    await memberPage.getByRole("button", { name: /Return to Workspace/i }).click();
    await expect(memberPage).toHaveURL(/.*workspace/);
  });
});
