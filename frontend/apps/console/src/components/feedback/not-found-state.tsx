import { FileQuestion, Home, ArrowLeft } from "lucide-react";
import { useNavigate } from "react-router-dom";
import { Button } from "@/components/ui/button";
import { cn } from "@/lib/utils";

export interface NotFoundStateProps {
  title?: string;
  description?: string;
  className?: string;
}

export function NotFoundState({
  title = "Resource or Page Not Found",
  description = "The requested console route does not exist or has been deprecated. Please verify the URL or return to your active workspace.",
  className,
}: NotFoundStateProps) {
  const navigate = useNavigate();

  return (
    <div
      role="region"
      aria-label="Not found error"
      className={cn(
        "flex min-h-[450px] flex-col items-center justify-center p-8 text-center animate-in fade-in-50",
        className
      )}
    >
      <div className="flex h-20 w-20 items-center justify-center rounded-full bg-muted/60 text-muted-foreground mb-4">
        <FileQuestion className="h-10 w-10" aria-hidden="true" />
      </div>
      <div className="rounded-full bg-primary/10 px-3 py-1 text-xs font-semibold text-primary mb-2">
        HTTP 404
      </div>
      <h1 className="text-2xl font-bold tracking-tight text-foreground">{title}</h1>
      <p className="mt-2 max-w-md text-sm text-muted-foreground">{description}</p>

      <div className="mt-6 flex items-center space-x-3">
        <Button
          variant="outline"
          onClick={() => navigate(-1)}
          leftIcon={<ArrowLeft className="h-4 w-4" />}
        >
          Go Back
        </Button>
        <Button
          onClick={() => navigate("/workspace")}
          leftIcon={<Home className="h-4 w-4" />}
        >
          Workspace Home
        </Button>
      </div>
    </div>
  );
}
