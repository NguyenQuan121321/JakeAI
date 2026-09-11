"""Deterministic Workload Classification Engine for Intelligent Model Routing (COST-09).

Classifies inference requests across seven workload domains:
1. simple_chat: Fast conversational queries without technical or tool dependencies.
2. coding: Software engineering, code generation, refactoring, and debugging.
3. reasoning: Mathematical, logical, multi-step analytical, and financial reasoning.
4. rag: Retrieval-augmented generation with external grounding documents.
5. structured_json: JSON Schema compliance and structured extraction.
6. long_context: Document synthesis spanning large context windows.
7. general: Standard multi-turn queries.

Computes:
- Workload domain
- Minimum required capabilities (e.g. supports_tools, supports_json, supports_reasoning)
- Target quality requirement threshold (0.0 - 1.0)
- Target latency in ms
- Context requirement in estimated tokens
- Verifiable classification reasons
"""

from __future__ import annotations

import json
import re
from typing import Any

from pydantic import BaseModel, Field

from app.optimizer.token_pruner import estimate_tokens


class WorkloadClassification(BaseModel):
    """Verifiable classification outcome for an incoming LLM request."""

    workload_class: str = Field(
        ...,
        description="Class: simple_chat, coding, reasoning, rag, structured_json, long_context, general",
    )
    required_capabilities: list[str] = Field(
        default_factory=list,
        description="Capabilities required: supports_tools, supports_json, supports_reasoning, supports_prompt_cache",
    )
    quality_requirement: float = Field(
        default=0.6,
        ge=0.0,
        le=1.0,
        description="Minimum model quality index (0.0 to 1.0) required to maintain task integrity",
    )
    latency_target_ms: int | None = Field(
        default=None,
        description="Target latency threshold in milliseconds",
    )
    context_requirement: int = Field(
        default=0,
        ge=0,
        description="Estimated token context requirement of prompt and conversation history",
    )
    confidence: float = Field(
        default=1.0,
        ge=0.0,
        le=1.0,
        description="Confidence score in the classification outcome",
    )
    reasons: list[str] = Field(
        default_factory=list,
        description="Verifiable step-by-step reasoning for the classification decision",
    )


