/**
 * Enterprise Centralized HTTP Client Abstraction
 *
 * Responsibilities:
 * - Centralized base URL configuration
 * - Request headers, content negotiation, and correlation tracking (X-Correlation-ID, X-Request-ID)
 * - Safe Bearer token injection without logging
 * - Tenant context propagation (X-Tenant-ID)
 * - JSON serialization & response parsing
 * - Request timeout via AbortSignal
 * - Normalized error handling (ApiError)
 * - Safe retries for idempotent operations on 503/429/network errors
 * - Single-flight token refresh mutex on 401 Unauthorized
 */

import { ApiError } from "./api-error";
import { tokenStore } from "../auth/token-store";
import type { HttpMethod, RequestOptions, ApiResponse, RequestMetadata } from "../types/api";

export interface HttpClientConfig {
  baseUrl?: string;
  defaultTimeoutMs?: number;
  maxRetries?: number;
  onRefreshToken?: () => Promise<string | null>;
}

export class ApiClient {
  private baseUrl: string;
  private defaultTimeoutMs: number;
  private maxRetries: number;
  private refreshPromise: Promise<string | null> | null = null;
  private onRefreshToken?: () => Promise<string | null>;

  constructor(config: HttpClientConfig = {}) {
    this.baseUrl = config.baseUrl ?? (typeof import.meta !== "undefined" && import.meta.env?.VITE_API_BASE_URL ? String(import.meta.env.VITE_API_BASE_URL) : "");
    this.defaultTimeoutMs = config.defaultTimeoutMs ?? 30000;
    this.maxRetries = config.maxRetries ?? 2;
    this.onRefreshToken = config.onRefreshToken;
  }

  public setRefreshTokenHandler(handler: () => Promise<string | null>): void {
    this.onRefreshToken = handler;
  }

  public setBaseUrl(url: string): void {
    this.baseUrl = url;
  }

  public getBaseUrl(): string {
    return this.baseUrl;
  }

  /**
   * Primary HTTP request dispatcher
   */
  public async request<TData = unknown, TBody = unknown>(
    endpoint: string,
    options: RequestOptions<TBody> = {}
  ): Promise<ApiResponse<TData>> {
    const method = (options.method || "GET").toUpperCase() as HttpMethod;
    const isIdempotent = ["GET", "HEAD", "OPTIONS"].includes(method);
    const shouldRetry = options.retry ?? isIdempotent;
    const maxRetries = shouldRetry ? (options.maxRetries ?? this.maxRetries) : 0;

    let attempt = 0;
    let lastError: unknown;

    while (attempt <= maxRetries) {
      try {
        return await this.executeSingleRequest<TData, TBody>(endpoint, options, method);
      } catch (err) {
        lastError = err;

        // Never retry non-idempotent requests unless explicitly marked
        if (!shouldRetry) {
          throw err;
        }

        // Only retry on transient failures (503 Service Unavailable, 429 Rate Limit, or Network/Timeout)
        if (err instanceof ApiError) {
          const isTransient = err.status === 503 || err.status === 429 || err.isNetworkError || err.isTimeout;
          if (!isTransient || attempt >= maxRetries) {
            throw err;
          }

          // Backoff delay with jitter
          const retryAfter = err.retryAfterSeconds;
          const delayMs = retryAfter
            ? retryAfter * 1000
            : Math.min(1000 * Math.pow(2, attempt) + Math.random() * 200, 10000);

          await new Promise((resolve) => setTimeout(resolve, delayMs));
        } else {
          throw err;
        }

        attempt++;
      }
    }

    throw lastError;
  }

