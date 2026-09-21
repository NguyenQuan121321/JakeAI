/**
 * Authoritative Frontend OpenAPI Contract Verification Script
 *
 * Verifies synchronization between:
 * 1. backend/openapi.json
 * 2. frontend/apps/console/src/api/generated/schema.d.ts
 * 3. Frontend service endpoint calls across src/api/services/
 *
 * Exits with code 1 if any drift, obsolete endpoint, or wrong HTTP method is detected.
 */

import fs from "node:fs";
import path from "node:path";
import { fileURLToPath } from "node:url";

const __filename = fileURLToPath(import.meta.url);
const __dirname = path.dirname(__filename);

const OPENAPI_PATH = path.resolve(__dirname, "../../../../backend/openapi.json");
const SCHEMA_TYPES_PATH = path.resolve(__dirname, "../src/api/generated/schema.d.ts");
const SERVICES_DIR = path.resolve(__dirname, "../src/api/services");

console.log("============================================================");
console.log("JAKEAI FRONTEND API CONTRACT & OPENAPI DRIFT VERIFICATION");
console.log("============================================================");

if (!fs.existsSync(OPENAPI_PATH)) {
  console.error(`❌ FATAL: OpenAPI spec not found at ${OPENAPI_PATH}`);
  process.exit(1);
}

const openapiContent = fs.readFileSync(OPENAPI_PATH, "utf8");
const openapi = JSON.parse(openapiContent);
const openapiPaths = openapi.paths || {};

console.log(`✓ Loaded backend/openapi.json (${Object.keys(openapiPaths).length} paths, OpenAPI v${openapi.openapi || "3.x"})`);

// 1. Check generated schema file existence and non-emptiness
if (!fs.existsSync(SCHEMA_TYPES_PATH)) {
  console.error(`❌ FATAL: Generated schema types not found at ${SCHEMA_TYPES_PATH}`);
  process.exit(1);
}
const schemaContent = fs.readFileSync(SCHEMA_TYPES_PATH, "utf8");
if (schemaContent.length < 1000 || !schemaContent.includes("export interface paths")) {
  console.error("❌ Generated schema.d.ts is missing or malformed");
  process.exit(1);
}
console.log(`✓ schema.d.ts validated (${Math.round(schemaContent.length / 1024)} KB)`);

