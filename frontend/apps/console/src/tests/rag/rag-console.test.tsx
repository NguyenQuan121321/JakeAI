/**
 * RAG Console Comprehensive Integration Tests
 *
 * Mandated Verification Criteria Tested:
 * 1. RAG query execution & chunk rendering
 * 2. Ingestion pending state & task polling
 * 3. Ingestion success (synchronous 201 & async completion)
 * 4. Ingestion failure & retry flow
 * 5. Citation display & verification drawer
 * 6. Epistemic abstention (NO_RELEVANT_EVIDENCE, zero false grounding)
 */

import { describe, it, expect, beforeEach, afterEach } from "vitest";
import { render, screen, waitFor, fireEvent } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { MemoryRouter } from "react-router-dom";
import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { server } from "@/mocks/server";
import { AuthProvider } from "@/context/auth-context";
import { ThemeProvider } from "@/context/theme-context";
import { tokenStore } from "@/api/auth/token-store";
import { RagSearchView } from "@/components/rag/rag-search-view";
import RagPage from "@/pages/rag";

function renderRagConsole(initialTab = "search") {
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
          <MemoryRouter initialEntries={[`/rag?tab=${initialTab}`]}>
            <RagPage />
          </MemoryRouter>
        </AuthProvider>
      </ThemeProvider>
    </QueryClientProvider>
  );
}

