import type { LucideIcon } from "lucide-react";

export interface NavItem {
  title: string;
  href: string;
  icon: LucideIcon;
  badge?: string;
  roles?: string[];
  permissions?: string[];
  external?: boolean;
}

export interface NavSection {
  title: string;
  items: NavItem[];
  roles?: string[];
  permissions?: string[];
}
