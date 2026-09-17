/**
 * Comprehensive ApiClient Unit & Integration Tests
 *
 * Tests:
 * - Successful GET & POST
 * - 401 Unauthorized & Token Refresh
 * - 403 Forbidden
 * - 404 Not Found
 * - 422 Unprocessable Entity (FastAPI format)
 * - 429 Rate Limiting (Retry-After)
 * - 500 Internal Server Error (suppressed stack trace)
 * - 503 Service Unavailable (safe retry behavior)
 * - Timeout handling
 * - Network failure
 * - Correlation ID preservation
 * - Zero token leakage
 */

import { describe, it, expect, beforeEach, vi } from "vitest";
import { http, HttpResponse } from "msw";
import { server } from "@/mocks/server";
import { ApiClient } from "@/api/client/http-client";
import { ApiError } from "@/api/client/api-error";
import { tokenStore } from "@/api/auth/token-store";

describe("ApiClient HTTP Abstraction & Error Normalization", () => {
  let client: ApiClient;

  beforeEach(() => {
    client = new ApiClient({ baseUrl: "https://api.jakeai.internal" });
    tokenStore.clear();
  });

  it("successfully performs GET request and parses JSON response", async () => {
    server.use(
      http.get("https://api.jakeai.internal/test-get", () => {
        return HttpResponse.json({ status: "ok", count: 42 });
      })
    );

    const res = await client.get<{ status: string; count: number }>("/test-get");
    expect(res.status).toBe(200);
    expect(res.data.status).toBe("ok");
    expect(res.data.count).toBe(42);
    expect(res.metadata.correlationId).toBeDefined();
  });

  it("successfully performs POST request with JSON payload and generates correlation ID", async () => {
    let capturedCorrelationId: string | null = null;
    let capturedBody: unknown = null;

    server.use(
      http.post("https://api.jakeai.internal/test-post", async ({ request }) => {
        capturedCorrelationId = request.headers.get("X-Correlation-ID");
        capturedBody = await request.json();
        return HttpResponse.json({ created: true }, { status: 201 });
      })
    );

    const res = await client.post<{ created: boolean }>("/test-post", { name: "test-task" });
    expect(res.status).toBe(201);
    expect(res.data.created).toBe(true);
    expect(capturedCorrelationId).toBeDefined();
    expect(capturedBody).toEqual({ name: "test-task" });
  });

  it("preserves correlation ID from response headers", async () => {
    server.use(
      http.get("https://api.jakeai.internal/test-corr", () => {
        return HttpResponse.json(
          { ok: true },
          { headers: { "X-Correlation-ID": "server-corr-9999" } }
        );
      })
    );

    const res = await client.get("/test-corr");
    expect(res.metadata.correlationId).toBe("server-corr-9999");
  });

  it("normalizes 401 Unauthorized and attempts single-flight token refresh", async () => {
    let callCount = 0;
    tokenStore.setTokens({ accessToken: "expired-token", refreshToken: "valid-refresh" });

    const refreshMock = vi.fn().mockImplementation(async () => {
      tokenStore.setTokens({ accessToken: "new-access-token", refreshToken: "valid-refresh" });
      return "new-access-token";
    });
    client.setRefreshTokenHandler(refreshMock);

    server.use(
      http.get("https://api.jakeai.internal/protected", ({ request }) => {
        callCount++;
        const auth = request.headers.get("Authorization");
        if (auth === "Bearer new-access-token") {
          return HttpResponse.json({ secret: "data" });
        }
        return HttpResponse.json({ detail: "Token expired" }, { status: 401 });
      })
    );

    const res = await client.get<{ secret: string }>("/protected");
    expect(res.data.secret).toBe("data");
    expect(refreshMock).toHaveBeenCalledTimes(1);
    expect(callCount).toBe(2);
  });

  it("normalizes 403 Forbidden with proper code and message", async () => {
    server.use(
      http.post("https://api.jakeai.internal/forbidden-action", () => {
        return HttpResponse.json(
          { detail: "Insufficient permissions. Required: agent:write" },
          { status: 403 }
        );
      })
    );

    await expect(client.post("/forbidden-action", {})).rejects.toSatisfy((err: unknown) => {
      expect(err).toBeInstanceOf(ApiError);
      const apiErr = err as ApiError;
      expect(apiErr.status).toBe(403);
      expect(apiErr.code).toBe("FORBIDDEN");
      expect(apiErr.isForbidden).toBe(true);
      expect(apiErr.message).toContain("Insufficient permissions");
      return true;
    });
  });

  it("normalizes 404 Not Found", async () => {
    server.use(
      http.get("https://api.jakeai.internal/missing-resource", () => {
        return HttpResponse.json({ detail: "Task not found" }, { status: 404 });
      })
    );

    await expect(client.get("/missing-resource")).rejects.toSatisfy((err: unknown) => {
      expect(err).toBeInstanceOf(ApiError);
      const apiErr = err as ApiError;
      expect(apiErr.status).toBe(404);
      expect(apiErr.isNotFound).toBe(true);
      expect(apiErr.code).toBe("NOT_FOUND");
      return true;
    });
  });

  it("normalizes 422 Unprocessable Entity (FastAPI validation error format)", async () => {
    server.use(
      http.post("https://api.jakeai.internal/validate-me", () => {
        return HttpResponse.json(
          {
            detail: [
              {
                loc: ["body", "temperature"],
                msg: "ensure this value is less than or equal to 2.0",
                type: "value_error.number.not_le",
              },
            ],
          },
          { status: 422 }
        );
      })
    );

    await expect(client.post("/validate-me", { temperature: 5.0 })).rejects.toSatisfy((err: unknown) => {
      expect(err).toBeInstanceOf(ApiError);
      const apiErr = err as ApiError;
      expect(apiErr.status).toBe(422);
      expect(apiErr.isValidationError).toBe(true);
      expect(apiErr.code).toBe("VALIDATION_ERROR");
      expect(apiErr.validationErrors).toHaveLength(1);
      expect(apiErr.validationErrors![0].loc).toEqual(["body", "temperature"]);
      expect(apiErr.message).toContain("temperature");
      return true;
    });
  });

  it("normalizes 429 Rate Limited and extracts Retry-After header", async () => {
    server.use(
      http.post("https://api.jakeai.internal/rate-limited", () => {
        return HttpResponse.json(
          { detail: "Rate limit exceeded" },
          {
            status: 429,
            headers: { "Retry-After": "30" },
          }
        );
      })
    );

    await expect(client.post("/rate-limited", {})).rejects.toSatisfy((err: unknown) => {
      expect(err).toBeInstanceOf(ApiError);
      const apiErr = err as ApiError;
      expect(apiErr.status).toBe(429);
      expect(apiErr.isRateLimited).toBe(true);
      expect(apiErr.code).toBe("RATE_LIMITED");
      expect(apiErr.retryAfterSeconds).toBe(30);
      return true;
    });
  });

  it("normalizes 500 Internal Server Error without exposing stack trace", async () => {
    server.use(
      http.get("https://api.jakeai.internal/crash", () => {
        return HttpResponse.json(
          { trace: "Traceback (most recent call last)... File 'app.py', line 99" },
          { status: 500 }
        );
      })
    );

    await expect(client.get("/crash", { retry: false })).rejects.toSatisfy((err: unknown) => {
      expect(err).toBeInstanceOf(ApiError);
      const apiErr = err as ApiError;
      expect(apiErr.status).toBe(500);
      expect(apiErr.isServerError).toBe(true);
      expect(apiErr.code).toBe("INTERNAL_SERVER_ERROR");
      // Message must be sanitized, not raw python trace
      expect(apiErr.message).not.toContain("Traceback");
      expect(apiErr.message).toBe("An unexpected server error occurred. Please try again later.");
      return true;
    });
  });

  it("retries transient 503 Service Unavailable on safe GET requests", async () => {
    let attempts = 0;
    server.use(
      http.get("https://api.jakeai.internal/flaky", () => {
        attempts++;
        if (attempts < 2) {
          return HttpResponse.json({ error: "Unavailable" }, { status: 503 });
        }
        return HttpResponse.json({ recovered: true });
      })
    );

    const res = await client.get<{ recovered: boolean }>("/flaky", { maxRetries: 2 });
    expect(res.data.recovered).toBe(true);
    expect(attempts).toBe(2);
  });

  it("never retries non-idempotent POST requests on 503 by default", async () => {
    let attempts = 0;
    server.use(
      http.post("https://api.jakeai.internal/charge", () => {
        attempts++;
        return HttpResponse.json({ error: "Unavailable" }, { status: 503 });
      })
    );

    await expect(client.post("/charge", {})).rejects.toSatisfy((err: unknown) => {
      expect(err).toBeInstanceOf(ApiError);
      expect((err as ApiError).status).toBe(503);
      return true;
    });

    expect(attempts).toBe(1); // strictly 1 attempt!
  });

  it("handles request timeout and produces normalized timeout ApiError", async () => {
    server.use(
      http.get("https://api.jakeai.internal/hang", async () => {
        await new Promise((resolve) => setTimeout(resolve, 500));
        return HttpResponse.json({ done: true });
      })
    );

    await expect(client.get("/hang", { timeoutMs: 50, retry: false })).rejects.toSatisfy((err: unknown) => {
      expect(err).toBeInstanceOf(ApiError);
      const apiErr = err as ApiError;
      expect(apiErr.status).toBe(408);
      expect(apiErr.isTimeout).toBe(true);
      expect(apiErr.code).toBe("TIMEOUT");
      return true;
    });
  });

  it("handles network disconnection and produces normalized network ApiError", async () => {
    server.use(
      http.get("https://api.jakeai.internal/offline", () => {
        return HttpResponse.error();
      })
    );

    await expect(client.get("/offline", { retry: false })).rejects.toSatisfy((err: unknown) => {
      expect(err).toBeInstanceOf(ApiError);
      const apiErr = err as ApiError;
      expect(apiErr.status).toBe(0);
      expect(apiErr.isNetworkError).toBe(true);
      expect(apiErr.code).toBe("NETWORK_ERROR");
      return true;
    });
  });

  it("never logs tokens or embeds bearer secrets into error properties", async () => {
    tokenStore.setTokens({ accessToken: "super-secret-jwt-token-12345" });

    server.use(
      http.get("https://api.jakeai.internal/sensitive-fail", () => {
        return HttpResponse.json({ detail: "Invalid token" }, { status: 401 });
      })
    );

    try {
      await client.get("/sensitive-fail", { skipAuth: false });
    } catch (err) {
      expect(err).toBeInstanceOf(ApiError);
      const str = JSON.stringify(err);
      expect(str).not.toContain("super-secret-jwt-token-12345");
      expect((err as ApiError).message).not.toContain("super-secret-jwt-token-12345");
    }
  });
});