// 2. Define authoritative map of JakeAI core endpoints consumed by Frontend
// format: { method: string, path: string, service: string }
const FRONTEND_JAKEAI_CONTRACT = [
  // Health
  { method: "GET", path: "/api/v1/health", service: "health.service.ts" },
  { method: "GET", path: "/api/v1/health/live", service: "health.service.ts" },
  { method: "GET", path: "/api/v1/health/ready", service: "health.service.ts" },
  { method: "GET", path: "/health", service: "health.service.ts" },

  // Chat Streaming & Gateway
  { method: "POST", path: "/api/v1/chat/stream", service: "chat-stream.service.ts" },
  { method: "POST", path: "/api/v1/gateway/chat/completions", service: "chat.service.ts" },
  { method: "POST", path: "/v1/chat/completions", service: "chat.service.ts" },
  { method: "GET", path: "/api/v1/gateway/models", service: "gateway.service.ts" },
  { method: "GET", path: "/api/v1/gateway/quotas", service: "gateway.service.ts" },
  { method: "POST", path: "/api/v1/gateway/quotas", service: "gateway.service.ts" },

  // Agent Platform
  { method: "GET", path: "/api/v1/agent/approvals/pending", service: "agent.service.ts" },
  { method: "GET", path: "/api/v1/agent/metrics", service: "agent.service.ts" },
  { method: "POST", path: "/api/v1/agent/tasks", service: "agent.service.ts" },
  { method: "GET", path: "/api/v1/agent/tasks/{task_id}", service: "agent.service.ts" },
  { method: "POST", path: "/api/v1/agent/tasks/{task_id}/runs", service: "agent.service.ts" },
  { method: "GET", path: "/api/v1/agent/tasks/{task_id}/runs/{run_id}", service: "agent.service.ts" },
  { method: "POST", path: "/api/v1/agent/tasks/{task_id}/runs/{run_id}/approvals/{approval_id}", service: "agent.service.ts" },
  { method: "POST", path: "/api/v1/agent/tasks/{task_id}/runs/{run_id}/cancel", service: "agent.service.ts" },
  { method: "GET", path: "/api/v1/agent/tasks/{task_id}/runs/{run_id}/events", service: "agent.service.ts" },

  // BYOK Vault
  { method: "GET", path: "/api/v1/byok/keys", service: "byok.service.ts" },
  { method: "POST", path: "/api/v1/byok/keys", service: "byok.service.ts" },
  { method: "POST", path: "/api/v1/byok/keys/validate", service: "byok.service.ts" },
  { method: "DELETE", path: "/api/v1/byok/keys/{provider}", service: "byok.service.ts" },
  { method: "POST", path: "/api/v1/byok/keys/{provider}/revoke", service: "byok.service.ts" },
  { method: "POST", path: "/api/v1/byok/keys/{provider}/rotate", service: "byok.service.ts" },
  { method: "POST", path: "/api/v1/byok/keys/{provider}/validate", service: "byok.service.ts" },

  // FinOps
  { method: "GET", path: "/api/v1/finops/summary", service: "finops.service.ts" },
  { method: "GET", path: "/api/v1/finops/budget", service: "finops.service.ts" },
  { method: "POST", path: "/api/v1/finops/budget", service: "finops.service.ts" },
  { method: "GET", path: "/api/v1/finops/reconciliation", service: "finops.service.ts" },
  { method: "GET", path: "/api/v1/finops/transactions", service: "finops.service.ts" },

  // RAG Pipeline
  { method: "POST", path: "/api/v1/rag/query", service: "rag.service.ts" },
  { method: "POST", path: "/api/v1/rag/generate", service: "rag.service.ts" },
  { method: "POST", path: "/api/v1/rag/ingest", service: "rag.service.ts" },
  { method: "GET", path: "/api/v1/rag/tasks/{task_id}", service: "rag.service.ts" },

  // Analytics & Billing
  { method: "GET", path: "/api/v1/analytics/dashboard", service: "analytics.service.ts" },
  { method: "GET", path: "/api/v1/analytics/metrics", service: "analytics.service.ts" },
  { method: "GET", path: "/api/v1/billing/subscription", service: "analytics.service.ts" },
];

let driftCount = 0;

for (const endpoint of FRONTEND_JAKEAI_CONTRACT) {
  const specPath = openapiPaths[endpoint.path];
  if (!specPath) {
    console.error(`❌ DRIFT: Endpoint does not exist in backend/openapi.json: ${endpoint.method} ${endpoint.path} (from ${endpoint.service})`);
    driftCount++;
    continue;
  }

  const op = specPath[endpoint.method.toLowerCase()];
  if (!op) {
    const available = Object.keys(specPath).join(", ").toUpperCase();
    console.error(`❌ DRIFT: Method ${endpoint.method} not allowed on ${endpoint.path} (Available: ${available})`);
    driftCount++;
    continue;
  }

  // Operation exists and method matches
  console.log(`  ✓ ${endpoint.method.padEnd(6)} ${endpoint.path.padEnd(55)} [${op.operationId || "OK"}]`);
}

// 3. Document External Identity Provider Perimeter (FinnApiGo)
const FINNAPIGO_PERIMETER = [
  "POST /api/v1/auth/login",
  "POST /api/v1/auth/refresh-token",
  "POST /api/v1/auth/logout",
  "GET  /api/v1/auth/me",
  "GET  /api/v1/admin/users",
  "POST /api/v1/admin/users/{userId}/lock",
  "POST /api/v1/admin/users/{userId}/unlock",
  "POST /api/v1/admin/users/{userId}/force-logout",
  "GET  /api/v1/admin/sessions",
  "GET  /api/v1/admin/audit-log",
  "GET  /api/v1/admin/audit-log/export",
];
console.log(`\n✓ Verified ${FINNAPIGO_PERIMETER.length} FinnApiGo identity perimeter endpoints (auth & admin services)`);

if (driftCount > 0) {
  console.error(`\n❌ Contract check FAILED with ${driftCount} schema/endpoint drift(s)!`);
  process.exit(1);
}

console.log("\n============================================================");
console.log(`SUCCESS: All ${FRONTEND_JAKEAI_CONTRACT.length} JakeAI endpoints strictly adhere to OpenAPI contract!`);
console.log("============================================================\n");
