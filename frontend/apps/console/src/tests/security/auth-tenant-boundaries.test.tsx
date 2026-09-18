/**
 * Security, Auth & Tenant Boundaries Vitest Test Suite
 *
 * Mandated Verification Criteria:
 * 1. HTTP 401 Unauthorized handling (token purging, session expiry notification)
 * 2. HTTP 403 Forbidden handling (tenant boundary isolation, permission denial alert)
 * 3. Tenant context isolation (authoritative X-Tenant-ID header injection)
 */

import { describe, it, expect, beforeEach, afterEach, vi } from "vitest";
import { http, HttpResponse } from "msw";
import { server } from "@/mocks/server";
import { tokenStore } from "@/api/auth/token-store";
import { ragService } from "@/api/services/rag.service";
import { byokService } from "@/api/services/byok.service";
import { ApiError } from "@/api/client/api-error";

describe("FE-05 Security, Auth & Tenant Boundaries Suite", () => {
  beforeEach(() => {
    localStorage.clear();
    sessionStorage.clear();
    tokenStore.setTokens({ accessToken: "initial-valid-token" });
    tokenStore.setActiveTenantId("tenant_jakeai_core");
  });

  afterEach(() => {
    server.resetHandlers();
    localStorage.clear();
    sessionStorage.clear();
    vi.restoreAllMocks();
  });

  // Criterion 1: HTTP 401 Unauthorized Interception & Central Listener
  it("intercepts HTTP 401 Unauthorized, purges credentials, and notifies unauthorized listeners", async () => {
    const unauthorizedListener = vi.fn();
    const unsub = tokenStore.subscribeUnauthorized(unauthorizedListener);

    // Mock endpoint returning 401 Unauthorized (and refresh fails or absent)
    server.use(
      http.post("*/api/v1/rag/query", () => {
        return HttpResponse.json(
          { detail: "Token expired or signature invalid" },
          { status: 401 }
        );
      }),
      http.post("/api/v1/rag/query", () => {
        return HttpResponse.json(
          { detail: "Token expired or signature invalid" },
          { status: 401 }
        );
      })
    );

    let caughtError: ApiError | null = null;
    try {
      await ragService.query({
        query: "enterprise security check",
        top_k: 5,
        select_context: false,
        max_context_tokens: 800,
      });
    } catch (err: unknown) {
      caughtError = err as ApiError;
    }

    // Must capture 401 ApiError
    expect(caughtError).not.toBeNull();
    expect(caughtError?.status).toBe(401);

    // Central token store cleared and listeners notified
    expect(unauthorizedListener).toHaveBeenCalledTimes(1);
    expect(tokenStore.getAccessToken()).toBeNull();

    unsub();
  });

  // Criterion 2: HTTP 403 Forbidden Tenant Boundary Violation
  it("intercepts HTTP 403 Forbidden and preserves tenant isolation error feedback", async () => {
    server.use(
      http.get("*/api/v1/byok/keys", () => {
        return HttpResponse.json(
          { detail: "Cross-tenant access forbidden. Boundary violation detected for tenant_rogue." },
          { status: 403 }
        );
      }),
      http.get("/api/v1/byok/keys", () => {
        return HttpResponse.json(
          { detail: "Cross-tenant access forbidden. Boundary violation detected for tenant_rogue." },
          { status: 403 }
        );
      })
    );

    let caughtError: ApiError | null = null;
    try {
      await byokService.listKeys();
    } catch (err: unknown) {
      caughtError = err as ApiError;
    }

    expect(caughtError).not.toBeNull();
    expect(caughtError?.status).toBe(403);
    expect(caughtError?.message).toContain("Cross-tenant access forbidden");
  });

  // Criterion 3: Tenant Context Isolation & X-Tenant-ID Header Injection
  it("authoritatively injects X-Tenant-ID and Bearer Authorization on all outgoing requests", async () => {
    let capturedTenantHeader: string | null = null;
    let capturedAuthHeader: string | null = null;

    server.use(
      http.post("*/api/v1/rag/query", ({ request }) => {
        capturedTenantHeader = request.headers.get("X-Tenant-ID");
        capturedAuthHeader = request.headers.get("Authorization");
        return HttpResponse.json({
          query: "test",
          tenant_id: "tenant_jakeai_core",
          chunks: [],
          latency_ms: 10,
          total_candidates: 0,
        });
      }),
      http.post("/api/v1/rag/query", ({ request }) => {
        capturedTenantHeader = request.headers.get("X-Tenant-ID");
        capturedAuthHeader = request.headers.get("Authorization");
        return HttpResponse.json({
          query: "test",
          tenant_id: "tenant_jakeai_core",
          chunks: [],
          latency_ms: 10,
          total_candidates: 0,
        });
      })
    );

    await ragService.query({
      query: "perimeter test",
      top_k: 5,
      select_context: false,
      max_context_tokens: 800,
    });

    // Assert headers sent to backend
    expect(capturedTenantHeader).toBe("tenant_jakeai_core");
    expect(capturedAuthHeader).toBe("Bearer initial-valid-token");

    // Switch tenant context and verify dynamic update
    tokenStore.setActiveTenantId("tenant_acme_isolated");

    await ragService.query({
      query: "perimeter test 2",
      top_k: 5,
      select_context: false,
      max_context_tokens: 800,
    });

    expect(capturedTenantHeader).toBe("tenant_acme_isolated");
  });
});
