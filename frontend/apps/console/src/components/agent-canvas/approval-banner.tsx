import * as React from "react";
import { AlertTriangle, ShieldCheck, Check, X, Loader2 } from "lucide-react";
import { Button } from "@/components/ui/button";
import { Input } from "@/components/ui/input";
import {
  Dialog,
  DialogContent,
  DialogHeader,
  DialogTitle,
  DialogDescription,
  DialogFooter,
} from "@/components/ui/dialog";
import { agentService } from "@/api/services/agent.service";

interface ApprovalBannerProps {
  taskId: string;
  runId: string;
  approvalId: string;
  toolName: string;
  reason?: string;
  stepId?: string;
  toolArgs?: Record<string, unknown>;
  onDecided: (approved: boolean, responseReason?: string) => void;
}

export const ApprovalBanner: React.FC<ApprovalBannerProps> = ({
  taskId,
  runId,
  approvalId,
  toolName,
  reason,
  stepId,
  toolArgs,
  onDecided,
}) => {
  const [isModalOpen, setIsModalOpen] = React.useState(false);
  const [decisionPending, setDecisionPending] = React.useState<"approve" | "reject" | null>(null);
  const [rationale, setRationale] = React.useState("");
  const [error, setError] = React.useState<string | null>(null);

  const handleDecision = async (approved: boolean) => {
    setDecisionPending(approved ? "approve" : "reject");
    setError(null);
    try {
      await agentService.decideApproval(taskId, runId, approvalId, {
        approved,
        reason: rationale || (approved ? "Approved by operator via canvas" : "Rejected by operator"),
      });
      setIsModalOpen(false);
      onDecided(approved, rationale);
    } catch (err: unknown) {
      const msg = err instanceof Error ? err.message : "Failed to record approval decision";
      setError(msg);
    } finally {
      setDecisionPending(null);
    }
  };

  return (
    <>
      {/* Floating Action Banner */}
      <div
        className="mx-4 my-2 p-3.5 rounded-xl border border-rose-500/40 bg-rose-500/10 dark:bg-rose-950/40 shadow-lg flex flex-col sm:flex-row sm:items-center justify-between gap-3 animate-in fade-in slide-in-from-top-2"
        data-testid="approval-required-banner"
      >
        <div className="flex items-start gap-3">
          <div className="p-2 rounded-lg bg-rose-500/20 text-rose-600 dark:text-rose-400 mt-0.5">
            <AlertTriangle className="h-5 w-5" />
          </div>
          <div>
            <div className="flex items-center gap-2">
              <span className="text-xs font-bold uppercase tracking-wider text-rose-600 dark:text-rose-400">
                Human Approval Required
              </span>
              {stepId && (
                <span className="text-[10px] font-mono px-1.5 py-0.2 rounded bg-background/80 text-muted-foreground border">
                  Step: {stepId}
                </span>
              )}
            </div>
            <p className="text-xs font-medium text-foreground mt-0.5">
              Target Tool: <span className="font-mono font-bold text-primary">{toolName}</span>
            </p>
            <p className="text-[11px] text-muted-foreground mt-0.5">
              {reason || "Execution paused pending authorized operator decision."}
            </p>
          </div>
        </div>

        <div className="flex items-center gap-2 flex-shrink-0">
          <Button
            variant="outline"
            size="sm"
            onClick={() => setIsModalOpen(true)}
            className="text-xs h-8"
          >
            Inspect Arguments
          </Button>
          <Button
            variant="destructive"
            size="sm"
            onClick={() => handleDecision(false)}
            disabled={decisionPending !== null}
            className="text-xs h-8"
            data-testid="reject-approval-button"
          >
            {decisionPending === "reject" ? (
              <Loader2 className="h-3.5 w-3.5 animate-spin mr-1" />
            ) : (
              <X className="h-3.5 w-3.5 mr-1" />
            )}
            Reject
          </Button>
          <Button
            variant="default"
            size="sm"
            onClick={() => handleDecision(true)}
            disabled={decisionPending !== null}
            className="text-xs h-8 bg-emerald-600 hover:bg-emerald-700 text-white"
            data-testid="approve-approval-button"
          >
            {decisionPending === "approve" ? (
              <Loader2 className="h-3.5 w-3.5 animate-spin mr-1" />
            ) : (
              <Check className="h-3.5 w-3.5 mr-1" />
            )}
            Approve
          </Button>
        </div>
      </div>

      {/* Inspection & Rationale Modal */}
      <Dialog open={isModalOpen} onOpenChange={setIsModalOpen}>
        <DialogContent className="sm:max-w-md">
          <DialogHeader>
            <DialogTitle className="flex items-center gap-2 text-base">
              <ShieldCheck className="h-5 w-5 text-rose-500" />
              Authorize Dangerous Action
            </DialogTitle>
            <DialogDescription className="text-xs">
              Review parameters and provide optional rationale for the audit ledger.
            </DialogDescription>
          </DialogHeader>

          <div className="space-y-3 py-2 text-xs">
            <div className="p-2.5 rounded-lg border bg-muted/40 space-y-1">
              <div className="text-[10px] uppercase font-bold text-muted-foreground">Action</div>
              <div className="font-mono font-bold text-primary">{toolName}</div>
              <div className="text-muted-foreground text-[11px]">{reason}</div>
            </div>

            {toolArgs && Object.keys(toolArgs).length > 0 && (
              <div className="space-y-1">
                <span className="text-[10px] uppercase font-bold text-muted-foreground">
                  Tool Parameters
                </span>
                <pre className="p-2 rounded-lg border bg-muted/20 font-mono text-[11px] max-h-40 overflow-y-auto">
                  {JSON.stringify(toolArgs, null, 2)}
                </pre>
              </div>
            )}

            <div className="space-y-1.5">
              <span className="text-[10px] uppercase font-bold text-muted-foreground">
                Decision Rationale (Optional)
              </span>
              <Input
                placeholder="Reason or safety verification notes..."
                value={rationale}
                onChange={(e) => setRationale(e.target.value)}
                className="text-xs h-8"
              />
            </div>

            {error && (
              <div className="p-2 rounded-lg border border-destructive/40 bg-destructive/10 text-destructive text-xs">
                {error}
              </div>
            )}
          </div>

          <DialogFooter className="flex sm:justify-between gap-2">
            <Button
              variant="outline"
              size="sm"
              onClick={() => setIsModalOpen(false)}
              disabled={decisionPending !== null}
            >
              Cancel
            </Button>
            <div className="flex gap-2">
              <Button
                variant="destructive"
                size="sm"
                onClick={() => handleDecision(false)}
                disabled={decisionPending !== null}
              >
                {decisionPending === "reject" ? (
                  <Loader2 className="h-3.5 w-3.5 animate-spin mr-1" />
                ) : (
                  <X className="h-3.5 w-3.5 mr-1" />
                )}
                Reject
              </Button>
              <Button
                variant="default"
                size="sm"
                onClick={() => handleDecision(true)}
                disabled={decisionPending !== null}
                className="bg-emerald-600 hover:bg-emerald-700 text-white"
              >
                {decisionPending === "approve" ? (
                  <Loader2 className="h-3.5 w-3.5 animate-spin mr-1" />
                ) : (
                  <Check className="h-3.5 w-3.5 mr-1" />
                )}
                Approve Action
              </Button>
            </div>
          </DialogFooter>
        </DialogContent>
      </Dialog>
    </>
  );
};
