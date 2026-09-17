import * as React from "react";
import { NavLink, useLocation } from "react-router-dom";
import {
  LayoutDashboard,
  Bot,
  Layers,
  Database,
  KeyRound,
  Coins,
  BarChart3,
  ShieldAlert,
  Settings,
  ChevronLeft,
  ChevronRight,
  Sparkles,
} from "lucide-react";
import { useAuth } from "@/context/auth-context";
import { Tooltip } from "@/components/ui/tooltip";
import { cn } from "@/lib/utils";
import type { NavSection } from "@/types/navigation";

const NAVIGATION_SECTIONS: NavSection[] = [
  {
    title: "Workspace",
    items: [
      {
        title: "Overview",
        href: "/workspace",
        icon: LayoutDashboard,
      },
    ],
  },
  {
    title: "Agents",
    items: [
      {
        title: "Agent Platform",
        href: "/agent",
        icon: Bot,
      },
      {
        title: "Execution Runs",
        href: "/agent/runs",
        icon: Layers,
      },
    ],
  },
  {
    title: "RAG",
    items: [
      {
        title: "Knowledge Base",
        href: "/rag",
        icon: Database,
      },
    ],
  },
  {
    title: "Providers",
    items: [
      {
        title: "BYOK & Gateways",
        href: "/providers",
        icon: KeyRound,
      },
    ],
  },
  {
    title: "FinOps",
    items: [
      {
        title: "Token Accounting",
        href: "/finops",
        icon: Coins,
      },
    ],
  },
  {
    title: "Analytics",
    items: [
      {
        title: "Telemetry & SLOs",
        href: "/analytics",
        icon: BarChart3,
      },
    ],
  },
  {
    title: "Administration",
    roles: ["admin", "tenant_admin"],
    items: [
      {
        title: "Tenants & RBAC",
        href: "/admin",
        icon: ShieldAlert,
        roles: ["admin", "tenant_admin"],
      },
    ],
  },
];

export function Sidebar({
  isCollapsed,
  setIsCollapsed,
  onNavigate,
}: {
  isCollapsed: boolean;
  setIsCollapsed?: (collapsed: boolean) => void;
  onNavigate?: () => void;
}) {
  const { hasRole, hasPermission } = useAuth();
  const location = useLocation();

  // Filter sections and items based on active authorization context
  const filteredSections = React.useMemo(() => {
    return NAVIGATION_SECTIONS.map((section) => {
      // Check section-level roles
      if (section.roles && !hasRole(section.roles)) return null;
      if (section.permissions && !hasPermission(section.permissions)) return null;

      // Filter child items
      const items = section.items.filter((item) => {
        if (item.roles && !hasRole(item.roles)) return false;
        if (item.permissions && !hasPermission(item.permissions)) return false;
        return true;
      });

      if (items.length === 0) return null;
      return { ...section, items };
    }).filter(Boolean) as NavSection[];
  }, [hasRole, hasPermission]);

  return (
    <aside
      role="navigation"
      aria-label="Main navigation"
      className={cn(
        "relative flex flex-col border-r bg-card/60 backdrop-blur-md transition-all duration-300 select-none z-30 h-full",
        isCollapsed ? "w-16" : "w-64"
      )}
    >
      {/* Brand Header */}
      <div className="flex h-16 items-center justify-between border-b px-4">
        <NavLink
          to="/workspace"
          onClick={onNavigate}
          className="flex items-center space-x-2.5 focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-ring rounded-md"
        >
          <div className="flex h-9 w-9 shrink-0 items-center justify-center rounded-lg bg-primary text-primary-foreground shadow-sm">
            <Sparkles className="h-5 w-5" />
          </div>
          {!isCollapsed && (
            <div className="flex flex-col">
              <span className="font-bold text-sm tracking-tight text-foreground">JakeAI</span>
              <span className="text-[10px] uppercase font-semibold text-primary tracking-wider">
                Enterprise Layer
              </span>
            </div>
          )}
        </NavLink>

        {setIsCollapsed && (
          <button
            type="button"
            onClick={() => setIsCollapsed(!isCollapsed)}
            aria-label={isCollapsed ? "Expand sidebar" : "Collapse sidebar"}
            className="hidden md:flex h-6 w-6 items-center justify-center rounded-md border text-muted-foreground hover:bg-accent hover:text-accent-foreground focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-ring"
          >
            {isCollapsed ? <ChevronRight className="h-3.5 w-3.5" /> : <ChevronLeft className="h-3.5 w-3.5" />}
          </button>
        )}
      </div>

      {/* Navigation Sections */}
      <div className="flex-1 overflow-y-auto py-4 px-3 space-y-6">
        {filteredSections.map((section) => (
          <div key={section.title} className="space-y-1">
            {!isCollapsed && (
              <h3 className="px-3 text-[10px] font-bold uppercase tracking-wider text-muted-foreground/70 mb-2">
                {section.title}
              </h3>
            )}
            <ul className="space-y-1">
              {section.items.map((item) => {
                const Icon = item.icon;
                const isActive =
                  item.href === "/"
                    ? location.pathname === "/"
                    : location.pathname.startsWith(item.href);

                const linkContent = (
                  <NavLink
                    to={item.href}
                    onClick={onNavigate}
                    aria-current={isActive ? "page" : undefined}
                    className={cn(
                      "flex items-center rounded-md px-3 py-2 text-sm font-medium transition-colors focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-ring",
                      isActive
                        ? "bg-primary text-primary-foreground shadow-sm"
                        : "text-muted-foreground hover:bg-accent hover:text-foreground",
                      isCollapsed && "justify-center px-0"
                    )}
                  >
                    <Icon className={cn("h-4 w-4 shrink-0", !isCollapsed && "mr-3")} />
                    {!isCollapsed && <span>{item.title}</span>}
                  </NavLink>
                );

                return (
                  <li key={item.href}>
                    {isCollapsed ? (
                      <Tooltip content={item.title} position="right">
                        {linkContent}
                      </Tooltip>
                    ) : (
                      linkContent
                    )}
                  </li>
                );
              })}
            </ul>
          </div>
        ))}
      </div>

      {/* Bottom Settings Link */}
      <div className="border-t p-3 space-y-1">
        {isCollapsed ? (
          <Tooltip content="Platform Settings" position="right">
            <NavLink
              to="/settings"
              onClick={onNavigate}
              aria-label="Platform Settings"
              className={cn(
                "flex h-9 w-9 items-center justify-center rounded-md text-muted-foreground hover:bg-accent hover:text-foreground focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-ring mx-auto",
                location.pathname === "/settings" && "bg-primary text-primary-foreground"
              )}
            >
              <Settings className="h-4 w-4" />
            </NavLink>
          </Tooltip>
        ) : (
          <NavLink
            to="/settings"
            onClick={onNavigate}
            className={cn(
              "flex items-center rounded-md px-3 py-2 text-sm font-medium text-muted-foreground hover:bg-accent hover:text-foreground focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-ring transition-colors",
              location.pathname === "/settings" && "bg-primary text-primary-foreground"
            )}
          >
            <Settings className="mr-3 h-4 w-4" />
            <span>Platform Settings</span>
          </NavLink>
        )}
      </div>
    </aside>
  );
}
