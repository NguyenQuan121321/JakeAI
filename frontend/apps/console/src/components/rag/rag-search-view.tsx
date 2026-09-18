import * as React from "react";
import {
  Search,
  Copy,
  Check,
  Zap,
  AlertCircle,
} from "lucide-react";
import { Button } from "@/components/ui/button";
import { Input } from "@/components/ui/input";
import { Badge } from "@/components/ui/badge";
import { Card, CardHeader, CardTitle, CardDescription, CardContent } from "@/components/ui/card";
import { useRagQueryMutation } from "@/api/hooks/use-rag-query";
import type { RAGQueryResponse, DocumentChunk } from "@/api/types/domain";
import { ApiError } from "@/api/client/api-error";

export function RagSearchView() {
  const [query, setQuery] = React.useState<string>("perimeter security");
  const [topK, setTopK] = React.useState<number>(5);
  const [selectContext, setSelectContext] = React.useState<boolean>(true);
  const [maxContextTokens, setMaxContextTokens] = React.useState<number>(800);
  const [copiedChunkId, setCopiedChunkId] = React.useState<string | null>(null);
  const [searchResult, setSearchResult] = React.useState<RAGQueryResponse | null>(null);
  const [errorMessage, setErrorMessage] = React.useState<string | null>(null);

  const queryMutation = useRagQueryMutation();

  const handleSearch = async (e?: React.FormEvent) => {
    if (e?.preventDefault) e.preventDefault();
    if (!query.trim()) return;

    setErrorMessage(null);
    try {
      const res = await queryMutation.mutateAsync({
        query: query.trim(),
        top_k: topK,
        select_context: selectContext,
        max_context_tokens: maxContextTokens,
      });
      setSearchResult(res);
    } catch (err: unknown) {
      if (err instanceof ApiError) {
        setErrorMessage(err.message);
      } else {
        setErrorMessage(err instanceof Error ? err.message : "RAG query failed.");
      }
    }
  };

  const handleCopyChunk = (chunk: DocumentChunk) => {
    navigator.clipboard.writeText(chunk.content);
    setCopiedChunkId(chunk.chunk_id);
    setTimeout(() => setCopiedChunkId(null), 2000);
  };

  return (
    <div className="space-y-6">
      {/* Search Header & Form */}
      <Card>
        <CardHeader className="pb-3">
          <CardTitle className="text-base flex items-center gap-2">
            <Search className="h-4 w-4 text-primary" />
            Hybrid Dense & Lexical Search Workspace
          </CardTitle>
          <CardDescription className="text-xs">
            Query tenant-partitioned vector and keyword indexes with reciprocal rank fusion and context selection.
          </CardDescription>
        </CardHeader>
        <CardContent>
          <form onSubmit={handleSearch} className="space-y-4">
            <div className="flex flex-col sm:flex-row gap-2">
              <div className="flex-1 relative">
                <Input
                  placeholder="Enter semantic query (e.g. perimeter security, compliance rules)..."
                  value={query}
                  onChange={(e) => setQuery(e.target.value)}
                  disabled={queryMutation.isPending}
                  className="pr-10"
                />
              </div>
              <Button
                type="button"
                disabled={!query.trim() || queryMutation.isPending}
                isLoading={queryMutation.isPending}
                leftIcon={<Search className="h-4 w-4" />}
                onClick={() => handleSearch()}
                data-testid="rag-search-button"
              >
                Search Index
              </Button>
            </div>

            {/* Filter and Tuner Bar */}
            <div className="grid grid-cols-1 sm:grid-cols-3 gap-3 p-3 rounded-lg bg-muted/40 border text-xs">
              <div className="space-y-1">
                <label htmlFor="rag-top-k" className="font-medium text-foreground block">
                  Top-K Candidates: {topK}
                </label>
                <input
                  id="rag-top-k"
                  type="range"
                  min={1}
                  max={20}
                  value={topK}
                  onChange={(e) => setTopK(Number(e.target.value))}
                  disabled={queryMutation.isPending}
                  className="w-full accent-primary"
                />
              </div>

              <div className="flex items-center justify-between sm:justify-start gap-3">
                <div className="space-y-0.5">
                  <label htmlFor="rag-select-context" className="font-medium text-foreground block cursor-pointer">
                    Context Selection & Pruning
                  </label>
                  <span className="text-[11px] text-muted-foreground block">
                    Deduplication & budget packing
                  </span>
                </div>
                <input
                  id="rag-select-context"
                  type="checkbox"
                  checked={selectContext}
                  onChange={(e) => setSelectContext(e.target.checked)}
                  disabled={queryMutation.isPending}
                  className="h-4 w-4 rounded border-input text-primary focus:ring-primary"
                />
              </div>

              <div className="space-y-1">
                <label htmlFor="rag-max-tokens" className="font-medium text-foreground block">
                  Max Context Tokens
                </label>
                <Input
                  id="rag-max-tokens"
                  type="number"
                  min={100}
                  max={4000}
                  value={maxContextTokens}
                  onChange={(e) => setMaxContextTokens(Number(e.target.value))}
                  disabled={!selectContext || queryMutation.isPending}
                  className="h-8 text-xs"
                />
              </div>
            </div>
          </form>
        </CardContent>
      </Card>

      {/* Error Banner */}
      {errorMessage && (
        <div
          role="alert"
          className="p-3.5 rounded-lg bg-rose-50 border border-rose-200 text-rose-700 text-xs flex items-start gap-2.5 dark:bg-rose-950/40 dark:border-rose-900 dark:text-rose-300"
        >
          <AlertCircle className="h-4 w-4 shrink-0 mt-0.5" />
          <div>
            <span className="font-semibold block">Search Request Error</span>
            <span>{errorMessage}</span>
          </div>
        </div>
      )}

      {/* Reranking / Token Efficiency Metrics (Only if exposed by backend) */}
      {searchResult && (
        <div className="grid grid-cols-2 sm:grid-cols-4 gap-3">
          <div className="p-3 rounded-lg border bg-card text-xs space-y-0.5">
            <span className="text-muted-foreground block">Total Candidates</span>
            <span className="font-semibold text-base font-mono">{searchResult.total_candidates}</span>
          </div>
          <div className="p-3 rounded-lg border bg-card text-xs space-y-0.5">
            <span className="text-muted-foreground block">Latency</span>
            <span className="font-semibold text-base font-mono">{searchResult.latency_ms} ms</span>
          </div>
          <div className="p-3 rounded-lg border bg-card text-xs space-y-0.5">
            <span className="text-muted-foreground block">Context Tokens</span>
            <span className="font-semibold text-base font-mono">{searchResult.context_tokens ?? "N/A"}</span>
          </div>
          <div className="p-3 rounded-lg border bg-card text-xs space-y-0.5">
            <span className="text-muted-foreground block">Tokens Saved</span>
            <span className="font-semibold text-base font-mono text-emerald-600">
              {searchResult.tokens_saved !== null && searchResult.tokens_saved !== undefined
                ? `${searchResult.tokens_saved} (${Math.round((searchResult.reduction_ratio || 0) * 100)}%)`
                : "N/A"}
            </span>
          </div>
        </div>
      )}

      {/* Selected Context Structured View */}
      {searchResult?.selected_context && (
        <Card>
          <CardHeader className="pb-2">
            <CardTitle className="text-xs uppercase font-semibold text-muted-foreground tracking-wider flex items-center gap-1.5">
              <Zap className="h-3.5 w-3.5 text-primary" />
              Pruned Structured Context Envelope
            </CardTitle>
          </CardHeader>
          <CardContent>
            <pre className="p-3 rounded-md bg-muted/40 border font-mono text-xs text-foreground whitespace-pre-wrap leading-relaxed overflow-x-auto">
              {searchResult.selected_context}
            </pre>
          </CardContent>
        </Card>
      )}

      {/* Retrieved Chunks Results */}
      {searchResult && (
        <div className="space-y-3">
          <div className="flex items-center justify-between">
            <h3 className="text-sm font-semibold text-foreground">
              Retrieved Document Chunks ({searchResult.chunks.length})
            </h3>
            <span className="text-xs text-muted-foreground font-mono">
              Tenant: {searchResult.tenant_id}
            </span>
          </div>

          {searchResult.chunks.length === 0 ? (
            <div className="p-8 text-center rounded-lg border border-dashed text-xs text-muted-foreground">
              No matching document chunks found in tenant index.
            </div>
          ) : (
            <div className="space-y-3">
              {searchResult.chunks.map((chunk, idx) => (
                <div
                  key={chunk.chunk_id || idx}
                  className="p-4 rounded-lg border bg-card space-y-2 hover:border-primary/50 transition-colors"
                >
                  <div className="flex flex-col sm:flex-row sm:items-center justify-between gap-2 border-b pb-2">
                    <div className="flex items-center gap-2">
                      <Badge variant="outline" className="font-mono text-[10px]">
                        Chunk #{idx + 1}
                      </Badge>
                      <span className="font-semibold text-xs text-foreground truncate max-w-xs">
                        {chunk.source}
                      </span>
                    </div>

                    <div className="flex items-center gap-2 text-xs">
                      {chunk.score !== undefined && (
                        <span className="font-mono text-[11px] bg-primary/10 text-primary px-2 py-0.5 rounded font-semibold">
                          Score: {typeof chunk.score === "number" ? chunk.score.toFixed(3) : chunk.score}
                        </span>
                      )}
                      <button
                        type="button"
                        onClick={() => handleCopyChunk(chunk)}
                        className="text-xs text-muted-foreground hover:text-foreground flex items-center gap-1"
                      >
                        {copiedChunkId === chunk.chunk_id ? (
                          <>
                            <Check className="h-3 w-3 text-emerald-500" /> Copied
                          </>
                        ) : (
                          <>
                            <Copy className="h-3 w-3" /> Copy Passage
                          </>
                        )}
                      </button>
                    </div>
                  </div>

                  <p className="text-xs text-foreground leading-relaxed">
                    {chunk.content}
                  </p>

                  <div className="flex flex-wrap items-center justify-between gap-2 pt-1 text-[11px] text-muted-foreground font-mono">
                    <span>ID: {chunk.chunk_id}</span>
                    {chunk.metadata && Object.keys(chunk.metadata).length > 0 && (
                      <div className="flex items-center gap-1">
                        {Object.entries(chunk.metadata).map(([k, v]) => (
                          <span key={k} className="bg-muted px-1.5 py-0.5 rounded border text-[10px]">
                            {k}: {String(v)}
                          </span>
                        ))}
                      </div>
                    )}
                  </div>
                </div>
              ))}
            </div>
          )}
        </div>
      )}
    </div>
  );
}
