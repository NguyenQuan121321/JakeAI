/**
 * Security UX & Enterprise Authorization Vitest Test Suite
 *
 * Verification Requirements:
 * 1. ConfirmDialog: warning and destructive modes, challenge text validation, action execution
 * 2. PermissionDeniedState: presentation of required role badges and fallback navigation
 * 3. ErrorState: presentation of support correlation ID and 1-click copy capability
 * 4. Secret Masking: zero credential leakage and defensive formatting of API tokens
 * 5. PBAC/RBAC authorization helpers: wildcard handling, role matching, and permission checks
 */

import { describe, it, expect, vi, beforeEach, afterEach } from "vitest";
import { render, screen, fireEvent, waitFor } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { MemoryRouter } from "react-router-dom";
import { ConfirmDialog } from "@/components/feedback/confirm-dialog";
import { PermissionDeniedState } from "@/components/feedback/permission-denied-state";
import { ErrorState } from "@/components/ui/error-state";
import { maskSecret } from "@/lib/formatters";
import { AuthProvider, useAuth } from "@/context/auth-context";
import { ThemeProvider } from "@/context/theme-context";
import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import type { User } from "@/types/auth";

function TestAuthConsumer({
  requiredRole,
  requiredPermission,
}: {
  requiredRole?: string | string[];
  requiredPermission?: string;
}) {
  const { user, hasRole, can } = useAuth();

  const isRoleAllowed = requiredRole ? hasRole(requiredRole) : true;
  const isPermAllowed = requiredPermission ? can(requiredPermission) : true;

  return (
    <div>
      <span data-testid="user-name">{user?.name}</span>
      {isRoleAllowed && <button data-testid="role-action-btn">Role Protected Action</button>}
      {isPermAllowed && <button data-testid="perm-action-btn">Permission Protected Action</button>}
    </div>
  );
}

