/**
 * Safe Enterprise Numeric & Secret Formatting Utilities
 *
 * Implements defensive parsing, zero NaN leakage, and safe secret masking.
 * Never calculates authoritative billing values — presentation-only formatting.
 */

/**
 * Formats a monetary value safely as USD currency.
 * Handles null, undefined, NaN, and negative values gracefully.
 *
 * @example
 * formatCurrency(142.85) // "$142.85"
 * formatCurrency(0.00345, 4) // "$0.0035"
 * formatCurrency(null) // "$0.00"
 */
export function formatCurrency(
  val?: number | null,
  decimals: number = 2
): string {
  if (val === null || val === undefined || isNaN(Number(val))) {
    return "$0.00";
  }

  const num = Number(val);
  const isNegative = num < 0;
  const absNum = Math.abs(num);

  const formatted = new Intl.NumberFormat("en-US", {
    style: "currency",
    currency: "USD",
    minimumFractionDigits: decimals,
    maximumFractionDigits: decimals,
  }).format(absNum);

  return isNegative ? `-${formatted}` : formatted;
}

/**
 * Formats a raw token count into human-readable compact or grouped notation.
 *
 * @example
 * formatTokens(14200000) // "14.20M"
 * formatTokens(450000) // "450.00K"
 * formatTokens(1250) // "1,250"
 * formatTokens(0) // "0"
 */
export function formatTokens(val?: number | null): string {
  if (val === null || val === undefined || isNaN(Number(val))) {
    return "0";
  }

  const num = Math.round(Number(val));
  const absNum = Math.abs(num);

  if (absNum >= 1_000_000_000) {
    return `${(num / 1_000_000_000).toFixed(2)}B`;
  }
  if (absNum >= 1_000_000) {
    return `${(num / 1_000_000).toFixed(2)}M`;
  }
  if (absNum >= 1_000) {
    return `${(num / 1_000).toFixed(2)}K`;
  }

  return num.toLocaleString("en-US");
}

/**
 * Formats a ratio or percentage safely.
 *
 * @param val Number representing percentage (e.g. 28.4 or 0.284)
 * @param isRatio If true, val is multiplied by 100 first (e.g. 0.284 -> 28.4%)
 * @param decimals Number of decimal digits (default: 1)
 */
export function formatPercentage(
  val?: number | null,
  isRatio: boolean = false,
  decimals: number = 1
): string {
  if (val === null || val === undefined || isNaN(Number(val))) {
    return "0.0%";
  }

  const raw = Number(val);
  const pct = isRatio ? raw * 100 : raw;
  return `${pct.toFixed(decimals)}%`;
}

/**
 * Formats standard numeric counts with comma grouping.
 */
export function formatNumber(val?: number | null): string {
  if (val === null || val === undefined || isNaN(Number(val))) {
    return "0";
  }
  return Number(val).toLocaleString("en-US");
}

/**
 * Masks sensitive secrets, API keys, and credentials defensively.
 * Never leaks the full credential string in DOM or logs.
 *
 * @example
 * maskSecret("sk-proj-1234567890abcdef") // "sk-proj-...cdef"
 * maskSecret("secret_value", 3) // "sec...lue"
 * maskSecret(null) // "••••••••••••"
 */
export function maskSecret(
  secret?: string | null,
  visibleChars: number = 4
): string {
  if (!secret || typeof secret !== "string") {
    return "••••••••••••";
  }

  const trimmed = secret.trim();
  if (trimmed.length <= visibleChars * 2) {
    return "••••••••••••";
  }

  // Preserve standard prefix if present (e.g. "sk-proj-", "sk-", "ghp_")
  const prefixMatch = trimmed.match(/^([a-zA-Z0-9_-]+[-_])/);
  const prefix = prefixMatch ? prefixMatch[1] : trimmed.slice(0, visibleChars);
  const suffix = trimmed.slice(-visibleChars);

  return `${prefix}...${suffix}`;
}
