import * as React from "react";
import { Upload, AlertCircle } from "lucide-react";
import {
  Dialog,
  DialogContent,
  DialogHeader,
  DialogTitle,
  DialogDescription,
  DialogFooter,
} from "@/components/ui/dialog";
import { Button } from "@/components/ui/button";
import { Input } from "@/components/ui/input";
import { Textarea } from "@/components/ui/textarea";
import { useRagIngestMutation } from "@/api/hooks/use-rag-query";
import type {
  DocumentIngestRequest,
  DocumentIngestResponse,
  IngestionTaskResponse,
} from "@/api/types/domain";
import { ApiError } from "@/api/client/api-error";

export interface DocumentUploadDialogProps {
  open: boolean;
  onOpenChange: (open: boolean) => void;
  onSuccessSync?: (res: DocumentIngestResponse, req: DocumentIngestRequest) => void;
  onSuccessAsync?: (res: IngestionTaskResponse, req: DocumentIngestRequest) => void;
}

export function DocumentUploadDialog({
  open,
  onOpenChange,
  onSuccessSync,
  onSuccessAsync,
}: DocumentUploadDialogProps) {
  const [source, setSource] = React.useState<string>("");
  const [content, setContent] = React.useState<string>("");
  const [chunkSize, setChunkSize] = React.useState<number>(500);
  const [chunkOverlap, setChunkOverlap] = React.useState<number>(50);
  const [asyncMode, setAsyncMode] = React.useState<boolean>(true);
  const [errorMessage, setErrorMessage] = React.useState<string | null>(null);

  const ingestMutation = useRagIngestMutation();

  React.useEffect(() => {
    if (open) {
      setErrorMessage(null);
    }
  }, [open]);

  const handleFileUpload = (e: React.ChangeEvent<HTMLInputElement>) => {
    const file = e.target.files?.[0];
    if (!file) return;

    if (!source) {
      setSource(file.name);
    }

    const reader = new FileReader();
    reader.onload = (event) => {
      const text = event.target?.result as string;
      if (text) {
        setContent(text);
      }
    };
    reader.readAsText(file);
  };

  const handleSubmit = async (e: React.FormEvent) => {
    e.preventDefault();
    if (!content.trim()) {
      setErrorMessage("Document content cannot be empty.");
      return;
    }

    setErrorMessage(null);
    const req: DocumentIngestRequest = {
      content: content.trim(),
      source: source.trim() || "document.txt",
      chunk_size: chunkSize,
      chunk_overlap: chunkOverlap,
    };

    try {
      const res = await ingestMutation.mutateAsync({
        request: req,
        asyncMode,
      });

      if ("task_id" in res && res.task_id) {
        onSuccessAsync?.(res as IngestionTaskResponse, req);
      } else {
        onSuccessSync?.(res as DocumentIngestResponse, req);
      }

      // Reset and close
      setSource("");
      setContent("");
      onOpenChange(false);
    } catch (err: unknown) {
      if (err instanceof ApiError) {
        setErrorMessage(err.message || "Document ingestion failed.");
      } else {
        setErrorMessage(err instanceof Error ? err.message : "Document ingestion failed.");
      }
    }
  };

  return (
    <Dialog open={open} onOpenChange={onOpenChange}>
      <DialogContent className="max-w-lg">
        <DialogHeader>
          <div className="flex items-center gap-2">
            <div className="p-2 rounded-lg bg-primary/10 text-primary">
              <Upload className="h-5 w-5" />
            </div>
            <div>
              <DialogTitle>Ingest Document into Knowledge Base</DialogTitle>
              <DialogDescription>
                Chunk, embed, and index text into your tenant-isolated RAG index.
              </DialogDescription>
            </div>
          </div>
        </DialogHeader>

        <form onSubmit={handleSubmit} className="space-y-4 py-2">
          {errorMessage && (
            <div
              role="alert"
              className="p-3 rounded-md bg-rose-50 border border-rose-200 text-rose-700 text-xs flex items-start gap-2 dark:bg-rose-950/40 dark:border-rose-900 dark:text-rose-300"
            >
              <AlertCircle className="h-4 w-4 shrink-0 mt-0.5" />
              <span>{errorMessage}</span>
            </div>
          )}

          {/* Document Source */}
          <div className="space-y-1.5">
            <label htmlFor="rag-doc-source" className="text-xs font-semibold text-foreground">
              Document Name / Source Identifier
            </label>
            <Input
              id="rag-doc-source"
              placeholder="e.g. security-handbook-2026.pdf"
              value={source}
              onChange={(e) => setSource(e.target.value)}
              disabled={ingestMutation.isPending}
              required
            />
          </div>

          {/* File Picker or Direct Text Input */}
          <div className="space-y-1.5">
            <div className="flex items-center justify-between">
              <label htmlFor="rag-doc-content" className="text-xs font-semibold text-foreground">
                Document Content
              </label>
              <label className="text-xs text-primary hover:underline cursor-pointer flex items-center gap-1">
                <Upload className="h-3 w-3" />
                Upload Text/PDF File
                <input
                  type="file"
                  className="hidden"
                  accept=".txt,.md,.json,.pdf"
                  onChange={handleFileUpload}
                  disabled={ingestMutation.isPending}
                />
              </label>
            </div>
            <Textarea
              id="rag-doc-content"
              rows={5}
              placeholder="Paste or type document content to be indexed..."
              value={content}
              onChange={(e) => setContent(e.target.value)}
              disabled={ingestMutation.isPending}
              required
            />
          </div>

          {/* Chunking Configuration */}
          <div className="grid grid-cols-2 gap-3 p-3 rounded-lg bg-muted/40 border">
            <div className="space-y-1">
              <label htmlFor="rag-chunk-size" className="text-xs font-medium text-foreground">
                Chunk Size (chars)
              </label>
              <Input
                id="rag-chunk-size"
                type="number"
                min={50}
                max={4000}
                value={chunkSize}
                onChange={(e) => setChunkSize(Number(e.target.value))}
                disabled={ingestMutation.isPending}
              />
            </div>
            <div className="space-y-1">
              <label htmlFor="rag-chunk-overlap" className="text-xs font-medium text-foreground">
                Overlap (chars)
              </label>
              <Input
                id="rag-chunk-overlap"
                type="number"
                min={0}
                max={1000}
                value={chunkOverlap}
                onChange={(e) => setChunkOverlap(Number(e.target.value))}
                disabled={ingestMutation.isPending}
              />
            </div>
          </div>

          {/* Async Mode Option */}
          <div className="flex items-center justify-between p-3 rounded-lg border bg-muted/20">
            <div className="space-y-0.5">
              <label htmlFor="rag-async-mode" className="text-xs font-semibold text-foreground block cursor-pointer">
                Asynchronous Task Queue (202 Accepted)
              </label>
              <span className="text-[11px] text-muted-foreground block">
                Enqueues job into bounded Redis queue for background worker indexing.
              </span>
            </div>
            <input
              id="rag-async-mode"
              type="checkbox"
              checked={asyncMode}
              onChange={(e) => setAsyncMode(e.target.checked)}
              disabled={ingestMutation.isPending}
              className="h-4 w-4 rounded border-input text-primary focus:ring-primary"
            />
          </div>

          <DialogFooter className="pt-2">
            <Button
              type="button"
              variant="outline"
              onClick={() => onOpenChange(false)}
              disabled={ingestMutation.isPending}
            >
              Cancel
            </Button>
            <Button
              type="submit"
              disabled={!content.trim() || ingestMutation.isPending}
              isLoading={ingestMutation.isPending}
              leftIcon={<Upload className="h-4 w-4" />}
              onClick={handleSubmit}
            >
              {asyncMode ? "Enqueue Ingestion Job" : "Ingest Synchronously"}
            </Button>
          </DialogFooter>
        </form>
      </DialogContent>
    </Dialog>
  );
}
