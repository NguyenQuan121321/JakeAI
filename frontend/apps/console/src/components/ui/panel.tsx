import * as React from "react";
import { ChevronDown, ChevronUp } from "lucide-react";
import { cn } from "@/lib/utils";

export interface PanelProps {
  title: string;
  description?: string;
  badge?: React.ReactNode;
  actions?: React.ReactNode;
  collapsible?: boolean;
  defaultCollapsed?: boolean;
  children: React.ReactNode;
  className?: string;
}

export function Panel({
  title,
  description,
  badge,
  actions,
  collapsible = false,
  defaultCollapsed = false,
  children,
  className,
}: PanelProps) {
  const [isCollapsed, setIsCollapsed] = React.useState(defaultCollapsed);

  return (
    <div className={cn("rounded-lg border bg-card text-card-foreground shadow-sm", className)}>
      <div className="flex items-center justify-between p-4 border-b">
        <div className="flex items-center space-x-3">
          {collapsible && (
            <button
              type="button"
              onClick={() => setIsCollapsed((prev) => !prev)}
              aria-expanded={!isCollapsed}
              aria-label={isCollapsed ? `Expand ${title}` : `Collapse ${title}`}
              className="text-muted-foreground hover:text-foreground focus:outline-none"
            >
              {isCollapsed ? (
                <ChevronDown className="h-4 w-4" />
              ) : (
                <ChevronUp className="h-4 w-4" />
              )}
            </button>
          )}
          <div>
            <div className="flex items-center space-x-2">
              <h4 className="text-sm font-semibold tracking-tight">{title}</h4>
              {badge}
            </div>
            {description && <p className="text-xs text-muted-foreground mt-0.5">{description}</p>}
          </div>
        </div>
        {actions && <div className="flex items-center space-x-2">{actions}</div>}
      </div>
      {!isCollapsed && <div className="p-4">{children}</div>}
    </div>
  );
}
