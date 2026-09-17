import * as React from "react";
import { Outlet } from "react-router-dom";
import { Sidebar } from "@/components/shell/sidebar";
import { TopBar } from "@/components/shell/top-bar";
import { MobileNav } from "@/components/shell/mobile-nav";
import { CommandPalette } from "@/components/ui/command-palette";
import { OfflineBanner } from "@/components/feedback/offline-banner";
import { Toaster } from "@/components/ui/toast";

export function AppShell() {
  const [sidebarCollapsed, setSidebarCollapsed] = React.useState(false);
  const [mobileNavOpen, setMobileNavOpen] = React.useState(false);
  const [commandPaletteOpen, setCommandPaletteOpen] = React.useState(false);

  return (
    <div className="flex h-screen w-full overflow-hidden bg-background text-foreground">
      {/* Desktop Sidebar (hidden on mobile/tablet screens < 768px) */}
      <div className="hidden md:flex h-full shrink-0">
        <Sidebar
          isCollapsed={sidebarCollapsed}
          setIsCollapsed={setSidebarCollapsed}
        />
      </div>

      {/* Mobile / Tablet Slide-out Navigation Drawer */}
      <MobileNav
        open={mobileNavOpen}
        onOpenChange={setMobileNavOpen}
      />

      {/* Main View Area */}
      <div className="flex flex-1 flex-col overflow-hidden min-w-0">
        <OfflineBanner />
        <TopBar
          onMenuClick={() => setMobileNavOpen(true)}
          onCommandClick={() => setCommandPaletteOpen(true)}
        />

        {/* Accessible Content Area */}
        <main
          id="main-content"
          role="main"
          tabIndex={-1}
          className="flex-1 overflow-y-auto p-4 sm:p-6 md:p-8 focus:outline-none"
        >
          <div className="mx-auto max-w-7xl">
            <Outlet />
          </div>
        </main>
      </div>

      {/* Global Command Palette */}
      <CommandPalette
        open={commandPaletteOpen}
        onOpenChange={setCommandPaletteOpen}
      />

      {/* Global Toast Notifications */}
      <Toaster />
    </div>
  );
}
