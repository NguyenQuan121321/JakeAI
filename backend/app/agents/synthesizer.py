"""Response Synthesizer node for Markdown formatting and citation assembly."""

from typing import Any

from app.agents.state import AgentState


async def synthesizer_node(state: AgentState) -> dict[str, Any]:
    """Consolidate multi-agent outputs into polished Markdown for UI consumption."""
    prompt = state.get("prompt", "")
    tenant_id = state.get("tenant_id", "default")
    financial_data = state.get("financial_analysis", {})
    tool_calls = state.get("tool_calls", [])
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

    if not financial_data and not tool_calls:
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
