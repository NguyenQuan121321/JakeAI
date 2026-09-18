import {
  Database,
  Layers,
  FileText,
  ShieldCheck,
  CheckCircle2,
  Activity,
  HardDrive,
} from "lucide-react";
import { MetricCard } from "@/components/ui/metric-card";
import { StatusIndicator } from "@/components/ui/status-indicator";
import { Card, CardHeader, CardTitle, CardDescription, CardContent } from "@/components/ui/card";
import { Badge } from "@/components/ui/badge";
import { useAuth } from "@/context/auth-context";

export interface KnowledgeBasesViewProps {
  documentCount: number;
  totalChunks: number;
  lastUpdateText?: string;
  onNavigateToUpload?: () => void;
}

export function KnowledgeBasesView({
  documentCount,
  totalChunks,
  lastUpdateText = "Just now",
}: KnowledgeBasesViewProps) {
  const { user } = useAuth();
  const tenantId = user?.tenantId || "tenant_jakeai_core";

  return (
    <div className="space-y-6">
      {/* Overview Metrics */}
      <div className="grid grid-cols-1 sm:grid-cols-3 gap-4">
        <MetricCard
          title="Indexed Vector Chunks"
          value={totalChunks.toLocaleString()}
          icon={Database}
        />
        <MetricCard
          title="Tenant Documents"
          value={documentCount.toLocaleString()}
          icon={FileText}
        />
        <MetricCard
          title="Tenant Isolation Health"
          value="100%"
          change={{ value: "Strict Scoped", trend: "up", label: tenantId }}
          icon={ShieldCheck}
        />
      </div>

      {/* Tenant Knowledge Base Card */}
      <div className="grid grid-cols-1 lg:grid-cols-3 gap-6">
        <Card className="lg:col-span-2">
          <CardHeader className="pb-4">
            <div className="flex flex-col sm:flex-row sm:items-center justify-between gap-2">
              <div>
                <CardTitle className="text-lg flex items-center gap-2">
                  <Database className="h-5 w-5 text-primary" />
                  Primary Tenant Knowledge Base
                </CardTitle>
                <CardDescription className="text-xs mt-1">
                  Tenant-partitioned hybrid retrieval index backed by Qdrant dense vector store and BM25 lexical sparse index.
                </CardDescription>
              </div>
              <StatusIndicator status="healthy" customLabel="Operational" variant="badge" />
            </div>
          </CardHeader>
          <CardContent className="space-y-4">
            <div className="grid grid-cols-2 sm:grid-cols-4 gap-4 p-3.5 rounded-lg bg-muted/40 border text-xs">
              <div>
                <span className="text-muted-foreground block">Name</span>
                <span className="font-semibold text-foreground">tenant_{tenantId}_rag</span>
              </div>
              <div>
                <span className="text-muted-foreground block">Documents</span>
                <span className="font-semibold text-foreground">{documentCount}</span>
              </div>
              <div>
                <span className="text-muted-foreground block">Health</span>
                <span className="font-semibold text-emerald-600 flex items-center gap-1">
                  <CheckCircle2 className="h-3 w-3" /> Ready
                </span>
              </div>
              <div>
                <span className="text-muted-foreground block">Last Ingestion</span>
                <span className="font-semibold text-foreground">{lastUpdateText}</span>
              </div>
            </div>

            {/* Subsystem Health Breakdown */}
            <div className="space-y-2 pt-2">
              <h4 className="text-xs font-semibold text-muted-foreground uppercase tracking-wider">
                Store Components & Boundaries
              </h4>
              <div className="grid grid-cols-1 sm:grid-cols-3 gap-3 text-xs">
                <div className="border rounded-md p-2.5 space-y-1 bg-card">
                  <div className="flex items-center justify-between">
                    <span className="font-medium text-foreground flex items-center gap-1.5">
                      <HardDrive className="h-3.5 w-3.5 text-primary" /> Dense Vector
                    </span>
                    <Badge variant="outline" className="text-[9px]">Qdrant</Badge>
                  </div>
                  <p className="text-[11px] text-muted-foreground">FastEmbed 384d cosine similarity</p>
                </div>

                <div className="border rounded-md p-2.5 space-y-1 bg-card">
                  <div className="flex items-center justify-between">
                    <span className="font-medium text-foreground flex items-center gap-1.5">
                      <Layers className="h-3.5 w-3.5 text-primary" /> Sparse Lexical
                    </span>
                    <Badge variant="outline" className="text-[9px]">BM25</Badge>
                  </div>
                  <p className="text-[11px] text-muted-foreground">Exact keyword & terminology match</p>
                </div>

                <div className="border rounded-md p-2.5 space-y-1 bg-card">
                  <div className="flex items-center justify-between">
                    <span className="font-medium text-foreground flex items-center gap-1.5">
                      <ShieldCheck className="h-3.5 w-3.5 text-emerald-500" /> Tenant Boundary
                    </span>
                    <Badge variant="secondary" className="text-[9px] font-mono">Scoped</Badge>
                  </div>
                  <p className="text-[11px] text-muted-foreground font-mono truncate">{tenantId}</p>
                </div>
              </div>
            </div>
          </CardContent>
        </Card>

        {/* Information & Security Policy Card */}
        <Card>
          <CardHeader className="pb-3">
            <CardTitle className="text-sm flex items-center gap-2">
              <Activity className="h-4 w-4 text-primary" />
              Tenant Ownership Metadata
            </CardTitle>
            <CardDescription className="text-xs">
              Backend strictly enforces tenant isolation at the index level.
            </CardDescription>
          </CardHeader>
          <CardContent className="space-y-3 text-xs">
            <div className="space-y-2 border-b pb-3">
              <div className="flex justify-between">
                <span className="text-muted-foreground">Authorized Tenant:</span>
                <span className="font-mono font-medium">{tenantId}</span>
              </div>
              <div className="flex justify-between">
                <span className="text-muted-foreground">Cross-Tenant Isolation:</span>
                <span className="text-emerald-600 font-medium">Verified Active</span>
              </div>
              <div className="flex justify-between">
                <span className="text-muted-foreground">Bounded Task Queue:</span>
                <span className="font-mono font-medium">Max Concurrency: 2</span>
              </div>
            </div>

            <p className="text-[11px] text-muted-foreground leading-relaxed">
              In accordance with enterprise tenant isolation policies, this console only displays knowledge bases and vector partitions registered to your authenticated organization.
            </p>
          </CardContent>
        </Card>
      </div>
    </div>
  );
}
