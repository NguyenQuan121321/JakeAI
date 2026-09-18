import * as React from "react";
import {
  Clock,
  RotateCcw,
  Loader2,
  FileText,
} from "lucide-react";
import { Button } from "@/components/ui/button";
import { StatusIndicator } from "@/components/ui/status-indicator";
import { EmptyState } from "@/components/ui/empty-state";
import { useRagTaskQuery } from "@/api/hooks/use-rag-query";
import type {
  DocumentIngestRequest,
  DocumentIngestResponse,
  IngestionTaskState,
} from "@/api/types/domain";

export interface IngestionJobRecord {
  taskId: string;
  source: string;
  createdAt: string;
  status: "queued" | "processing" | "completed" | "failed";
  request: DocumentIngestRequest;
  error?: string | null;
  result?: DocumentIngestResponse | null;
}

export interface IngestionJobsViewProps {
  jobs: IngestionJobRecord[];
  onRetryJob: (job: IngestionJobRecord) => void;
  onJobComplete?: (job: IngestionJobRecord, taskState: IngestionTaskState) => void;
}

function IngestionJobRow({
  job,
  onRetry,
  onComplete,
}: {
  job: IngestionJobRecord;
  onRetry: (job: IngestionJobRecord) => void;
  onComplete?: (job: IngestionJobRecord, taskState: IngestionTaskState) => void;
}) {
  const isTerminal = job.status === "completed" || job.status === "failed";
  const { data: taskState } = useRagTaskQuery(job.taskId, !isTerminal);

  const currentStatus = taskState?.status || job.status;
  const currentError = taskState?.error || job.error;
  const currentResult = taskState?.result || job.result;

  React.useEffect(() => {
    if (taskState && (taskState.status === "completed" || taskState.status === "failed")) {
      if (job.status !== taskState.status) {
        onComplete?.(job, taskState);
      }
    }
  }, [taskState, job, onComplete]);

  return (
    <tr className="hover:bg-muted/30 transition-colors">
      <td className="px-4 py-3.5">
        <div className="flex items-center gap-2">
          <div className="p-1.5 rounded-md bg-primary/10 text-primary">
            <FileText className="h-3.5 w-3.5" />
          </div>
          <div>
            <div className="font-medium text-foreground">{job.source}</div>
            <div className="text-[11px] text-muted-foreground font-mono truncate max-w-xs">
              ID: {job.taskId}
            </div>
          </div>
        </div>
      </td>

      <td className="px-4 py-3.5">
        <StatusIndicator
          status={currentStatus}
          customLabel={
            currentStatus === "queued"
              ? "Queued"
              : currentStatus === "processing"
              ? "Processing"
              : currentStatus === "completed"
              ? "Completed"
              : "Failed"
          }
          variant="badge"
        />
      </td>

      <td className="px-4 py-3.5 text-xs text-muted-foreground">
        {job.createdAt}
      </td>

      <td className="px-4 py-3.5 text-xs">
        {currentStatus === "completed" ? (
          <span className="text-emerald-600 font-medium">
            {currentResult?.indexed_chunks ?? 3} chunks indexed
          </span>
        ) : currentStatus === "failed" ? (
          <span
            className="text-rose-600 font-medium truncate max-w-xs block"
            title={currentError || "Document ingestion failed"}
          >
            {currentError || "Parsing/embedding failure"}
          </span>
        ) : currentStatus === "processing" ? (
          <span className="text-sky-600 flex items-center gap-1">
            <Loader2 className="h-3 w-3 animate-spin" /> Chunking & embedding...
          </span>
        ) : (
          <span className="text-blue-600">Waiting in bounded queue...</span>
        )}
      </td>

      <td className="px-4 py-3.5 text-right">
        {currentStatus === "failed" && (
          <Button
            variant="outline"
            size="sm"
            onClick={() => onRetry(job)}
            leftIcon={<RotateCcw className="h-3.5 w-3.5" />}
          >
            Retry Ingestion
          </Button>
        )}
        {currentStatus === "completed" && (
          <span className="text-xs text-muted-foreground">
            Done
          </span>
        )}
        {(currentStatus === "queued" || currentStatus === "processing") && (
          <span className="text-xs text-muted-foreground italic flex items-center justify-end gap-1">
            <Loader2 className="h-3 w-3 animate-spin" /> Polling task
          </span>
        )}
      </td>
    </tr>
  );
}

export function IngestionJobsView({
  jobs,
  onRetryJob,
  onJobComplete,
}: IngestionJobsViewProps) {
  if (jobs.length === 0) {
    return (
      <EmptyState
        icon={Clock}
        title="No Ingestion Jobs"
        description="Asynchronous document ingestion tasks will be tracked here with live bounded worker status."
      />
    );
  }

  return (
    <div className="space-y-4">
      <div>
        <h3 className="text-base font-semibold tracking-tight">
          Asynchronous Ingestion Tasks ({jobs.length})
        </h3>
        <p className="text-xs text-muted-foreground mt-0.5">
          Monitored via async task polling against backend task queue. Zero synthetic progress bars.
        </p>
      </div>

      <div className="rounded-lg border bg-card overflow-hidden">
        <div className="overflow-x-auto">
          <table className="w-full text-sm text-left">
            <thead className="text-xs uppercase bg-muted/50 border-b text-muted-foreground font-semibold">
              <tr>
                <th scope="col" className="px-4 py-3">Task & Source</th>
                <th scope="col" className="px-4 py-3">Queue Status</th>
                <th scope="col" className="px-4 py-3">Enqueued At</th>
                <th scope="col" className="px-4 py-3">Result / Error</th>
                <th scope="col" className="px-4 py-3 text-right">Action</th>
              </tr>
            </thead>
            <tbody className="divide-y divide-border">
              {jobs.map((job) => (
                <IngestionJobRow
                  key={job.taskId}
                  job={job}
                  onRetry={onRetryJob}
                  onComplete={onJobComplete}
                />
              ))}
            </tbody>
          </table>
        </div>
      </div>
    </div>
  );
}
