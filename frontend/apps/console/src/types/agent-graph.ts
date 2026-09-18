import type { Node, Edge } from "@xyflow/react";

export type CanvasNodeType =
  | "task"
  | "agent"
  | "model"
  | "rag"
  | "tool"
  | "verification"
  | "approval"
  | "result";

export type CanvasNodeStatus =
  | "idle"
  | "queued"
  | "running"
  | "waiting_approval"
  | "completed"
  | "failed"
  | "cancelled";

export interface NodeCitation {
  source: string;
  snippet?: string;
  confidence?: number;
  chunk_id?: string;
}

export interface CanvasNodeData extends Record<string, unknown> {
  id: string;
  label: string;
  category: CanvasNodeType;
  status: CanvasNodeStatus;
  description?: string;
  sublabel?: string;
  latencyMs?: number;
  executionCount?: number;
  error?: string | null;
  inputs?: Record<string, unknown>;
  outputs?: unknown;
  citations?: NodeCitation[];
  metadata?: Record<string, unknown>;
  toolName?: string;
  verdict?: "PASS" | "NEEDS_REVISION" | "FAILED" | "REJECTED";
  stepNumber?: number;
  isCurrentStep?: boolean;
  approvalId?: string;
  approvalReason?: string;
}

export type CanvasNode = Node<CanvasNodeData, CanvasNodeType>;

export interface CanvasEdge extends Edge {
  status?: CanvasNodeStatus;
}

export interface TimelineEvent {
  id: string;
  eventType: string;
  timestamp: number;
  taskId: string;
  runId: string;
  nodeId?: string;
  title: string;
  description?: string;
  status?: CanvasNodeStatus;
  durationMs?: number;
  data?: Record<string, unknown>;
}

export interface OrchestrationGraphState {
  nodes: CanvasNode[];
  edges: CanvasEdge[];
  activeNodeId: string | null;
  selectedNodeId: string | null;
}
