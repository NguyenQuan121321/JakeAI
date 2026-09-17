import { Database, Plus, Search, Layers, FileText } from "lucide-react";
import { Button } from "@/components/ui/button";
import { MetricCard } from "@/components/ui/metric-card";
import { StatusIndicator } from "@/components/ui/status-indicator";
import { Card, CardHeader, CardTitle, CardDescription, CardContent } from "@/components/ui/card";
import { Input } from "@/components/ui/input";

const COLLECTIONS = [
  {
    id: "col-1",
    name: "Engineering Architecture Docs",
    dimension: 1536,
    chunkCount: 12400,
    status: "healthy",
    updatedAt: "10 mins ago",
    model: "text-embedding-3-small",
  },
  {
    id: "col-2",
    name: "Security & Compliance ADRs",
    dimension: 1536,
    chunkCount: 4200,
    status: "healthy",
    updatedAt: "2 hours ago",
    model: "text-embedding-3-small",
  },
  {
    id: "col-3",
    name: "Customer API Specifications",
    dimension: 3072,
    chunkCount: 89000,
    status: "degraded",
    updatedAt: "1 day ago",
    model: "text-embedding-3-large",
  },
];

export default function RagPage() {
  return (
    <div className="space-y-8">
      {/* Header */}
      <div className="flex flex-col sm:flex-row sm:items-center sm:justify-between gap-4">
        <div>
          <h1 className="text-2xl font-bold tracking-tight">RAG & Knowledge Base</h1>
          <p className="text-sm text-muted-foreground mt-1">
            Manage semantic vector stores, chunking strategies, and hybrid retrieval indexes.
          </p>
        </div>
        <Button size="sm" leftIcon={<Plus className="h-4 w-4" />}>
          New Collection
        </Button>
      </div>

      {/* Metrics */}
      <div className="grid grid-cols-1 sm:grid-cols-3 gap-4">
        <MetricCard title="Total Vector Chunks" value="105,600" icon={Database} />
        <MetricCard
          title="Retrieval Grounding Rate"
          value="99.2%"
          change={{ value: "+0.4%", trend: "up", label: "hallucination-resistant" }}
          icon={FileText}
        />
        <MetricCard title="Active Vector Stores" value="3" icon={Layers} />
      </div>

      {/* Search Input Demo */}
      <div className="max-w-md">
        <Input
          placeholder="Semantic vector query search..."
          leftAdornment={<Search className="h-4 w-4" />}
        />
      </div>

      {/* Collections Grid */}
      <div className="grid grid-cols-1 md:grid-cols-3 gap-4">
        {COLLECTIONS.map((col) => (
          <Card key={col.id}>
            <CardHeader className="pb-3">
              <div className="flex items-start justify-between">
                <CardTitle className="text-base">{col.name}</CardTitle>
                <StatusIndicator status={col.status} variant="badge" />
              </div>
              <CardDescription className="text-xs">
                Dimension: {col.dimension} • {col.model}
              </CardDescription>
            </CardHeader>
            <CardContent>
              <div className="flex items-center justify-between text-xs text-muted-foreground border-t pt-3 mt-2">
                <span>{col.chunkCount.toLocaleString()} chunks</span>
                <span>Updated {col.updatedAt}</span>
              </div>
            </CardContent>
          </Card>
        ))}
      </div>
    </div>
  );
}
