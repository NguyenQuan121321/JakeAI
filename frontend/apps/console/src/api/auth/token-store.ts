/**
 * Secure Token Storage Layer
 *
 * Stores JWT access & refresh credentials strictly in memory by default,
 * with safe session isolation.
 *
 * Invariants:
 * - Never log tokens or secrets to console, telemetry, or storage events.
 * - Centralized observer mechanism for 401 expiration and token changes.
 */

export interface AuthTokens {
  accessToken: string;
  refreshToken?: string;
  expiresAt?: string;
}

export type AuthChangeListener = (tokens: AuthTokens | null) => void;
export type UnauthorizedListener = () => void;

class TokenStore {
  private tokens: AuthTokens | null = null;
  private activeTenantId: string | null = null;
  private changeListeners: Set<AuthChangeListener> = new Set();
  private unauthorizedListeners: Set<UnauthorizedListener> = new Set();

  constructor() {
    // Attempt non-sensitive active tenant restoration
    try {
      if (typeof window !== "undefined" && window.localStorage) {
        this.activeTenantId = localStorage.getItem("jakeai-active-workspace");
      }
    } catch {
      // Storage access blocked or unavailable
    }
  }

  public getAccessToken(): string | null {
    return this.tokens?.accessToken || null;
  }

  public getRefreshToken(): string | null {
    return this.tokens?.refreshToken || null;
  }

  public getTokens(): AuthTokens | null {
    return this.tokens ? { ...this.tokens } : null;
  }

  public setTokens(tokens: AuthTokens | null): void {
    this.tokens = tokens ? { ...tokens } : null;
    this.notifyChange();
  }

  public getActiveTenantId(): string | null {
    return this.activeTenantId;
  }

  public setActiveTenantId(tenantId: string | null): void {
    this.activeTenantId = tenantId;
    try {
      if (typeof window !== "undefined" && window.localStorage) {
        if (tenantId) {
          localStorage.setItem("jakeai-active-workspace", tenantId);
        } else {
          localStorage.removeItem("jakeai-active-workspace");
        }
      }
    } catch {
      // Storage access blocked or unavailable
    }
  }

  public clear(): void {
    this.tokens = null;
    this.notifyChange();
  }

  public notifyUnauthorized(): void {
    this.unauthorizedListeners.forEach((listener) => {
      try {
        listener();
      } catch {
        // Suppress listener error
      }
    });
  }

  public subscribeChange(listener: AuthChangeListener): () => void {
    this.changeListeners.add(listener);
    return () => this.changeListeners.delete(listener);
  }

  public subscribeUnauthorized(listener: UnauthorizedListener): () => void {
    this.unauthorizedListeners.add(listener);
    return () => this.unauthorizedListeners.delete(listener);
  }

  private notifyChange(): void {
    const current = this.getTokens();
    this.changeListeners.forEach((listener) => {
      try {
        listener(current);
      } catch {
        // Suppress listener error
      }
    });
  }
}

export const tokenStore = new TokenStore();
