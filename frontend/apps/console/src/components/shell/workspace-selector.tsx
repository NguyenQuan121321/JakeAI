import { Building2, Check, ChevronsUpDown, ShieldCheck } from "lucide-react";
import { useAuth } from "@/context/auth-context";
import { Dropdown, DropdownTrigger, DropdownContent, DropdownItem, DropdownLabel, DropdownSeparator } from "@/components/ui/dropdown";
import { Badge } from "@/components/ui/badge";

export function WorkspaceSelector() {
  const { workspaces, activeWorkspace, switchWorkspace } = useAuth();

  if (!activeWorkspace) return null;

  return (
    <Dropdown>
      <DropdownTrigger asChild>
        <button
          type="button"
          aria-label="Switch workspace"
          className="flex items-center space-x-2.5 rounded-lg border bg-background/50 px-3 py-1.5 text-left text-sm font-medium shadow-sm hover:bg-accent hover:text-accent-foreground focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-ring transition-colors"
        >
          <div className="flex h-6 w-6 items-center justify-center rounded bg-primary/10 text-primary">
            <Building2 className="h-3.5 w-3.5" />
          </div>
          <div className="flex flex-col text-left">
            <div className="flex items-center space-x-1.5">
              <span className="font-semibold text-xs leading-none text-foreground">{activeWorkspace.name}</span>
              <span className="text-[10px] uppercase font-bold text-muted-foreground/80 tracking-wider">
                [{activeWorkspace.environment.slice(0, 4)}]
              </span>
            </div>
            <span className="text-[11px] text-muted-foreground leading-tight">{activeWorkspace.slug}</span>
          </div>
          <ChevronsUpDown className="h-4 w-4 opacity-50 shrink-0 ml-1" />
        </button>
      </DropdownTrigger>

      <DropdownContent align="left" className="w-64 p-1">
        <DropdownLabel>Workspaces & Tenants</DropdownLabel>
        <DropdownSeparator />
        {workspaces.map((ws) => {
          const isSelected = ws.id === activeWorkspace.id;
          return (
            <DropdownItem
              key={ws.id}
              onClick={() => switchWorkspace(ws.id)}
              className="flex items-center justify-between py-2"
            >
              <div className="flex items-center space-x-2.5">
                <div className="flex h-5 w-5 items-center justify-center rounded bg-muted text-muted-foreground">
                  {isSelected ? (
                    <Check className="h-3.5 w-3.5 text-primary" />
                  ) : (
                    <Building2 className="h-3 w-3" />
                  )}
                </div>
                <div className="flex flex-col">
                  <span className="font-medium text-xs">{ws.name}</span>
                  <span className="text-[10px] text-muted-foreground">{ws.environment}</span>
                </div>
              </div>
              <Badge variant="outline" className="text-[10px] py-0 px-1.5 uppercase">
                {ws.plan}
              </Badge>
            </DropdownItem>
          );
        })}
        <DropdownSeparator />
        <div className="px-2.5 py-1.5 text-[11px] text-muted-foreground flex items-center space-x-1.5">
          <ShieldCheck className="h-3.5 w-3.5 text-primary" />
          <span>Tenant Context: Isolation Active</span>
        </div>
      </DropdownContent>
    </Dropdown>
  );
}
