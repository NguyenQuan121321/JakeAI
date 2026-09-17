import * as React from "react";
import { WifiOff } from "lucide-react";
import { cn } from "@/lib/utils";

export function OfflineBanner({ className }: { className?: string }) {
  const [isOffline, setIsOffline] = React.useState(!navigator.onLine);

  React.useEffect(() => {
    const handleOnline = () => setIsOffline(false);
    const handleOffline = () => setIsOffline(true);

    window.addEventListener("online", handleOnline);
    window.addEventListener("offline", handleOffline);

    return () => {
      window.removeEventListener("online", handleOnline);
      window.removeEventListener("offline", handleOffline);
    };
  }, []);

  if (!isOffline) return null;

  return (
    <div
      role="alert"
      aria-live="assertive"
      className={cn(
        "flex items-center justify-center space-x-2 bg-amber-500 px-4 py-2 text-xs font-semibold text-white shadow-md transition-all animate-in slide-in-from-top duration-200",
        className
      )}
    >
      <WifiOff className="h-4 w-4 shrink-0" aria-hidden="true" />
      <span>
        Network connection lost. The console is currently in offline mode; some actions may fail.
      </span>
    </div>
  );
}
