import { CheckCircle2, XCircle, AlertOctagon, WifiOff, Clock, Loader2, HelpCircle } from "lucide-react";
import { cn } from "@/lib/utils";

export type ByokValidationState =
  | "valid"
  | "invalid"
  | "provider_unavailable"
  | "network_error"
  | "rate_limited"
  | "validating"
  | "untested";

export interface ByokValidationBadgeProps {
  status: ByokValidationState | string;
  errorMessage?: string | null;
  className?: string;
  showIcon?: boolean;
}

export function ByokValidationBadge({
  status,
  errorMessage,
  className,
  showIcon = true,
}: ByokValidationBadgeProps) {
  const normalized = (status || "untested").toLowerCase().replace(/[\s-]/g, "_");

  switch (normalized) {
    case "valid":
      return (
        <span
          role="status"
          aria-label="Validation status: Valid"
          className={cn(
            "inline-flex items-center gap-1.5 px-2.5 py-0.5 rounded-full text-xs font-medium border bg-emerald-50 text-emerald-700 border-emerald-200 dark:bg-emerald-950/60 dark:text-emerald-300 dark:border-emerald-800",
            className
          )}
        >
          {showIcon && <CheckCircle2 className="h-3.5 w-3.5 text-emerald-600 dark:text-emerald-400" aria-hidden="true" />}
          <span>Valid</span>
        </span>
      );

    case "invalid":
      return (
        <span
          role="status"
          aria-label={`Validation status: Invalid${errorMessage ? ` - ${errorMessage}` : ""}`}
          title={errorMessage || "Invalid API key"}
          className={cn(
            "inline-flex items-center gap-1.5 px-2.5 py-0.5 rounded-full text-xs font-medium border bg-rose-50 text-rose-700 border-rose-200 dark:bg-rose-950/60 dark:text-rose-300 dark:border-rose-800",
            className
          )}
        >
          {showIcon && <XCircle className="h-3.5 w-3.5 text-rose-600 dark:text-rose-400" aria-hidden="true" />}
          <span>Invalid</span>
        </span>
      );

    case "provider_unavailable":
    case "503":
      return (
        <span
          role="status"
          aria-label="Validation status: Provider Unavailable (503)"
          title={errorMessage || "Upstream provider is temporarily unreachable or returned 503"}
          className={cn(
            "inline-flex items-center gap-1.5 px-2.5 py-0.5 rounded-full text-xs font-medium border bg-amber-50 text-amber-700 border-amber-200 dark:bg-amber-950/60 dark:text-amber-300 dark:border-amber-800",
            className
          )}
        >
          {showIcon && <AlertOctagon className="h-3.5 w-3.5 text-amber-600 dark:text-amber-400" aria-hidden="true" />}
          <span>Provider Unavailable</span>
        </span>
      );

    case "network_error":
    case "network":
      return (
        <span
          role="status"
          aria-label="Validation status: Network Error"
          title={errorMessage || "Client connection failed or network timed out"}
          className={cn(
            "inline-flex items-center gap-1.5 px-2.5 py-0.5 rounded-full text-xs font-medium border bg-slate-100 text-slate-700 border-slate-300 dark:bg-slate-800 dark:text-slate-300 dark:border-slate-700",
            className
          )}
        >
          {showIcon && <WifiOff className="h-3.5 w-3.5 text-slate-500 dark:text-slate-400" aria-hidden="true" />}
          <span>Network Error</span>
        </span>
      );

    case "rate_limited":
    case "429":
      return (
        <span
          role="status"
          aria-label="Validation status: Rate Limited (429)"
          title={errorMessage || "Rate limit exceeded on provider endpoint"}
          className={cn(
            "inline-flex items-center gap-1.5 px-2.5 py-0.5 rounded-full text-xs font-medium border bg-purple-50 text-purple-700 border-purple-200 dark:bg-purple-950/60 dark:text-purple-300 dark:border-purple-800",
            className
          )}
        >
          {showIcon && <Clock className="h-3.5 w-3.5 text-purple-600 dark:text-purple-400" aria-hidden="true" />}
          <span>Rate Limited</span>
        </span>
      );

    case "validating":
      return (
        <span
          role="status"
          aria-label="Validation status: Validating..."
          className={cn(
            "inline-flex items-center gap-1.5 px-2.5 py-0.5 rounded-full text-xs font-medium border bg-sky-50 text-sky-700 border-sky-200 dark:bg-sky-950/60 dark:text-sky-300 dark:border-sky-800",
            className
          )}
        >
          {showIcon && <Loader2 className="h-3.5 w-3.5 text-sky-600 dark:text-sky-400 animate-spin" aria-hidden="true" />}
          <span>Validating...</span>
        </span>
      );

    default:
      return (
        <span
          role="status"
          aria-label="Validation status: Untested"
          className={cn(
            "inline-flex items-center gap-1.5 px-2.5 py-0.5 rounded-full text-xs font-medium border bg-muted text-muted-foreground border-border",
            className
          )}
        >
          {showIcon && <HelpCircle className="h-3.5 w-3.5 text-muted-foreground" aria-hidden="true" />}
          <span>Untested</span>
        </span>
      );
  }
}
