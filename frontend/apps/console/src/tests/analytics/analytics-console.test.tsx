/**
 * Analytics & Operational Telemetry Vitest Integration Test Suite
 *
 * Verification Requirements:
 * 1. Operational KPI rendering from authoritative backend dashboard (requests, tokens, cost savings, TTFT)
 * 2. Model usage distribution chart and share statistics
 * 3. Token efficiency breakdown (cache avoidance, provider KV cache)
 * 4. JakeAI-Agent platform runtime telemetry and approval counters
 * 5. DevOps PR audit telemetry
 * 6. Support correlation ID display upon failure
 * 7. Permission boundary enforcement (analytics:read)
 */

import { describe, it, expect, beforeEach, afterEach, vi } from "vitest";
import { render, screen, waitFor } from "@testing-library/react";
import { MemoryRouter } from "react-router-dom";
import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { http, HttpResponse } from "msw";
import { server } from "@/mocks/server";
import { AuthProvider } from "@/context/auth-context";
import { ThemeProvider } from "@/context/theme-context";
import { tokenStore } from "@/api/auth/token-store";
import type { User } from "@/types/auth";
import AnalyticsPage from "@/pages/analytics";

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

describe("FE-06 Analytics & Operational Telemetry Suite", () => {
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

  it("renders authoritative operational KPIs from backend dashboard", async () => {
    renderWithProviders(<AnalyticsPage />);

    // Wait for the Analytics header
    await waitFor(() => {
      expect(screen.getByText("Platform Analytics & Telemetry")).toBeInTheDocument();
      expect(screen.getByText(/Telemetry Online/)).toBeInTheDocument();
    });

    // Verify top 4 real KPI cards
    await waitFor(() => {
      expect(screen.getByText("48.20K")).toBeInTheDocument(); // Tokens Processed
      expect(screen.getByText("$14.50")).toBeInTheDocument(); // Cost Savings
      expect(screen.getByText("220ms")).toBeInTheDocument(); // Avg TTFT
    });

    // Check TTFT compliance badge
    expect(screen.getByText(/SLO < 500ms/)).toBeInTheDocument();
  });

  it("renders model usage distribution and token efficiency telemetry", async () => {
    renderWithProviders(<AnalyticsPage />);

    await waitFor(() => {
      expect(screen.getByText("Inference Distribution by Model")).toBeInTheDocument();
      expect(screen.getByText("Token Efficiency & Caching Telemetry")).toBeInTheDocument();
    });

    // Verify model breakdown entries
    expect(screen.getByText("gpt-4o")).toBeInTheDocument();
    expect(screen.getByText("claude-3-5-sonnet")).toBeInTheDocument();

    // Verify provider KV cache metrics
    expect(screen.getByText("Provider KV Cache Hit Rate")).toBeInTheDocument();
    expect(screen.getByText("KV Cache Cost Avoidance")).toBeInTheDocument();
  });

  it("displays JakeAI-Agent runtime platform telemetry and PR audit activity", async () => {
    renderWithProviders(<AnalyticsPage />);

    await waitFor(() => {
      expect(screen.getByText("JakeAI-Agent Platform Telemetry")).toBeInTheDocument();
      expect(screen.getByText("DevOps & Codebase Audits")).toBeInTheDocument();
    });

    // Check agent telemetry labels
    expect(screen.getByText("Active Runs")).toBeInTheDocument();
    expect(screen.getByText("Completed Runs")).toBeInTheDocument();
    expect(screen.getByText("Waiting Approvals")).toBeInTheDocument();
    expect(screen.getByText("Steps Executed")).toBeInTheDocument();

    // Check PR audit count
    expect(screen.getByText("Pull Requests Audited")).toBeInTheDocument();
    expect(screen.getAllByText("8").length).toBeGreaterThan(0);
  });

  it("surfaces support correlation ID upon API failure", async () => {
    server.use(
      http.get("*/api/v1/analytics/dashboard", () => {
        return new HttpResponse(
          JSON.stringify({ detail: "Gateway telemetry aggregator timeout" }),
          {
            status: 504,
            headers: {
              "Content-Type": "application/json",
              "X-Correlation-ID": "corr-telemetry-err-404",
            },
          }
        );
      }),
      http.get("/api/v1/analytics/dashboard", () => {
        return new HttpResponse(
          JSON.stringify({ detail: "Gateway telemetry aggregator timeout" }),
          {
            status: 504,
            headers: {
              "Content-Type": "application/json",
              "X-Correlation-ID": "corr-telemetry-err-404",
            },
          }
        );
      })
    );

    renderWithProviders(<AnalyticsPage />);

    await waitFor(() => {
      expect(screen.getByText("corr-telemetry-err-404")).toBeInTheDocument();
      expect(screen.getByText("Failed to Load Analytics")).toBeInTheDocument();
    });
  });

  it("enforces permission denial when caller lacks analytics:read permission", async () => {
    const restrictedUser: User = {
      id: "usr_restricted",
      name: "Restricted Viewer",
      email: "viewer@example.com",
      tenantId: "tenant_jakeai_core",
      roles: ["viewer"],
      permissions: ["rag:read"],
    };

    renderWithProviders(<AnalyticsPage />, restrictedUser);

    await waitFor(() => {
      expect(screen.getByText("Analytics Access Restricted")).toBeInTheDocument();
      expect(screen.getByText(/You do not possess the required analytics:read/)).toBeInTheDocument();
    });
  });
});
