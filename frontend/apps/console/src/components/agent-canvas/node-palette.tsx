import * as React from "react";
import {
  Bot,
  Cpu,
  Database,
  Wrench,
  ShieldCheck,
  AlertTriangle,
  CheckCircle2,
  Target,
  Search,
  Layers,
  Sparkles,
  Info,
} from "lucide-react";
import { Input } from "@/components/ui/input";
import { Badge } from "@/components/ui/badge";
import { Button } from "@/components/ui/button";
import { cn } from "@/lib/utils";
import type { CanvasNodeType } from "@/types/agent-graph";

interface PaletteItem {
  id: string;
  name: string;
  category: CanvasNodeType;
  sublabel: string;
  description: string;
  risk?: "safe" | "normal" | "sensitive" | "dangerous";
  capabilities?: string[];
}

const PALETTE_ITEMS: PaletteItem[] = [
  // Task
  {
    id: "pal-task",
    name: "Task Objective",
    category: "task",
    sublabel: "TaskSpec",
    description: "Multi-tenant problem statement and operational boundaries.",
  },
  // Agents
  {
    id: "pal-agent-sup",
    name: "Supervisor Agent",
    category: "agent",
    sublabel: "supervisor",
    description: "High-level goal decomposition and specialist dispatching.",
    capabilities: ["supervision", "planning"],
  },
  {
    id: "pal-agent-fin",
    name: "Financial Specialist",
    category: "agent",
    sublabel: "financial_specialist",
    description: "Quantitative EBITDA, margin, and variance computation.",
    capabilities: ["financial_analysis"],
  },
  {
    id: "pal-agent-bank",
    name: "FinnApiGo Specialist",
    category: "agent",
    sublabel: "finnapigo_specialist",
    description: "Direct banking ledger interactions via authenticated tokens.",
    capabilities: ["banking_api"],
  },
  {
    id: "pal-agent-rag",
    name: "RAG Retrieval Specialist",
    category: "agent",
    sublabel: "retrieval_specialist",
    description: "Hybrid dense & sparse query execution over vector stores.",
    capabilities: ["rag_retrieval"],
  },
  {
    id: "pal-agent-react",
    name: "General ReAct Agent",
    category: "agent",
    sublabel: "general_agent",
    description: "Autonomous reasoning and multi-step tool problem solver.",
    capabilities: ["general_reasoning", "code_execution"],
  },
  // Models
  {
    id: "pal-model-flash",
    name: "Gemini 1.5 Flash",
    category: "model",
    sublabel: "gemini-1.5-flash",
    description: "Sub-second low latency model for classification & routing.",
  },
  {
    id: "pal-model-pro",
    name: "Gemini 1.5 Pro",
    category: "model",
    sublabel: "gemini-1.5-pro",
    description: "Deep reasoning model for complex financial synthesis.",
  },
  {
    id: "pal-model-gpt4o",
    name: "GPT-4o",
    category: "model",
    sublabel: "gpt-4o",
    description: "Omni model for code execution and structured validation.",
  },
  // RAG
  {
    id: "pal-rag-hybrid",
    name: "Hybrid Qdrant + BM25",
    category: "rag",
    sublabel: "vector_collection",
    description: "Reciprocal rank fused retrieval with cross-encoder reranking.",
  },
  // Tools
  {
    id: "pal-tool-balance",
    name: "Get Account Balance",
    category: "tool",
    sublabel: "get_account_balance",
    description: "Queries authoritative bank balance for authenticated tenant.",
    risk: "normal",
  },
  {
    id: "pal-tool-txns",
    name: "List Transactions",
    category: "tool",
    sublabel: "list_transactions",
    description: "Retrieves recent audited transaction logs.",
    risk: "normal",
  },
  {
    id: "pal-tool-calc",
    name: "Precision Calculator",
    category: "tool",
    sublabel: "calculator",
    description: "Deterministic math engine preventing float hallucinations.",
    risk: "safe",
  },
  {
    id: "pal-tool-search",
    name: "Symbol & Doc Search",
    category: "tool",
    sublabel: "search_symbols",
    description: "In-memory AST and lexical document symbol index.",
    risk: "safe",
  },
  {
    id: "pal-tool-shell",
    name: "Dangerous Shell Execution",
    category: "tool",
    sublabel: "mock_dangerous_shell",
    description: "Simulated sensitive command requiring human approval gate.",
    risk: "dangerous",
  },
  // Verification
  {
    id: "pal-verif-invariants",
    name: "Canonical Verifier",
    category: "verification",
    sublabel: "verifier",
    description: "Audits mathematical invariants, tenant boundaries, and grounding.",
  },
  // Approval
  {
    id: "pal-approval",
    name: "Human Approval Gate",
    category: "approval",
    sublabel: "HITL_Gate",
    description: "Operator sign-off checkpoint pausing execution until authorized.",
  },
  // Result
  {
    id: "pal-result",
    name: "Synthesis & Result",
    category: "result",
    sublabel: "final_output",
    description: "Consolidated verified output with citations and metrics.",
  },
];

const CATEGORY_ICONS: Record<CanvasNodeType, React.ElementType> = {
  task: Target,
  agent: Bot,
  model: Cpu,
  rag: Database,
  tool: Wrench,
  verification: ShieldCheck,
  approval: AlertTriangle,
  result: CheckCircle2,
};

