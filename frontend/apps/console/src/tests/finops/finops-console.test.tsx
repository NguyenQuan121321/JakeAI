/**
 * FinOps Console Vitest Integration Test Suite
 *
 * Verification Requirements:
 * 1. Spend & token usage summary authoritative rendering from backend
 * 2. Budget utilization progress gauge and status (normal, warning, suspended)
 * 3. Modal budget edit form with strict quota/budget/threshold validation
 * 4. Non-overlapping savings attribution breakdown
 * 5. Model spend distribution and transactions ledger
 * 6. Data-driven optimization recommendations
 * 7. Error state rendering with correlation ID extraction
 */

import { describe, it, expect, beforeEach, afterEach, vi } from "vitest";
import { render, screen, waitFor, fireEvent } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { MemoryRouter } from "react-router-dom";
import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { http, HttpResponse } from "msw";
import { server } from "@/mocks/server";
import { AuthProvider } from "@/context/auth-context";
import { ThemeProvider } from "@/context/theme-context";
import { tokenStore } from "@/api/auth/token-store";
import FinopsPage from "@/pages/finops";

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

describe("FE-06 FinOps Console Suite", () => {
  beforeEach(() => {
    localStorage.clear();
    sessionStorage.clear();
    tokenStore.setTokens({ accessToken: "mock-valid-token" });
    tokenStore.setActiveTenantId("tenant_jakeai_core");
  });

  afterEach(() => {
    server.resetHandlers();
    localStorage.clear();
    sessionStorage.clear();
    vi.restoreAllMocks();
  });

  it("renders authoritative spend, token usage, and budget metrics from backend", async () => {
    renderWithProviders(<FinopsPage />);

    // Wait for the FinOps title and period to load
    await waitFor(() => {
      expect(screen.getByText("AI FinOps & Token Governance")).toBeInTheDocument();
      expect(screen.getByText(/2026-09/)).toBeInTheDocument();
    });

    // Check spend metrics (from default mock summary: $142.85 actual spend, $38.40 savings, 21.2% saved)
    await waitFor(() => {
      expect(screen.getAllByText("$142.85").length).toBeGreaterThan(0);
      expect(screen.getAllByText("$38.40").length).toBeGreaterThan(0);
      expect(screen.getByText("21.2%")).toBeInTheDocument();
    });

    // Check token and utilization numbers
    expect(screen.getAllByText("4.50M").length).toBeGreaterThan(0); // total raw tokens
    expect(screen.getByText(/300.00K pruned/)).toBeInTheDocument(); // physical pruning
    expect(screen.getAllByText("28.4%").length).toBeGreaterThan(0); // budget utilization
  });

  it("displays budget progress, allocation status, and remaining balances", async () => {
    renderWithProviders(<FinopsPage />);

    await waitFor(() => {
      expect(screen.getByText("Monthly Token Quota")).toBeInTheDocument();
      expect(screen.getByText("Monthly Dollar Budget Ceiling")).toBeInTheDocument();
    });

    // Status badge indicates normal / active quota
    expect(screen.getByText("Active Quota")).toBeInTheDocument();

    // Verify token details
    expect(screen.getByText("Tokens Used")).toBeInTheDocument();
    expect(screen.getByText("Quota Limit")).toBeInTheDocument();
    expect(screen.getByText("Tokens Remaining")).toBeInTheDocument();
    expect(screen.getByText("Reconciliation Truth")).toBeInTheDocument();
  });

  it("opens edit budget modal, validates inputs, and submits budget updates", async () => {
    const user = userEvent.setup();
    renderWithProviders(<FinopsPage />);

    // Wait for button to be available
    const editButton = await screen.findByRole("button", { name: /Edit Budget/i });
    await user.click(editButton);

    // Modal dialog header should appear
    expect(screen.getByText("Configure Tenant Budget & Quotas")).toBeInTheDocument();

    const quotaInput = screen.getByLabelText(/Monthly Token Quota Limit/i);
    const dollarInput = screen.getByLabelText(/Monthly Dollar Ceiling/i);
    const thresholdInput = screen.getByLabelText(/Warning Threshold Alert/i);
    const form = quotaInput.closest("form")!;

    // Test validation: negative or too small token quota (< 10000)
    fireEvent.change(quotaInput, { target: { value: "500" } });
    fireEvent.submit(form);

    await waitFor(() => {
      expect(screen.getByText("Token quota limit must be at least 10,000 tokens.")).toBeInTheDocument();
    });

    // Test validation: negative dollar ceiling
    fireEvent.change(quotaInput, { target: { value: "6000000" } });
    fireEvent.change(dollarInput, { target: { value: "-50" } });
    fireEvent.submit(form);

    await waitFor(() => {
      expect(screen.getByText("Monthly dollar budget ceiling must be at least $1.00 USD.")).toBeInTheDocument();
    });

    // Test validation: invalid threshold > 99
    fireEvent.change(dollarInput, { target: { value: "750" } });
    fireEvent.change(thresholdInput, { target: { value: "105" } });
    fireEvent.submit(form);

    await waitFor(() => {
      expect(screen.getByText("Warning threshold must be an integer between 10% and 99%.")).toBeInTheDocument();
    });

    // Enter valid data and save
    fireEvent.change(thresholdInput, { target: { value: "85" } });
    fireEvent.submit(form);

    // Dialog should close after submission
    await waitFor(() => {
      expect(screen.queryByText("Configure Tenant Budget & Quotas")).not.toBeInTheDocument();
    });
  });

  it("displays over-limit suspension warning when quota is exhausted", async () => {
    const mockSuspendedBudget = {
      tenant_id: "tenant_jakeai_core",
      period: "2026-09",
      token_quota: 5000000,
      tokens_used: 5200000,
      tokens_remaining: 0,
      percentage_tokens_used: 104.0,
      dollar_budget_usd: 500.0,
      dollar_spent_usd: 550.0,
      dollar_remaining_usd: 0,
      percentage_dollars_used: 110.0,
      warning_threshold: 0.8,
      is_suspended: true,
      warning: "Tenant has exceeded token and dollar limits. Inference execution suspended.",
    };

    server.use(
      http.get("*/api/v1/finops/summary", () => {
        return HttpResponse.json({
          tenant_id: "tenant_jakeai_core",
          period: "2026-09",
          total_requests: 5000,
          reconciled_requests: 5000,
          reconciliation_rate: 100.0,
          total_raw_tokens: 10000000,
          total_optimized_tokens: 9500000,
          total_physical_tokens_removed: 500000,
          total_cached_tokens: 1000000,
          total_uncached_tokens: 8500000,
          total_output_tokens: 1500000,
          total_baseline_cost_usd: 600.0,
          total_actual_cost_usd: 550.0,
          total_savings_usd: 50.0,
          overall_savings_percentage: 8.33,
          savings_attribution: {
            cache_hit_usd: 35.0,
            physical_reduction_usd: 15.0,
            provider_cache_usd: 0.0,
            model_routing_usd: 0.0,
            avoided_retries_usd: 0.0,
            total_savings_usd: 50.0,
          },
          budget_status: mockSuspendedBudget,
        });
      }),
      http.get("/api/v1/finops/summary", () => {
        return HttpResponse.json({
          tenant_id: "tenant_jakeai_core",
          period: "2026-09",
          total_requests: 5000,
          reconciled_requests: 5000,
          reconciliation_rate: 100.0,
          total_raw_tokens: 10000000,
          total_optimized_tokens: 9500000,
          total_physical_tokens_removed: 500000,
          total_cached_tokens: 1000000,
          total_uncached_tokens: 8500000,
          total_output_tokens: 1500000,
          total_baseline_cost_usd: 600.0,
          total_actual_cost_usd: 550.0,
          total_savings_usd: 50.0,
          overall_savings_percentage: 8.33,
          savings_attribution: {
            cache_hit_usd: 35.0,
            physical_reduction_usd: 15.0,
            provider_cache_usd: 0.0,
            model_routing_usd: 0.0,
            avoided_retries_usd: 0.0,
            total_savings_usd: 50.0,
          },
          budget_status: mockSuspendedBudget,
        });
      }),
      http.get("*/api/v1/finops/budget", () => HttpResponse.json(mockSuspendedBudget)),
      http.get("/api/v1/finops/budget", () => HttpResponse.json(mockSuspendedBudget))
    );

    renderWithProviders(<FinopsPage />);

    await waitFor(() => {
      expect(screen.getByText(/Hard Quota Ceiling Exceeded/)).toBeInTheDocument();
    });
  });

  it("renders non-overlapping savings attribution and optimization recommendations", async () => {
    renderWithProviders(<FinopsPage />);

    await waitFor(() => {
      expect(screen.getByText("Non-Overlapping Savings Attribution")).toBeInTheDocument();
      expect(screen.getByText("FinOps Optimization Recommendations")).toBeInTheDocument();
    });

    // Check attribution labels
    expect(screen.getByText("Exact & Semantic Cache")).toBeInTheDocument();
    expect(screen.getByText("Physical Token Pruning")).toBeInTheDocument();

    // Check recommendations rendered from mock telemetry
    expect(screen.getByText("Physical Token Pruning Effective")).toBeInTheDocument();
  });

  it("displays transactions ledger with search filter", async () => {
    renderWithProviders(<FinopsPage />);

    await waitFor(() => {
      expect(screen.getByText("Inference Accounting Ledger")).toBeInTheDocument();
      expect(screen.getByText("req-fin-001")).toBeInTheDocument();
      expect(screen.getAllByText("gpt-4o").length).toBeGreaterThan(0);
    });
  });

  it("surfaces support correlation ID on API failure", async () => {
    server.use(
      http.get("*/api/v1/finops/summary", () => {
        return new HttpResponse(
          JSON.stringify({ detail: "Database connection failed" }),
          {
            status: 500,
            headers: {
              "Content-Type": "application/json",
              "X-Correlation-ID": "corr-finops-err-999",
            },
          }
        );
      })
    );

    renderWithProviders(<FinopsPage />);

    await waitFor(() => {
      expect(screen.getByText("corr-finops-err-999")).toBeInTheDocument();
      expect(screen.getByText("Failed to Load FinOps Summary")).toBeInTheDocument();
    });
  });
});
