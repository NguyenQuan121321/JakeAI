import { describe, it, expect } from "vitest";
import { render, screen } from "@testing-library/react";
import { MemoryRouter } from "react-router-dom";
import { AuthProvider } from "@/context/auth-context";
import { ThemeProvider } from "@/context/theme-context";
import { AppShell } from "@/components/shell/app-shell";
import type { User } from "@/types/auth";

const ADMIN_USER: User = {
  id: "usr_admin",
  name: "Alex Mercer",
  email: "alex.mercer@jakeai.internal",
  tenantId: "tenant_jakeai_core",
  roles: ["admin", "tenant_admin"],
  permissions: ["*"],
};

const VIEWER_USER: User = {
  id: "usr_viewer",
  name: "Viewer User",
  email: "viewer@jakeai.internal",
  tenantId: "tenant_jakeai_core",
  roles: ["viewer"],
  permissions: ["read:workspace"],
};

describe("Application Shell & Navigation", () => {
  it("renders all required navigation sections for admin user", () => {
    render(
      <ThemeProvider>
        <AuthProvider initialUser={ADMIN_USER} initialAuthenticated={true}>
          <MemoryRouter initialEntries={["/workspace"]}>
            <AppShell />
          </MemoryRouter>
        </AuthProvider>
      </ThemeProvider>
    );

    // Sidebar navigation landmark
    expect(screen.getByRole("navigation", { name: /main navigation/i })).toBeInTheDocument();

    // Check presence of sidebar sections
    expect(screen.getByText("Workspace")).toBeInTheDocument();
    expect(screen.getByText("Agents")).toBeInTheDocument();
    expect(screen.getByText("RAG")).toBeInTheDocument();
    expect(screen.getByText("Providers")).toBeInTheDocument();
    expect(screen.getByText("FinOps")).toBeInTheDocument();
    expect(screen.getByText("Analytics")).toBeInTheDocument();
    expect(screen.getByText("Administration")).toBeInTheDocument();
  });

  it("omits Administration navigation section for non-admin user", () => {
    render(
      <ThemeProvider>
        <AuthProvider initialUser={VIEWER_USER} initialAuthenticated={true}>
          <MemoryRouter initialEntries={["/workspace"]}>
            <AppShell />
          </MemoryRouter>
        </AuthProvider>
      </ThemeProvider>
    );

    // Common navigation should be visible
    expect(screen.getByText("Workspace")).toBeInTheDocument();
    expect(screen.getByText("Agents")).toBeInTheDocument();

    // Admin should NOT be visible for viewer
    expect(screen.queryByText("Administration")).not.toBeInTheDocument();
  });

  it("renders workspace selector with active tenant", () => {
    render(
      <ThemeProvider>
        <AuthProvider initialUser={ADMIN_USER} initialAuthenticated={true}>
          <MemoryRouter initialEntries={["/workspace"]}>
            <AppShell />
          </MemoryRouter>
        </AuthProvider>
      </ThemeProvider>
    );

    // Active workspace name should be displayed
    expect(screen.getByText("JakeAI Core Platform")).toBeInTheDocument();
  });

  it("provides accessible skip to main content link", () => {
    render(
      <ThemeProvider>
        <AuthProvider initialUser={ADMIN_USER} initialAuthenticated={true}>
          <MemoryRouter initialEntries={["/workspace"]}>
            <AppShell />
          </MemoryRouter>
        </AuthProvider>
      </ThemeProvider>
    );

    const skipLink = screen.getByText("Skip to main content");
    expect(skipLink).toBeInTheDocument();
    expect(skipLink).toHaveAttribute("href", "#main-content");
  });
});
