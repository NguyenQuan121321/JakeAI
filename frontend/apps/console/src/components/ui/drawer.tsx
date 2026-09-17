import * as React from "react";
import { X } from "lucide-react";
import { cn } from "@/lib/utils";

interface DrawerProps {
  open: boolean;
  onOpenChange: (open: boolean) => void;
  position?: "left" | "right" | "bottom";
  children: React.ReactNode;
  className?: string;
  title?: string;
  description?: string;
}

export function Drawer({
  open,
  onOpenChange,
  position = "left",
  children,
  className,
  title = "Navigation Drawer",
  description,
}: DrawerProps) {
  React.useEffect(() => {
    const handleKeyDown = (e: KeyboardEvent) => {
      if (e.key === "Escape" && open) {
        onOpenChange(false);
      }
    };
    if (open) {
      document.body.style.overflow = "hidden";
      window.addEventListener("keydown", handleKeyDown);
    }
    return () => {
      document.body.style.overflow = "unset";
      window.removeEventListener("keydown", handleKeyDown);
    };
  }, [open, onOpenChange]);

  if (!open) return null;

  const positionClasses = {
    left: "inset-y-0 left-0 h-full w-3/4 max-w-sm border-r animate-in slide-in-from-left duration-300",
    right: "inset-y-0 right-0 h-full w-3/4 max-w-md border-l animate-in slide-in-from-right duration-300",
    bottom: "inset-x-0 bottom-0 max-h-[85vh] w-full border-t animate-in slide-in-from-bottom duration-300",
  };

  return (
    <div className="fixed inset-0 z-50 flex" role="dialog" aria-modal="true" aria-label={title}>
      {/* Backdrop */}
      <div
        className="fixed inset-0 bg-background/80 backdrop-blur-sm transition-opacity"
        onClick={() => onOpenChange(false)}
        aria-hidden="true"
      />
      {/* Panel */}
      <div
        className={cn(
          "relative z-50 flex flex-col bg-background p-6 shadow-2xl overflow-y-auto",
          positionClasses[position],
          className
        )}
      >
        <div className="flex items-center justify-between pb-4 border-b">
          <div>
            <h2 className="text-base font-semibold">{title}</h2>
            {description && <p className="text-xs text-muted-foreground">{description}</p>}
          </div>
          <button
            type="button"
            onClick={() => onOpenChange(false)}
            aria-label="Close drawer"
            className="rounded-sm opacity-70 transition-opacity hover:opacity-100 focus:outline-none focus:ring-2 focus:ring-ring"
          >
            <X className="h-4 w-4" />
          </button>
        </div>
        <div className="mt-4 flex-1">{children}</div>
      </div>
    </div>
  );
}
