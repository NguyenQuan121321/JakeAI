import * as React from "react";
import { cn } from "@/lib/utils";

export interface ChartDataItem {
  label: string;
  value: number;
  color?: string;
  secondaryText?: string;
}

const DEFAULT_CHART_COLORS = [
  "#3b82f6", // blue-500
  "#8b5cf6", // violet-500
  "#10b981", // emerald-500
  "#f59e0b", // amber-500
  "#06b6d4", // cyan-500
  "#ec4899", // pink-500
  "#6366f1", // indigo-500
  "#14b8a6", // teal-500
];

/**
 * Donut / Ring SVG Chart
 */
export function DonutChart({
  data,
  totalLabel,
  totalValue,
  size = 180,
  strokeWidth = 24,
  className,
}: {
  data: ChartDataItem[];
  totalLabel?: string;
  totalValue?: string | number;
  size?: number;
  strokeWidth?: number;
  className?: string;
}) {
  const [hoveredIdx, setHoveredIdx] = React.useState<number | null>(null);

  const radius = (size - strokeWidth) / 2;
  const circumference = 2 * Math.PI * radius;

  const total = React.useMemo(() => {
    const sum = data.reduce((acc, item) => acc + item.value, 0);
    return sum > 0 ? sum : 1;
  }, [data]);

  let accumulatedPercent = 0;

  return (
    <div className={cn("flex flex-col sm:flex-row items-center gap-6", className)}>
      <div className="relative flex-shrink-0" style={{ width: size, height: size }}>
        <svg
          width={size}
          height={size}
          viewBox={`0 0 ${size} ${size}`}
          className="transform -rotate-90"
          role="img"
          aria-label="Distribution donut chart"
        >
          {/* Background track */}
          <circle
            cx={size / 2}
            cy={size / 2}
            r={radius}
            fill="transparent"
            stroke="currentColor"
            strokeWidth={strokeWidth}
            className="text-muted/40"
          />

          {data.map((item, idx) => {
            const ratio = item.value / total;
            const strokeDasharray = `${ratio * circumference} ${circumference}`;
            const strokeDashoffset = -accumulatedPercent * circumference;
            accumulatedPercent += ratio;

            const color = item.color || DEFAULT_CHART_COLORS[idx % DEFAULT_CHART_COLORS.length];
            const isHovered = hoveredIdx === idx;

            return (
              <circle
                key={item.label}
                cx={size / 2}
                cy={size / 2}
                r={radius}
                fill="transparent"
                stroke={color}
                strokeWidth={isHovered ? strokeWidth + 3 : strokeWidth}
                strokeDasharray={strokeDasharray}
                strokeDashoffset={strokeDashoffset}
                strokeLinecap="round"
                className="transition-all duration-200 cursor-pointer"
                onMouseEnter={() => setHoveredIdx(idx)}
                onMouseLeave={() => setHoveredIdx(null)}
              >
                <title>{`${item.label}: ${item.value} (${((item.value / total) * 100).toFixed(1)}%)`}</title>
              </circle>
            );
          })}
        </svg>

        {/* Center label */}
        <div className="absolute inset-0 flex flex-col items-center justify-center text-center pointer-events-none">
          {hoveredIdx !== null ? (
            <>
              <span className="text-xs text-muted-foreground font-medium truncate max-w-[90px]">
                {data[hoveredIdx].label}
              </span>
              <span className="text-base font-bold text-foreground">
                {((data[hoveredIdx].value / total) * 100).toFixed(1)}%
              </span>
            </>
          ) : (
            <>
              {totalValue !== undefined && (
                <span className="text-lg font-bold text-foreground tracking-tight">
                  {totalValue}
                </span>
              )}
              {totalLabel && (
                <span className="text-[11px] text-muted-foreground font-medium">
                  {totalLabel}
                </span>
              )}
            </>
          )}
        </div>
      </div>

      {/* Legend */}
      <div className="flex-1 w-full space-y-2">
        {data.map((item, idx) => {
          const color = item.color || DEFAULT_CHART_COLORS[idx % DEFAULT_CHART_COLORS.length];
          const pct = ((item.value / total) * 100).toFixed(1);
          const isHovered = hoveredIdx === idx;

          return (
            <div
              key={item.label}
              className={cn(
                "flex items-center justify-between text-xs py-1 px-2 rounded cursor-pointer transition-colors",
                isHovered ? "bg-muted" : "hover:bg-muted/50"
              )}
              onMouseEnter={() => setHoveredIdx(idx)}
              onMouseLeave={() => setHoveredIdx(null)}
            >
              <div className="flex items-center space-x-2 min-w-0">
                <span
                  className="h-2.5 w-2.5 rounded-full flex-shrink-0"
                  style={{ backgroundColor: color }}
                  aria-hidden="true"
                />
                <span className="font-medium text-foreground truncate">{item.label}</span>
              </div>
              <div className="flex items-center space-x-2 flex-shrink-0 ml-2">
                {item.secondaryText && (
                  <span className="text-muted-foreground font-mono">{item.secondaryText}</span>
                )}
                <span className="font-semibold text-foreground font-mono">{pct}%</span>
              </div>
            </div>
          );
        })}
      </div>
    </div>
  );
}

