/**
 * Chat & Stream Service
 *
 * Interacts with JakeAI LangGraph chat streaming and OpenAI-compatible Gateway.
 */

import { apiClient } from "../client/http-client";
import type {
  GatewayChatRequest,
  GatewayChatResponse,
} from "../types/domain";

export class ChatService {
  /**
   * Submit completion to OpenAI-compatible AI gateway
   */
  public async postGatewayChat(
    request: GatewayChatRequest
  ): Promise<GatewayChatResponse> {
    const res = await apiClient.post<GatewayChatResponse>(
      "/api/v1/gateway/chat/completions",
      request
    );
    return res.data;
  }

  /**
   * Root OpenAI-compatible alias /v1/chat/completions
   */
  public async postV1Chat(
    request: GatewayChatRequest
  ): Promise<GatewayChatResponse> {
    const res = await apiClient.post<GatewayChatResponse>(
      "/v1/chat/completions",
      request
    );
    return res.data;
  }
}

export const chatService = new ChatService();
export { chatStreamService, ChatStreamService } from "./chat-stream.service";
