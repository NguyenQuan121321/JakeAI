/**
 * Providers Service
 *
 * Provides composite view of available AI providers, supported models, and BYOK key status.
 */

import { gatewayService } from "./gateway.service";
import { byokService } from "./byok.service";
import type { ModelItem, BYOKProviderItem } from "../types/domain";

export interface ProviderStatus {
  provider: string;
  name: string;
  models: ModelItem[];
  hasByokKey: boolean;
  isHealthy: boolean;
}

export class ProvidersService {
  public async getProvidersWithStatus(): Promise<ProviderStatus[]> {
    const [modelData, byokData] = await Promise.all([
      gatewayService.listModels().catch(() => ({ data: [] })),
      byokService.listKeys().catch(() => ({ keys: [] })),
    ]);

    const byokKeySet = new Set((byokData.keys || []).map((k: BYOKProviderItem) => k.provider.toLowerCase()));

    // Group models by provider
    const providerMap = new Map<string, ModelItem[]>();
    for (const m of modelData.data || []) {
      const p = (m.owned_by || "openai").toLowerCase();
      if (!providerMap.has(p)) {
        providerMap.set(p, []);
      }
      providerMap.get(p)!.push(m);
    }

    // Default provider catalog
    const standardProviders = ["openai", "anthropic", "google", "deepseek", "cohere"];
    const results: ProviderStatus[] = [];

    for (const p of standardProviders) {
      const models = providerMap.get(p) || [];
      results.push({
        provider: p,
        name: p.charAt(0).toUpperCase() + p.slice(1),
        models,
        hasByokKey: byokKeySet.has(p),
        isHealthy: true,
      });
    }

    return results;
  }
}

export const providersService = new ProvidersService();
