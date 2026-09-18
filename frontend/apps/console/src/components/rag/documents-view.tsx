import * as React from "react";
import { FileText, Plus, ExternalLink } from "lucide-react";
import { Button } from "@/components/ui/button";
import { StatusIndicator } from "@/components/ui/status-indicator";
import { EmptyState } from "@/components/ui/empty-state";
import { DocumentDetailsDialog, type DocumentItem } from "./document-details-dialog";

export interface DocumentsViewProps {
  documents: DocumentItem[];
  onUploadClick: () => void;
}

export function DocumentsView({ documents, onUploadClick }: DocumentsViewProps) {
  const [selectedDoc, setSelectedDoc] = React.useState<DocumentItem | null>(null);
  const [detailsOpen, setDetailsOpen] = React.useState<boolean>(false);

  const handleInspect = (doc: DocumentItem) => {
    setSelectedDoc(doc);
    setDetailsOpen(true);
  };

  if (documents.length === 0) {
    return (
      <EmptyState
        icon={FileText}
        title="No Documents Ingested Yet"
        description="Upload text documents, architecture records, or security guidelines to build your tenant knowledge base."
        action={
          <Button onClick={onUploadClick} leftIcon={<Plus className="h-4 w-4" />}>
            Upload First Document
          </Button>
        }
      />
    );
  }

  return (
    <div className="space-y-4">
      <div className="flex flex-col sm:flex-row sm:items-center justify-between gap-4">
        <div>
          <h3 className="text-base font-semibold tracking-tight">Tenant Documents ({documents.length})</h3>
          <p className="text-xs text-muted-foreground mt-0.5">
            Indexed into Qdrant dense vector store and BM25 lexical sparse index.
          </p>
        </div>
        <Button size="sm" onClick={onUploadClick} leftIcon={<Plus className="h-4 w-4" />}>
          Upload Document
        </Button>
      </div>

      <div className="rounded-lg border bg-card overflow-hidden">
        <div className="overflow-x-auto">
          <table className="w-full text-sm text-left">
            <thead className="text-xs uppercase bg-muted/50 border-b text-muted-foreground font-semibold">
              <tr>
                <th scope="col" className="px-4 py-3">Document Source</th>
                <th scope="col" className="px-4 py-3">Chunks</th>
                <th scope="col" className="px-4 py-3">Tenant Boundary</th>
                <th scope="col" className="px-4 py-3">Status</th>
                <th scope="col" className="px-4 py-3">Ingested At</th>
                <th scope="col" className="px-4 py-3 text-right">Action</th>
              </tr>
            </thead>
            <tbody className="divide-y divide-border">
              {documents.map((doc) => (
                <tr key={doc.id} className="hover:bg-muted/30 transition-colors">
                  <td className="px-4 py-3.5">
                    <div className="flex items-center gap-2">
                      <div className="p-1.5 rounded-md bg-primary/10 text-primary">
                        <FileText className="h-3.5 w-3.5" />
                      </div>
                      <span className="font-medium text-foreground">{doc.source}</span>
                    </div>
                  </td>

                  <td className="px-4 py-3.5">
                    <span className="font-mono text-xs bg-muted px-2 py-0.5 rounded border">
                      {doc.indexedChunks} chunk{doc.indexedChunks !== 1 ? "s" : ""}
                    </span>
                  </td>

                  <td className="px-4 py-3.5 font-mono text-xs text-muted-foreground">
                    {doc.tenantId}
                  </td>

                  <td className="px-4 py-3.5">
                    <StatusIndicator status="healthy" customLabel="Indexed" variant="badge" />
                  </td>

                  <td className="px-4 py-3.5 text-xs text-muted-foreground">
                    {doc.createdAt}
                  </td>

                  <td className="px-4 py-3.5 text-right">
                    <Button
                      variant="ghost"
                      size="sm"
                      onClick={() => handleInspect(doc)}
                      leftIcon={<ExternalLink className="h-3.5 w-3.5" />}
                    >
                      Details
                    </Button>
                  </td>
                </tr>
              ))}
            </tbody>
          </table>
        </div>
      </div>

      <DocumentDetailsDialog
        document={selectedDoc}
        open={detailsOpen}
        onOpenChange={setDetailsOpen}
      />
    </div>
  );
}
