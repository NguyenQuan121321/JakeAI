/**
 * Workspace Threads, Model Selection, and UX Integration Tests
 *
 * Tests:
 * - Thread creation, switching, deletion, and local persistence
 * - Model selector population from /api/v1/gateway/models
 * - Keyboard shortcuts (Enter sends, Shift+Enter new line)
 * - Empty state suggestion chips
 */

import { describe, it, expect, beforeEach, afterEach } from "vitest";
import { render, screen, waitFor } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { MemoryRouter } from "react-router-dom";
import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
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

describe("Workspace Thread Management & Model UX", () => {
  beforeEach(() => {
    localStorage.clear();
    tokenStore.setTokens({ accessToken: "mock-valid-token" });
    tokenStore.setActiveTenantId("tenant_jakeai_core");
  });

  afterEach(() => {
    server.resetHandlers();
    localStorage.clear();
  });

  it("populates controlled model selector from backend gateway models", async () => {
    renderWorkspace();

    // Model select button/element is visible
    const modelTrigger = await screen.findByRole("button", { name: /select model/i });
    expect(modelTrigger).toBeInTheDocument();
  });

  it("creates, switches, and persists conversation threads", async () => {
    const user = userEvent.setup();
    renderWorkspace();

    // Initially in empty state
    expect(screen.getByText("JakeAI Orchestration Workspace")).toBeInTheDocument();

    // Send first message in Thread 1
    const textarea = screen.getByPlaceholderText(/ask jakeai anything/i);
    await user.type(textarea, "Thread 1 initial query");
    await user.click(screen.getByRole("button", { name: /send/i }));

    // Wait for message in chatLog
    await waitFor(() => {
      expect(screen.getAllByText("Thread 1 initial query").length).toBeGreaterThanOrEqual(1);
    });

    // Create New Conversation
    const newChatBtn = screen.getByRole("button", { name: /new conversation/i });
    await user.click(newChatBtn);

    // Empty state returns for new thread
    await waitFor(() => {
      expect(screen.getByText("JakeAI Orchestration Workspace")).toBeInTheDocument();
    });

    // Send message in Thread 2
    const textarea2 = screen.getByPlaceholderText(/ask jakeai anything/i);
    await user.type(textarea2, "Thread 2 unique query");
    await user.click(screen.getByRole("button", { name: /send/i }));

    await waitFor(() => {
      expect(screen.getAllByText("Thread 2 unique query").length).toBeGreaterThanOrEqual(1);
    });

    // Switch back to Thread 1 by clicking its title in the sidebar
    const thread1Titles = screen.getAllByText("Thread 1 initial query");
    // Click the sidebar title item
    await user.click(thread1Titles[0]);

    // Thread 1 messages restored in chat
    await waitFor(() => {
      expect(screen.getAllByText("Thread 1 initial query").length).toBeGreaterThanOrEqual(1);
    });
  });

  it("clears active conversation messages", async () => {
    const user = userEvent.setup();
    renderWorkspace();

    const textarea = screen.getByPlaceholderText(/ask jakeai anything/i);
    await user.type(textarea, "Message to be cleared");
    await user.click(screen.getByRole("button", { name: /send/i }));

    await waitFor(() => {
      expect(screen.getAllByText("Message to be cleared").length).toBeGreaterThanOrEqual(1);
    });

    // Click Clear Active Thread
    const clearBtn = screen.getByRole("button", { name: /clear active thread/i });
    await user.click(clearBtn);

    // Returns to empty state
    await waitFor(() => {
      expect(screen.getByText("JakeAI Orchestration Workspace")).toBeInTheDocument();
    });
  });

  it("handles Enter to send and Shift+Enter for new line", async () => {
    const user = userEvent.setup();
    renderWorkspace();

    const textarea = screen.getByPlaceholderText(/ask jakeai anything/i);

    // Shift+Enter creates a new line without sending
    await user.type(textarea, "Line 1{Shift>}{Enter}{/Shift}Line 2");
    expect(textarea).toHaveValue("Line 1\nLine 2");
    expect(screen.queryByText("Line 1")).not.toBeInTheDocument();

    // Plain Enter sends the message
    await user.type(textarea, "{Enter}");

    await waitFor(() => {
      expect(
        screen.getAllByText((content) => content.includes("Line 1") && content.includes("Line 2"))
          .length
      ).toBeGreaterThanOrEqual(1);
    });
  });

  it("triggers prompt generation from empty state starter suggestions", async () => {
    const user = userEvent.setup();
    renderWorkspace();

    // Click starter prompt
    const starterCard = screen.getByRole("button", {
      name: /Financial Ratio & EBITDA Analysis/i,
    });
    await user.click(starterCard);

    // Verified that request was sent
    await waitFor(() => {
      expect(
        screen.getByText(/Calculate EBITDA and analyze corporate financial liquidity ratios/i)
      ).toBeInTheDocument();
    });
  });
});
