/**
 * Providers Service
 *
 * Provides composite view of available AI providers, supported models, and BYOK key status.
 */

import { gatewayService } from "./gateway.service";
import { byokService } from "./byok.service";
import type { ModelItem, BYOKProviderItem } from "../types/domain";

export const SUPPORTED_PROVIDERS = [
  "openai",
  "gemini",
  "anthropic",
  "groq",
  "deepseek",
  "openrouter",
] as const;

export type SupportedProvider = (typeof SUPPORTED_PROVIDERS)[number];

export const PROVIDER_DISPLAY_NAMES: Record<string, string> = {
  openai: "OpenAI",
  gemini: "Google Gemini",
  anthropic: "Anthropic Claude",
  groq: "Groq LPU",
  deepseek: "DeepSeek",
  openrouter: "OpenRouter",
};

export interface ProviderStatus {
  provider: string;
  name: string;
  models: ModelItem[];
  hasByokKey: boolean;
  isHealthy: boolean;
  byokItem?: BYOKProviderItem;
  latencyMs?: number;
}

export class ProvidersService {
  public async getProvidersWithStatus(): Promise<ProviderStatus[]> {
    const [modelData, byokData] = await Promise.all([
      gatewayService.listModels().catch(() => ({ data: [] })),
      byokService.listKeys().catch(() => ({ keys: [] })),
    ]);

    const byokMap = new Map<string, BYOKProviderItem>();
    for (const k of byokData.keys || []) {
      byokMap.set(k.provider.toLowerCase(), k);
    }

    // Group models by provider
    const providerMap = new Map<string, ModelItem[]>();
    for (const m of modelData.data || []) {
      const p = (m.owned_by || "openai").toLowerCase();
      if (!providerMap.has(p)) {
        providerMap.set(p, []);
      }
      providerMap.get(p)!.push(m);
    }

    const results: ProviderStatus[] = [];

    for (const p of SUPPORTED_PROVIDERS) {
      const models = providerMap.get(p) || [];
      const byokItem = byokMap.get(p);
      const hasByokKey = Boolean(byokItem?.configured || byokItem?.masked_key);
      const isUnavailable =
        byokItem?.validation_status === "provider_unavailable" ||
        byokItem?.validation_status === "503";
      const isHealthy = !isUnavailable;

      results.push({
        provider: p,
        name: PROVIDER_DISPLAY_NAMES[p] || p.charAt(0).toUpperCase() + p.slice(1),
        models,
        hasByokKey,
        isHealthy,
        byokItem,
      });
    }

    return results;
  }

  public async validateProviderKey(
    provider: string
  ): Promise<{ isValid: boolean; error: string | null; latencyMs: number }> {
    const startTime = performance.now();
    try {
      const res = await byokService.validateExistingKey(provider);
      const latencyMs = Math.round(performance.now() - startTime);
      return {
        isValid: res.is_valid,
        error: res.error ?? null,
        latencyMs,
      };
    } catch (err: unknown) {
      const latencyMs = Math.round(performance.now() - startTime);
      const message = err instanceof Error ? err.message : "Validation failed";
      return {
        isValid: false,
        error: message,
        latencyMs,
      };
    }
  }
}

export const providersService = new ProvidersService();

