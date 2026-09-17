import { describe, it, expect, vi } from "vitest";
import { render, screen } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { Button } from "@/components/ui/button";
import { ErrorState } from "@/components/ui/error-state";
import { LoadingState } from "@/components/feedback/loading-state";
import { EmptyState } from "@/components/ui/empty-state";
import { MetricCard } from "@/components/ui/metric-card";

describe("Design System Core Primitives", () => {
  describe("Button", () => {
    it("renders button with text and handles clicks", async () => {
      const handleClick = vi.fn();
      const user = userEvent.setup();
      render(<Button onClick={handleClick}>Click Me</Button>);

      const btn = screen.getByRole("button", { name: "Click Me" });
      await user.click(btn);
      expect(handleClick).toHaveBeenCalledTimes(1);
    });

    it("displays spinner and sets aria-busy when loading", () => {
      render(<Button isLoading>Processing</Button>);
      const btn = screen.getByRole("button");
      expect(btn).toBeDisabled();
      expect(btn).toHaveAttribute("aria-busy", "true");
    });
  });

  describe("LoadingState", () => {
    it("renders with status role and aria-busy set to true", () => {
      render(<LoadingState message="Fetching agent telemetry..." />);
      const statusEl = screen.getByRole("status");
      expect(statusEl).toBeInTheDocument();
      expect(statusEl).toHaveAttribute("aria-busy", "true");
      expect(screen.getByText("Fetching agent telemetry...")).toBeInTheDocument();
    });
  });

  describe("ErrorState", () => {
    it("renders accessible error alert with retry button", async () => {
      const handleRetry = vi.fn();
      const user = userEvent.setup();
      render(
        <ErrorState
          title="Network Failure"
          message="Could not communicate with backend gateway."
          onRetry={handleRetry}
        />
      );

      const alert = screen.getByRole("alert");
      expect(alert).toBeInTheDocument();
      expect(screen.getByText("Network Failure")).toBeInTheDocument();

      const retryBtn = screen.getByRole("button", { name: /retry operation/i });
      await user.click(retryBtn);
      expect(handleRetry).toHaveBeenCalledTimes(1);
    });
  });

  describe("EmptyState", () => {
    it("renders title, description and action slot", () => {
      render(
        <EmptyState
          title="No Vector Collections Found"
          description="Create your first collection to enable retrieval."
          action={<Button>Create Collection</Button>}
        />
      );

      expect(screen.getByText("No Vector Collections Found")).toBeInTheDocument();
      expect(screen.getByText("Create your first collection to enable retrieval.")).toBeInTheDocument();
      expect(screen.getByRole("button", { name: "Create Collection" })).toBeInTheDocument();
    });
  });

  describe("MetricCard", () => {
    it("renders title, value and trend indicator", () => {
      render(
        <MetricCard
          title="Daily Active Tokens"
          value="1.2M"
          change={{ value: "+14.2%", trend: "up", label: "vs yesterday" }}
        />
      );

      expect(screen.getByText("Daily Active Tokens")).toBeInTheDocument();
      expect(screen.getByText("1.2M")).toBeInTheDocument();
      expect(screen.getByText("+14.2%")).toBeInTheDocument();
      expect(screen.getByText("vs yesterday")).toBeInTheDocument();
    });
  });
});
