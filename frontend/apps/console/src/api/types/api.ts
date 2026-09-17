/**
 * Core API Client & Transport Layer Types
 */

export type HttpMethod = "GET" | "POST" | "PUT" | "PATCH" | "DELETE" | "HEAD" | "OPTIONS";

export interface RequestOptions<TBody = unknown> {
  method?: HttpMethod;
  headers?: Record<string, string>;
  params?: Record<string, string | number | boolean | undefined | null>;
  body?: TBody;
  timeoutMs?: number;
  retry?: boolean;
  maxRetries?: number;
  correlationId?: string;
  tenantId?: string;
  skipAuth?: boolean;
  signal?: AbortSignal;
}

export interface RequestMetadata {
  method: HttpMethod;
  url: string;
  startTime: number;
  durationMs: number;
  status: number;
  correlationId: string;
  requestId?: string;
}

export interface ApiResponse<TData = unknown> {
  data: TData;
  status: number;
  statusText: string;
  headers: Headers;
  metadata: RequestMetadata;
}

/**
 * Standard FastAPI Validation Error item in 422 responses
 */
export interface FastAPIValidationErrorItem {
  loc: (string | number)[];
  msg: string;
  type: string;
}

export interface FastAPIValidationErrorResponse {
  detail: FastAPIValidationErrorItem[] | string;
}

/**
 * Normalized Upstream Provider Error structure (app.providers.errors.ProviderError)
 */
export interface ProviderErrorDetail {
  message: string;
  type: string;
  provider: string;
  model?: string;
}

export interface ProviderErrorResponse {
  error: ProviderErrorDetail;
}

/**
 * FinnApiGo Standard Response Envelope (internal/response/response.go)
 */
export interface FinnApiResponse<T = unknown> {
  code: number;
  message: string;
  data: T;
}
