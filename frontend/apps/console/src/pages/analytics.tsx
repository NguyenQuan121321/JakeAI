import { BarChart3, Activity, Zap, ShieldAlert, Radio } from "lucide-react";
import { MetricCard } from "@/components/ui/metric-card";
import { Card, CardHeader, CardTitle, CardDescription, CardContent } from "@/components/ui/card";
import { StatusIndicator } from "@/components/ui/status-indicator";
import { CodeBlock } from "@/components/ui/code-block";

export default function AnalyticsPage() {
  const prometheusSnippet = `# Prometheus scrape endpoint
# curl -H "Authorization: Bearer \${TOKEN}" https://api.jakeai.internal/metrics
jakeai_http_requests_total{method="POST",status="200"} 42819
jakeai_provider_latency_seconds_bucket{le="0.5"} 38920
jakeai_semantic_cache_hits_total 12930
jakeai_finops_tokens_consumed_total{model="gpt-4o"} 1829304`;

  return (
    <div className="space-y-8">
      {/* Header */}
      <div className="flex flex-col sm:flex-row sm:items-center sm:justify-between gap-4">
        <div>
          <h1 className="text-2xl font-bold tracking-tight">Analytics & Telemetry</h1>
          <p className="text-sm text-muted-foreground mt-1">
            End-to-end W3C distributed tracing, Prometheus telemetry, and service level objectives.
          </p>
        </div>
        <div className="flex items-center space-x-2">
          <StatusIndicator status="running" variant="badge" customLabel="Live Telemetry" />
        </div>
      </div>

      {/* Metrics */}
      <div className="grid grid-cols-1 sm:grid-cols-4 gap-4">
        <MetricCard
          title="HTTP Throughput"
          value="182 req/min"
          change={{ value: "+14%", trend: "up", label: "vs 1h ago" }}
          icon={Activity}
        />
        <MetricCard
          title="p95 Latency"
          value="240ms"
          change={{ value: "SLO < 500ms", trend: "neutral", label: "compliant" }}
          icon={Zap}
        />
        <MetricCard
          title="Error Rate (5xx)"
          value="0.02%"
          change={{ value: "-0.01%", trend: "down", label: "stable" }}
          icon={ShieldAlert}
        />
        <MetricCard
          title="Distributed Traces"
          value="100%"
          change={{ value: "W3C valid", trend: "up", label: "traceparent" }}
          icon={Radio}
        />
      </div>

      {/* Prometheus Telemetry Block */}
      <Card>
        <CardHeader>
          <CardTitle className="text-base flex items-center space-x-2">
            <BarChart3 className="h-4 w-4 text-primary" />
            <span>Authoritative Telemetry Exposition</span>
          </CardTitle>
          <CardDescription>
            Live OpenTelemetry metrics conformant with Prometheus text format 0.0.4.
          </CardDescription>
        </CardHeader>
        <CardContent>
          <CodeBlock code={prometheusSnippet} language="bash" title="/metrics Endpoint Output" />
        </CardContent>
      </Card>
    </div>
  );
}
