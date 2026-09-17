import { Bot, Plus, Layers, ShieldCheck, Zap } from "lucide-react";
import { useNavigate } from "react-router-dom";
import { Button } from "@/components/ui/button";
import { Card, CardHeader, CardTitle, CardDescription, CardContent } from "@/components/ui/card";
import { StatusIndicator } from "@/components/ui/status-indicator";
import { MetricCard } from "@/components/ui/metric-card";
import { Badge } from "@/components/ui/badge";

interface AgentDef {
  id: string;
  name: string;
  role: string;
  model: string;
  status: "healthy" | "idle" | "running" | "degraded";
  toolCount: number;
  totalRuns: number;
}

const AGENTS: AgentDef[] = [
  {
    id: "agent_orchestrator",
    name: "Supervisor Orchestrator",
    role: "Task Decomposition & Plan Synthesis",
    model: "claude-3-5-sonnet",
    status: "healthy",
    toolCount: 12,
    totalRuns: 1420,
  },
  {
    id: "agent_coder",
    name: "Autonomous Coding Worker",
    role: "Full-stack code generation and refactoring",
    model: "gpt-4o",
    status: "running",
    toolCount: 8,
    totalRuns: 3840,
  },
  {
    id: "agent_rag_researcher",
    name: "RAG Document Retrieval Worker",
    role: "Semantic search across corporate vector collections",
    model: "text-embedding-3-small",
    status: "healthy",
    toolCount: 4,
    totalRuns: 8910,
  },
  {
    id: "agent_finops_guard",
    name: "FinOps Quota Sentry",
    role: "Hard spend ceiling & token optimization",
    model: "claude-3-haiku",
    status: "idle",
    toolCount: 3,
    totalRuns: 980,
  },
];

export default function AgentPage() {
  const navigate = useNavigate();

  return (
    <div className="space-y-8">
      {/* Header */}
      <div className="flex flex-col sm:flex-row sm:items-center sm:justify-between gap-4">
        <div>
          <h1 className="text-2xl font-bold tracking-tight">Agent Platform</h1>
          <p className="text-sm text-muted-foreground mt-1">
            Configure multi-agent topologies, tool registries, and supervisor planning trees.
          </p>
        </div>
        <div className="flex items-center space-x-2.5">
          <Button
            variant="outline"
            size="sm"
            onClick={() => navigate("/agent/runs")}
            leftIcon={<Layers className="h-4 w-4" />}
          >
            View Execution Runs
          </Button>
          <Button size="sm" leftIcon={<Plus className="h-4 w-4" />}>
            New Agent
          </Button>
        </div>
      </div>

      {/* Metrics */}
      <div className="grid grid-cols-1 sm:grid-cols-3 gap-4">
        <MetricCard title="Registered Agents" value="4" icon={Bot} />
        <MetricCard title="Total Tool Invocations" value="15,150" icon={Zap} />
        <MetricCard
          title="Policy & Boundary Checks"
          value="100% Passed"
          change={{ value: "0 leaks", trend: "up", label: "isolated" }}
          icon={ShieldCheck}
        />
      </div>

      {/* Agent Roster Grid */}
      <div className="grid grid-cols-1 md:grid-cols-2 gap-4">
        {AGENTS.map((agent) => (
          <Card key={agent.id} className="hover:border-primary/50 transition-colors">
            <CardHeader className="flex flex-row items-start justify-between space-y-0 pb-2">
              <div>
                <CardTitle className="text-base font-semibold">{agent.name}</CardTitle>
                <CardDescription className="text-xs mt-1">{agent.role}</CardDescription>
              </div>
              <StatusIndicator status={agent.status} variant="badge" />
            </CardHeader>
            <CardContent>
              <div className="mt-4 flex items-center justify-between text-xs border-t pt-3">
                <div className="flex items-center space-x-2">
                  <span className="text-muted-foreground">Model:</span>
                  <Badge variant="secondary" className="font-mono text-[10px]">
                    {agent.model}
                  </Badge>
                </div>
                <div className="flex items-center space-x-4 text-muted-foreground">
                  <span>{agent.toolCount} tools</span>
                  <span>{agent.totalRuns.toLocaleString()} runs</span>
                </div>
              </div>
            </CardContent>
          </Card>
        ))}
      </div>
    </div>
  );
}
