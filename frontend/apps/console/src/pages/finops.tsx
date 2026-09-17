import { Coins, AlertOctagon, TrendingDown, DollarSign, PieChart } from "lucide-react";
import { MetricCard } from "@/components/ui/metric-card";
import { Card, CardHeader, CardTitle, CardDescription, CardContent } from "@/components/ui/card";
import { Alert, AlertTitle, AlertDescription } from "@/components/ui/alert";
import { StatusIndicator } from "@/components/ui/status-indicator";

export default function FinOpsPage() {
  return (
    <div className="space-y-8">
      {/* Header */}
      <div>
        <h1 className="text-2xl font-bold tracking-tight">AI FinOps & Token Accounting</h1>
        <p className="text-sm text-muted-foreground mt-1">
          Monitor token consumption, enforce project spend ceilings, and maximize semantic cache savings.
        </p>
      </div>

      {/* Metrics */}
      <div className="grid grid-cols-1 sm:grid-cols-4 gap-4">
        <MetricCard
          title="Current Monthly Spend"
          value="$142.50"
          change={{ value: "47.5%", trend: "neutral", label: "of $300 ceiling" }}
          icon={DollarSign}
        />
        <MetricCard
          title="Cache Cost Avoidance"
          value="$38.40"
          change={{ value: "+12.3%", trend: "down", label: "saved this month" }}
          icon={TrendingDown}
        />
        <MetricCard
          title="Total Tokens Processed"
          value="18.9M"
          change={{ value: "+2.1M", trend: "up", label: "last 7 days" }}
          icon={Coins}
        />
        <MetricCard
          title="Hard Ceiling Sentry"
          value="Arm & Enforcing"
          change={{ value: "$300.00", trend: "neutral", label: "max cap" }}
          icon={AlertOctagon}
        />
      </div>

      {/* Spend Ceiling Alert */}
      <Alert variant="info">
        <AlertTitle>Hard Quota Watcher Invariant</AlertTitle>
        <AlertDescription>
          Requests are evaluated in real-time before provider invocation. If spend exceeds the $300.00 monthly threshold, non-essential jobs will transition to <StatusIndicator status="blocked" variant="inline" /> status automatically.
        </AlertDescription>
      </Alert>

      {/* Breakdown Cards */}
      <div className="grid grid-cols-1 md:grid-cols-2 gap-6">
        <Card>
          <CardHeader>
            <CardTitle className="text-base flex items-center space-x-2">
              <PieChart className="h-4 w-4 text-primary" />
              <span>Token Spend by Model</span>
            </CardTitle>
            <CardDescription>Distribution across LLM backends</CardDescription>
          </CardHeader>
          <CardContent>
            <div className="space-y-3 text-xs">
              <div>
                <div className="flex justify-between mb-1">
                  <span className="font-semibold">claude-3-5-sonnet</span>
                  <span>$84.20 (59%)</span>
                </div>
                <div className="h-2 w-full rounded-full bg-muted overflow-hidden">
                  <div className="h-full bg-primary rounded-full" style={{ width: "59%" }} />
                </div>
              </div>
              <div>
                <div className="flex justify-between mb-1">
                  <span className="font-semibold">gpt-4o</span>
                  <span>$42.10 (30%)</span>
                </div>
                <div className="h-2 w-full rounded-full bg-muted overflow-hidden">
                  <div className="h-full bg-sky-500 rounded-full" style={{ width: "30%" }} />
                </div>
              </div>
              <div>
                <div className="flex justify-between mb-1">
                  <span className="font-semibold">text-embedding-3-small</span>
                  <span>$16.20 (11%)</span>
                </div>
                <div className="h-2 w-full rounded-full bg-muted overflow-hidden">
                  <div className="h-full bg-emerald-500 rounded-full" style={{ width: "11%" }} />
                </div>
              </div>
            </div>
          </CardContent>
        </Card>

        <Card>
          <CardHeader>
            <CardTitle className="text-base flex items-center space-x-2">
              <Coins className="h-4 w-4 text-primary" />
              <span>Spend by Agent Platform</span>
            </CardTitle>
            <CardDescription>Attribution across autonomous roles</CardDescription>
          </CardHeader>
          <CardContent>
            <div className="space-y-3 text-xs">
              <div>
                <div className="flex justify-between mb-1">
                  <span className="font-semibold">Autonomous Coding Worker</span>
                  <span>$92.00 (65%)</span>
                </div>
                <div className="h-2 w-full rounded-full bg-muted overflow-hidden">
                  <div className="h-full bg-violet-500 rounded-full" style={{ width: "65%" }} />
                </div>
              </div>
              <div>
                <div className="flex justify-between mb-1">
                  <span className="font-semibold">Supervisor Orchestrator</span>
                  <span>$36.50 (25%)</span>
                </div>
                <div className="h-2 w-full rounded-full bg-muted overflow-hidden">
                  <div className="h-full bg-amber-500 rounded-full" style={{ width: "25%" }} />
                </div>
              </div>
              <div>
                <div className="flex justify-between mb-1">
                  <span className="font-semibold">RAG Document Retrieval Worker</span>
                  <span>$14.00 (10%)</span>
                </div>
                <div className="h-2 w-full rounded-full bg-muted overflow-hidden">
                  <div className="h-full bg-teal-500 rounded-full" style={{ width: "10%" }} />
                </div>
              </div>
            </div>
          </CardContent>
        </Card>
      </div>
    </div>
  );
}
