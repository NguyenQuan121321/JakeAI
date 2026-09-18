import * as React from "react";
import { AlertTriangle, ShieldAlert, Loader2 } from "lucide-react";
import {
  Dialog,
  DialogContent,
  DialogHeader,
  DialogTitle,
  DialogDescription,
  DialogFooter,
} from "@/components/ui/dialog";
import { Button } from "@/components/ui/button";
import { Input } from "@/components/ui/input";
import { cn } from "@/lib/utils";

export interface ConfirmDialogProps {
  open: boolean;
  onOpenChange: (open: boolean) => void;
  title: string;
  description: string;
  confirmLabel?: string;
  cancelLabel?: string;
  variant?: "default" | "destructive" | "warning";
  /** If provided, user must type this exact text to enable the confirm button */
  requireConfirmationText?: string;
  confirmationPlaceholder?: string;
  onConfirm: () => void | Promise<void>;
  isLoading?: boolean;
}

export function ConfirmDialog({
  open,
  onOpenChange,
  title,
  description,
  confirmLabel = "Confirm",
  cancelLabel = "Cancel",
  variant = "default",
  requireConfirmationText,
  confirmationPlaceholder,
  onConfirm,
  isLoading = false,
}: ConfirmDialogProps) {
  const [typedText, setTypedText] = React.useState("");

  React.useEffect(() => {
    if (!open) {
      setTypedText("");
    }
  }, [open]);

  const isConfirmationValid = React.useMemo(() => {
    if (!requireConfirmationText) return true;
    return typedText.trim() === requireConfirmationText.trim();
  }, [requireConfirmationText, typedText]);

  const handleConfirm = async () => {
    if (!isConfirmationValid || isLoading) return;
    await onConfirm();
  };

  const isDestructive = variant === "destructive";

  return (
    <Dialog open={open} onOpenChange={onOpenChange}>
      <DialogContent onClose={() => onOpenChange(false)} className="max-w-md">
        <DialogHeader>
          <div className="flex items-center space-x-3">
            <div
              className={cn(
                "flex h-10 w-10 items-center justify-center rounded-full flex-shrink-0",
                isDestructive
                  ? "bg-destructive/15 text-destructive"
                  : "bg-amber-500/15 text-amber-600 dark:text-amber-400"
              )}
            >
              {isDestructive ? (
                <ShieldAlert className="h-5 w-5" aria-hidden="true" />
              ) : (
                <AlertTriangle className="h-5 w-5" aria-hidden="true" />
              )}
            </div>
            <div>
              <DialogTitle className="text-base font-semibold">{title}</DialogTitle>
            </div>
          </div>
          <DialogDescription className="mt-2 text-sm text-muted-foreground">
            {description}
          </DialogDescription>
        </DialogHeader>

        {requireConfirmationText && (
          <div className="my-4 space-y-2">
            <label
              htmlFor="confirmation-input"
              className="text-xs font-medium text-foreground block"
            >
              To confirm, type{" "}
              <span className="font-mono font-bold text-destructive">
                {requireConfirmationText}
              </span>{" "}
              below:
            </label>
            <Input
              id="confirmation-input"
              type="text"
              autoFocus
              value={typedText}
              onChange={(e) => setTypedText(e.target.value)}
              placeholder={confirmationPlaceholder || `Type "${requireConfirmationText}"`}
              className="font-mono text-sm"
              onKeyDown={(e) => {
                if (e.key === "Enter" && isConfirmationValid && !isLoading) {
                  e.preventDefault();
                  handleConfirm();
                }
              }}
            />
          </div>
        )}

        <DialogFooter className="mt-6 flex flex-col-reverse sm:flex-row sm:justify-end sm:space-x-2">
          <Button
            type="button"
            variant="outline"
            size="sm"
            onClick={() => onOpenChange(false)}
            disabled={isLoading}
          >
            {cancelLabel}
          </Button>
          <Button
            type="button"
            variant={isDestructive ? "destructive" : "default"}
            size="sm"
            onClick={handleConfirm}
            disabled={!isConfirmationValid || isLoading}
            className="min-w-[90px]"
          >
            {isLoading ? (
              <>
                <Loader2 className="h-4 w-4 animate-spin mr-1.5" />
                Processing...
              </>
            ) : (
              confirmLabel
            )}
          </Button>
        </DialogFooter>
      </DialogContent>
    </Dialog>
  );
}
