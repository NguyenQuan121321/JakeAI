import { Menu, Search } from "lucide-react";
import { WorkspaceSelector } from "@/components/shell/workspace-selector";
import { UserNav } from "@/components/shell/user-nav";
import { ThemeToggle } from "@/components/shell/theme-toggle";
import { NotificationActivity } from "@/components/shell/notification-activity";

export function TopBar({
  onMenuClick,
  onCommandClick,
}: {
  onMenuClick: () => void;
  onCommandClick: () => void;
}) {
  return (
    <header className="sticky top-0 z-40 flex h-16 w-full items-center justify-between border-b bg-background/80 px-4 sm:px-6 backdrop-blur-md">
      {/* Skip to Content Link for keyboard accessibility */}
      <a
        href="#main-content"
        className="sr-only focus:not-sr-only focus:absolute focus:top-3 focus:left-3 focus:z-50 focus:rounded-md focus:bg-primary focus:px-3 focus:py-2 focus:text-primary-foreground focus:outline-none focus:ring-2 focus:ring-ring"
      >
        Skip to main content
      </a>

      {/* Left: Mobile hamburger & Workspace Selector */}
      <div className="flex items-center space-x-3">
        <button
          type="button"
          onClick={onMenuClick}
          aria-label="Open mobile navigation"
          className="flex md:hidden rounded-md p-2 text-muted-foreground hover:bg-accent hover:text-foreground focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-ring"
        >
          <Menu className="h-5 w-5" />
        </button>
        <WorkspaceSelector />
      </div>

      {/* Center: Command Palette Trigger Button */}
      <div className="flex-1 max-w-md mx-4 hidden sm:block">
        <button
          type="button"
          onClick={onCommandClick}
          className="flex h-9 w-full items-center justify-between rounded-md border border-input bg-background/50 px-3 py-1 text-xs text-muted-foreground shadow-sm hover:bg-accent hover:text-accent-foreground focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-ring transition-colors"
        >
          <div className="flex items-center space-x-2">
            <Search className="h-4 w-4" />
            <span>Search commands or routes...</span>
          </div>
          <kbd className="pointer-events-none inline-flex h-5 select-none items-center gap-1 rounded border bg-muted px-1.5 font-mono text-[10px] font-medium text-muted-foreground opacity-100">
            <span className="text-xs">⌘</span>K
          </kbd>
        </button>
      </div>

      {/* Right: Controls (Theme, Notifications, User) */}
      <div className="flex items-center space-x-2">
        <button
          type="button"
          onClick={onCommandClick}
          aria-label="Open command palette"
          className="sm:hidden rounded-full p-2 text-muted-foreground hover:bg-accent hover:text-foreground focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-ring"
        >
          <Search className="h-5 w-5" />
        </button>

        <ThemeToggle />
        <NotificationActivity />
        <div className="h-5 w-px bg-border mx-1" aria-hidden="true" />
        <UserNav />
      </div>
    </header>
  );
}