class WorkloadClassifier:
    """Deterministic, policy-compliant request classifier."""

    _REASONING_PATTERNS = re.compile(
        r"\b(?:step[- ]by[- ]step|think carefully|prove|derivation|derive|"
        r"differential equation|integral|theorem|matrix multiplication|solve for [a-z]|"
        r"chain of thought|calculate (?:the )?(?:dcf|irr|wacc|ebitda|margin|probability)|"
        r"balance sheet|financial statement analysis|logical deduction|counterfactual)\b",
        re.IGNORECASE,
    )

    _CODING_PATTERNS = re.compile(
        r"(?:```[a-zA-Z]*\n|def\s+[a-zA-Z_]\w*\(|class\s+[a-zA-Z_]\w*[:\(]|"
        r"import\s+[a-zA-Z_]\w*|from\s+[a-zA-Z_]\w*\s+import|SELECT\s+.*FROM|"
        r"function\s+[a-zA-Z_]\w*\(|const\s+[a-zA-Z_]\w*\s*=|public\s+(?:static\s+)?void|"
        r"Traceback \(most recent call last\):|TypeError:|ValueError:)",
        re.MULTILINE,
    )

    _RAG_PATTERNS = re.compile(
        r"(?:\[Document\s+\d+\]|\[Retrieved Chunk|Source:\s*http|References?:|\bCitations?:)",
        re.IGNORECASE,
    )

    _SIMPLE_CHAT_KEYWORDS = {
        "hello",
        "hi",
        "hey",
        "greetings",
        "good morning",
        "good afternoon",
        "good evening",
        "how are you",
        "who are you",
        "what is your name",
        "tell me a joke",
        "thank you",
        "thanks",
        "bye",
        "goodbye",
    }

    def classify(
        self,
        prompt: str,
        messages: list[dict[str, Any]] | list[Any] | None = None,
        tools: list[dict[str, Any]] | None = None,
        response_format: dict[str, Any] | str | None = None,
    ) -> WorkloadClassification:
        """Classify request inputs into verifiable WorkloadClassification."""
        reasons: list[str] = []
        required_caps: list[str] = []

        # 1. Aggregate full text to measure context tokens and inspect features
        full_text_chunks: list[str] = [prompt] if prompt else []
        if messages:
            for m in messages:
                if isinstance(m, dict):
                    content = m.get("content")
                    if isinstance(content, str) and content:
                        full_text_chunks.append(content)
                elif hasattr(m, "content"):
                    c = getattr(m, "content", "")
                    if isinstance(c, str) and c:
                        full_text_chunks.append(c)

        aggregated_text = "\n".join(full_text_chunks).strip()
        context_tokens = estimate_tokens(aggregated_text) if aggregated_text else 0

        # Account for tool schemas in context size if present
        if tools:
            try:
                tools_json = json.dumps(tools)
                context_tokens += estimate_tokens(tools_json)
            except Exception:
                context_tokens += len(tools) * 50

        # 2. Check explicit structural requirements: Tools and Structured JSON
        has_tools = bool(tools)
        if tools:
            required_caps.append("supports_tools")
            reasons.append(
                f"Request provides {len(tools)} tool schemas; requires 'supports_tools'."
            )

        has_json_schema = bool(response_format)
        if has_json_schema:
            required_caps.append("supports_json")
            reasons.append(
                "Request specifies response_format; requires 'supports_json'."
            )

        # 3. Domain Pattern Detection
        is_reasoning = bool(self._REASONING_PATTERNS.search(aggregated_text))
        is_coding = bool(self._CODING_PATTERNS.search(aggregated_text))
        is_rag = bool(self._RAG_PATTERNS.search(aggregated_text))
        is_long_context = context_tokens >= 12_000

        # 4. Resolve Primary Workload Class & Quality Requirement
        workload_class = "general"
        quality_req = 0.65
        latency_target_ms: int | None = 2000

        if is_reasoning:
            workload_class = "reasoning"
            required_caps.append("supports_reasoning")
            quality_req = 0.90
            latency_target_ms = 8000
            reasons.append("Analytical / mathematical reasoning triggers detected.")
        elif is_coding:
            workload_class = "coding"
            quality_req = 0.85
            latency_target_ms = 3000
            reasons.append("Code syntax or development artifacts detected.")
        elif is_long_context:
            workload_class = "long_context"
            quality_req = 0.80
            latency_target_ms = 5000
            reasons.append(
                f"Context length ({context_tokens} tokens) exceeds long_context threshold."
            )
        elif is_rag:
            workload_class = "rag"
            quality_req = 0.75
            latency_target_ms = 2500
            reasons.append("Retrieved grounding documents / citations present.")
        elif has_json_schema and not has_tools:
            workload_class = "structured_json"
            quality_req = 0.70
            latency_target_ms = 1500
            reasons.append("Structured output extraction without complex reasoning.")
        elif has_tools:
            workload_class = "tool_calling"
            quality_req = 0.75
            latency_target_ms = 2000
            reasons.append("Tool execution workflow active.")
        else:
            # Check for simple_chat
            words = prompt.strip().split()
            word_count = len(words)
            prompt_lower = prompt.strip().lower()

            is_greeting = any(
                prompt_lower == kw or prompt_lower.startswith(kw)
                for kw in self._SIMPLE_CHAT_KEYWORDS
            )

            if (is_greeting or word_count <= 25) and not is_coding and not is_reasoning:
                workload_class = "simple_chat"
                quality_req = 0.40
                latency_target_ms = 800
                reasons.append(
                    f"Short conversational query ({word_count} words) without technical dependencies -> simple_chat."
                )
            else:
                workload_class = "general"
                quality_req = 0.65
                latency_target_ms = 2000
                reasons.append("Standard multi-turn query classified as general.")

        # Ensure unique required capabilities while preserving order
        unique_caps: list[str] = []
        for cap in required_caps:
            if cap not in unique_caps:
                unique_caps.append(cap)

        return WorkloadClassification(
            workload_class=workload_class,
            required_capabilities=unique_caps,
            quality_requirement=quality_req,
            latency_target_ms=latency_target_ms,
            context_requirement=context_tokens,
            confidence=0.95,
            reasons=reasons,
        )


_classifier: WorkloadClassifier | None = None


def get_workload_classifier() -> WorkloadClassifier:
    """Retrieve singleton WorkloadClassifier."""
    global _classifier
    if _classifier is None:
        _classifier = WorkloadClassifier()
    return _classifier
