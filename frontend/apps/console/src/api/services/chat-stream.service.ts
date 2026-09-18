/**
 * Real-time SSE Chat Streaming Controller
 *
 * Implements authoritative streaming connection to /api/v1/chat/stream.
 * Handles:
 * - Connection handshake & tenant context propagation
 * - Incremental SSE frame parsing across arbitrary chunk boundaries
 * - Event dispatching: status, token, tool_call, telemetry, done, error
 * - Clean teardown on abort, unmount, or network failure
 * - HTTP status normalization (401, 403, 413, 422, 429, 503)
 */

import { tokenStore } from "@/api/auth/token-store";
import type {
  StreamChatRequestOptions,
  SSEStatusPayload,
  SSETokenPayload,
  SSEToolCallPayload,
  SSETelemetryPayload,
  SSEDonePayload,
  SSEErrorPayload,
} from "@/types/chat";

export class ChatStreamService {
  private baseUrl: string;

  constructor() {
    this.baseUrl =
      typeof import.meta !== "undefined" && import.meta.env?.VITE_API_BASE_URL
        ? String(import.meta.env.VITE_API_BASE_URL)
        : "";
  }

  /**
   * Establish SSE connection to /api/v1/chat/stream and consume events.
   */
  public async streamChat(options: StreamChatRequestOptions): Promise<void> {
    const {
      prompt,
      conversationId,
      model,
      provider,
      signal,
      onStatus,
      onToken,
      onToolCall,
      onTelemetry,
      onDone,
      onError,
    } = options;

    const fallbackOrigin = "http://127.0.0.1:8000";
    const base = this.baseUrl || fallbackOrigin;
    const url = `${base.replace(/\/$/, "")}/api/v1/chat/stream`;

    const correlationId =
      typeof crypto !== "undefined" && typeof crypto.randomUUID === "function"
        ? crypto.randomUUID()
        : `corr-stream-${Date.now()}`;

    const headers: Record<string, string> = {
      "Content-Type": "application/json",
      Accept: "text/event-stream",
      "X-Correlation-ID": correlationId,
      "X-Request-ID": correlationId,
    };

    const token = tokenStore.getAccessToken();
    if (token) {
      headers["Authorization"] = `Bearer ${token}`;
    }

    const tenantId = tokenStore.getActiveTenantId();
    if (tenantId) {
      headers["X-Tenant-ID"] = tenantId;
    }

    const requestBody: Record<string, unknown> = {
      prompt,
      conversation_id: conversationId,
    };

    if (model || provider) {
      requestBody.parameters = {
        ...(model ? { model } : {}),
        ...(provider ? { provider } : {}),
      };
    }

    let response: Response;
    try {
      response = await fetch(url, {
        method: "POST",
        headers,
        body: JSON.stringify(requestBody),
        signal,
      });
    } catch (err: unknown) {
      if (signal?.aborted) {
        return;
      }
      const netError =
        err instanceof Error
          ? err
          : new Error("Network interruption or connection refused");
      onError?.(netError);
      throw netError;
    }

    // Handle HTTP status errors
    if (!response.ok) {
      let errorMessage = `HTTP ${response.status}: ${response.statusText}`;
      try {
        const errorJson = await response.json();
        if (typeof errorJson?.detail === "string") {
          errorMessage = errorJson.detail;
        } else if (typeof errorJson?.error?.message === "string") {
          errorMessage = errorJson.error.message;
        }
      } catch {
        // Use default error message
      }

      if (response.status === 401) {
        tokenStore.clear();
        tokenStore.notifyUnauthorized();
        const err = new Error("Session expired or unauthorized. Please log in again.");
        onError?.(err);
        throw err;
      }

      if (response.status === 403) {
        const err = new Error("Forbidden: Access to this workspace or resource is denied.");
        onError?.(err);
        throw err;
      }

      if (response.status === 429) {
        const err = new Error(
          errorMessage.includes("quota")
            ? "Token budget quota exceeded. Please upgrade plan or try again later."
            : "Too many requests. Rate limit reached, please slow down."
        );
        onError?.(err);
        throw err;
      }

      if (response.status === 503) {
        const err = new Error("AI Service or upstream provider temporarily unavailable. Please retry.");
        onError?.(err);
        throw err;
      }

      const err = new Error(errorMessage);
      onError?.(err);
      throw err;
    }

    if (!response.body) {
      const err = new Error("Response body is empty or not readable as a stream");
      onError?.(err);
      throw err;
    }

    const reader = response.body.getReader();
    const decoder = new TextDecoder("utf-8");
    let buffer = "";

    const onAbort = () => {
      reader.cancel().catch(() => {});
    };
    if (signal) {
      if (signal.aborted) {
        await reader.cancel().catch(() => {});
        return;
      }
      signal.addEventListener("abort", onAbort);
    }

    try {
      while (true) {
        if (signal?.aborted) {
          await reader.cancel().catch(() => {});
          return;
        }

        const { done, value } = await reader.read();
        if (done) {
          break;
        }

        buffer += decoder.decode(value, { stream: true });
        const lines = buffer.split("\n");
        // Leave uncompleted trailing line in buffer
        buffer = lines.pop() || "";

        let currentEvent = "";
        for (const line of lines) {
          const trimmedLine = line.trim();
          if (!trimmedLine) {
            continue;
          }

          if (trimmedLine.startsWith("event:")) {
            currentEvent = trimmedLine.replace(/^event:\s*/, "").trim();
          } else if (trimmedLine.startsWith("data:")) {
            const dataContent = trimmedLine.replace(/^data:\s*/, "").trim();
            this.dispatchSSEEvent(
              currentEvent,
              dataContent,
              onStatus,
              onToken,
              onToolCall,
              onTelemetry,
              onDone,
              onError
            );
          }
        }
      }

      // Process any remainder in buffer
      if (buffer.trim().startsWith("data:")) {
        const dataContent = buffer.trim().replace(/^data:\s*/, "").trim();
        this.dispatchSSEEvent(
          "",
          dataContent,
          onStatus,
          onToken,
          onToolCall,
          onTelemetry,
          onDone,
          onError
        );
      }
    } catch (readErr: unknown) {
      if (signal?.aborted) {
        return;
      }
      const streamErr =
        readErr instanceof Error
          ? readErr
          : new Error("Stream connection interrupted");
      onError?.(streamErr);
      throw streamErr;
    } finally {
      if (signal) {
        signal.removeEventListener("abort", onAbort);
      }
      try {
        reader.releaseLock();
      } catch {
        // Already released
      }
    }
  }

