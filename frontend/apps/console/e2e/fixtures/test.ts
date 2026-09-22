/**
 * Centralized Playwright Fixture Extension
 *
 * Provides typed, isolated fixtures:
 * - authenticatedPage (default admin)
 * - unauthenticatedPage (explicitly logged out)
 * - adminPage (admin credentials & full access)
 * - memberPage (developer/member credentials for RBAC boundaries)
 */

import { test as base, expect, type Page } from "@playwright/test";
import {
  ADMIN_USER,
  MEMBER_USER,
  installAuthenticatedSession,
  installUnauthenticatedSession,
  installAdminSession,
  installMemberSession,
} from "./auth";
import { setupDefaultMocks } from "./api-mocks";

export interface CustomFixtures {
  authenticatedPage: Page;
  unauthenticatedPage: Page;
  adminPage: Page;
  memberPage: Page;
}

export const test = base.extend<CustomFixtures>({
  authenticatedPage: async ({ page }, use) => {
    await setupDefaultMocks(page, ADMIN_USER);
    await installAuthenticatedSession(page, ADMIN_USER);
    await use(page);
  },
  unauthenticatedPage: async ({ page }, use) => {
    await setupDefaultMocks(page, ADMIN_USER);
    await installUnauthenticatedSession(page);
    await use(page);
  },
  adminPage: async ({ page }, use) => {
    await setupDefaultMocks(page, ADMIN_USER);
    await installAdminSession(page);
    await use(page);
  },
  memberPage: async ({ page }, use) => {
    await setupDefaultMocks(page, MEMBER_USER);
    await installMemberSession(page);
    await use(page);
  },
});

export { expect };
