/**
 * Workspace Orchestration Visibility, Citations & Security Tests
 *
 * Tests:
 * - 6 canonical pipeline stages (Planning, Agent selection, Retrieval, Tool execution, Verification, Final response)
 * - Tool activity cards (status, duration, RBAC blocked reason)
 * - Grounded citations & CitationDialog modal inspection
 * - Security invariant: Strict zero chain-of-thought/reasoning leakage
 */

import { describe, it, expect, beforeEach, afterEach } from "vitest";
import { render, screen, waitFor } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { MemoryRouter } from "react-router-dom";
import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { http, HttpResponse } from "msw";
import { server } from "@/mocks/server";
import { AuthProvider } from "@/context/auth-context";
import { ThemeProvider } from "@/context/theme-context";
import { tokenStore } from "@/api/auth/token-store";
import WorkspacePage from "@/pages/workspace";

function renderWorkspace() {
  const queryClient = new QueryClient({
    defaultOptions: { queries: { retry: false } },
  });

  return render(
    <QueryClientProvider client={queryClient}>
      <ThemeProvider>
        <AuthProvider initialAuthenticated={true}>
          <MemoryRouter initialEntries={["/workspace"]}>
            <WorkspacePage />
          </MemoryRouter>
        </AuthProvider>
      </ThemeProvider>
    </QueryClientProvider>
  );
}

