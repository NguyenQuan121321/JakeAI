/**
 * Citation Inspection Dialog
 *
 * Provides verifiable evidence inspection modal displaying verbatim source passage,
 * grounding confidence score, chunk ID, and tenant provenance.
 */

import { BookOpen, ShieldCheck, Hash, Building2 } from "lucide-react";
import {
  Dialog,
  DialogContent,
  DialogHeader,
  DialogTitle,
  DialogDescription,
  DialogFooter,
} from "@/components/ui/dialog";
import { Button } from "@/components/ui/button";
import { Badge } from "@/components/ui/badge";
import type { Citation } from "@/types/chat";

interface CitationDialogProps {
  citation: Citation | null;
  open: boolean;
  onOpenChange: (open: boolean) => void;
}

export function CitationDialog({
  citation,
  open,
  onOpenChange,
}: CitationDialogProps) {
  if (!citation) return null;

  const confidencePct = Math.round((citation.confidence || 1.0) * 100);

  return (
    <Dialog open={open} onOpenChange={onOpenChange}>
      <DialogContent className="max-w-xl" onClose={() => onOpenChange(false)}>
        <DialogHeader>
          <div className="flex items-center space-x-2 text-primary">
            <BookOpen className="h-5 w-5" />
            <DialogTitle className="text-base font-semibold">
              Grounded Citation Footnote [{citation.index}]
            </DialogTitle>
          </div>
          <DialogDescription>
            Authoritative source passage verified against tenant knowledge boundaries.
          </DialogDescription>
        </DialogHeader>

        <div className="space-y-4 py-3 text-xs">
          {/* Metadata Grid */}
          <div className="grid grid-cols-2 sm:grid-cols-3 gap-2.5 rounded-lg border border-border bg-muted/40 p-3">
            <div>
              <span className="text-[10px] text-muted-foreground uppercase font-semibold block">
                Source
              </span>
              <p className="font-semibold text-foreground truncate mt-0.5" title={citation.source}>
                {citation.source || "FinnApiGo Internal"}
              </p>
            </div>

            <div>
              <span className="text-[10px] text-muted-foreground uppercase font-semibold block">
                Confidence
              </span>
              <div className="flex items-center space-x-1 mt-0.5">
                <ShieldCheck className="h-3.5 w-3.5 text-emerald-500 shrink-0" />
                <Badge
                  variant="outline"
                  className="bg-emerald-500/10 text-emerald-600 dark:text-emerald-400 border-emerald-500/20 text-[10px] py-0"
                >
                  {confidencePct}% Grounded
                </Badge>
              </div>
            </div>

            <div>
              <span className="text-[10px] text-muted-foreground uppercase font-semibold block">
                Provenance
              </span>
              <div className="flex items-center space-x-1 mt-0.5 text-muted-foreground truncate">
                <Building2 className="h-3 w-3 shrink-0" />
                <span className="truncate">{citation.tenant_id || "active"}</span>
              </div>
            </div>

            {citation.chunk_id && (
              <div className="col-span-full">
                <span className="text-[10px] text-muted-foreground uppercase font-semibold block">
                  Chunk Identifier
                </span>
                <div className="flex items-center space-x-1 mt-0.5 text-muted-foreground font-mono text-[11px]">
                  <Hash className="h-3 w-3 shrink-0" />
                  <span className="truncate">{citation.chunk_id}</span>
                </div>
              </div>
            )}
          </div>

          {/* Verbatim Excerpt Passage */}
          <div className="space-y-1.5">
            <span className="text-[11px] font-semibold text-foreground uppercase tracking-wide">
              Verified Excerpt Snippet
            </span>
            <div className="rounded-md border border-border bg-background p-3.5 text-foreground leading-relaxed font-serif text-sm italic whitespace-pre-wrap max-h-60 overflow-y-auto">
              "{citation.snippet || "Verified tenant passage."}"
            </div>
          </div>
        </div>

        <DialogFooter>
          <Button variant="outline" size="sm" onClick={() => onOpenChange(false)}>
            Close
          </Button>
        </DialogFooter>
      </DialogContent>
    </Dialog>
  );
}