  private dispatchSSEEvent(
    event: string,
    dataStr: string,
    onStatus?: (status: SSEStatusPayload) => void,
    onToken?: (tokenDelta: string) => void,
    onToolCall?: (toolPayload: SSEToolCallPayload) => void,
    onTelemetry?: (telemetry: SSETelemetryPayload) => void,
    onDone?: (done: SSEDonePayload) => void,
    onError?: (error: Error) => void
  ): void {
    if (event === "token") {
      try {
        const parsed = JSON.parse(dataStr) as SSETokenPayload;
        const delta = parsed.delta ?? parsed.token ?? parsed.content ?? dataStr;
        onToken?.(delta);
      } catch {
        onToken?.(dataStr);
      }
      return;
    }

    if (event === "status") {
      try {
        const parsed = JSON.parse(dataStr) as SSEStatusPayload;
        onStatus?.(parsed);
      } catch {
        onStatus?.({ message: dataStr });
      }
      return;
    }

    if (event === "tool_call") {
      try {
        const parsed = JSON.parse(dataStr) as SSEToolCallPayload;
        onToolCall?.(parsed);
      } catch {
        onToolCall?.({ name: dataStr });
      }
      return;
    }

    if (event === "telemetry") {
      try {
        const parsed = JSON.parse(dataStr) as SSETelemetryPayload;
        onTelemetry?.(parsed);
      } catch {
        // Silently skip malformed telemetry
      }
      return;
    }

    if (event === "done") {
      try {
        const parsed = JSON.parse(dataStr) as SSEDonePayload;
        onDone?.(parsed);
      } catch {
        onDone?.({
          conversation_id: "",
          tenant_id: "",
          elapsed_ms: 0,
        });
      }
      return;
    }

    if (event === "error") {
      try {
        const parsed = JSON.parse(dataStr) as SSEErrorPayload;
        const err = new Error(parsed.detail || parsed.error || "Streaming error occurred");
        onError?.(err);
      } catch {
        onError?.(new Error(dataStr || "Streaming error occurred"));
      }
      return;
    }

    // Default fallback: if no event specified but data resembles token or json
    try {
      const parsed = JSON.parse(dataStr);
      if (parsed.delta || parsed.token || parsed.content) {
        onToken?.(parsed.delta || parsed.token || parsed.content);
      }
    } catch {
      onToken?.(dataStr);
    }
  }
}

export const chatStreamService = new ChatStreamService();
