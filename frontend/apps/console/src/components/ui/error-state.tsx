import * as React from "react";
import { AlertCircle, RotateCcw, ChevronDown, ChevronUp, Copy, Check } from "lucide-react";
import { Button } from "@/components/ui/button";
import { cn } from "@/lib/utils";
import { ApiError } from "@/api/client/api-error";

export interface ErrorStateProps {
  title?: string;
  message?: string;
  error?: Error | unknown;
  correlationId?: string;
  requestId?: string;
  onRetry?: () => void;
  className?: string;
}

export function ErrorState({
  title = "Something went wrong",
  message = "An unexpected error occurred while processing this operation.",
  error,
  correlationId: propCorrelationId,
  requestId: propRequestId,
  onRetry,
  className,
}: ErrorStateProps) {
  const [showDetails, setShowDetails] = React.useState(false);
  const [copied, setCopied] = React.useState(false);

  // Extract correlation ID defensively from error if not explicitly supplied
  const effectiveCorrelationId = React.useMemo(() => {
    if (propCorrelationId) return propCorrelationId;
    if (error instanceof ApiError) {
      return error.correlationId || error.requestId;
    }
    if (error && typeof error === "object" && "correlationId" in error) {
      return String((error as { correlationId: unknown }).correlationId);
    }
    return propRequestId;
  }, [propCorrelationId, propRequestId, error]);

  const handleCopyCorrelationId = () => {
    if (!effectiveCorrelationId) return;
    navigator.clipboard.writeText(effectiveCorrelationId);
    setCopied(true);
    setTimeout(() => setCopied(false), 2000);
  };

  const errorString = React.useMemo(() => {
    if (!error) return null;
    if (error instanceof Error) return `${error.name}: ${error.message}\n${error.stack || ""}`;
    if (typeof error === "string") return error;
    try {
      return JSON.stringify(error, null, 2);
    } catch {
      return String(error);
    }
  }, [error]);

  return (
    <div
      role="alert"
      className={cn(
        "flex min-h-[300px] flex-col items-center justify-center rounded-lg border border-destructive/30 bg-destructive/5 p-8 text-center",
        className
      )}
    >
      <div className="flex h-16 w-16 items-center justify-center rounded-full bg-destructive/10 text-destructive mb-4">
        <AlertCircle className="h-8 w-8" aria-hidden="true" />
      </div>
      <h3 className="text-base font-semibold text-destructive">{title}</h3>
      <p className="mt-1.5 max-w-md text-sm text-muted-foreground">{message}</p>

      {effectiveCorrelationId && (
        <div className="mt-3 flex items-center gap-2 rounded-md bg-muted/80 border px-3 py-1.5 text-xs">
          <span className="text-muted-foreground">Support Correlation ID:</span>
          <code className="font-mono font-semibold text-foreground">{effectiveCorrelationId}</code>
          <button
            type="button"
            onClick={handleCopyCorrelationId}
            className="ml-1 text-muted-foreground hover:text-foreground transition-colors"
            title="Copy correlation ID"
            aria-label="Copy correlation ID"
          >
            {copied ? <Check className="h-3.5 w-3.5 text-emerald-500" /> : <Copy className="h-3.5 w-3.5" />}
          </button>
        </div>
      )}

      {onRetry && (
        <div className="mt-6">
          <Button
            variant="outline"
            onClick={onRetry}
            leftIcon={<RotateCcw className="h-4 w-4" />}
          >
            Retry Operation
          </Button>
        </div>
      )}

      {errorString && (
        <div className="mt-6 w-full max-w-lg text-left">
          <button
            type="button"
            onClick={() => setShowDetails((prev) => !prev)}
            className="flex items-center text-xs text-muted-foreground hover:text-foreground font-medium mb-2 focus:outline-none"
          >
            <span>{showDetails ? "Hide technical details" : "Show technical details"}</span>
            {showDetails ? (
              <ChevronUp className="h-3.5 w-3.5 ml-1" />
            ) : (
              <ChevronDown className="h-3.5 w-3.5 ml-1" />
            )}
          </button>
          {showDetails && (
            <pre className="max-h-48 overflow-auto rounded bg-muted p-3 text-xs font-mono text-muted-foreground whitespace-pre-wrap break-all border">
              {errorString}
            </pre>
          )}
        </div>
      )}
    </div>
  );
}
