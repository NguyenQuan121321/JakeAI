import { describe, it, expect, vi, beforeEach } from "vitest";
import { render, screen, fireEvent } from "@testing-library/react";
import { NodeInspector } from "@/components/agent-canvas/node-inspector";
import type { CanvasNodeData } from "@/types/agent-graph";

describe("Agent NodeInspector Component", () => {
  beforeEach(() => {
    vi.clearAllMocks();
  });

  it("renders empty state placeholder when no node is selected", () => {
    render(<NodeInspector nodeData={null} onClose={vi.fn()} />);
    expect(screen.getByText("Select a node in the canvas")).toBeInTheDocument();
    expect(
      screen.getByText(/Inspect contract-approved parameters, execution status/i)
    ).toBeInTheDocument();
  });

  it("renders contract-approved inputs, outputs, citations, latency and verdict", () => {
    const mockNode: CanvasNodeData = {
      id: "node-test-1",
      label: "SEC 10-K Retrieval Agent",
      sublabel: "agent-fin-retriever",
      category: "agent",
      status: "completed",
      description: "Performs dense-sparse hybrid retrieval",
      latencyMs: 142,
      executionCount: 2,
      verdict: "PASS",
      inputs: {
        ticker: "AAPL",
        year: 2024,
      },
      outputs: "Identified $105B in cash equivalents and marketable securities.",
      citations: [
        {
          source: "SEC 10-K FY2024 Item 8 Note 3",
          snippet: "Cash, cash equivalents and marketable securities totaled $105,000 million",
          confidence: 0.98,
        },
      ],
    };

    const onClose = vi.fn();
    render(<NodeInspector nodeData={mockNode} onClose={onClose} />);

    expect(screen.getByText("SEC 10-K Retrieval Agent")).toBeInTheDocument();
    expect(screen.getByText("agent-fin-retriever")).toBeInTheDocument();
    expect(screen.getByText("142ms")).toBeInTheDocument();
    expect(screen.getByText("x2")).toBeInTheDocument();
    expect(screen.getByText("PASS")).toBeInTheDocument();
    expect(screen.getByText(/"ticker":\s*"AAPL"/)).toBeInTheDocument();
    expect(screen.getByText(/Identified \$105B in cash equivalents/)).toBeInTheDocument();
    expect(screen.getByText("SEC 10-K FY2024 Item 8 Note 3")).toBeInTheDocument();
    expect(screen.getByText(/98% match/)).toBeInTheDocument();

    // Close button
    const closeBtn = screen.getByLabelText("Close Inspector");
    fireEvent.click(closeBtn);
    expect(onClose).toHaveBeenCalled();
  });

  it("STRICT PRIVACY GUARD: filters out private CoT reasoning traces, JWTs, and internal prompts", () => {
    const sensitiveNode: CanvasNodeData = {
      id: "node-sensitive-test",
      label: "Financial Decision Engine",
      sublabel: "model-gpt-4o",
      category: "model",
      status: "completed",
      inputs: { query: "Public company financial health" },
      outputs: "Healthy liquidity ratio of 1.45.",
      metadata: {
        // Safe metadata
        required_capabilities: ["financial_analysis", "rag"],
        selected_model: "gpt-4o-mini",
        // Prohibited internal fields
        chain_of_thought: "HIDDEN_COT_REASONING_DO_NOT_EXPOSE",
        internal_prompt: "SECRET_SYSTEM_PROMPT_INSTRUCTION",
        system_prompt: "INTERNAL_PROMPT_POLICY_COMPLIANCE",
        jwt: "eyJhbGciOiJIUzI1NiIsInR5cCI6IkpXVCJ9.sensitive_payload",
        api_key: "sk-live-super-secret-token-key-12345",
        obo_token: "obo_restricted_user_bearer_token",
      },
    };

    render(<NodeInspector nodeData={sensitiveNode} onClose={vi.fn()} />);

    // Safe fields should be rendered
    expect(screen.getByText("Financial Decision Engine")).toBeInTheDocument();
    expect(screen.getByText("required_capabilities:")).toBeInTheDocument();
    expect(screen.getByText("selected_model:")).toBeInTheDocument();

    // Strictly assert NO private / sensitive CoT or secrets are in the document
    expect(screen.queryByText(/HIDDEN_COT_REASONING/i)).not.toBeInTheDocument();
    expect(screen.queryByText(/SECRET_SYSTEM_PROMPT/i)).not.toBeInTheDocument();
    expect(screen.queryByText(/INTERNAL_PROMPT_POLICY/i)).not.toBeInTheDocument();
    expect(screen.queryByText(/eyJhbGciOiJIUzI1Ni/i)).not.toBeInTheDocument();
    expect(screen.queryByText(/sk-live-super-secret/i)).not.toBeInTheDocument();
    expect(screen.queryByText(/obo_restricted/i)).not.toBeInTheDocument();
  });

  it("copies output text to clipboard when copy button is clicked", () => {
    const writeTextSpy = vi.fn().mockResolvedValue(undefined);
    Object.defineProperty(navigator, "clipboard", {
      value: {
        writeText: writeTextSpy,
      },
      writable: true,
      configurable: true,
    });

    const mockNode: CanvasNodeData = {
      id: "node-copy-test",
      label: "Summary Synthesizer",
      category: "result",
      status: "completed",
      outputs: "Final synthesized financial audit report",
    };

    render(<NodeInspector nodeData={mockNode} onClose={vi.fn()} />);

    const copyBtn = screen.getByText("Copy");
    fireEvent.click(copyBtn);

    expect(writeTextSpy).toHaveBeenCalledWith("Final synthesized financial audit report");
  });
});
