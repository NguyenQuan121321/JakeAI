/**
 * Business-friendly Workspace Empty State Component
 *
 * Welcomes users with JakeAI platform capabilities and
 * one-click starter suggestion prompts.
 */

import { Bot, Sparkles, TrendingUp, ShieldCheck, Database, Wrench } from "lucide-react";
import { Card } from "@/components/ui/card";

interface WorkspaceEmptyStateProps {
  onSelectPrompt: (prompt: string) => void;
  isStreaming?: boolean;
}

const STARTER_PROMPTS = [
  {
    title: "Financial Ratio & EBITDA Analysis",
    prompt: "Calculate EBITDA and analyze corporate financial liquidity ratios",
    icon: TrendingUp,
    description: "Evaluates cash flows, solvency, and liquidity with financial specialists",
  },
  {
    title: "Platform Capabilities & Models",
    prompt: "Hello JakeAI, summarize current platform capabilities and supported providers",
    icon: Sparkles,
    description: "Multi-agent LangGraph orchestration across Gemini, OpenAI, and Anthropic",
  },
  {
    title: "Enterprise Tool & Ledger Inspection",
    prompt: "Inspect current account balance and list recent ledger transactions",
    icon: Wrench,
    description: "Invokes authenticated FinnApiGo tool bridge with RBAC guardrails",
  },
  {
    title: "Knowledge Base & Grounded Citations",
    prompt: "Explain corporate expense reimbursement policies with verified citations",
    icon: Database,
    description: "Retrieves evidence from tenant vector store and verifies claims",
  },
];

export function WorkspaceEmptyState({
  onSelectPrompt,
  isStreaming = false,
}: WorkspaceEmptyStateProps) {
  return (
    <div className="flex flex-col items-center justify-center p-6 text-center max-w-2xl mx-auto my-auto py-12">
      <div className="flex h-12 w-12 items-center justify-center rounded-2xl bg-primary/10 text-primary mb-4 border border-primary/20 shadow-sm">
        <Bot className="h-6 w-6" />
      </div>

      <h1 className="text-xl font-bold tracking-tight text-foreground sm:text-2xl">
        JakeAI Orchestration Workspace
      </h1>
      <p className="mt-2 text-sm text-muted-foreground max-w-lg leading-relaxed">
        Enterprise multi-agent AI assistant backed by LangGraph execution, real-time tool bridges, and grounded Self-RAG verification.
      </p>

      {/* Feature Pills */}
      <div className="mt-4 flex flex-wrap items-center justify-center gap-2 text-xs text-muted-foreground">
        <span className="inline-flex items-center space-x-1 rounded-full border border-border bg-muted/30 px-3 py-1">
          <ShieldCheck className="h-3.5 w-3.5 text-emerald-500" />
          <span>Tenant Isolated</span>
        </span>
        <span className="inline-flex items-center space-x-1 rounded-full border border-border bg-muted/30 px-3 py-1">
          <Sparkles className="h-3.5 w-3.5 text-primary" />
          <span>Multi-Agent Planning</span>
        </span>
        <span className="inline-flex items-center space-x-1 rounded-full border border-border bg-muted/30 px-3 py-1">
          <Database className="h-3.5 w-3.5 text-blue-500" />
          <span>Grounded Citations</span>
        </span>
      </div>

      {/* Starter Prompts Grid */}
      <div className="mt-8 grid grid-cols-1 sm:grid-cols-2 gap-3 w-full text-left">
        {STARTER_PROMPTS.map((starter) => {
          const Icon = starter.icon;
          return (
            <Card
              key={starter.title}
              onClick={() => {
                if (!isStreaming) onSelectPrompt(starter.prompt);
              }}
              className="cursor-pointer border-border/70 hover:border-primary/50 hover:bg-muted/30 transition-all p-3.5 rounded-xl group"
              role="button"
              tabIndex={0}
              onKeyDown={(e) => {
                if (e.key === "Enter" || e.key === " ") {
                  if (!isStreaming) onSelectPrompt(starter.prompt);
                }
              }}
            >
              <div className="flex items-start space-x-3">
                <div className="flex h-8 w-8 items-center justify-center rounded-lg bg-primary/5 text-primary shrink-0 group-hover:bg-primary/10 transition-colors">
                  <Icon className="h-4 w-4" />
                </div>
                <div className="flex-1 min-w-0">
                  <h3 className="text-xs font-semibold text-foreground truncate group-hover:text-primary transition-colors">
                    {starter.title}
                  </h3>
                  <p className="text-[11px] text-muted-foreground mt-0.5 line-clamp-2">
                    {starter.description}
                  </p>
                </div>
              </div>
            </Card>
          );
        })}
      </div>
    </div>
  );
}
