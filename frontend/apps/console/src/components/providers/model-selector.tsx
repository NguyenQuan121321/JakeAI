import * as React from "react";
import { useQuery } from "@tanstack/react-query";
import { Cpu, Layers, AlertTriangle } from "lucide-react";
import { gatewayService } from "@/api/services/gateway.service";
import { queryKeys } from "@/api/hooks/query-keys";
import { CACHE_POLICIES } from "@/api/query-client";
import {
  SUPPORTED_PROVIDERS,
  PROVIDER_DISPLAY_NAMES,
} from "@/api/services/providers.service";
import type { ModelItem } from "@/api/types/domain";
import { cn } from "@/lib/utils";

export interface ModelSelectorProps {
  selectedProvider?: string;
  selectedModel?: string;
  onSelect: (provider: string, model: string) => void;
  disabled?: boolean;
  className?: string;
  idPrefix?: string;
}

export function ModelSelector({
  selectedProvider,
  selectedModel,
  onSelect,
  disabled = false,
  className,
  idPrefix = "model-selector",
}: ModelSelectorProps) {
  const { data: modelData, isLoading } = useQuery({
    queryKey: queryKeys.gateway.models(),
    queryFn: () => gatewayService.listModels(),
    staleTime: CACHE_POLICIES.configuration.staleTime,
    gcTime: CACHE_POLICIES.configuration.gcTime,
  });

  const availableModels: ModelItem[] = React.useMemo(() => {
    return modelData?.data || [];
  }, [modelData]);

  // Group models by provider
  const modelsByProvider = React.useMemo(() => {
    const map = new Map<string, ModelItem[]>();
    for (const p of SUPPORTED_PROVIDERS) {
      map.set(p, []);
    }
    for (const m of availableModels) {
      const p = (m.owned_by || "openai").toLowerCase();
      if (!map.has(p)) {
        map.set(p, []);
      }
      map.get(p)!.push(m);
    }
    return map;
  }, [availableModels]);

  // Auto-select first available provider if not set
  const activeProvider = React.useMemo(() => {
    if (selectedProvider && modelsByProvider.has(selectedProvider)) {
      return selectedProvider;
    }
    // Find first provider that has exposed models
    for (const p of SUPPORTED_PROVIDERS) {
      const list = modelsByProvider.get(p) || [];
      if (list.length > 0) return p;
    }
    return SUPPORTED_PROVIDERS[0];
  }, [selectedProvider, modelsByProvider]);

  const providerModels = React.useMemo(() => {
    return modelsByProvider.get(activeProvider) || [];
  }, [modelsByProvider, activeProvider]);

  const handleProviderChange = (e: React.ChangeEvent<HTMLSelectElement>) => {
    const newProv = e.target.value;
    const modelsForProv = modelsByProvider.get(newProv) || [];
    const firstModel = modelsForProv[0]?.id || "";
    onSelect(newProv, firstModel);
  };

  const handleModelChange = (e: React.ChangeEvent<HTMLSelectElement>) => {
    const newModel = e.target.value;
    onSelect(activeProvider, newModel);
  };

  return (
    <div className={cn("grid grid-cols-1 sm:grid-cols-2 gap-3", className)}>
      {/* Provider Selector */}
      <div className="space-y-1.5">
        <label
          htmlFor={`${idPrefix}-provider`}
          className="text-xs font-semibold text-foreground flex items-center gap-1.5"
        >
          <Layers className="h-3.5 w-3.5 text-muted-foreground" />
          Provider
        </label>
        <select
          id={`${idPrefix}-provider`}
          aria-label="Select AI Provider"
          value={activeProvider}
          onChange={handleProviderChange}
          disabled={disabled || isLoading}
          className="w-full h-9 rounded-md border border-input bg-background px-3 py-1 text-sm shadow-sm focus:outline-none focus:ring-2 focus:ring-ring disabled:cursor-not-allowed disabled:opacity-50"
        >
          {SUPPORTED_PROVIDERS.map((prov) => {
            const count = (modelsByProvider.get(prov) || []).length;
            const isExposed = count > 0;
            return (
              <option
                key={prov}
                value={prov}
                disabled={!isExposed}
                className={!isExposed ? "text-muted-foreground" : ""}
              >
                {PROVIDER_DISPLAY_NAMES[prov] || prov}
                {!isExposed ? " (No models available)" : ` (${count} model${count > 1 ? "s" : ""})`}
              </option>
            );
          })}
        </select>
      </div>

      {/* Model Selector */}
      <div className="space-y-1.5">
        <label
          htmlFor={`${idPrefix}-model`}
          className="text-xs font-semibold text-foreground flex items-center gap-1.5"
        >
          <Cpu className="h-3.5 w-3.5 text-muted-foreground" />
          Model
        </label>
        <select
          id={`${idPrefix}-model`}
          aria-label="Select Model"
          value={selectedModel || (providerModels[0]?.id ?? "")}
          onChange={handleModelChange}
          disabled={disabled || isLoading || providerModels.length === 0}
          className="w-full h-9 rounded-md border border-input bg-background px-3 py-1 text-sm shadow-sm focus:outline-none focus:ring-2 focus:ring-ring disabled:cursor-not-allowed disabled:opacity-50 font-mono"
        >
          {providerModels.length === 0 ? (
            <option value="" disabled>
              Backend reports no available models
            </option>
          ) : (
            providerModels.map((m) => (
              <option key={m.id} value={m.id}>
                {m.id}
              </option>
            ))
          )}
        </select>
      </div>

      {/* Notice if provider has no exposed models */}
      {providerModels.length === 0 && !isLoading && (
        <div className="sm:col-span-2 flex items-center gap-1.5 text-xs text-amber-600 dark:text-amber-400 mt-1">
          <AlertTriangle className="h-3.5 w-3.5 shrink-0" />
          <span>This provider currently has no available models exposed by the AI Gateway.</span>
        </div>
      )}
    </div>
  );
}
