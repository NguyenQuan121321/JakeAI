/**
 * JWT Token Utilities & Claims Parser
 *
 * Implements FinnApiGo compact and expanded dual-schema claim resolution:
 * - subject: sub | uid
 * - tenant: tenant_id | tid
 * - roles: roles | role
 * - permissions: permissions | perms
 * - scopes: scopes
 * - correlation: cid
 */

export interface DecodedJwtClaims {
  sub: string;
  tenant_id: string;
  org_id?: string;
  roles: string[];
  permissions: string[];
  scopes: string[];
  cid?: string;
  exp?: number;
  iat?: number;
  email?: string;
  name?: string;
  raw: Record<string, unknown>;
}

export function decodeJwt(token: string): DecodedJwtClaims | null {
  try {
    const parts = token.split(".");
    if (parts.length !== 3) {
      return null;
    }

    // Base64URL decode the payload (second segment)
    const base64Url = parts[1];
    const base64 = base64Url.replace(/-/g, "+").replace(/_/g, "/");
    const jsonPayload = decodeURIComponent(
      atob(base64)
        .split("")
        .map((c) => "%" + ("00" + c.charCodeAt(0).toString(16)).slice(-2))
        .join("")
    );

    const payload = JSON.parse(jsonPayload) as Record<string, unknown>;

    const sub = String(payload.sub || payload.uid || "");
    const tenant_id = String(payload.tenant_id || payload.tid || "default");
    const org_id = payload.org_id ? String(payload.org_id) : undefined;

    const rawRoles = payload.roles || payload.role || [];
    const roles = Array.isArray(rawRoles) ? rawRoles.map(String) : [String(rawRoles)];

    const rawPerms = payload.permissions || payload.perms || [];
    const permissions = Array.isArray(rawPerms) ? rawPerms.map(String) : [String(rawPerms)];

    let scopes: string[] = [];
    if (Array.isArray(payload.scopes)) {
      scopes = payload.scopes.map(String);
    } else if (typeof payload.scopes === "string") {
      scopes = payload.scopes.split(" ");
    }

    const cid = payload.cid ? String(payload.cid) : undefined;
    const exp = typeof payload.exp === "number" ? payload.exp : undefined;
    const iat = typeof payload.iat === "number" ? payload.iat : undefined;
    const email = typeof payload.email === "string" ? payload.email : undefined;
    const name = typeof payload.name === "string" ? payload.name : undefined;

    return {
      sub,
      tenant_id,
      org_id,
      roles,
      permissions,
      scopes,
      cid,
      exp,
      iat,
      email,
      name,
      raw: payload,
    };
  } catch {
    return null;
  }
}

/**
 * Check if token has expired or is within buffer seconds of expiring
 */
export function isTokenExpired(token: string, bufferSeconds = 30): boolean {
  const claims = decodeJwt(token);
  if (!claims || !claims.exp) {
    return false;
  }
  const nowInSeconds = Math.floor(Date.now() / 1000);
  return claims.exp <= nowInSeconds + bufferSeconds;
}
