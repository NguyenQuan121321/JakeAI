/**
 * Workspace Top Navigation & Capability Header
 *
 * Exposes active workspace context, multi-agent status,
 * and controlled provider/model selection fetched from /api/v1/gateway/models.
 */

import { useEffect, useState } from "react";
import { Bot, Sparkles, Cpu } from "lucide-react";
import { useAuth } from "@/context/auth-context";
import { gatewayService } from "@/api/services/gateway.service";
import { Badge } from "@/components/ui/badge";
import { Select } from "@/components/ui/select";
import { StatusIndicator } from "@/components/ui/status-indicator";

interface WorkspaceHeaderProps {
  selectedModel: string;
  onModelChange: (model: string, provider?: string) => void;
  mascotState?: string;
  isStreaming?: boolean;
}

interface ModelOption {
  id: string;
  owned_by: string;
  label: string;
}

export function WorkspaceHeader({
  selectedModel,
  onModelChange,
  mascotState = "idle",
  isStreaming = false,
}: WorkspaceHeaderProps) {
  const { activeWorkspace } = useAuth();
  const [modelOptions, setModelOptions] = useState<ModelOption[]>([]);
  const [isLoadingModels, setIsLoadingModels] = useState<boolean>(true);

  useEffect(() => {
    let isMounted = true;
    async function loadModels() {
      try {
        setIsLoadingModels(true);
        const res = await gatewayService.listModels();
        if (isMounted && res?.data && res.data.length > 0) {
          const options: ModelOption[] = res.data.map((m) => ({
            id: m.id,
            owned_by: m.owned_by || "jakeai",
            label: `${m.id} (${m.owned_by || "default"})`,
          }));
          setModelOptions(options);

          // If current selectedModel is not in options, default to first
          if (!options.some((opt) => opt.id === selectedModel)) {
            onModelChange(options[0].id, options[0].owned_by);
          }
        }
      } catch {
        // Fallback to default catalog if backend call fails
        if (isMounted) {
          setModelOptions([
            { id: "gemini-1.5-flash", owned_by: "gemini", label: "gemini-1.5-flash (Google Gemini)" },
            { id: "gemini-1.5-pro", owned_by: "gemini", label: "gemini-1.5-pro (Google Gemini)" },
            { id: "gpt-4o", owned_by: "openai", label: "gpt-4o (OpenAI)" },
            { id: "gpt-4o-mini", owned_by: "openai", label: "gpt-4o-mini (OpenAI)" },
            { id: "claude-3-5-sonnet", owned_by: "anthropic", label: "claude-3-5-sonnet (Anthropic)" },
          ]);
        }
      } finally {
        if (isMounted) {
          setIsLoadingModels(false);
        }
      }
    }
    loadModels();
    return () => {
      isMounted = false;
    };
  }, []);

  const handleSelectModel = (val: string) => {
    const found = modelOptions.find((opt) => opt.id === val);
    onModelChange(val, found?.owned_by);
  };

  const getMascotBadge = () => {
    if (mascotState === "thinking" || isStreaming) {
      return (
        <Badge variant="outline" className="bg-primary/10 text-primary border-primary/20 space-x-1">
          <Sparkles className="h-3 w-3 animate-pulse" />
          <span>Orchestrating</span>
        </Badge>
      );
    }
    if (mascotState === "alert") {
      return (
        <Badge variant="outline" className="bg-destructive/10 text-destructive border-destructive/20 space-x-1">
          <span>Alert</span>
        </Badge>
      );
    }
    return (
      <Badge variant="outline" className="bg-muted text-muted-foreground space-x-1">
        <span>Ready</span>
      </Badge>
    );
  };

  return (
    <div className="flex flex-wrap items-center justify-between gap-4 border-b border-border bg-card/60 px-4 py-3 backdrop-blur-sm sm:px-6">
      {/* Left: Workspace & Orchestrator context */}
      <div className="flex items-center space-x-3">
        <div className="flex h-9 w-9 items-center justify-center rounded-lg bg-primary/10 text-primary">
          <Bot className="h-5 w-5" />
        </div>
        <div>
          <div className="flex items-center space-x-2">
            <h2 className="text-sm font-semibold tracking-tight text-foreground">
              JakeAI Orchestrator
            </h2>
            <StatusIndicator status="running" variant="dot" showLabel={false} />
            {getMascotBadge()}
          </div>
          <p className="text-xs text-muted-foreground">
            Tenant: <span className="font-medium text-foreground">{activeWorkspace?.name || "JakeAI Core"}</span>
            <span className="mx-1.5 opacity-40">•</span>
            <span className="capitalize">{activeWorkspace?.environment || "production"}</span>
          </p>
        </div>
      </div>

      {/* Right: Controlled Model Selector */}
      <div className="flex items-center space-x-3">
        <div className="flex items-center space-x-2">
          <Cpu className="h-4 w-4 text-muted-foreground" />
          <label htmlFor="model-select" className="text-xs font-medium text-muted-foreground hidden sm:inline">
            Model:
          </label>
        </div>
        <div className="w-56 sm:w-64">
          <Select
            ariaLabel="Select model"
            value={selectedModel}
            onChange={handleSelectModel}
            disabled={isLoadingModels || isStreaming}
            options={
              isLoadingModels
                ? [{ value: selectedModel, label: "Loading models..." }]
                : modelOptions.map((opt) => ({
                    value: opt.id,
                    label: opt.label,
                  }))
            }
          />
        </div>
      </div>
    </div>
  );
}
