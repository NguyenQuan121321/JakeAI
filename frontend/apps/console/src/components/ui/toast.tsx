import { X, CheckCircle2, AlertCircle, Info, AlertTriangle } from "lucide-react";
import { useToast, type ToastVariant } from "@/hooks/use-toast";
import { cn } from "@/lib/utils";

export function Toaster() {
  const { toasts, dismiss } = useToast();

  const getVariantStyles = (variant?: ToastVariant) => {
    switch (variant) {
      case "destructive":
        return "border-destructive bg-destructive text-destructive-foreground";
      case "success":
        return "border-emerald-600 bg-emerald-600 text-white";
      case "warning":
        return "border-amber-600 bg-amber-600 text-white";
      case "info":
        return "border-blue-600 bg-blue-600 text-white";
      default:
        return "border bg-background text-foreground shadow-lg";
    }
  };

  const getIcon = (variant?: ToastVariant) => {
    switch (variant) {
      case "destructive":
        return <AlertCircle className="h-5 w-5" />;
      case "success":
        return <CheckCircle2 className="h-5 w-5" />;
      case "warning":
        return <AlertTriangle className="h-5 w-5" />;
      case "info":
        return <Info className="h-5 w-5" />;
      default:
        return null;
    }
  };

  return (
    <div
      aria-live="polite"
      aria-atomic="true"
      className="fixed bottom-0 right-0 z-50 flex max-h-screen w-full flex-col-reverse p-4 sm:bottom-0 sm:right-0 sm:top-auto sm:flex-col md:max-w-[420px] gap-2 pointer-events-none"
    >
      {toasts.map((toast) => (
        <div
          key={toast.id}
          role="status"
          className={cn(
            "pointer-events-auto relative flex w-full items-center justify-between space-x-2 overflow-hidden rounded-md border p-4 shadow-lg transition-all animate-in slide-in-from-bottom-5",
            getVariantStyles(toast.variant)
          )}
        >
          <div className="flex items-start space-x-3">
            {getIcon(toast.variant)}
            <div className="grid gap-1">
              {toast.title && <div className="text-sm font-semibold">{toast.title}</div>}
              {toast.description && <div className="text-xs opacity-90">{toast.description}</div>}
            </div>
          </div>
          <button
            type="button"
            onClick={() => dismiss(toast.id)}
            aria-label="Close notification"
            className="rounded-md p-1 opacity-70 hover:opacity-100 focus:outline-none focus:ring-2 focus:ring-ring"
          >
            <X className="h-4 w-4" />
          </button>
        </div>
      ))}
    </div>
  );
}
