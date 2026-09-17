import { Navigate, useLocation } from "react-router-dom";
import { useAuth } from "@/context/auth-context";
import { LoadingState } from "@/components/feedback/loading-state";
import { PermissionDeniedState } from "@/components/feedback/permission-denied-state";

interface ProtectedRouteProps {
  children: React.ReactNode;
  requiredRoles?: string[];
  requiredPermissions?: string[];
}

export function ProtectedRoute({
  children,
  requiredRoles,
  requiredPermissions,
}: ProtectedRouteProps) {
  const { isAuthenticated, isLoading, hasRole, hasPermission } = useAuth();
  const location = useLocation();

  if (isLoading) {
    return <LoadingState message="Authenticating enterprise tenant session..." fullScreen />;
  }

  if (!isAuthenticated) {
    return <Navigate to="/login" state={{ from: location }} replace />;
  }

  // Enforce Authorization (RBAC / PBAC)
  if (requiredRoles && !hasRole(requiredRoles)) {
    return <PermissionDeniedState requiredRoles={requiredRoles} />;
  }

  if (requiredPermissions && !hasPermission(requiredPermissions)) {
    return <PermissionDeniedState description="You do not possess the required fine-grained permissions for this route." />;
  }

  return <>{children}</>;
}
