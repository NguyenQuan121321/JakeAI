/**
 * Providers, Models & BYOK Keystore Vitest Test Suite
 *
 * Mandated Verification Criteria:
 * 1. Provider unavailable (503 / health degraded status badge)
 * 2. Model unavailable & cascade selection in ModelSelector
 * 3. BYOK validation states (valid, invalid, 429 rate limited, 503 provider unavailable, network error)
 * 4. BYOK rotation (dialog, candidate key, input wipe, updated masked hint)
 * 5. BYOK revoke (suspends key, updates status badge)
 * 6. BYOK delete (removes key from vault)
 * 7. Security audit: zero raw key retention in localStorage, sessionStorage, and console logs
 */

import { describe, it, expect, beforeEach, afterEach, vi } from "vitest";
import { render, screen, waitFor, fireEvent } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { MemoryRouter } from "react-router-dom";
import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { http, HttpResponse } from "msw";
import { server } from "@/mocks/server";
import { resetMockByokKeys } from "@/mocks/handlers";
import { AuthProvider } from "@/context/auth-context";
import { ThemeProvider } from "@/context/theme-context";
import { tokenStore } from "@/api/auth/token-store";
import ProvidersPage from "@/pages/providers";
import { ModelSelector } from "@/components/providers/model-selector";
import { ByokValidationBadge } from "@/components/providers/byok-validation-badge";
import { ByokKeyDialog } from "@/components/providers/byok-key-dialog";
import { ByokVaultTable } from "@/components/providers/byok-vault-table";

function renderWithProviders(ui: React.ReactElement) {
  const queryClient = new QueryClient({
    defaultOptions: {
      queries: { retry: false },
      mutations: { retry: false },
    },
  });

  return render(
    <QueryClientProvider client={queryClient}>
      <ThemeProvider>
        <AuthProvider initialAuthenticated={true}>
          <MemoryRouter>{ui}</MemoryRouter>
        </AuthProvider>
      </ThemeProvider>
    </QueryClientProvider>
  );
}

