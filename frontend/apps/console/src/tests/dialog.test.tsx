import * as React from "react";
import { describe, it, expect } from "vitest";
import { render, screen, fireEvent } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { Dialog, DialogContent, DialogHeader, DialogTitle, DialogDescription, DialogFooter } from "@/components/ui/dialog";
import { Button } from "@/components/ui/button";

function ControlledDialog({ openByDefault = true }: { openByDefault?: boolean }) {
  const [open, setOpen] = React.useState(openByDefault);
  return (
    <div>
      <button onClick={() => setOpen(true)}>Open Modal</button>
      <Dialog open={open} onOpenChange={setOpen}>
        <DialogContent onClose={() => setOpen(false)}>
          <DialogHeader>
            <DialogTitle>Test Dialog Title</DialogTitle>
            <DialogDescription>Test Dialog Description</DialogDescription>
          </DialogHeader>
          <div>Modal Body Content</div>
          <DialogFooter>
            <Button onClick={() => setOpen(false)}>Confirm</Button>
          </DialogFooter>
        </DialogContent>
      </Dialog>
    </div>
  );
}

describe("Dialog Primitive", () => {
  it("renders when open and provides accessible ARIA dialog roles", () => {
    render(<ControlledDialog openByDefault={true} />);

    const dialog = screen.getByRole("dialog");
    expect(dialog).toBeInTheDocument();
    expect(dialog).toHaveAttribute("aria-modal", "true");
    expect(screen.getByText("Test Dialog Title")).toBeInTheDocument();
    expect(screen.getByText("Test Dialog Description")).toBeInTheDocument();
  });

  it("closes when the close button is clicked", async () => {
    const user = userEvent.setup();
    render(<ControlledDialog openByDefault={true} />);

    expect(screen.getByRole("dialog")).toBeInTheDocument();
    const closeBtn = screen.getByLabelText("Close dialog");
    await user.click(closeBtn);

    expect(screen.queryByRole("dialog")).not.toBeInTheDocument();
  });

  it("closes on Escape key press", () => {
    render(<ControlledDialog openByDefault={true} />);

    expect(screen.getByRole("dialog")).toBeInTheDocument();
    fireEvent.keyDown(window, { key: "Escape", code: "Escape" });

    expect(screen.queryByRole("dialog")).not.toBeInTheDocument();
  });
});
