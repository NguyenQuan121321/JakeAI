import { useState } from "react";
import { Bot, Coins, Zap, Database, ArrowUpRight, Play, KeyRound } from "lucide-react";
import { useNavigate } from "react-router-dom";
import { useAuth } from "@/context/auth-context";
import { MetricCard } from "@/components/ui/metric-card";
import { StatusIndicator } from "@/components/ui/status-indicator";
import { Button } from "@/components/ui/button";
import { Card, CardHeader, CardTitle, CardDescription, CardContent } from "@/components/ui/card";
import { Panel } from "@/components/ui/panel";
import { CodeBlock } from "@/components/ui/code-block";
import { Dialog, DialogContent, DialogHeader, DialogTitle, DialogDescription, DialogFooter } from "@/components/ui/dialog";
import { Input } from "@/components/ui/input";

export default function WorkspacePage() {
  const { activeWorkspace } = useAuth();
  const navigate = useNavigate();
  const [quickRunDialogOpen, setQuickRunDialogOpen] = useState(false);
  const [prompt, setPrompt] = useState("");

  const curlSnippet = `curl -X POST "https://api.jakeai.internal/v1/chat/completions" \\
  -H "Authorization: Bearer \${JAKEAI_API_KEY}" \\
  -H "X-Tenant-ID: ${activeWorkspace?.id || "tenant_jakeai_core"}" \\
  -H "Content-Type: application/json" \\
  -d '{
    "model": "jakeai-orchestrator-v1",
    "messages": [{"role": "user", "content": "Analyze token consumption"}]
  }'`;

  return (
    <div className="space-y-8">
      {/* Page Header */}
      <div className="flex flex-col sm:flex-row sm:items-center sm:justify-between gap-4">
        <div>
          <div className="flex items-center space-x-3">
            <h1 className="text-2xl font-bold tracking-tight text-foreground">Workspace Overview</h1>
            <StatusIndicator status="healthy" variant="badge" />
          </div>
          <p className="text-sm text-muted-foreground mt-1">
            Active Tenant: <span className="font-semibold text-foreground">{activeWorkspace?.name}</span> ({activeWorkspace?.environment})
          </p>
        </div>

        <div className="flex items-center space-x-2.5">
          <Button
            variant="outline"
            size="sm"
            onClick={() => navigate("/providers")}
            leftIcon={<KeyRound className="h-4 w-4" />}
          >
            Configure BYOK
          </Button>
          <Button
            size="sm"
            onClick={() => setQuickRunDialogOpen(true)}
            leftIcon={<Play className="h-4 w-4" />}
          >
            Launch Run
          </Button>
        </div>
      </div>

      {/* KPI Metric Cards */}
      <div className="grid grid-cols-1 sm:grid-cols-2 lg:grid-cols-4 gap-4">
        <MetricCard
          title="Active Autonomous Agents"
          value="18"
          change={{ value: "+3 new", trend: "up", label: "this week" }}
          icon={Bot}
        />
        <MetricCard
          title="Token Usage (24h)"
          value="4.2M"
          change={{ value: "-8.4%", trend: "down", label: "cache savings" }}
          icon={Coins}
        />
        <MetricCard
          title="Avg p95 Latency"
          value="240ms"
          change={{ value: "-45ms", trend: "down", label: "vs last run" }}
          icon={Zap}
        />
        <MetricCard
          title="Knowledge Embeddings"
          value="142,800"
          change={{ value: "+1,200", trend: "up", label: "synchronized" }}
          icon={Database}
        />
      </div>

      {/* Main Grid: Status & Telemetry */}
      <div className="grid grid-cols-1 lg:grid-cols-3 gap-6">
        {/* Left 2 Cols: Subsystems & Quick Integrations */}
        <div className="lg:col-span-2 space-y-6">
          <Panel
            title="System Service Status"
            description="Authoritative platform microservices and backend operational health"
            actions={<StatusIndicator status="healthy" variant="dot" />}
          >
            <div className="divide-y text-sm">
              <div className="py-3 flex items-center justify-between">
                <div>
                  <p className="font-medium">AI Orchestration Engine</p>
                  <p className="text-xs text-muted-foreground">Multi-agent worker execution pool</p>
                </div>
                <StatusIndicator status="running" variant="badge" />
              </div>
              <div className="py-3 flex items-center justify-between">
                <div>
                  <p className="font-medium">Semantic Vector Cache (Redis)</p>
                  <p className="text-xs text-muted-foreground">Deterministic response deduplication</p>
                </div>
                <StatusIndicator status="healthy" variant="badge" />
              </div>
              <div className="py-3 flex items-center justify-between">
                <div>
                  <p className="font-medium">BYOK Keystore & Gateway</p>
                  <p className="text-xs text-muted-foreground">Stateless zero-retention provider bridge</p>
                </div>
                <StatusIndicator status="healthy" variant="badge" />
              </div>
              <div className="py-3 flex items-center justify-between">
                <div>
                  <p className="font-medium">AI FinOps Hard Quota Watcher</p>
                  <p className="text-xs text-muted-foreground">Real-time spend ceiling enforcement</p>
                </div>
                <StatusIndicator status="idle" variant="badge" />
              </div>
            </div>
          </Panel>

          <Card>
            <CardHeader>
              <CardTitle className="text-base">Quick API Integration</CardTitle>
              <CardDescription>
                Invoke JakeAI OpenAI-compatible AI gateway from your backend or services.
              </CardDescription>
            </CardHeader>
            <CardContent>
              <CodeBlock code={curlSnippet} language="bash" title="Terminal cURL Request" />
            </CardContent>
          </Card>
        </div>

        {/* Right Col: Quick Navigation & Status Legend */}
        <div className="space-y-6">
          <Card>
            <CardHeader className="pb-3">
              <CardTitle className="text-base">Semantic Status Overview</CardTitle>
              <CardDescription>All 12 standardized system states</CardDescription>
            </CardHeader>
            <CardContent className="space-y-2">
              <div className="grid grid-cols-2 gap-2 text-xs">
                <StatusIndicator status="healthy" variant="pill" />
                <StatusIndicator status="running" variant="pill" />
                <StatusIndicator status="queued" variant="pill" />
                <StatusIndicator status="waiting_approval" variant="pill" />
                <StatusIndicator status="paused" variant="pill" />
                <StatusIndicator status="degraded" variant="pill" />
                <StatusIndicator status="failed" variant="pill" />
                <StatusIndicator status="blocked" variant="pill" />
                <StatusIndicator status="cancelled" variant="pill" />
                <StatusIndicator status="completed" variant="pill" />
                <StatusIndicator status="idle" variant="pill" />
                <StatusIndicator status="unknown" variant="pill" />
              </div>
            </CardContent>
          </Card>

          <Card>
            <CardHeader className="pb-3">
              <CardTitle className="text-base">Enterprise Modules</CardTitle>
              <CardDescription>Direct navigation</CardDescription>
            </CardHeader>
            <CardContent className="space-y-2">
              <Button
                variant="outline"
                className="w-full justify-between text-xs"
                onClick={() => navigate("/agent")}
              >
                <span>Agent Platform</span>
                <ArrowUpRight className="h-3.5 w-3.5 text-muted-foreground" />
              </Button>
              <Button
                variant="outline"
                className="w-full justify-between text-xs"
                onClick={() => navigate("/rag")}
              >
                <span>RAG Knowledge Base</span>
                <ArrowUpRight className="h-3.5 w-3.5 text-muted-foreground" />
              </Button>
              <Button
                variant="outline"
                className="w-full justify-between text-xs"
                onClick={() => navigate("/finops")}
              >
                <span>AI FinOps & Spend</span>
                <ArrowUpRight className="h-3.5 w-3.5 text-muted-foreground" />
              </Button>
              <Button
                variant="outline"
                className="w-full justify-between text-xs"
                onClick={() => navigate("/analytics")}
              >
                <span>Observability & Telemetry</span>
                <ArrowUpRight className="h-3.5 w-3.5 text-muted-foreground" />
              </Button>
            </CardContent>
          </Card>
        </div>
      </div>

      {/* Quick Run Launch Dialog */}
      <Dialog open={quickRunDialogOpen} onOpenChange={setQuickRunDialogOpen}>
        <DialogContent onClose={() => setQuickRunDialogOpen(false)}>
          <DialogHeader>
            <DialogTitle>Launch Autonomous Agent Run</DialogTitle>
            <DialogDescription>
              Submit an agent prompt to the JakeAI Orchestrator with active tenant isolation.
            </DialogDescription>
          </DialogHeader>
          <div className="space-y-4 py-2">
            <div className="space-y-1.5">
              <label htmlFor="agent-prompt" className="text-xs font-semibold">
                Prompt / Task Instruction
              </label>
              <Input
                id="agent-prompt"
                placeholder="e.g. Audit vector collection embeddings for drift..."
                value={prompt}
                onChange={(e) => setPrompt(e.target.value)}
              />
            </div>
          </div>
          <DialogFooter>
            <Button variant="outline" onClick={() => setQuickRunDialogOpen(false)}>
              Cancel
            </Button>
            <Button
              onClick={() => {
                setQuickRunDialogOpen(false);
                navigate("/agent/runs");
              }}
              leftIcon={<Play className="h-4 w-4" />}
            >
              Start Execution
            </Button>
          </DialogFooter>
        </DialogContent>
      </Dialog>
    </div>
  );
}
