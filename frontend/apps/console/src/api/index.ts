/**
 * JakeAI Single Frontend/Backend Integration Layer
 *
 * Exporting client, errors, types, domain models, services, hooks, and auth/capabilities.
 */

export * from "./types/api";
export * from "./types/domain";
export * from "./client/api-error";
export * from "./client/http-client";
export * from "./auth/token-store";
export * from "./auth/jwt";
export * from "./auth/capabilities";
export * from "./auth/tenant";
export * from "./query-client";
export * from "./services/auth.service";
export * from "./services/health.service";
export * from "./services/chat.service";
export * from "./services/gateway.service";
export * from "./services/agent.service";
export * from "./services/rag.service";
export * from "./services/byok.service";
export * from "./services/finops.service";
export * from "./services/analytics.service";
export * from "./services/providers.service";
export * from "./services/admin.service";
export * from "./hooks";
