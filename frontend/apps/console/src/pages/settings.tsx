import { Laptop, Moon, Sun, Bell, Shield, Check } from "lucide-react";
import { useTheme } from "@/context/theme-context";
import { useAuth } from "@/context/auth-context";
import { useToast } from "@/hooks/use-toast";
import { Card, CardHeader, CardTitle, CardDescription, CardContent } from "@/components/ui/card";
import { Button } from "@/components/ui/button";
import { Badge } from "@/components/ui/badge";

export default function SettingsPage() {
  const { theme, setTheme } = useTheme();
  const { user, activeWorkspace } = useAuth();
  const { toast } = useToast();

  const handleSaveNotificationPref = () => {
    toast({
      title: "Preferences saved",
      description: "Your notification and UI preferences have been safely persisted.",
      variant: "success",
    });
  };

  return (
    <div className="space-y-8 max-w-4xl">
      <div>
        <h1 className="text-2xl font-bold tracking-tight">Platform Settings</h1>
        <p className="text-sm text-muted-foreground mt-1">
          Configure appearance, safe UI preferences, and view active tenant authorization metadata.
        </p>
      </div>

      {/* Theme Card */}
      <Card>
        <CardHeader>
          <CardTitle className="text-base">Interface Appearance</CardTitle>
          <CardDescription>
            Choose your preferred display theme. System will automatically match your OS settings.
          </CardDescription>
        </CardHeader>
        <CardContent>
          <div className="grid grid-cols-1 sm:grid-cols-3 gap-3">
            <button
              type="button"
              onClick={() => setTheme("light")}
              className={`flex items-center justify-between p-4 rounded-lg border text-left transition-all ${
                theme === "light"
                  ? "border-primary bg-primary/5 ring-2 ring-primary"
                  : "border-border hover:bg-muted/50"
              }`}
            >
              <div className="flex items-center space-x-3">
                <Sun className="h-5 w-5 text-amber-500" />
                <div>
                  <p className="text-sm font-semibold">Light</p>
                  <p className="text-xs text-muted-foreground">Clean high contrast</p>
                </div>
              </div>
              {theme === "light" && <Check className="h-4 w-4 text-primary" />}
            </button>

            <button
              type="button"
              onClick={() => setTheme("dark")}
              className={`flex items-center justify-between p-4 rounded-lg border text-left transition-all ${
                theme === "dark"
                  ? "border-primary bg-primary/5 ring-2 ring-primary"
                  : "border-border hover:bg-muted/50"
              }`}
            >
              <div className="flex items-center space-x-3">
                <Moon className="h-5 w-5 text-sky-400" />
                <div>
                  <p className="text-sm font-semibold">Dark</p>
                  <p className="text-xs text-muted-foreground">Reduced eye strain</p>
                </div>
              </div>
              {theme === "dark" && <Check className="h-4 w-4 text-primary" />}
            </button>

            <button
              type="button"
              onClick={() => setTheme("system")}
              className={`flex items-center justify-between p-4 rounded-lg border text-left transition-all ${
                theme === "system"
                  ? "border-primary bg-primary/5 ring-2 ring-primary"
                  : "border-border hover:bg-muted/50"
              }`}
            >
              <div className="flex items-center space-x-3">
                <Laptop className="h-5 w-5 text-muted-foreground" />
                <div>
                  <p className="text-sm font-semibold">System</p>
                  <p className="text-xs text-muted-foreground">Follow OS setting</p>
                </div>
              </div>
              {theme === "system" && <Check className="h-4 w-4 text-primary" />}
            </button>
          </div>
        </CardContent>
      </Card>

      {/* Tenant Context Information */}
      <Card>
        <CardHeader>
          <CardTitle className="text-base flex items-center space-x-2">
            <Shield className="h-4 w-4 text-primary" />
            <span>Active Authorization Session</span>
          </CardTitle>
          <CardDescription>
            Tenant context injected upon FinnApiGo JWT verification.
          </CardDescription>
        </CardHeader>
        <CardContent>
          <div className="divide-y text-xs">
            <div className="py-2.5 flex justify-between">
              <span className="text-muted-foreground">Subject User ID</span>
              <span className="font-mono text-foreground">{user?.id}</span>
            </div>
            <div className="py-2.5 flex justify-between">
              <span className="text-muted-foreground">Tenant Identifier</span>
              <span className="font-mono text-foreground">{activeWorkspace?.id}</span>
            </div>
            <div className="py-2.5 flex justify-between">
              <span className="text-muted-foreground">Tenant Roles</span>
              <div className="flex gap-1">
                {user?.roles.map((r) => (
                  <Badge key={r} variant="secondary" className="text-[10px] font-mono">
                    {r}
                  </Badge>
                ))}
              </div>
            </div>
            <div className="py-2.5 flex justify-between">
              <span className="text-muted-foreground">Granted Permissions</span>
              <span className="font-mono text-primary">{user?.permissions.join(", ")}</span>
            </div>
          </div>
        </CardContent>
      </Card>

      {/* Notification Toast Demo */}
      <Card>
        <CardHeader>
          <CardTitle className="text-base flex items-center space-x-2">
            <Bell className="h-4 w-4 text-primary" />
            <span>Notification & Preferences</span>
          </CardTitle>
          <CardDescription>
            Persist UI preferences without writing secrets or tokens to insecure storage.
          </CardDescription>
        </CardHeader>
        <CardContent className="flex items-center justify-between">
          <p className="text-xs text-muted-foreground">
            Test non-blocking notification toast alert primitive.
          </p>
          <Button size="sm" onClick={handleSaveNotificationPref}>
            Trigger Test Toast
          </Button>
        </CardContent>
      </Card>
    </div>
  );
}
