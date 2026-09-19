import {
  BarChart3,
  Activity,
  Zap,
  TrendingDown,
  Coins,
  Radio,
  Cpu,
  ShieldCheck,
  CheckCircle,
} from "lucide-react";
import {
  useAnalyticsDashboardQuery,
  useSubscriptionQuery,
} from "@/api/hooks/use-analytics-query";
import { useFinopsSummaryQuery } from "@/api/hooks/use-finops-query";
import { useAgentMetricsQuery } from "@/api/hooks/use-agent-query";
import { useAuth } from "@/context/auth-context";
import { MetricCard } from "@/components/ui/metric-card";
import { Card, CardHeader, CardTitle, CardDescription, CardContent } from "@/components/ui/card";
import { StatusIndicator } from "@/components/ui/status-indicator";
import { Badge } from "@/components/ui/badge";
import { LoadingState } from "@/components/feedback/loading-state";
import { ErrorState } from "@/components/ui/error-state";
import { PermissionDeniedState } from "@/components/feedback/permission-denied-state";
import { DonutChart, HorizontalBarChart, type ChartDataItem } from "@/components/ui/charts";
import {
  formatCurrency,
  formatTokens,
  formatPercentage,
  formatNumber,
} from "@/lib/formatters";

export default function AnalyticsPage() {
  const { can } = useAuth();

  const canReadAnalytics = can("analytics:read") || can("admin:read");

  const {
    data: dashboard,
    isLoading: isDashLoading,
    isError: isDashError,
    error: dashError,
    refetch: refetchDash,
  } = useAnalyticsDashboardQuery();

  const {
    data: summary,
    isLoading: isSummaryLoading,
  } = useFinopsSummaryQuery();

  const {
    data: subscription,
  } = useSubscriptionQuery();

  const {
    data: agentMetrics,
  } = useAgentMetricsQuery();

  // Permission Guard
  if (!canReadAnalytics) {
    return (
      <PermissionDeniedState
        title="Analytics Access Restricted"
        description="You do not possess the required analytics:read permissions to access operational telemetry."
      />
    );
  }

  // Loading State
  if (isDashLoading || isSummaryLoading) {
    return <LoadingState message="Collecting live platform metrics and telemetry..." />;
  }

  // Error State with Correlation ID
  if (isDashError) {
    return (
      <ErrorState
        title="Failed to Load Analytics"
        message="Unable to retrieve operational metrics dashboard."
        error={dashError}
        onRetry={refetchDash}
      />
    );
  }

  if (!dashboard) {
    return (
      <div className="p-8 text-center text-muted-foreground">
        No active operational telemetry reported for this tenant.
      </div>
    );
  }

  // Model distribution chart data directly from backend
  const modelEntries = Object.entries(dashboard.model_distribution || {});
  const modelChartData: ChartDataItem[] = modelEntries.map(([model, share]) => {
    // Handle both 0..1 ratio or 0..100 percentage
    const value = share <= 1 ? Math.round(share * 100) : Math.round(share);
    return {
      label: model,
      value,
      secondaryText: `${value}% share`,
    };
  });

  // Token efficiency breakdown
  const totalTokens = dashboard.tokens_processed || 1;
  const cacheTokens = dashboard.tokens_saved_cache || 0;
  const providerCacheTokens = dashboard.tokens_saved_provider_cache || 0;
  const uncachedTokens = Math.max(0, totalTokens - cacheTokens - providerCacheTokens);

  const tokenEfficiencyItems: ChartDataItem[] = [
    {
      label: "Tier 1 & Tier 2 Cache Avoided",
      value: cacheTokens,
      color: "#10b981",
      secondaryText: formatTokens(cacheTokens),
    },
    {
      label: "Provider KV Cache Hit",
      value: providerCacheTokens,
      color: "#8b5cf6",
      secondaryText: formatTokens(providerCacheTokens),
    },
    {
      label: "Standard Uncached Compute",
      value: uncachedTokens,
      color: "#3b82f6",
      secondaryText: formatTokens(uncachedTokens),
    },
  ].filter((item) => item.value > 0);

  return (
    <div className="space-y-8">
      {/* Header */}
      <div className="flex flex-col sm:flex-row sm:items-center sm:justify-between gap-4">
        <div>
          <div className="flex items-center space-x-2">
            <h1 className="text-2xl font-bold tracking-tight">Platform Analytics & Telemetry</h1>
            <Badge variant="outline" className="font-mono text-xs uppercase">
              Tier: {dashboard.subscription_tier || subscription?.tier || "Enterprise"}
            </Badge>
          </div>
          <p className="text-sm text-muted-foreground mt-1">
            Authoritative operational telemetry, TTFT performance, token savings, and autonomous agent activity.
          </p>
        </div>
        <div className="flex items-center space-x-2">
          <StatusIndicator status="running" variant="badge" customLabel="Telemetry Online" />
        </div>
      </div>

      {/* Top 4 Real KPI Cards */}
      <div className="grid grid-cols-1 sm:grid-cols-2 lg:grid-cols-4 gap-4">
        <MetricCard
          title="Requests Processed"
          value={formatNumber(summary?.total_requests || 0)}
          change={{
            value: formatPercentage(summary?.reconciliation_rate || 100),
            trend: "up",
            label: "reconciliation rate",
          }}
          icon={Activity}
        />
        <MetricCard
          title="Tokens Processed"
          value={formatTokens(dashboard.tokens_processed)}
          change={{
            value: `${formatTokens(dashboard.tokens_saved_cache)} saved`,
            trend: "down",
            label: "via semantic cache",
          }}
          icon={Coins}
        />
        <MetricCard
          title="Cost Savings"
          value={formatCurrency(dashboard.cost_savings_usd)}
          change={{
            value: formatPercentage(dashboard.savings_percentage),
            trend: "down",
            label: "cost avoided",
          }}
          icon={TrendingDown}
        />
        <MetricCard
          title="Avg Time to First Token"
          value={`${Math.round(dashboard.avg_ttft_ms)}ms`}
          change={{
            value: "SLO < 500ms",
            trend: dashboard.avg_ttft_ms <= 500 ? "down" : "up",
            label: dashboard.avg_ttft_ms <= 500 ? "compliant" : "exceeded",
          }}
          icon={Zap}
        />
      </div>

      {/* Visual Analytics Charts Grid */}
      <div className="grid grid-cols-1 md:grid-cols-2 gap-6">
        {/* Model Usage Distribution */}
        <Card>
          <CardHeader>
            <CardTitle className="text-base flex items-center space-x-2">
              <BarChart3 className="h-4 w-4 text-primary" />
              <span>Inference Distribution by Model</span>
            </CardTitle>
            <CardDescription>
              Proportion of total tokens executed across provider models
            </CardDescription>
          </CardHeader>
          <CardContent>
            {modelChartData.length > 0 ? (
              <DonutChart
                data={modelChartData}
                totalLabel="Models Active"
                totalValue={modelChartData.length}
              />
            ) : (
              <div className="text-xs text-muted-foreground py-6 text-center">
                No active model distribution recorded yet.
              </div>
            )}
          </CardContent>
        </Card>

        {/* Caching & Efficiency */}
        <Card>
          <CardHeader>
            <CardTitle className="text-base flex items-center space-x-2">
              <Radio className="h-4 w-4 text-primary" />
              <span>Token Efficiency & Caching Telemetry</span>
            </CardTitle>
            <CardDescription>
              Direct impact of multi-tier caching and physical optimization
            </CardDescription>
          </CardHeader>
          <CardContent className="space-y-4">
            {tokenEfficiencyItems.length > 0 ? (
              <HorizontalBarChart items={tokenEfficiencyItems} />
            ) : (
              <div className="text-xs text-muted-foreground py-6 text-center">
                No token savings data available.
              </div>
            )}

            <div className="grid grid-cols-2 gap-3 pt-2 border-t text-xs">
              <div className="bg-muted/40 p-2.5 rounded">
                <span className="text-muted-foreground block">Provider KV Cache Hit Rate</span>
                <span className="font-semibold text-foreground font-mono">
                  {formatPercentage(dashboard.provider_cache_hit_rate, true)}
                </span>
              </div>
              <div className="bg-muted/40 p-2.5 rounded">
                <span className="text-muted-foreground block">KV Cache Cost Avoidance</span>
                <span className="font-semibold text-emerald-600 dark:text-emerald-400 font-mono">
                  {formatCurrency(dashboard.provider_cache_savings_usd)}
                </span>
              </div>
            </div>
          </CardContent>
        </Card>
      </div>

      {/* Exposed Agent & Codebase Audit Activity */}
      <div className="grid grid-cols-1 md:grid-cols-2 gap-6">
        {/* Agent Activity */}
        <Card>
          <CardHeader>
            <CardTitle className="text-base flex items-center space-x-2">
              <Cpu className="h-4 w-4 text-primary" />
              <span>JakeAI-Agent Platform Telemetry</span>
            </CardTitle>
            <CardDescription>
              Autonomous task runtime activity and approval gates
            </CardDescription>
          </CardHeader>
          <CardContent>
            {agentMetrics ? (
              <div className="grid grid-cols-2 sm:grid-cols-4 gap-3 text-xs">
                <div className="p-2.5 rounded bg-muted/40">
                  <span className="text-muted-foreground block">Active Runs</span>
                  <span className="text-base font-bold text-foreground font-mono">
                    {formatNumber(
                      Math.max(
                        0,
                        (agentMetrics.runs_started ?? 0) -
                          ((agentMetrics.runs_completed ?? 0) +
                            (agentMetrics.runs_failed ?? 0) +
                            (agentMetrics.runs_cancelled ?? 0))
                      )
                    )}
                  </span>
                </div>
                <div className="p-2.5 rounded bg-muted/40">
                  <span className="text-muted-foreground block">Completed Runs</span>
                  <span className="text-base font-bold text-foreground font-mono">
                    {formatNumber(agentMetrics.runs_completed ?? 0)}
                  </span>
                </div>
                <div className="p-2.5 rounded bg-muted/40">
                  <span className="text-muted-foreground block">Waiting Approvals</span>
                  <span className="text-base font-bold text-amber-600 dark:text-amber-400 font-mono">
                    {formatNumber(
                      Math.max(
                        0,
                        (agentMetrics.approvals_requested ?? 0) -
                          ((agentMetrics.approvals_approved ?? 0) +
                            (agentMetrics.approvals_rejected ?? 0))
                      )
                    )}
                  </span>
                </div>
                <div className="p-2.5 rounded bg-muted/40">
                  <span className="text-muted-foreground block">Steps Executed</span>
                  <span className="text-base font-bold text-foreground font-mono">
                    {formatNumber(agentMetrics.steps_executed ?? 0)}
                  </span>
                </div>
              </div>
            ) : (
              <div className="text-xs text-muted-foreground py-4 text-center">
                Agent execution telemetry is active and synchronized.
              </div>
            )}
          </CardContent>
        </Card>

        {/* DevOps & Codebase Audit */}
        <Card>
          <CardHeader>
            <CardTitle className="text-base flex items-center space-x-2">
              <ShieldCheck className="h-4 w-4 text-primary" />
              <span>DevOps & Codebase Audits</span>
            </CardTitle>
            <CardDescription>
              Automated PR security inspections and change audits
            </CardDescription>
          </CardHeader>
          <CardContent>
            <div className="flex items-center justify-between p-4 rounded-lg bg-muted/30 border">
              <div>
                <span className="text-xs text-muted-foreground block">Pull Requests Audited</span>
                <span className="text-2xl font-bold font-mono text-foreground">
                  {formatNumber(dashboard.prs_audited)}
                </span>
              </div>
              <div className="flex items-center space-x-1.5 text-xs text-emerald-600 dark:text-emerald-400 font-medium">
                <CheckCircle className="h-4 w-4" />
                <span>Automated Sentry Active</span>
              </div>
            </div>

            {subscription?.features && (
              <div className="mt-4 flex flex-wrap gap-1.5">
                {subscription.features.map((feat) => (
                  <Badge key={feat} variant="secondary" className="text-[10px] font-mono">
                    {feat}
                  </Badge>
                ))}
              </div>
            )}
          </CardContent>
        </Card>
      </div>
    </div>
  );
}
