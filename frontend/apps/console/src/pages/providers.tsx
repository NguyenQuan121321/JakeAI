import { KeyRound, Plus, ShieldCheck, Zap } from "lucide-react";
import { Button } from "@/components/ui/button";
import { MetricCard } from "@/components/ui/metric-card";
import { StatusIndicator } from "@/components/ui/status-indicator";
import { Card, CardHeader, CardTitle, CardDescription, CardContent } from "@/components/ui/card";
import { Badge } from "@/components/ui/badge";
import { Alert, AlertTitle, AlertDescription } from "@/components/ui/alert";

interface ProviderConfig {
  id: string;
  name: string;
  models: string[];
  status: "healthy" | "degraded" | "blocked";
  latency: number;
  byokConfigured: boolean;
  maskKey: string;
}

const PROVIDERS: ProviderConfig[] = [
  {
    id: "anthropic",
    name: "Anthropic Claude Gateway",
    models: ["claude-3-5-sonnet-20241022", "claude-3-haiku-20240307"],
    status: "healthy",
    latency: 185,
    byokConfigured: true,
    maskKey: "sk-ant-api03-••••••••••••-AA",
  },
  {
    id: "openai",
    name: "OpenAI Direct Bridge",
    models: ["gpt-4o", "gpt-4o-mini", "text-embedding-3-small"],
    status: "healthy",
    latency: 210,
    byokConfigured: true,
    maskKey: "sk-proj-••••••••••••-Z1",
  },
  {
    id: "google",
    name: "Google Gemini Vertex Bridge",
    models: ["gemini-1.5-pro", "gemini-1.5-flash"],
    status: "degraded",
    latency: 480,
    byokConfigured: true,
    maskKey: "AIzaSy••••••••••••-9K",
  },
];

export default function ProvidersPage() {
  return (
    <div className="space-y-8">
      {/* Header */}
      <div className="flex flex-col sm:flex-row sm:items-center sm:justify-between gap-4">
        <div>
          <h1 className="text-2xl font-bold tracking-tight">Providers & BYOK Keystore</h1>
          <p className="text-sm text-muted-foreground mt-1">
            Enterprise Bring-Your-Own-Key provider connections with zero server retention.
          </p>
        </div>
        <Button size="sm" leftIcon={<Plus className="h-4 w-4" />}>
          Add Provider
        </Button>
      </div>

      <Alert variant="info">
        <AlertTitle>Stateless Zero-Retention Keystore Active</AlertTitle>
        <AlertDescription>
          In accordance with ADR-0003, provider API keys are encrypted at rest with tenant-scoped HSM keys and never written to logs or telemetry streams.
        </AlertDescription>
      </Alert>

      {/* Metrics */}
      <div className="grid grid-cols-1 sm:grid-cols-3 gap-4">
        <MetricCard title="Connected Providers" value="3" icon={KeyRound} />
        <MetricCard title="Available Base Models" value="7" icon={Zap} />
        <MetricCard
          title="Keystore Security Audit"
          value="Passed"
          change={{ value: "100%", trend: "up", label: "isolated" }}
          icon={ShieldCheck}
        />
      </div>

      {/* Providers Grid */}
      <div className="grid grid-cols-1 md:grid-cols-3 gap-4">
        {PROVIDERS.map((p) => (
          <Card key={p.id}>
            <CardHeader className="pb-3">
              <div className="flex items-start justify-between">
                <CardTitle className="text-base">{p.name}</CardTitle>
                <StatusIndicator status={p.status} variant="badge" />
              </div>
              <CardDescription className="text-xs font-mono">{p.maskKey}</CardDescription>
            </CardHeader>
            <CardContent>
              <div className="space-y-2 text-xs">
                <div className="flex flex-wrap gap-1">
                  {p.models.map((m) => (
                    <Badge key={m} variant="secondary" className="font-mono text-[9px]">
                      {m}
                    </Badge>
                  ))}
                </div>
                <div className="flex items-center justify-between text-muted-foreground border-t pt-3 mt-3">
                  <span>Latency: {p.latency}ms</span>
                  <span>BYOK Verified</span>
                </div>
              </div>
            </CardContent>
          </Card>
        ))}
      </div>
    </div>
  );
}
