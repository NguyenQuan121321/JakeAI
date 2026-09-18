/**
 * Workspace Streaming & Error Recovery Integration Tests
 *
 * Tests:
 * - Sending message & receiving SSE streamed tokens
 * - Manual cancellation via Stop button
 * - Stream failure via SSE error event
 * - Retry behavior
 * - HTTP status errors (401, 403, 429, 503)
 * - Navigation / component unmount cleanup during active stream
 */

import { describe, it, expect, beforeEach, afterEach, vi } from "vitest";
import { render, screen, waitFor, act } from "@testing-library/react";
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

describe("Workspace Real-Time Chat & Streaming", () => {
  beforeEach(() => {
    localStorage.clear();
    tokenStore.setTokens({ accessToken: "mock-valid-token" });
    tokenStore.setActiveTenantId("tenant_jakeai_core");
  });

  afterEach(() => {
    server.resetHandlers();
    localStorage.clear();
  });

  it("sends message and receives streamed SSE tokens into the message view", async () => {
    const user = userEvent.setup();
    renderWorkspace();

    const textarea = screen.getByPlaceholderText(/ask jakeai anything/i);
    await user.type(textarea, "Analyze financial solvency");

    const sendBtn = screen.getByRole("button", { name: /send/i });
    await user.click(sendBtn);

    // User message is rendered
    expect(screen.getAllByText("Analyze financial solvency").length).toBeGreaterThanOrEqual(1);

    // Streaming tokens accumulate and render
    await waitFor(() => {
      expect(
        screen.getByText(/JakeAI analyzes your request with multi-agent verification/i)
      ).toBeInTheDocument();
    });

    // Verification and citation rendered
    await waitFor(() => {
      expect(screen.getByText(/Grounded Sources & Citations/i)).toBeInTheDocument();
      expect(screen.getByText(/FinnApiGo Core Ledger/i)).toBeInTheDocument();
    });
  });

  it("cancels in-flight streaming when Stop button is clicked", async () => {
    const user = userEvent.setup();

    // Mock slow stream
    server.use(
      http.post("*/api/v1/chat/stream", () => {
        const encoder = new TextEncoder();
        const stream = new ReadableStream({
          start(controller) {
            controller.enqueue(
              encoder.encode(
                `event: status\ndata: {"phase":"initialized"}\n\nevent: token\ndata: {"delta":"Beginning generation..."}\n\n`
              )
            );
            // Don't close immediately to simulate long-running generation
          },
        });
        return new HttpResponse(stream, {
          headers: { "Content-Type": "text/event-stream" },
        });
      })
    );

    renderWorkspace();

    const textarea = screen.getByPlaceholderText(/ask jakeai anything/i);
    await user.type(textarea, "Long running financial audit");
    await user.click(screen.getByRole("button", { name: /send/i }));

    // Stop button appears
    const stopBtn = await screen.findByRole("button", { name: /stop/i });
    expect(stopBtn).toBeInTheDocument();

    // Click stop
    await user.click(stopBtn);

    // Stop button is replaced with Send button
    await waitFor(() => {
      expect(screen.getByRole("button", { name: /send/i })).toBeInTheDocument();
    });
  });

  it("handles SSE error event and allows retrying the request", async () => {
    const user = userEvent.setup();

    let attemptCount = 0;
    server.use(
      http.post("*/api/v1/chat/stream", () => {
        attemptCount++;
        const encoder = new TextEncoder();
        if (attemptCount === 1) {
          const stream = new ReadableStream({
            start(controller) {
              controller.enqueue(
                encoder.encode(
                  `event: error\ndata: {"error":"Guardrail violation","detail":"Safety policy threshold exceeded"}\n\n`
                )
              );
              controller.close();
            },
          });
          return new HttpResponse(stream, {
            headers: { "Content-Type": "text/event-stream" },
          });
        }

        // Success on retry
        const stream = new ReadableStream({
          start(controller) {
            controller.enqueue(
              encoder.encode(
                `event: token\ndata: {"delta":"Recovered response after retry"}\n\nevent: done\ndata: {"elapsed_ms":50,"conversation_id":"c1","tenant_id":"t1"}\n\n`
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
    await user.type(textarea, "Trigger test guardrail");
    await user.click(screen.getByRole("button", { name: /send/i }));

    // Error banner appears
    await waitFor(() => {
      expect(screen.getAllByText(/Safety policy threshold exceeded/i).length).toBeGreaterThanOrEqual(1);
    });

    // Click retry
    const retryBtn = screen.getByRole("button", { name: /retry request/i });
    await user.click(retryBtn);

    // Verify recovery
    await waitFor(() => {
      expect(screen.getByText(/Recovered response after retry/i)).toBeInTheDocument();
    });
  });

  it("handles HTTP 401 Unauthorized and notifies auth store", async () => {
    const user = userEvent.setup();
    const unauthorizedSpy = vi.fn();
    const unsubscribe = tokenStore.subscribeUnauthorized(unauthorizedSpy);

    server.use(
      http.post("*/api/v1/chat/stream", () => {
        return new HttpResponse(JSON.stringify({ detail: "Token has expired" }), {
          status: 401,
          headers: { "Content-Type": "application/json" },
        });
      })
    );

    renderWorkspace();

    const textarea = screen.getByPlaceholderText(/ask jakeai anything/i);
    await user.type(textarea, "Query with expired session");
    await user.click(screen.getByRole("button", { name: /send/i }));

    await waitFor(() => {
      expect(unauthorizedSpy).toHaveBeenCalled();
      expect(screen.getAllByText(/Session expired or unauthorized/i).length).toBeGreaterThanOrEqual(1);
    });

    unsubscribe();
  });

  it("handles HTTP 403 Forbidden with clear boundary message", async () => {
    const user = userEvent.setup();

    server.use(
      http.post("*/api/v1/chat/stream", () => {
        return new HttpResponse(JSON.stringify({ detail: "Tenant boundary isolation enforced" }), {
          status: 403,
          headers: { "Content-Type": "application/json" },
        });
      })
    );

    renderWorkspace();

    const textarea = screen.getByPlaceholderText(/ask jakeai anything/i);
    await user.type(textarea, "Access restricted cross-tenant data");
    await user.click(screen.getByRole("button", { name: /send/i }));

    await waitFor(() => {
      expect(screen.getAllByText(/Access to this workspace or resource is denied/i).length).toBeGreaterThanOrEqual(1);
    });
  });

  it("handles HTTP 429 Quota Exceeded with rate limit alert", async () => {
    const user = userEvent.setup();

    server.use(
      http.post("*/api/v1/chat/stream", () => {
        return new HttpResponse(JSON.stringify({ detail: "Token budget quota exceeded" }), {
          status: 429,
          headers: { "Content-Type": "application/json" },
        });
      })
    );

    renderWorkspace();

    const textarea = screen.getByPlaceholderText(/ask jakeai anything/i);
    await user.type(textarea, "High volume tokens prompt");
    await user.click(screen.getByRole("button", { name: /send/i }));

    await waitFor(() => {
      expect(screen.getAllByText(/Token budget quota exceeded/i).length).toBeGreaterThanOrEqual(1);
    });
  });

  it("handles HTTP 503 Service Unavailable with provider downtime message", async () => {
    const user = userEvent.setup();

    server.use(
      http.post("*/api/v1/chat/stream", () => {
        return new HttpResponse(JSON.stringify({ detail: "Provider backend offline" }), {
          status: 503,
          headers: { "Content-Type": "application/json" },
        });
      })
    );

    renderWorkspace();

    const textarea = screen.getByPlaceholderText(/ask jakeai anything/i);
    await user.type(textarea, "Test provider failure");
    await user.click(screen.getByRole("button", { name: /send/i }));

    await waitFor(() => {
      expect(screen.getAllByText(/AI Service or upstream provider temporarily unavailable/i).length).toBeGreaterThanOrEqual(1);
    });
  });

  it("cleans up active streams on component unmount without leaving orphaned readers", async () => {
    const user = userEvent.setup();
    const abortSpy = vi.spyOn(AbortController.prototype, "abort");

    server.use(
      http.post("*/api/v1/chat/stream", () => {
        const encoder = new TextEncoder();
        const stream = new ReadableStream({
          start(controller) {
            controller.enqueue(
              encoder.encode(`event: token\ndata: {"delta":"Streaming..."}\n\n`)
            );
          },
        });
        return new HttpResponse(stream, {
          headers: { "Content-Type": "text/event-stream" },
        });
      })
    );

    const { unmount } = renderWorkspace();

    const textarea = screen.getByPlaceholderText(/ask jakeai anything/i);
    await user.type(textarea, "Unmount test prompt");
    await user.click(screen.getByRole("button", { name: /send/i }));

    await waitFor(() => {
      expect(screen.getByRole("button", { name: /stop/i })).toBeInTheDocument();
    });

    // Unmount while stream is in flight
    act(() => {
      unmount();
    });

    expect(abortSpy).toHaveBeenCalled();
    abortSpy.mockRestore();
  });
});