  /**
   * Internal single execution with 401 refresh handling
   */
  private async executeSingleRequest<TData, TBody>(
    endpoint: string,
    options: RequestOptions<TBody>,
    method: HttpMethod,
    isReplay = false
  ): Promise<ApiResponse<TData>> {
    const startTime = Date.now();
    const correlationId = options.correlationId || this.generateCorrelationId();

    // Compose Target URL
    const url = this.buildUrl(endpoint, options.params);

    // Build Headers
    const headers = new Headers(options.headers);

    if (!headers.has("Accept")) {
      headers.set("Accept", "application/json");
    }

    headers.set("X-Correlation-ID", correlationId);
    headers.set("X-Request-ID", correlationId);

    // Tenant Context Injection
    const activeTenant = options.tenantId || tokenStore.getActiveTenantId();
    if (activeTenant && !headers.has("X-Tenant-ID")) {
      headers.set("X-Tenant-ID", activeTenant);
    }

    // Centralized Bearer Token Injection
    if (!options.skipAuth && !headers.has("Authorization")) {
      const token = tokenStore.getAccessToken();
      if (token) {
        headers.set("Authorization", `Bearer ${token}`);
      }
    }

    // Body & Content-Type Serialization
    let bodyPayload: BodyInit | undefined;
    if (options.body !== undefined && method !== "GET" && method !== "HEAD") {
      if (typeof options.body === "string" || options.body instanceof FormData || options.body instanceof Blob) {
        bodyPayload = options.body;
      } else {
        headers.set("Content-Type", "application/json");
        bodyPayload = JSON.stringify(options.body);
      }
    }

    // Timeout signal handling
    const timeoutMs = options.timeoutMs ?? this.defaultTimeoutMs;
    const controller = new AbortController();
    let timeoutId: ReturnType<typeof setTimeout> | null = null;

    if (options.signal) {
      options.signal.addEventListener("abort", () => controller.abort(options.signal?.reason));
    }

    if (timeoutMs > 0) {
      timeoutId = setTimeout(() => {
        controller.abort(new DOMException("Request timed out", "TimeoutError"));
      }, timeoutMs);
    }

    let response: Response;
    try {
      response = await fetch(url, {
        method,
        headers,
        body: bodyPayload,
        signal: controller.signal,
      });
    } catch (fetchErr) {
      if (timeoutId) clearTimeout(timeoutId);
      throw ApiError.fromNetworkError(fetchErr, correlationId);
    } finally {
      if (timeoutId) clearTimeout(timeoutId);
    }

    const durationMs = Date.now() - startTime;
    const resCorrelationId =
      response.headers.get("x-correlation-id") ||
      response.headers.get("x-request-id") ||
      correlationId;
    const resRequestId = response.headers.get("x-request-id") || resCorrelationId;

    const metadata: RequestMetadata = {
      method,
      url,
      startTime,
      durationMs,
      status: response.status,
      correlationId: resCorrelationId,
      requestId: resRequestId,
    };

    // 401 Unauthorized Interception & Central Refresh Token Flow
    if (response.status === 401 && !options.skipAuth && !isReplay) {
      const refreshedToken = await this.executeTokenRefresh();
      if (refreshedToken) {
        // Replay original request with refreshed access token
        return this.executeSingleRequest<TData, TBody>(endpoint, options, method, true);
      } else {
        // Refresh failed or no refresh token; notify centralized unauthorized listener
        tokenStore.clear();
        tokenStore.notifyUnauthorized();
      }
    }

    // Parse Response Payload
    let parsedData: unknown = null;
    const contentType = response.headers.get("content-type") || "";

    if (response.status !== 204) {
      if (contentType.includes("application/json")) {
        try {
          parsedData = await response.json();
        } catch {
          parsedData = null;
        }
      } else {
        try {
          parsedData = await response.text();
        } catch {
          parsedData = null;
        }
      }
    }
    // Non-2xx Response Handling
    if (!response.ok) {
      throw ApiError.fromHttpResponse(
        response.status,
        parsedData,
        response.headers,
        resCorrelationId
      );
    }

    return {
      data: parsedData as TData,
      status: response.status,
      statusText: response.statusText,
      headers: response.headers,
      metadata,
    };
  }

  /**
   * Thread-safe single-flight refresh token coordination
   */
  private async executeTokenRefresh(): Promise<string | null> {
    if (!this.onRefreshToken) {
      return null;
    }

    const refreshToken = tokenStore.getRefreshToken();
    if (!refreshToken) {
      return null;
    }

    if (!this.refreshPromise) {
      this.refreshPromise = this.onRefreshToken()
        .then((newToken) => {
          return newToken;
        })
        .catch(() => {
          return null;
        })
        .finally(() => {
          this.refreshPromise = null;
        });
    }

    return this.refreshPromise;
  }

  private buildUrl(endpoint: string, params?: Record<string, string | number | boolean | undefined | null>): string {
    const isFullUrl = endpoint.startsWith("http://") || endpoint.startsWith("https://");
    const fallbackOrigin = "http://127.0.0.1:8000";
    const base = this.baseUrl || fallbackOrigin;

    let fullUrl = isFullUrl
      ? endpoint
      : `${base.replace(/\/$/, "")}/${endpoint.replace(/^\//, "")}`;

    if (params) {
      const searchParams = new URLSearchParams();
      for (const [key, value] of Object.entries(params)) {
        if (value !== undefined && value !== null) {
          searchParams.append(key, String(value));
        }
      }
      const qs = searchParams.toString();
      if (qs) {
        fullUrl += (fullUrl.includes("?") ? "&" : "?") + qs;
      }
    }

    return fullUrl;
  }

  private generateCorrelationId(): string {
    if (typeof crypto !== "undefined" && typeof crypto.randomUUID === "function") {
      return crypto.randomUUID();
    }
    return `corr-${Date.now()}-${Math.random().toString(36).substring(2, 9)}`;
  }

  // Convenience HTTP Verb Methods
  public get<T>(endpoint: string, options: Omit<RequestOptions, "method"> = {}): Promise<ApiResponse<T>> {
    return this.request<T>(endpoint, { ...options, method: "GET" });
  }

  public post<T, B = unknown>(endpoint: string, body?: B, options: Omit<RequestOptions<B>, "method" | "body"> = {}): Promise<ApiResponse<T>> {
    return this.request<T, B>(endpoint, { ...options, method: "POST", body });
  }

  public put<T, B = unknown>(endpoint: string, body?: B, options: Omit<RequestOptions<B>, "method" | "body"> = {}): Promise<ApiResponse<T>> {
    return this.request<T, B>(endpoint, { ...options, method: "PUT", body });
  }

  public patch<T, B = unknown>(endpoint: string, body?: B, options: Omit<RequestOptions<B>, "method" | "body"> = {}): Promise<ApiResponse<T>> {
    return this.request<T, B>(endpoint, { ...options, method: "PATCH", body });
  }

  public delete<T>(endpoint: string, options: Omit<RequestOptions, "method"> = {}): Promise<ApiResponse<T>> {
    return this.request<T>(endpoint, { ...options, method: "DELETE" });
  }
}

export const apiClient = new ApiClient();
