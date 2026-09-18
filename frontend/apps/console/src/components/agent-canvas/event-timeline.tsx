import * as React from "react";
import {
  ChevronUp,
  ChevronDown,
  Activity,
  Clock,
  CheckCircle2,
  AlertCircle,
  AlertTriangle,
  RotateCw,
  Search,
  Trash2,
} from "lucide-react";
import { Button } from "@/components/ui/button";
import { Badge } from "@/components/ui/badge";
import { Input } from "@/components/ui/input";
import { cn } from "@/lib/utils";
import type { TimelineEvent, CanvasNodeStatus } from "@/types/agent-graph";

interface EventTimelineProps {
  events: TimelineEvent[];
  isExpanded: boolean;
  onToggleExpand: () => void;
  onSelectEventNode?: (nodeId: string) => void;
  onClearEvents?: () => void;
}

const EVENT_STATUS_BADGES: Record<CanvasNodeStatus, { badge: string; icon: React.ElementType }> = {
  idle: { badge: "bg-muted text-muted-foreground", icon: Clock },
  queued: { badge: "bg-amber-500/10 text-amber-600 dark:text-amber-400 border-amber-500/30", icon: Clock },
  running: { badge: "bg-primary/20 text-primary border-primary/40 animate-pulse", icon: RotateCw },
  waiting_approval: { badge: "bg-rose-500/20 text-rose-600 dark:text-rose-400 border-rose-500/50", icon: AlertTriangle },
  completed: { badge: "bg-emerald-500/10 text-emerald-600 dark:text-emerald-400 border-emerald-500/30", icon: CheckCircle2 },
  failed: { badge: "bg-destructive/15 text-destructive border-destructive/30", icon: AlertCircle },
  cancelled: { badge: "bg-zinc-500/15 text-zinc-500 border-zinc-500/30", icon: AlertCircle },
};

