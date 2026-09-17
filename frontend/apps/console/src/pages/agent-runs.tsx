import * as React from "react";
import { ArrowLeft } from "lucide-react";
import { useNavigate } from "react-router-dom";
import { DataGrid, type ColumnDef } from "@/components/ui/data-grid";
import { StatusIndicator } from "@/components/ui/status-indicator";
import { Button } from "@/components/ui/button";
import { Dialog, DialogContent, DialogHeader, DialogTitle, DialogDescription, DialogFooter } from "@/components/ui/dialog";
import { CodeBlock } from "@/components/ui/code-block";
import type { SemanticStatus } from "@/types/status";

interface AgentRun {
  id: string;
  correlationId: string;
  agentName: string;
  task: string;
  status: SemanticStatus;
  durationMs: number;
  tokensUsed: number;
  createdAt: string;
  outputSummary?: string;
  errorDetail?: string;
}

const RUNS_DATA: AgentRun[] = [
  {
    id: "run-882",
    correlationId: "c-9a8b-11ef",
    agentName: "Autonomous Coding Worker",
    task: "Refactor backend session validator for zero token retention",
    status: "completed",
    durationMs: 3420,
    tokensUsed: 14200,
    createdAt: "2026-09-17 19:22:10",
    outputSummary: "10 files analyzed, 2 refactored, all tests passing.",
  },
  {
    id: "run-883",
    correlationId: "c-9a8c-22ff",
    agentName: "Supervisor Orchestrator",
    task: "Coordinate multi-model benchmark evaluation on 50 tasks",
    status: "running",
    durationMs: 12450,
    tokensUsed: 45000,
    createdAt: "2026-09-17 19:28:44",
  },
  {
    id: "run-884",
    correlationId: "c-9a8d-33aa",
    agentName: "RAG Document Retrieval Worker",
    task: "Vectorize SEC 10-K filings into financial collection",
    status: "waiting_approval",
    durationMs: 820,
    tokensUsed: 3100,
    createdAt: "2026-09-17 19:30:15",
    outputSummary: "Requires operator sign-off: batch size > 500 documents.",
  },
  {
    id: "run-885",
    correlationId: "c-9a8e-44bb",
    agentName: "Autonomous Coding Worker",
    task: "Deploy Caddy gateway proxy reverse rule for internal bridge",
    status: "failed",
    durationMs: 1840,
    tokensUsed: 8200,
    createdAt: "2026-09-17 19:31:02",
    errorDetail: "Provider upstream timeout (HTTP 504) after 3 exponential backoff retries.",
  },
  {
    id: "run-886",
    correlationId: "c-9a8f-55cc",
    agentName: "FinOps Quota Sentry",
    task: "Calculate daily token allocation ceiling for tenant_agent_sandbox",
    status: "completed",
    durationMs: 410,
    tokensUsed: 1200,
    createdAt: "2026-09-17 19:32:00",
    outputSummary: "Quota verified: 85,000 / 100,000 tokens utilized.",
  },
  {
    id: "run-887",
    correlationId: "c-9a90-66dd",
    agentName: "Supervisor Orchestrator",
    task: "Generate unit tests for auth-context and theme-context",
    status: "queued",
    durationMs: 0,
    tokensUsed: 0,
    createdAt: "2026-09-17 19:34:22",
  },
];

