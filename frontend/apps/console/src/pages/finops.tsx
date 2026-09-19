import * as React from "react";
import {
  Coins,
  AlertOctagon,
  TrendingDown,
  DollarSign,
  PieChart,
  Edit3,
  Layers,
  Sparkles,
  ShieldCheck,
  CheckCircle2,
  AlertTriangle,
} from "lucide-react";
import { useFinopsSummaryQuery, useUpdateBudgetMutation, useFinopsTransactionsQuery } from "@/api/hooks/use-finops-query";
import { useAuth } from "@/context/auth-context";
import { MetricCard } from "@/components/ui/metric-card";
import { Card, CardHeader, CardTitle, CardDescription, CardContent } from "@/components/ui/card";
import { Alert, AlertTitle, AlertDescription } from "@/components/ui/alert";
import { StatusIndicator } from "@/components/ui/status-indicator";
import { Button } from "@/components/ui/button";
import { Input } from "@/components/ui/input";
import { Badge } from "@/components/ui/badge";
import {
  Dialog,
  DialogContent,
  DialogHeader,
  DialogTitle,
  DialogDescription,
  DialogFooter,
} from "@/components/ui/dialog";
import { LoadingState } from "@/components/feedback/loading-state";
import { ErrorState } from "@/components/ui/error-state";
import { PermissionDeniedState } from "@/components/feedback/permission-denied-state";
import { DataGrid, type ColumnDef } from "@/components/ui/data-grid";
import { DonutChart, HorizontalBarChart, MetricGauge, type ChartDataItem } from "@/components/ui/charts";
import {
  formatCurrency,
  formatTokens,
  formatPercentage,
  formatNumber,
} from "@/lib/formatters";
import type { FinOpsRecord } from "@/api/types/domain";

