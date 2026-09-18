import * as React from "react";
import {
  Sparkles,
  ShieldCheck,
  AlertOctagon,
  CheckCircle2,
  BookOpen,
  AlertCircle,
} from "lucide-react";
import { Button } from "@/components/ui/button";
import { Input } from "@/components/ui/input";
import { Badge } from "@/components/ui/badge";
import { Card, CardHeader, CardTitle, CardDescription, CardContent } from "@/components/ui/card";
import {
  Dialog,
  DialogContent,
  DialogHeader,
  DialogTitle,
  DialogDescription,
} from "@/components/ui/dialog";
import { useRagGenerateMutation } from "@/api/hooks/use-rag-query";
import { ModelSelector } from "@/components/providers/model-selector";
import type { RAGGenerateResponse } from "@/api/types/domain";
import { ApiError } from "@/api/client/api-error";

type CitationItem = NonNullable<RAGGenerateResponse["citations"]>[number];

export function GroundedGenerationView() {
  const [query, setQuery] = React.useState<string>(
    "What are the security requirements for enterprise perimeter isolation?"
  );
  const [selectedProvider, setSelectedProvider] = React.useState<string>("openai");
  const [selectedModel, setSelectedModel] = React.useState<string>("gpt-4o");
  const [topK, setTopK] = React.useState<number>(5);
  const [maxContextTokens, setMaxContextTokens] = React.useState<number>(800);
  const [generationResult, setGenerationResult] = React.useState<RAGGenerateResponse | null>(null);
  const [selectedCitation, setSelectedCitation] = React.useState<CitationItem | null>(null);
  const [errorMessage, setErrorMessage] = React.useState<string | null>(null);

  const generateMutation = useRagGenerateMutation();

  const handleGenerate = async (e: React.FormEvent) => {
    e.preventDefault();
    if (!query.trim()) return;

    setErrorMessage(null);
    try {
      const res = await generateMutation.mutateAsync({
        query: query.trim(),
        model: selectedModel || undefined,
        top_k: topK,
        max_context_tokens: maxContextTokens,
      });
      setGenerationResult(res);
    } catch (err: unknown) {
      if (err instanceof ApiError) {
        setErrorMessage(err.message);
      } else {
        setErrorMessage(err instanceof Error ? err.message : "Grounded generation failed.");
      }
    }
  };

  // Grounding state interpretation strictly adhering to backend report
  const groundingState = React.useMemo(() => {
    if (!generationResult) return null;

    if (generationResult.status === "ABSTAINED") {
      const reason = generationResult.abstention_reason || "NO_RELEVANT_EVIDENCE";
      if (reason === "NO_RELEVANT_EVIDENCE") {
        return {
          label: "Abstained: Insufficient Evidence",
          variant: "amber" as const,
          description: "Model abstained because no factual evidence in tenant knowledge base supports this query.",
        };
      }
      if (reason === "CONTRADICTORY_EVIDENCE") {
        return {
          label: "Abstained: Contradictory Evidence",
          variant: "rose" as const,
          description: "Context passages contain conflicting statements.",
        };
      }
      if (reason === "GUARDRAIL_VIOLATION") {
        return {
          label: "Abstained: Guardrail Violation",
          variant: "rose" as const,
          description: "Prompt or retrieval output triggered platform safety policy.",
        };
      }
      return {
        label: `Abstained: ${reason}`,
        variant: "amber" as const,
        description: `Model abstained from synthesis. Reason code: ${reason}`,
      };
    }

    if (generationResult.status === "SUCCESS") {
      const g = generationResult.grounding as { is_grounded?: boolean } | undefined;
      const isGrounded = g?.is_grounded !== false;
      if (isGrounded) {
        return {
          label: "Grounded",
          variant: "emerald" as const,
          description: "Claims factually entailed and verified against retrieved tenant context passages.",
        };
      }
      return {
        label: "Partial Grounding",
        variant: "amber" as const,
        description: "Some claims could not be conclusively verified against source passages.",
      };
    }

    return {
      label: generationResult.status || "Unknown",
      variant: "neutral" as const,
      description: "Pipeline execution status reported by backend.",
    };
  }, [generationResult]);

  return (
    <div className="space-y-6">
      {/* Configuration & Form */}
      <Card>
        <CardHeader className="pb-3">
          <CardTitle className="text-base flex items-center gap-2">
            <Sparkles className="h-4 w-4 text-primary" />
            10-Step Grounded Synthesis Workbench
          </CardTitle>
          <CardDescription className="text-xs">
            Hybrid search, rerank, context envelope bounding, grounded synthesis, and citation verification.
          </CardDescription>
        </CardHeader>
        <CardContent>
          <form onSubmit={handleGenerate} className="space-y-4">
            <div className="space-y-1.5">
              <label htmlFor="rag-gen-query" className="text-xs font-semibold text-foreground">
                Question or Prompt
              </label>
              <Input
                id="rag-gen-query"
                placeholder="Ask a question requiring grounded tenant evidence..."
                value={query}
                onChange={(e) => setQuery(e.target.value)}
                disabled={generateMutation.isPending}
                required
              />
            </div>

            {/* Controlled Model Selector */}
            <div className="p-3 rounded-lg bg-muted/40 border">
              <ModelSelector
                selectedProvider={selectedProvider}
                selectedModel={selectedModel}
                onSelect={(prov, model) => {
                  setSelectedProvider(prov);
                  setSelectedModel(model);
                }}
                disabled={generateMutation.isPending}
                idPrefix="grounded-gen"
              />
            </div>

            {/* Generation Parameters */}
            <div className="grid grid-cols-1 sm:grid-cols-2 gap-3 text-xs">
              <div className="space-y-1">
                <label htmlFor="rag-gen-topk" className="font-medium text-foreground">
                  Candidate Chunks (Top-K): {topK}
                </label>
                <input
                  id="rag-gen-topk"
                  type="range"
                  min={1}
                  max={20}
                  value={topK}
                  onChange={(e) => setTopK(Number(e.target.value))}
                  disabled={generateMutation.isPending}
                  className="w-full accent-primary"
                />
              </div>

              <div className="space-y-1">
                <label htmlFor="rag-gen-tokens" className="font-medium text-foreground">
                  Context Token Budget Ceiling
                </label>
                <Input
                  id="rag-gen-tokens"
                  type="number"
                  min={100}
                  max={4000}
                  value={maxContextTokens}
                  onChange={(e) => setMaxContextTokens(Number(e.target.value))}
                  disabled={generateMutation.isPending}
                  className="h-8 text-xs"
                />
              </div>
            </div>

            <Button
              type="submit"
              disabled={!query.trim() || generateMutation.isPending}
              isLoading={generateMutation.isPending}
              leftIcon={<Sparkles className="h-4 w-4" />}
              onClick={handleGenerate}
            >
              Generate Grounded Answer
            </Button>
          </form>
        </CardContent>
      </Card>

      {/* Error Alert */}
      {errorMessage && (
        <div
          role="alert"
          className="p-3.5 rounded-lg bg-rose-50 border border-rose-200 text-rose-700 text-xs flex items-start gap-2.5 dark:bg-rose-950/40 dark:border-rose-900 dark:text-rose-300"
        >
          <AlertCircle className="h-4 w-4 shrink-0 mt-0.5" />
          <div>
            <span className="font-semibold block">Generation Error</span>
            <span>{errorMessage}</span>
          </div>
        </div>
      )}

      {/* Generation Result Section */}
      {generationResult && (
        <div className="space-y-6">
          {/* Status & Telemetry Row */}
          <div className="flex flex-col sm:flex-row sm:items-center justify-between gap-3 p-4 rounded-lg border bg-card">
            <div className="space-y-1">
              <span className="text-xs text-muted-foreground block">Grounding State</span>
              {groundingState && (
                <div className="flex items-center gap-2">
                  <span
                    role="status"
                    className={`inline-flex items-center gap-1.5 px-3 py-1 rounded-full text-xs font-semibold border ${
                      groundingState.variant === "emerald"
                        ? "bg-emerald-50 text-emerald-700 border-emerald-300 dark:bg-emerald-950/60 dark:text-emerald-300 dark:border-emerald-800"
                        : groundingState.variant === "rose"
                        ? "bg-rose-50 text-rose-700 border-rose-300 dark:bg-rose-950/60 dark:text-rose-300 dark:border-rose-800"
                        : "bg-amber-50 text-amber-700 border-amber-300 dark:bg-amber-950/60 dark:text-amber-300 dark:border-amber-800"
                    }`}
                  >
                    {groundingState.variant === "emerald" ? (
                      <CheckCircle2 className="h-4 w-4" />
                    ) : (
                      <AlertOctagon className="h-4 w-4" />
                    )}
                    <span>{groundingState.label}</span>
                  </span>
                  <span className="text-xs text-muted-foreground font-mono">
                    {generationResult.latency_ms} ms
                  </span>
                </div>
              )}
            </div>

            <div className="flex flex-wrap gap-4 text-xs">
              <div>
                <span className="text-muted-foreground block">Context Tokens</span>
                <span className="font-mono font-semibold">{generationResult.context_tokens}</span>
              </div>
              <div>
                <span className="text-muted-foreground block">Tokens Saved</span>
                <span className="font-mono font-semibold text-emerald-600">
                  {generationResult.tokens_saved} ({Math.round(generationResult.reduction_ratio * 100)}%)
                </span>
              </div>
              <div>
                <span className="text-muted-foreground block">Envelope</span>
                <span className="font-mono font-semibold">{generationResult.envelope_tokens ?? generationResult.context_tokens} tok</span>
              </div>
            </div>
          </div>

          {/* Generated Answer Card */}
          <Card>
            <CardHeader className="pb-3">
              <CardTitle className="text-base flex items-center justify-between">
                <span>Synthesized Answer</span>
                <Badge variant="outline" className="font-mono text-[11px]">
                  Tenant: {generationResult.tenant_id}
                </Badge>
              </CardTitle>
            </CardHeader>
            <CardContent className="space-y-4">
              <div
                data-testid="rag-answer-text"
                className="p-4 rounded-md border bg-muted/20 text-sm text-foreground leading-relaxed whitespace-pre-wrap"
              >
                {generationResult.answer}
              </div>

              {/* Citations Shelf */}
              <div className="space-y-3 pt-2">
                <h4 className="text-xs font-semibold text-foreground flex items-center gap-1.5 uppercase tracking-wider">
                  <BookOpen className="h-3.5 w-3.5 text-primary" />
                  Verifiable Citations ({generationResult.citations?.length || 0})
                </h4>

                {(!generationResult.citations || generationResult.citations.length === 0) ? (
                  <p className="text-xs text-muted-foreground italic">
                    No citation footnotes linked to this response.
                  </p>
                ) : (
                  <div className="grid grid-cols-1 md:grid-cols-2 gap-3">
                    {generationResult.citations.map((c, idx) => (
                      <div
                        key={c.chunk_id || idx}
                        onClick={() => setSelectedCitation(c)}
                        role="button"
                        tabIndex={0}
                        onKeyDown={(e) => {
                          if (e.key === "Enter" || e.key === " ") {
                            setSelectedCitation(c);
                          }
                        }}
                        className="p-3 rounded-lg border bg-card space-y-1.5 text-xs hover:border-primary/50 transition-colors cursor-pointer"
                      >
                        <div className="flex items-center justify-between">
                          <span className="font-mono font-bold text-primary">
                            [{c.index ?? idx + 1}] {c.source}
                          </span>
                          <span className="font-mono text-[10px] bg-muted px-1.5 py-0.5 rounded border">
                            conf: {typeof c.confidence === "number" ? c.confidence.toFixed(2) : c.confidence}
                          </span>
                        </div>

                        <p className="italic text-muted-foreground text-[11px] leading-relaxed border-l-2 pl-2 border-primary/40">
                          "{c.snippet}"
                        </p>

                        {c.chunk_id && (
                          <div className="text-[10px] font-mono text-muted-foreground/80 truncate pt-0.5">
                            chunk_id: {c.chunk_id}
                          </div>
                        )}
                      </div>
                    ))}
                  </div>
                )}
              </div>

              {/* Citation Verification Modal */}
              <Dialog
                open={Boolean(selectedCitation)}
                onOpenChange={(open) => !open && setSelectedCitation(null)}
              >
                <DialogContent className="max-w-lg">
                  <DialogHeader>
                    <DialogTitle>
                      Citation [{selectedCitation?.index ?? 1}] Verification Details
                    </DialogTitle>
                    <DialogDescription>
                      Source: {selectedCitation?.source} • Confidence:{" "}
                      {typeof selectedCitation?.confidence === "number"
                        ? selectedCitation.confidence.toFixed(2)
                        : selectedCitation?.confidence}
                    </DialogDescription>
                  </DialogHeader>

                  {selectedCitation && (
                    <div className="space-y-4 py-2 text-xs">
                      {(() => {
                        const grounding = generationResult?.grounding as
                          | {
                              claims?: Array<{
                                claim_text?: string;
                                reasoning?: string;
                                supporting_chunk_ids?: string[];
                              }>;
                            }
                          | undefined;
                        const claim = grounding?.claims?.find(
                          (cl) =>
                            cl.supporting_chunk_ids?.includes(selectedCitation.chunk_id || "") ||
                            cl.reasoning
                        );
                        return claim?.reasoning ? (
                          <div className="p-3 rounded-lg border bg-emerald-50/50 border-emerald-200 dark:bg-emerald-950/20 dark:border-emerald-800 space-y-1">
                            <span className="font-semibold text-emerald-800 dark:text-emerald-300 block">
                              Entailment Verification Reasoning
                            </span>
                            <p className="text-foreground">{claim.reasoning}</p>
                          </div>
                        ) : null;
                      })()}

                      <div className="space-y-1.5">
                        <span className="font-semibold text-muted-foreground block uppercase text-[10px] tracking-wider">
                          Attributed Passage Snippet
                        </span>
                        <div className="p-3 rounded border bg-muted/20 font-serif italic text-foreground leading-relaxed">
                          "{selectedCitation.snippet}"
                        </div>
                      </div>

                      <div className="grid grid-cols-2 gap-2 text-[11px] p-2 rounded bg-muted/30">
                        <div>
                          <span className="text-muted-foreground block">Chunk Identifier</span>
                          <span className="font-mono font-medium">{selectedCitation.chunk_id || "N/A"}</span>
                        </div>
                        <div>
                          <span className="text-muted-foreground block">Origin Source</span>
                          <span className="font-mono font-medium truncate">{selectedCitation.source}</span>
                        </div>
                      </div>
                    </div>
                  )}
                </DialogContent>
              </Dialog>

              {/* Claim Entailment Verification Breakdown if reported */}
              {Boolean(generationResult.grounding && typeof generationResult.grounding === "object") ? (
                <div className="border-t pt-4 space-y-2">
                  <h4 className="text-xs font-semibold text-foreground flex items-center gap-1.5">
                    <ShieldCheck className="h-3.5 w-3.5 text-emerald-600" />
                    Claim-Level Grounding Verification
                  </h4>
                  {Array.isArray((generationResult.grounding as { claims?: Array<{ claim_text: string; entailment: string }> }).claims) && (
                    <div className="space-y-1.5 max-h-40 overflow-y-auto">
                      {(generationResult.grounding as { claims: Array<{ claim_text: string; entailment: string }> }).claims.map((claim, idx) => (
                        <div
                          key={idx}
                          className="flex items-center justify-between p-2 rounded border bg-muted/20 text-xs"
                        >
                          <span className="truncate max-w-md">{claim.claim_text}</span>
                          <Badge
                            variant={claim.entailment === "SUPPORTED" ? "secondary" : "destructive"}
                            className="font-mono text-[10px]"
                          >
                            {claim.entailment}
                          </Badge>
                        </div>
                      ))}
                    </div>
                  )}
                </div>
              ) : null}
            </CardContent>
          </Card>
        </div>
      )}
    </div>
  );
}
