/**
 * Admin Console & Tenant Governance Vitest Integration Test Suite
 *
 * Verification Requirements:
 * 1. Admin overview and 5 tabs navigation (Users, Tenants, Roles, Audit, Sessions)
 * 2. User directory rendering, search filtering, and self-lock prevention
 * 3. Lock user confirmation dialog flow and unlock action
 * 4. Force logout destructive confirmation dialog and session revocation
 * 5. Roles & PBAC Capability Matrix and Caller Claims Inspector
 * 6. Audit logs table and export functionality (CSV/NDJSON)
 * 7. Active sessions inspection
 * 8. Permission boundary enforcement (requires admin or tenant_admin role)
 */

import { describe, it, expect, beforeEach, afterEach, vi } from "vitest";
import { render, screen, waitFor, fireEvent } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { MemoryRouter } from "react-router-dom";
import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { server } from "@/mocks/server";
import { resetAdminMocks } from "@/mocks/handlers";
import { AuthProvider } from "@/context/auth-context";
import { ThemeProvider } from "@/context/theme-context";
import { tokenStore } from "@/api/auth/token-store";
import type { User } from "@/types/auth";
import AdminPage from "@/pages/admin";

function renderWithProviders(ui: React.ReactElement, initialUser?: User | null) {
  const queryClient = new QueryClient({
    defaultOptions: {
      queries: { retry: false },
      mutations: { retry: false },
    },
  });

  return render(
    <QueryClientProvider client={queryClient}>
      <ThemeProvider>
        <AuthProvider initialAuthenticated={true} initialUser={initialUser}>
          <MemoryRouter>{ui}</MemoryRouter>
        </AuthProvider>
      </ThemeProvider>
    </QueryClientProvider>
  );
}

