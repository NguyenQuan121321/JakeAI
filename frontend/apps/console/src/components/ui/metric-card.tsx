import { TrendingUp, TrendingDown, Minus, type LucideIcon } from "lucide-react";
import { Card, CardContent } from "@/components/ui/card";
import { cn } from "@/lib/utils";

export interface MetricCardProps {
  title: string;
  value: string | number;
  change?: {
    value: string | number;
    trend: "up" | "down" | "neutral";
    label?: string;
  };
  icon?: LucideIcon;
  description?: string;
  className?: string;
}

export function MetricCard({
  title,
  value,
  change,
  icon: Icon,
  description,
  className,
}: MetricCardProps) {
  const getTrendIcon = () => {
    if (!change) return null;
    switch (change.trend) {
      case "up":
        return <TrendingUp className="h-3.5 w-3.5 text-emerald-500 shrink-0 mr-1" aria-hidden="true" />;
      case "down":
        return <TrendingDown className="h-3.5 w-3.5 text-rose-500 shrink-0 mr-1" aria-hidden="true" />;
      case "neutral":
      default:
        return <Minus className="h-3.5 w-3.5 text-muted-foreground shrink-0 mr-1" aria-hidden="true" />;
    }
  };

  const getTrendColor = () => {
    if (!change) return "";
    switch (change.trend) {
      case "up":
        return "text-emerald-600 dark:text-emerald-400";
      case "down":
        return "text-rose-600 dark:text-rose-400";
      case "neutral":
      default:
        return "text-muted-foreground";
    }
  };

  return (
    <Card className={cn("overflow-hidden transition-all hover:shadow-md", className)}>
      <CardContent className="p-6">
        <div className="flex items-center justify-between space-x-2">
          <p className="text-sm font-medium text-muted-foreground">{title}</p>
          {Icon && (
            <div className="flex h-8 w-8 items-center justify-center rounded-md bg-muted/60 text-muted-foreground">
              <Icon className="h-4 w-4" aria-hidden="true" />
            </div>
          )}
        </div>
        <div className="mt-2 flex items-baseline space-x-2">
          <div className="text-2xl font-bold tracking-tight text-foreground">{value}</div>
        </div>
        {(change || description) && (
          <div className="mt-2 flex items-center text-xs text-muted-foreground">
            {change && (
              <span className={cn("inline-flex items-center font-medium mr-2", getTrendColor())}>
                {getTrendIcon()}
                <span>{change.value}</span>
              </span>
            )}
            {change?.label && <span>{change.label}</span>}
            {!change?.label && description && <span>{description}</span>}
          </div>
        )}
      </CardContent>
    </Card>
  );
}
