import { describe, it, expect } from "vitest";
import { render, screen } from "@testing-library/react";
import { StatusIndicator } from "@/components/ui/status-indicator";
import { STATUS_REGISTRY, getStatusDefinition } from "@/lib/status";
import type { SemanticStatus } from "@/types/status";

describe("Status System & Semantic Tokens", () => {
  const allStatuses: SemanticStatus[] = [
    "idle",
    "queued",
    "running",
    "paused",
    "waiting_approval",
    "completed",
    "failed",
    "cancelled",
    "blocked",
    "degraded",
    "healthy",
    "unknown",
  ];

  it("contains registry definitions for all 12 semantic statuses", () => {
    expect(Object.keys(STATUS_REGISTRY)).toHaveLength(12);
    allStatuses.forEach((status) => {
      const def = getStatusDefinition(status);
      expect(def).toBeDefined();
      expect(def.label).toBeTruthy();
      expect(def.ariaLabel).toContain(def.label);
      expect(def.icon).toBeDefined();
    });
  });

  allStatuses.forEach((status) => {
    it(`renders status '${status}' with accessible aria-label and label text`, () => {
      const { unmount } = render(<StatusIndicator status={status} variant="badge" />);
      const statusElement = screen.getByRole("status");
      expect(statusElement).toBeInTheDocument();

      const def = getStatusDefinition(status);
      expect(statusElement).toHaveAttribute("aria-label", def.ariaLabel);
      expect(statusElement).toHaveTextContent(def.label);
      unmount();
    });
  });

  it("renders dot variant without relying solely on color", () => {
    render(<StatusIndicator status="running" variant="dot" showLabel={true} />);
    const statusElement = screen.getByRole("status");
    expect(statusElement).toHaveTextContent("Running");
    expect(statusElement).toHaveAttribute("aria-label", "Status: Running");
  });

  it("falls back gracefully to 'unknown' status for unrecognized strings", () => {
    render(<StatusIndicator status="non_existent_status" />);
    const statusElement = screen.getByRole("status");
    expect(statusElement).toHaveTextContent("Unknown");
    expect(statusElement).toHaveAttribute("aria-label", "Status: Unknown");
  });
});
