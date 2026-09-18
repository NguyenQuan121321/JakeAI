/**
 * RAG Pipeline Service
 *
 * Covers vector query, grounded answer generation, and asynchronous document ingestion.
 */

import { apiClient } from "../client/http-client";
import type {
  RAGQueryRequest,
  RAGQueryResponse,
  RAGGenerateRequest,
  RAGGenerateResponse,
  DocumentIngestRequest,
  DocumentIngestResponse,
  IngestionTaskResponse,
  IngestionTaskState,
} from "../types/domain";

export class RAGService {
  public async query(request: RAGQueryRequest): Promise<RAGQueryResponse> {
    const res = await apiClient.post<RAGQueryResponse>("/api/v1/rag/query", request);
    return res.data;
  }

  public async generate(request: RAGGenerateRequest): Promise<RAGGenerateResponse> {
    const res = await apiClient.post<RAGGenerateResponse>("/api/v1/rag/generate", request);
    return res.data;
  }

  public async ingest(
    request: DocumentIngestRequest,
    asyncMode = false
  ): Promise<DocumentIngestResponse | IngestionTaskResponse> {
    const endpoint = asyncMode ? "/api/v1/rag/ingest?async_mode=true" : "/api/v1/rag/ingest";
    const res = await apiClient.post<DocumentIngestResponse | IngestionTaskResponse>(endpoint, request);
    return res.data;
  }

  public async getIngestionTask(taskId: string): Promise<IngestionTaskState> {
    const res = await apiClient.get<IngestionTaskState>(
      `/api/v1/rag/tasks/${encodeURIComponent(taskId)}`
    );
    return res.data;
  }
}

export const ragService = new RAGService();