function renderWithAuth(
  ui: React.ReactElement,
  initialUser?: User | null
) {
  const queryClient = new QueryClient({
    defaultOptions: { queries: { retry: false } },
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

describe("FE-06 Security UX & Authorization Suite", () => {
  beforeEach(() => {
    localStorage.clear();
    sessionStorage.clear();
    vi.clearAllMocks();
  });

  afterEach(() => {
    localStorage.clear();
    sessionStorage.clear();
    vi.restoreAllMocks();
  });

  describe("ConfirmDialog Interaction & Guardrails", () => {
    it("renders destructive modal and requires exact confirmation challenge text", async () => {
      const user = userEvent.setup();
      const onConfirm = vi.fn();
      const onOpenChange = vi.fn();

      render(
        <ConfirmDialog
          open={true}
          onOpenChange={onOpenChange}
          title="Revoke Enterprise BYOK Key"
          description="This will permanently delete the key and suspend active agent jobs."
          confirmLabel="Revoke Key"
          variant="destructive"
          requireConfirmationText="CONFIRM_DELETE"
          onConfirm={onConfirm}
        />
      );

      expect(screen.getByText("Revoke Enterprise BYOK Key")).toBeInTheDocument();
      expect(screen.getByText(/This will permanently delete the key/)).toBeInTheDocument();

      const confirmBtn = screen.getByRole("button", { name: "Revoke Key" });
      expect(confirmBtn).toBeDisabled();

      // Typing non-matching text should keep it disabled
      const input = screen.getByPlaceholderText(/Type "CONFIRM_DELETE"/i);
      await user.type(input, "WRONG_TEXT");
      expect(confirmBtn).toBeDisabled();

      // Typing exact challenge text enables button
      await user.clear(input);
      await user.type(input, "CONFIRM_DELETE");
      expect(confirmBtn).not.toBeDisabled();

      fireEvent.click(confirmBtn);
      expect(onConfirm).toHaveBeenCalledTimes(1);
    });

    it("renders warning dialog without challenge text and executes onConfirm", () => {
      const onConfirm = vi.fn();
      const onOpenChange = vi.fn();

      render(
        <ConfirmDialog
          open={true}
          onOpenChange={onOpenChange}
          title="Suspend User Account"
          description="Are you sure you want to suspend this user?"
          confirmLabel="Suspend"
          variant="warning"
          onConfirm={onConfirm}
        />
      );

      expect(screen.getByText("Suspend User Account")).toBeInTheDocument();
      const confirmBtn = screen.getByRole("button", { name: "Suspend" });
      expect(confirmBtn).not.toBeDisabled();

      fireEvent.click(confirmBtn);
      expect(onConfirm).toHaveBeenCalledTimes(1);
    });

    it("renders loading state during asynchronous confirmation execution", () => {
      render(
        <ConfirmDialog
          open={true}
          onOpenChange={vi.fn()}
          title="Revoking Credentials"
          description="Contacting key vault..."
          onConfirm={vi.fn()}
          isLoading={true}
        />
      );

      expect(screen.getByText("Processing...")).toBeInTheDocument();
      const confirmBtn = screen.getByRole("button", { name: /Processing.../i });
      expect(confirmBtn).toBeDisabled();
    });
  });

  describe("PermissionDeniedState Presentation", () => {
    it("renders access restricted banner with required role badges and fallback options", () => {
      render(
        <MemoryRouter>
          <PermissionDeniedState
            title="Billing Admin Restricted"
            description="You do not have permission to modify budget limits."
            requiredRoles={["admin", "finops_analyst"]}
          />
        </MemoryRouter>
      );

      expect(screen.getByText("Billing Admin Restricted")).toBeInTheDocument();
      expect(screen.getByText("You do not have permission to modify budget limits.")).toBeInTheDocument();
      expect(screen.getByText("admin")).toBeInTheDocument();
      expect(screen.getByText("finops_analyst")).toBeInTheDocument();
      expect(screen.getByRole("button", { name: /Go Back/i })).toBeInTheDocument();
      expect(screen.getByRole("button", { name: /Return to Workspace/i })).toBeInTheDocument();
    });
  });

  describe("ErrorState Correlation ID Support", () => {
    it("renders correlation ID badge and enables 1-click clipboard copy", async () => {
      // Mock clipboard
      const clipboardMock = vi.fn().mockResolvedValue(undefined);
      Object.defineProperty(navigator, "clipboard", {
        value: {
          writeText: clipboardMock,
        },
        writable: true,
        configurable: true,
      });

      const onRetry = vi.fn();
      render(
        <ErrorState
          title="Rate Limit Exceeded"
          message="Upstream token budget reached."
          correlationId="cid-sec-test-8849"
          onRetry={onRetry}
        />
      );

      expect(screen.getByText("Rate Limit Exceeded")).toBeInTheDocument();
      expect(screen.getByText("Upstream token budget reached.")).toBeInTheDocument();
      expect(screen.getByText(/cid-sec-test-8849/)).toBeInTheDocument();

      // Click copy correlation ID button
      const copyBtn = screen.getByRole("button", { name: /copy correlation id/i });
      fireEvent.click(copyBtn);

      expect(clipboardMock).toHaveBeenCalledWith("cid-sec-test-8849");

      await waitFor(() => {
        expect(copyBtn.querySelector(".lucide-check")).not.toBeNull();
      });
    });
  });

  describe("Zero Secret Leakage & Credential Masking", () => {
    it("safely masks API keys preserving prefixes and hiding high-entropy credentials", () => {
      // Standard OpenAI style key
      const maskedOpenAi = maskSecret("sk-proj-abc123456789xyz0987def");
      expect(maskedOpenAi).toBe("sk-proj-...7def");
      expect(maskedOpenAi).not.toContain("abc123456789xyz0987");

      // GitHub style PAT
      const maskedGh = maskSecret("ghp_9876543210fedcba5678");
      expect(maskedGh).toBe("ghp_...5678");

      // Short secret - fully redacted
      expect(maskSecret("short")).toBe("••••••••••••");
      expect(maskSecret("")).toBe("••••••••••••");
      expect(maskSecret(null)).toBe("••••••••••••");
      expect(maskSecret(undefined)).toBe("••••••••••••");
    });
  });

  describe("Enterprise PBAC & RBAC Authorization Gates", () => {
    it("authorizes platform admin with wildcard * permissions across all gates", () => {
      const adminUser: User = {
        id: "usr_superadmin",
        name: "Super Administrator",
        email: "root@jakeai.internal",
        tenantId: "tenant_jakeai_core",
        roles: ["admin"],
        permissions: ["*"],
      };

      renderWithAuth(
        <TestAuthConsumer
          requiredRole={["admin", "tenant_admin"]}
          requiredPermission="finops:write"
        />,
        adminUser
      );

      expect(screen.getByText("Super Administrator")).toBeInTheDocument();
      expect(screen.getByTestId("role-action-btn")).toBeInTheDocument();
      expect(screen.getByTestId("perm-action-btn")).toBeInTheDocument();
    });

    it("restricts standard member from performing administrative operations", () => {
      const memberUser: User = {
        id: "usr_regular",
        name: "Standard Member",
        email: "member@jakeai.internal",
        tenantId: "tenant_jakeai_core",
        roles: ["member"],
        permissions: ["chat:read", "chat:write"],
      };

      renderWithAuth(
        <TestAuthConsumer
          requiredRole={["admin", "tenant_admin"]}
          requiredPermission="finops:write"
        />,
        memberUser
      );

      expect(screen.getByText("Standard Member")).toBeInTheDocument();
      expect(screen.queryByTestId("role-action-btn")).not.toBeInTheDocument();
      expect(screen.queryByTestId("perm-action-btn")).not.toBeInTheDocument();
    });
  });
});