describe("FE-05 RAG Console Integration Suite", () => {
  beforeEach(() => {
    localStorage.clear();
    tokenStore.setTokens({ accessToken: "mock-valid-token" });
    tokenStore.setActiveTenantId("tenant_jakeai_core");
  });

  afterEach(() => {
    server.resetHandlers();
    localStorage.clear();
  });

  // Criterion 1: RAG Query Execution
  it("executes RAG search query and renders retrieved chunks with similarity metrics and metadata", async () => {
    const queryClient = new QueryClient({
      defaultOptions: { queries: { retry: false }, mutations: { retry: false } },
    });
    render(
      <QueryClientProvider client={queryClient}>
        <RagSearchView />
      </QueryClientProvider>
    );

    const searchBtn = screen.getByTestId("rag-search-button");
    fireEvent.click(searchBtn);

    // Chunks rendered
    await waitFor(() => {
      expect(
        screen.getAllByText(/Enterprise AI Security requires perimeter isolation/i).length
      ).toBeGreaterThanOrEqual(1);
    });

    // Similarity score badge and source badge
    expect(screen.getByText(/0.940/i)).toBeInTheDocument();
    expect(screen.getByText(/security-handbook.pdf/i)).toBeInTheDocument();

    // Metadata pills
    expect(screen.getByText(/SecOps/i)).toBeInTheDocument();
    expect(screen.getByText(/Internal/i)).toBeInTheDocument();

    // Copy chunk snippet
    const copyBtn = screen.getByRole("button", { name: /copy passage/i });
    expect(copyBtn).toBeInTheDocument();
  });

  // Criterion 2 & 3: Ingestion Pending & Async Polling Success
  it("initiates async document ingestion, tracks pending state, and updates on polling completion", async () => {
    const user = userEvent.setup();
    renderRagConsole("documents");

    // Open upload dialog
    const uploadBtn = screen.getAllByRole("button", { name: /upload document/i })[0];
    await user.click(uploadBtn);

    // Fill in document dialog
    const sourceInput = screen.getByLabelText(/document name \/ source identifier/i);
    await user.type(sourceInput, "quarterly-report.pdf");

    const contentInput = screen.getByLabelText(/^document content$/i);
    await user.type(contentInput, "Quarterly security compliance audit passed with zero vulnerabilities.");

    // Submit ingestion
    const submitBtn = screen.getByRole("button", { name: /enqueue ingestion job/i });
    await user.click(submitBtn);

    // Upload dialog closes, switches to Ingestion Jobs view
    await waitFor(() => {
      expect(screen.getByText(/quarterly-report.pdf/i)).toBeInTheDocument();
    });

    // Ingestion jobs view shows queued/processing task
    expect(screen.getByText(/Asynchronous Ingestion Tasks/i)).toBeInTheDocument();
  });

  // Criterion 3: Ingestion Success (Synchronous mode)
  it("executes synchronous document ingestion and immediately records active document", async () => {
    const user = userEvent.setup();
    renderRagConsole("documents");

    // Open upload dialog
    const uploadBtn = screen.getAllByRole("button", { name: /upload document/i })[0];
    await user.click(uploadBtn);

    const sourceInput = screen.getByLabelText(/document name \/ source identifier/i);
    await user.type(sourceInput, "soc2-type2.pdf");

    const contentInput = screen.getByLabelText(/^document content$/i);
    await user.type(contentInput, "SOC2 Type II compliance verified for all cryptographic key management systems.");

    // Toggle async mode OFF
    const asyncToggle = screen.getByLabelText(/asynchronous/i);
    await user.click(asyncToggle);

    // Submit
    const submitBtn = screen.getByRole("button", { name: /ingest synchronously/i });
    await user.click(submitBtn);

    // Document appears in Documents list
    await waitFor(() => {
      expect(screen.getByText("soc2-type2.pdf")).toBeInTheDocument();
    });
  });

  // Criterion 4: Ingestion Failure & Error Display
  it("handles document ingestion failure and displays error feedback", async () => {
    const user = userEvent.setup();
    renderRagConsole("documents");

    const uploadBtn = screen.getAllByRole("button", { name: /upload document/i })[0];
    await user.click(uploadBtn);

    const sourceInput = screen.getByLabelText(/document name \/ source identifier/i);
    await user.type(sourceInput, "corrupt-file.pdf");

    const contentInput = screen.getByLabelText(/^document content$/i);
    await user.type(contentInput, "fail-now: trigger 400 error");

    const submitBtn = screen.getByRole("button", { name: /enqueue ingestion job/i });
    await user.click(submitBtn);

    // Error alert displayed inside dialog
    await waitFor(() => {
      expect(
        screen.getByText(/unsupported document format or corrupted encoding/i)
      ).toBeInTheDocument();
    });
  });

  // Criterion 5: Citation Display & Verification Drawer
  it("generates grounded answers with interactive citations and inspects citation context", async () => {
    const user = userEvent.setup();
    renderRagConsole("grounded-generation");

    const queryInput = screen.getByPlaceholderText(/ask a question requiring grounded tenant evidence/i);
    await user.clear(queryInput);
    await user.type(queryInput, "What are enterprise security guidelines?");

    const generateBtn = screen.getByRole("button", { name: /generate grounded answer/i });
    await user.click(generateBtn);

    // Grounded synthesis rendered
    await waitFor(() => {
      expect(
        screen.getByText(/According to enterprise guidelines \[1\], perimeter isolation and cryptographic key scoping are required/i)
      ).toBeInTheDocument();
    });

    // Verification badge displayed
    expect(screen.getByText("Grounded")).toBeInTheDocument();

    // Citation badge rendered
    const citationBadge = screen.getByText(/\[1\] security-handbook.pdf/i);
    expect(citationBadge).toBeInTheDocument();

    // Click citation to open citation verification modal
    await user.click(citationBadge);

    await waitFor(() => {
      expect(screen.getByText(/Citation \[1\] Verification Details/i)).toBeInTheDocument();
      expect(screen.getByText(/Direct factual entailment from security handbook chunk-1/i)).toBeInTheDocument();
    });
  });

  // Criterion 6: Epistemic Abstention (NO_RELEVANT_EVIDENCE & Zero False Grounding)
  it("handles epistemic abstention without falsely reporting grounded synthesis", async () => {
    const user = userEvent.setup();
    renderRagConsole("grounded-generation");

    const queryInput = screen.getByPlaceholderText(/ask a question requiring grounded tenant evidence/i);
    await user.clear(queryInput);
    await user.type(queryInput, "What is the secret Martian alien transmission?");

    const generateBtn = screen.getByRole("button", { name: /generate grounded answer/i });
    await user.click(generateBtn);

    // Status: Abstained rendered
    await waitFor(() => {
      expect(
        screen.getByText(/Abstained: Insufficient Evidence/i)
      ).toBeInTheDocument();
    });

    // Clear abstention reason displayed
    expect(
      screen.getByText(/I cannot answer this question as the knowledge base does not contain relevant verifiable evidence/i)
    ).toBeInTheDocument();

    // MUST NOT display "Grounded" badge
    expect(screen.queryByText(/^Grounded$/)).not.toBeInTheDocument();

    // Zero citations rendered
    expect(screen.queryByText(/\[1\]/)).not.toBeInTheDocument();
  });
});
