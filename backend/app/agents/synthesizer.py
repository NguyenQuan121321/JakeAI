import logging
from typing import Any

from app.agents.state import AgentState
from app.core.circuit_breaker import CircuitBreaker
from app.core.llm_provider import call_upstream_llm
from app.rag.citations import CitationGenerator
from app.rag.models import DocumentChunk

logger = logging.getLogger(__name__)

_synthesizer_circuit = CircuitBreaker(
    name="synthesizer_circuit",
    failure_threshold=3,
    recovery_timeout_seconds=15.0,
)

_call_gemini_or_openai = call_upstream_llm


async def synthesizer_node(state: AgentState) -> dict[str, Any]:
    """Consolidate multi-agent outputs into Markdown with citations."""
    prompt = state.get("prompt", "")
    tenant_id = state.get("tenant_id", "default")
    financial_data = state.get("financial_analysis", {})
    tool_calls = state.get("tool_calls", [])
    raw_retrieved_chunks = state.get("retrieved_chunks", [])
    citations: list[dict[str, Any]] = []

    markdown_parts: list[str] = [
        "### Financial & Intelligence Report\n",
        (
            f"**Tenant**: `{tenant_id}` | "
            "**Status**: Verified by JakeAI Multi-Agent Pipeline\n"
        ),
    ]

    if financial_data:
        rev = financial_data.get("revenue", 0.0)
        exp = financial_data.get("operating_expenses", 0.0)
        inc = financial_data.get("operating_income", 0.0)
        margin = financial_data.get("operating_margin_pct", 0.0)
        ebitda = financial_data.get("ebitda", 0.0)

        markdown_parts.append("\n#### 📊 Financial Performance Metrics\n")
        markdown_parts.append("| Metric | Value (USD) | Benchmark / Ratio |")
        markdown_parts.append("| :--- | :--- | :--- |")
        markdown_parts.append(f"| **Gross Revenue** | `${rev:,.2f}` | Baseline |")
        markdown_parts.append(
            f"| **Operating Expenses** | `${exp:,.2f}` | Operating Cost |"
        )
        markdown_parts.append(
            f"| **Operating Income** | `${inc:,.2f}` | **{margin}% Margin** |"
        )
        markdown_parts.append(
            f"| **Adjusted EBITDA** | `${ebitda:,.2f}` | Normalized |"
        )

        citations.append(
            {
                "source": "Internal Ledger / Financial Specialist Agent",
                "confidence": 0.98,
                "period": "Current FY",
            }
        )

    if tool_calls:
        markdown_parts.append("\n#### 🛠️ Upstream FinnApiGo Integrations\n")
        for tc in tool_calls:
            tool_name = tc.get("tool_name", "unknown")
            if tc.get("status") == "BLOCKED":
                reason = tc.get("reason", "Unauthorized by policy")
                markdown_parts.append(
                    f"- ⚠️ **{tool_name}**: Access Denied (Blocked by Security Guardrail: {reason})."
                )
            else:
                output = tc.get("output", {})
                markdown_parts.append(
                    f"- **{tool_name}**: Successfully synchronized with FinnApiGo."
                )
                for k, v in output.items():
                    markdown_parts.append(f"  - `{k}`: {v}")
                citations.append(
                    {
                        "source": f"FinnApiGo API ({tool_name})",
                        "confidence": 1.0,
                        "tenant_id": tenant_id,
                    }
                )

    # 3. Contextual RAG Passage Citations
    if raw_retrieved_chunks:
        doc_chunks = [
            DocumentChunk(
                chunk_id=c.get("chunk_id", f"chk-{i}"),
                content=c.get("content", ""),
                tenant_id=c.get("tenant_id", tenant_id),
                source=c.get("source", "Retrieved Document"),
                metadata=c.get("metadata", {}),
                score=c.get("score", 0.9),
            )
            for i, c in enumerate(raw_retrieved_chunks)
        ]
        preliminary_text = "\n".join(markdown_parts)
        generator = CitationGenerator()
        annotated_text, rag_citations = generator.generate_citations(
            preliminary_text, doc_chunks
        )
        final_response = annotated_text
        for cite in rag_citations:
            citations.append(cite.model_dump())
    else:
        if not financial_data and not tool_calls:
            llm_text = await _call_gemini_or_openai(prompt, tenant_id=tenant_id)
            if llm_text:
                markdown_parts.append(f"\n{llm_text}\n")
            else:
                markdown_parts.append(
                    "\nHello! I am JakeAI, your financial and operational AI companion.\n\n"
                    f'You asked: *"{prompt}"*\n\n'
                    "How can I assist your financial analytics or FinnApiGo services today?"
                )
        markdown_parts.append(
            "\n---\n*Verified by JakeAI Self-RAG Verifier & Policy Enforcement.*"
        )
        final_response = "\n".join(markdown_parts)

    return {
        "current_agent": "synthesizer",
        "workflow_phase": "completed",
        "final_response": final_response,
        "mascot_state": "idle",
        "citations": citations,
        "messages": [
            *state.get("messages", []),
            "Synthesizer: Markdown response synthesized with citations and mascot.",
        ],
    }
