/**
 * Normalized API Error Abstraction
 *
 * Transforms diverse backend error envelopes (FastAPI HTTPException,
 * 422 Validation Errors, ProviderError, FinnApiGo APIResponse, network failures)
 * into a single unified ApiError instance.
 *
 * Invariant: Never exposes internal stack traces or secrets to users.
 */

import type { FastAPIValidationErrorItem } from "../types/api";

export interface ApiErrorOptions {
  status: number;
  code: string;
  message: string;
  requestId?: string;
  correlationId?: string;
  details?: unknown;
  retryAfterSeconds?: number;
  isNetworkError?: boolean;
  isTimeout?: boolean;
}

export class ApiError extends Error {
  public readonly status: number;
  public readonly code: string;
  public readonly requestId?: string;
  public readonly correlationId?: string;
  public readonly details?: unknown;
  public readonly retryAfterSeconds?: number;
  public readonly isNetworkError: boolean;
  public readonly isTimeout: boolean;

  constructor(options: ApiErrorOptions) {
    super(options.message);
    this.name = "ApiError";
    this.status = options.status;
    this.code = options.code;
    this.requestId = options.requestId;
    this.correlationId = options.correlationId;
    this.details = options.details;
    this.retryAfterSeconds = options.retryAfterSeconds;
    this.isNetworkError = options.isNetworkError ?? (options.status === 0);
    this.isTimeout = options.isTimeout ?? (options.status === 408);

    // Maintain standard error prototype chain in transpiled ES
    Object.setPrototypeOf(this, ApiError.prototype);
  }

  get isAuthError(): boolean {
    return this.status === 401;
  }

  get isForbidden(): boolean {
    return this.status === 403;
  }

  get isNotFound(): boolean {
    return this.status === 404;
  }

  get isValidationError(): boolean {
    return this.status === 422;
  }

  get isRateLimited(): boolean {
    return this.status === 429;
  }

  get isServerError(): boolean {
    return this.status >= 500 && this.status < 600;
  }

  /**
   * Extract validation error items if status is 422
   */
  get validationErrors(): FastAPIValidationErrorItem[] | null {
    if (!this.isValidationError || !this.details) return null;
    if (typeof this.details === "object" && this.details !== null && "detail" in this.details) {
      const detail = (this.details as { detail: unknown }).detail;
      if (Array.isArray(detail)) {
        return detail as FastAPIValidationErrorItem[];
      }
    }
    return null;
  }

  /**
   * Factory to construct ApiError from an HTTP response and parsed payload
   */
  public static fromHttpResponse(
    status: number,
    body: unknown,
    headers?: Headers,
    correlationId?: string
  ): ApiError {
    const resCorrelationId =
      headers?.get("x-correlation-id") ||
      headers?.get("x-request-id") ||
      correlationId;
    const requestId = headers?.get("x-request-id") || resCorrelationId;

    let retryAfterSeconds: number | undefined;
    const retryHeader = headers?.get("retry-after");
    if (retryHeader) {
      const parsed = parseInt(retryHeader, 10);
      if (!isNaN(parsed) && parsed > 0) {
        retryAfterSeconds = parsed;
      }
    }

    let code = `HTTP_${status}`;
    let message = `Request failed with status ${status}`;
    let details: unknown = body;

    // 1. Check for FastAPI ValidationError (422)
    if (status === 422 && body && typeof body === "object" && "detail" in body) {
      code = "VALIDATION_ERROR";
      const detail = (body as { detail: unknown }).detail;
      if (Array.isArray(detail) && detail.length > 0) {
        const first = detail[0] as FastAPIValidationErrorItem;
        const fieldPath = Array.isArray(first.loc) ? first.loc.filter((l) => l !== "body").join(".") : "";
        message = fieldPath ? `Invalid input for ${fieldPath}: ${first.msg}` : `Invalid input: ${first.msg}`;
      } else if (typeof detail === "string") {
        message = detail;
      }
    }
    // 2. Check for Upstream ProviderError ({ error: { message, type, provider, model } })
    else if (body && typeof body === "object" && "error" in body) {
      const errObj = (body as { error: Record<string, unknown> }).error;
      code = typeof errObj.type === "string" ? errObj.type.toUpperCase() : code;
      message = typeof errObj.message === "string" ? errObj.message : message;
      details = errObj;
    }
    // 3. Check for FastAPI standard HTTPException ({ detail: string })
    else if (body && typeof body === "object" && "detail" in body) {
      const detail = (body as { detail: unknown }).detail;
      if (typeof detail === "string") {
        message = detail;
        if (status === 401) code = "UNAUTHORIZED";
        else if (status === 403) code = "FORBIDDEN";
        else if (status === 404) code = "NOT_FOUND";
        else if (status === 413) code = "ENTITY_TOO_LARGE";
        else if (status === 429) code = "RATE_LIMITED";
      }
    }
    // 4. Check for FinnApiGo Response Envelope ({ code, message, data })
    else if (body && typeof body === "object" && "code" in body && "message" in body) {
      const finn = body as { code: number; message: string; data?: unknown };
      message = finn.message || message;
      details = finn.data ?? details;
      if (status === 401) code = "UNAUTHORIZED";
      else if (status === 403) code = "FORBIDDEN";
      else if (status === 404) code = "NOT_FOUND";
      else if (status === 429) code = "RATE_LIMITED";
    }

    // Default status code fallbacks
    if (status === 401 && code === `HTTP_401`) code = "UNAUTHORIZED";
    if (status === 403 && code === `HTTP_403`) code = "FORBIDDEN";
    if (status === 404 && code === `HTTP_404`) code = "NOT_FOUND";
    if (status === 429 && code === `HTTP_429`) code = "RATE_LIMITED";
    if (status === 500 && code === `HTTP_500`) {
      code = "INTERNAL_SERVER_ERROR";
      message = "An unexpected server error occurred. Please try again later.";
    }
    if (status === 503 && code === `HTTP_503`) {
      code = "SERVICE_UNAVAILABLE";
      message = "The requested service is temporarily unavailable.";
    }

    return new ApiError({
      status,
      code,
      message,
      requestId,
      correlationId: resCorrelationId,
      details,
      retryAfterSeconds,
    });
  }

  /**
   * Factory for network or timeout failures
   */
  public static fromNetworkError(error: unknown, correlationId?: string): ApiError {
    const isTimeout =
      error instanceof DOMException && error.name === "TimeoutError" ||
      (error instanceof Error && error.name === "AbortError" && error.message.includes("timeout"));

    if (isTimeout) {
      return new ApiError({
        status: 408,
        code: "TIMEOUT",
        message: "The request timed out. Please check your network connection and retry.",
        correlationId,
        isTimeout: true,
      });
    }

    const message =
      error instanceof Error && error.message
        ? error.message.includes("Failed to fetch")
          ? "Network connection lost. Please verify your internet connection."
          : error.message
        : "Network communication failure.";

    return new ApiError({
      status: 0,
      code: "NETWORK_ERROR",
      message,
      correlationId,
      isNetworkError: true,
    });
  }
}
