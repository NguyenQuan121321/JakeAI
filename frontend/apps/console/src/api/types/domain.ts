/**
 * Application Domain Types
 * 
 * Clean domain-specific abstractions derived from the authoritative OpenAPI schema (schema.d.ts).
 * Keeps generated types separate from domain abstractions while preventing duplication.
 */

import type { components, paths } from "../generated/schema";

export type Schemas = components["schemas"];

// Agent Platform
export type TaskState = Schemas["TaskState"];
export type CreateTaskRequest = Schemas["CreateTaskRequest"];
export type RunState = Schemas["RunState"];
export type CreateRunRequest = Schemas["CreateRunRequest"];
export type ApprovalRequest = Schemas["ApprovalRequest"];
export type ApprovalDecision = Schemas["ApprovalDecision"];
export type ApprovalStatus = Schemas["ApprovalStatus"];
export type AgentMetricsSnapshot = Schemas["AgentMetricsSnapshot"];

// FinOps
export type FinOpsSummary = Schemas["FinOpsSummary"];
export type FinOpsRecord = Schemas["FinOpsRecord"];
export type TenantBudget = Schemas["TenantBudget"];
export type UpdateBudgetRequest = Schemas["UpdateBudgetRequest"];
export type ReconciliationReport = Schemas["ReconciliationReport"];

// BYOK Vault
export type BYOKKeyResponse = Schemas["BYOKKeyResponse"];
export type BYOKListResponse = Schemas["BYOKListResponse"];
export type BYOKStoreRequest = Schemas["BYOKStoreRequest"];
export type BYOKValidateRequest = Schemas["BYOKValidateRequest"];
export type BYOKValidationResponse = Schemas["BYOKValidationResponse"];
export type BYOKRotateRequest = Schemas["BYOKRotateRequest"];
export type BYOKProviderItem = Schemas["BYOKProviderItem"];

// AI Gateway & Models
export type ModelListResponse = Schemas["ModelListResponse"];
export type ModelItem = Schemas["ModelItem"];
export type QuotaStatus = Schemas["QuotaStatus"];
export type UpdateQuotaRequest = Schemas["UpdateQuotaRequest"];
export type GatewayChatRequest = Schemas["GatewayChatRequest"];
export type GatewayChatResponse = Schemas["GatewayChatResponse"];

// RAG Pipeline
export type DocumentIngestRequest = Schemas["DocumentIngestRequest"];
export type DocumentIngestResponse = Schemas["DocumentIngestResponse"];
export type RAGQueryRequest = Schemas["RAGQueryRequest"];
export type RAGQueryResponse = Schemas["RAGQueryResponse"];
export type RAGGenerateRequest = Schemas["RAGGenerateRequest"];
export type RAGGenerateResponse = Schemas["RAGGenerateResponse"];
export type IngestionTaskState = Schemas["IngestionTaskState"];
export type IngestionTaskResponse = Schemas["IngestionTaskResponse"];
export type Citation = Schemas["Citation"];
export type DocumentChunk = Schemas["DocumentChunk"];

// Health & Telemetry
export type HealthResponse = Schemas["HealthResponse"];
export type AnalyticsDashboard = Schemas["AnalyticsDashboard"];
export type MetricsSnapshot = Schemas["MetricsSnapshot"];
export type SubscriptionInfo = Schemas["SubscriptionInfo"];

// Chat Stream
export type ChatStreamRequest = Schemas["ChatStreamRequest"];

// Paths & Operations shortcuts
export type ApiPaths = keyof paths;