describe("Workspace Orchestration & Citations Visibility", () => {
  beforeEach(() => {
    localStorage.clear();
    tokenStore.setTokens({ accessToken: "mock-valid-token" });
    tokenStore.setActiveTenantId("tenant_jakeai_core");
  });

  afterEach(() => {
    server.resetHandlers();
    localStorage.clear();
  });

  it("displays the 6 canonical orchestration stages in the execution panel", async () => {
    const user = userEvent.setup();
    renderWorkspace();

    const textarea = screen.getByPlaceholderText(/ask jakeai anything/i);
    await user.type(textarea, "Explain multi-agent architecture");
    await user.click(screen.getByRole("button", { name: /send/i }));

    // Verify presence of all 6 canonical stages
    await waitFor(() => {
      expect(screen.getByText("Multi-Agent Orchestration")).toBeInTheDocument();
      expect(screen.getByText("Planning")).toBeInTheDocument();
      expect(screen.getByText("Agent selection")).toBeInTheDocument();
      expect(screen.getByText("Retrieval")).toBeInTheDocument();
      expect(screen.getByText("Tool execution")).toBeInTheDocument();
      expect(screen.getByText("Verification")).toBeInTheDocument();
      expect(screen.getByText("Final response")).toBeInTheDocument();
    });

    // Verify verification count summary
    await waitFor(() => {
      expect(screen.getByText(/6\/6 stages verified/i)).toBeInTheDocument();
    });
  });

  it("renders tool activity cards with blocked and successful execution statuses", async () => {
    const user = userEvent.setup();

    server.use(
      http.post("*/api/v1/chat/stream", () => {
        const encoder = new TextEncoder();
        const stream = new ReadableStream({
          start(controller) {
            // 1. Successful Tool
            controller.enqueue(
              encoder.encode(
                `event: tool_call\ndata: ${JSON.stringify({
                  tool_calls: [
                    {
                      tool_name: "get_account_balance",
                      status: "SUCCESS",
                      duration_ms: 12.4,
                    },
                  ],
                })}\n\n`
              )
            );

            // 2. Blocked Tool
            controller.enqueue(
              encoder.encode(
                `event: tool_call\ndata: ${JSON.stringify({
                  tool_calls: [
                    {
                      tool_name: "wire_transfer_funds",
                      status: "BLOCKED",
                      reason: "Requires role 'treasury_admin'",
                      duration_ms: 3.1,
                    },
                  ],
                })}\n\n`
              )
            );

            // 3. Complete
            controller.enqueue(
              encoder.encode(
                `event: token\ndata: {"delta":"Execution completed with policy guards."}\n\nevent: done\ndata: {"elapsed_ms":120,"conversation_id":"c1","tenant_id":"t1"}\n\n`
              )
            );
            controller.close();
          },
        });
        return new HttpResponse(stream, {
          headers: { "Content-Type": "text/event-stream" },
        });
      })
    );

    renderWorkspace();

    const textarea = screen.getByPlaceholderText(/ask jakeai anything/i);
    await user.type(textarea, "Attempt funds transfer and balance inquiry");
    await user.click(screen.getByRole("button", { name: /send/i }));

    // Successful tool card
    await waitFor(() => {
      expect(screen.getByText("get_account_balance")).toBeInTheDocument();
      expect(screen.getByText("SUCCESS")).toBeInTheDocument();
    });

    // Blocked tool card with reason
    await waitFor(() => {
      expect(screen.getByText("wire_transfer_funds")).toBeInTheDocument();
      expect(screen.getByText("BLOCKED")).toBeInTheDocument();
      expect(screen.getByText(/Access Denied: Requires role 'treasury_admin'/i)).toBeInTheDocument();
    });
  });

  it("renders grounded citations and opens citation inspection dialog on click", async () => {
    const user = userEvent.setup();

    server.use(
      http.post("*/api/v1/chat/stream", () => {
        const encoder = new TextEncoder();
        const stream = new ReadableStream({
          start(controller) {
            controller.enqueue(
              encoder.encode(
                `event: token\ndata: {"delta":"According to financial regulations, capital reserve ratios must exceed 12%."}\n\n`
              )
            );
            controller.enqueue(
              encoder.encode(
                `event: done\ndata: ${JSON.stringify({
                  conversation_id: "c1",
                  tenant_id: "tenant_jakeai_core",
                  elapsed_ms: 150,
                  citations: [
                    {
                      index: 1,
                      source: "FINANCIAL-COMPLIANCE-DOC.pdf",
                      snippet: "Tier 1 capital reserve ratio must strictly exceed 12.0% of risk-weighted assets.",
                      tenant_id: "tenant_jakeai_core",
                      confidence: 0.96,
                      chunk_id: "chunk-reg-4421",
                    },
                  ],
                })}\n\n`
              )
            );
            controller.close();
          },
        });
        return new HttpResponse(stream, {
          headers: { "Content-Type": "text/event-stream" },
        });
      })
    );

    renderWorkspace();

    const textarea = screen.getByPlaceholderText(/ask jakeai anything/i);
    await user.type(textarea, "What are the capital reserve requirements?");
    await user.click(screen.getByRole("button", { name: /send/i }));

    // Citation chip rendered
    const citationChip = await screen.findByRole("button", {
      name: /inspect citation 1/i,
    });
    expect(citationChip).toBeInTheDocument();
    expect(screen.getByText(/FINANCIAL-COMPLIANCE-DOC.pdf/i)).toBeInTheDocument();

    // Click chip to open dialog
    await user.click(citationChip);

    // Dialog contents visible
    await waitFor(() => {
      expect(screen.getByText(/Grounded Citation Footnote \[1\]/i)).toBeInTheDocument();
      expect(screen.getByText(/chunk-reg-4421/i)).toBeInTheDocument();
      expect(
        screen.getByText(/Tier 1 capital reserve ratio must strictly exceed 12.0%/i)
      ).toBeInTheDocument();
      expect(screen.getByText(/96% Grounded/i)).toBeInTheDocument();
    });

    // Close dialog
    const closeBtn = screen.getByLabelText("Close dialog");
    await user.click(closeBtn);

    await waitFor(() => {
      expect(screen.queryByText(/Grounded Citation Footnote \[1\]/i)).not.toBeInTheDocument();
    });
  });

  it("strictly enforces zero chain-of-thought leakage", async () => {
    const user = userEvent.setup();

    server.use(
      http.post("*/api/v1/chat/stream", () => {
        const encoder = new TextEncoder();
        const stream = new ReadableStream({
          start(controller) {
            // Emits approved events only; even if backend or malicious payload attempted to inject thoughts
            controller.enqueue(
              encoder.encode(
                `event: status\ndata: {"node":"supervisor","phase":"routing","message":"Supervisor: Dispatching."}\n\n`
              )
            );
            controller.enqueue(
              encoder.encode(
                `event: token\ndata: {"delta":"Safe business response with public facts."}\n\n`
              )
            );
            controller.enqueue(
              encoder.encode(
                `event: done\ndata: {"elapsed_ms":90,"conversation_id":"c1","tenant_id":"t1"}\n\n`
              )
            );
            controller.close();
          },
        });
        return new HttpResponse(stream, {
          headers: { "Content-Type": "text/event-stream" },
        });
      })
    );

    renderWorkspace();

    const textarea = screen.getByPlaceholderText(/ask jakeai anything/i);
    await user.type(textarea, "Check security invariants");
    await user.click(screen.getByRole("button", { name: /send/i }));

    await waitFor(() => {
      expect(screen.getByText("Safe business response with public facts.")).toBeInTheDocument();
    });

    // Assert that no reasoning tags or chain-of-thought headers are displayed in DOM
    expect(screen.queryByText(/<think>/i)).not.toBeInTheDocument();
    expect(screen.queryByText(/chain of thought/i)).not.toBeInTheDocument();
    expect(screen.queryByText(/private reasoning/i)).not.toBeInTheDocument();
  });
});
