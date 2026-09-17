import { describe, it, expect } from "vitest";
import { render, screen } from "@testing-library/react";
import { MemoryRouter, Routes, Route } from "react-router-dom";
import { AuthProvider } from "@/context/auth-context";
import { ProtectedRoute } from "@/routes/protected-route";
import { NotFoundState } from "@/components/feedback/not-found-state";
import type { User } from "@/types/auth";

const REGULAR_MEMBER: User = {
  id: "usr_member",
  name: "John Member",
  email: "john.member@jakeai.internal",
  tenantId: "tenant_jakeai_core",
  roles: ["member"],
  permissions: ["read:workspace"],
};

const ADMIN_USER: User = {
  id: "usr_admin",
  name: "Admin User",
  email: "admin@jakeai.internal",
  tenantId: "tenant_jakeai_core",
  roles: ["admin"],
  permissions: ["*"],
};

describe("Routing & Route Protection", () => {
  it("redirects unauthenticated users attempting to access protected route to /login", () => {
    render(
      <AuthProvider initialAuthenticated={false} initialUser={null}>
        <MemoryRouter initialEntries={["/workspace"]}>
          <Routes>
            <Route path="/login" element={<div>Login Page Target</div>} />
            <Route
              path="/workspace"
              element={
                <ProtectedRoute>
                  <div>Secret Workspace Content</div>
                </ProtectedRoute>
              }
            />
          </Routes>
        </MemoryRouter>
      </AuthProvider>
    );

    expect(screen.getByText("Login Page Target")).toBeInTheDocument();
    expect(screen.queryByText("Secret Workspace Content")).not.toBeInTheDocument();
  });

  it("renders protected content when user is authenticated", () => {
    render(
      <AuthProvider initialAuthenticated={true} initialUser={REGULAR_MEMBER}>
        <MemoryRouter initialEntries={["/workspace"]}>
          <Routes>
            <Route
              path="/workspace"
              element={
                <ProtectedRoute>
                  <div>Secret Workspace Content</div>
                </ProtectedRoute>
              }
            />
          </Routes>
        </MemoryRouter>
      </AuthProvider>
    );

    expect(screen.getByText("Secret Workspace Content")).toBeInTheDocument();
  });

  it("renders PermissionDeniedState (403) when user lacks required role, not just hiding buttons", () => {
    render(
      <AuthProvider initialAuthenticated={true} initialUser={REGULAR_MEMBER}>
        <MemoryRouter initialEntries={["/admin"]}>
          <Routes>
            <Route
              path="/admin"
              element={
                <ProtectedRoute requiredRoles={["admin", "tenant_admin"]}>
                  <div>Admin Confidential Console</div>
                </ProtectedRoute>
              }
            />
          </Routes>
        </MemoryRouter>
      </AuthProvider>
    );

    // Should display access restriction alert
    expect(screen.getByRole("alert")).toBeInTheDocument();
    expect(screen.getByText("Access Restricted")).toBeInTheDocument();
    expect(screen.queryByText("Admin Confidential Console")).not.toBeInTheDocument();
  });

  it("allows access to admin route when user has required admin role", () => {
    render(
      <AuthProvider initialAuthenticated={true} initialUser={ADMIN_USER}>
        <MemoryRouter initialEntries={["/admin"]}>
          <Routes>
            <Route
              path="/admin"
              element={
                <ProtectedRoute requiredRoles={["admin", "tenant_admin"]}>
                  <div>Admin Confidential Console</div>
                </ProtectedRoute>
              }
            />
          </Routes>
        </MemoryRouter>
      </AuthProvider>
    );

    expect(screen.getByText("Admin Confidential Console")).toBeInTheDocument();
  });

  it("renders NotFoundState when non-existent route is requested", () => {
    render(
      <MemoryRouter initialEntries={["/non-existent-path"]}>
        <Routes>
          <Route path="*" element={<NotFoundState />} />
        </Routes>
      </MemoryRouter>
    );

    expect(screen.getByText("HTTP 404")).toBeInTheDocument();
    expect(screen.getByText("Resource or Page Not Found")).toBeInTheDocument();
  });
});
