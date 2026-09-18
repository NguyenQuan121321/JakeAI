/**
 * Grounded Citations Shelf
 *
 * Displays verifiable reference chips beneath assistant responses.
 * Clicking a chip opens the authoritative inspection modal.
 */

import { useState } from "react";
import { BookOpen, ExternalLink } from "lucide-react";
import { CitationDialog } from "./citation-dialog";
import type { Citation } from "@/types/chat";

interface CitationShelfProps {
  citations: Citation[];
}

export function CitationShelf({ citations }: CitationShelfProps) {
  const [activeCitation, setActiveCitation] = useState<Citation | null>(null);

  if (!citations || citations.length === 0) {
    return null;
  }

  return (
    <div className="mt-3 border-t border-border/60 pt-2.5">
      <div className="flex items-center space-x-1.5 mb-2 text-xs font-semibold text-muted-foreground">
        <BookOpen className="h-3.5 w-3.5 text-primary" />
        <span>Grounded Sources & Citations ({citations.length})</span>
      </div>

      <div className="flex flex-wrap gap-1.5">
        {citations.map((cite, index) => {
          const confidencePct = Math.round((cite.confidence || 1.0) * 100);
          return (
            <button
              key={`${cite.source}-${index}`}
              type="button"
              onClick={() => setActiveCitation(cite)}
              className="group inline-flex items-center space-x-1.5 rounded-full border border-primary/20 bg-primary/5 hover:bg-primary/10 px-2.5 py-1 text-xs font-medium text-primary transition-colors focus:outline-none focus:ring-2 focus:ring-primary/40"
              title={`Inspect source: ${cite.source}`}
              aria-label={`Inspect citation ${index + 1}: ${cite.source}`}
            >
              <span className="font-semibold">[{cite.index || index + 1}]</span>
              <span className="max-w-[140px] truncate">{cite.source || "FinnApiGo"}</span>
              <span className="text-[10px] opacity-75">({confidencePct}%)</span>
              <ExternalLink className="h-2.5 w-2.5 opacity-60 group-hover:opacity-100 shrink-0" />
            </button>
          );
        })}
      </div>

      {/* Inspect Modal Dialog */}
      <CitationDialog
        citation={activeCitation}
        open={Boolean(activeCitation)}
        onOpenChange={(open) => {
          if (!open) setActiveCitation(null);
        }}
      />
    </div>
  );
}