export default function AgentRunsPage() {
  const navigate = useNavigate();
  const [selectedRun, setSelectedRun] = React.useState<AgentRun | null>(null);
  const [statusFilter, setStatusFilter] = React.useState<string>("all");

  const filteredData = React.useMemo(() => {
    if (statusFilter === "all") return RUNS_DATA;
    return RUNS_DATA.filter((run) => run.status === statusFilter);
  }, [statusFilter]);

  const columns: ColumnDef<AgentRun>[] = [
    {
      key: "id",
      header: "Run ID",
      sortable: true,
      render: (run) => (
        <span className="font-mono text-xs font-semibold text-primary">{run.id}</span>
      ),
    },
    {
      key: "agentName",
      header: "Agent",
      sortable: true,
      render: (run) => <span className="font-medium text-xs">{run.agentName}</span>,
    },
    {
      key: "task",
      header: "Task / Goal",
      render: (run) => (
        <span className="text-xs text-muted-foreground truncate max-w-xs block" title={run.task}>
          {run.task}
        </span>
      ),
    },
    {
      key: "status",
      header: "Status",
      sortable: true,
      render: (run) => <StatusIndicator status={run.status} variant="badge" />,
    },
    {
      key: "durationMs",
      header: "Latency",
      sortable: true,
      render: (run) => (
        <span className="font-mono text-xs text-muted-foreground">
          {run.durationMs > 0 ? `${run.durationMs}ms` : "—"}
        </span>
      ),
    },
    {
      key: "tokensUsed",
      header: "Tokens",
      sortable: true,
      render: (run) => (
        <span className="font-mono text-xs text-muted-foreground">
          {run.tokensUsed > 0 ? run.tokensUsed.toLocaleString() : "—"}
        </span>
      ),
    },
    {
      key: "createdAt",
      header: "Timestamp",
      sortable: true,
      render: (run) => <span className="text-xs text-muted-foreground">{run.createdAt}</span>,
    },
  ];

  return (
    <div className="space-y-6">
      {/* Header */}
      <div className="flex flex-col sm:flex-row sm:items-center sm:justify-between gap-4">
        <div>
          <div className="flex items-center space-x-2">
            <Button
              variant="ghost"
              size="icon"
              onClick={() => navigate("/agent")}
              aria-label="Back to Agent Platform"
            >
              <ArrowLeft className="h-4 w-4" />
            </Button>
            <h1 className="text-2xl font-bold tracking-tight">Agent Execution Runs</h1>
          </div>
          <p className="text-sm text-muted-foreground mt-1 ml-9">
            Real-time audit log of multi-agent runs, execution traces, and token accounting.
          </p>
        </div>
      </div>

      {/* Filter Tabs */}
      <div className="flex flex-wrap items-center gap-2 pb-2">
        {["all", "running", "completed", "waiting_approval", "failed", "queued"].map((st) => (
          <Button
            key={st}
            variant={statusFilter === st ? "default" : "outline"}
            size="sm"
            onClick={() => setStatusFilter(st)}
            className="text-xs capitalize"
          >
            {st.replace("_", " ")}
          </Button>
        ))}
      </div>

      {/* Runs DataGrid */}
      <DataGrid
        data={filteredData}
        columns={columns}
        pageSize={10}
        searchPlaceholder="Search by task, agent or correlation ID..."
        onRowClick={(run) => setSelectedRun(run)}
      />

      {/* Run Detail Modal */}
      {selectedRun && (
        <Dialog open={!!selectedRun} onOpenChange={(open) => !open && setSelectedRun(null)}>
          <DialogContent onClose={() => setSelectedRun(null)} className="max-w-2xl">
            <DialogHeader>
              <div className="flex items-center justify-between pr-6">
                <DialogTitle>Execution Run: {selectedRun.id}</DialogTitle>
                <StatusIndicator status={selectedRun.status} variant="badge" />
              </div>
              <DialogDescription>
                Correlation Trace ID: <span className="font-mono text-primary">{selectedRun.correlationId}</span>
              </DialogDescription>
            </DialogHeader>

            <div className="space-y-4 py-2 text-xs">
              <div className="grid grid-cols-2 sm:grid-cols-4 gap-3 border rounded-md p-3 bg-muted/30">
                <div>
                  <span className="text-muted-foreground block">Agent:</span>
                  <span className="font-semibold text-foreground">{selectedRun.agentName}</span>
                </div>
                <div>
                  <span className="text-muted-foreground block">Duration:</span>
                  <span className="font-mono text-foreground">{selectedRun.durationMs}ms</span>
                </div>
                <div>
                  <span className="text-muted-foreground block">Tokens:</span>
                  <span className="font-mono text-foreground">{selectedRun.tokensUsed.toLocaleString()}</span>
                </div>
                <div>
                  <span className="text-muted-foreground block">Started:</span>
                  <span className="text-foreground">{selectedRun.createdAt}</span>
                </div>
              </div>

              <div>
                <span className="text-muted-foreground block mb-1 font-medium">Task Prompt:</span>
                <p className="rounded border bg-background p-2.5 text-foreground leading-relaxed">
                  {selectedRun.task}
                </p>
              </div>

              {selectedRun.outputSummary && (
                <div>
                  <span className="text-muted-foreground block mb-1 font-medium">Output Summary:</span>
                  <p className="rounded border bg-background p-2.5 text-foreground leading-relaxed">
                    {selectedRun.outputSummary}
                  </p>
                </div>
              )}

              {selectedRun.errorDetail && (
                <div>
                  <span className="text-destructive block mb-1 font-medium">Failure Reason:</span>
                  <div className="rounded border border-destructive/30 bg-destructive/10 p-2.5 text-destructive font-mono">
                    {selectedRun.errorDetail}
                  </div>
                </div>
              )}

              <div>
                <span className="text-muted-foreground block mb-1 font-medium">Trace Context Payload:</span>
                <CodeBlock
                  code={JSON.stringify(
                    {
                      trace_id: selectedRun.correlationId,
                      tenant_id: "tenant_jakeai_core",
                      run_id: selectedRun.id,
                      status: selectedRun.status,
                      tokens: selectedRun.tokensUsed,
                    },
                    null,
                    2
                  )}
                  language="json"
                />
              </div>
            </div>

            <DialogFooter>
              <Button variant="outline" onClick={() => setSelectedRun(null)}>
                Close
              </Button>
            </DialogFooter>
          </DialogContent>
        </Dialog>
      )}
    </div>
  );
}
