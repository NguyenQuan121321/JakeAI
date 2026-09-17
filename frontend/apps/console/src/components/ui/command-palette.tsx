import * as React from "react";
import { useNavigate } from "react-router-dom";
import {
  Search,
  LayoutDashboard,
  Bot,
  Layers,
  Database,
  KeyRound,
  Coins,
  BarChart3,
  ShieldAlert,
  Settings,
  Sun,
  Moon,
  LogOut,
  X,
} from "lucide-react";
import { useTheme } from "@/context/theme-context";
import { useAuth } from "@/context/auth-context";
import { cn } from "@/lib/utils";

interface CommandItem {
  id: string;
  title: string;
  category: "Navigation" | "Actions" | "Preferences";
  icon: React.ComponentType<{ className?: string }>;
  onSelect: () => void;
  keywords?: string[];
}

export function CommandPalette({
  open,
  onOpenChange,
}: {
  open: boolean;
  onOpenChange: (open: boolean) => void;
}) {
  const navigate = useNavigate();
  const { setTheme, resolvedTheme } = useTheme();
  const { logout, hasRole } = useAuth();
  const [query, setQuery] = React.useState("");
  const [selectedIndex, setSelectedIndex] = React.useState(0);
  const inputRef = React.useRef<HTMLInputElement>(null);

  const isAdmin = hasRole(["admin", "tenant_admin"]);

  const commands: CommandItem[] = React.useMemo(() => {
    const list: CommandItem[] = [
      {
        id: "nav-workspace",
        title: "Workspace Overview",
        category: "Navigation",
        icon: LayoutDashboard,
        onSelect: () => navigate("/workspace"),
        keywords: ["home", "dashboard", "overview"],
      },
      {
        id: "nav-agents",
        title: "Agent Platform",
        category: "Navigation",
        icon: Bot,
        onSelect: () => navigate("/agent"),
        keywords: ["ai", "orchestrator", "workers"],
      },
      {
        id: "nav-agent-runs",
        title: "Agent Execution Runs",
        category: "Navigation",
        icon: Layers,
        onSelect: () => navigate("/agent/runs"),
        keywords: ["traces", "history", "logs"],
      },
      {
        id: "nav-rag",
        title: "RAG & Knowledge Base",
        category: "Navigation",
        icon: Database,
        onSelect: () => navigate("/rag"),
        keywords: ["embeddings", "vector", "search"],
      },
      {
        id: "nav-providers",
        title: "Providers & BYOK",
        category: "Navigation",
        icon: KeyRound,
        onSelect: () => navigate("/providers"),
        keywords: ["openai", "anthropic", "keys", "models"],
      },
      {
        id: "nav-finops",
        title: "AI FinOps & Budgets",
        category: "Navigation",
        icon: Coins,
        onSelect: () => navigate("/finops"),
        keywords: ["cost", "tokens", "spend", "accounting"],
      },
      {
        id: "nav-analytics",
        title: "Analytics & Telemetry",
        category: "Navigation",
        icon: BarChart3,
        onSelect: () => navigate("/analytics"),
        keywords: ["metrics", "latency", "throughput", "p95"],
      },
      {
        id: "nav-settings",
        title: "Platform Settings",
        category: "Navigation",
        icon: Settings,
        onSelect: () => navigate("/settings"),
        keywords: ["config", "preferences", "theme"],
      },
      {
        id: "action-theme",
        title: `Switch to ${resolvedTheme === "dark" ? "Light" : "Dark"} Mode`,
        category: "Preferences",
        icon: resolvedTheme === "dark" ? Sun : Moon,
        onSelect: () => setTheme(resolvedTheme === "dark" ? "light" : "dark"),
        keywords: ["theme", "color", "mode"],
      },
      {
        id: "action-logout",
        title: "Log Out / Exit Session",
        category: "Actions",
        icon: LogOut,
        onSelect: () => {
          logout();
          navigate("/login");
        },
        keywords: ["signout", "exit", "disconnect"],
      },
    ];

    if (isAdmin) {
      list.push({
        id: "nav-admin",
        title: "Administration & RBAC",
        category: "Navigation",
        icon: ShieldAlert,
        onSelect: () => navigate("/admin"),
        keywords: ["tenants", "users", "roles", "permissions"],
      });
    }

    return list;
  }, [navigate, resolvedTheme, setTheme, logout, isAdmin]);

  const filteredCommands = React.useMemo(() => {
    if (!query.trim()) return commands;
    const q = query.toLowerCase();
    return commands.filter(
      (cmd) =>
        cmd.title.toLowerCase().includes(q) ||
        cmd.category.toLowerCase().includes(q) ||
        cmd.keywords?.some((k) => k.toLowerCase().includes(q))
    );
  }, [commands, query]);

  React.useEffect(() => {
    setSelectedIndex(0);
  }, [query]);

  React.useEffect(() => {
    if (open) {
      setTimeout(() => inputRef.current?.focus(), 50);
    } else {
      setQuery("");
    }
  }, [open]);

  // Global Ctrl+K / Cmd+K listener
  React.useEffect(() => {
    const handleKeyDown = (e: KeyboardEvent) => {
      if ((e.ctrlKey || e.metaKey) && e.key.toLowerCase() === "k") {
        e.preventDefault();
        onOpenChange(!open);
      }
      if (e.key === "Escape" && open) {
        onOpenChange(false);
      }
    };
    window.addEventListener("keydown", handleKeyDown);
    return () => window.removeEventListener("keydown", handleKeyDown);
  }, [open, onOpenChange]);

  const handleKeyDown = (e: React.KeyboardEvent) => {
    if (e.key === "ArrowDown") {
      e.preventDefault();
      setSelectedIndex((prev) => (prev < filteredCommands.length - 1 ? prev + 1 : 0));
    } else if (e.key === "ArrowUp") {
      e.preventDefault();
      setSelectedIndex((prev) => (prev > 0 ? prev - 1 : filteredCommands.length - 1));
    } else if (e.key === "Enter") {
      e.preventDefault();
      const selected = filteredCommands[selectedIndex];
      if (selected) {
        selected.onSelect();
        onOpenChange(false);
      }
    }
  };

  if (!open) return null;

  return (
    <div
      className="fixed inset-0 z-50 flex items-start justify-center pt-20 px-4"
      role="dialog"
      aria-modal="true"
      aria-label="Command Palette"
    >
      <div
        className="fixed inset-0 bg-background/80 backdrop-blur-sm transition-opacity"
        onClick={() => onOpenChange(false)}
        aria-hidden="true"
      />
      <div className="relative z-50 w-full max-w-xl rounded-xl border bg-popover text-popover-foreground shadow-2xl overflow-hidden animate-in zoom-in-95 duration-150">
        <div className="flex items-center border-b px-4 py-3">
          <Search className="mr-3 h-5 w-5 shrink-0 text-muted-foreground" aria-hidden="true" />
          <input
            ref={inputRef}
            type="text"
            className="flex-1 bg-transparent text-sm placeholder:text-muted-foreground outline-none"
            placeholder="Type a command or search console..."
            value={query}
            onChange={(e) => setQuery(e.target.value)}
            onKeyDown={handleKeyDown}
          />
          <button
            type="button"
            onClick={() => onOpenChange(false)}
            aria-label="Close command palette"
            className="rounded p-1 text-muted-foreground hover:text-foreground"
          >
            <X className="h-4 w-4" />
          </button>
        </div>
        <div className="max-h-80 overflow-y-auto p-2" role="listbox">
          {filteredCommands.length === 0 ? (
            <div className="py-6 text-center text-sm text-muted-foreground">
              No matching commands or routes found.
            </div>
          ) : (
            filteredCommands.map((cmd, idx) => {
              const Icon = cmd.icon;
              const isSelected = idx === selectedIndex;
              return (
                <div
                  key={cmd.id}
                  role="option"
                  aria-selected={isSelected}
                  className={cn(
                    "flex items-center justify-between rounded-md px-3 py-2 text-sm cursor-pointer select-none transition-colors",
                    isSelected ? "bg-accent text-accent-foreground font-medium" : "hover:bg-accent/50 text-foreground"
                  )}
                  onClick={() => {
                    cmd.onSelect();
                    onOpenChange(false);
                  }}
                  onMouseEnter={() => setSelectedIndex(idx)}
                >
                  <div className="flex items-center space-x-3">
                    <Icon className="h-4 w-4 text-muted-foreground" />
                    <span>{cmd.title}</span>
                  </div>
                  <span className="text-[10px] text-muted-foreground uppercase font-semibold tracking-wider">
                    {cmd.category}
                  </span>
                </div>
              );
            })
          )}
        </div>
        <div className="flex items-center justify-between border-t bg-muted/40 px-4 py-2 text-[11px] text-muted-foreground">
          <span>Navigate with ↑ and ↓</span>
          <span>Execute with ↵ Enter</span>
          <span>Close with Esc</span>
        </div>
      </div>
    </div>
  );
}
