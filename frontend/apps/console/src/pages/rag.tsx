import * as React from "react";
import {
  Database,
  FileText,
  Clock,
  Search,
  Sparkles,
  Plus,
} from "lucide-react";
import { Tabs, TabsList, TabsTrigger, TabsContent } from "@/components/ui/tabs";
import { Button } from "@/components/ui/button";
import { KnowledgeBasesView } from "@/components/rag/knowledge-bases-view";
import { DocumentsView } from "@/components/rag/documents-view";
import { IngestionJobsView, type IngestionJobRecord } from "@/components/rag/ingestion-jobs-view";
import { RagSearchView } from "@/components/rag/rag-search-view";
import { GroundedGenerationView } from "@/components/rag/grounded-generation-view";
import { DocumentUploadDialog } from "@/components/rag/document-upload-dialog";
import type { DocumentItem } from "@/components/rag/document-details-dialog";
import { useSearchParams } from "react-router-dom";
import { useAuth } from "@/context/auth-context";
import { useRagIngestMutation } from "@/api/hooks/use-rag-query";
import type {
  DocumentIngestRequest,
  DocumentIngestResponse,
  IngestionTaskResponse,
  IngestionTaskState,
} from "@/api/types/domain";

export default function RagPage() {
  const { user } = useAuth();
  const tenantId = user?.tenantId || "tenant_jakeai_core";
  const normalizeTab = (raw: string | null): string => {
    if (!raw) return "knowledge-bases";
    if (raw === "search") return "search-test";
    if (raw === "generation") return "grounded-generation";
    return raw;
  };

  const [searchParams, setSearchParams] = useSearchParams();
  const [activeTab, setActiveTab] = React.useState<string>(normalizeTab(searchParams.get("tab")));

  React.useEffect(() => {
    const t = normalizeTab(searchParams.get("tab"));
    if (["knowledge-bases", "documents", "ingestion-jobs", "search-test", "grounded-generation"].includes(t)) {
      setActiveTab(t);
    }
  }, [searchParams]);

  const handleTabChange = (val: string) => {
    setActiveTab(val);
    setSearchParams((prev) => {
      const next = new URLSearchParams(prev);
      next.set("tab", val);
      return next;
    });
  };

  const [uploadDialogOpen, setUploadDialogOpen] = React.useState<boolean>(false);

  // Ingested documents list under this tenant
  const [documents, setDocuments] = React.useState<DocumentItem[]>([
    {
      id: "doc-sec-01",
      source: "security-handbook.pdf",
      indexedChunks: 12,
      chunkIds: [
        "security-handbook-0-f19a02",
        "security-handbook-1-b827e1",
        "security-handbook-2-7e9140",
      ],
      tenantId,
      createdAt: "2026-09-17 14:30:00 UTC",
      status: "indexed",
      contentSnippet:
        "Enterprise AI Security requires perimeter isolation, zero-retention vaults, and tenant-scoped AES-256-GCM keys.",
      metadata: { department: "SecOps", classification: "Internal" },
    },
    {
      id: "doc-cmp-02",
      source: "compliance-2026.pdf",
      indexedChunks: 8,
      chunkIds: [
        "compliance-2026-0-aa12b4",
        "compliance-2026-1-c038f9",
      ],
      tenantId,
      createdAt: "2026-09-16 09:15:00 UTC",
      status: "indexed",
      contentSnippet:
        "All inference requests enforce zero data retention and AES-256 encrypted vaults.",
      metadata: { department: "Compliance", classification: "Public" },
    },
  ]);

  // Asynchronous ingestion jobs
  const [jobs, setJobs] = React.useState<IngestionJobRecord[]>([
    {
      taskId: "task-seed-01",
      source: "architecture-adr.pdf",
      createdAt: "10 mins ago",
      status: "completed",
      request: {
        source: "architecture-adr.pdf",
        content: "ADR-0003: Zero retention keystore architecture.",
        chunk_size: 500,
        chunk_overlap: 50,
      },
      result: {
        status: "success",
        indexed_chunks: 4,
        chunk_ids: ["adr-0-123", "adr-1-456"],
        source: "architecture-adr.pdf",
        tenant_id: tenantId,
      },
    },
  ]);

  const ingestMutation = useRagIngestMutation();

  const totalChunks = React.useMemo(() => {
    return documents.reduce((acc, d) => acc + d.indexedChunks, 0);
  }, [documents]);

  const handleSuccessSync = (res: DocumentIngestResponse, req: DocumentIngestRequest) => {
    const newDoc: DocumentItem = {
      id: `doc-${Date.now()}`,
      source: res.source,
      indexedChunks: res.indexed_chunks,
      chunkIds: res.chunk_ids || [],
      tenantId: res.tenant_id,
      createdAt: new Date().toISOString().replace("T", " ").slice(0, 19) + " UTC",
      status: "indexed",
      contentSnippet: req.content.slice(0, 140) + "...",
      metadata: req.metadata,
    };
    setDocuments((prev) => [newDoc, ...prev]);
    setActiveTab("documents");
  };

  const handleSuccessAsync = (res: IngestionTaskResponse, req: DocumentIngestRequest) => {
    const newJob: IngestionJobRecord = {
      taskId: res.task_id,
      source: res.source,
      createdAt: "Just now",
      status: "queued",
      request: req,
    };
    setJobs((prev) => [newJob, ...prev]);
    setActiveTab("ingestion-jobs");
  };

  const handleJobComplete = (job: IngestionJobRecord, taskState: IngestionTaskState) => {
    setJobs((prev) =>
      prev.map((j) =>
        j.taskId === job.taskId
          ? {
              ...j,
              status: taskState.status as "completed" | "failed",
              error: taskState.error,
              result: taskState.result,
            }
          : j
      )
    );

    // If completed successfully, add to documents catalog
    if (taskState.status === "completed" && taskState.result) {
      const newDoc: DocumentItem = {
        id: `doc-${taskState.task_id}`,
        source: taskState.source,
        indexedChunks: taskState.result.indexed_chunks,
        chunkIds: taskState.result.chunk_ids || [],
        tenantId: taskState.tenant_id,
        createdAt: new Date().toISOString().replace("T", " ").slice(0, 19) + " UTC",
        status: "indexed",
        contentSnippet: taskState.content.slice(0, 140) + "...",
      };
      setDocuments((prev) => {
        if (prev.some((d) => d.source === newDoc.source)) return prev;
        return [newDoc, ...prev];
      });
    }
  };

  const handleRetryJob = async (job: IngestionJobRecord) => {
    try {
      const res = await ingestMutation.mutateAsync({
        request: job.request,
        asyncMode: true,
      });

      if ("task_id" in res && res.task_id) {
        const retriedJob: IngestionJobRecord = {
          taskId: res.task_id,
          source: res.source,
          createdAt: "Just now (Retry)",
          status: "queued",
          request: job.request,
        };
        setJobs((prev) => [retriedJob, ...prev]);
      }
    } catch {
      // Error handled
    }
  };

  return (
    <div className="space-y-8 pb-12" data-active-tab={activeTab}>
      {/* Header */}
      <div className="flex flex-col sm:flex-row sm:items-center sm:justify-between gap-4">
        <div>
          <div className="flex items-center gap-2.5">
            <h1 className="text-2xl font-bold tracking-tight">RAG & Knowledge Console</h1>
            <span className="text-xs font-mono bg-muted text-muted-foreground px-2 py-0.5 rounded border">
              Tenant: {tenantId}
            </span>
          </div>
          <p className="text-sm text-muted-foreground mt-1">
            Enterprise semantic knowledge base management, hybrid dense/sparse retrieval, and verified grounded answer synthesis.
          </p>
        </div>

        <Button
          size="sm"
          onClick={() => setUploadDialogOpen(true)}
          leftIcon={<Plus className="h-4 w-4" />}
        >
          Upload Document
        </Button>
      </div>

      {/* 5 Views Tabbed Navigation */}
      <Tabs value={activeTab} onValueChange={handleTabChange} className="space-y-6">
        <TabsList ariaLabel="RAG Console Views" className="grid grid-cols-2 sm:grid-cols-5 w-full">
          <TabsTrigger value="knowledge-bases" className="flex items-center gap-1.5 text-xs">
            <Database className="h-3.5 w-3.5" />
            Knowledge Bases
          </TabsTrigger>
          <TabsTrigger value="documents" className="flex items-center gap-1.5 text-xs">
            <FileText className="h-3.5 w-3.5" />
            Documents ({documents.length})
          </TabsTrigger>
          <TabsTrigger value="ingestion-jobs" className="flex items-center gap-1.5 text-xs">
            <Clock className="h-3.5 w-3.5" />
            Ingestion Jobs ({jobs.length})
          </TabsTrigger>
          <TabsTrigger value="search-test" className="flex items-center gap-1.5 text-xs">
            <Search className="h-3.5 w-3.5" />
            Search/Test
          </TabsTrigger>
          <TabsTrigger value="grounded-generation" className="flex items-center gap-1.5 text-xs">
            <Sparkles className="h-3.5 w-3.5" />
            Grounded Generation
          </TabsTrigger>
        </TabsList>

        {/* View 1: Knowledge Bases */}
        <TabsContent value="knowledge-bases">
          <KnowledgeBasesView
            documentCount={documents.length}
            totalChunks={totalChunks}
            lastUpdateText="Today at 14:30 UTC"
            onNavigateToUpload={() => setUploadDialogOpen(true)}
          />
        </TabsContent>

        {/* View 2: Documents */}
        <TabsContent value="documents">
          <DocumentsView
            documents={documents}
            onUploadClick={() => setUploadDialogOpen(true)}
          />
        </TabsContent>

        {/* View 3: Ingestion Jobs */}
        <TabsContent value="ingestion-jobs">
          <IngestionJobsView
            jobs={jobs}
            onRetryJob={handleRetryJob}
            onJobComplete={handleJobComplete}
          />
        </TabsContent>

        {/* View 4: Search/Test */}
        <TabsContent value="search-test">
          <RagSearchView />
        </TabsContent>

        {/* View 5: Grounded Generation */}
        <TabsContent value="grounded-generation">
          <GroundedGenerationView />
        </TabsContent>
      </Tabs>

      {/* Document Upload Modal */}
      <DocumentUploadDialog
        open={uploadDialogOpen}
        onOpenChange={setUploadDialogOpen}
        onSuccessSync={handleSuccessSync}
        onSuccessAsync={handleSuccessAsync}
      />
    </div>
  );
}