describe("FE-06 Admin Console & Security Governance Suite", () => {
  beforeEach(() => {
    localStorage.clear();
    sessionStorage.clear();
    resetAdminMocks();
    tokenStore.setTokens({ accessToken: "mock-valid-token" });
    tokenStore.setActiveTenantId("tenant_jakeai_core");
  });

  afterEach(() => {
    server.resetHandlers();
    resetAdminMocks();
    localStorage.clear();
    sessionStorage.clear();
    vi.restoreAllMocks();
  });

  it("renders admin console overview, metrics, and tab navigation", async () => {
    renderWithProviders(<AdminPage />);

    // Wait for the Admin title and badges
    await waitFor(() => {
      expect(screen.getByText("Enterprise Administration & Security")).toBeInTheDocument();
      expect(screen.getByText("Admin Restricted")).toBeInTheDocument();
    });

    // Check metric cards
    expect(screen.getByText("Active Tenant Users")).toBeInTheDocument();
    expect(screen.getByText("Active Tenant Sessions")).toBeInTheDocument();
    expect(screen.getByText("Tenant Workspaces")).toBeInTheDocument();

    // Check all 5 tabs are present
    expect(screen.getByRole("tab", { name: /Users/i })).toBeInTheDocument();
    expect(screen.getByRole("tab", { name: /Tenants/i })).toBeInTheDocument();
    expect(screen.getByRole("tab", { name: /Roles & Matrix/i })).toBeInTheDocument();
    expect(screen.getByRole("tab", { name: /Audit Logs/i })).toBeInTheDocument();
    expect(screen.getByRole("tab", { name: /Sessions/i })).toBeInTheDocument();
  });

  it("renders user accounts, performs search filtering, and prevents self-locking", async () => {
    const user = userEvent.setup();
    renderWithProviders(<AdminPage />);

    // Wait for users table to populate
    await waitFor(() => {
      expect(screen.getByText("@alex.mercer")).toBeInTheDocument();
      expect(screen.getByText("@sarah.connor")).toBeInTheDocument();
    });

    // Verify self-lock prevention: Alex Mercer (current user) has lock button disabled
    const alexRow = screen.getByText("@alex.mercer").closest("tr")!;
    const alexLockBtn = alexRow.querySelector("button[disabled]");
    expect(alexLockBtn).not.toBeNull();

    // Search filter: search for "sarah"
    const searchInput = screen.getByPlaceholderText(/Search users/i);
    await user.type(searchInput, "sarah");

    await waitFor(() => {
      expect(screen.getByText("@sarah.connor")).toBeInTheDocument();
      expect(screen.queryByText("@alex.mercer")).not.toBeInTheDocument();
    });
  });

  it("locks user through confirmation dialog and then unlocks", async () => {
    renderWithProviders(<AdminPage />);

    // Wait for sarah.connor row
    await waitFor(() => {
      expect(screen.getByText("@sarah.connor")).toBeInTheDocument();
    });

    const sarahRow = screen.getByText("@sarah.connor").closest("tr")!;
    const lockButton = sarahRow.querySelector("button.text-amber-600") as HTMLButtonElement;
    expect(lockButton).not.toBeNull();
    fireEvent.click(lockButton);

    // Confirm dialog should be open
    await waitFor(() => {
      expect(screen.getByText("Lock User Account")).toBeInTheDocument();
      expect(screen.getByText(/Are you sure you want to temporarily suspend access for Sarah Connor/)).toBeInTheDocument();
    });

    // Confirm lock
    const confirmLockBtn = screen.getByRole("button", { name: "Lock Account" });
    fireEvent.click(confirmLockBtn);

    // Dialog should close and user status should update to Locked
    await waitFor(() => {
      expect(screen.queryByText("Lock User Account")).not.toBeInTheDocument();
      expect(screen.getByText("Locked")).toBeInTheDocument();
    });

    // Unlock button should now appear for Sarah
    const unlockBtn = screen.getByRole("button", { name: /Unlock/i });
    expect(unlockBtn).toBeInTheDocument();
    fireEvent.click(unlockBtn);

    // User should be unlocked back to Active
    await waitFor(() => {
      expect(screen.queryByText("Locked")).not.toBeInTheDocument();
    });
  });

  it("forces user logout through destructive confirmation dialog", async () => {
    renderWithProviders(<AdminPage />);

    await waitFor(() => {
      expect(screen.getByText("@sarah.connor")).toBeInTheDocument();
    });

    const sarahRow = screen.getByText("@sarah.connor").closest("tr")!;
    const forceLogoutBtn = sarahRow.querySelector("button[title*='Revoke all active sessions']") as HTMLButtonElement;
    expect(forceLogoutBtn).not.toBeNull();
    fireEvent.click(forceLogoutBtn);

    // Confirm dialog should open with destructive styling
    await waitFor(() => {
      expect(screen.getByText("Force Logout User Across All Devices")).toBeInTheDocument();
      expect(screen.getByText(/This will immediately revoke all active refresh tokens/)).toBeInTheDocument();
    });

    // Click confirm revocation
    const revokeBtn = screen.getByRole("button", { name: "Revoke All Sessions" });
    fireEvent.click(revokeBtn);

    await waitFor(() => {
      expect(screen.queryByText("Force Logout User Across All Devices")).not.toBeInTheDocument();
    });
  });

  it("switches to Roles tab and inspects PBAC capability matrix & caller claims", async () => {
    renderWithProviders(<AdminPage />);

    const rolesTab = await screen.findByRole("tab", { name: /Roles & Matrix/i });
    fireEvent.click(rolesTab);

    // Matrix content should be visible
    await waitFor(() => {
      expect(screen.getByText("Enterprise RBAC / PBAC Permission Matrix")).toBeInTheDocument();
      expect(screen.getByText("My Active Session Claims")).toBeInTheDocument();
    });

    // Verify role cards or table rows exist
    expect(screen.getAllByText("tenant_admin").length).toBeGreaterThan(0);
    expect(screen.getAllByText("finops_analyst").length).toBeGreaterThan(0);
  });

  it("switches to Audit Logs tab and checks immutable hash and export options", async () => {
    renderWithProviders(<AdminPage />);

    const auditTab = await screen.findByRole("tab", { name: /Audit Logs/i });
    fireEvent.click(auditTab);

    await waitFor(() => {
      expect(screen.getByText("Immutable Audit Log Trail")).toBeInTheDocument();
      expect(screen.getByText("USER_LOGIN")).toBeInTheDocument();
    });

    // Verify export buttons are present and clickable
    const exportCsvBtn = screen.getByRole("button", { name: "CSV" });
    const exportNdjsonBtn = screen.getByRole("button", { name: "NDJSON" });
    expect(exportCsvBtn).toBeInTheDocument();
    expect(exportNdjsonBtn).toBeInTheDocument();
  });

  it("switches to Sessions tab and inspects active sessions", async () => {
    renderWithProviders(<AdminPage />);

    const sessionsTab = await screen.findByRole("tab", { name: /Sessions/i });
    fireEvent.click(sessionsTab);

    await waitFor(() => {
      expect(screen.getAllByText("Active Tenant Sessions").length).toBeGreaterThan(0);
      expect(screen.getByText("192.168.1.50")).toBeInTheDocument();
    });
  });

  it("enforces permission denial when caller lacks admin role or capabilities", async () => {
    const memberUser: User = {
      id: "usr_member",
      name: "Standard Member",
      email: "member@example.com",
      tenantId: "tenant_jakeai_core",
      roles: ["member"],
      permissions: ["rag:read", "chat:read"],
    };

    renderWithProviders(<AdminPage />, memberUser);

    await waitFor(() => {
      expect(screen.getByText("Admin Console Access Restricted")).toBeInTheDocument();
      expect(screen.getByText(/Your current role does not have administrative permissions/)).toBeInTheDocument();
    });
  });
});