describe("FE-05 Providers, Models & BYOK Console Suite", () => {
  beforeEach(() => {
    localStorage.clear();
    sessionStorage.clear();
    resetMockByokKeys();
    tokenStore.setTokens({ accessToken: "mock-valid-token" });
    tokenStore.setActiveTenantId("tenant_jakeai_core");
  });

  afterEach(() => {
    server.resetHandlers();
    resetMockByokKeys();
    localStorage.clear();
    sessionStorage.clear();
    vi.restoreAllMocks();
  });

  // Criterion 1: Provider Unavailable / Health Degradation
  it("displays Unavailable status badge when provider reports health degradation or 503", async () => {
    const mockModels = () =>
      HttpResponse.json({
        data: [
          { id: "gpt-4o", object: "model", created: 1700000000, owned_by: "openai" },
          { id: "claude-3-5-sonnet", object: "model", created: 1700000000, owned_by: "anthropic" },
        ],
      });

    const mockKeys = () =>
      HttpResponse.json({
        tenant_id: "tenant_jakeai_core",
        keys: [
          {
            provider: "openai",
            masked_key: "sk-...9a8b",
            configured: true,
            status: "active",
            validation_status: "valid",
          },
          {
            provider: "anthropic",
            masked_key: "sk-...3c4d",
            configured: true,
            status: "active",
            validation_status: "provider_unavailable",
          },
        ],
      });

    server.use(
      http.get("*/api/v1/gateway/models", mockModels),
      http.get("/api/v1/gateway/models", mockModels),
      http.get("*/api/v1/byok/keys", mockKeys),
      http.get("/api/v1/byok/keys", mockKeys)
    );

    renderWithProviders(<ProvidersPage />);

    // Wait for header
    await waitFor(() => {
      expect(screen.getByText("Providers, Models & BYOK Console")).toBeInTheDocument();
    });

    // Check if Connected Providers & Health is in document
    await waitFor(() => {
      expect(screen.getByText("Connected Providers & Health")).toBeInTheDocument();
    });

    // Wait for cards and assert health status indicators
    await waitFor(() => {
      const heading = screen.getByText("Connected Providers & Health");
      const parent = heading.closest(".space-y-4");
      expect(parent?.innerHTML).toContain("OpenAI");
      expect(parent?.innerHTML).toContain("Operational");
      expect(parent?.innerHTML).toContain("Unavailable");
      expect(parent?.innerHTML).toContain("No Models");
    });
  });

  // Criterion 2: Model Selector Cascade & Unavailable Model Handling
  it("cascades provider selection to models and disables unavailable models", async () => {
    const onSelect = vi.fn();

    const mockModels = () =>
      HttpResponse.json({
        data: [
          { id: "gpt-4o", object: "model", created: 1700000000, owned_by: "openai" },
          { id: "gpt-4o-mini", object: "model", created: 1700000000, owned_by: "openai" },
          { id: "claude-3-5-sonnet", object: "model", created: 1700000000, owned_by: "anthropic" },
        ],
      });

    server.use(
      http.get("*/api/v1/gateway/models", mockModels),
      http.get("/api/v1/gateway/models", mockModels)
    );

    renderWithProviders(
      <ModelSelector
        selectedProvider="openai"
        selectedModel="gpt-4o"
        onSelect={onSelect}
      />
    );

    // Verify provider dropdown options and model select populated
    await waitFor(() => {
      const modelSelect = screen.getByLabelText("Select Model") as HTMLSelectElement;
      expect(modelSelect.value).toBe("gpt-4o");
    });

    const modelSelect = screen.getByLabelText("Select Model") as HTMLSelectElement;

    const options = Array.from(modelSelect.querySelectorAll("option")).map((o) => o.value);
    expect(options).toContain("gpt-4o");
    expect(options).toContain("gpt-4o-mini");
    expect(options).not.toContain("claude-3-5-sonnet");

    // Change provider to Anthropic
    const providerSelect = screen.getByLabelText("Select AI Provider");
    fireEvent.change(providerSelect, { target: { value: "anthropic" } });

    expect(onSelect).toHaveBeenCalledWith("anthropic", "claude-3-5-sonnet");
  });

  // Criterion 3: BYOK Validation Badges across distinct states
  it("renders distinct UX badges for valid, invalid, 429 rate-limited, and 503 unavailable states", () => {
    const { rerender } = render(<ByokValidationBadge status="valid" />);
    expect(screen.getByText("Valid")).toBeInTheDocument();

    rerender(<ByokValidationBadge status="invalid" errorMessage="Key revoked" />);
    expect(screen.getByText("Invalid")).toBeInTheDocument();

    rerender(<ByokValidationBadge status="rate_limited" />);
    expect(screen.getByText("Rate Limited")).toBeInTheDocument();

    rerender(<ByokValidationBadge status="provider_unavailable" />);
    expect(screen.getByText("Provider Unavailable")).toBeInTheDocument();

    rerender(<ByokValidationBadge status="network_error" />);
    expect(screen.getByText("Network Error")).toBeInTheDocument();
  });

  // Criterion 4: BYOK Candidate Key Probe in Dialog (Valid, Invalid, 429, 503)
  it("probes candidate key validation and renders precise error status badges", async () => {
    const user = userEvent.setup();

    renderWithProviders(
      <ByokKeyDialog
        open={true}
        onOpenChange={vi.fn()}
        mode="add"
        initialProvider="openai"
      />
    );

    const keyInput = screen.getByPlaceholderText(/Paste secret API key/i);
    const probeBtn = screen.getByRole("button", { name: /Probe Test Key/i });

    // Test 1: Invalid key probe
    await user.type(keyInput, "sk-proj-invalidkey12345");
    await user.click(probeBtn);

    await waitFor(() => {
      expect(screen.getByText("Invalid")).toBeInTheDocument();
      expect(
        screen.getByText(/Authentication failed with upstream provider/i)
      ).toBeInTheDocument();
    });

    // Test 2: Rate limited probe (429)
    await user.clear(keyInput);
    await user.type(keyInput, "sk-proj-rate-limited-key");
    await user.click(probeBtn);

    await waitFor(() => {
      expect(screen.getByText("Rate Limited")).toBeInTheDocument();
    });

    // Test 3: Provider unavailable probe (503)
    await user.clear(keyInput);
    await user.type(keyInput, "sk-proj-unavailable-key");
    await user.click(probeBtn);

    await waitFor(() => {
      expect(screen.getByText("Provider Unavailable")).toBeInTheDocument();
    });

    // Test 4: Valid key probe
    await user.clear(keyInput);
    await user.type(keyInput, "sk-proj-legit-valid-key");
    await user.click(probeBtn);

    await waitFor(() => {
      expect(screen.getByText("Valid")).toBeInTheDocument();
    });
  });

  // Criterion 5: BYOK Key Rotation with Sensitive Input Wipe
  it("executes BYOK key rotation, wipes sensitive state, and updates vault table hint", async () => {
    const user = userEvent.setup();

    renderWithProviders(<ByokVaultTable />);

    // Wait for OpenAI row to render
    await waitFor(() => {
      expect(screen.getByText("sk-...9a8b")).toBeInTheDocument();
    });

    // Click Rotate on OpenAI row
    const rotateButtons = screen.getAllByRole("button", { name: /rotate/i });
    await user.click(rotateButtons[0]);

    // Dialog opens in rotate mode
    await waitFor(() => {
      expect(screen.getByText(/Rotate Key: OpenAI/i)).toBeInTheDocument();
    });

    const keyInput = screen.getByPlaceholderText(/Paste secret API key/i) as HTMLInputElement;
    await user.type(keyInput, "sk-proj-superrotatedkey8888");
    expect(keyInput.value).toBe("sk-proj-superrotatedkey8888");

    // Submit rotation
    const submitBtn = screen.getByRole("button", { name: /Confirm Rotation/i });
    await user.click(submitBtn);

    // Dialog closes and table shows updated masked key sk-...8888
    await waitFor(() => {
      expect(screen.getByText("sk-...8888")).toBeInTheDocument();
    });

    // Sensitive key input unmounted / removed from DOM
    expect(screen.queryByPlaceholderText(/Paste secret API key/i)).not.toBeInTheDocument();
  });

  // Criterion 6: BYOK Key Revocation
  it("suspends active key and updates vault status badge to Revoked", async () => {
    const user = userEvent.setup();

    renderWithProviders(<ByokVaultTable />);

    await waitFor(() => {
      expect(screen.getByText("sk-...9a8b")).toBeInTheDocument();
    });

    // Click Revoke on OpenAI row
    const revokeBtn = screen.getAllByRole("button", { name: /revoke/i })[0];
    await user.click(revokeBtn);

    // Confirmation dialog opens
    await waitFor(() => {
      expect(screen.getByText("Revoke Provider Key?")).toBeInTheDocument();
    });

    // Confirm revoke
    const confirmBtn = screen.getByRole("button", { name: /confirm revoke/i });
    await user.click(confirmBtn);

    // Key status badge transitions to Revoked
    await waitFor(() => {
      expect(screen.getByText("Revoked")).toBeInTheDocument();
    });
  });

  // Criterion 7: BYOK Key Deletion
  it("permanently purges key from tenant vault", async () => {
    const user = userEvent.setup();

    renderWithProviders(<ByokVaultTable />);

    await waitFor(() => {
      expect(screen.getByText("sk-...3c4d")).toBeInTheDocument();
    });

    // Click Delete on Anthropic row (second row with configured key)
    const deleteButtons = screen.getAllByRole("button", { name: /delete/i });
    await user.click(deleteButtons[1]);

    // Confirmation dialog opens
    await waitFor(() => {
      expect(screen.getByText("Permanently Delete Key?")).toBeInTheDocument();
    });

    // Confirm delete
    const confirmBtn = screen.getByRole("button", { name: /confirm delete/i });
    await user.click(confirmBtn);

    // Anthropic key is removed from vault
    await waitFor(() => {
      expect(screen.queryByText("sk-...3c4d")).not.toBeInTheDocument();
    });
  });

  // Criterion 8: Security Audit — Zero Raw Key Retention
  it("enforces zero raw key retention in localStorage, sessionStorage, and console logs", async () => {
    const user = userEvent.setup();

    // Setup spies for console
    const logSpy = vi.spyOn(console, "log");
    const warnSpy = vi.spyOn(console, "warn");
    const errorSpy = vi.spyOn(console, "error");

    const SECRET_KEY = "sk-proj-ultra-secret-test-key-never-leak-9999";

    renderWithProviders(
      <ByokKeyDialog
        open={true}
        onOpenChange={vi.fn()}
        mode="add"
        initialProvider="openai"
      />
    );

    const keyInput = screen.getByPlaceholderText(/Paste secret API key/i);
    await user.type(keyInput, SECRET_KEY);

    // Probe the key
    const probeBtn = screen.getByRole("button", { name: /Probe Test Key/i });
    await user.click(probeBtn);

    await waitFor(() => {
      expect(screen.getByText("Valid")).toBeInTheDocument();
    });

    // Save key
    const saveBtn = screen.getByRole("button", { name: /Encrypt & Store Key/i });
    await user.click(saveBtn);

    // Verify localStorage has zero traces of SECRET_KEY
    for (let i = 0; i < localStorage.length; i++) {
      const key = localStorage.key(i) || "";
      const val = localStorage.getItem(key) || "";
      expect(key).not.toContain(SECRET_KEY);
      expect(val).not.toContain(SECRET_KEY);
    }

    // Verify sessionStorage has zero traces of SECRET_KEY
    for (let i = 0; i < sessionStorage.length; i++) {
      const key = sessionStorage.key(i) || "";
      const val = sessionStorage.getItem(key) || "";
      expect(key).not.toContain(SECRET_KEY);
      expect(val).not.toContain(SECRET_KEY);
    }

    // Verify console calls did not print the raw key
    const allConsoleCalls = [
      ...logSpy.mock.calls,
      ...warnSpy.mock.calls,
      ...errorSpy.mock.calls,
    ].flat();

    for (const call of allConsoleCalls) {
      const str = typeof call === "string" ? call : JSON.stringify(call);
      expect(str).not.toContain(SECRET_KEY);
    }
  });
});