export const EventTimeline: React.FC<EventTimelineProps> = ({
  events,
  isExpanded,
  onToggleExpand,
  onSelectEventNode,
  onClearEvents,
}) => {
  const [filterType, setFilterType] = React.useState<string>("all");
  const [search, setSearch] = React.useState<string>("");
  const endRef = React.useRef<HTMLDivElement>(null);

  React.useEffect(() => {
    if (isExpanded) {
      endRef.current?.scrollIntoView({ behavior: "smooth" });
    }
  }, [events.length, isExpanded]);

  const filteredEvents = React.useMemo(() => {
    return events.filter((ev) => {
      const matchSearch =
        ev.title.toLowerCase().includes(search.toLowerCase()) ||
        (ev.description && ev.description.toLowerCase().includes(search.toLowerCase())) ||
        ev.eventType.toLowerCase().includes(search.toLowerCase());

      if (!matchSearch) return false;

      if (filterType === "all") return true;
      if (filterType === "steps") return ev.eventType.includes("step");
      if (filterType === "tools") return ev.eventType.includes("tool") || ev.eventType.includes("observation");
      if (filterType === "approvals") return ev.eventType.includes("approval");
      if (filterType === "verifications") return ev.eventType.includes("verification");
      if (filterType === "terminal") {
        return ["completed", "failed", "cancelled", "rejected", "timeout"].includes(ev.eventType);
      }
      return true;
    });
  }, [events, filterType, search]);

  return (
    <div
      className={cn(
        "flex flex-col bg-card border-t transition-all duration-200 select-none z-10",
        isExpanded ? "h-64" : "h-10"
      )}
      data-testid="event-timeline-panel"
    >
      {/* Top Bar */}
      <div className="flex items-center justify-between px-4 py-2 border-b h-10 flex-shrink-0 bg-card">
        <div className="flex items-center gap-2.5">
          <Activity className="h-4 w-4 text-primary" />
          <span className="text-xs font-bold uppercase tracking-wider">
            Execution Trace & Event Timeline
          </span>
          <Badge variant="outline" className="text-[10px] font-mono h-5">
            {events.length} events
          </Badge>
        </div>

        <div className="flex items-center gap-2">
          {isExpanded && (
            <>
              {/* Filter Pills */}
              <div className="flex items-center gap-1 text-[10px]">
                {["all", "steps", "tools", "approvals", "verifications", "terminal"].map((f) => (
                  <button
                    key={f}
                    onClick={() => setFilterType(f)}
                    className={cn(
                      "px-2 py-0.5 rounded capitalize transition-colors",
                      filterType === f
                        ? "bg-primary text-primary-foreground font-medium"
                        : "bg-muted text-muted-foreground hover:bg-accent"
                    )}
                  >
                    {f}
                  </button>
                ))}
              </div>

              {/* Quick Search */}
              <div className="relative w-36">
                <Search className="absolute left-2 top-2 h-3 w-3 text-muted-foreground" />
                <Input
                  placeholder="Filter events..."
                  value={search}
                  onChange={(e) => setSearch(e.target.value)}
                  className="pl-7 h-6 text-[11px] bg-background"
                />
              </div>

              {onClearEvents && (
                <Button
                  variant="ghost"
                  size="icon"
                  className="h-6 w-6 text-muted-foreground hover:text-foreground"
                  onClick={onClearEvents}
                  title="Clear trace"
                >
                  <Trash2 className="h-3.5 w-3.5" />
                </Button>
              )}
            </>
          )}

          <Button
            variant="ghost"
            size="sm"
            className="h-6 px-2 text-xs flex items-center gap-1 text-muted-foreground hover:text-foreground"
            onClick={onToggleExpand}
            aria-label={isExpanded ? "Collapse timeline" : "Expand timeline"}
          >
            {isExpanded ? (
              <>
                <ChevronDown className="h-3.5 w-3.5" /> Collapse
              </>
            ) : (
              <>
                <ChevronUp className="h-3.5 w-3.5" /> Expand
              </>
            )}
          </Button>
        </div>
      </div>

      {/* Events Body */}
      {isExpanded && (
        <div className="flex-1 overflow-y-auto p-3 space-y-1.5 font-mono text-xs">
          {filteredEvents.length === 0 ? (
            <div className="text-center py-10 text-muted-foreground text-xs">
              No events recorded yet. Start a run to stream execution events in real time.
            </div>
          ) : (
            filteredEvents.map((ev) => {
              const status = ev.status || "idle";
              const badgeInfo = EVENT_STATUS_BADGES[status] || EVENT_STATUS_BADGES.idle;
              const StatusIcon = badgeInfo.icon;
              const timeStr = new Date(ev.timestamp).toLocaleTimeString();

              return (
                <div
                  key={ev.id}
                  onClick={() => ev.nodeId && onSelectEventNode?.(ev.nodeId)}
                  className={cn(
                    "flex items-start gap-3 p-2 rounded-lg border bg-background/60 hover:bg-accent/40 transition-colors text-[11px]",
                    ev.nodeId && "cursor-pointer"
                  )}
                  data-testid={`timeline-event-${ev.eventType}`}
                >
                  {/* Timestamp */}
                  <span className="text-[10px] text-muted-foreground flex-shrink-0 pt-0.5">
                    {timeStr}
                  </span>

                  {/* Status icon / badge */}
                  <div className="flex-shrink-0 mt-0.5">
                    <StatusIcon className="h-3.5 w-3.5 text-muted-foreground" />
                  </div>

                  {/* Event Content */}
                  <div className="flex-1 min-w-0">
                    <div className="flex items-center gap-2">
                      <span className="font-semibold text-foreground truncate">
                        {ev.title}
                      </span>
                      <span className="text-[9px] text-muted-foreground px-1.5 py-0.2 rounded bg-muted">
                        {ev.eventType}
                      </span>
                      {ev.durationMs !== undefined && (
                        <span className="text-[10px] text-muted-foreground flex items-center gap-0.5">
                          <Clock className="h-2.5 w-2.5" />
                          {ev.durationMs}ms
                        </span>
                      )}
                    </div>
                    {ev.description && (
                      <p className="text-[11px] text-muted-foreground truncate mt-0.5">
                        {ev.description}
                      </p>
                    )}
                  </div>

                  {/* Node reference */}
                  {ev.nodeId && (
                    <span className="text-[9px] text-primary/80 font-semibold px-1.5 py-0.5 rounded bg-primary/10 flex-shrink-0">
                      focus {ev.nodeId}
                    </span>
                  )}
                </div>
              );
            })
          )}
          <div ref={endRef} />
        </div>
      )}
    </div>
  );
};
