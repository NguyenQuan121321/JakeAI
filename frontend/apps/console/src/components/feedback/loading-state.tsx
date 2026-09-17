import { Loader2 } from "lucide-react";
import { cn } from "@/lib/utils";
import { Skeleton } from "@/components/ui/skeleton";

export interface LoadingStateProps {
  message?: string;
  fullScreen?: boolean;
  variant?: "spinner" | "skeleton" | "card";
  className?: string;
}

export function LoadingState({
  message = "Loading console resource...",
  fullScreen = false,
  variant = "spinner",
  className,
}: LoadingStateProps) {
  if (variant === "skeleton") {
    return (
      <div
        role="status"
        aria-busy="true"
        aria-label={message}
        className={cn("space-y-4 p-6 w-full animate-pulse", className)}
      >
        <div className="flex items-center space-x-4">
          <Skeleton className="h-12 w-12 rounded-full" />
          <div className="space-y-2 flex-1">
            <Skeleton className="h-4 w-1/3" />
            <Skeleton className="h-3 w-1/2" />
          </div>
        </div>
        <div className="grid grid-cols-1 md:grid-cols-3 gap-4 pt-4">
          <Skeleton className="h-28 rounded-lg" />
          <Skeleton className="h-28 rounded-lg" />
          <Skeleton className="h-28 rounded-lg" />
        </div>
        <Skeleton className="h-64 w-full rounded-lg mt-6" />
        <span className="sr-only">{message}</span>
      </div>
    );
  }

  if (variant === "card") {
    return (
      <div
        role="status"
        aria-busy="true"
        aria-label={message}
        className={cn("rounded-lg border bg-card p-6 shadow-sm", className)}
      >
        <Skeleton className="h-5 w-1/3 mb-2" />
        <Skeleton className="h-3 w-2/3 mb-6" />
        <Skeleton className="h-36 w-full" />
        <span className="sr-only">{message}</span>
      </div>
    );
  }

  return (
    <div
      role="status"
      aria-busy="true"
      aria-label={message}
      className={cn(
        "flex flex-col items-center justify-center p-8 text-center",
        fullScreen ? "fixed inset-0 z-50 bg-background/80 backdrop-blur-sm" : "min-h-[300px]",
        className
      )}
    >
      <div className="flex h-12 w-12 items-center justify-center rounded-full bg-primary/10 text-primary mb-3">
        <Loader2 className="h-6 w-6 animate-spin" aria-hidden="true" />
      </div>
      <p className="text-sm font-medium text-foreground">{message}</p>
      <span className="sr-only">Please wait, loading data.</span>
    </div>
  );
}