/**
 * Horizontal Proportion / Stacked Bar Chart
 */
export function HorizontalBarChart({
  items,
  showLabels = true,
  className,
}: {
  items: ChartDataItem[];
  showLabels?: boolean;
  className?: string;
}) {
  const total = items.reduce((acc, item) => acc + item.value, 0) || 1;

  return (
    <div className={cn("space-y-3", className)}>
      {/* Stacked Progress Bar */}
      <div
        className="h-3 w-full rounded-full bg-muted/60 overflow-hidden flex"
        role="progressbar"
        aria-label="Proportion breakdown"
      >
        {items.map((item, idx) => {
          const ratio = (item.value / total) * 100;
          if (ratio <= 0) return null;
          const color = item.color || DEFAULT_CHART_COLORS[idx % DEFAULT_CHART_COLORS.length];

          return (
            <div
              key={item.label}
              style={{ width: `${ratio}%`, backgroundColor: color }}
              className="h-full transition-all duration-300 relative group"
              title={`${item.label}: ${item.value} (${ratio.toFixed(1)}%)`}
            />
          );
        })}
      </div>

      {/* Item details list */}
      {showLabels && (
        <div className="grid grid-cols-1 sm:grid-cols-2 gap-2 text-xs">
          {items.map((item, idx) => {
            const color = item.color || DEFAULT_CHART_COLORS[idx % DEFAULT_CHART_COLORS.length];
            const pct = ((item.value / total) * 100).toFixed(1);

            return (
              <div key={item.label} className="flex items-center justify-between p-1.5 rounded bg-muted/30">
                <div className="flex items-center space-x-2 min-w-0">
                  <span
                    className="h-2 w-2 rounded-full flex-shrink-0"
                    style={{ backgroundColor: color }}
                  />
                  <span className="text-muted-foreground truncate">{item.label}</span>
                </div>
                <div className="flex items-center space-x-1.5 flex-shrink-0 ml-2 font-mono">
                  {item.secondaryText && (
                    <span className="text-muted-foreground">{item.secondaryText}</span>
                  )}
                  <span className="font-semibold text-foreground">{pct}%</span>
                </div>
              </div>
            );
          })}
        </div>
      )}
    </div>
  );
}

/**
 * Metric Progress Gauge (showing current vs warning vs limit)
 */
export function MetricGauge({
  value,
  limit,
  warningThreshold = 0.8,
  label,
  valueText,
  limitText,
  className,
}: {
  value: number;
  limit: number;
  warningThreshold?: number;
  label?: string;
  valueText?: string;
  limitText?: string;
  className?: string;
}) {
  const percentage = limit > 0 ? Math.min(100, Math.max(0, (value / limit) * 100)) : 0;
  const isSuspended = percentage >= 100;
  const isWarning = percentage >= warningThreshold * 100 && !isSuspended;

  const barColor = isSuspended
    ? "bg-destructive"
    : isWarning
    ? "bg-amber-500"
    : "bg-primary";

  return (
    <div className={cn("space-y-1.5", className)}>
      <div className="flex justify-between items-center text-xs">
        <span className="font-medium text-foreground">{label}</span>
        <div className="space-x-1 font-mono">
          <span className="font-bold text-foreground">{valueText || value}</span>
          <span className="text-muted-foreground">/ {limitText || limit}</span>
          <span
            className={cn(
              "ml-1.5 px-1.5 py-0.5 rounded text-[10px] font-semibold",
              isSuspended
                ? "bg-destructive/15 text-destructive"
                : isWarning
                ? "bg-amber-500/15 text-amber-600 dark:text-amber-400"
                : "bg-muted text-muted-foreground"
            )}
          >
            {percentage.toFixed(1)}%
          </span>
        </div>
      </div>
      <div className="relative h-2 w-full rounded-full bg-muted overflow-hidden">
        {/* Soft warning marker */}
        <div
          className="absolute top-0 bottom-0 w-0.5 bg-foreground/30 z-10"
          style={{ left: `${warningThreshold * 100}%` }}
          title={`Warning threshold (${(warningThreshold * 100).toFixed(0)}%)`}
        />
        <div
          className={cn("h-full rounded-full transition-all duration-500", barColor)}
          style={{ width: `${percentage}%` }}
        />
      </div>
    </div>
  );
}