interface NodePaletteProps {
  onSelectTopology: (topology: "supervisor" | "rag" | "react") => void;
  activeTopology: "supervisor" | "rag" | "react";
  onInspectItem?: (item: PaletteItem) => void;
}

export const NodePalette: React.FC<NodePaletteProps> = ({
  onSelectTopology,
  activeTopology,
  onInspectItem,
}) => {
  const [search, setSearch] = React.useState("");
  const [selectedCategory, setSelectedCategory] = React.useState<string>("all");

  const filteredItems = React.useMemo(() => {
    return PALETTE_ITEMS.filter((item) => {
      const matchesSearch =
        item.name.toLowerCase().includes(search.toLowerCase()) ||
        item.sublabel.toLowerCase().includes(search.toLowerCase()) ||
        item.description.toLowerCase().includes(search.toLowerCase());
      const matchesCategory =
        selectedCategory === "all" || item.category === selectedCategory;
      return matchesSearch && matchesCategory;
    });
  }, [search, selectedCategory]);

  return (
    <div className="flex flex-col h-full bg-card border-r w-72 flex-shrink-0 select-none">
      {/* Header */}
      <div className="p-3.5 border-b space-y-3">
        <div className="flex items-center justify-between">
          <div className="flex items-center gap-2">
            <Layers className="h-4 w-4 text-primary" />
            <h2 className="text-xs font-bold uppercase tracking-wider">Node Palette</h2>
          </div>
          <Badge variant="outline" className="text-[10px] font-mono">
            {PALETTE_ITEMS.length} types
          </Badge>
        </div>

        {/* Topologies Quick Selector */}
        <div className="space-y-1.5">
          <span className="text-[10px] text-muted-foreground font-medium block">
            Topologies
          </span>
          <div className="grid grid-cols-3 gap-1">
            <Button
              variant={activeTopology === "supervisor" ? "default" : "outline"}
              size="sm"
              className="text-[10px] h-7 px-1.5"
              onClick={() => onSelectTopology("supervisor")}
            >
              Supervisor
            </Button>
            <Button
              variant={activeTopology === "rag" ? "default" : "outline"}
              size="sm"
              className="text-[10px] h-7 px-1.5"
              onClick={() => onSelectTopology("rag")}
            >
              RAG
            </Button>
            <Button
              variant={activeTopology === "react" ? "default" : "outline"}
              size="sm"
              className="text-[10px] h-7 px-1.5"
              onClick={() => onSelectTopology("react")}
            >
              ReAct
            </Button>
          </div>
        </div>

        {/* Search */}
        <div className="relative">
          <Search className="absolute left-2.5 top-2.5 h-3.5 w-3.5 text-muted-foreground" />
          <Input
            placeholder="Filter nodes or tools..."
            value={search}
            onChange={(e) => setSearch(e.target.value)}
            className="pl-8 h-8 text-xs bg-background"
          />
        </div>

        {/* Category Pills */}
        <div className="flex gap-1 overflow-x-auto pb-1 text-[10px] scrollbar-thin">
          {["all", "agent", "tool", "model", "rag", "verification", "approval"].map((cat) => (
            <button
              key={cat}
              onClick={() => setSelectedCategory(cat)}
              className={cn(
                "px-2 py-0.5 rounded capitalize whitespace-nowrap transition-colors",
                selectedCategory === cat
                  ? "bg-primary text-primary-foreground font-medium"
                  : "bg-muted text-muted-foreground hover:bg-accent"
              )}
            >
              {cat}
            </button>
          ))}
        </div>
      </div>

      {/* Item List */}
      <div className="flex-1 overflow-y-auto p-2.5 space-y-1.5">
        {filteredItems.map((item) => {
          const Icon = CATEGORY_ICONS[item.category] || Sparkles;
          return (
            <div
              key={item.id}
              onClick={() => onInspectItem?.(item)}
              className="group p-2.5 rounded-lg border border-transparent hover:border-border hover:bg-accent/40 cursor-pointer transition-all duration-150"
            >
              <div className="flex items-start gap-2.5">
                <div className="p-1.5 rounded-md bg-muted/70 group-hover:bg-primary/10 transition-colors mt-0.5">
                  <Icon className="h-3.5 w-3.5 text-muted-foreground group-hover:text-primary transition-colors" />
                </div>
                <div className="flex-1 min-w-0">
                  <div className="flex items-center justify-between gap-1">
                    <span className="text-xs font-semibold truncate group-hover:text-primary transition-colors">
                      {item.name}
                    </span>
                    {item.risk === "dangerous" && (
                      <Badge variant="destructive" className="text-[9px] px-1 py-0 h-4">
                        Approval
                      </Badge>
                    )}
                  </div>
                  <span className="text-[10px] font-mono text-muted-foreground block truncate">
                    {item.sublabel}
                  </span>
                  <p className="text-[11px] text-muted-foreground line-clamp-2 mt-1 leading-snug">
                    {item.description}
                  </p>
                </div>
              </div>
            </div>
          );
        })}

        {filteredItems.length === 0 && (
          <div className="text-center py-8 text-xs text-muted-foreground">
            No matching nodes found.
          </div>
        )}
      </div>

      {/* Footer Info Note */}
      <div className="p-2.5 border-t bg-muted/20 text-[10px] text-muted-foreground flex items-center gap-1.5">
        <Info className="h-3.5 w-3.5 flex-shrink-0 text-muted-foreground" />
        <span>Canvas mirrors backend state deterministically.</span>
      </div>
    </div>
  );
};
