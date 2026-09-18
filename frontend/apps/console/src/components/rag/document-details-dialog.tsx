import * as React from "react";
import { FileText, Hash, Copy, Check } from "lucide-react";
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

export interface DocumentItem {
  id: string;
  source: string;
  indexedChunks: number;
  chunkIds: string[];
  tenantId: string;
  createdAt: string;
  status: "indexed" | "failed" | "processing";
  contentSnippet?: string;
  metadata?: Record<string, unknown>;
}

export interface DocumentDetailsDialogProps {
  document: DocumentItem | null;
  open: boolean;
  onOpenChange: (open: boolean) => void;
}

export function DocumentDetailsDialog({
  document,
  open,
  onOpenChange,
}: DocumentDetailsDialogProps) {
  const [copied, setCopied] = React.useState<boolean>(false);

  if (!document) return null;

  const handleCopyChunkIds = () => {
    navigator.clipboard.writeText(document.chunkIds.join("\n"));
    setCopied(true);
    setTimeout(() => setCopied(false), 2000);
  };

  return (
    <Dialog open={open} onOpenChange={onOpenChange}>
      <DialogContent className="max-w-lg">
        <DialogHeader>
          <div className="flex items-center gap-2">
            <div className="p-2 rounded-lg bg-primary/10 text-primary">
              <FileText className="h-5 w-5" />
            </div>
            <div>
              <DialogTitle className="truncate max-w-sm">{document.source}</DialogTitle>
              <DialogDescription>
                Document chunking and tenant indexing verification
              </DialogDescription>
            </div>
          </div>
        </DialogHeader>

        <div className="space-y-4 py-2 text-xs">
          {/* Metadata Grid */}
          <div className="grid grid-cols-2 gap-3 p-3 rounded-lg bg-muted/40 border">
            <div>
              <span className="text-muted-foreground block">Tenant Boundary</span>
              <span className="font-mono font-semibold text-foreground">{document.tenantId}</span>
            </div>
            <div>
              <span className="text-muted-foreground block">Indexed Chunks</span>
              <span className="font-semibold text-foreground">{document.indexedChunks} chunk(s)</span>
            </div>
            <div>
              <span className="text-muted-foreground block">Ingestion Timestamp</span>
              <span className="text-foreground">{document.createdAt}</span>
            </div>
            <div>
              <span className="text-muted-foreground block">Store Status</span>
              <Badge variant="outline" className="text-emerald-600 border-emerald-300">
                Indexed & Ready
              </Badge>
            </div>
          </div>

          {/* Chunk IDs List */}
          <div className="space-y-1.5">
            <div className="flex items-center justify-between">
              <span className="font-semibold text-foreground flex items-center gap-1.5">
                <Hash className="h-3.5 w-3.5 text-muted-foreground" />
                Deterministic Chunk IDs ({document.chunkIds.length})
              </span>
              <button
                type="button"
                onClick={handleCopyChunkIds}
                className="text-[11px] text-primary hover:underline flex items-center gap-1"
              >
                {copied ? (
                  <>
                    <Check className="h-3 w-3" /> Copied
                  </>
                ) : (
                  <>
                    <Copy className="h-3 w-3" /> Copy IDs
                  </>
                )}
              </button>
            </div>
            <div className="max-h-28 overflow-y-auto rounded border p-2 bg-muted/20 font-mono text-[11px] space-y-1">
              {document.chunkIds.map((cid) => (
                <div key={cid} className="truncate text-muted-foreground hover:text-foreground">
                  {cid}
                </div>
              ))}
            </div>
          </div>

          {/* Content Snippet */}
          {document.contentSnippet && (
            <div className="space-y-1.5">
              <span className="font-semibold text-foreground block">Passage Snippet</span>
              <div className="p-3 rounded-md border bg-muted/10 italic text-muted-foreground leading-relaxed">
                "{document.contentSnippet}"
              </div>
            </div>
          )}
        </div>

        <DialogFooter>
          <Button variant="outline" onClick={() => onOpenChange(false)}>
            Close
          </Button>
        </DialogFooter>
      </DialogContent>
    </Dialog>
  );
}
