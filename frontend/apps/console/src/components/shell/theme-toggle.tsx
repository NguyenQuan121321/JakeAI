import { Sun, Moon, Laptop } from "lucide-react";
import { useTheme } from "@/context/theme-context";
import { Dropdown, DropdownTrigger, DropdownContent, DropdownItem } from "@/components/ui/dropdown";

export function ThemeToggle() {
  const { theme, setTheme } = useTheme();

  return (
    <Dropdown>
      <DropdownTrigger asChild>
        <button
          type="button"
          aria-label="Toggle theme"
          className="rounded-full p-2 text-muted-foreground hover:bg-accent hover:text-accent-foreground focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-ring transition-colors"
        >
          <Sun className="h-5 w-5 rotate-0 scale-100 transition-transform dark:-rotate-90 dark:scale-0" />
          <Moon className="absolute h-5 w-5 rotate-90 scale-0 transition-transform dark:rotate-0 dark:scale-100 top-2 left-2" />
          <span className="sr-only">Toggle theme</span>
        </button>
      </DropdownTrigger>
      <DropdownContent align="right" className="w-36">
        <DropdownItem onClick={() => setTheme("light")}>
          <Sun className="mr-2 h-4 w-4" />
          <span>Light {theme === "light" ? "✓" : ""}</span>
        </DropdownItem>
        <DropdownItem onClick={() => setTheme("dark")}>
          <Moon className="mr-2 h-4 w-4" />
          <span>Dark {theme === "dark" ? "✓" : ""}</span>
        </DropdownItem>
        <DropdownItem onClick={() => setTheme("system")}>
          <Laptop className="mr-2 h-4 w-4" />
          <span>System {theme === "system" ? "✓" : ""}</span>
        </DropdownItem>
      </DropdownContent>
    </Dropdown>
  );
}
