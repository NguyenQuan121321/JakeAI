/**
 * Bring Your Own Key (BYOK) Vault Service
 *
 * Covers AES-256 encrypted provider keys, rotation, validation, and revocation.
 */

import { apiClient } from "../client/http-client";
import type {
  BYOKListResponse,
  BYOKKeyResponse,
  BYOKStoreRequest,
  BYOKValidateRequest,
  BYOKValidationResponse,
  BYOKRotateRequest,
} from "../types/domain";

export class BYOKService {
  public async listKeys(): Promise<BYOKListResponse> {
    const res = await apiClient.get<BYOKListResponse>("/api/v1/byok/keys");
    return res.data;
  }

  public async storeKey(request: BYOKStoreRequest): Promise<BYOKKeyResponse> {
    const res = await apiClient.post<BYOKKeyResponse>("/api/v1/byok/keys", request);
    return res.data;
  }

  public async validateCandidateKey(
    request: BYOKValidateRequest
  ): Promise<BYOKValidationResponse> {
    const res = await apiClient.post<BYOKValidationResponse>("/api/v1/byok/keys/validate", request);
    return res.data;
  }

  public async deleteKey(provider: string): Promise<Record<string, unknown>> {
    const res = await apiClient.delete<Record<string, unknown>>(
      `/api/v1/byok/keys/${encodeURIComponent(provider)}`
    );
    return res.data;
  }

  public async revokeKey(provider: string): Promise<BYOKKeyResponse> {
    const res = await apiClient.post<BYOKKeyResponse>(
      `/api/v1/byok/keys/${encodeURIComponent(provider)}/revoke`,
      {}
    );
    return res.data;
  }

  public async rotateKey(
    provider: string,
    request: BYOKRotateRequest
  ): Promise<BYOKKeyResponse> {
    const res = await apiClient.post<BYOKKeyResponse>(
      `/api/v1/byok/keys/${encodeURIComponent(provider)}/rotate`,
      request
    );
    return res.data;
  }

  public async validateExistingKey(
    provider: string
  ): Promise<BYOKValidationResponse> {
    const res = await apiClient.post<BYOKValidationResponse>(
      `/api/v1/byok/keys/${encodeURIComponent(provider)}/validate`,
      {}
    );
    return res.data;
  }
}

export const byokService = new BYOKService();
