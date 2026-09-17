import { User as UserIcon, LogOut, Settings, ExternalLink } from "lucide-react";
import { useNavigate } from "react-router-dom";
import { useAuth } from "@/context/auth-context";
import { Dropdown, DropdownTrigger, DropdownContent, DropdownItem, DropdownLabel, DropdownSeparator } from "@/components/ui/dropdown";
import { Badge } from "@/components/ui/badge";

export function UserNav() {
  const { user, logout } = useAuth();
  const navigate = useNavigate();

  if (!user) return null;

  const initials = user.name
    .split(" ")
    .map((n) => n[0])
    .join("")
    .substring(0, 2)
    .toUpperCase();

  const handleLogout = () => {
    logout();
    navigate("/login");
  };

  return (
    <Dropdown>
      <DropdownTrigger asChild>
        <button
          type="button"
          aria-label="User account menu"
          className="flex items-center space-x-2 rounded-full p-0.5 hover:ring-2 hover:ring-ring focus:outline-none focus:ring-2 focus:ring-ring transition-all"
        >
          {user.avatarUrl ? (
            <img
              src={user.avatarUrl}
              alt={user.name}
              className="h-8 w-8 rounded-full object-cover border border-border"
            />
          ) : (
            <div className="flex h-8 w-8 items-center justify-center rounded-full bg-primary text-primary-foreground text-xs font-semibold">
              {initials || <UserIcon className="h-4 w-4" />}
            </div>
          )}
        </button>
      </DropdownTrigger>

      <DropdownContent align="right" className="w-56 p-1">
        <DropdownLabel>
          <div className="flex flex-col space-y-1">
            <p className="text-sm font-medium leading-none">{user.name}</p>
            <p className="text-xs leading-none text-muted-foreground truncate">{user.email}</p>
          </div>
          <div className="mt-2 flex flex-wrap gap-1">
            {user.roles.map((role) => (
              <Badge key={role} variant="secondary" className="text-[10px] py-0 px-1 font-mono">
                {role}
              </Badge>
            ))}
          </div>
        </DropdownLabel>
        <DropdownSeparator />
        <DropdownItem onClick={() => navigate("/settings")}>
          <Settings className="mr-2 h-4 w-4 text-muted-foreground" />
          <span>Platform Settings</span>
        </DropdownItem>
        <DropdownItem onClick={() => window.open("/docs", "_blank")}>
          <ExternalLink className="mr-2 h-4 w-4 text-muted-foreground" />
          <span>API Documentation</span>
        </DropdownItem>
        <DropdownSeparator />
        <DropdownItem destructive onClick={handleLogout}>
          <LogOut className="mr-2 h-4 w-4 text-destructive" />
          <span>Log out</span>
        </DropdownItem>
      </DropdownContent>
    </Dropdown>
  );
}
