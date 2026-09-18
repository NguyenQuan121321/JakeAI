import * as React from "react";
import {
  KeyRound,
  ShieldCheck,
  Server,
  Cpu,
  RefreshCw,
} from "lucide-react";
import { Button } from "@/components/ui/button";
import { MetricCard } from "@/components/ui/metric-card";
import { StatusIndicator } from "@/components/ui/status-indicator";
import { Card, CardHeader, CardTitle, CardDescription, CardContent } from "@/components/ui/card";
import { Badge } from "@/components/ui/badge";
import { Alert, AlertTitle, AlertDescription } from "@/components/ui/alert";
import { useProvidersQuery } from "@/api/hooks/use-providers-query";
import { useByokKeysQuery } from "@/api/hooks/use-byok-query";
import { ByokVaultTable } from "@/components/providers/byok-vault-table";
import { ModelSelector } from "@/components/providers/model-selector";
import { useAuth } from "@/context/auth-context";

export default function ProvidersPage() {
  const { user } = useAuth();
  const { data: providers, isLoading: providersLoading, refetch: refetchProviders } = useProvidersQuery();
  const { data: byokData, isLoading: byokLoading } = useByokKeysQuery();

  const [testSelectedProvider, setTestSelectedProvider] = React.useState<string>("openai");
  const [testSelectedModel, setTestSelectedModel] = React.useState<string>("");

  const totalProviders = providers?.length || 0;
  const totalModels = React.useMemo(() => {
    if (!providers) return 0;
    return providers.reduce((acc, p) => acc + p.models.length, 0);
  }, [providers]);

  const configuredKeysCount = React.useMemo(() => {
    return (byokData?.keys || []).filter((k) => (k.configured || k.masked_key) && k.status !== "revoked").length;
  }, [byokData]);

  return (
    <div className="space-y-8 pb-12">
      {/* Header */}
      <div className="flex flex-col sm:flex-row sm:items-center sm:justify-between gap-4">
        <div>
          <div className="flex items-center gap-2.5">
            <h1 className="text-2xl font-bold tracking-tight">Providers, Models & BYOK Console</h1>
            <span className="text-xs font-mono bg-muted text-muted-foreground px-2 py-0.5 rounded border">
              Tenant: {user?.tenantId || "tenant_jakeai_core"}
            </span>
          </div>
          <p className="text-sm text-muted-foreground mt-1">
            Manage enterprise AI provider integrations, gateway model catalog, and zero-retention cryptographic credential vaults.
          </p>
        </div>
        <div className="flex items-center gap-2">
          <Button
            variant="outline"
            size="sm"
            onClick={() => refetchProviders()}
            leftIcon={<RefreshCw className="h-4 w-4" />}
          >
            Refresh Catalog
          </Button>
        </div>
      </div>

      {/* Security Banner */}
      <Alert variant="info">
        <AlertTitle className="flex items-center gap-2">
          <ShieldCheck className="h-4 w-4 text-sky-500" />
          Stateless Zero-Retention Cryptographic Keystore Active
        </AlertTitle>
        <AlertDescription>
          In accordance with ADR-0003, provider API keys are encrypted at rest with tenant-isolated AES-256-GCM keys.
          Raw keys are never logged, never persisted in client storage (localStorage/sessionStorage), and masked immediately after registration.
        </AlertDescription>
      </Alert>

      {/* Metrics Row */}
      <div className="grid grid-cols-1 sm:grid-cols-4 gap-4">
        <MetricCard
          title="Active AI Providers"
          value={providersLoading ? "..." : totalProviders.toString()}
          icon={Server}
        />
        <MetricCard
          title="Gateway Models Exposed"
          value={providersLoading ? "..." : totalModels.toString()}
          icon={Cpu}
        />
        <MetricCard
          title="Configured BYOK Keys"
          value={byokLoading ? "..." : `${configuredKeysCount} / ${totalProviders}`}
          icon={KeyRound}
        />
        <MetricCard
          title="Isolation Boundary"
          value="Enforced"
          change={{ value: "HSM Scoped", trend: "up", label: "AES-256-GCM" }}
          icon={ShieldCheck}
        />
      </div>

      {/* Providers Grid */}
      <div className="space-y-4">
        <div>
          <h2 className="text-base font-semibold tracking-tight">Connected Providers & Health</h2>
          <p className="text-xs text-muted-foreground mt-0.5">
            Real-time operational status, latency probes, and models exposed by each upstream provider.
          </p>
        </div>

        <div className="grid grid-cols-1 md:grid-cols-2 lg:grid-cols-3 gap-4">
          {providers?.map((p) => {
            const hasModels = p.models.length > 0;
            return (
              <Card key={p.provider} className="flex flex-col justify-between">
                <CardHeader className="pb-3">
                  <div className="flex items-start justify-between">
                    <div>
                      <CardTitle className="text-base">{p.name}</CardTitle>
                      <CardDescription className="text-xs font-mono text-muted-foreground mt-0.5">
                        {p.provider}
                      </CardDescription>
                    </div>
                    <StatusIndicator
                      status={!p.isHealthy ? "critical" : hasModels ? "healthy" : "idle"}
                      customLabel={!p.isHealthy ? "Unavailable" : hasModels ? "Operational" : "No Models"}
                      variant="badge"
                    />
                  </div>
                </CardHeader>

                <CardContent className="space-y-3 pt-0">
                  <div className="space-y-1.5">
                    <div className="text-xs font-medium text-muted-foreground flex items-center justify-between">
                      <span>Available Models:</span>
                      <span className="font-mono text-[11px]">{p.models.length} model{p.models.length !== 1 ? "s" : ""}</span>
                    </div>
                    {hasModels ? (
                      <div className="flex flex-wrap gap-1 max-h-24 overflow-y-auto">
                        {p.models.map((m) => (
                          <Badge key={m.id} variant="secondary" className="font-mono text-[10px]">
                            {m.id}
                          </Badge>
                        ))}
                      </div>
                    ) : (
                      <p className="text-xs text-muted-foreground italic">
                        Backend does not expose models for this provider
                      </p>
                    )}
                  </div>

                  <div className="flex items-center justify-between text-xs text-muted-foreground border-t pt-2.5 mt-2">
                    <span>
                      BYOK: {p.hasByokKey ? (
                        <span className="text-emerald-600 font-medium">Configured</span>
                      ) : (
                        <span className="text-muted-foreground">Default Platform</span>
                      )}
                    </span>
                    <span className="font-mono text-[11px]">
                      {p.byokItem?.masked_key || "platform-pool"}
                    </span>
                  </div>
                </CardContent>
              </Card>
            );
          })}
        </div>
      </div>

      {/* Model Selector Interactive Tester */}
      <Card>
        <CardHeader className="pb-3">
          <CardTitle className="text-base flex items-center gap-2">
            <Cpu className="h-4 w-4 text-primary" />
            Model Selector Workspace
          </CardTitle>
          <CardDescription className="text-xs">
            Test hierarchical Provider → Model resolution. Unavailable models are disabled dynamically.
          </CardDescription>
        </CardHeader>
        <CardContent className="space-y-4">
          <ModelSelector
            selectedProvider={testSelectedProvider}
            selectedModel={testSelectedModel}
            onSelect={(prov, model) => {
              setTestSelectedProvider(prov);
              setTestSelectedModel(model);
            }}
          />

          {testSelectedModel && (
            <div className="rounded-md bg-muted/40 border p-3 flex flex-col sm:flex-row sm:items-center justify-between gap-2 text-xs">
              <div>
                <span className="text-muted-foreground">Active Selection:</span>{" "}
                <span className="font-mono font-semibold text-foreground">{testSelectedModel}</span>
              </div>
              <div className="flex items-center gap-2">
                <Badge variant="outline" className="font-mono text-[10px]">
                  Provider: {testSelectedProvider}
                </Badge>
                <span className="text-emerald-600 font-medium flex items-center gap-1">
                  ✓ Verified in AI Gateway catalog
                </span>
              </div>
            </div>
          )}
        </CardContent>
      </Card>

      {/* BYOK Keystore Section */}
      <ByokVaultTable />
    </div>
  );
}
