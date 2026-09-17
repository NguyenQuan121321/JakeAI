import * as React from "react";
import { Bell, CheckCircle2, AlertTriangle, Cpu, Coins, X } from "lucide-react";
import { Drawer } from "@/components/ui/drawer";
import { Badge } from "@/components/ui/badge";
import { Button } from "@/components/ui/button";

interface ActivityEvent {
  id: string;
  title: string;
  description: string;
  time: string;
  type: "success" | "warning" | "agent" | "finops";
  read: boolean;
}

const INITIAL_EVENTS: ActivityEvent[] = [
  {
    id: "act-1",
    title: "Orchestrator Run Completed",
    description: "Multi-agent coding task task-882 finished with 0 errors.",
    time: "4 mins ago",
    type: "success",
    read: false,
  },
  {
    id: "act-2",
    title: "Spend Ceiling Warning (80%)",
    description: "Anthropic Claude 3.5 Sonnet quota reached 82% of soft cap.",
    time: "18 mins ago",
    type: "finops",
    read: false,
  },
  {
    id: "act-3",
    title: "Vector Pipeline Indexed",
    description: "45 documentation chunks vectorized and committed to pgvector.",
    time: "1 hour ago",
    type: "agent",
    read: true,
  },
  {
    id: "act-4",
    title: "Provider Latency Spike",
    description: "OpenAI GPT-4o p95 latency degraded to 1420ms for 2 minutes.",
    time: "3 hours ago",
    type: "warning",
    read: true,
  },
];

export function NotificationActivity() {
  const [isOpen, setIsOpen] = React.useState(false);
  const [events, setEvents] = React.useState<ActivityEvent[]>(INITIAL_EVENTS);

  const unreadCount = events.filter((e) => !e.read).length;

  const markAllAsRead = () => {
    setEvents((prev) => prev.map((e) => ({ ...e, read: true })));
  };

  const clearEvent = (id: string) => {
    setEvents((prev) => prev.filter((e) => e.id !== id));
  };

  const getEventIcon = (type: ActivityEvent["type"]) => {
    switch (type) {
      case "success":
        return <CheckCircle2 className="h-4 w-4 text-emerald-500" />;
      case "finops":
        return <Coins className="h-4 w-4 text-amber-500" />;
      case "warning":
        return <AlertTriangle className="h-4 w-4 text-orange-500" />;
      case "agent":
      default:
        return <Cpu className="h-4 w-4 text-primary" />;
    }
  };

  return (
    <>
      <button
        type="button"
        onClick={() => setIsOpen(true)}
        aria-label={`Open notifications (${unreadCount} unread)`}
        className="relative rounded-full p-2 text-muted-foreground hover:bg-accent hover:text-accent-foreground focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-ring transition-colors"
      >
        <Bell className="h-5 w-5" />
        {unreadCount > 0 && (
          <span className="absolute top-1.5 right-1.5 flex h-2 w-2">
            <span className="animate-ping absolute inline-flex h-full w-full rounded-full bg-primary opacity-75" />
            <span className="relative inline-flex rounded-full h-2 w-2 bg-primary" />
          </span>
        )}
      </button>

      <Drawer
        open={isOpen}
        onOpenChange={setIsOpen}
        position="right"
        title="Activity & Notifications"
        description="Real-time telemetry and platform event stream"
      >
        <div className="flex flex-col h-full">
          <div className="flex items-center justify-between py-2 border-b">
            <span className="text-xs font-semibold text-muted-foreground">
              {unreadCount} UNREAD ALERTS
            </span>
            {unreadCount > 0 && (
              <Button variant="ghost" size="sm" onClick={markAllAsRead} className="h-7 text-xs">
                Mark all read
              </Button>
            )}
          </div>

          <div className="flex-1 overflow-y-auto divide-y mt-2">
            {events.length === 0 ? (
              <div className="py-12 text-center text-sm text-muted-foreground">
                No new activity or notifications.
              </div>
            ) : (
              events.map((evt) => (
                <div
                  key={evt.id}
                  className={`py-3 px-1 flex items-start justify-between space-x-3 transition-colors ${
                    !evt.read ? "bg-accent/20" : ""
                  }`}
                >
                  <div className="flex items-start space-x-2.5">
                    <div className="mt-0.5">{getEventIcon(evt.type)}</div>
                    <div>
                      <div className="flex items-center space-x-2">
                        <p className="text-xs font-semibold text-foreground">{evt.title}</p>
                        {!evt.read && (
                          <Badge variant="default" className="text-[9px] py-0 px-1 leading-normal">
                            NEW
                          </Badge>
                        )}
                      </div>
                      <p className="text-xs text-muted-foreground mt-0.5">{evt.description}</p>
                      <span className="text-[10px] text-muted-foreground/80 mt-1 block">
                        {evt.time}
                      </span>
                    </div>
                  </div>
                  <button
                    type="button"
                    onClick={() => clearEvent(evt.id)}
                    aria-label="Dismiss alert"
                    className="text-muted-foreground/60 hover:text-foreground p-0.5 rounded"
                  >
                    <X className="h-3.5 w-3.5" />
                  </button>
                </div>
              ))
            )}
          </div>
        </div>
      </Drawer>
    </>
  );
}
