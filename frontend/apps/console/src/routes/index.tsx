import React, { Suspense, lazy } from "react";
import { createBrowserRouter, Navigate } from "react-router-dom";
import { AppShell } from "@/components/shell/app-shell";
import { ProtectedRoute } from "@/routes/protected-route";
import { LoadingState } from "@/components/feedback/loading-state";
import { ErrorBoundary } from "@/components/feedback/error-boundary";

// Route-level code splitting using React.lazy
const LoginPage = lazy(() => import("@/pages/login"));
const WorkspacePage = lazy(() => import("@/pages/workspace"));
const AgentPage = lazy(() => import("@/pages/agent"));
const AgentRunsPage = lazy(() => import("@/pages/agent-runs"));
const RagPage = lazy(() => import("@/pages/rag"));
const ProvidersPage = lazy(() => import("@/pages/providers"));
const FinOpsPage = lazy(() => import("@/pages/finops"));
const AnalyticsPage = lazy(() => import("@/pages/analytics"));
const AdminPage = lazy(() => import("@/pages/admin"));
const SettingsPage = lazy(() => import("@/pages/settings"));
const NotFoundPage = lazy(() => import("@/pages/not-found"));

function SuspenseWrapper({ children }: { children: React.ReactNode }) {
  return (
    <ErrorBoundary>
      <Suspense fallback={<LoadingState message="Loading module..." />}>
        {children}
      </Suspense>
    </ErrorBoundary>
  );
}

export const router = createBrowserRouter([
  {
    path: "/login",
    element: (
      <SuspenseWrapper>
        <LoginPage />
      </SuspenseWrapper>
    ),
  },
  {
    path: "/",
    element: (
      <ProtectedRoute>
        <AppShell />
      </ProtectedRoute>
    ),
    children: [
      {
        index: true,
        element: <Navigate to="/workspace" replace />,
      },
      {
        path: "workspace",
        element: (
          <SuspenseWrapper>
            <WorkspacePage />
          </SuspenseWrapper>
        ),
      },
      {
        path: "agent",
        element: (
          <SuspenseWrapper>
            <AgentPage />
          </SuspenseWrapper>
        ),
      },
      {
        path: "agent/runs",
        element: (
          <SuspenseWrapper>
            <AgentRunsPage />
          </SuspenseWrapper>
        ),
      },
      {
        path: "rag",
        element: (
          <SuspenseWrapper>
            <RagPage />
          </SuspenseWrapper>
        ),
      },
      {
        path: "providers",
        element: (
          <SuspenseWrapper>
            <ProvidersPage />
          </SuspenseWrapper>
        ),
      },
      {
        path: "finops",
        element: (
          <SuspenseWrapper>
            <FinOpsPage />
          </SuspenseWrapper>
        ),
      },
      {
        path: "analytics",
        element: (
          <SuspenseWrapper>
            <AnalyticsPage />
          </SuspenseWrapper>
        ),
      },
      {
        path: "admin",
        element: (
          <ProtectedRoute requiredRoles={["admin", "tenant_admin"]}>
            <SuspenseWrapper>
              <AdminPage />
            </SuspenseWrapper>
          </ProtectedRoute>
        ),
      },
      {
        path: "settings",
        element: (
          <SuspenseWrapper>
            <SettingsPage />
          </SuspenseWrapper>
        ),
      },
      {
        path: "*",
        element: (
          <SuspenseWrapper>
            <NotFoundPage />
          </SuspenseWrapper>
        ),
      },
    ],
  },
  {
    path: "*",
    element: (
      <SuspenseWrapper>
        <NotFoundPage />
      </SuspenseWrapper>
    ),
  },
]);
