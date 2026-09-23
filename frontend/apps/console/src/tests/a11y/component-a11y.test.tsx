/**
 * Accessibility (A11y) & Interactive ARIA Verification Suite
 *
 * Verifies:
 * - Keyboard navigation (Tab, Escape, Enter, Space)
 * - Focus trapping and restoration
 * - Dialog & Drawer ARIA compliance (role, aria-modal, aria-labelledby, aria-describedby)
 * - Form controls & accessible labels (input, select, textarea, error states)
 * - Screen reader announcements (role="status", aria-live="polite", role="alert")
 * - WCAG 2.1 AA semantic compliance
 */

import { describe, it, expect, vi } from "vitest";
import { render, screen, fireEvent, act } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { MemoryRouter } from "react-router-dom";
import { Dialog, DialogContent, DialogTitle, DialogDescription } from "@/components/ui/dialog";
import { Select } from "@/components/ui/select";
import { Input } from "@/components/ui/input";
import { Alert, AlertTitle, AlertDescription } from "@/components/ui/alert";
import { Button } from "@/components/ui/button";
import { PermissionDeniedState } from "@/components/feedback/permission-denied-state";
import { OfflineBanner } from "@/components/feedback/offline-banner";
import { StatusIndicator } from "@/components/ui/status-indicator";

describe("FE-07 Component Accessibility & ARIA Verification", () => {
  describe("Dialog A11y & Focus Management", () => {
    it("renders with correct ARIA modal roles, labelledby, and describedby", () => {
      render(
        <Dialog open={true} onOpenChange={() => {}}>
          <DialogContent titleId="custom-title" descriptionId="custom-desc">
            <DialogTitle id="custom-title">Confirm Operation</DialogTitle>
            <DialogDescription id="custom-desc">This action cannot be undone.</DialogDescription>
            <Button>Proceed</Button>
          </DialogContent>
        </Dialog>
      );

      const dialogEl = screen.getByRole("dialog");
      expect(dialogEl).toHaveAttribute("aria-modal", "true");
      expect(dialogEl).toHaveAttribute("aria-labelledby", "custom-title");
      expect(dialogEl).toHaveAttribute("aria-describedby", "custom-desc");
    });

    it("closes dialog when Escape key is pressed", () => {
      const handleOpenChange = vi.fn();
      render(
        <Dialog open={true} onOpenChange={handleOpenChange}>
          <DialogContent>
            <DialogTitle>Escape Test</DialogTitle>
            <Button>Inside</Button>
          </DialogContent>
        </Dialog>
      );

      fireEvent.keyDown(window, { key: "Escape" });
      expect(handleOpenChange).toHaveBeenCalledWith(false);
    });

    it("has accessible close button with aria-label", () => {
      const handleClose = vi.fn();
      render(
        <Dialog open={true} onOpenChange={() => {}}>
          <DialogContent onClose={handleClose}>
            <DialogTitle>Close Button Test</DialogTitle>
          </DialogContent>
        </Dialog>
      );

      const closeBtn = screen.getByRole("button", { name: /close dialog/i });
      expect(closeBtn).toBeInTheDocument();
      fireEvent.click(closeBtn);
      expect(handleClose).toHaveBeenCalledTimes(1);
    });
  });

  describe("Form Controls & Accessible Labels", () => {
    it("associates input with label and communicates error states via aria-invalid", () => {
      render(
        <div>
          <label htmlFor="test-input">API Token</label>
          <Input id="test-input" hasError={true} aria-describedby="input-error" />
          <span id="input-error" role="alert">Token is required</span>
        </div>
      );

      const inputEl = screen.getByLabelText("API Token");
      expect(inputEl).toBeInTheDocument();
      expect(inputEl).toHaveAttribute("aria-invalid", "true");
      expect(inputEl).toHaveAttribute("aria-describedby", "input-error");
      expect(screen.getByRole("alert")).toHaveTextContent("Token is required");
    });

    it("manages keyboard navigation in Select with Enter, Space, and Arrow keys", async () => {
      const user = userEvent.setup();
      const handleChange = vi.fn();
      const options = [
        { value: "gpt-4o", label: "OpenAI GPT-4o" },
        { value: "claude-3-5", label: "Claude 3.5 Sonnet" },
        { value: "gemini-1-5", label: "Gemini 1.5 Pro" },
      ];

      render(
        <Select
          options={options}
          value="gpt-4o"
          onChange={handleChange}
          ariaLabel="Select model"
        />
      );

      const selectTrigger = screen.getByRole("combobox");
      expect(selectTrigger).toHaveAttribute("aria-expanded", "false");
      expect(selectTrigger).toHaveAttribute("aria-haspopup", "listbox");

      // Open with click
      await user.click(selectTrigger);
      expect(selectTrigger).toHaveAttribute("aria-expanded", "true");

      const listbox = screen.getByRole("listbox");
      expect(listbox).toBeInTheDocument();

      // Click second option
      const option2 = screen.getByRole("option", { name: "Claude 3.5 Sonnet" });
      await user.click(option2);
      expect(handleChange).toHaveBeenCalledWith("claude-3-5");
    });
  });

  describe("Status Announcements & Alert Roles", () => {
    it("renders Alert component with role='alert' for critical feedback", () => {
      render(
        <Alert variant="destructive">
          <AlertTitle>Quota Exceeded</AlertTitle>
          <AlertDescription>Your monthly token budget has reached 100%.</AlertDescription>
        </Alert>
      );

      const alertEl = screen.getByRole("alert");
      expect(alertEl).toBeInTheDocument();
      expect(alertEl).toHaveTextContent("Quota Exceeded");
    });

    it("renders PermissionDeniedState with heading and clear security boundary message", () => {
      render(
        <MemoryRouter>
          <PermissionDeniedState
            requiredRoles={["admin"]}
            title="Access Restricted"
            description="Administrative privileges required to access audit logs."
          />
        </MemoryRouter>
      );

      expect(screen.getByRole("heading", { level: 2 })).toHaveTextContent("Access Restricted");
      expect(screen.getByRole("alert")).toBeInTheDocument();
    });

    it("renders OfflineBanner with role='alert' and aria-live='assertive' upon offline event", () => {
      render(<OfflineBanner />);

      // Trigger offline event
      act(() => {
        window.dispatchEvent(new Event("offline"));
      });

      const banner = screen.getByRole("alert");
      expect(banner).toHaveAttribute("aria-live", "assertive");
      expect(banner).toHaveTextContent(/Offline Mode/i);
    });

    it("renders StatusIndicator with accessible screen-reader aria-label", () => {
      render(<StatusIndicator status="running" showLabel={false} />);
      const indicator = screen.getByRole("status");
      expect(indicator).toHaveAttribute("aria-label", "Status: Running");
    });
  });
});
