import type { LucideIcon } from "lucide-react";

export type SemanticStatus =
  | "idle"
  | "queued"
  | "running"
  | "paused"
  | "waiting_approval"
  | "completed"
  | "failed"
  | "cancelled"
  | "blocked"
  | "degraded"
  | "healthy"
  | "unknown";

export type StatusCategory =
  | "neutral"
  | "info"
  | "warning"
  | "destructive"
  | "success";

export interface StatusDefinition {
  status: SemanticStatus;
  label: string;
  description: string;
  category: StatusCategory;
  icon: LucideIcon;
  badgeClasses: string;
  dotClasses: string;
  iconClasses: string;
  ariaLabel: string;
}