export default function FinOpsPage() {
  const { can } = useAuth();

  // Queries
  const {
    data: summary,
    isLoading: isSummaryLoading,
    isError: isSummaryError,
    error: summaryError,
    refetch: refetchSummary,
  } = useFinopsSummaryQuery();

  const {
    data: transactions = [],
    isLoading: isTxLoading,
  } = useFinopsTransactionsQuery();

  const updateBudgetMutation = useUpdateBudgetMutation();

  // Dialog State
  const [isEditDialogOpen, setIsEditDialogOpen] = React.useState(false);
  const [quotaInput, setQuotaInput] = React.useState<string>("");
  const [dollarInput, setDollarInput] = React.useState<string>("");
  const [thresholdInput, setThresholdInput] = React.useState<string>("80");
  const [formError, setFormError] = React.useState<string | null>(null);

  // Authorization Check
  const canReadFinOps = can("finops:read") || can("billing:read");
  const canWriteFinOps = can("finops:write") || can("billing:write");

  const budget = summary?.budget_status;

  // Open Edit Modal with Current Values
  const handleOpenEditDialog = () => {
    if (!budget) return;
    setQuotaInput(String(budget.token_quota || 5000000));
    setDollarInput(budget.dollar_budget_usd !== null && budget.dollar_budget_usd !== undefined ? String(budget.dollar_budget_usd) : "");
    setThresholdInput(String(Math.round((budget.warning_threshold || 0.8) * 100)));
    setFormError(null);
    setIsEditDialogOpen(true);
  };

  // Submit Budget Update
  const handleSaveBudget = async (e: React.FormEvent) => {
    e.preventDefault();
    setFormError(null);

    const quotaNum = parseInt(quotaInput.replace(/,/g, ""), 10);
    if (isNaN(quotaNum) || quotaNum < 10000) {
      setFormError("Token quota limit must be at least 10,000 tokens.");
      return;
    }

    let dollarNum: number | null = null;
    if (dollarInput.trim() !== "") {
      dollarNum = parseFloat(dollarInput.replace(/[$,]/g, ""));
      if (isNaN(dollarNum) || dollarNum < 1.0) {
        setFormError("Monthly dollar budget ceiling must be at least $1.00 USD.");
        return;
      }
    }

    const thresholdPercent = parseInt(thresholdInput, 10);
    if (isNaN(thresholdPercent) || thresholdPercent < 10 || thresholdPercent > 99) {
      setFormError("Warning threshold must be an integer between 10% and 99%.");
      return;
    }

    try {
      await updateBudgetMutation.mutateAsync({
        token_quota: quotaNum,
        dollar_budget_usd: dollarNum,
        warning_threshold: thresholdPercent / 100,
      });
      setIsEditDialogOpen(false);
    } catch (err: unknown) {
      setFormError(err instanceof Error ? err.message : "Failed to update budget thresholds.");
    }
  };

  // Permission Guard
  if (!canReadFinOps) {
    return (
      <PermissionDeniedState
        title="FinOps Access Restricted"
        description="You do not possess the required finops:read or billing:read permissions to view enterprise token accounting."
      />
    );
  }

  // Loading State
  if (isSummaryLoading) {
    return <LoadingState message="Reconciling enterprise FinOps ledger and token quotas..." />;
  }

  // Error State
  if (isSummaryError) {
    return (
      <ErrorState
        title="Failed to Load FinOps Summary"
        message="Unable to retrieve authoritative token spend telemetry from backend."
        error={summaryError}
        onRetry={refetchSummary}
      />
    );
  }

  if (!summary || !budget) {
    return (
      <div className="p-8 text-center text-muted-foreground">
        No active FinOps period records found for this tenant workspace.
      </div>
    );
  }

  // Savings Attribution Breakdown
  const attribution = summary.savings_attribution || {
    cache_hit_usd: 0,
    physical_reduction_usd: 0,
    provider_cache_usd: 0,
    model_routing_usd: 0,
    avoided_retries_usd: 0,
    total_savings_usd: 0,
  };

  const savingsItems: ChartDataItem[] = [
    {
      label: "Exact & Semantic Cache",
      value: attribution.cache_hit_usd,
      color: "#10b981",
      secondaryText: formatCurrency(attribution.cache_hit_usd),
    },
    {
      label: "Physical Token Pruning",
      value: attribution.physical_reduction_usd,
      color: "#3b82f6",
      secondaryText: formatCurrency(attribution.physical_reduction_usd),
    },
    {
      label: "Provider Prompt Cache",
      value: attribution.provider_cache_usd,
      color: "#8b5cf6",
      secondaryText: formatCurrency(attribution.provider_cache_usd),
    },
    {
      label: "Model Routing Optimization",
      value: attribution.model_routing_usd,
      color: "#f59e0b",
      secondaryText: formatCurrency(attribution.model_routing_usd),
    },
  ].filter((item) => item.value > 0);

  // Model breakdown from transactions
  const modelSpendMap: Record<string, { count: number; cost: number; tokens: number }> = {};
  transactions.forEach((tx) => {
    const key = tx.model || "unknown";
    if (!modelSpendMap[key]) {
      modelSpendMap[key] = { count: 0, cost: 0, tokens: 0 };
    }
    modelSpendMap[key].count += 1;
    modelSpendMap[key].cost += tx.actual_billed_cost_usd ?? tx.effective_cost_usd ?? 0;
    modelSpendMap[key].tokens += tx.raw_tokens || 0;
  });

  const modelChartData: ChartDataItem[] = Object.entries(modelSpendMap).map(([model, data]) => ({
    label: model,
    value: data.cost > 0 ? Number(data.cost.toFixed(4)) : data.tokens,
    secondaryText: data.cost > 0 ? formatCurrency(data.cost, 4) : `${formatTokens(data.tokens)} tok`,
  }));

type FinOpsLedgerRow = FinOpsRecord & { id: string };

  const transactionRows: FinOpsLedgerRow[] = transactions.map((tx) => ({
    ...tx,
    id: tx.request_id,
  }));

  // Table columns for transactions ledger
  const transactionColumns: ColumnDef<FinOpsLedgerRow>[] = [
    {
      key: "request_id",
      header: "Request ID",
      render: (tx) => (
        <span className="font-mono text-xs font-semibold text-foreground">
          {tx.request_id}
        </span>
      ),
      sortable: true,
    },
    {
      key: "provider",
      header: "Provider",
      render: (tx) => (
        <Badge variant="outline" className="font-mono text-[10px] uppercase">
          {tx.provider}
        </Badge>
      ),
      sortable: true,
    },
    {
      key: "model",
      header: "Model",
      render: (tx) => <span className="font-mono text-xs text-foreground">{tx.model}</span>,
      sortable: true,
    },
    {
      key: "tokens",
      header: "Tokens (Raw / Opt)",
      render: (tx) => (
        <div className="text-xs font-mono">
          <span className="font-medium text-foreground">{formatNumber(tx.raw_tokens)}</span>
          <span className="text-muted-foreground"> / {formatNumber(tx.optimized_tokens)}</span>
          {tx.cached_tokens > 0 && (
            <span className="ml-1 text-emerald-600 dark:text-emerald-400 font-semibold">
              ({formatNumber(tx.cached_tokens)} cached)
            </span>
          )}
        </div>
      ),
    },
    {
      key: "actual_billed_cost_usd",
      header: "Actual Cost",
      render: (tx) => (
        <span className="font-mono text-xs font-semibold text-foreground">
          {formatCurrency(tx.actual_billed_cost_usd ?? tx.effective_cost_usd, 4)}
        </span>
      ),
      sortable: true,
    },
    {
      key: "total_savings_usd",
      header: "Saved",
      render: (tx) => (
        <span className="font-mono text-xs font-medium text-emerald-600 dark:text-emerald-400">
          {formatCurrency(tx.total_savings_usd, 4)}
        </span>
      ),
      sortable: true,
    },
    {
      key: "reconciliation_status",
      header: "Reconciliation",
      render: (tx) => (
        <Badge
          variant={tx.reconciliation_status === "authoritative" ? "success" : "secondary"}
          className="text-[10px] uppercase font-mono"
        >
          {tx.reconciliation_status}
        </Badge>
      ),
    },
  ];

  // Over-limit check
  const isOverLimit = budget.is_suspended || budget.percentage_tokens_used >= 100 || (budget.percentage_dollars_used !== null && budget.percentage_dollars_used !== undefined && budget.percentage_dollars_used >= 100);
  const isNearThreshold = (budget.percentage_tokens_used >= budget.warning_threshold * 100 || (budget.percentage_dollars_used !== null && budget.percentage_dollars_used !== undefined && budget.percentage_dollars_used >= budget.warning_threshold * 100)) && !isOverLimit;

  return (
    <div className="space-y-8">
      {/* Header with Title & Action */}
      <div className="flex flex-col sm:flex-row sm:items-center sm:justify-between gap-4">
        <div>
          <div className="flex items-center space-x-2">
            <h1 className="text-2xl font-bold tracking-tight">AI FinOps & Token Governance</h1>
            <Badge variant="outline" className="font-mono text-xs">
              Period: {summary.period}
            </Badge>
          </div>
          <p className="text-sm text-muted-foreground mt-1">
            Authoritative multi-tenant cost reconciliation, token quota thresholds, and non-overlapping savings attribution.
          </p>
        </div>
        <div className="flex items-center space-x-2">
          {canWriteFinOps && (
            <Button
              size="sm"
              variant="outline"
              onClick={handleOpenEditDialog}
              leftIcon={<Edit3 className="h-4 w-4" />}
            >
              Edit Budget
            </Button>
          )}
        </div>
      </div>

      {/* Critical Over-limit Banner */}
      {isOverLimit && (
        <Alert variant="destructive">
          <AlertOctagon className="h-5 w-5" />
          <AlertTitle className="font-bold">Hard Quota Ceiling Exceeded — Tenant Suspended</AlertTitle>
          <AlertDescription>
            {budget.warning || "Allocated token quota or monthly spending ceiling has reached 100%. Non-critical inference operations are temporarily paused by the quota enforcement sentry."}
          </AlertDescription>
        </Alert>
      )}

      {/* Soft Warning Threshold Banner */}
      {isNearThreshold && (
        <Alert variant="warning">
          <AlertTriangle className="h-5 w-5" />
          <AlertTitle className="font-bold">Approaching Spend Warning Threshold</AlertTitle>
          <AlertDescription>
            Tenant usage has crossed the {Math.round(budget.warning_threshold * 100)}% alert ceiling. Consider adjusting token allocations or enabling response caching before reaching suspension limits.
          </AlertDescription>
        </Alert>
      )}

      {/* Authoritative Metrics Cards */}
      <div className="grid grid-cols-1 sm:grid-cols-2 lg:grid-cols-4 gap-4">
        <MetricCard
          title="Actual Billed Spend"
          value={formatCurrency(summary.total_actual_cost_usd)}
          change={{
            value: formatCurrency(summary.total_baseline_cost_usd),
            trend: "neutral",
            label: "baseline unoptimized",
          }}
          icon={DollarSign}
        />
        <MetricCard
          title="Attributed Cost Savings"
          value={formatCurrency(summary.total_savings_usd)}
          change={{
            value: formatPercentage(summary.overall_savings_percentage),
            trend: "down",
            label: "net savings ratio",
          }}
          icon={TrendingDown}
        />
        <MetricCard
          title="Tokens Processed"
          value={formatTokens(summary.total_raw_tokens)}
          change={{
            value: `${formatTokens(summary.total_physical_tokens_removed)} pruned`,
            trend: "up",
            label: "physical optimization",
          }}
          icon={Coins}
        />
        <MetricCard
          title="Budget Utilization"
          value={formatPercentage(budget.percentage_tokens_used)}
          change={{
            value: `${formatTokens(budget.tokens_remaining)} rem`,
            trend: isOverLimit ? "up" : "neutral",
            label: "of quota ceiling",
          }}
          icon={AlertOctagon}
        />
      </div>

      {/* Budget Status Gauges */}
      <Card>
        <CardHeader className="pb-3">
          <div className="flex items-center justify-between">
            <div>
              <CardTitle className="text-base flex items-center space-x-2">
                <ShieldCheck className="h-4 w-4 text-primary" />
                <span>Tenant Quota & Budget Enforcement</span>
              </CardTitle>
              <CardDescription>
                Live reconciliation against provider usage. Enforced before upstream inference execution.
              </CardDescription>
            </div>
            <StatusIndicator
              status={isOverLimit ? "suspended" : isNearThreshold ? "degraded" : "ready"}
              variant="badge"
              customLabel={isOverLimit ? "Suspended" : isNearThreshold ? "Near Limit" : "Active Quota"}
            />
          </div>
        </CardHeader>
        <CardContent className="space-y-6 pt-2">
          {/* Token Quota Progress */}
          <MetricGauge
            label="Monthly Token Quota"
            value={budget.tokens_used}
            limit={budget.token_quota}
            warningThreshold={budget.warning_threshold}
            valueText={formatTokens(budget.tokens_used)}
            limitText={formatTokens(budget.token_quota)}
          />

          {/* Optional Dollar Budget Progress */}
          {budget.dollar_budget_usd !== null && budget.dollar_budget_usd !== undefined && budget.dollar_budget_usd > 0 && (
            <MetricGauge
              label="Monthly Dollar Budget Ceiling"
              value={budget.dollar_spent_usd}
              limit={budget.dollar_budget_usd}
              warningThreshold={budget.warning_threshold}
              valueText={formatCurrency(budget.dollar_spent_usd)}
              limitText={formatCurrency(budget.dollar_budget_usd)}
            />
          )}

          <div className="grid grid-cols-2 sm:grid-cols-4 gap-4 pt-2 border-t text-xs">
            <div>
              <span className="text-muted-foreground block">Tokens Used</span>
              <span className="font-semibold text-foreground font-mono">{formatTokens(budget.tokens_used)}</span>
            </div>
            <div>
              <span className="text-muted-foreground block">Quota Limit</span>
              <span className="font-semibold text-foreground font-mono">{formatTokens(budget.token_quota)}</span>
            </div>
            <div>
              <span className="text-muted-foreground block">Tokens Remaining</span>
              <span className="font-semibold text-foreground font-mono">{formatTokens(budget.tokens_remaining)}</span>
            </div>
            <div>
              <span className="text-muted-foreground block">Reconciliation Truth</span>
              <span className="font-semibold text-emerald-600 dark:text-emerald-400 font-mono">
                {formatPercentage(summary.reconciliation_rate)} Authoritative
              </span>
            </div>
          </div>
        </CardContent>
      </Card>

      {/* Breakdown Cards Grid */}
      <div className="grid grid-cols-1 md:grid-cols-2 gap-6">
        {/* Savings Attribution Breakdown */}
        <Card>
          <CardHeader>
            <CardTitle className="text-base flex items-center space-x-2">
              <PieChart className="h-4 w-4 text-primary" />
              <span>Non-Overlapping Savings Attribution</span>
            </CardTitle>
            <CardDescription>
              Guarantees zero double-counting across optimization tiers
            </CardDescription>
          </CardHeader>
          <CardContent>
            {savingsItems.length > 0 ? (
              <HorizontalBarChart items={savingsItems} />
            ) : (
              <div className="text-xs text-muted-foreground py-6 text-center">
                Zero optimization savings recorded in the current active period.
              </div>
            )}
          </CardContent>
        </Card>

        {/* Model Distribution Breakdown */}
        <Card>
          <CardHeader>
            <CardTitle className="text-base flex items-center space-x-2">
              <Layers className="h-4 w-4 text-primary" />
              <span>Model Spend & Consumption</span>
            </CardTitle>
            <CardDescription>
              Cost distribution across upstream inference backends
            </CardDescription>
          </CardHeader>
          <CardContent>
            {modelChartData.length > 0 ? (
              <DonutChart
                data={modelChartData}
                totalLabel="Total Spend"
                totalValue={formatCurrency(summary.total_actual_cost_usd)}
              />
            ) : (
              <div className="text-xs text-muted-foreground py-6 text-center">
                No per-model ledger transactions recorded yet.
              </div>
            )}
          </CardContent>
        </Card>
      </div>

      {/* FinOps Recommendations (Derived from backend status truth) */}
      <Card>
        <CardHeader>
          <CardTitle className="text-base flex items-center space-x-2">
            <Sparkles className="h-4 w-4 text-primary" />
            <span>FinOps Optimization Recommendations</span>
          </CardTitle>
          <CardDescription>
            System recommendations based on tenant telemetry and cache utilization
          </CardDescription>
        </CardHeader>
        <CardContent>
          <div className="space-y-3 text-xs">
            {summary.budget_status.warning && (
              <div className="flex items-start space-x-3 p-3 rounded-lg border border-amber-500/20 bg-amber-500/5">
                <AlertTriangle className="h-4 w-4 text-amber-600 mt-0.5 flex-shrink-0" />
                <div>
                  <span className="font-semibold text-foreground">Quota Threshold Warning</span>
                  <p className="text-muted-foreground mt-0.5">{summary.budget_status.warning}</p>
                </div>
              </div>
            )}

            {summary.total_cached_tokens === 0 && (
              <div className="flex items-start space-x-3 p-3 rounded-lg border border-primary/20 bg-primary/5">
                <CheckCircle2 className="h-4 w-4 text-primary mt-0.5 flex-shrink-0" />
                <div>
                  <span className="font-semibold text-foreground">Enable Tier 1 / Tier 2 Response Caching</span>
                  <p className="text-muted-foreground mt-0.5">
                    Zero tokens were served from cache this month. Enabling exact and semantic cache in Gateway reduces latency to &lt;20ms and avoids 100% of upstream costs for repetitive queries.
                  </p>
                </div>
              </div>
            )}

            {summary.total_physical_tokens_removed > 0 && (
              <div className="flex items-start space-x-3 p-3 rounded-lg border border-emerald-500/20 bg-emerald-500/5">
                <CheckCircle2 className="h-4 w-4 text-emerald-600 mt-0.5 flex-shrink-0" />
                <div>
                  <span className="font-semibold text-foreground">Physical Token Pruning Effective</span>
                  <p className="text-muted-foreground mt-0.5">
                    {formatTokens(summary.total_physical_tokens_removed)} redundant tokens were pruned before upstream inference, saving {formatCurrency(attribution.physical_reduction_usd)} directly.
                  </p>
                </div>
              </div>
            )}

            {summary.budget_status.dollar_budget_usd === null && (
              <div className="flex items-start space-x-3 p-3 rounded-lg border bg-muted/40">
                <Coins className="h-4 w-4 text-muted-foreground mt-0.5 flex-shrink-0" />
                <div>
                  <span className="font-semibold text-foreground">Configure Dollar Budget Ceiling</span>
                  <p className="text-muted-foreground mt-0.5">
                    No explicit dollar expenditure ceiling is active. Setting a monthly dollar cap provides dual protection alongside token quotas.
                  </p>
                </div>
              </div>
            )}
          </div>
        </CardContent>
      </Card>

      {/* Transaction Accounting Ledger */}
      <Card>
        <CardHeader>
          <CardTitle className="text-base">Inference Accounting Ledger</CardTitle>
          <CardDescription>
            Per-request transaction records with separated local estimates and authoritative provider truth.
          </CardDescription>
        </CardHeader>
        <CardContent>
          {isTxLoading ? (
            <div className="py-8 text-center text-xs text-muted-foreground">
              Loading transactions ledger...
            </div>
          ) : transactions.length === 0 ? (
            <div className="py-8 text-center text-xs text-muted-foreground">
              No transactions recorded for this billing cycle.
            </div>
          ) : (
            <DataGrid
              data={transactionRows}
              columns={transactionColumns}
              pageSize={10}
              searchPlaceholder="Filter by request, provider, or model..."
            />
          )}
        </CardContent>
      </Card>

      {/* Edit Budget Modal Dialog */}
      <Dialog open={isEditDialogOpen} onOpenChange={setIsEditDialogOpen}>
        <DialogContent onClose={() => setIsEditDialogOpen(false)} className="max-w-md">
          <DialogHeader>
            <DialogTitle>Configure Tenant Budget & Quotas</DialogTitle>
            <DialogDescription>
              Set monthly token quota ceiling and dollar budget thresholds for this tenant.
            </DialogDescription>
          </DialogHeader>

          <form noValidate onSubmit={handleSaveBudget} className="space-y-4 my-2">
            {formError && (
              <Alert variant="destructive" className="py-2 text-xs">
                <AlertDescription>{formError}</AlertDescription>
              </Alert>
            )}

            <div className="space-y-1.5">
              <label htmlFor="quota-input" className="text-xs font-semibold text-foreground block">
                Monthly Token Quota Limit
              </label>
              <Input
                id="quota-input"
                type="number"
                min="10000"
                step="10000"
                value={quotaInput}
                onChange={(e) => setQuotaInput(e.target.value)}
                placeholder="e.g. 5000000"
                required
              />
              <p className="text-[11px] text-muted-foreground">
                Minimum 10,000 tokens. Current: {formatTokens(budget.token_quota)}
              </p>
            </div>

            <div className="space-y-1.5">
              <label htmlFor="dollar-input" className="text-xs font-semibold text-foreground block">
                Monthly Dollar Ceiling (USD)
              </label>
              <Input
                id="dollar-input"
                type="number"
                min="1"
                step="0.01"
                value={dollarInput}
                onChange={(e) => setDollarInput(e.target.value)}
                placeholder="Optional (e.g. 500.00)"
              />
              <p className="text-[11px] text-muted-foreground">
                Leave blank to govern by token quota only.
              </p>
            </div>

            <div className="space-y-1.5">
              <label htmlFor="threshold-input" className="text-xs font-semibold text-foreground block">
                Warning Threshold Alert (%)
              </label>
              <Input
                id="threshold-input"
                type="number"
                min="10"
                max="99"
                value={thresholdInput}
                onChange={(e) => setThresholdInput(e.target.value)}
                placeholder="e.g. 80"
                required
              />
              <p className="text-[11px] text-muted-foreground">
                Triggers warning alerts before reaching 100% hard ceiling.
              </p>
            </div>

            <DialogFooter className="mt-6">
              <Button
                type="button"
                variant="outline"
                size="sm"
                onClick={() => setIsEditDialogOpen(false)}
                disabled={updateBudgetMutation.isPending}
              >
                Cancel
              </Button>
              <Button
                type="submit"
                size="sm"
                disabled={updateBudgetMutation.isPending}
              >
                {updateBudgetMutation.isPending ? "Saving..." : "Save Budget"}
              </Button>
            </DialogFooter>
          </form>
        </DialogContent>
      </Dialog>
    </div>
  );
}
