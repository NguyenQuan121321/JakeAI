/**
 * Authentication Service
 *
 * Implements FinnApiGo identity contracts:
 * - POST /api/v1/auth/login
 * - POST /api/v1/auth/refresh-token
 * - POST /api/v1/auth/logout
 * - GET  /api/v1/auth/me
 */

import { apiClient } from "../client/http-client";
import { tokenStore } from "../auth/token-store";
import type { FinnApiResponse } from "../types/api";

export interface LoginRequest {
  email: string;
  password?: string;
}

export interface AuthProfile {
  id: number | string;
  username?: string;
  email: string;
  fullName?: string;
  role?: string;
  isActive?: boolean;
  isEmailVerified?: boolean;
}

export interface LoginResponseData {
  accessToken: string;
  refreshToken?: string;
  expiresAt?: string;
  profile?: AuthProfile;
  mfaRequired?: boolean;
  mfaToken?: string;
}

export interface RefreshTokenResponseData {
  accessToken: string;
  refreshToken?: string;
  expiresAt?: string;
}

export class AuthService {
  /**
   * Authenticate user against FinnApiGo
   */
  public async login(credentials: LoginRequest): Promise<LoginResponseData> {
    const res = await apiClient.post<FinnApiResponse<LoginResponseData>>(
      "/api/v1/auth/login",
      credentials,
      { skipAuth: true }
    );

    const payload = res.data.data;
    if (payload?.accessToken) {
      tokenStore.setTokens({
        accessToken: payload.accessToken,
        refreshToken: payload.refreshToken,
        expiresAt: payload.expiresAt,
      });
    }

    return payload;
  }

  /**
   * Refresh expired JWT access token using single-use refresh token
   */
  public async refreshToken(): Promise<string | null> {
    const refreshToken = tokenStore.getRefreshToken();
    if (!refreshToken) {
      return null;
    }

    try {
      const res = await apiClient.post<FinnApiResponse<RefreshTokenResponseData>>(
        "/api/v1/auth/refresh-token",
        { refreshToken },
        { skipAuth: true }
      );

      const payload = res.data.data;
      if (payload?.accessToken) {
        tokenStore.setTokens({
          accessToken: payload.accessToken,
          refreshToken: payload.refreshToken || refreshToken,
          expiresAt: payload.expiresAt,
        });
        return payload.accessToken;
      }
      return null;
    } catch {
      tokenStore.clear();
      return null;
    }
  }

  /**
   * Fetch sanitized authenticated user profile
   */
  public async getMe(): Promise<AuthProfile> {
    const res = await apiClient.get<FinnApiResponse<AuthProfile>>("/api/v1/auth/me");
    return res.data.data;
  }

  /**
   * Revoke current session and clear tokens
   */
  public async logout(): Promise<void> {
    try {
      await apiClient.post<FinnApiResponse<null>>("/api/v1/auth/logout", {});
    } catch {
      // Best-effort logout: even if server fails, clear client tokens
    } finally {
      tokenStore.clear();
    }
  }
}

export const authService = new AuthService();

// Wire up the single-flight refresh token handler on apiClient
apiClient.setRefreshTokenHandler(() => authService.refreshToken());
