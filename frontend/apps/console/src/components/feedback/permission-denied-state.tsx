import { ShieldAlert, ArrowLeft } from "lucide-react";
import { useNavigate } from "react-router-dom";
import { Button } from "@/components/ui/button";
import { cn } from "@/lib/utils";

export interface PermissionDeniedStateProps {
  title?: string;
  description?: string;
  requiredRoles?: string[];
  className?: string;
}

export function PermissionDeniedState({
  title = "Access Restricted",
  description = "Your current authorization context does not have sufficient tenant permissions to access this administrative module.",
  requiredRoles,
  className,
}: PermissionDeniedStateProps) {
  const navigate = useNavigate();

  return (
    <div
      role="alert"
      className={cn(
        "flex min-h-[400px] flex-col items-center justify-center rounded-lg border border-amber-500/20 bg-amber-500/5 p-8 text-center",
        className
      )}
    >
      <div className="flex h-16 w-16 items-center justify-center rounded-full bg-amber-500/10 text-amber-600 dark:text-amber-400 mb-4">
        <ShieldAlert className="h-8 w-8" aria-hidden="true" />
      </div>
      <h2 className="text-xl font-semibold text-foreground tracking-tight">{title}</h2>
      <p className="mt-2 max-w-md text-sm text-muted-foreground">{description}</p>

      {requiredRoles && requiredRoles.length > 0 && (
        <div className="mt-4 flex items-center space-x-2">
          <span className="text-xs text-muted-foreground">Required role(s):</span>
          <div className="flex gap-1.5">
            {requiredRoles.map((role) => (
              <span
                key={role}
                className="rounded bg-muted px-2 py-0.5 text-xs font-mono font-medium text-foreground"
              >
                {role}
              </span>
            ))}
          </div>
        </div>
      )}

      <div className="mt-6 flex items-center space-x-3">
        <Button
          variant="outline"
          onClick={() => navigate(-1)}
          leftIcon={<ArrowLeft className="h-4 w-4" />}
        >
          Go Back
        </Button>
        <Button onClick={() => navigate("/workspace")}>
          Return to Workspace
        </Button>
      </div>
    </div>
  );
}
