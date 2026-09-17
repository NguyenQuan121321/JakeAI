import * as React from "react";
import { Check, Copy } from "lucide-react";
import { cn } from "@/lib/utils";

export interface CodeBlockProps {
  code: string;
  language?: string;
  title?: string;
  showLineNumbers?: boolean;
  className?: string;
}

export function CodeBlock({
  code,
  language = "json",
  title,
  showLineNumbers = false,
  className,
}: CodeBlockProps) {
  const [copied, setCopied] = React.useState(false);

  const handleCopy = async () => {
    try {
      await navigator.clipboard.writeText(code);
      setCopied(true);
      setTimeout(() => setCopied(false), 2000);
    } catch {
      // Fallback
      setCopied(false);
    }
  };

  const lines = code.trim().split("\n");

  return (
    <div className={cn("relative rounded-lg border bg-muted/70 font-mono text-sm shadow-sm overflow-hidden", className)}>
      <div className="flex items-center justify-between border-b bg-muted/90 px-4 py-1.5 text-xs text-muted-foreground">
        <div className="flex items-center space-x-2">
          {title && <span className="font-semibold text-foreground">{title}</span>}
          {language && (
            <span className="rounded bg-background px-1.5 py-0.5 text-[10px] uppercase font-bold tracking-wider">
              {language}
            </span>
          )}
        </div>
        <button
          type="button"
          onClick={handleCopy}
          aria-label={copied ? "Copied to clipboard" : "Copy code"}
          className="flex items-center space-x-1 rounded p-1 hover:bg-background/80 hover:text-foreground transition-colors focus:outline-none focus:ring-1 focus:ring-ring"
        >
          {copied ? (
            <>
              <Check className="h-3.5 w-3.5 text-emerald-500" />
              <span className="text-[11px] text-emerald-500">Copied</span>
            </>
          ) : (
            <>
              <Copy className="h-3.5 w-3.5" />
              <span className="text-[11px]">Copy</span>
            </>
          )}
        </button>
      </div>
      <div className="overflow-x-auto p-4 text-xs">
        {showLineNumbers ? (
          <table className="w-full border-collapse">
            <tbody>
              {lines.map((line, idx) => (
                <tr key={idx} className="hover:bg-muted/40">
                  <td className="w-8 select-none pr-4 text-right text-muted-foreground/60 align-top">
                    {idx + 1}
                  </td>
                  <td className="text-foreground whitespace-pre">{line}</td>
                </tr>
              ))}
            </tbody>
          </table>
        ) : (
          <pre className="text-foreground whitespace-pre">{code.trim()}</pre>
        )}
      </div>
    </div>
  );
}
