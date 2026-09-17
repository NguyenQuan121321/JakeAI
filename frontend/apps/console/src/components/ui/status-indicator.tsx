import { getStatusDefinition } from "@/lib/status";
import type { SemanticStatus } from "@/types/status";
import { cn } from "@/lib/utils";

export interface StatusIndicatorProps {
  status: SemanticStatus | string;
  variant?: "badge" | "dot" | "pill" | "inline";
  showIcon?: boolean;
  showLabel?: boolean;
  customLabel?: string;
  className?: string;
}

export function StatusIndicator({
  status,
  variant = "badge",
  showIcon = true,
  showLabel = true,
  customLabel,
  className,
}: StatusIndicatorProps) {
  const def = getStatusDefinition(status);
  const Icon = def.icon;
  const label = customLabel || def.label;

  if (variant === "dot") {
    return (
      <span
        role="status"
        aria-label={def.ariaLabel}
        className={cn("inline-flex items-center space-x-2", className)}
      >
        <span className={cn("h-2.5 w-2.5 rounded-full shrink-0", def.dotClasses)} aria-hidden="true" />
        {showLabel && <span className="text-xs font-medium text-foreground">{label}</span>}
      </span>
    );
  }

  if (variant === "inline") {
    return (
      <span
        role="status"
        aria-label={def.ariaLabel}
        className={cn("inline-flex items-center space-x-1.5 text-xs font-medium", className)}
      >
        {showIcon && <Icon className={cn("h-3.5 w-3.5 shrink-0", def.iconClasses)} aria-hidden="true" />}
        {showLabel && <span>{label}</span>}
      </span>
    );
  }

  if (variant === "pill") {
    return (
      <span
        role="status"
        aria-label={def.ariaLabel}
        className={cn(
          "inline-flex items-center rounded-full border px-2.5 py-0.5 text-xs font-medium space-x-1.5",
          def.badgeClasses,
          className
        )}
      >
        <span className={cn("h-1.5 w-1.5 rounded-full", def.dotClasses)} aria-hidden="true" />
        {showLabel && <span>{label}</span>}
      </span>
    );
  }

  // Default: 'badge'
  return (
    <span
      role="status"
      aria-label={def.ariaLabel}
      className={cn(
        "inline-flex items-center rounded-md border px-2.5 py-1 text-xs font-medium space-x-1.5 shadow-sm",
        def.badgeClasses,
        className
      )}
    >
      {showIcon && <Icon className={cn("h-3.5 w-3.5 shrink-0", def.iconClasses)} aria-hidden="true" />}
      {showLabel && <span>{label}</span>}
    </span>
  );
}
