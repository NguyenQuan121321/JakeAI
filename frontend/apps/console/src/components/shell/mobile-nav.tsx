import { Drawer } from "@/components/ui/drawer";
import { Sidebar } from "@/components/shell/sidebar";

export function MobileNav({
  open,
  onOpenChange,
}: {
  open: boolean;
  onOpenChange: (open: boolean) => void;
}) {
  return (
    <Drawer
      open={open}
      onOpenChange={onOpenChange}
      position="left"
      title="JakeAI Console"
      className="p-0 max-w-xs"
    >
      <div className="h-full">
        <Sidebar
          isCollapsed={false}
          onNavigate={() => onOpenChange(false)}
        />
      </div>
    </Drawer>
  );
}
